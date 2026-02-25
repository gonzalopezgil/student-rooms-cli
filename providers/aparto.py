"""
providers/aparto.py — Aparto accommodation provider (apartostudent.com).

Scraping strategy (two-tier):
  1. Main site HTML scraping (lightweight monitor):
     - Fetches each Dublin property page
     - Parses room types (Bronze/Silver/Gold/Platinum Ensuite) + prices
     - Parses __NEXT_DATA__ JSON if available
     - Used for `discover` and as a lightweight `scan`
  2. StarRez portal probe (deeper check):
     - Navigates portal.apartostudent.com to check real Semester 1 availability
     - Used for `probe-booking`
"""
from __future__ import annotations

import json
import logging
import re
import time
from typing import Any, Dict, List, Optional, Tuple

import requests
from bs4 import BeautifulSoup

from providers.base import BaseProvider, RoomOption

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

MAIN_BASE = "https://apartostudent.com"
PORTAL_BASE = "https://portal.apartostudent.com/StarRezPortalXEU"

# Dublin properties: slug → display name + location
DUBLIN_PROPERTIES: List[Dict[str, str]] = [
    {"slug": "binary-hub",       "name": "Binary Hub",         "location": "Bonham St, Dublin 8"},
    {"slug": "beckett-house",    "name": "Beckett House",       "location": "Pearse St, Dublin 2"},
    {"slug": "dorset-point",     "name": "Dorset Point",        "location": "Dorset St, Dublin 1"},
    {"slug": "montrose",         "name": "Montrose",            "location": "Stillorgan Rd (near UCD)"},
    {"slug": "the-loom",         "name": "The Loom",            "location": "Dublin"},
    {"slug": "stephens-quarter", "name": "Stephen's Quarter",   "location": "Dublin 2"},
]

# StarRez Ireland booking entry point
STARREZ_ENTRY_URL = (
    f"{PORTAL_BASE}/F33813C2/65/1556/"
    "Book_a_room-Choose_Your_Country?UrlToken=8E2FC74D"
)
STARREZ_COUNTRY_VALUE = "1"   # Ireland

# Academic year format used in Aparto URLs / portal
ACADEMIC_YEAR_FORMAT = {
    "2026-27": "01-08-2026_04-09-2027",
    "2025-26": "01-08-2025_04-09-2026",
}

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/122.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-IE,en;q=0.9",
}

# ---------------------------------------------------------------------------
# HTML / JSON parsing helpers
# ---------------------------------------------------------------------------

def _fetch(
    session: requests.Session,
    url: str,
    timeout: int = 20,
    retries: int = 3,
) -> Optional[str]:
    """Fetch URL with retries; return HTML text or None on failure."""
    for attempt in range(1, retries + 1):
        try:
            resp = session.get(url, headers=HEADERS, timeout=timeout)
            if resp.status_code == 200:
                return resp.text
            if resp.status_code == 404:
                return None
            logger.warning("HTTP %s fetching %s (attempt %s/%s)", resp.status_code, url, attempt, retries)
        except requests.RequestException as exc:
            logger.warning("Request error fetching %s: %s (attempt %s/%s)", url, exc, attempt, retries)
        if attempt < retries:
            time.sleep(1.5 * attempt)
    return None


def _extract_next_data(html: str) -> Optional[Dict[str, Any]]:
    """Extract the __NEXT_DATA__ JSON embedded by Next.js."""
    try:
        soup = BeautifulSoup(html, "html.parser")
        tag = soup.find("script", id="__NEXT_DATA__")
        if tag and tag.string:
            return json.loads(tag.string)
    except Exception as exc:
        logger.debug("__NEXT_DATA__ parse error: %s", exc)
    return None


