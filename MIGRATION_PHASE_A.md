# Migration: Phase A+ CLI

## Overview

The project migrated from interactive prompts to an agent-friendly CLI foundation.
Phase A+ adds booking-flow probing and OpenClaw-native notification/job orchestration.

## Architecture

- `client.py`: HTTP client for discovery + booking-flow endpoints.
- `matching.py`: room filters + strict Semester 1 matching policy.
- `models/config.py`: YAML config models and loader.
- `notifier.py`: OpenClaw message/agent delivery + optional cron job creation.
- `cli.py`: command dispatch (`discover`, `scan`, `watch`, `test-match`, `notify`, `probe-booking`).
- `main.py`: CLI entrypoint.

## Key behavior changes

- Removed legacy Python mobile notification flow (Pushover/config.ini path deprecated).
- Added strict Semester 1 constraints:
  - keyword match (`semester 1`)
  - month-window enforcement (Sep/Oct -> Jan/Feb)
- Added prioritization strategy for candidate selection:
  - ensuite first
  - cheapest weekly price next
- Added booking-flow probe command to produce actionable student-portal links.
- Added optional immediate OpenClaw reservation jobs on match.

## CLI summary

- `discover`: list countries/cities/residences.
- `scan`: single pass, optional notify, optional `--all-options`.
- `watch`: polling loop with optional notifications/jobs.
- `test-match`: validate Semester 1 policy quickly.
- `notify`: send a direct OpenClaw notification test.
- `probe-booking`: generate booking links/context for a selected match.

## Next steps

- Persist dedup state to avoid repeated alerts for identical option fingerprints.
- Add lock/cooldown for job creation to avoid duplicate reservation jobs.
- Add browser-assist runner command that consumes `probe-booking` JSON directly.
- Add integration tests with mocked Yugo API responses.
