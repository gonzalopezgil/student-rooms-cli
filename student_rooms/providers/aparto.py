"""
providers/aparto.py — Aparto accommodation provider (apartostudent.com).

Scraping strategy (StarRez termID probing):
  1. Navigate EU portal → select Ireland → get session cookies
  2. Probe a range of termIDs via direct room search URLs
  3. Each valid termID returns a "Choose your room" page with:
     - Term name (e.g. "Binary Hub - 26/27 - 41 Weeks")
     - Date range (start/end dates)
     - Room availability data
  4. Detect Semester 1 by analyzing term names and date ranges
  5. Cache known termIDs to detect NEW ones between scans
"""
from __future__ import annotations

import json
import logging
import re
import time
from typing import Any, Dict, List, Optional, Set, Tuple
from dataclasses import dataclass, field
from datetime import datetime

import requests
from bs4 import BeautifulSoup

from student_rooms.providers.base import BaseProvider, RoomOption

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

MAIN_BASE = "https://apartostudent.com"
PORTAL_EU_BASE = "https://portal.apartostudent.com/StarRezPortalXEU"
PORTAL_IE_BASE = "https://apartostudent.starrezhousing.com/StarRezPortal"

# Dublin properties: slug → display name + location
DUBLIN_PROPERTIES: List[Dict[str, str]] = [
    {"slug": "binary-hub",       "name": "Binary Hub",         "location": "Bonham St, Dublin 8"},
    {"slug": "beckett-house",    "name": "Beckett House",      "location": "Pearse St, Dublin 2"},
    {"slug": "dorset-point",     "name": "Dorset Point",       "location": "Dorset St, Dublin 1"},
    {"slug": "montrose",         "name": "Montrose",           "location": "Stillorgan Rd (near UCD)"},
    {"slug": "the-loom",         "name": "The Loom",           "location": "Mill St, Dublin 8"},
    {"slug": "stephens-quarter", "name": "Stephen's Quarter",  "location": "Earlsfort Tce, Dublin 2"},
]

# Dublin property names for matching (lowercase)
DUBLIN_PROPERTY_NAMES = {p["name"].lower() for p in DUBLIN_PROPERTIES}

# Known termIDs for Dublin properties (26/27, full year)
KNOWN_DUBLIN_TERM_IDS = {
    1264: "Dorset Point - 26/27 - 41 Weeks",
    1265: "Beckett House - 26/27 - 41 Weeks",
    1266: "The Loom - 26/27 - 41 weeks",
    1267: "Binary Hub - 26/27 - 41 Weeks",
    1268: "Montrose - 26/27 - 41 weeks",
}

# TermID scan range for detecting new terms
# Current known range: 1258-1284 (Feb 2026)
# Scan wider to catch new additions
TERM_ID_SCAN_START = 1250
TERM_ID_SCAN_END = 1350

# StarRez Ireland booking entry point
STARREZ_ENTRY_URL = (
    f"{PORTAL_EU_BASE}/F33813C2/65/1556/"
    "Book_a_room-Choose_Your_Country?UrlToken=8E2FC74D"
)

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/122.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-IE,en;q=0.9",
}

# Semester 1 detection
SEMESTER1_KEYWORDS = ["semester 1", "sem 1", "semester1", "first semester"]
SEMESTER1_MAX_WEEKS = 25
FULL_YEAR_MIN_WEEKS = 35


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------

@dataclass
class StarRezTerm:
    """A booking term discovered via termID probing."""
    term_id: int
    term_name: str          # e.g. "Binary Hub - 26/27 - 41 Weeks"
    property_name: str      # e.g. "Binary Hub"
    start_date: Optional[str]  # DD/MM/YYYY format
    end_date: Optional[str]
    start_iso: Optional[str]   # YYYY-MM-DD from data attributes
    end_iso: Optional[str]
    weeks: Optional[int]
    is_dublin: bool
    is_semester1: bool
    has_rooms: bool
    booking_url: str


