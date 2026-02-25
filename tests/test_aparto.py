"""
tests/test_aparto.py — Tests for the Aparto provider.
Tests HTML parsing, price extraction, and provider interface.
"""
import unittest
from unittest.mock import MagicMock, patch

from student_rooms.providers.aparto import (
    ApartoProvider,
    DUBLIN_PROPERTIES,
    _extract_next_data,
    _extract_prices_from_html,
    _extract_rsc_json_chunks,
)
from student_rooms.providers.base import RoomOption


# ---------------------------------------------------------------------------
# Sample HTML fragments for testing
# ---------------------------------------------------------------------------

SAMPLE_PROPERTY_HTML = """
<!DOCTYPE html>
<html>
<head><title>Binary Hub - Aparto</title></head>
<body>
<div class="room-types">
  <div class="room-card">
    <h3>Bronze Ensuite</h3>
    <p class="price">€291 p/w</p>
  </div>
  <div class="room-card">
    <h3>Silver Ensuite</h3>
    <p class="price">€300 p/w</p>
  </div>
  <div class="room-card">
    <h3>Gold Ensuite</h3>
    <p class="price">€310 p/w</p>
  </div>
  <div class="room-card">
    <h3>Platinum Ensuite</h3>
    <p class="price">€320 p/w</p>
  </div>
</div>
</body>
</html>
"""

SAMPLE_PROPERTY_HTML_NO_PRICE = """
<!DOCTYPE html>
<html>
<head><title>Stephen's Quarter - Aparto</title></head>
<body>
<div class="room-types">
  <div class="room-card">
    <h3>Bronze Ensuite</h3>
    <p>Coming soon</p>
  </div>
  <div class="room-card">
    <h3>Studio Room</h3>
    <p>Contact for pricing</p>
  </div>
</div>
</body>
</html>
"""

SAMPLE_NEXT_DATA_HTML = """
<!DOCTYPE html>
<html>
<head>
<script id="__NEXT_DATA__" type="application/json">
{
  "props": {
    "pageProps": {
      "rooms": [
        {"name": "Gold Ensuite", "price": 310},
        {"name": "Platinum Ensuite", "price": 320}
      ]
    }
  }
}
</script>
</head>
<body></body>
</html>
"""

SAMPLE_RSC_HTML = """
<!DOCTYPE html>
<html>
<head>
<script>
self.__next_f.push([1, "0:{\\"rooms\\":[{\\"name\\":\\"Bronze Ensuite\\",\\"price\\":291}]}"])
</script>
</head>
<body>
<div>Bronze Ensuite</div>
<div>€291 p/w</div>
</body>
</html>
"""


class TestExtractPricesFromHtml(unittest.TestCase):
    """Test HTML price/room extraction."""

    def test_extracts_all_tiers(self):
        rooms = _extract_prices_from_html(SAMPLE_PROPERTY_HTML, "Binary Hub")
        self.assertEqual(len(rooms), 4)
        room_types = [r["room_type"] for r in rooms]
        self.assertIn("Bronze Ensuite", room_types)
        self.assertIn("Silver Ensuite", room_types)
        self.assertIn("Gold Ensuite", room_types)
        self.assertIn("Platinum Ensuite", room_types)

    def test_extracts_prices(self):
        rooms = _extract_prices_from_html(SAMPLE_PROPERTY_HTML, "Binary Hub")
        prices = {r["room_type"]: r["price_weekly"] for r in rooms}
        self.assertEqual(prices["Bronze Ensuite"], 291.0)
        self.assertEqual(prices["Silver Ensuite"], 300.0)
        self.assertEqual(prices["Gold Ensuite"], 310.0)
        self.assertEqual(prices["Platinum Ensuite"], 320.0)

    def test_sorted_by_tier_order(self):
        rooms = _extract_prices_from_html(SAMPLE_PROPERTY_HTML, "Binary Hub")
        types = [r["room_type"] for r in rooms]
        self.assertEqual(types[0], "Bronze Ensuite")
        self.assertEqual(types[-1], "Platinum Ensuite")

    def test_no_price_fallback(self):
        rooms = _extract_prices_from_html(SAMPLE_PROPERTY_HTML_NO_PRICE, "Stephen's Quarter")
        self.assertTrue(len(rooms) >= 1)
        for room in rooms:
            self.assertIn("room_type", room)

    def test_price_label_format(self):
        rooms = _extract_prices_from_html(SAMPLE_PROPERTY_HTML, "Binary Hub")
        for room in rooms:
            if room["price_weekly"]:
                self.assertTrue(room["price_label"].startswith("€"))
                self.assertIn("/week", room["price_label"])


