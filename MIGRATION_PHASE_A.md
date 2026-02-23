# Migration: Phase A CLI

## Overview

Phase A replaces the interactive console flow with a CLI-first, non-interactive foundation. The scraper still reads the Yugo API and applies matching/filtering rules, but no booking or browser automation is included.

## Architecture

- `client.py`: thin HTTP client for Yugo endpoints (countries, cities, residences, rooms, tenancy options).
- `matching.py`: room filters and Semester 1 matching logic.
- `models/config.py`: YAML/INI configuration models and loader.
- `notifier.py`: Pushover sender + OpenClaw placeholder trigger.
- `cli.py`: command dispatch (`discover`, `scan`, `watch`, `test-match`, `notify`).
- `main.py`: CLI entrypoint.

## Configuration flow

- `config.yaml` is the primary configuration file.
- `config.ini` is still accepted for legacy Pushover credentials when YAML is absent or missing them.
- Command-line flags can override target location resolution on a per-run basis.

## CLI summary

- `discover`: list countries, cities, or residences.
- `scan`: run a single scan and print matches.
- `watch`: poll periodically using `polling.interval_seconds` and `polling.jitter_seconds`.
- `test-match`: quick check of Semester 1 matching rules.
- `notify`: send a test notification to configured channels.

## Next steps (Phase B/C)

- Add persistent state to avoid duplicate notifications.
- Extend matching rules to cover multiple semesters and custom date ranges.
- Implement booking automation or external integrations (OpenClaw triggers).
- Package CLI as an installable `yugo` console script.
- Add integration tests with mocked API responses.
