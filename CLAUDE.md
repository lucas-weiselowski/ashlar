# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

Ashlar is a context-compaction toolkit for AI agents: it trims bloated tool output (repeated file reads, verbose logs, oversized search results) down to a dense, load-bearing block before it reaches the model — the "rough ashlar → perfect ashlar" pitch in README.md. All three tools are implemented: `record`/`report` (measure), `gavel` (dedup repeated reads), `chisel` (trim verbose output). `skill/ashlar/SKILL.md` packages `gavel`/`chisel` as a Claude Code skill (see Architecture below).

## Commands

No build step, no runtime dependencies beyond Python 3 stdlib. Dev-only deps (`ruff`, `pytest`) are pinned in `requirements-dev.txt` and installed by CI from it — install locally with `pip install -r requirements-dev.txt` (or a venv) to run the same checks:

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
- Ledger storage is `~/.ashlar/ledger.jsonl` (home directory, **not** in this repo) — one JSON object per line: `{ts, before, after, label}`. `report` sums the whole file; there's no rotation/pruning. `gavel`'s per-key cache lives alongside it at `~/.ashlar/gavel/<sha256(key)[:16]>.txt`; `chisel` writes a full recovery copy to `~/.ashlar/chisel/<sha256(text)[:16]>.txt` whenever it drops *any* content (filtered by keyword or elided by `--max-lines`) — mode `0600` (command output routinely holds secrets) and pruned to the 200 most recent files, unlike the ledger/gavel cache.
- `skill/ashlar/SKILL.md` — Claude Code skill documenting when/how to invoke `gavel`/`chisel` (opt-in, agent decides). `skill/ashlar/scripts/ashlar` is a relative symlink to `bin/ashlar` (single source of truth stays in `bin/`); if you move either file, fix the symlink.
- `hooks/posttooluse_bash_chisel.py` — Claude Code `PostToolUse` hook (transparent, no agent decision needed) that pipes large Bash stdout through `bin/ashlar chisel` before Claude sees it. Not part of `bin/ashlar` itself (single-file rule stays scoped to the CLI) — shells out to it like any other caller. Wired via `.claude-plugin/plugin.json`'s `hooks.PostToolUse` with `matcher: "Bash"`. Fails safe to passthrough on anything it isn't fully certain about; see the file's own docstring for the exact contract.
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

## Parallel development workflow (worktrees + agents)

Lets multiple Claude Code agents work on ashlar at once without clobbering
each other, while `main` stays releasable and CI green.

**Standing authorization scope**: this section *is* the user's standing
authorization for agents to commit and push on non-`main` branches per the
rules below, without asking each time. It does **not** extend to merging
into `main`, tagging, or pushing tags — those stay per-action, ask-first
(merge/tag are harder to reverse and touch shared state).

### Topology
- Main checkout (`/Users/lucas/Documents/Code/ashlar`) stays clean, on
  `main`, always releasable. Never used for direct feature edits — only
  merges, tags, and release commits.
- Each feature/fix gets its own branch + its own git worktree, sibling to
  the main checkout: `../ashlar-worktrees/<slug>/`. One agent per worktree,
  one worktree per branch — never two agents in the same worktree or on
  the same branch concurrently.
- Prefer the Agent tool's `isolation: "worktree"` option to spin these up
  (auto-created, auto-removed if the agent makes no changes) over
  hand-running `git worktree add` for ad hoc parallel work. Use manual
  `git worktree add -b <branch> ../ashlar-worktrees/<slug>` only when a
  worktree must persist across multiple turns/sessions.
- Branch naming: `feat/<slug>`, `fix/<slug>`, `chore/<slug>` — matches the
  Conventional Commits type already used for commit subjects.

### Before starting work in a new worktree
Check other open branches/worktrees for overlap on `bin/ashlar` (it's a
single file, no module boundaries — two agents editing the same
subcommand concurrently will conflict): `git diff main...<other-branch> --
bin/ashlar` for each active branch. If scopes overlap, serialize instead
of parallelizing — don't spawn both at once.

### Commit policy (inside a worktree)
Commit when a coherent unit of work is done AND `ruff check .`,
`ruff format --check .`, `python -m pytest -v` all pass in that worktree.
Never commit red/broken state. Small, atomic commits, Conventional
Commits format, trailer `Co-Authored-By: Claude <noreply@anthropic.com>`
(existing repo convention — no model name, no Claude-Session line);
generate the message via `/caveman:caveman-commit`. Never commit directly
to `main` from a worktree.

### Push + PR policy
Before opening a PR, rebase the branch onto latest `main`
(`git fetch origin && git rebase origin/main`). `CHANGELOG.md`
`[Unreleased]` conflicts during rebase are expected when branches land in
parallel — resolve by keeping both entries (append, don't drop either
side). Then `git push -u origin <branch>` and `gh pr create` targeting
`main`. Self-review the diff (e.g. via the `code-reviewer` agent or
`/code-review`) before opening the PR — cuts down what the solo human
maintainer has to catch by hand.

### Merge policy
Merge to `main` only when CI is green on the PR **and** the user has
confirmed that specific merge. Always squash-merge
(`gh pr merge --squash --delete-branch`) — commit history inside a
feature branch isn't worth preserving in this repo, so there's no
judgment call to make. After merge (or if a PR is rejected/abandoned):
`git worktree remove ../ashlar-worktrees/<slug>` and confirm the remote
branch is gone, so worktrees never pile up stale.

### Tag / release policy
Unchanged from "Versioning / releases" below, just anchored here: tag
only from `main`, only when the user explicitly asks to cut a release —
never autonomously. Push the tag immediately after creating it (that's
what triggers `release.yml`). If `release.yml` fails *after* the tag is
already pushed, don't force-move or delete the public tag — fix the
underlying issue, bump to the next patch version, and cut a new tag
instead.

### Decision table
| Action | Who decides | Trigger |
|---|---|---|
| commit | agent, in its worktree | unit done + lint/tests green |
| push branch | agent | ready for CI/review (rebased on main first) |
| open PR | agent | after push, after self-review |
| merge to main | user confirms, agent executes | CI green + user OK |
| tag release | user asks explicitly | releasable set merged to main |
| push tag | agent, immediately after tagging | always (triggers release.yml) |

### Not yet enforced
Branch protection (required status checks on `main`) isn't configured —
this workflow is doc-level policy, not repo-enforced. Consider enabling
it in GitHub settings if agents start bypassing the PR flow.

## Conventions specific to this repo

- Commit trailer: `Co-Authored-By: Claude <noreply@anthropic.com>` — no model name/version, and no `Claude-Session:` line. This differs from the default global convention and is intentional for this project.
- README.md carries the Masonic theme deliberately (rough/perfect ashlar, "Ordo ab Chao", "So mote it be") and contains **intentional hidden HTML comments** (VITRIOL acrostic, 47th Problem of Euclid reference, All-Seeing Eye) that are invisible on the rendered GitHub page by design. Do not strip these as dead/unnecessary comments — preserve the theme and the hidden-message convention in any README edits, and keep new hidden content in the same style (real Masonic/esoteric references, not invented pseudo-history).
