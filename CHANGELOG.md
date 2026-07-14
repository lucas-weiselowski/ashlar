# Changelog

Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/). Versioning follows [SemVer](https://semver.org/).

## [Unreleased]
### Added
- `gavel` subcommand — dedup repeated tool output; caches last-seen content per `--key` under `~/.ashlar/gavel/`, returns an unchanged-marker or unified diff on repeat reads instead of the full body.
- `chisel` subcommand — trim verbose text (logs, stack traces, grep dumps) to load-bearing lines: collapses repeated lines, keeps error/warning/traceback matches plus `--context`, head/tail-truncates to `--max-lines`.
- `gavel`/`chisel` both accept `--record [--label]` to log their before/after token counts straight to the ledger.
- `skill/ashlar/SKILL.md` — Claude Code skill wrapping `gavel`/`chisel` with usage guidance, portable to any agent harness that can shell out.
- `tests/test_ashlar.py` — pytest suite driving `bin/ashlar` as a subprocess (isolated `$HOME` per test) covering all four subcommands.
- CI (`.github/workflows/ci.yml`): ruff lint/format check, pytest across Python 3.9–3.13, and an end-to-end CLI smoke job. Runs on push/PR to `main`.
- Release automation (`.github/workflows/release.yml`): pushing a `vX.Y.Z` tag verifies `__version__`/CHANGELOG.md agree with the tag, re-runs the test suite, then publishes a GitHub Release with that version's changelog section as the body.
- `.github/dependabot.yml` — monthly PRs to bump pinned Action SHAs.
- `pyproject.toml` — ruff (lint + format) and pytest config.

## [0.1.0] - 2026-07-14
### Added
- `record`/`report` subcommands, JSONL ledger at `~/.ashlar/ledger.jsonl`.
- `report --by-label` — per-label savings breakdown.
- `report --since` — time-windowed summary (`30m`, `24h`, `7d`, `2w`).
- `record --before-file`/`--after-file` (path or `-` for stdin) — measure piped or file content via a chars/4 token estimate instead of typing counts by hand.
- `--version` flag.