# ---------------------------------------------------------------------------
# Helpers
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
        try:
            unescaped = raw.encode("utf-8").decode("unicode_escape")
        except Exception:
            unescaped = raw.replace('\\"', '"').replace("\\n", "\n")
        try:
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
    """Parse room types and prices from HTML."""
    soup = BeautifulSoup(html, "html.parser")
    text = soup.get_text(separator=" ")

    APARTO_TIERS = ["Bronze", "Silver", "Gold", "Platinum"]

    rooms = []
    seen_tiers: set = set()

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
        tier_order = {t: i for i, t in enumerate(APARTO_TIERS)}
        rooms.sort(key=lambda r: tier_order.get(r["room_type"].split()[0].title(), 99))
        return rooms

    # Fallback: separate tier list + price list
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

    price_pattern = re.compile(r'€\s*(\d+(?:[.,]\d+)?)\s*(?:p/?w|/week|per week|pw)', re.IGNORECASE)
    prices_raw = price_pattern.findall(text)
    prices = sorted({float(p.replace(",", ".")) for p in prices_raw if p})

    if not found_tiers:
        weekly = prices[0] if prices else None
        return [{
            "room_type": "Room (type TBC)",
            "price_label": f"from €{weekly:.0f}/week" if weekly else "price N/A",
            "price_weekly": weekly,
        }]

    tier_order = {t: i for i, t in enumerate(APARTO_TIERS)}
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
    """Attempt to extract room data from __NEXT_DATA__."""
    rooms = []
    try:
        def _walk(obj: Any, depth: int = 0):
            if depth > 10:
                return
            if isinstance(obj, dict):
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
# Term analysis
# ---------------------------------------------------------------------------

def _parse_weeks_from_name(term_name: str) -> Optional[int]:
    """Extract week count from term name like 'Binary Hub - 26/27 - 41 Weeks'."""
    m = re.search(r'(\d+)\s*[Ww]eek', term_name)
    return int(m.group(1)) if m else None


def _extract_property_name(term_name: str) -> str:
    """Extract property name from term name like 'Binary Hub - 26/27 - 41 Weeks'."""
    if " - " in term_name:
        return term_name.split(" - ")[0].strip()
    return term_name


def _is_dublin_term(term_name: str) -> bool:
    """Check if a term belongs to a Dublin property."""
    prop_name = _extract_property_name(term_name).lower()
    return any(dp in prop_name or prop_name in dp for dp in DUBLIN_PROPERTY_NAMES)


def _is_semester1_term(
    term_name: str,
    start_date: Optional[str],
    end_date: Optional[str],
    weeks: Optional[int],
) -> bool:
    """
    Detect if a term is a Semester 1 option.

    Checks:
    1. Name contains semester 1 keywords
    2. Duration is <= 25 weeks (not full year)
    3. Start date is August/September/October
    4. End date is December/January/February
    """
    name_lower = term_name.lower()

    # Direct keyword match
    if any(kw in name_lower for kw in SEMESTER1_KEYWORDS):
        return True

    # Duration-based detection
    if weeks is not None and weeks <= SEMESTER1_MAX_WEEKS:
        if start_date and end_date:
            try:
                s = datetime.strptime(start_date, "%d/%m/%Y")
                e = datetime.strptime(end_date, "%d/%m/%Y")
                if s.month in (8, 9, 10) and e.month in (12, 1, 2):
                    return True
            except ValueError:
                pass

    # ISO date format fallback
    if start_date and end_date and "-" in start_date:
        try:
            s = datetime.strptime(start_date, "%Y-%m-%d")
            e = datetime.strptime(end_date, "%Y-%m-%d")
            duration_weeks = (e - s).days / 7
            if (duration_weeks <= SEMESTER1_MAX_WEEKS and
                s.month in (8, 9, 10) and
                e.month in (12, 1, 2)):
                return True
        except ValueError:
            pass

    return False


# ---------------------------------------------------------------------------
# StarRez portal session & term probing
# ---------------------------------------------------------------------------

