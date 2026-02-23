import argparse
import json
import logging
import random
import sys
import time
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from client import YugoClient, find_by_name
from matching import filter_room, get_weekly_price, is_ensuite, match_semester1
from models.config import Config, load_config
from notifier import notify, validate_notification_config

logger = logging.getLogger(__name__)


def configure_logging() -> None:
    logger_root = logging.getLogger()
    logger_root.setLevel(logging.INFO)
    formatter = logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")

    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(formatter)
    logger_root.addHandler(console_handler)


def resolve_country_id(client: YugoClient, config: Config, country: Optional[str], country_id: Optional[str]) -> Optional[str]:
    if country_id:
        return country_id
    if config.target.country_id:
        return config.target.country_id

    name = country or config.target.country
    if not name:
        return None
    countries = client.list_countries()
    match = find_by_name(countries, name)
    if match:
        country_id_value = match.get("countryId") or match.get("id")
        if country_id_value is not None:
            return str(country_id_value)
    return None


def resolve_city_id(
    client: YugoClient,
    config: Config,
    city: Optional[str],
    city_id: Optional[str],
    country: Optional[str],
    country_id: Optional[str],
) -> Optional[str]:
    if city_id:
        return city_id
    if config.target.city_id:
        return config.target.city_id

    name = city or config.target.city
    if not name:
        return None

    resolved_country_id = resolve_country_id(client, config, country, country_id)
    if not resolved_country_id:
        return None

    cities = client.list_cities(resolved_country_id)
    match = find_by_name(cities, name)
    if match:
        city_id_value = match.get("contentId") or match.get("id")
        if city_id_value is not None:
            return str(city_id_value)
    return None


def _to_js_date_string(date_str: str) -> str:
    dt = datetime.strptime(date_str, "%Y-%m-%d")
    # Backend-compatible format observed in booking-flow JS requests
    return dt.strftime("%a %b %d %Y 00:00:00 GMT+0000 (UTC)")


def format_record_message(record: Dict[str, Any]) -> str:
    weekly = get_weekly_price(record.get("roomData") or {})
    weekly_str = f"€{weekly:.2f}/week" if weekly is not None else (record.get("roomPriceLabel") or "N/A")
    ensuite = "yes" if is_ensuite(record.get("roomData") or {}) else "no"

    return (
        f"Residence: {record.get('residenceName', 'Unknown')}\n"
        f"Room: {record.get('roomName', 'Unknown')}\n"
        f"Ensuite: {ensuite}\n"
        f"Price: {weekly_str}\n"
        f"Tenancy: {record.get('optionName', 'Unknown')} ({record.get('optionStartDate', '')} -> {record.get('optionEndDate', '')})"
    )


def collect_matches(client: YugoClient, city_id: str, config: Config, apply_semester_filter: bool = True) -> Tuple[List[Dict[str, Any]], int]:
    residences = client.list_residences(city_id)
    matches: List[Dict[str, Any]] = []
    option_count = 0

    for residence in residences:
        residence_id = residence.get("id")
        residence_content_id = residence.get("contentId")
        if not residence_id or not residence_content_id:
            continue

        rooms = client.list_rooms(str(residence_id))
        for room in rooms:
            if not filter_room(room, config.filters):
                continue

            room_id = room.get("id")
            if not room_id:
                continue

            groups = client.list_tenancy_options(str(residence_id), str(residence_content_id), str(room_id))
            if not groups:
                continue

            for group in groups:
                options = group.get("tenancyOption") or []
                if not options:
                    continue

                option_count += len(options)

                for option in options:
                    option_wrapper = {
                        "fromYear": group.get("fromYear"),
                        "toYear": group.get("toYear"),
                        "tenancyOption": [option],
                    }

                    if apply_semester_filter and not match_semester1(option_wrapper, config.academic_year):
                        continue

                    matches.append(
                        {
                            "residenceId": str(residence_id),
                            "residenceContentId": str(residence_content_id),
                            "residenceName": residence.get("name"),
                            "residenceLocationInfo": residence.get("locationInfo"),
                            "residencePaymentLink": residence.get("paymentLink"),
                            "residencePortalLink": residence.get("portalLink"),
                            "roomId": str(room_id),
                            "roomName": room.get("name"),
                            "roomPriceLabel": room.get("priceLabel"),
                            "roomMaxNumOfBedsInFlat": room.get("maxNumOfBedsInFlat"),
                            "roomData": room,
                            "optionId": str(option.get("id")) if option.get("id") else None,
                            "optionName": option.get("name"),
                            "optionFormattedLabel": option.get("formattedLabel"),
                            "optionStartDate": option.get("startDate"),
                            "optionEndDate": option.get("endDate"),
                            "optionTenancyLength": option.get("tenancyLength"),
                            "optionStatus": option.get("status"),
                            "optionLinkToRedirect": option.get("linkToRedirect"),
                            "academicYearId": group.get("academicYearId"),
                            "fromYear": group.get("fromYear"),
                            "toYear": group.get("toYear"),
                        }
                    )

    return matches, option_count


