# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

Ashlar is a context-compaction toolkit for AI agents: it trims bloated tool output (repeated file reads, verbose logs, oversized search results) down to a dense, load-bearing block before it reaches the model — the "rough ashlar → perfect ashlar" pitch in README.md. Today only the tracking side is built; the compaction engine itself is not yet implemented (see Architecture below).

## Commands

No build step, no dependencies beyond Python 3 stdlib, no test suite yet.

```
chmod +x bin/ashlar                                   # first run only
./bin/ashlar record --before 14200 --after 3100 --label "grep dump, auth module"
./bin/ashlar report
./bin/ashlar report --by-label
./bin/ashlar report --since 7d
./bin/ashlar --version
```

`--before`/`--after` are token counts; `--label` is optional free text. `--before-file`/`--after-file` (path or `-` for stdin) estimate a count from content instead (chars/4 heuristic — not a real tokenizer).

## Architecture

- `bin/ashlar` — the entire CLI. Single-file Python script, stdlib `argparse` with two subcommands (`record`, `report`). No package structure, no external deps — keep it that way unless the tool actually grows past a single file.
- Ledger storage is `~/.ashlar/ledger.jsonl` (home directory, **not** in this repo) — one JSON object per line: `{ts, before, after, label}`. `report` sums the whole file; there's no rotation/pruning.
- `assets/*.svg` — hand-authored, no external image fetching or third-party assets. Keep any future images the same way (self-contained inline SVG, no CDN/network dependency).

## Roadmap context

The README's "Working Tools" section (24-inch gauge / common gavel / chisel) is the actual technical roadmap, not just flavor text:
- 24-inch gauge → measuring (what `record`/`report` do today)
- common gavel → bulk trimming (dedup repeated tool output, diff repeated file reads) — not yet built
- chisel → fine smoothing (summarizing verbose logs/output down to load-bearing lines) — not yet built

When implementing either, keep the tool naming consistent with this mapping rather than inventing new terminology.

## Versioning / releases

`__version__` lives in `bin/ashlar` (SemVer). `CHANGELOG.md` follows Keep a Changelog. Each release: bump `__version__`, move `[Unreleased]` entries into a dated version section in `CHANGELOG.md`, tag `vX.Y.Z` (annotated) on the release commit.

## Conventions specific to this repo

- Commit trailer: `Co-Authored-By: Claude <noreply@anthropic.com>` — no model name/version, and no `Claude-Session:` line. This differs from the default global convention and is intentional for this project.
- README.md carries the Masonic theme deliberately (rough/perfect ashlar, "Ordo ab Chao", "So mote it be") and contains **intentional hidden HTML comments** (VITRIOL acrostic, 47th Problem of Euclid reference, All-Seeing Eye) that are invisible on the rendered GitHub page by design. Do not strip these as dead/unnecessary comments — preserve the theme and the hidden-message convention in any README edits, and keep new hidden content in the same style (real Masonic/esoteric references, not invented pseudo-history).