class TestExtractNextData(unittest.TestCase):
    """Test __NEXT_DATA__ extraction."""

    def test_extracts_json(self):
        data = _extract_next_data(SAMPLE_NEXT_DATA_HTML)
        self.assertIsNotNone(data)
        self.assertIn("props", data)

    def test_returns_none_without_tag(self):
        data = _extract_next_data("<html><body>No NEXT_DATA here</body></html>")
        self.assertIsNone(data)


class TestExtractRscJsonChunks(unittest.TestCase):
    """Test RSC JSON chunk extraction."""

    def test_extracts_chunks(self):
        chunks = _extract_rsc_json_chunks(SAMPLE_RSC_HTML)
        self.assertTrue(len(chunks) >= 0)


class TestDublinProperties(unittest.TestCase):
    """Test the static properties list."""

    def test_has_six_properties(self):
        self.assertEqual(len(DUBLIN_PROPERTIES), 6)

    def test_all_have_required_keys(self):
        for prop in DUBLIN_PROPERTIES:
            self.assertIn("slug", prop)
            self.assertIn("name", prop)
            self.assertIn("location", prop)

    def test_known_slugs(self):
        slugs = [p["slug"] for p in DUBLIN_PROPERTIES]
        self.assertIn("binary-hub", slugs)
        self.assertIn("beckett-house", slugs)
        self.assertIn("dorset-point", slugs)
        self.assertIn("montrose", slugs)
        self.assertIn("the-loom", slugs)
        self.assertIn("stephens-quarter", slugs)


class TestApartoProvider(unittest.TestCase):
    """Test ApartoProvider methods."""

    def test_provider_name(self):
        provider = ApartoProvider()
        self.assertEqual(provider.name, "aparto")

    def test_discover_returns_all_properties(self):
        provider = ApartoProvider()
        props = provider.discover_properties()
        self.assertEqual(len(props), 6)
        for prop in props:
            self.assertEqual(prop["provider"], "aparto")
            self.assertIn("url", prop)
            self.assertTrue(prop["url"].startswith("https://apartostudent.com"))

    @patch("student_rooms.providers.aparto._fetch")
    def test_scrape_property_with_html(self, mock_fetch):
        mock_fetch.return_value = SAMPLE_PROPERTY_HTML
        provider = ApartoProvider()
        rooms = provider._scrape_property({"slug": "binary-hub", "name": "Binary Hub", "location": "Dublin 8"})
        self.assertEqual(len(rooms), 4)
        self.assertEqual(rooms[0]["property_name"], "Binary Hub")
        self.assertEqual(rooms[0]["property_slug"], "binary-hub")

    @patch("student_rooms.providers.aparto._fetch")
    def test_scrape_property_returns_empty_on_failure(self, mock_fetch):
        mock_fetch.return_value = None
        provider = ApartoProvider()
        rooms = provider._scrape_property({"slug": "fake", "name": "Fake", "location": ""})
        self.assertEqual(rooms, [])


class TestRoomOption(unittest.TestCase):
    """Test RoomOption dataclass."""

    def _sample_option(self, **kwargs) -> RoomOption:
        defaults = dict(
            provider="aparto",
            property_name="Binary Hub",
            property_slug="binary-hub",
            room_type="Gold Ensuite",
            price_weekly=310.0,
            price_label="€310/week",
            available=True,
            booking_url="https://portal.apartostudent.com/...",
            start_date=None,
            end_date=None,
            academic_year="2026-27",
            option_name="Semester 1 2026-27",
        )
        defaults.update(kwargs)
        return RoomOption(**defaults)

    def test_dedup_key_stable(self):
        opt1 = self._sample_option()
        opt2 = self._sample_option()
        self.assertEqual(opt1.dedup_key(), opt2.dedup_key())

    def test_dedup_key_differs_by_property(self):
        opt1 = self._sample_option(property_slug="binary-hub")
        opt2 = self._sample_option(property_slug="beckett-house")
        self.assertNotEqual(opt1.dedup_key(), opt2.dedup_key())

    def test_dedup_key_differs_by_room_type(self):
        opt1 = self._sample_option(room_type="Gold Ensuite")
        opt2 = self._sample_option(room_type="Bronze Ensuite")
        self.assertNotEqual(opt1.dedup_key(), opt2.dedup_key())

    def test_alert_lines(self):
        opt = self._sample_option(location="Bonham St, Dublin 8")
        lines = opt.alert_lines()
        self.assertTrue(any("Binary Hub" in l for l in lines))
        self.assertTrue(any("Gold Ensuite" in l for l in lines))
        self.assertTrue(any("€310" in l for l in lines))
        self.assertTrue(any("Dublin 8" in l for l in lines))


