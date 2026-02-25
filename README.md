# student-rooms-cli 🏠

Multi-provider student accommodation finder and monitor. Discover properties, scan for availability, and get instant alerts when rooms matching your criteria appear.

Built for students hunting semester accommodation — especially when options appear unpredictably and sell out fast.

## Providers

| Provider | Website | Method | Coverage |
|----------|---------|--------|----------|
| **Yugo** | [yugo.com](https://yugo.com) | REST API | UK, Ireland, Spain, Portugal, Australia, and more |
| **Aparto** | [apartostudent.com](https://apartostudent.com) | StarRez portal probing + site scraping | Dublin (IE) |

## Installation

```bash
# Clone and install in development mode
git clone https://github.com/gonzalopezgil/student-rooms-cli.git
cd student-rooms-cli
python3 -m venv .venv
source .venv/bin/activate
pip install -e .

# Or install dependencies directly
pip install requests beautifulsoup4 pyyaml
```

## Quick Start

```bash
# Copy and edit the sample config
cp config.sample.yaml config.yaml

# List all properties in Dublin
python -m student_rooms discover --provider all

# Scan for Semester 1 availability
python -m student_rooms scan --provider all

# Scan ALL options (including full-year, unfiltered)
python -m student_rooms scan --provider all --all-options --json

# Continuous monitoring with alerts
python -m student_rooms watch --provider all

# Deep-probe a specific option's booking flow
python -m student_rooms probe-booking --provider yugo --residence "Dominick Place"

# Send a test notification
python -m student_rooms notify --message "Test alert 🏠"
```

If installed via `pip install -e .`, you can also use:
```bash
student-rooms discover --provider all
student-rooms scan --provider all
```

## Commands

| Command | Description |
|---------|-------------|
| `discover` | List all properties available from providers in your target city |
| `scan` | One-shot scan for rooms matching your semester/price criteria |
| `watch` | Continuous monitoring loop — alerts on new availability |
| `probe-booking` | Deep-probe the booking flow for a matched option (generates direct booking links) |
| `notify` | Send a test notification to verify your notification setup |
| `test-match` | Test the semester matching logic against sample data |

## Configuration

Copy `config.sample.yaml` to `config.yaml` and edit:

```yaml
# Target city
target:
  country: "Ireland"
  city: "Dublin"

# Academic year & semester detection
academic_year:
  start_year: 2026
  end_year: 2027
  semester1:
    name_keywords: ["semester 1", "sem 1", "first semester"]
    require_keyword: true
    start_months: [8, 9, 10]
    end_months: [12, 1, 2]

# Price filters
filters:
  max_weekly_price: 350.0

# Monitoring interval
polling:
  interval_seconds: 3600
  jitter_seconds: 300

# Notifications (see below)
notifications:
  type: "stdout"
```

### Notification Backends

Choose one notification backend via `notifications.type`:

#### `stdout` (default)
Just prints to console. No configuration needed.

#### `webhook`
Generic HTTP POST — works with Discord webhooks, Slack, [ntfy.sh](https://ntfy.sh), and more.

```yaml
notifications:
  type: "webhook"
  webhook:
    url: "https://discord.com/api/webhooks/YOUR_ID/YOUR_TOKEN"
    method: "POST"
    headers: {}
    body_template: '{"content": "{message}"}'
```

#### `telegram`
Direct Telegram Bot API — provide your own bot token and chat ID.

```yaml
notifications:
  type: "telegram"
  telegram:
    bot_token: "YOUR_BOT_TOKEN"
    chat_id: "YOUR_CHAT_ID"
    parse_mode: null
```

#### `openclaw`
[OpenClaw](https://github.com/nichochar/openclaw) CLI integration. Requires OpenClaw installed and configured. Supports message mode, agent mode, and automatic reservation job creation.

```yaml
notifications:
  type: "openclaw"
  openclaw:
    mode: "message"
    channel: "telegram"
    target: "YOUR_CHAT_ID"
    create_job_on_match: false
```

## How It Works

### Yugo Provider
1. Resolves country → city → residences via Yugo's JSON API
2. For each residence, fetches room types and tenancy options
3. Filters by academic year and semester using name keywords + date analysis
4. Supports full booking-flow probing (available beds, flat selection, portal redirect)

### Aparto Provider (StarRez)
1. Establishes session via the EU StarRez portal
2. Probes a range of **termIDs** via direct room search URLs
3. Parses term names, date ranges, and room availability from response pages
4. Detects Semester 1 by keyword matching + duration/date analysis
5. Enriches results with pricing data scraped from property pages

### Watch Mode
- Scans all enabled providers at configurable intervals
- Deduplicates: only alerts on **new** options not previously seen
- Persists seen options in `reports/seen_options.json`
- Adds random jitter to avoid request patterns

## Agent Integration

This tool is designed to work well with AI agents and automation:

```bash
# JSON output for programmatic consumption
python -m student_rooms scan --provider all --json
python -m student_rooms discover --provider all --json

# Scan + notify in one command
python -m student_rooms scan --provider all --notify

# Watch mode as a background process
python -m student_rooms watch --provider all &
```

The `--json` flag outputs structured data suitable for parsing by AI agents, scripts, or pipeline tools.

## Project Structure

```
student_rooms/
├── __init__.py
├── __main__.py          # python -m student_rooms entry point
├── cli.py               # CLI argument parsing + command handlers
├── matching.py          # Semester matching logic
├── models/
│   └── config.py        # Configuration dataclasses + YAML loader
├── providers/
│   ├── base.py          # BaseProvider ABC + RoomOption dataclass
│   ├── yugo.py          # Yugo REST API provider
│   └── aparto.py        # Aparto StarRez portal provider
└── notifiers/
    ├── base.py           # BaseNotifier ABC + factory
    ├── webhook.py        # Generic HTTP webhook
    ├── telegram.py       # Direct Telegram Bot API
    └── openclaw.py       # OpenClaw CLI integration (optional)
```

## Development

```bash
# Install dev dependencies
pip install -e ".[dev]"

# Run tests
python -m pytest tests/ -v

# Run a specific test file
python -m pytest tests/test_notifiers.py -v
```

## Contributing

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/new-provider`)
3. Add tests for new functionality
4. Ensure all tests pass (`python -m pytest tests/ -v`)
5. Submit a pull request

### Adding a New Provider

1. Create `student_rooms/providers/your_provider.py`
2. Implement `BaseProvider` (see `base.py` for the interface)
3. Register it in `cli.py`'s `make_providers()` function
4. Add tests in `tests/test_your_provider.py`

### Adding a New Notifier

1. Create `student_rooms/notifiers/your_notifier.py`
2. Implement `BaseNotifier` (see `base.py`)
3. Add config dataclass in `models/config.py`
4. Register in `notifiers/base.py`'s `create_notifier()` factory
5. Add tests in `tests/test_notifiers.py`

## License

MIT — see [LICENSE](LICENSE).
