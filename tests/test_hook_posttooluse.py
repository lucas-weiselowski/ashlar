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


def test_compaction_spawns_only_one_subprocess(tmp_path):
    # Regression: chisel and record used to be two separate subprocess spawns
    # per compacted call. chisel's --record flag does both in one process now.
    big_stdout = "\n".join(f"line {i}" for i in range(2000))
    run_hook(bash_payload(big_stdout), tmp_path)

    ledger = tmp_path / ".ashlar" / "ledger.jsonl"
    assert len(ledger.read_text().splitlines()) == 1  # exactly one record, not two


def test_repeated_tail_lines_are_not_duplicated(tmp_path):
    # Regression: the tail-guard used to compare against RAW stdout lines, but
    # chisel collapses repeated lines into "line  (×N)" first, so the naive
    # endswith() check always failed on a repetitive tail and re-appended the
    # raw duplicates on top of the already-collapsed summary.
    lines = [f"setup line {i}" for i in range(300)] + ["retrying..."] * 25
    big_stdout = "\n".join(lines)
    result = run_hook(bash_payload(big_stdout), tmp_path)

    assert result.returncode == 0
    updated = json.loads(result.stdout)["hookSpecificOutput"]["updatedToolOutput"]
    assert updated["stdout"].count("retrying...") <= 2  # collapsed summary, not 25 raw repeats


def test_oversized_stdout_over_byte_cap_is_passthrough(tmp_path):
    huge_stdout = "x" * 3_000_000  # over MAX_BYTES_TO_COMPACT
    result = run_hook(bash_payload(huge_stdout), tmp_path)
    assert result.returncode == 0
    assert result.stdout == ""


def test_keyword_filtered_output_still_carries_recovery_pointer(tmp_path):
    # Regression: recovery previously only fired on --max-lines elision. Most
    # real compaction never reaches elision — it's filtered by keyword match
    # alone — and that path had zero recovery before this fix.
    lines = [f"noise {i}" for i in range(600)]
    lines[300] = "warning: something happened"
    big_stdout = "\n".join(lines)
    result = run_hook(bash_payload(big_stdout), tmp_path)

    assert result.returncode == 0
    updated = json.loads(result.stdout)["hookSpecificOutput"]["updatedToolOutput"]
    assert "full original at" in updated["stdout"]
