# Yugo Scraper (Agent-ready CLI)

Yugo Scraper is a Python CLI to discover, filter, and monitor Yugo accommodation options.
It is designed so OpenClaw agents can operate it directly (scan, prioritize, generate booking links, notify, and optionally create follow-up jobs).

## What it does now

- Non-interactive CLI workflow:
  - `discover`
  - `scan`
  - `watch`
  - `test-match`
  - `notify`
  - `probe-booking`
- Strict Semester 1 matching policy (configurable).
- Prioritization logic: **ensuite first**, then **cheapest**.
- Booking-flow probing (CLI-first):
  - `available-beds`
  - `flats-with-beds`
  - `skip-room-selection`
  - `student-portal-redirect`
- OpenClaw-native notifications and optional instant job creation.

## Not in scope (yet)

- Full irreversible checkout by pure API only. Final reservation completion usually continues in browser/student portal.

## Installation

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Configuration

Use `config.yaml` (or pass `--config <path>`).

For Dublin 26/27 starter config, see:

- `config.dublin.26-27.sample.yaml`

Key sections:

- `academic_year.semester1.name_keywords`: strict matching tokens (default: only `semester 1`)
- `academic_year.semester1.enforce_month_window`: enforce Sep/Oct -> Jan/Feb shape
- `notifications.openclaw`: Telegram (or other channel) delivery + optional job creation

## Usage

```bash
python main.py --help
```

### Discover

```bash
python main.py discover --countries
python main.py discover --cities --country "Ireland"
python main.py discover --residences --city "Dublin" --country "Ireland"
```

### Scan

```bash
# strict Semester 1 (default from config)
python main.py scan --city "Dublin" --country "Ireland"

# debugging / current market inventory regardless of semester rules
python main.py scan --city "Dublin" --country "Ireland" --all-options --json
```

### Watch loop

```bash
python main.py watch --city "Dublin" --country "Ireland"
```

### Probe booking flow (generate booking link + context)

```bash
# strict matches from config
python main.py probe-booking --city "Dublin" --country "Ireland" --json

# force current available options (useful for testing)
python main.py probe-booking \
  --city "Dublin" --country "Ireland" \
  --all-options --tenancy "41 Weeks" --residence "Dominick" --json
```

### Notification test

```bash
python main.py notify --message "Yugo test"
```

## Notes for agents

- Prefer `probe-booking --json` before browser automation.
- Use returned `skipRoomLink`/`handoverLink` as entry point to student portal booking process.
- If `notifications.openclaw.create_job_on_match=true`, scanner can auto-create an immediate isolated OpenClaw job.

## Reference docs

- `MIGRATION_PHASE_A.md`
- `BOOKING_AUTOMATION_ANALYSIS.md`

## License

MIT (see `LICENSE`).
