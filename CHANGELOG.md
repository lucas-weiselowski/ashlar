# Changelog

Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/). Versioning follows [SemVer](https://semver.org/).

## [Unreleased]
### Added
- `chisel --max-line-chars` (default 2000) — caps a single oversized line, head/tail elided. Line-based collapsing and `--max-lines` truncation both operate at line granularity, so a single huge line with no newlines (minified JSON, a base64 blob, one giant API response) previously sailed through completely uncompacted.
- `chisel --normalize-repeats` — opt-in, collapses consecutive lines that differ only by a timestamp/UUID/epoch value, not just byte-identical ones. Off by default so existing exact-match behavior is unchanged.
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
- `LOAD_BEARING_RE` used `\b(error|exception|...)\b`, which never matches inside a glued identifier like `NullPointerException` or `TypeError` — no word boundary exists between lowercase and uppercase letters mid-word. Real exception class names in stack traces were silently filtered out. Widened to `\b\w*(?:error|exception|...)\w*\b`.
- Same regex missed plural/gerund forms — `\bwarn(?:ing)?\b` didn't match "warnings", `\bfail(?:ed|ure)?\b` didn't match "failing"/"fails" (trailing word characters block the closing `\b`). Replaced the fixed suffix alternatives with open `\w*` wrapping, same approach `assert\w*` already used correctly.
- `gavel`'s unified diff could be larger than the source itself on near-total rewrites (e.g. a timestamp changing on every line), silently costing more tokens than it saved on real-world-sized input. `gavel` now falls back to emitting the full new content when the diff isn't actually smaller — gated to inputs ≥500 estimated tokens so the documented tiny-input overhead case (see SKILL.md) is untouched.
- `gavel`'s cache key and `chisel`'s recovery-copy filename both truncated their sha256 digest to 16 hex chars (64 bits) — a collision would silently diff against, or point recovery at, the wrong content with no error. Both now use the full 64-char digest.
- A single line with no newlines (minified JSON, a base64 blob, a giant one-line API response) passed through `chisel` completely uncompacted — every reduction path (dedup, keyword filter, `--max-lines`) operates on lines, and there was only ever one. New `--max-line-chars` (default 2000) truncates any individual oversized line, head/tail, independent of line count.
- `chisel`/`gavel` crashed with an uncaught `UnicodeDecodeError` on non-UTF-8 input (a truncated multibyte char, stray binary from a killed process) instead of degrading gracefully. Reads now use `errors="replace"`.
- A single malformed line in `~/.ashlar/ledger.jsonl` (partial write from a killed process, hand-edited) crashed `report` entirely and permanently, with no way to see any totals until the file was manually fixed. Malformed lines are now skipped.
- No concurrency guard existed on the ledger append or the gavel cache read-modify-write — relevant since this repo's own workflow runs multiple agents against the same `~/.ashlar/` directory in parallel. Both now take an advisory `flock` for the duration of the critical section.
- `chisel --max-lines`/`--context` and `report --since` accepted nonsensical input (`--max-lines 0`, negative `--context`, an empty `--since`) that produced garbled output or a raw traceback instead of a clear error. Now validated at the argparse layer.
- Colorized log output (ANSI escape codes) inflated token counts for no semantic value and defeated exact-match line dedup when two otherwise-identical lines differed only by color codes. `chisel`/`gavel` now strip ANSI escapes before processing (the reported "before" count still reflects the true raw input size, so the strip counts toward savings, not against them).

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
