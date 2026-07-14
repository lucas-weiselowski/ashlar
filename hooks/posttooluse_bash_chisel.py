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
before the hook process itself launches. MIN_TOKENS_TO_COMPACT below
only gates the second, more expensive subprocess (`ashlar chisel`).
The floor cost is one python3 cold start per Bash call, always paid.
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
TAIL_GUARD_LINES = 20  # final N lines of stdout are always preserved
# verbatim — exit-status-adjacent content
# usually lives there and chisel's regex
# doesn't guarantee it survives.

ASHLAR_BIN = Path(__file__).resolve().parent.parent / "bin" / "ashlar"
CHISEL_TIMEOUT_SECONDS = 5
RECORD_TIMEOUT_SECONDS = 3


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

    if not ASHLAR_BIN.exists():
        _passthrough()

    try:
        chisel_proc = subprocess.run(
            [sys.executable, str(ASHLAR_BIN), "chisel", "--max-lines", "500"],
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
    tail_text = "\n".join(tail_lines)

    chiseled_body = chiseled[:-1] if chiseled.endswith("\n") else chiseled
    if tail_lines and not chiseled_body.endswith(tail_text):
        marker = f"\n... [ashlar: preserving final {len(tail_lines)} lines of original output] ...\n"
        chiseled = chiseled_body + marker + tail_text + "\n"

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

    try:
        subprocess.run(
            [
                sys.executable,
                str(ASHLAR_BIN),
                "record",
                "--before",
                str(before_tokens),
                "--after",
                str(after_tokens),
                "--label",
                "auto:posttooluse:bash",
            ],
            capture_output=True,
            text=True,
            timeout=RECORD_TIMEOUT_SECONDS,
        )
    except Exception:
        pass

    sys.exit(0)


if __name__ == "__main__":
    try:
        main()
    except SystemExit:
        raise
    except Exception:
        sys.exit(0)