def prioritize_matches(matches: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    def key(item: Dict[str, Any]):
        room = item.get("roomData") or {}
        ensuite_rank = 0 if is_ensuite(room) else 1
        weekly = get_weekly_price(room)
        weekly_rank = weekly if weekly is not None else float("inf")
        return (
            ensuite_rank,
            weekly_rank,
            str(item.get("residenceName") or ""),
            str(item.get("roomName") or ""),
            str(item.get("optionName") or ""),
        )

    return sorted(matches, key=key)


def probe_booking_flow(client: YugoClient, match: Dict[str, Any]) -> Dict[str, Any]:
    residence_content_id = match["residenceContentId"]

    # Warm booking session/cookies required by some booking endpoints
    warm = client.session.get(client.base_url + "booking-flow-page", params={"residenceContentId": residence_content_id}, timeout=client.timeout)
    warm.raise_for_status()

    property_data = client.get_residence_property(match["residenceId"])
    buildings = ((property_data.get("property") or {}).get("buildings") or [])
    building_ids = [b.get("id") for b in buildings if b.get("id")]

    floor_indexes_set = set()
    for building in buildings:
        for floor in building.get("floors") or []:
            try:
                floor_indexes_set.add(int(float(floor.get("index"))))
            except (TypeError, ValueError):
                continue
    floor_indexes = sorted(floor_indexes_set)

    if not building_ids or not floor_indexes:
        raise RuntimeError("Could not resolve building/floor metadata for booking probe.")

    start_date_js = _to_js_date_string(match["optionStartDate"])
    end_date_js = _to_js_date_string(match["optionEndDate"])

    common_params = {
        "roomTypeId": match["roomId"],
        "residenceExternalId": match["residenceId"],
        "tenancyOptionId": match["optionId"],
        "tenancyStartDate": start_date_js,
        "tenancyEndDate": end_date_js,
        "academicYearId": match["academicYearId"],
        "maxNumOfFlatmates": str(match.get("roomMaxNumOfBedsInFlat") or 7),
        "buildingIds": ",".join(building_ids),
        "floorIndexes": ",".join(str(i) for i in floor_indexes),
    }

    available_beds = client.get_available_beds(common_params)

    flats_with_beds_params = {
        **common_params,
        "sortDirection": "false",
        "pageNumber": "1",
        "pageSize": "6",
        "totalPriceOriginal": "0",
        "pricePerNightOriginal": str((match.get("roomData") or {}).get("minPricePerNight") or ""),
    }

    flats_with_beds = client.get_flats_with_beds(flats_with_beds_params)

    selected_bed_id = None
    selected_flat_id = None
    floors = ((flats_with_beds.get("flats") or {}).get("floors") or [])
    for floor in floors:
        for flat in floor.get("flats") or []:
            beds = flat.get("beds") or []
            if beds:
                selected_bed_id = beds[0].get("bedId") or beds[0].get("id")
                selected_flat_id = flat.get("id")
                break
        if selected_bed_id:
            break

    skip_room = client.get_skip_room_selection(common_params)

    handover_payload = {
        "roomTypeId": match["roomId"],
        "residenceExternalId": match["residenceId"],
        "tenancyOptionId": match["optionId"],
        "tenancyStartDate": start_date_js,
        "tenancyEndDate": end_date_js,
        "academicYearId": match["academicYearId"],
        "bedId": selected_bed_id or "",
        "flatId": selected_flat_id or "",
        "currencyCode": "EUR",
    }

    handover = client.post_student_portal_redirect(handover_payload)

    return {
        "match": {
            "residence": match.get("residenceName"),
            "room": match.get("roomName"),
            "tenancy": match.get("optionName"),
            "fromYear": match.get("fromYear"),
            "toYear": match.get("toYear"),
            "startDate": match.get("optionStartDate"),
            "endDate": match.get("optionEndDate"),
            "ensuite": is_ensuite(match.get("roomData") or {}),
            "weeklyPrice": get_weekly_price(match.get("roomData") or {}),
        },
        "bookingContext": {
            "commonParams": common_params,
            "selectedBedId": selected_bed_id,
            "selectedFlatId": selected_flat_id,
        },
        "apiResults": {
            "availableBeds": available_beds,
            "flatsWithBedsSummary": {
                "floorsReturned": len(floors),
                "hasPreferenceFilters": bool(((flats_with_beds.get("flats") or {}).get("preferenceFilters"))),
            },
            "skipRoomSelection": skip_room,
            "studentPortalRedirect": handover,
        },
        "links": {
            "skipRoomLink": skip_room.get("linkToRedirect"),
            "handoverLink": handover.get("linkToRedirect"),
            "portalLink": match.get("residencePortalLink"),
            "paymentLink": match.get("residencePaymentLink"),
        },
    }


def build_alert_message(ranked_matches: List[Dict[str, Any]], probe: Optional[Dict[str, Any]] = None) -> str:
    top = ranked_matches[0]
    top_weekly = get_weekly_price(top.get("roomData") or {})
    top_weekly_str = f"€{top_weekly:.2f}/week" if top_weekly is not None else (top.get("roomPriceLabel") or "N/A")
    top_ensuite = "✅" if is_ensuite(top.get("roomData") or {}) else "❌"

    lines = [
        "🚨 YUGO ALERT · Semester 1 detectado",
        "",
        "⭐ Opción prioritaria:",
        f"- Residencia: {top.get('residenceName')}",
        f"- Habitación: {top.get('roomName')}",
        f"- Ensuite: {top_ensuite}",
        f"- Precio: {top_weekly_str}",
        f"- Fechas: {top.get('optionStartDate')} → {top.get('optionEndDate')}",
        f"- Tenancy: {top.get('optionName')}",
    ]

    if probe:
        if probe.get("links", {}).get("skipRoomLink"):
            lines.append(f"- Link reserva: {probe['links']['skipRoomLink']}")
        elif probe.get("links", {}).get("handoverLink"):
            lines.append(f"- Link reserva: {probe['links']['handoverLink']}")

    if len(ranked_matches) > 1:
        lines.extend(["", "Alternativas (top 5):"])
        for idx, item in enumerate(ranked_matches[:5], start=1):
            w = get_weekly_price(item.get("roomData") or {})
            w_str = f"€{w:.2f}/week" if w is not None else (item.get("roomPriceLabel") or "N/A")
            en = "ensuite" if is_ensuite(item.get("roomData") or {}) else "no-ensuite"
            lines.append(
                f"{idx}. {item.get('residenceName')} | {item.get('roomName')} | {en} | {w_str} | {item.get('optionName')}"
            )

    return "\n".join(lines)


def build_reservation_job_prompt(probe: Dict[str, Any], reservation_mode: str) -> str:
    link = probe.get("links", {}).get("skipRoomLink") or probe.get("links", {}).get("handoverLink")
    mode = reservation_mode.lower().strip()
    if mode not in {"assist", "autobook"}:
        mode = "assist"

    guardrail = (
        "Do NOT submit irreversible payment actions. Stop at final confirmation and notify Gonzalo."
        if mode == "assist"
        else "Attempt full booking flow. If payment confirmation is required, notify Gonzalo immediately before final submit."
    )

    return (
        "You are a reservation execution agent.\n\n"
        "A Yugo Semester 1 option was detected.\n"
        f"Primary booking link: {link}\n\n"
        "Steps:\n"
        "1) Open the booking link in browser.\n"
        "2) Complete the reservation flow as far as possible.\n"
        "3) Keep all details consistent with detected tenancy (dates/option).\n"
        f"4) {guardrail}\n"
        "5) Send a concise status update to Gonzalo at the end."
    )


def handle_discover(args: argparse.Namespace, config: Config) -> int:
    client = YugoClient()

    if args.countries:
        countries = client.list_countries()
        if args.json:
            print(json.dumps(countries, ensure_ascii=False, indent=2))
        else:
            for item in countries:
                print(f"{item.get('countryId') or item.get('id')}\t{item.get('name')}")
        return 0

    if args.cities:
        country_id = resolve_country_id(client, config, args.country, args.country_id)
        if not country_id:
            print("Country id is required (or set target.country/target.country_id in config.yaml).")
            return 2
        cities = client.list_cities(country_id)
        if args.json:
            print(json.dumps(cities, ensure_ascii=False, indent=2))
        else:
            for item in cities:
                print(f"{item.get('contentId') or item.get('id')}\t{item.get('name')}")
        return 0

    if args.residences:
        city_id = resolve_city_id(client, config, args.city, args.city_id, args.country, args.country_id)
        if not city_id:
            print("City id is required (or set target.city/target.city_id in config.yaml).")
            return 2
        residences = client.list_residences(city_id)
        if args.json:
            print(json.dumps(residences, ensure_ascii=False, indent=2))
        else:
            for item in residences:
                print(f"{item.get('id')}\t{item.get('name')}")
        return 0

    print("No discover target provided. Use --countries, --cities, or --residences.")
    return 2


def handle_scan(args: argparse.Namespace, config: Config) -> int:
    client = YugoClient()
    city_id = resolve_city_id(client, config, args.city, args.city_id, args.country, args.country_id)
    if not city_id:
        print("City id is required (or set target.city/target.city_id in config.yaml).")
        return 2

    matches, option_count = collect_matches(client, city_id, config, apply_semester_filter=not args.all_options)
    ranked = prioritize_matches(matches)

    if args.json:
        print(
            json.dumps(
                {
                    "scannedOptions": option_count,
                    "matchCount": len(matches),
                    "matches": ranked,
                },
                ensure_ascii=False,
                indent=2,
            )
        )
    else:
        if ranked:
            print("\n\n".join(format_record_message(match) for match in ranked[:10]))
        print(f"Scanned {option_count} tenancy options. Matches: {len(matches)}")

    if args.notify and ranked:
        error = validate_notification_config(config.notifications)
        if error:
            print(error)
            return 2

        probe = None
        try:
            probe = probe_booking_flow(client, ranked[0])
        except Exception as exc:
            logger.warning("Booking probe failed for notification payload: %s", exc)

        message = build_alert_message(ranked, probe)
        job_prompt = build_reservation_job_prompt(probe, config.notifications.openclaw.reservation_mode) if probe else None
        notify(message, config.notifications, reservation_job_prompt=job_prompt)

    return 0


def handle_watch(args: argparse.Namespace, config: Config) -> int:
    client = YugoClient()
    city_id = resolve_city_id(client, config, args.city, args.city_id, args.country, args.country_id)
    if not city_id:
        print("City id is required (or set target.city/target.city_id in config.yaml).")
        return 2

    interval = max(5, config.polling.interval_seconds)
    jitter = max(0, config.polling.jitter_seconds)
    print(f"Starting watch loop: interval={interval}s jitter={jitter}s")

    while True:
        matches, option_count = collect_matches(client, city_id, config)
        ranked = prioritize_matches(matches)
        logger.info("Scanned %s tenancy options. Matches: %s", option_count, len(matches))

        if ranked and config.notifications.openclaw.enabled:
            error = validate_notification_config(config.notifications)
            if not error:
                probe = None
                try:
                    probe = probe_booking_flow(client, ranked[0])
                except Exception as exc:
                    logger.warning("Booking probe failed in watch loop: %s", exc)

                message = build_alert_message(ranked, probe)
                job_prompt = build_reservation_job_prompt(probe, config.notifications.openclaw.reservation_mode) if probe else None
                notify(message, config.notifications, reservation_job_prompt=job_prompt)
            else:
                logger.error(error)

        sleep_for = interval + random.randint(0, jitter) if jitter else interval
        time.sleep(sleep_for)


def handle_test_match(args: argparse.Namespace, config: Config) -> int:
    option = {
        "fromYear": args.from_year,
        "toYear": args.to_year,
        "tenancyOption": [
            {
                "name": args.name,
                "formattedLabel": args.label,
                "startDate": args.start_date,
                "endDate": args.end_date,
            }
        ],
    }
    matched = match_semester1(option, config.academic_year)
    if args.json:
        print(json.dumps({"match": bool(matched)}, ensure_ascii=False))
    else:
        print("MATCH" if matched else "NO MATCH")
    return 0


def handle_notify(args: argparse.Namespace, config: Config) -> int:
    error = validate_notification_config(config.notifications)
    if error:
        print(error)
        return 2

    message = args.message or "Yugo notification test"
    notify(message, config.notifications)
    print("Notification dispatched (if enabled channels are configured).")
    return 0


def handle_probe_booking(args: argparse.Namespace, config: Config) -> int:
    client = YugoClient()
    city_id = resolve_city_id(client, config, args.city, args.city_id, args.country, args.country_id)
    if not city_id:
        print("City id is required (or set target.city/target.city_id in config.yaml).")
        return 2

    matches, _ = collect_matches(client, city_id, config, apply_semester_filter=not args.all_options)
    if not matches:
        print("No matches found with current semester/filter rules.")
        return 1

    def _contains(value: Optional[str], needle: Optional[str]) -> bool:
        if not needle:
            return True
        if not value:
            return False
        return needle.strip().lower() in value.strip().lower()

    candidates = [
        match
        for match in matches
        if _contains(match.get("residenceName"), args.residence)
        and _contains(match.get("roomName"), args.room)
        and _contains(match.get("optionName"), args.tenancy)
    ]
    candidates = prioritize_matches(candidates)

    if not candidates:
        print("No match candidates after applying residence/room/tenancy filters.")
        return 1

    idx = max(0, args.index)
    if idx >= len(candidates):
        print(f"Index {idx} out of range. Candidates: {len(candidates)}")
        return 2

    selected = candidates[idx]

    try:
        probe = probe_booking_flow(client, selected)
    except Exception as exc:
        print(f"Booking probe failed: {exc}")
        return 1

    if args.notify:
        error = validate_notification_config(config.notifications)
        if error:
            print(error)
            return 2
        message = build_alert_message(candidates, probe)
        job_prompt = build_reservation_job_prompt(probe, config.notifications.openclaw.reservation_mode)
        notify(message, config.notifications, reservation_job_prompt=job_prompt)

    if args.json:
        print(json.dumps(probe, ensure_ascii=False, indent=2))
    else:
        print("Booking probe OK")
        print(f"- Residence: {probe['match']['residence']}")
        print(f"- Room: {probe['match']['room']}")
        print(f"- Tenancy: {probe['match']['tenancy']} ({probe['match']['startDate']} -> {probe['match']['endDate']})")
        print(f"- Available beds: {(probe['apiResults']['availableBeds'].get('available-beds') or {}).get('count')}")
        print(f"- Skip-room link: {probe['links']['skipRoomLink']}")
        print(f"- Handover link: {probe['links']['handoverLink']}")

    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="yugo", description="Yugo CLI")
    parser.add_argument("--config", default="config.yaml", help="Path to YAML config.")

    subparsers = parser.add_subparsers(dest="command", required=True)

    discover = subparsers.add_parser("discover", help="List available countries, cities, or residences.")
    discover.add_argument("--countries", action="store_true", help="List countries.")
    discover.add_argument("--cities", action="store_true", help="List cities for a country.")
    discover.add_argument("--residences", action="store_true", help="List residences for a city.")
    discover.add_argument("--country", help="Country name to resolve.")
    discover.add_argument("--country-id", help="Country id to use.")
    discover.add_argument("--city", help="City name to resolve.")
    discover.add_argument("--city-id", help="City id to use.")
    discover.add_argument("--json", action="store_true", help="Output JSON.")

    scan = subparsers.add_parser("scan", help="Run a single scan against the Yugo API.")
    scan.add_argument("--country", help="Country name to resolve.")
    scan.add_argument("--country-id", help="Country id to use.")
    scan.add_argument("--city", help="City name to resolve.")
    scan.add_argument("--city-id", help="City id to use.")
    scan.add_argument("--all-options", action="store_true", help="Disable semester matching and return all options.")
    scan.add_argument("--notify", action="store_true", help="Send notification for top prioritized match.")
    scan.add_argument("--json", action="store_true", help="Output JSON.")

    watch = subparsers.add_parser("watch", help="Poll the Yugo API on an interval.")
    watch.add_argument("--country", help="Country name to resolve.")
    watch.add_argument("--country-id", help="Country id to use.")
    watch.add_argument("--city", help="City name to resolve.")
    watch.add_argument("--city-id", help="City id to use.")

    test_match = subparsers.add_parser("test-match", help="Test Semester 1 matching logic.")
    test_match.add_argument("--from-year", type=int, required=True, help="Tenancy fromYear.")
    test_match.add_argument("--to-year", type=int, required=True, help="Tenancy toYear.")
    test_match.add_argument("--name", default="Semester 1", help="Tenancy option name.")
    test_match.add_argument("--label", default="Semester 1", help="Tenancy formatted label.")
    test_match.add_argument("--start-date", default="2026-09-01", help="Tenancy startDate (YYYY-MM-DD).")
    test_match.add_argument("--end-date", default="2027-01-31", help="Tenancy endDate (YYYY-MM-DD).")
    test_match.add_argument("--json", action="store_true", help="Output JSON.")

    notify_parser = subparsers.add_parser("notify", help="Send a test notification.")
    notify_parser.add_argument("--message", help="Message to send.")

    probe = subparsers.add_parser(
        "probe-booking",
        help="Probe booking-flow endpoints for a matched option and return booking links/metadata.",
    )
    probe.add_argument("--country", help="Country name to resolve.")
    probe.add_argument("--country-id", help="Country id to use.")
    probe.add_argument("--city", help="City name to resolve.")
    probe.add_argument("--city-id", help="City id to use.")
    probe.add_argument("--all-options", action="store_true", help="Disable semester matching and allow probing any option.")
    probe.add_argument("--residence", help="Filter matched candidates by residence name contains.")
    probe.add_argument("--room", help="Filter matched candidates by room name contains.")
    probe.add_argument("--tenancy", help="Filter matched candidates by tenancy label contains.")
    probe.add_argument("--index", type=int, default=0, help="Candidate index after filters (default 0).")
    probe.add_argument("--notify", action="store_true", help="Notify via configured OpenClaw channel.")
    probe.add_argument("--json", action="store_true", help="Output JSON.")

    return parser


def main(argv: Optional[List[str]] = None) -> int:
    configure_logging()
    parser = build_parser()
    args = parser.parse_args(argv)

    config, warnings = load_config(args.config)
    for warning in warnings:
        logger.warning(warning)

    handlers = {
        "discover": handle_discover,
        "scan": handle_scan,
        "watch": handle_watch,
        "test-match": handle_test_match,
        "notify": handle_notify,
        "probe-booking": handle_probe_booking,
    }

    handler = handlers.get(args.command)
    if not handler:
        parser.print_help()
        return 2

    return handler(args, config)


if __name__ == "__main__":
    sys.exit(main())
