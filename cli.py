import argparse
import logging
import random
import sys
import time
from typing import Dict, List, Optional, Tuple

from client import YugoClient, find_by_name
from matching import filter_room, get_monthly_price, match_semester1
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


def format_option_message(residence: Dict, room: Dict, option: Dict) -> str:
    tenancy = (option.get("tenancyOption") or [{}])[0]
    price_label = room.get("priceLabel") or ""
    monthly_price = get_monthly_price(room)
    price_detail = f"{price_label}"
    if monthly_price is not None:
        price_detail = f"{price_label} (~{monthly_price:.2f} per month)"
    return (
        f"Residence: {residence.get('name', 'Unknown')}\n"
        f"Room: {room.get('name', 'Unknown')} - {price_detail}\n"
        f"Tenancy: {tenancy.get('name', 'Unknown')} - {tenancy.get('formattedLabel', '')}"
    )


def scan_city(client: YugoClient, city_id: str, config: Config) -> Tuple[List[str], int]:
    residences = client.list_residences(city_id)
    messages: List[str] = []
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
            options = client.list_tenancy_options(str(residence_id), str(residence_content_id), str(room_id))
            if not options:
                continue

            for option in options:
                option_count += 1
                if not match_semester1(option, config.academic_year):
                    continue
                messages.append(format_option_message(residence, room, option))

    return messages, option_count


def handle_discover(args: argparse.Namespace, config: Config) -> int:
    client = YugoClient()
    if args.countries:
        countries = client.list_countries()
        for item in countries:
            print(f"{item.get('countryId') or item.get('id')}\t{item.get('name')}")
        return 0

    if args.cities:
        country_id = resolve_country_id(client, config, args.country, args.country_id)
        if not country_id:
            print("Country id is required (or set target.country/target.country_id in config.yaml).")
            return 2
        cities = client.list_cities(country_id)
        for item in cities:
            print(f"{item.get('contentId') or item.get('id')}\t{item.get('name')}")
        return 0

    if args.residences:
        city_id = resolve_city_id(client, config, args.city, args.city_id, args.country, args.country_id)
        if not city_id:
            print("City id is required (or set target.city/target.city_id in config.yaml).")
            return 2
        residences = client.list_residences(city_id)
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

    messages, option_count = scan_city(client, city_id, config)
    if messages:
        print("\n\n".join(messages))
    print(f"Scanned {option_count} tenancy options. Matches: {len(messages)}")

    if args.notify and messages:
        error = validate_notification_config(config.notifications)
        if error:
            print(error)
            return 2
        notify("\n\n".join(messages), config.notifications)
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
        messages, option_count = scan_city(client, city_id, config)
        logger.info("Scanned %s tenancy options. Matches: %s", option_count, len(messages))
        if messages and config.notifications:
            notify("\n\n".join(messages), config.notifications)
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
            }
        ],
    }
    matched = match_semester1(option, config.academic_year)
    print("MATCH" if matched else "NO MATCH")
    return 0


def handle_notify(args: argparse.Namespace, config: Config) -> int:
    error = validate_notification_config(config.notifications)
    if error:
        print(error)
        return 2
    message = args.message or "Yugo Phase A test notification"
    notify(message, config.notifications)
    print("Notification dispatched (if enabled channels are configured).")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="yugo", description="Yugo Phase A CLI")
    parser.add_argument("--config", default="config.yaml", help="Path to YAML config.")
    parser.add_argument("--config-ini", default="config.ini", help="Path to legacy INI config.")

    subparsers = parser.add_subparsers(dest="command", required=True)

    discover = subparsers.add_parser("discover", help="List available countries, cities, or residences.")
    discover.add_argument("--countries", action="store_true", help="List countries.")
    discover.add_argument("--cities", action="store_true", help="List cities for a country.")
    discover.add_argument("--residences", action="store_true", help="List residences for a city.")
    discover.add_argument("--country", help="Country name to resolve.")
    discover.add_argument("--country-id", help="Country id to use.")
    discover.add_argument("--city", help="City name to resolve.")
    discover.add_argument("--city-id", help="City id to use.")

    scan = subparsers.add_parser("scan", help="Run a single scan against the Yugo API.")
    scan.add_argument("--country", help="Country name to resolve.")
    scan.add_argument("--country-id", help="Country id to use.")
    scan.add_argument("--city", help="City name to resolve.")
    scan.add_argument("--city-id", help="City id to use.")
    scan.add_argument("--notify", action="store_true", help="Send notifications for matches.")

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

    notify_parser = subparsers.add_parser("notify", help="Send a test notification.")
    notify_parser.add_argument("--message", help="Message to send.")

    return parser


def main(argv: Optional[List[str]] = None) -> int:
    configure_logging()
    parser = build_parser()
    args = parser.parse_args(argv)

    config, warnings = load_config(args.config, args.config_ini)
    for warning in warnings:
        logger.warning(warning)

    handlers = {
        "discover": handle_discover,
        "scan": handle_scan,
        "watch": handle_watch,
        "test-match": handle_test_match,
        "notify": handle_notify,
    }

    handler = handlers.get(args.command)
    if not handler:
        parser.print_help()
        return 2

    return handler(args, config)


if __name__ == "__main__":
    sys.exit(main())