class StarRezScraper:
    """
    Navigate the StarRez Aparto portal and probe termIDs.

    Strategy:
    1. Establish session by navigating EU portal → Ireland
    2. Probe termIDs by directly accessing room search redirect URLs
    3. Parse term info from each valid response page
    """

    def __init__(self, session: requests.Session):
        self.session = session
        self._session_established = False

    def _establish_session(self) -> bool:
        """Navigate EU portal → Ireland to establish session cookies."""
        if self._session_established:
            return True

        try:
            r1 = self.session.get(STARREZ_ENTRY_URL, headers=HEADERS, timeout=20)
            if r1.status_code != 200:
                logger.warning("StarRez entry page HTTP %d", r1.status_code)
                return False

            soup = BeautifulSoup(r1.text, "html.parser")
            form = soup.find("form")
            if not form:
                logger.warning("No form on StarRez entry page")
                return False

            action = form.get("action", "")
            fields: Dict[str, str] = {}
            for inp in soup.find_all("input"):
                name = inp.get("name")
                if name:
                    fields[name] = inp.get("value", "")

            select = soup.find("select")
            if select:
                fields[select.get("name", "CheckOrderList")] = "1"  # Ireland

            post_url = f"https://portal.apartostudent.com/StarRezPortalXEU{action}"

            time.sleep(0.3)
            r2 = self.session.post(post_url, data=fields, headers=HEADERS, timeout=20, allow_redirects=False)
            redirect_path = r2.text.strip().strip('"')
            if not redirect_path or not redirect_path.startswith("/"):
                logger.warning("Unexpected redirect response: %s", r2.text[:100])
                return False

            time.sleep(0.3)
            r3 = self.session.get(
                f"https://portal.apartostudent.com{redirect_path}",
                headers=HEADERS,
                timeout=20,
                allow_redirects=True,
            )
            if r3.status_code != 200:
                logger.warning("Residence page HTTP %d", r3.status_code)
                return False

            self._session_established = True
            logger.info("StarRez session established: %s", r3.url)
            return True

        except requests.RequestException as exc:
            logger.warning("StarRez session error: %s", exc)
            return False

    def probe_term(self, term_id: int) -> Optional[StarRezTerm]:
        """
        Probe a single termID by accessing its room search redirect URL.
        Returns StarRezTerm if valid, None if invalid/error.
        """
        url = (
            f"{PORTAL_IE_BASE}/General/RoomSearch/RoomSearch/RedirectToMainFilter"
            f"?roomSelectionModelID=361&filterID=1&option=RoomLocationArea&termID={term_id}"
        )
        try:
            r = self.session.get(url, headers=HEADERS, timeout=15, allow_redirects=True)
            if r.status_code != 200:
                return None
            if "Choose your room" not in r.text:
                return None
        except requests.RequestException:
            return None

        soup = BeautifulSoup(r.text, "html.parser")

        # Extract term name + dates from info text
        term_info_match = re.search(
            r"You have selected '([^']+)' booking term.*?"
            r"begins on (\d{2}/\d{2}/\d{4}).*?"
            r"ends on (\d{2}/\d{2}/\d{4})",
            r.text,
            re.DOTALL,
        )

        # Get ISO dates from data attributes
        page_container = soup.find(attrs={"data-termid": True})
        start_iso = page_container.get("data-datestart", "")[:10] if page_container else None
        end_iso = page_container.get("data-dateend", "")[:10] if page_container else None

        term_name = term_info_match.group(1) if term_info_match else f"Term {term_id}"
        start_date = term_info_match.group(2) if term_info_match else None
        end_date = term_info_match.group(3) if term_info_match else None

        property_name = _extract_property_name(term_name)
        weeks = _parse_weeks_from_name(term_name)
        is_dublin = _is_dublin_term(term_name)

        # For Semester 1 detection, use DD/MM/YYYY if available, else ISO
        is_sem1 = _is_semester1_term(
            term_name,
            start_date or start_iso,
            end_date or end_iso,
            weeks,
        )

        # Check for actual room listings
        has_rooms = (
            "room-result" in r.text.lower()
            or "€" in soup.get_text()
            or bool(soup.find(attrs={"data-roombaseid": True}))
        )

        return StarRezTerm(
            term_id=term_id,
            term_name=term_name,
            property_name=property_name,
            start_date=start_date,
            end_date=end_date,
            start_iso=start_iso,
            end_iso=end_iso,
            weeks=weeks,
            is_dublin=is_dublin,
            is_semester1=is_sem1,
            has_rooms=has_rooms,
            booking_url=r.url,
        )

    def scan_term_range(
        self,
        start_id: int = TERM_ID_SCAN_START,
        end_id: int = TERM_ID_SCAN_END,
        dublin_only: bool = True,
        delay: float = 0.35,
    ) -> List[StarRezTerm]:
        """
        Scan a range of termIDs and return all valid terms.

        This is the core monitoring function. By scanning termIDs periodically,
        we can detect when new terms (e.g., Semester 1) are added.
        """
        if not self._establish_session():
            logger.error("Failed to establish StarRez session")
            return []

        terms: List[StarRezTerm] = []
        consecutive_misses = 0

        for tid in range(start_id, end_id + 1):
            term = self.probe_term(tid)
            if term:
                consecutive_misses = 0
                if dublin_only and not term.is_dublin:
                    continue
                terms.append(term)
                logger.debug(
                    "Term %d: %s (%s → %s) dublin=%s sem1=%s",
                    tid, term.term_name, term.start_date, term.end_date,
                    term.is_dublin, term.is_semester1,
                )
            else:
                consecutive_misses += 1
                # Stop scanning if we hit too many consecutive misses
                # (beyond the known range)
                if consecutive_misses > 20 and tid > max(KNOWN_DUBLIN_TERM_IDS.keys()) + 30:
                    logger.debug("Stopping scan at termID %d (20 consecutive misses)", tid)
                    break

            if delay > 0:
                time.sleep(delay)

        logger.info(
            "StarRez scan complete: %d/%d termIDs checked, %d Dublin terms found",
            min(end_id - start_id + 1, tid - start_id + 1),
            end_id - start_id + 1,
            len(terms),
        )
        return terms


