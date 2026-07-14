"""Tests for hooks/posttooluse_bash_chisel.py — driven exactly like Claude Code
would: a JSON PostToolUse payload on stdin, JSON (or nothing) on stdout."""

import json
import subprocess
import sys
from pathlib import Path

HOOK = Path(__file__).resolve().parent.parent / "hooks" / "posttooluse_bash_chisel.py"


def run_hook(payload_text, home):
    return subprocess.run(
        [sys.executable, str(HOOK)],
        input=payload_text,
        capture_output=True,
        text=True,
        env={"PATH": "/usr/bin:/bin", "HOME": str(home)},
        timeout=15,
    )


def bash_payload(stdout, stderr="", interrupted=False, is_image=False, tool_name="Bash"):
    return json.dumps(
        {
            "tool_name": tool_name,
            "tool_input": {"command": "whatever"},
            "tool_response": {
                "stdout": stdout,
                "stderr": stderr,
                "interrupted": interrupted,
                "isImage": is_image,
            },
            "tool_use_id": "toolu_test",
            "duration_ms": 1,
        }
    )


def test_large_output_gets_compacted_with_valid_shape(tmp_path):
    big_stdout = "\n".join(f"line {i}" for i in range(2000))  # well over threshold
    result = run_hook(bash_payload(big_stdout, stderr="some stderr"), tmp_path)

    assert result.returncode == 0
    out = json.loads(result.stdout)
    updated = out["hookSpecificOutput"]["updatedToolOutput"]
    assert set(updated.keys()) >= {"stdout", "stderr", "interrupted", "isImage"}
    assert len(updated["stdout"]) < len(big_stdout)
    # stderr must never be touched by the hook
    assert updated["stderr"] == "some stderr"
    assert updated["interrupted"] is False
    assert updated["isImage"] is False


def test_tail_of_stdout_is_preserved(tmp_path):
    lines = [f"noise {i}" for i in range(1000)] + ["EXIT CODE MARKER 137"]
    big_stdout = "\n".join(lines)
    result = run_hook(bash_payload(big_stdout), tmp_path)

    assert result.returncode == 0
    updated = json.loads(result.stdout)["hookSpecificOutput"]["updatedToolOutput"]
    assert "EXIT CODE MARKER 137" in updated["stdout"]


def test_small_output_is_untouched_passthrough(tmp_path):
    result = run_hook(bash_payload("just a few lines\nof output\n"), tmp_path)
    assert result.returncode == 0
    assert result.stdout == ""  # pure passthrough: no stdout at all


def test_non_bash_tool_is_passthrough(tmp_path):
    payload = bash_payload("x" * 5000, tool_name="Read")
    result = run_hook(payload, tmp_path)
    assert result.returncode == 0
    assert result.stdout == ""


def test_malformed_json_fails_safe(tmp_path):
    result = run_hook("{not valid json", tmp_path)
    assert result.returncode == 0
    assert result.stdout == ""


def test_empty_stdin_fails_safe(tmp_path):
    result = run_hook("", tmp_path)
    assert result.returncode == 0
    assert result.stdout == ""


def test_missing_tool_response_fields_fail_safe(tmp_path):
    payload = json.dumps({"tool_name": "Bash", "tool_response": {"stdout": "x" * 5000}})
    result = run_hook(payload, tmp_path)
    assert result.returncode == 0
    assert result.stdout == ""


def test_image_output_is_passthrough(tmp_path):
    result = run_hook(bash_payload("x" * 5000, is_image=True), tmp_path)
    assert result.returncode == 0
    assert result.stdout == ""


def test_compaction_writes_ledger_entry(tmp_path):
    big_stdout = "\n".join(f"line {i}" for i in range(2000))
    run_hook(bash_payload(big_stdout), tmp_path)

    ledger = tmp_path / ".ashlar" / "ledger.jsonl"
    assert ledger.exists()
    entry = json.loads(ledger.read_text().splitlines()[-1])
    assert entry["label"] == "auto:posttooluse:bash"
    assert entry["after"] < entry["before"]
