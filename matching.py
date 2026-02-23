from typing import Dict, Optional

from models.config import AcademicYearConfig, FilterConfig


def _has_private_arrangement(room: Dict, key: str) -> Optional[bool]:
    arrangement = room.get(key)
    if arrangement:
        return "private" in arrangement.lower()
    return None


def get_monthly_price(room: Dict) -> Optional[float]:
    price_label = room.get("priceLabel")
    if price_label:
        label = price_label.lower()
        price_billing_cycle = room.get("minPriceForBillingCycle")
        if price_billing_cycle is not None:
            try:
                if "month" in label:
                    return float(price_billing_cycle)
                if "week" in label:
                    return float(price_billing_cycle) * 4.33
            except (TypeError, ValueError):
                return None
    price_per_night = room.get("minPricePerNight")
    if price_per_night:
        try:
            return float(price_per_night) * 7 * 4.33
        except (TypeError, ValueError):
            return None
    return None


def get_weekly_price(room: Dict) -> Optional[float]:
    price_label = room.get("priceLabel")
    if price_label:
        label = price_label.lower()
        price_billing_cycle = room.get("minPriceForBillingCycle")
        if price_billing_cycle is not None:
            try:
                if "week" in label:
                    return float(price_billing_cycle)
                if "month" in label:
                    return float(price_billing_cycle) / 4.33
            except (TypeError, ValueError):
                return None
    price_per_night = room.get("minPricePerNight")
    if price_per_night:
        try:
            return float(price_per_night) * 7
        except (TypeError, ValueError):
            return None
    return None


def filter_room(room: Dict, filters: FilterConfig) -> bool:
    sold_out = room.get("soldOut")
    if sold_out is not False:
        return False

    if filters.private_bathroom is not None:
        private_bathroom = _has_private_arrangement(room, "bathroomArrangement")
        if private_bathroom is None or private_bathroom != filters.private_bathroom:
            return False

    if filters.private_kitchen is not None:
        private_kitchen = _has_private_arrangement(room, "kitchenArrangement")
        if private_kitchen is None or private_kitchen != filters.private_kitchen:
            return False

    if filters.max_monthly_price is not None:
        price_per_month = get_monthly_price(room)
        if price_per_month is None or price_per_month > filters.max_monthly_price:
            return False

    if filters.max_weekly_price is not None:
        price_per_week = get_weekly_price(room)
        if price_per_week is None or price_per_week > filters.max_weekly_price:
            return False

    return True


def match_semester1(option: Dict, academic_year: AcademicYearConfig) -> bool:
    if not option:
        return False

    from_year = option.get("fromYear")
    to_year = option.get("toYear")

    if academic_year.start_year is not None and from_year != academic_year.start_year:
        return False
    if academic_year.end_year is not None and to_year != academic_year.end_year:
        return False

    label_parts = []
    tenancy = option.get("tenancyOption") or []
    if tenancy:
        label_parts.append(str(tenancy[0].get("name", "")))
        label_parts.append(str(tenancy[0].get("formattedLabel", "")))

    label = " ".join(label_parts).lower()
    keywords = [keyword.lower() for keyword in academic_year.semester1.name_keywords]
    if academic_year.semester1.require_keyword:
        return any(keyword in label for keyword in keywords)
    if label:
        return True
    return False