# ---------------------------------------------------------------------------
# Provider implementation
# ---------------------------------------------------------------------------

class ApartoProvider(BaseProvider):
    """Aparto provider: StarRez termID probing + main site price scraping."""

    def __init__(self):
        self._session = requests.Session()

    @property
    def name(self) -> str:
        return "aparto"

    def discover_properties(self) -> List[Dict[str, Any]]:
        """Return static list of known Dublin properties."""
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
        """Scrape a single property page for room types + prices."""
        url = f"{MAIN_BASE}/locations/dublin/{prop['slug']}"
        html = _fetch(self._session, url)
        if not html:
            logger.warning("Aparto: could not fetch %s", url)
            return []

        rooms: List[Dict[str, Any]] = []

        next_data = _extract_next_data(html)
        if next_data:
            next_rooms = _extract_rooms_from_next_data(next_data)
            if next_rooms:
                rooms = next_rooms

        if not rooms:
            rooms = _extract_prices_from_html(html, prop["name"])

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
        Full scan: probe StarRez termIDs + scrape main site for prices.

        Strategy:
        1. Scan termIDs to find all Dublin booking terms
        2. Filter for Semester 1 terms (or return all if filter is off)
        3. Enrich with pricing data from the main site
        """
        results: List[RoomOption] = []

        # Step 1: Probe StarRez termIDs
        scraper = StarRezScraper(self._session)
        all_terms = scraper.scan_term_range(dublin_only=True)
        logger.info("Aparto: found %d Dublin terms", len(all_terms))

        # Filter by academic year (26/27)
        year_terms = [
            t for t in all_terms
            if "26/27" in t.term_name or (
                t.start_iso and t.start_iso.startswith("2026") and
                t.end_iso and (t.end_iso.startswith("2027") or t.end_iso.startswith("2026"))
            )
        ]

        # Apply semester filter
        if apply_semester_filter and semester == 1:
            target_terms = [t for t in year_terms if t.is_semester1]
        else:
            target_terms = year_terms

        if not target_terms:
            sem1_count = sum(1 for t in year_terms if t.is_semester1)
            logger.info(
                "Aparto: %d year terms, %d Semester 1 terms (filter=%s)",
                len(year_terms), sem1_count, apply_semester_filter,
            )
            if not apply_semester_filter:
                target_terms = year_terms

        if not target_terms:
            return results

        # Step 2: Get pricing data from main site
        property_rooms: Dict[str, List[Dict]] = {}
        prop_lookup = {p["name"].lower(): p for p in DUBLIN_PROPERTIES}
        for prop in DUBLIN_PROPERTIES:
            time.sleep(0.5)
            rooms = self._scrape_property(prop)
            if rooms:
                property_rooms[prop["slug"]] = rooms

        # Step 3: Build RoomOptions
        for term in target_terms:
            prop_info = prop_lookup.get(term.property_name.lower())
            if not prop_info:
                for key, val in prop_lookup.items():
                    if term.property_name.lower() in key or key in term.property_name.lower():
                        prop_info = val
                        break

            slug = prop_info["slug"] if prop_info else term.property_name.lower().replace(" ", "-")
            location = prop_info["location"] if prop_info else ""

            rooms = property_rooms.get(slug, [])
            if not rooms:
                rooms = [{"room_type": "Room (type TBC)", "price_weekly": None, "price_label": "price TBC"}]

            for room in rooms:
                results.append(RoomOption(
                    provider="aparto",
                    property_name=term.property_name,
                    property_slug=slug,
                    room_type=room.get("room_type", "Room"),
                    price_weekly=room.get("price_weekly"),
                    price_label=room.get("price_label", ""),
                    available=True,
                    booking_url=term.booking_url,
                    start_date=term.start_iso,
                    end_date=term.end_iso,
                    academic_year=academic_year,
                    option_name=term.term_name,
                    location=location,
                    raw={
                        "term_id": term.term_id,
                        "weeks": term.weeks,
                        "is_semester1": term.is_semester1,
                        "start_date_dd": term.start_date,
                        "end_date_dd": term.end_date,
                    },
                ))

        return results

    def probe_booking(self, option: RoomOption) -> Dict[str, Any]:
        """Deep-probe for a specific option."""
        scraper = StarRezScraper(self._session)
        all_terms = scraper.scan_term_range(dublin_only=True)

        term_id = option.raw.get("term_id")
        matching_term = None
        if term_id:
            matching_term = next((t for t in all_terms if t.term_id == term_id), None)

        semester1_terms = [t for t in all_terms if t.is_semester1 and "26/27" in t.term_name]

        return {
            "match": {
                "property": option.property_name,
                "room": option.room_type,
                "academicYear": option.academic_year,
                "termName": matching_term.term_name if matching_term else "N/A",
                "hasSemester1": bool(semester1_terms),
            },
            "portalState": {
                "dublinTermCount": len([t for t in all_terms if "26/27" in t.term_name]),
                "semester1Count": len(semester1_terms),
                "allDublinTerms": [
                    {
                        "name": t.term_name,
                        "termId": t.term_id,
                        "startDate": t.start_date,
                        "endDate": t.end_date,
                        "weeks": t.weeks,
                        "isSemester1": t.is_semester1,
                    }
                    for t in all_terms if "26/27" in t.term_name
                ],
            },
            "links": {
                "bookingPortal": STARREZ_ENTRY_URL,
                "propertyPage": f"{MAIN_BASE}/locations/dublin/{option.property_slug}",
                "termLink": matching_term.booking_url if matching_term else None,
            },
            "raw": option.raw,
        }