def _extract_rsc_json_chunks(html: str) -> List[Any]:
    """
    Extract JSON objects pushed via Next.js RSC:
      self.__next_f.push([1, '...json...'])
    """
    results = []
    pattern = re.compile(r'self\.__next_f\.push\(\[1\s*,\s*"((?:[^"\\]|\\.)*)"\]\)', re.DOTALL)
    for match in pattern.finditer(html):
        raw = match.group(1)
        # Un-escape the JSON string
        try:
            unescaped = raw.encode("utf-8").decode("unicode_escape")
        except Exception:
            unescaped = raw.replace('\\"', '"').replace("\\n", "\n")
        try:
            # RSC chunks contain lines like "0:{...}" or "1:..." – try to parse JSON objects
            for line in unescaped.splitlines():
                colon_idx = line.find(":")
                if colon_idx < 0:
                    continue
                json_part = line[colon_idx + 1:]
                if json_part.startswith("{") or json_part.startswith("["):
                    try:
                        results.append(json.loads(json_part))
                    except json.JSONDecodeError:
                        pass
        except Exception:
            pass
    return results


def _extract_prices_from_html(html: str, property_name: str) -> List[Dict[str, Any]]:
    """
    Parse room types and prices directly from HTML.
    Looks for patterns like:
      - "Bronze Ensuite" / "Silver Ensuite" / "Gold Ensuite" / "Platinum Ensuite"
      - "€291 p/w" / "€291/week" / "from €291"
    Returns a list of {room_type, price_label, price_weekly}.

    Strategy:
    1. Find tier+subtype combinations that appear close to a price
    2. Fall back to separate tier list + price list if proximity fails
    """
    soup = BeautifulSoup(html, "html.parser")
    text = soup.get_text(separator=" ")

    # Aparto-specific tiers (ordered by tier level)
    APARTO_TIERS = ["Bronze", "Silver", "Gold", "Platinum"]
    GENERIC_TIERS = ["Studio", "Deluxe", "Premium", "Classic", "Standard"]

    price_pattern = re.compile(r'€\s*(\d+(?:[.,]\d+)?)\s*(?:p/?w|/week|per week|pw)', re.IGNORECASE)

    # --- Strategy 1: proximity matching (tier string near a price) ---
    rooms = []
    seen_tiers: set = set()

    # Look for "Tier [Subtype]... €NNN" within ~200 chars
    proximity_pattern = re.compile(
        r'(Bronze|Silver|Gold|Platinum|Studio|Deluxe)[\s\-]*(Ensuite|En-suite|Studio|Room|Suite|Apartment)?'
        r'.{0,200}?€\s*(\d+(?:[.,]\d+)?)\s*(?:p/?w|/week|per week|pw)',
        re.IGNORECASE | re.DOTALL,
    )
    for m in proximity_pattern.finditer(text):
        tier = m.group(1).strip().title()
        subtype = (m.group(2) or "Ensuite").strip().title()
        label = f"{tier} {subtype}"
        if label in seen_tiers:
            continue
        seen_tiers.add(label)
        try:
            price = float(m.group(3).replace(",", "."))
        except ValueError:
            price = None
        rooms.append({
            "room_type": label,
            "price_label": f"€{price:.0f}/week" if price else "price N/A",
            "price_weekly": price,
        })

    if rooms:
        # Sort by Aparto tier order
        tier_order = {t: i for i, t in enumerate(APARTO_TIERS + GENERIC_TIERS)}
        rooms.sort(key=lambda r: tier_order.get(r["room_type"].split()[0].title(), 99))
        return rooms

    # --- Strategy 2: separate tier list + price list ---
    tier_pattern = re.compile(
        r'\b(Bronze|Silver|Gold|Platinum|Studio|Deluxe)\b'
        r'[\s\-]*(Ensuite|En-suite|Room|Suite|Apartment)?',
        re.IGNORECASE,
    )
    found_tiers = []
    for m in tier_pattern.finditer(text):
        tier = m.group(1).strip().title()
        subtype = (m.group(2) or "Ensuite").strip().title()
        label = f"{tier} {subtype}"
        if label not in found_tiers:
            found_tiers.append(label)

    prices_raw = price_pattern.findall(text)
    prices = []
    for p in prices_raw:
        try:
            prices.append(float(p.replace(",", ".")))
        except ValueError:
            pass
    # deduplicate and sort
    prices = sorted(set(prices))

    if not found_tiers:
        weekly = prices[0] if prices else None
        return [{
            "room_type": "Room (type TBC)",
            "price_label": f"from €{weekly:.0f}/week" if weekly else "price N/A",
            "price_weekly": weekly,
        }]

    # Match each tier to a price by index
    tier_order = {t: i for i, t in enumerate(APARTO_TIERS + GENERIC_TIERS)}
    found_tiers.sort(key=lambda l: tier_order.get(l.split()[0].title(), 99))

    for idx, tier_label in enumerate(found_tiers):
        weekly = prices[idx] if idx < len(prices) else (prices[0] if prices else None)
        rooms.append({
            "room_type": tier_label,
            "price_label": f"€{weekly:.0f}/week" if weekly else "price N/A",
            "price_weekly": weekly,
        })

    return rooms


