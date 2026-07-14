# AGENTS.md

Instructions for AI coding agents (GitHub Copilot coding agent, OpenAI Codex, and similar) working in this repository.

## What this is

Ashlar is a context-compaction toolkit for AI agents: it trims bloated tool output (repeated file reads, verbose logs, oversized search results) down to a dense, load-bearing block before it reaches a model. Three tools, one CLI (`bin/ashlar`):

- `record`/`report` — measure token savings, ledger at `~/.ashlar/ledger.jsonl` (not in this repo)
- `gavel` — dedup repeated tool output (per-key cache under `~/.ashlar/gavel/`)
- `chisel` — trim verbose text (logs, stack traces) to load-bearing lines

`skill/ashlar/SKILL.md` packages `gavel`/`chisel` as a Claude Code skill; `skill/ashlar/scripts/ashlar` is a relative symlink to `bin/ashlar` — fix it if you move either file.

## Setup and validation

No build step, no runtime dependencies beyond Python 3 stdlib. Dev-only deps are pinned in `requirements-dev.txt`:

```
python3 -m venv .venv && source .venv/bin/activate   # or any venv approach
pip install -r requirements-dev.txt
chmod +x bin/ashlar

ruff check .
ruff format --check .
python -m pytest -v
```

All three must pass before proposing a change. `tests/test_ashlar.py` drives `bin/ashlar` as a subprocess with an isolated `$HOME` per test — don't mock around it.

## Code conventions

- `bin/ashlar` is a single-file Python script, stdlib `argparse`, no package structure, no external deps. Keep it that way unless the tool genuinely outgrows one file — don't split it preemptively.
- Line length 120, target Python 3.9 (see `pyproject.toml`'s `[tool.ruff]`). Lint rules: `E`, `F`, `I`, `UP`, `B`.
- No comments explaining *what* code does — only *why*, when non-obvious (a workaround, a hidden constraint). Match the terse style already in `bin/ashlar`.
- Follow the existing "24-inch gauge / common gavel / chisel" naming from README.md's Working Tools section for any new subcommand — don't invent new terminology for the same concepts.

## Commit / PR conventions

- Conventional Commits format, subject ≤50 chars, body only when the "why" isn't obvious from the diff.
- Commit trailer: `Co-Authored-By: Claude <noreply@anthropic.com>` — no model name/version, no session links. This repo intentionally omits those, unlike other repos this author works in.
- Target PRs at `main`. `main` has required status checks (`lint`, `test` × Python 3.9–3.13, `smoke`, `CodeQL`) enforced via branch protection — a PR cannot merge until all are green.
- Squash-merge only; no merge commits.

## CI pipeline

- `.github/workflows/ci.yml` — lint (ruff), test (pytest matrix across 3.9–3.13), smoke (end-to-end CLI exercise). Runs on push/PR to `main` and manual `workflow_dispatch`.
- `.github/workflows/codeql.yml` — CodeQL static analysis for Python, on push/PR to `main` plus a weekly cron.
- `.github/workflows/release.yml` — on `vX.Y.Z` tag push: verifies `bin/ashlar`'s `__version__`, `.claude-plugin/plugin.json`'s `version`, and a matching `CHANGELOG.md` section all agree with the tag, re-runs lint + tests, then publishes a GitHub Release.
- All third-party Actions are pinned to a full commit SHA with the version as a trailing `# vX.Y.Z` comment — never reference an Action by a mutable tag (`@v4`, `@main`). `.github/dependabot.yml` opens monthly PRs to bump these.
- Every job has `timeout-minutes` set — don't remove it when editing a workflow.

## Versioning

`__version__` in `bin/ashlar` and `version` in `.claude-plugin/plugin.json` must both match the release tag; `CHANGELOG.md` (Keep a Changelog format) needs a section for that version. All three are checked by `release.yml` before anything publishes — a mismatch fails the workflow, nothing goes out half-done.

## Things not to touch without a strong reason

- README.md's Masonic theme (rough/perfect ashlar, "Ordo ab Chao", hidden HTML comments) is deliberate — don't strip hidden comments as dead code.
- The ledger/gavel-cache paths under `~/.ashlar/` are user home directory state, never repo-tracked — don't add code that writes them into the repo.
- Don't add a requirements file, lockfile, or dependency beyond `requirements-dev.txt`'s existing pins without a clear reason; this project's whole pitch is "no runtime deps beyond stdlib."
