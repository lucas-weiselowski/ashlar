# Benchmark fixtures

How the 6 scenarios in [`benchmark-report-v2.html`](../benchmark-report-v2.html)
were built, and how to regenerate them.

## Why synthetic, not captured

The v1 report (`benchmark-report.html`) used two real captures (this repo's own
`pytest` run, `bin/ashlar`'s own source) and four synthetic-but-representative
fixtures. v2 standardizes on synthetic fixtures for all six, built to match the
same named, common agent tool-output shapes — a real capture isn't reproducible
by someone else on a different machine/repo state, a generator script is.

## The 6 scenarios

| # | Scenario | How it's built |
|---|----------|-----------------|
| 1 | `gavel` — unchanged repeat read | `bin/ashlar`'s own source, read twice with no changes between reads. |
| 2 | `gavel` — single-line edit repeat read | Same source, `__version__` string bumped by one line between reads. |
| 3 | `gavel` — ~50% file rewrite repeat read | Same source, second half of all lines replaced with unrelated placeholder comments — a unified diff of the two versions shares little content, which is the case that used to cost `gavel` tokens (see the "Since the last report" section of the v2 report). |
| 4 | `chisel` — verbose test run | 479 synthetic `pytest`-style PASS lines + 1 FAILED line + a failure traceback block, seeded so the run is deterministic. |
| 5 | `chisel` — large grep dump | 750 synthetic `file:line:content` grep hits across 7 fake source files and 10 code-shaped terms, **none of which match chisel's load-bearing keyword list on purpose** — a generic symbol-name grep dump is mostly not error/warning-shaped. One load-bearing-but-unlabeled comment (a circular-dependency warning) is planted mid-list to reproduce the "keyword selection is exact, not semantic" finding. |
| 6 | `chisel` — build log + Python traceback | ~700 synthetic build-step lines + a traceback ending in `ConfigValidationError` — a CamelCase exception name with no word boundary before "Error", the exact shape `LOAD_BEARING_RE`'s CamelCase fix targets. |

Scenarios 4–6 use `random.seed(42)` / `random.seed(7)` (see the script) so the
generated content is byte-identical across runs and machines — only the
fixture *shape* is synthetic, not its determinism.

## Regenerating

```
cd /tmp/some-scratch-dir   # writes 6 files + the ledger to the current dir / $HOME
python3 /path/to/ashlar/docs/benchmark-fixtures/generate_fixtures.py
```

This writes the 6 fixture files to the current directory, then runs the same
`gavel`/`chisel` commands the v2 report's Method section describes against
whatever `bin/ashlar` is checked out at `../../bin/ashlar` relative to this
script, recording results to `~/.ashlar/ledger.jsonl` under `bench:*-v2` /
`bench:*-v2b` labels. Read them back with:

```
ashlar report --by-label | grep -E 'bench:.*-v2'
```

**Before-token counts reproduce exactly** — the fixture content is
deterministic. **After-token counts for the 3 `chisel` scenarios can differ by
a handful of tokens** across machines: `chisel` embeds a recovery-file path
(`~/.ashlar/chisel/<hash>.txt`) into its own output as a recovery marker, and
that path's length depends on your `$HOME`. Cut percentages are stable to
within a rounding point; the per-scenario token counts in the v2 report are
this machine's exact numbers, not a universal constant.

## Cleaning up a bench run

These scenarios write to the same `~/.ashlar/ledger.jsonl` and
`~/.ashlar/gavel/` cache that real usage does — there's no `ashlar` subcommand
to delete a ledger entry by label. If you want to re-run without accumulating
duplicate `bench:*` rows, either use a fresh `--label` suffix (as `-v2` /
`-v2b` do here relative to the original `v1` run) or run with `HOME` pointed
at a scratch directory:

```
HOME=/tmp/ashlar-bench-scratch python3 generate_fixtures.py
```
