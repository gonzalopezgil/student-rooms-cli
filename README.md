# Yugo Scraper (Phase A)

Yugo Scraper is a Python-based tool that discovers and monitors Yugo accommodation availability via the public Yugo API. Phase A delivers a non-interactive CLI foundation and matching logic without any booking or browser automation.

## Phase A+ scope

- CLI-first workflow (`yugo discover`, `yugo scan`, `yugo watch`, `yugo test-match`, `yugo notify`, `yugo probe-booking`).
- YAML configuration (`config.yaml`) with target, filters, academic-year matching, polling, and notification placeholders.
- Modular architecture (client, matching, models/config, notifier, cli).
- Minimal testing for Semester 1 matching logic.
- Booking-flow probing endpoint support (available beds, flats with beds, skip-room, student-portal handover link generation).
- No irreversible reservation checkout automation yet (browser-assisted handoff recommended).
- Technical analysis for CLI-vs-browser booking split: `BOOKING_AUTOMATION_ANALYSIS.md`.

## Installation

```bash
pip install -r requirements.txt
```

## Configuration

Primary configuration lives in `config.yaml`:

> For Dublin 26/27 tracking, use `config.dublin.26-27.sample.yaml` as a starting template.


```yaml
target:
  country: "United Kingdom"
  city: "London"

filters:
  private_bathroom: true
  private_kitchen: false
  max_weekly_price: null
  max_monthly_price: 1200

academic_year:
  start_year: 2024
  end_year: 2025
  semester1:
    name_keywords:
      - "semester 1"
      - "sem 1"
      - "fall"
      - "autumn"
    require_keyword: true

polling:
  interval_seconds: 300
  jitter_seconds: 30

notifications:
  pushover:
    enabled: false
    api_token: ""
    user_key: ""
  openclaw:
    enabled: false
    endpoint: ""
    api_key: ""
```

Legacy `config.ini` (Pushover only) is still supported for backward compatibility:

```ini
[Pushover]
api_token = YOUR_API_TOKEN_HERE
user_key = YOUR_USER_KEY_HERE
```

## Usage

All commands are non-interactive. Use `--config` to point to a YAML file if needed.

```bash
python main.py --help
```

### Discover

```bash
python main.py discover --countries
python main.py discover --cities --country "United Kingdom"
python main.py discover --residences --city "London" --country "United Kingdom"
```

### Scan

```bash
python main.py scan --city "London" --country "United Kingdom"
python main.py scan --city-id 12345 --notify
python main.py scan --city "Dublin" --country "Ireland" --json
```

### Watch

```bash
python main.py watch --city "London" --country "United Kingdom"
```

### Probe booking flow (CLI-first handover)

```bash
# Uses current config filters/matching; picks first candidate
python main.py probe-booking --city "Dublin" --country "Ireland"

# Narrow candidate and output machine-readable JSON (for agents)
python main.py probe-booking \
  --city "Dublin" --country "Ireland" \
  --residence "Dominick" --room "Classic" --tenancy "41 Weeks" \
  --json
```

### Test matching

```bash
python main.py test-match --from-year 2024 --to-year 2025 --name "Semester 1" --label "Semester 1 (Fall)"
```

### Notifications

```bash
python main.py notify --message "Yugo Phase A notification test"
```

## License

This project is licensed under the MIT License - see the LICENSE file for details.

## Disclaimer

This tool is intended for personal use and educational purposes. Please use it responsibly and adhere to the Yugo platform's terms of service.
