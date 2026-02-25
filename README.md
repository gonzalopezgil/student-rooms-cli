# dublin-rooms 🏠

CLI tool to monitor student accommodation availability in Dublin for **Semester 1 2026-2027** (September → January/February). Built for Álvaro's Erasmus.

## Providers

| Provider | Properties | Method |
|----------|-----------|--------|
| **Aparto** (apartostudent.com) | Binary Hub, Beckett House, Dorset Point, Montrose, The Loom, Stephen's Quarter | StarRez portal termID probing + main site scraping |
| **Yugo** (yugo.com) | Dominick Place, Ardcairn House, Highfield Park, Brewers Close, The Tannery, New Mill, Broadstone Hall, Kavanagh Court | REST API |

## Current State (February 2026)

- **Aparto**: Full-year (41 weeks) available for all 5 Dublin properties. No Semester 1 yet.
- **Yugo**: Full-year (41 weeks) and 51 weeks available. No Semester 1 yet.
- This is **expected** — semester options typically appear later in the year.

## Commands

```bash
# List all Dublin properties
python cli.py discover --provider all

# Scan for Semester 1 availability (filtered)
python cli.py scan --provider all

# Scan ALL options (including full-year)
python cli.py scan --provider all --all-options --json

# Continuous monitoring (every hour, Telegram alerts)
python cli.py watch --provider all

# Deep probe a specific option
python cli.py probe-booking --provider aparto --residence "Binary Hub"

# Send test notification
python cli.py notify --message "Test notification"
```

## How It Works

### Aparto (StarRez Portal)
1. Navigates the EU portal → selects Ireland → establishes session
2. Probes a range of **termIDs** (1250-1350) via direct room search URLs
3. Each valid termID returns term name, property, date range, and room availability
4. Detects Semester 1 by:
   - Name keywords: "semester 1", "sem 1", etc.
   - Duration ≤ 25 weeks with start in Aug/Sep/Oct and end in Dec/Jan/Feb
5. Enriches with pricing data from apartostudent.com property pages

### Yugo (REST API)
1. Lists residences for Dublin (city_id=598808)
2. For each residence, fetches room types and tenancy options
3. Checks academic year 2026-2027 tenancy groups
4. Detects Semester 1 by name keywords or short duration with correct dates

### Watch Mode
- Scans both providers every hour (configurable)
- Deduplicates: only alerts on **new** options not previously seen
- Sends Telegram notification via OpenClaw when Semester 1 appears
- Seen options persisted in `reports/seen_options.json`

## Configuration

Edit `config.yaml`:

```yaml
providers:
  yugo:
    enabled: true
  aparto:
    enabled: true

target:
  country: "Ireland"
  city: "Dublin"
  country_id: "598930"
  city_id: "598808"

polling:
  interval_seconds: 3600    # 1 hour
  jitter_seconds: 300       # 5 min random jitter

notifications:
  openclaw:
    enabled: true
    channel: "telegram"
    target: "1473631236"
```

## Setup

```bash
# Create venv and install deps
python3 -m venv .venv
source .venv/bin/activate
pip install requests beautifulsoup4 pyyaml

# Run tests
python -m pytest tests/ -v

# Quick scan
python cli.py scan --provider all --all-options
```

## Architecture

```
cli.py                 # Entry point, argument parsing, watch loop
config.yaml            # Configuration
matching.py            # Semester 1 matching logic (Yugo format)
notifier.py            # Telegram notifications via OpenClaw
models/
  config.py            # Config dataclasses
providers/
  base.py              # BaseProvider + RoomOption dataclass
  aparto.py            # Aparto: StarRez termID probing
  yugo.py              # Yugo: REST API client
tests/
  test_aparto.py       # 26 tests
  test_matching.py     # 4 tests
reports/
  seen_options.json    # Dedup persistence for watch mode
```

## Known TermIDs (Aparto, Feb 2026)

| termID | Term | Dates |
|--------|------|-------|
| 1264 | Dorset Point - 26/27 - 41 Weeks | 26/08/2026 → 09/06/2027 |
| 1265 | Beckett House - 26/27 - 41 Weeks | 26/08/2026 → 09/06/2027 |
| 1266 | The Loom - 26/27 - 41 weeks | 26/08/2026 → 09/06/2027 |
| 1267 | Binary Hub - 26/27 - 41 Weeks | 29/08/2026 → 12/06/2027 |
| 1268 | Montrose - 26/27 - 41 weeks | 29/08/2026 → 12/06/2027 |
