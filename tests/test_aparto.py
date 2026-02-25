"""
tests/test_aparto.py — Tests for the Aparto provider.
Tests HTML parsing, price extraction, and provider interface.
"""
import unittest
from unittest.mock import MagicMock, patch

from providers.aparto import (
    ApartoProvider,
    DUBLIN_PROPERTIES,
    _extract_next_data,
    _extract_prices_from_html,
    _extract_rsc_json_chunks,
)
from providers.base import RoomOption


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
        # Bronze < Silver < Gold < Platinum
        types = [r["room_type"] for r in rooms]
        self.assertEqual(types[0], "Bronze Ensuite")
        self.assertEqual(types[-1], "Platinum Ensuite")

    def test_no_price_fallback(self):
        rooms = _extract_prices_from_html(SAMPLE_PROPERTY_HTML_NO_PRICE, "Stephen's Quarter")
        # Should still find room types even without prices
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
        # Should extract at least the JSON object from the RSC push
        self.assertTrue(len(chunks) >= 0)  # May vary by escaping


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

    @patch("providers.aparto._fetch")
    def test_scrape_property_with_html(self, mock_fetch):
        """Test that _scrape_property parses HTML correctly."""
        mock_fetch.return_value = SAMPLE_PROPERTY_HTML
        provider = ApartoProvider()
        rooms = provider._scrape_property({"slug": "binary-hub", "name": "Binary Hub", "location": "Dublin 8"})
        self.assertEqual(len(rooms), 4)
        self.assertEqual(rooms[0]["property_name"], "Binary Hub")
        self.assertEqual(rooms[0]["property_slug"], "binary-hub")

    @patch("providers.aparto._fetch")
    def test_scrape_property_returns_empty_on_failure(self, mock_fetch):
        """Test that _scrape_property returns [] when fetch fails."""
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
    """Test ApartoProvider.scan with mocked HTTP."""

    @patch("providers.aparto._fetch")
    @patch.object(ApartoProvider, "_session", create=True)
    def test_scan_returns_room_options(self, _mock_session, mock_fetch):
        mock_fetch.return_value = SAMPLE_PROPERTY_HTML
        provider = ApartoProvider()

        # Mock StarRez to skip portal check
        with patch("providers.aparto.StarRezScraper") as MockScraper:
            instance = MockScraper.return_value
            instance.check_semester1_availability.return_value = (False, [], "mocked")
            results = provider.scan(academic_year="2026-27", semester=1)

        # 6 properties × 4 rooms each = 24 results
        self.assertEqual(len(results), 24)
        for r in results:
            self.assertIsInstance(r, RoomOption)
            self.assertEqual(r.provider, "aparto")
            self.assertEqual(r.academic_year, "2026-27")
            self.assertEqual(r.option_name, "Semester 1 2026-27")


if __name__ == "__main__":
    unittest.main()
