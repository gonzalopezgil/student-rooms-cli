# Aparto Provider Research (2026-02-25)

## Architecture
- **Main site:** `apartostudent.com` — Next.js (RSC) with Umbraco CMS backend
- **Booking portal:** `portal.apartostudent.com/StarRezPortalXEU/` — StarRez Portal (session-based HTML forms)
- **CDN:** Azure Front Door (`fde-apartostudent-ayefgmadgjajg0hc.a03.azurefd.net`)
- **Payments:** Mews (`api.mews.com/distributor/`)

## Data Availability

### From main website (scraping SSR HTML/RSC):
- Property names: Binary Hub, Beckett House, Dorset Point, Montrose, The Loom, Stephen's Quarter
- Room types: Bronze/Silver/Gold/Platinum Ensuite (per property)
- Prices: from €291-320/week (Binary Hub example)
- Academic years: dropdown selector (`01-08-2026_04-09-2027` = 2026-27)
- NO public REST API — data embedded in RSC Server Components

### From StarRez Portal:
- **Entry URL:** `portal.apartostudent.com/StarRezPortalXEU/F33813C2/65/1556/Book_a_room-Choose_Your_Country?UrlToken=8E2FC74D`
- Country selection: Ireland = value "1"
- Process IDs: 63 (Spain), 65 (Ireland), 87 (?), 72 (UK)
- Portal is multi-step HTML form flow (not REST API)
- Anti-CSRF likely, session-based
- `data-portalrulestatus="Open"` indicates booking is active

## Scraping Strategy

### Option A: Scrape main website (recommended for monitoring)
- Parse RSC payloads from property pages
- Each property has URL pattern: `/locations/dublin/{property-slug}`
- Extract room types, prices, availability status from HTML
- Advantages: no auth needed, no session state, cacheable
- Disadvantages: may not show real-time availability (just "from €X")

### Option B: StarRez Portal scraping (for availability + booking)
- Requires session management (CSRF tokens, cookies)
- Multi-step form navigation: Country → Property → Room → Dates → Availability
- More complex but shows ACTUAL availability
- Can potentially reach booking confirmation step

### Recommended approach: A + B combined
1. **Monitor** (frequent, lightweight): scrape main site for price changes and new room types
2. **Probe** (periodic, deeper): navigate StarRez portal to check actual availability for Semester 1
3. **Alert** when Semester 1 options appear
4. **Booking assist** via browser automation on StarRez portal when match found

## Dublin Properties (all)
| Property | Slug | Location |
|---|---|---|
| Binary Hub | binary-hub | Bonham St, D08 R596 |
| Beckett House | beckett-house | Pearse St |
| Dorset Point | dorset-point | Dorset St |
| Montrose | montrose | Stillorgan Rd (near UCD) |
| The Loom | the-loom | - |
| Stephen's Quarter | stephens-quarter | - |

## Key URLs
- Property list: `https://apartostudent.com/locations/dublin`
- Property page: `https://apartostudent.com/locations/dublin/{slug}`
- Booking portal entry: `https://portal.apartostudent.com/StarRezPortalXEU/F33813C2/65/1556/Book_a_room-Choose_Your_Country?UrlToken=8E2FC74D`
- StarRez Ireland flow: processID=65
