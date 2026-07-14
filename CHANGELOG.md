# Changelog

Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/). Versioning follows [SemVer](https://semver.org/).

## [Unreleased]
### Added
- `release.yml` verify job now checks `.claude-plugin/plugin.json`'s `version` matches the release tag, same as it already does for `bin/ashlar`'s `__version__` — a forgotten bump there used to pass CI silently while leaving installed plugin users stuck without updates.
- Standalone binaries: every tagged release now builds and publishes PyInstaller binaries for Linux (x86_64), macOS (arm64 and x86_64), and Windows (x86_64), plus a `SHA256SUMS` file, so `ashlar` can be used without Python installed. `requirements-build.txt` pins `pyinstaller`. `ci.yml` gained a fast single-platform build+smoke job so a packaging break shows up on every PR, not just at release time. `.github/dependabot.yml` now also watches the `pip` ecosystem.
- `record --max-ledger-age` — prunes ledger entries older than the given duration (default 90d, `0` disables) before appending, so `~/.ashlar/ledger.jsonl` no longer grows unbounded on a long-lived install and `report` stays cheap to scan.

### Changed
- README: reconciled "three tools" vs "four subcommands" phrasing, renamed "Keeping the Ledger" section to "Using the CLI" since it documents all four subcommands, not just `record`/`report`.
- README: moved Installation above Using the CLI (usage examples referenced `ashlar` before saying how to get it), and dropped the "Status" section — it restated the intro/Working-Tools content near-verbatim with no new information.

### Fixed
- `chisel`: `LOAD_BEARING_RE` now also matches CamelCase exception names (`ValueError`, `KeyError`, ...) — previously `\berror\b` required a word boundary that CamelCase names don't have, so the actual exception message in a traceback could get chiseled away while only the literal "Traceback" line survived. The added alternative is scoped case-sensitive so it only catches CamelCase, not lowercase substrings like "terror" (#5).
- `gavel`: falls back to sending the full new content instead of a unified diff when the diff isn't actually smaller — near-total rewrites could previously produce a diff bigger than just the new text, defeating the point of the tool for that call (#10).
- `report --by-label`: labels longer than 31 chars now get a visible `...` ellipsis instead of being silently cut off with no indication of truncation (#9).

## [0.2.0] - 2026-07-14
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
- `.claude-plugin/plugin.json` + `.claude-plugin/marketplace.json` — repo installable as a Claude Code plugin (own single-plugin marketplace).
- `install.sh` — one-line installer (`curl | bash` or local clone); adds this repo as a marketplace and installs the `ashlar` plugin via `claude plugin`.
- `requirements-dev.txt` — pins `ruff`/`pytest` versions used by CI and local dev, replacing unpinned `pip install`.

### Changed
- CI/release workflows now install dev deps from `requirements-dev.txt` (pinned, cached via `actions/setup-python`'s `cache: pip`) instead of `pip install ruff`/`pip install pytest` grabbing latest each run.
- `smoke` job now depends on both `lint` and `test` passing (previously only `test`), so a formatting break no longer burns a smoke-test runner.
- `release.yml`'s `verify` job now also runs `ruff check`/`ruff format --check`, so a lint regression can't slip into a tagged release even if it slipped past `main`.
- `ci.yml` gained a `workflow_dispatch` trigger for manual re-runs.

## [0.1.0] - 2026-07-14
### Added
- `record`/`report` subcommands, JSONL ledger at `~/.ashlar/ledger.jsonl`.
- `report --by-label` — per-label savings breakdown.
- `report --since` — time-windowed summary (`30m`, `24h`, `7d`, `2w`).
- `record --before-file`/`--after-file` (path or `-` for stdin) — measure piped or file content via a chars/4 token estimate instead of typing counts by hand.
- `--version` flag.
