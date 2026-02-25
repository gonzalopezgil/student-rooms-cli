# Task: Evolve yugo-scraper → dublin-rooms CLI

## Context
This is an existing CLI tool for scraping Yugo student accommodation. We need to:
1. Rename the project to `dublin-rooms` (or `student-rooms-cli`)
2. Add Aparto as a second provider
3. Make the watcher run continuously with real-time Telegram alerts

## Target User
Álvaro López Gil — going on Erasmus to Dublin, Semester 1 2026-2027 (September → January/February).
Availability is EXTREMELY limited. The watcher must detect availability ASAP.

## Requirements

### 1. Multi-provider architecture
- Refactor `client.py` into `providers/` directory
- `providers/yugo.py` — existing Yugo API client (move from client.py)
- `providers/aparto.py` — NEW: scrape Aparto website + StarRez portal
- `providers/base.py` — abstract base class for providers
- Common data models for rooms, properties, availability

### 2. Aparto Provider (`providers/aparto.py`)
Research is in `APARTO_RESEARCH.md`. Key points:
- Scrape property pages: `https://apartostudent.com/locations/dublin/{slug}`
- Dublin properties: binary-hub, beckett-house, dorset-point, montrose, the-loom, stephens-quarter
- Parse room types + prices from HTML (RSC Server Components, look for patterns like "Bronze Ensuite" + "€291 p/w")
- For availability: probe StarRez Portal (`portal.apartostudent.com/StarRezPortalXEU/...`)
  - Country selection: Ireland = value "1", processID=65
  - Session-based HTML forms, need CSRF handling
- Academic year format: `01-08-2026_04-09-2027` for 2026-27

### 3. CLI Commands (keep existing, add new)
- `discover` — list all properties from all providers
- `scan` — single-pass check for Semester 1 availability
- `watch` — continuous monitoring loop (THE critical command)
- `probe-booking` — deep booking-flow check (existing for Yugo, new for Aparto)
- `notify` — test notification delivery
- Add `--provider yugo|aparto|all` flag to all commands

### 4. Watcher (`watch` command)
- Poll both Yugo and Aparto every 60-90s (with jitter)
- Filter for Semester 1 only (Sept-Jan/Feb 2026-27)
- Deduplicate: don't alert twice for same room
- On match: send Telegram alert via OpenClaw (`openclaw message send`)
- Include: property name, room type, price, booking link
- Persist seen options to file to survive restarts

### 5. Config update
Update `config.yaml` to support multiple providers:
```yaml
providers:
  yugo:
    enabled: true
  aparto:
    enabled: true

target:
  country: "Ireland"
  city: "Dublin"
  academic_year: "2026-27"
  semester: 1  # Sept → Jan/Feb

notifications:
  openclaw:
    enabled: true
    channel: "telegram"
    target: "1473631236"
```

### 6. Project rename
- Update README.md with new name and multi-provider docs
- Update package metadata
- Keep git history (don't create new repo)

## Constraints
- Python 3.14 (already in .venv)
- Use `requests` + `beautifulsoup4` for HTML scraping
- No Selenium/Playwright — pure HTTP scraping for the watcher
- Browser automation only for actual booking (separate step)
- Keep all existing Yugo functionality working

## What NOT to do
- Don't implement actual booking automation (just detect + alert)
- Don't create GitHub Actions or CI
- Don't change the git remote URL yet

## When done
Run: `openclaw system event --text "Done: dublin-rooms CLI with Aparto provider, watcher ready" --mode now`
