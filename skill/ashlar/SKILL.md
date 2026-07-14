---
name: ashlar
description: Compact oversized tool output before it lands in context — dedup repeated file reads/tool calls (gavel), trim verbose logs/stack traces/grep dumps down to load-bearing lines (chisel), and track token savings over time (record/report). Use BEFORE returning a large chunk of raw output (roughly >2k tokens) back into the conversation, especially: re-reading a file you already read this session, a stack trace or app log, a grep/search dump with many hits, or any repeated tool call whose output barely changed since last time.
---

Ashlar is a stdlib-only Python CLI (`bin/ashlar`, no dependencies). It reads
stdin/a file, writes the compacted result to stdout, and prints stats to
stderr — so it composes with any shell pipeline, in Claude Code or any other
agent harness that can exec a subprocess. Nothing here is Claude-specific.

Binary: `ashlar` if on `PATH` (see repo README), otherwise use the copy
alongside this skill: `scripts/ashlar` (symlink to the repo's `bin/ashlar`).
If neither resolves, this skill's script is missing its target — copy
`bin/ashlar` next to `scripts/` or fix the symlink.

## When to reach for which tool

| Situation | Tool | Command |
|---|---|---|
| Re-reading a file/resource you (or another agent) already pulled this session | **gavel** | `ashlar gavel --key <path-or-id>` |
| Stack trace, app log, build/CI output | **chisel** | `ashlar chisel` |
| Grep/search dump with many repetitive hits | **chisel** | `ashlar chisel --max-lines 100` |
| Want cumulative savings tracked | either, add | `--record --label "<what>"` |

## gavel — dedup repeated reads

Caches the last-seen content per `--key` under `~/.ashlar/gavel/`. First call
returns content unchanged (nothing to dedup against yet). A later call with
identical content returns a one-line `<unchanged since last read: KEY>`
marker instead of the full body. A later call with different content returns
a unified diff instead of the full body.

```
cat some/file.py | ashlar gavel --key some/file.py
```

Use the resource's real path (or a stable logical id) as `--key` so repeat
reads of the *same* thing collide in the cache. Read stats from stderr
(`before -> after tokens`) before deciding whether the diff is worth keeping
over the full content — on tiny inputs the marker/diff overhead can exceed
the original, which is expected and reported honestly, not hidden.

## chisel — trim verbose text to load-bearing lines

Collapses consecutive duplicate lines to `line  (×N)`, keeps lines matching
error/exception/traceback/fail/fatal/panic/warn/timeout/etc. plus
`--context` lines around each match (default 2), and — if nothing matches,
or the result is still too long — falls back to head/tail truncation
(`--max-lines`, default 200) with a `... N lines elided ...` marker for the
middle.

```
some_command_that_dumps_a_huge_log 2>&1 | ashlar chisel --max-lines 80
```

Tune `--context` up if a matched error needs more surrounding lines to be
useful; tune `--max-lines` down for a harder cap on genuinely huge dumps.

The built-in keyword list is a fixed, English-only set — it can both miss
real failures worded differently (`segfault`, non-English error text,
framework-specific codes) and keep prose that merely mentions one of the
words. Pass `--keep-pattern REGEX` (repeatable) to OR extra terms into the
check without losing the built-in list:

```
ashlar chisel --file build.log --keep-pattern segfault --keep-pattern 'oom-killer'
```

## record/report — track savings

Both `gavel` and `chisel` accept `--record [--label X]` to log their
before/after token counts (chars/4 heuristic, not a real tokenizer) to the
same ledger `record` writes to. Check cumulative savings anytime:

```
ashlar report --by-label
ashlar report --since 7d
```

## Portability note

This skill has no Claude-specific coupling — `ashlar gavel`/`ashlar chisel`
are plain CLI filters (stdin/file in, stdout out, stats on stderr). Any
agent harness that can shell out can drop in the same two commands ahead of
returning tool output to its model.
