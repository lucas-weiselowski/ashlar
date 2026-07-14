"""End-to-end tests: invoke bin/ashlar as a subprocess, same as a real user would."""

import json
import subprocess
import sys
from pathlib import Path

import pytest

ASHLAR = Path(__file__).resolve().parent.parent / "bin" / "ashlar"


def run(args, home, input=None):
    return subprocess.run(
        [sys.executable, str(ASHLAR), *args],
        input=input,
        capture_output=True,
        text=True,
        env={"PATH": "/usr/bin:/bin", "HOME": str(home)},
    )


@pytest.fixture
def home(tmp_path):
    return tmp_path


def test_version(home):
    result = run(["--version"], home)
    assert result.returncode == 0
    assert "ashlar" in result.stdout


def test_record_and_report(home):
    result = run(["record", "--before", "1000", "--after", "250", "--label", "test"], home)
    assert result.returncode == 0
    assert "1000 -> 250 tokens (75% cut)" in result.stdout

    result = run(["report"], home)
    assert "1,000 tokens" in result.stdout
    assert "250 tokens" in result.stdout
    assert "750 tokens (75%)" in result.stdout


def test_report_no_entries(home):
    result = run(["report"], home)
    assert "No stones dressed yet" in result.stdout


def test_record_before_file_after_file(home, tmp_path):
    before_file = tmp_path / "before.txt"
    after_file = tmp_path / "after.txt"
    before_file.write_text("x" * 400)  # 400 chars / 4 = 100 tokens
    after_file.write_text("x" * 40)  # 10 tokens

    result = run(["record", "--before-file", str(before_file), "--after-file", str(after_file)], home)
    assert "100 -> 10 tokens (90% cut)" in result.stdout


def test_record_requires_before_or_before_file(home):
    result = run(["record", "--after", "10"], home)
    assert result.returncode != 0
    assert "required" in result.stderr


def test_report_by_label(home):
    run(["record", "--before", "1000", "--after", "500", "--label", "alpha"], home)
    run(["record", "--before", "2000", "--after", "1000", "--label", "beta"], home)

    result = run(["report", "--by-label"], home)
    assert "alpha" in result.stdout
    assert "beta" in result.stdout


def test_report_since_excludes_old_entries(home):
    run(["record", "--before", "1000", "--after", "500", "--label", "recent"], home)

    ledger = home / ".ashlar" / "ledger.jsonl"
    entries = [json.loads(line) for line in ledger.read_text().splitlines()]
    entries[0]["ts"] -= 999_999  # push far into the past
    ledger.write_text("\n".join(json.dumps(e) for e in entries) + "\n")

    result = run(["report", "--since", "1h"], home)
    assert "No stones dressed yet" in result.stdout


def test_gavel_first_read_passes_content_through(home, tmp_path):
    src = tmp_path / "file.py"
    src.write_text("line1\nline2\n")

    result = run(["gavel", "--key", "file.py", "--file", str(src)], home)
    assert result.returncode == 0
    assert result.stdout == "line1\nline2\n"
    assert "first read of this key" in result.stderr


def test_gavel_unchanged_returns_marker(home, tmp_path):
    src = tmp_path / "file.py"
    src.write_text("line1\nline2\n")

    run(["gavel", "--key", "file.py", "--file", str(src)], home)
    result = run(["gavel", "--key", "file.py", "--file", str(src)], home)

    assert "<unchanged since last read: file.py>" in result.stdout
    assert "identical to cached version" in result.stderr


def test_gavel_diff_on_change(home, tmp_path):
    src = tmp_path / "file.py"
    src.write_text("line1\nline2\n")
    run(["gavel", "--key", "file.py", "--file", str(src)], home)

    src.write_text("line1\nline2-changed\n")
    result = run(["gavel", "--key", "file.py", "--file", str(src)], home)

    assert "-line2" in result.stdout
    assert "+line2-changed" in result.stdout
    assert "diffed against cached version" in result.stderr


def test_gavel_record_flag_writes_ledger(home, tmp_path):
    src = tmp_path / "file.py"
    src.write_text("line1\n")

    run(["gavel", "--key", "file.py", "--file", str(src), "--record"], home)

    ledger = home / ".ashlar" / "ledger.jsonl"
    assert ledger.exists()
    entry = json.loads(ledger.read_text().splitlines()[0])
    assert entry["label"] == "gavel:file.py"


def test_chisel_collapses_repeated_lines(home, tmp_path):
    src = tmp_path / "log.txt"
    src.write_text("\n".join(["same line"] * 10))

    result = run(["chisel", "--file", str(src)], home)
    assert "same line  (×10)" in result.stdout


def test_chisel_keeps_error_lines_with_context(home, tmp_path):
    lines = [f"debug line {i}" for i in range(20)]
    lines[10] = "ERROR: something broke"
    src = tmp_path / "log.txt"
    src.write_text("\n".join(lines))

    result = run(["chisel", "--file", str(src), "--context", "1"], home)
    assert "ERROR: something broke" in result.stdout
    assert "debug line 9" in result.stdout
    assert "debug line 11" in result.stdout
    assert "debug line 0" not in result.stdout


def test_chisel_keeps_camelcase_exception_lines(home, tmp_path):
    lines = [f"debug line {i}" for i in range(20)]
    lines[10] = 'raise ValueError("missing required field: customer_id")'
    lines[11] = "ValueError: missing required field: customer_id"
    src = tmp_path / "log.txt"
    src.write_text("\n".join(lines))

    result = run(["chisel", "--file", str(src), "--context", "0"], home)
    assert "ValueError" in result.stdout
    assert "missing required field: customer_id" in result.stdout


def test_chisel_truncates_oversized_plain_output(home, tmp_path):
    src = tmp_path / "dump.txt"
    src.write_text("\n".join(f"hit {i}" for i in range(500)))

    result = run(["chisel", "--file", str(src), "--max-lines", "20"], home)
    out_lines = result.stdout.splitlines()
    assert len(out_lines) == 21  # 20 kept + 1 elision marker
    assert "lines elided" in result.stdout


def test_chisel_record_flag_writes_ledger(home, tmp_path):
    src = tmp_path / "log.txt"
    src.write_text("ERROR: boom\n")

    run(["chisel", "--file", str(src), "--record", "--label", "ci-log"], home)

    ledger = home / ".ashlar" / "ledger.jsonl"
    entry = json.loads(ledger.read_text().splitlines()[0])
    assert entry["label"] == "ci-log"
