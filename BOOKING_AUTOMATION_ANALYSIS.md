# Booking Automation Analysis (Dublin live)

Date: 2026-02-23

## Goal
Evaluate how far reservation can be driven directly from CLI/API and where browser automation is still required.

## Confirmed flow from CLI/API
Using a real live option (Dominick Place → Classic Ensuite → 41 Weeks 2026/27), the scraper can execute:

1. Discover context
   - `countries`
   - `cities?countryId=...`
   - `residences?cityId=...`
   - `rooms?residenceId=...`
   - `tenancyOptionsBySSId?...`

2. Booking metadata for a selected match
   - `residence-property?residenceId=...` (building/floor structure)

3. Availability + candidate bed discovery
   - `available-beds?...` ✅
   - `flats-with-beds?...` ✅

4. Generate booking links (handover to portal)
   - `skip-room-selection?...` ✅ returns `linkToRedirect`
   - `student-portal-redirect` (POST) ✅ returns `linkToRedirect`

These links are actionable `student-portal.yugo.com/en-gb/booking-process?...` deep links.

## Critical implementation details

- `tenancyStartDate` / `tenancyEndDate` must be sent in JS Date-like string format.
  - ISO-only payloads produced `400` on some endpoints.
  - Working example format:
    - `Thu Aug 27 2026 00:00:00 GMT+0000 (UTC)`
- `buildingIds` and `floorIndexes` must be populated from `residence-property`.
- Warm booking page request improves endpoint compatibility:
  - `booking-flow-page?residenceContentId=...`

## What still needs browser / authenticated portal

The scraper can generate deep booking links, but final reservation completion still depends on student-portal session/auth and form interactions inside portal UI.

### Recommended split

- CLI:
  - detect target option
  - probe booking flow
  - generate portal deep link + payload context
  - trigger OpenClaw job instantly
- Browser agent:
  - login student portal
  - navigate/confirm selected option
  - complete reservation steps

## Operational modes for agents

1. `ALERT`
   - Notify + links only
2. `ASSIST` (recommended default)
   - Notify + open browser and pre-position to booking step
3. `AUTOBOOK`
   - Attempt full flow automatically (guardrails required)

## New CLI support

`probe-booking` command now returns machine-readable booking context and links suitable for OpenClaw agents.

Example:

```bash
python main.py probe-booking \
  --config /tmp/dublin26.yaml \
  --residence "Dominick" \
  --room "Classic Ensuite" \
  --tenancy "41 Weeks" \
  --json
```

This command is intended to be called by orchestrator agents before launching browser automation.
