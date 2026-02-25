# Aparto Research — Dublin Rooms

## StarRez Portal Architecture (Feb 2026)

### Portal Flow
1. **EU Entry**: `portal.apartostudent.com/StarRezPortalXEU/F33813C2/65/1556/Book_a_room-Choose_Your_Country`
2. **Country Selection**: POST with `CheckOrderList=1` (Ireland) → redirect to IE portal
3. **IE Portal**: `apartostudent.starrezhousing.com/StarRezPortal/` (separate domain!)
4. **Residence Page**: `/StarRezPortal/.../51/365/Book_a_room-Select_your_Residenc` — lists 5 Dublin properties
5. **Room Search**: `/StarRezPortal/.../51/367/Book_a_room-Choose_your_room?...&TermID=XXXX`

### Key Discovery: TermID Probing
- Each booking option has a unique **termID** (integer)
- **Direct access**: `/StarRezPortal/General/RoomSearch/RoomSearch/RedirectToMainFilter?roomSelectionModelID=361&filterID=1&option=RoomLocationArea&termID={id}`
- Valid termID → redirects to "Choose your room" page with full term info
- Invalid termID → stays on residence page
- The room search page contains:
  - Term name: `"You have selected 'Binary Hub - 26/27 - 41 Weeks' booking term..."`
  - Date range: from `data-datestart` / `data-dateend` attributes
  - Room listings

### Known TermIDs (as of 2026-02-25)

**Dublin Properties (26/27 Full Year)**:
| termID | Property | Dates | Type |
|--------|----------|-------|------|
| 1264 | Dorset Point | 26/08/2026 → 09/06/2027 | 41 Weeks |
| 1265 | Beckett House | 26/08/2026 → 09/06/2027 | 41 Weeks |
| 1266 | The Loom | 26/08/2026 → 09/06/2027 | 41 weeks |
| 1267 | Binary Hub | 29/08/2026 → 12/06/2027 | 41 Weeks |
| 1268 | Montrose | 29/08/2026 → 12/06/2027 | 41 weeks |

**Dublin Properties (Other terms)**:
| termID | Property | Dates | Type |
|--------|----------|-------|------|
| 1258 | The Loom | 10/06/2026 → 19/08/2026 | 10 Week Summer (25/26) |
| 1272 | The Loom | 24/06/2026 → 19/08/2026 | RCSI GEM Summer |
| 1273 | The Loom | 24/06/2026 → 19/08/2026 | RCSI POST Summer |
| + 25/26 summer terms for all properties |

**Non-Dublin (Italy)**:
| termID | Property | Notes |
|--------|----------|-------|
| 1276-1279 | Giovenale | 10-12 months (Sep 2026 → 2027) |
| 1280-1283 | Ripamonti | 10-12 months |
| 1284 | CdM | TEST term |

### What Stephen's Quarter?
- NOT in the StarRez portal
- May use a different booking system or not be open yet for 26/27

### AJAX API (GetTermCardContent)
- URL: `/StarRezPortal/General/RoomSearch/roomsearch/GetTermCardContent`
- Method: POST (JSON)
- Data: `{pageID: 365, tableID: <flipper_id>}`
- Headers: `RequestVerificationToken: <csrf_token>`
- **Very flaky** — often returns HTTP 498. Not reliable for scraping.
- The termID probing approach is much more reliable.

### Main Website (apartostudent.com)
- Next.js SSR/RSC (React Server Components)
- Property pages: `apartostudent.com/locations/dublin/{slug}`
- No reliable API for availability data
- Useful for room types + pricing info
- Room tiers: Bronze, Silver, Gold, Platinum (Ensuite variations)

## Yugo API Architecture

### Endpoints
- Base: `https://yugo.com/en-gb/`
- Countries: `/countries` → `{countries: [{name, countryId, ...}]}`
- Cities: `/cities?countryId=598930` → `{cities: [{name, contentId, ...}]}`
- Residences: `/residences?cityId=598808` → `{residences: [...]}`
- Rooms: `/rooms?residenceId=<base64_id>` → `{rooms: [...]}`
- Tenancy: `/tenancyOptionsBySSId?residenceId=&residenceContentId=&roomId=`

### Dublin (city_id=598808)
8 residences: Dominick Place, Ardcairn House, Highfield Park, Brewers Close, The Tannery, New Mill, Broadstone Hall, Kavanagh Court

### Tenancy Options (2026-27)
- **41 Weeks**: 2026-08-27 → 2027-06-10
- **51 Weeks**: 2026-08-27 → 2027-08-19
- **No Semester 1** yet

## Monitoring Strategy

### Detection Methods
1. **Aparto**: Scan termID range 1250-1350 every hour. New Semester 1 terms will:
   - Have a Dublin property name
   - Duration ≤ 25 weeks (vs 41+ for full year)
   - Start Aug/Sep 2026, end Jan/Feb 2027
   - May contain "Semester 1" in name
2. **Yugo**: Check tenancy options API. Semester 1 will appear as:
   - New tenancyOption with "Semester 1" name
   - academicYearId for 2026-2027
   - Start Sep 2026, end Jan 2027

### Alert Triggers
- New Dublin Semester 1 termID appears on Aparto
- New Semester 1 tenancy option appears on any Yugo Dublin residence
- Immediately send Telegram notification with booking link