def _extract_rooms_from_next_data(next_data: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    Attempt to extract room data from __NEXT_DATA__.
    The shape varies by Next.js version; this is best-effort.
    """
    rooms = []
    try:
        # Walk all nested dicts looking for room-like structures
        def _walk(obj: Any, depth: int = 0):
            if depth > 10:
                return
            if isinstance(obj, dict):
                # Look for price + room type keys
                name = obj.get("name") or obj.get("title") or obj.get("roomType") or ""
                price = obj.get("price") or obj.get("priceFrom") or obj.get("weeklyPrice") or 0
                if name and price and any(
                    kw in str(name).lower()
                    for kw in ("bronze", "silver", "gold", "platinum", "ensuite", "studio", "room")
                ):
                    weekly = None
                    try:
                        weekly = float(str(price).replace("€", "").replace(",", "").strip())
                    except ValueError:
                        pass
                    rooms.append({
                        "room_type": str(name).strip().title(),
                        "price_label": f"€{weekly:.0f}/week" if weekly else str(price),
                        "price_weekly": weekly,
                    })
                for v in obj.values():
                    _walk(v, depth + 1)
            elif isinstance(obj, list):
                for item in obj:
                    _walk(item, depth + 1)

        _walk(next_data)
    except Exception as exc:
        logger.debug("next_data room extraction error: %s", exc)
    return rooms


# ---------------------------------------------------------------------------
# StarRez portal scraper
# ---------------------------------------------------------------------------

class StarRezScraper:
    """
    Navigate the StarRez Aparto portal to check real Semester 1 availability.
    Uses session-based HTML form navigation (no REST API).
    """

    def __init__(self, session: requests.Session):
        self.session = session

    def _post_form(self, url: str, data: Dict[str, Any], timeout: int = 20) -> Optional[str]:
        """Post form and follow any redirect.
        
        StarRez sometimes returns a quoted URL string as the response body
        (AJAX-style redirect) instead of HTML. We detect and follow it.
        """
        try:
            resp = self.session.post(url, data=data, headers=HEADERS, timeout=timeout)
            if resp.status_code != 200:
                logger.warning("StarRez POST %s → HTTP %s", url, resp.status_code)
                return None

            body = resp.text.strip()

            # Check if response is a quoted redirect URL (e.g. "/StarRezPortalXEU/...")
            if body.startswith('"') and body.endswith('"') and "/StarRez" in body:
                redirect_path = body.strip('"')
                if redirect_path.startswith("/StarRezPortalXEU"):
                    redirect_url = f"https://portal.apartostudent.com{redirect_path}"
                elif redirect_path.startswith("/"):
                    redirect_url = f"{PORTAL_BASE}{redirect_path}"
                else:
                    redirect_url = f"{PORTAL_BASE}/{redirect_path}"
                logger.info("StarRez redirect → %s", redirect_url)
                follow_resp = self.session.get(redirect_url, headers=HEADERS, timeout=timeout)
                if follow_resp.status_code == 200:
                    return follow_resp.text
                logger.warning("StarRez redirect follow → HTTP %s", follow_resp.status_code)
                return None

            return body
        except requests.RequestException as exc:
            logger.warning("StarRez POST error: %s", exc)
        return None

    def _get_form_fields(self, html: str) -> Dict[str, str]:
        """Extract hidden form fields (including CSRF tokens) from HTML."""
        soup = BeautifulSoup(html, "html.parser")
        fields: Dict[str, str] = {}
        for inp in soup.find_all("input"):
            name = inp.get("name")
            value = inp.get("value", "")
            if name:
                fields[str(name)] = str(value)
        return fields

    def _get_action_url(self, html: str, base_url: str) -> str:
        """Extract form action URL from HTML.
        
        StarRez form actions are typically relative to the portal root,
        e.g. /F33813C2/65/... which maps to PORTAL_BASE + action.
        """
        soup = BeautifulSoup(html, "html.parser")
        form = soup.find("form")
        if form:
            action = form.get("action", "")
            if action:
                if action.startswith("http"):
                    return action
                if action.startswith("/"):
                    return f"{PORTAL_BASE}{action}"
                return f"{PORTAL_BASE}/{action}"
        return base_url

    def check_semester1_availability(
        self, academic_year: str = "2026-27"
    ) -> Tuple[bool, List[Dict[str, Any]], str]:
        """
        Navigate StarRez portal to check if Semester 1 options are available.
        Returns: (available, list_of_options, status_message)
        """
        # Step 1: Load entry page
        html = _fetch(self.session, STARREZ_ENTRY_URL, timeout=20)
        if not html:
            return False, [], "Could not reach StarRez portal"

        # Check if portal is open
        if 'data-portalrulestatus="Open"' in html or "Choose_Your_Country" in html:
            logger.info("StarRez portal appears to be open")
        elif "Closed" in html or "closed" in html:
            return False, [], "StarRez portal appears closed"

        fields = self._get_form_fields(html)
        action_url = self._get_action_url(html, STARREZ_ENTRY_URL)

        # Step 2: Submit country selection (Ireland = 1)
        # Detect the actual select field name from HTML
        soup_fields = BeautifulSoup(html, "html.parser")
        select_el = soup_fields.find("select")
        country_field_name = select_el.get("name") if select_el else None

        if country_field_name:
            fields[country_field_name] = STARREZ_COUNTRY_VALUE
        else:
            # Fallback: try common field names
            for country_field in ["CheckOrderList", "DropDownCountry", "ddlCountry", "country", "CountryID"]:
                fields[country_field] = STARREZ_COUNTRY_VALUE

        time.sleep(1)
        html2 = self._post_form(action_url, fields)
        if not html2:
            return False, [], "Failed to submit country selection"

        # Step 3: Look for Semester 1 / academic year options in the response
        soup = BeautifulSoup(html2, "html.parser")
        page_text = soup.get_text(separator=" ")

        academic_year_str = ACADEMIC_YEAR_FORMAT.get(academic_year, "")
        found_semester1 = (
            "Semester 1" in page_text
            or "semester 1" in page_text.lower()
            or (academic_year_str and academic_year_str in page_text)
        )

        # Extract visible booking options
        options = []
        option_pattern = re.compile(
            r'(Semester\s*1|Semester\s*2|Full\s*Year|Academic\s*Year)',
            re.IGNORECASE,
        )
        price_pattern = re.compile(r'€\s*(\d+(?:[.,]\d+)?)', re.IGNORECASE)

        for match in option_pattern.finditer(page_text):
            label = match.group(0).strip()
            # Try to find price near this option
            nearby = page_text[max(0, match.start() - 50): match.end() + 100]
            price_m = price_pattern.search(nearby)
            weekly = float(price_m.group(1).replace(",", ".")) if price_m else None
            options.append({
                "label": label,
                "price_weekly": weekly,
            })

        status = "Semester 1 detected in portal" if found_semester1 else "No Semester 1 options visible"
        return found_semester1, options, status


# ---------------------------------------------------------------------------
# Provider implementation
# ---------------------------------------------------------------------------

class ApartoProvider(BaseProvider):
    """Aparto provider: scrapes apartostudent.com + StarRez portal."""

    def __init__(self):
        self._session = requests.Session()

    @property
    def name(self) -> str:
        return "aparto"

    def discover_properties(self) -> List[Dict[str, Any]]:
        """Return static list of known Dublin properties (enriched if possible)."""
        props = []
        for prop in DUBLIN_PROPERTIES:
            url = f"{MAIN_BASE}/locations/dublin/{prop['slug']}"
            props.append({
                "slug": prop["slug"],
                "name": prop["name"],
                "location": prop["location"],
                "url": url,
                "provider": "aparto",
            })
        return props

    def _scrape_property(self, prop: Dict[str, str]) -> List[Dict[str, Any]]:
        """
        Scrape a single property page and return room data.
        Returns list of {room_type, price_label, price_weekly, property, ...}
        """
        url = f"{MAIN_BASE}/locations/dublin/{prop['slug']}"
        html = _fetch(self._session, url)
        if not html:
            logger.warning("Aparto: could not fetch %s", url)
            return []

        rooms: List[Dict[str, Any]] = []

        # Try __NEXT_DATA__ first (most structured)
        next_data = _extract_next_data(html)
        if next_data:
            next_rooms = _extract_rooms_from_next_data(next_data)
            if next_rooms:
                rooms = next_rooms

        # Fall back to HTML text parsing
        if not rooms:
            rooms = _extract_prices_from_html(html, prop["name"])

        # Tag each room with property info
        for room in rooms:
            room.update({
                "property_name": prop["name"],
                "property_slug": prop["slug"],
                "location": prop["location"],
                "page_url": url,
            })

        return rooms

    def scan(
        self,
        academic_year: str = "2026-27",
        semester: int = 1,
        apply_semester_filter: bool = True,
    ) -> List[RoomOption]:
        """
        Scrape all Dublin properties and return RoomOption list.
        NOTE: Main-site data shows pricing but not granular Semester 1 availability.
        Use probe_booking() for StarRez-level confirmation.
        """
        results: List[RoomOption] = []
        portal_available = False
        portal_options: List[Dict] = []
        portal_status = ""

        # Quick StarRez check to see if Semester 1 is open
        if apply_semester_filter and semester == 1:
            try:
                star_scraper = StarRezScraper(self._session)
                portal_available, portal_options, portal_status = (
                    star_scraper.check_semester1_availability(academic_year)
                )
                logger.info("StarRez status: %s", portal_status)
            except Exception as exc:
                logger.warning("StarRez probe error: %s", exc)

        for prop in DUBLIN_PROPERTIES:
            time.sleep(0.5)  # polite delay between property pages
            rooms = self._scrape_property(prop)
            if not rooms:
                continue

            for room in rooms:
                weekly = room.get("price_weekly")
                price_label = room.get("price_label") or ""

                # For semester filtering: mark as available only if portal confirms it
                # If we couldn't check the portal, still include (with available=False as a probe signal)
                available = portal_available if apply_semester_filter else True

                booking_url = STARREZ_ENTRY_URL  # Best direct link we have

                results.append(RoomOption(
                    provider="aparto",
                    property_name=room.get("property_name") or prop["name"],
                    property_slug=prop["slug"],
                    room_type=room.get("room_type") or "Room",
                    price_weekly=weekly,
                    price_label=price_label,
                    available=available,
                    booking_url=booking_url,
                    start_date=None,  # StarRez portal has actual dates
                    end_date=None,
                    academic_year=academic_year,
                    option_name=f"Semester 1 {academic_year}" if semester == 1 else academic_year,
                    location=prop.get("location"),
                    raw={
                        "page_url": room.get("page_url") or "",
                        "portal_status": portal_status,
                        "portal_available": portal_available,
                        "portal_options": portal_options,
                    },
                ))

        return results

    def probe_booking(self, option: RoomOption) -> Dict[str, Any]:
        """
        Deep-probe StarRez portal for actual Semester 1 availability.
        Returns booking context + direct portal link.
        """
        star_scraper = StarRezScraper(self._session)
        academic_year = option.academic_year or "2026-27"
        available, options, status = star_scraper.check_semester1_availability(academic_year)

        return {
            "match": {
                "property": option.property_name,
                "room": option.room_type,
                "academicYear": academic_year,
                "portalStatus": status,
                "portalAvailable": available,
            },
            "portalOptions": options,
            "links": {
                "bookingPortal": STARREZ_ENTRY_URL,
                "propertyPage": f"{MAIN_BASE}/locations/dublin/{option.property_slug}",
            },
            "raw": option.raw,
        }
