#!/usr/bin/env python3
"""
PostToolUse hook: transparently chisels large Bash stdout before it reaches
the model. Automated wiring for `ashlar chisel` (see repo CLAUDE.md
"Roadmap context" — common gavel / chisel roadmap).

Contract: on ANY doubt, uncertainty, or error — print nothing and exit 0
(pure passthrough). Never touch stderr/interrupted/isImage. Never drop the
tail of stdout.

COST MODEL: this interpreter starts on every single Bash tool call,
regardless of output size — the plugin.json matcher is unconditionally
"Bash"; there is no hook-level mechanism to gate on tool_response size
before the hook process itself launches. MIN_TOKENS_TO_COMPACT and
MAX_BYTES_TO_COMPACT below gate the one `ashlar chisel` subprocess this
hook spawns (it also does the ledger recording, via --record, so there's
never a second subprocess). The floor cost is one python3 cold start per
Bash call, always paid.
"""

import json
import subprocess
import sys
from pathlib import Path

CHARS_PER_TOKEN = 4  # same heuristic bin/ashlar uses everywhere; duplicated
# here as one line of arithmetic only — the actual
# chisel algorithm is invoked via subprocess, not
# reimplemented (bin/ashlar is extensionless, not an
# importable module).

MIN_TOKENS_TO_COMPACT = 500  # ~2000 chars; below this, subprocess overhead
# for `ashlar chisel` (~35-40ms) isn't worth it.
MAX_BYTES_TO_COMPACT = 2_000_000  # ~2MB; above this, chisel's own hash/write/
# regex-scan cost isn't worth paying on a hot
# path that fires on every qualifying Bash
# call — skip and passthrough instead.
TAIL_GUARD_LINES = 20  # final N lines of stdout are always preserved
# verbatim — exit-status-adjacent content
# usually lives there and chisel's regex
# doesn't guarantee it survives.

ASHLAR_BIN = Path(__file__).resolve().parent.parent / "bin" / "ashlar"
CHISEL_TIMEOUT_SECONDS = 5


def _estimate_tokens(text):
    return len(text) // CHARS_PER_TOKEN


def _passthrough():
    sys.exit(0)


def main():
    try:
        raw_stdin = sys.stdin.read()
    except Exception:
        _passthrough()

    try:
        payload = json.loads(raw_stdin)
    except Exception:
        _passthrough()

    if not isinstance(payload, dict) or payload.get("tool_name") != "Bash":
        _passthrough()

    tool_response = payload.get("tool_response")
    if not isinstance(tool_response, dict):
        _passthrough()

    stdout = tool_response.get("stdout")
    stderr = tool_response.get("stderr")
    interrupted = tool_response.get("interrupted")
    is_image = tool_response.get("isImage")

    if (
        not isinstance(stdout, str)
        or not isinstance(stderr, str)
        or not isinstance(interrupted, bool)
        or not isinstance(is_image, bool)
    ):
        _passthrough()

    if is_image:
        _passthrough()

    if not stdout.strip():
        _passthrough()

    before_tokens = _estimate_tokens(stdout)
    if before_tokens < MIN_TOKENS_TO_COMPACT:
        _passthrough()

    if len(stdout) > MAX_BYTES_TO_COMPACT:
        _passthrough()

    try:
        # --record here logs chisel's own before/after, not this hook's final
        # size (the tail-guard below can still add lines back) — a one-process
        # tradeoff for avoiding a second interpreter cold start on every call.
        chisel_proc = subprocess.run(
            [
                sys.executable,
                str(ASHLAR_BIN),
                "chisel",
                "--max-lines",
                "500",
                "--record",
                "--label",
                "auto:posttooluse:bash",
            ],
            input=stdout,
            capture_output=True,
            text=True,
            timeout=CHISEL_TIMEOUT_SECONDS,
        )
    except Exception:
        _passthrough()

    if chisel_proc.returncode != 0:
        _passthrough()

    chiseled = chisel_proc.stdout
    if not chiseled:
        _passthrough()

    raw_lines = stdout.splitlines()
    tail_lines = raw_lines[-TAIL_GUARD_LINES:]

    chiseled_body = chiseled[:-1] if chiseled.endswith("\n") else chiseled
    chiseled_lines = chiseled_body.splitlines()
    kept_verbatim = set(chiseled_lines)
    # A tail line already present as a collapsed "line  (×N)" summary (see
    # bin/ashlar's _collapse_repeats) counts as kept — comparing the whole
    # block with endswith() misses this and re-appends it as a duplicate.
    missing_tail = [
        line
        for line in tail_lines
        if line not in kept_verbatim and not any(cl.startswith(line + "  (×") for cl in chiseled_lines)
    ]
    if missing_tail:
        marker = f"\n... [ashlar: preserving {len(missing_tail)} line(s) of original tail not otherwise present] ...\n"
        chiseled = chiseled_body + marker + "\n".join(missing_tail) + "\n"
    else:
        chiseled = chiseled_body + "\n"

    after_tokens = _estimate_tokens(chiseled)

    if after_tokens >= before_tokens:
        _passthrough()

    # Copy the full original tool_response and override only stdout, instead
    # of hand-building a 4-key literal. Any field beyond the 4 documented
    # ones (stdout/stderr/interrupted/isImage) survives untouched.
    updated_response = {**tool_response, "stdout": chiseled}

    try:
        rendered = json.dumps(
            {
                "hookSpecificOutput": {
                    "hookEventName": "PostToolUse",
                    "updatedToolOutput": updated_response,
                }
            }
        )
    except Exception:
        _passthrough()

    print(rendered)
    sys.stdout.flush()
    sys.exit(0)


if __name__ == "__main__":
    try:
        main()
    except SystemExit:
        raise
    except Exception:
        sys.exit(0)
