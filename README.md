# dublin-rooms

**Multi-provider Dublin student accommodation CLI.**

Monitors Yugo and Aparto properties for Semester 1 availability (Sept–Jan 2026-27 academic year).
Sends Telegram alerts via OpenClaw for any new matching options detected.

Built for: Álvaro López Gil — Erasmus Dublin 2026-27, Semester 1.

## Providers

| Provider | Source | Method |
|---|---|---|
| **Yugo** | `yugo.com` JSON API | REST API (no auth needed) |
| **Aparto** | `apartostudent.com` HTML + StarRez portal | Web scraping (BeautifulSoup) |

## Dublin Properties

### Yugo
Auto-discovered via API (country: Ireland → city: Dublin).

### Aparto
| Property | Location |
|---|---|
| Binary Hub | Bonham St, Dublin 8 |
| Beckett House | Pearse St, Dublin 2 |
| Dorset Point | Dorset St, Dublin 1 |
| Montrose | Stillorgan Rd (near UCD) |
| The Loom | Dublin |
| Stephen's Quarter | Dublin 2 |

## Installation

```bash
cd yugo-scraper
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Configuration

Edit `config.yaml`:

```yaml
providers:
  yugo:
    enabled: true
  aparto:
    enabled: true

notifications:
  openclaw:
    enabled: true        # set to true to get Telegram alerts
    channel: "telegram"
    target: "1473631236" # Gonzalo's Telegram ID
```

## Usage

```bash
python main.py --help
```

### Discover properties

```bash
# All providers
python main.py discover

# Specific provider
python main.py discover --provider yugo
python main.py discover --provider aparto

# JSON output
python main.py discover --json
```

### Single scan (Semester 1 filter)

```bash
# All providers
python main.py scan

# Yugo only
python main.py scan --provider yugo

# Aparto only
python main.py scan --provider aparto

# Skip semester filter (debug all options)
python main.py scan --all-options --json

# Scan and notify if match found
python main.py scan --notify
```

### Watch loop (continuous monitoring)

```bash
# Monitor all providers, alert on new options
python main.py watch

# Monitor only Aparto
python main.py watch --provider aparto
```

The watcher:
- Polls every 60s (±15s jitter)
- Deduplicates: won't alert twice for the same option
- Persists seen options to `reports/seen_options.json` (survives restarts)
- Sends Telegram alert for any new Semester 1 option detected

### Deep booking probe

```bash
# Probe all providers
python main.py probe-booking --json

# Probe Yugo specifically (generates booking links)
python main.py probe-booking --provider yugo --json

# Probe Aparto (navigates StarRez portal)
python main.py probe-booking --provider aparto --json

# Filter by property/room
python main.py probe-booking --residence "Binary Hub" --json
```

### Test notification

```bash
python main.py notify --message "Test alert 🏠"
```

### Test semester matching (Yugo legacy)

```bash
python main.py test-match --from-year 2026 --to-year 2027 \
  --start-date 2026-09-01 --end-date 2027-01-31
```

## Dedup / Seen Options

The watcher writes `reports/seen_options.json` after each cycle. Delete this file to re-alert on already-seen options.

## Alert Format

```
🚨 NUEVO · Dublin Rooms · Semester 1 detectado

⭐ Opción prioritaria:
🏠 Binary Hub (APARTO)
🛏 Gold Ensuite
💶 €320/week
📍 Bonham St, Dublin 8
🔗 https://portal.apartostudent.com/...

📋 3 opciones totales (top 5 alternativas):
  2. [YUGO] Dominick Street | Standard Ensuite | €310/week
```

## Notes for Agents

- **Yugo**: Use `probe-booking --provider yugo --json` to get `skipRoomLink`/`handoverLink` for direct browser handoff
- **Aparto**: Use `probe-booking --provider aparto --json` to get StarRez portal status + entry URL
- Once a match is found, navigate to the booking URL in browser and complete the form
- Do NOT attempt irreversible payment actions automatically

## Docs

- `TASK.md` — original refactoring spec
- `APARTO_RESEARCH.md` — Aparto site architecture research
- `BOOKING_AUTOMATION_ANALYSIS.md` — booking flow analysis

## License

MIT
