<!--
  Visita Interiora Terrae, Rectificando Invenies Occultum Lapidem.
  Visit the interior of the earth; by rectifying, thou shalt find the hidden stone.
  You are reading this because you looked past the rendered page. Good. That is the point.
-->

<p align="center">
  <img src="assets/banner.svg" alt="Ashlar" width="640">
</p>

<p align="center"><em>Ordo ab Chao.</em></p>

# Ashlar

[![CI](https://github.com/lucas-weiselowski/ashlar/actions/workflows/ci.yml/badge.svg)](https://github.com/lucas-weiselowski/ashlar/actions/workflows/ci.yml)

**Ashlar is a context-compaction toolkit for AI coding agents.** When an agent calls a tool — reading a file, dumping a log, running a search — most of what comes back is noise: repeated reads of the same file, walls of stack trace, oversized search results. That noise still costs tokens even though the model never needed it. Ashlar's job is to cut it down to the part that actually matters before it reaches the model.

All three working tools exist now (see [Status](#status)): `record`/`report` to measure, `gavel` to dedup repeated reads, `chisel` to trim verbose output to its load-bearing lines. A [Claude Code skill](skill/ashlar/SKILL.md) wraps `gavel`/`chisel` with usage guidance so any agent harness knows when to reach for them.

The README frames this in a stonemason's metaphor, kept throughout: raw context is a rough stone from the quarry — irregular, heavy, unfit for the wall. Three tools work it into a finished ashlar (a squared building stone) fit for use: the 24-inch gauge to measure, the common gavel to knock off gross excess, the chisel to smooth what's left.

<p align="center">
  <img src="assets/ashlars.svg" alt="Rough ashlar to perfect ashlar" width="520">
</p>

## The Working Tools

Three tools, three jobs — each maps to a real piece of the toolkit:

**24-inch Gauge — measure.** Every block of context is counted before it's touched: tokens in, tokens out, waste identified. This is what `record`/`report` do.

**Common Gavel — knock off the gross excess.** `gavel` caches the last-seen content per key; a repeat read of the same file/resource collapses to a one-line "unchanged" marker or a unified diff instead of the full body again.

<!-- The 47th Problem of Euclid proves what the square only assumes. Measure twice; the ledger is the proof. -->

**Chisel — smooth what the gavel leaves.** `chisel` collapses repeated lines, keeps error/warning/traceback lines plus context, and head/tail-truncates anything still oversized — verbose logs, stack traces, and grep dumps reduced to their load-bearing lines.

What enters a rough ashlar leaves a perfect one: smaller, denser, doing the same work in the wall.

## Keeping the Ledger

`bin/ashlar` is a single-file Python (stdlib only) CLI with four subcommands: `record`, `report`, `gavel`, `chisel`. It writes to a JSONL ledger at `~/.ashlar/ledger.jsonl` (one line per recorded compaction) so savings aren't lost between sessions.

```
# Type in counts you already know:
$ ashlar record --before 14200 --after 3100 --label "grep dump, auth module"
Recorded: 14200 -> 3100 tokens (78% cut)

# ...or let ashlar estimate token counts from actual content (chars/4 heuristic, not a real tokenizer):
$ ashlar record --before-file raw_output.txt --after-file trimmed_output.txt --label "log dump"

# Totals across everything recorded:
$ ashlar report
Stones dressed:   1
Rough weight:     14,200 tokens
Perfect weight:   3,100 tokens
Waste removed:    11,100 tokens (78%)

# Breakdown per --label, or a time-windowed summary:
$ ashlar report --by-label
$ ashlar report --since 7d

# Dedup a repeated read of the same file (diffs against the last-seen version, cached under ~/.ashlar/gavel/):
$ cat some/file.py | ashlar gavel --key some/file.py

# Trim a verbose log/stack trace/grep dump down to its load-bearing lines:
$ some_noisy_command 2>&1 | ashlar chisel --max-lines 80

# Either one can log its own savings straight to the ledger:
$ ashlar chisel --file build.log --record --label "CI build log"
```

## Status

All four subcommands are real, working functionality: `record`/`report` to measure, `gavel` to dedup repeated reads, `chisel` to trim verbose output. The [`skill/ashlar`](skill/ashlar/SKILL.md) directory packages `gavel`/`chisel` as a Claude Code skill — usage guidance an agent can follow to invoke them before returning large tool output, portable to any harness that can shell out to a CLI filter.

## Installation

**As a Claude Code plugin** (installs the [skill](skill/ashlar/SKILL.md) so an agent invokes `gavel`/`chisel` on its own):

```
curl -fsSL https://raw.githubusercontent.com/lucas-weiselowski/ashlar/main/install.sh | bash
```

or from a local clone:

```
git clone <this-repo> && cd ashlar
./install.sh
```

This registers the repo as a marketplace (`claude plugin marketplace add`) and installs the `ashlar` plugin (`claude plugin install ashlar@ashlar`). Restart Claude Code to pick it up.

**As a standalone CLI only** (no plugin/skill, just the `ashlar` command):

```
git clone <this-repo>
chmod +x ashlar/bin/ashlar
export PATH="$PATH:/path/to/ashlar/bin"
```

Requires Python 3, no other dependencies. Check it's on your PATH with `ashlar --version`.

## License

MIT — see [LICENSE](LICENSE).

---

<p align="center"><em>So mote it be.</em></p>

<!--
  The Eye that watches the ledger is the same Eye that watches the work.
  What is measured cannot hide. What is hidden was only ever unexamined.
  G.
-->