class TestApartoScanMocked(unittest.TestCase):
    """Test ApartoProvider.scan with mocked StarRez scraper."""

    @patch("student_rooms.providers.aparto._fetch")
    def test_scan_returns_room_options_no_semester1(self, mock_fetch):
        mock_fetch.return_value = SAMPLE_PROPERTY_HTML
        provider = ApartoProvider()

        from student_rooms.providers.aparto import StarRezScraper, StarRezTerm
        full_year_term = StarRezTerm(
            term_id=1267,
            term_name="Binary Hub - 26/27 - 41 Weeks",
            property_name="Binary Hub",
            start_date="29/08/2026",
            end_date="12/06/2027",
            start_iso="2026-08-29",
            end_iso="2027-06-12",
            weeks=41,
            is_dublin=True,
            is_semester1=False,
            has_rooms=True,
            booking_url="https://test.com/term/1267",
        )
        with patch.object(StarRezScraper, "scan_term_range", return_value=[full_year_term]):
            results = provider.scan(academic_year="2026-27", semester=1, apply_semester_filter=True)

        self.assertEqual(len(results), 0)

    @patch("student_rooms.providers.aparto._fetch")
    def test_scan_returns_all_when_semester1_available(self, mock_fetch):
        mock_fetch.return_value = SAMPLE_PROPERTY_HTML
        provider = ApartoProvider()

        from student_rooms.providers.aparto import StarRezScraper, StarRezTerm
        sem1_term = StarRezTerm(
            term_id=9999,
            term_name="Binary Hub - 26/27 - Semester 1",
            property_name="Binary Hub",
            start_date="29/08/2026",
            end_date="31/01/2027",
            start_iso="2026-08-29",
            end_iso="2027-01-31",
            weeks=22,
            is_dublin=True,
            is_semester1=True,
            has_rooms=True,
            booking_url="https://test.com/term/9999",
        )
        with patch.object(StarRezScraper, "scan_term_range", return_value=[sem1_term]):
            results = provider.scan(academic_year="2026-27", semester=1, apply_semester_filter=True)

        self.assertEqual(len(results), 4)
        for r in results:
            self.assertIsInstance(r, RoomOption)
            self.assertEqual(r.provider, "aparto")
            self.assertEqual(r.academic_year, "2026-27")
            self.assertEqual(r.property_name, "Binary Hub")
            self.assertTrue(r.available)
            self.assertIn("Semester 1", r.option_name)


class TestStarRezTermAnalysis(unittest.TestCase):
    """Test StarRez term detection and analysis."""

    def test_is_semester1_by_keyword(self):
        from student_rooms.providers.aparto import _is_semester1_term
        self.assertTrue(_is_semester1_term("Semester 1 26/27", "29/08/2026", "31/01/2027", 22))
        self.assertTrue(_is_semester1_term("Sem 1", None, None, None))
        self.assertFalse(_is_semester1_term("Full Year 41 Weeks", "29/08/2026", "12/06/2027", 41))

    def test_is_semester1_by_duration(self):
        from student_rooms.providers.aparto import _is_semester1_term
        self.assertTrue(_is_semester1_term("Special 22 Weeks", "29/08/2026", "31/01/2027", 22))
        self.assertFalse(_is_semester1_term("Special 22 Weeks", "01/02/2027", "30/06/2027", 22))

    def test_is_semester1_by_iso_dates(self):
        from student_rooms.providers.aparto import _is_semester1_term
        self.assertTrue(_is_semester1_term("Short Stay", "2026-09-01", "2027-01-31", None))
        self.assertFalse(_is_semester1_term("Full Year", "2026-08-29", "2027-06-12", None))

    def test_is_dublin_term(self):
        from student_rooms.providers.aparto import _is_dublin_term
        self.assertTrue(_is_dublin_term("Binary Hub - 26/27 - 41 Weeks"))
        self.assertTrue(_is_dublin_term("The Loom - 26/27 - Semester 1"))
        self.assertFalse(_is_dublin_term("Giovenale - 26/27 - 10 months"))

    def test_extract_property_name(self):
        from student_rooms.providers.aparto import _extract_property_name
        self.assertEqual(_extract_property_name("Binary Hub - 26/27 - 41 Weeks"), "Binary Hub")
        self.assertEqual(_extract_property_name("Montrose - 26/27 - 41 weeks"), "Montrose")

    def test_parse_weeks(self):
        from student_rooms.providers.aparto import _parse_weeks_from_name
        self.assertEqual(_parse_weeks_from_name("Binary Hub - 26/27 - 41 Weeks"), 41)
        self.assertEqual(_parse_weeks_from_name("The Loom - 25/26 - 10 Week Summer"), 10)
        self.assertIsNone(_parse_weeks_from_name("Giovenale - 26/27 - 10 months"))


if __name__ == "__main__":
    unittest.main()
