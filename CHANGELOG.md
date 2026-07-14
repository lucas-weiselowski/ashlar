# Changelog

Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/). Versioning follows [SemVer](https://semver.org/).

## [Unreleased]
### Added
- `hooks/posttooluse_bash_chisel.py` — Claude Code `PostToolUse` hook (matcher `Bash`) that transparently chisels large Bash stdout before it reaches the model, no manual invocation required. Skips small output (<500 estimated tokens), never touches `stderr`/`interrupted`/`isImage`, always preserves the final 20 lines of stdout verbatim, fails safe to a pure passthrough on any malformed input or internal error, and auto-records before/after token counts to the ledger (`auto:posttooluse:bash`). Wired into `.claude-plugin/plugin.json`.

### Changed
- README: reconciled "three tools" vs "four subcommands" phrasing, renamed "Keeping the Ledger" section to "Using the CLI" since it documents all four subcommands, not just `record`/`report`.

### Fixed
- `chisel`'s middle-elision (`--max-lines`) could silently drop a load-bearing line the keyword regex didn't recognize, with no way to recover it — safe enough for manual/human-checked use, but not for the new automatic hook. Elision now always saves the full original to `~/.ashlar/chisel/<hash>.txt` and points to it from the elision marker. `LOAD_BEARING_RE` also gained `critical`, `alert`, `abort(ed)?`, `invalid`, `corrupt(ed)?`.
- The recovery fix above only covered the `--max-lines` elision branch — the more common path (the keyword filter itself dropping every line outside `±context` of a match, without ever reaching elision) had no recovery at all. `cmd_chisel` now saves a recovery copy and appends the same pointer whenever *any* line is dropped, filtered or elided.
- Recovery copies hold full, unredacted command output and are now written far more often (automatically, via the hook, on any drop) — they're written `0600` instead of the default mode, and `~/.ashlar/chisel/` is pruned to the 200 most recent files instead of growing forever.
- `hooks/posttooluse_bash_chisel.py`'s tail-guard compared against raw stdout lines, but chisel collapses repeated lines into `line  (×N)` first — so a repetitive tail (retry loops, progress output) always failed the guard's `endswith` check and got re-appended as raw duplicates on top of the collapsed summary. The guard now checks each tail line's presence individually, collapsed form included.
- `hooks/posttooluse_bash_chisel.py` spawned two subprocesses per compacted call (`chisel`, then a separate `record`) — now a single `ashlar chisel --record` call does both.
- `hooks/posttooluse_bash_chisel.py` had no upper bound on input size before hashing/writing/regex-scanning; stdout over ~2MB now passes through untouched instead of paying that cost on a hot path.

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
