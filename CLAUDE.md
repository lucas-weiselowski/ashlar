# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

Ashlar is a context-compaction toolkit for AI agents: it trims bloated tool output (repeated file reads, verbose logs, oversized search results) down to a dense, load-bearing block before it reaches the model — the "rough ashlar → perfect ashlar" pitch in README.md. All three tools are implemented: `record`/`report` (measure), `gavel` (dedup repeated reads), `chisel` (trim verbose output). `skill/ashlar/SKILL.md` packages `gavel`/`chisel` as a Claude Code skill (see Architecture below).

## Commands

No build step, no runtime dependencies beyond Python 3 stdlib. Dev-only deps (`ruff`, `pytest`) are pulled ad hoc by CI, not vendored — install locally with `pip install ruff pytest` (or a venv) to run the same checks:

```
python -m pytest -v          # tests/test_ashlar.py — subprocess-driven, isolated $HOME per test
ruff check .
ruff format --check .
```

```
chmod +x bin/ashlar                                   # first run only
./bin/ashlar record --before 14200 --after 3100 --label "grep dump, auth module"
./bin/ashlar report
./bin/ashlar report --by-label
./bin/ashlar report --since 7d
./bin/ashlar gavel --key some/file.py --file some/file.py
./bin/ashlar chisel --file build.log --max-lines 80
./bin/ashlar --version
```

`--before`/`--after` are token counts; `--label` is optional free text. `--before-file`/`--after-file` (path or `-` for stdin) estimate a count from content instead (chars/4 heuristic — not a real tokenizer). `gavel`/`chisel` read from `--file` or stdin, write the compacted result to stdout, stats to stderr, and both accept `--record [--label]` to log straight to the ledger.

## Architecture

- `bin/ashlar` — the entire CLI. Single-file Python script, stdlib `argparse` with four subcommands (`record`, `report`, `gavel`, `chisel`). No package structure, no external deps — keep it that way unless the tool actually grows past a single file.
- Ledger storage is `~/.ashlar/ledger.jsonl` (home directory, **not** in this repo) — one JSON object per line: `{ts, before, after, label}`. `report` sums the whole file; there's no rotation/pruning. `gavel`'s per-key cache lives alongside it at `~/.ashlar/gavel/<sha256(key)[:16]>.txt`.
- `skill/ashlar/SKILL.md` — Claude Code skill documenting when/how to invoke `gavel`/`chisel`. `skill/ashlar/scripts/ashlar` is a relative symlink to `bin/ashlar` (single source of truth stays in `bin/`); if you move either file, fix the symlink.
- `assets/*.svg` — hand-authored, no external image fetching or third-party assets. Keep any future images the same way (self-contained inline SVG, no CDN/network dependency).
- `.github/workflows/ci.yml` — lint (ruff) + test (pytest, matrix Python 3.9–3.13) + CLI smoke job, on push/PR to `main`. Third-party Actions are pinned to commit SHA (comment carries the version tag); `.github/dependabot.yml` opens monthly PRs to bump them.
- `.github/workflows/release.yml` — on `vX.Y.Z` tag push: verifies `__version__` and a matching `CHANGELOG.md` section, re-runs tests, then publishes a GitHub Release via `.github/scripts/extract_release_notes.py` (pulls that version's changelog section as the release body).

## Roadmap context

The README's "Working Tools" section (24-inch gauge / common gavel / chisel) maps 1:1 to the CLI subcommands — all three are built:
- 24-inch gauge → `record`/`report` (measuring)
- common gavel → `gavel` (dedup repeated tool output / diff repeated file reads)
- chisel → `chisel` (verbose logs/output reduced to load-bearing lines)

Keep any future additions consistent with this naming rather than inventing new terminology.

## Versioning / releases

`__version__` lives in `bin/ashlar` (SemVer). `CHANGELOG.md` follows Keep a Changelog. Each release: bump `__version__`, move `[Unreleased]` entries into a dated version section in `CHANGELOG.md`, tag `vX.Y.Z` (annotated) on the release commit, push the tag — `release.yml` verifies version/changelog agree, re-runs tests, and publishes the GitHub Release automatically. A mismatch (forgot to bump, or CHANGELOG section missing) fails the workflow before anything is published.

## Conventions specific to this repo

- Commit trailer: `Co-Authored-By: Claude <noreply@anthropic.com>` — no model name/version, and no `Claude-Session:` line. This differs from the default global convention and is intentional for this project.
- README.md carries the Masonic theme deliberately (rough/perfect ashlar, "Ordo ab Chao", "So mote it be") and contains **intentional hidden HTML comments** (VITRIOL acrostic, 47th Problem of Euclid reference, All-Seeing Eye) that are invisible on the rendered GitHub page by design. Do not strip these as dead/unnecessary comments — preserve the theme and the hidden-message convention in any README edits, and keep new hidden content in the same style (real Masonic/esoteric references, not invented pseudo-history).
