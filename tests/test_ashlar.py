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


def test_chisel_truncates_oversized_plain_output(home, tmp_path):
    src = tmp_path / "dump.txt"
    src.write_text("\n".join(f"hit {i}" for i in range(500)))

    result = run(["chisel", "--file", str(src), "--max-lines", "20"], home)
    out_lines = result.stdout.splitlines()
    assert len(out_lines) == 22  # 20 kept + 1 elision marker + 1 recovery footer
    assert "lines elided" in result.stdout
    assert "full original at" in result.stdout


def _extract_recovery_path(stdout):
    return stdout.split("full original at ", 1)[1].split("⟩")[0]


def test_chisel_elision_keeps_full_original_recoverable(home, tmp_path):
    # Regression: a load-bearing line phrased in words the keyword regex doesn't
    # recognize can land inside the elided middle. Elision must never be a dead
    # end — the marker must point to a full copy that still has it.
    lines = [f"debug noise {i}" for i in range(500)]
    lines[250] = "Signature mismatch: build halted (code 77)"
    src = tmp_path / "dump.txt"
    src.write_text("\n".join(lines))

    result = run(["chisel", "--file", str(src), "--max-lines", "20"], home)
    assert "Signature mismatch" not in result.stdout  # confirms the regex gap is real
    assert "full original at" in result.stdout

    full_path = _extract_recovery_path(result.stdout)
    assert Path(full_path).exists()
    assert "Signature mismatch: build halted (code 77)" in Path(full_path).read_text()


def test_chisel_keyword_filter_alone_stays_recoverable(home, tmp_path):
    # Regression: recovery previously only triggered on --max-lines elision, so a
    # small input that never reaches elision but still gets keyword-filtered
    # (the common case — most chiseled output isn't 500+ lines) had no recovery
    # path at all. This is the bug the adversarial review actually found: the
    # fix for elision alone didn't cover the filter's own drops.
    lines = [f"debug line {i}" for i in range(50)]
    lines[10] = "warning: minor thing"
    lines[40] = "Tests: 42 passed, 3 broken"
    src = tmp_path / "log.txt"
    src.write_text("\n".join(lines))

    result = run(["chisel", "--file", str(src)], home)
    assert "Tests: 42 passed, 3 broken" not in result.stdout  # confirms the drop is real
    assert "full original at" in result.stdout

    full_path = _extract_recovery_path(result.stdout)
    assert Path(full_path).exists()
    assert "Tests: 42 passed, 3 broken" in Path(full_path).read_text()


def test_chisel_recovery_file_is_owner_only(home, tmp_path):
    # Recovery copies hold full, unredacted command output (secrets included) —
    # they must not be group/world-readable.
    lines = [f"debug line {i}" for i in range(50)]
    lines[10] = "warning: trigger a drop"
    src = tmp_path / "log.txt"
    src.write_text("\n".join(lines))

    result = run(["chisel", "--file", str(src)], home)
    full_path = _extract_recovery_path(result.stdout)
    mode = Path(full_path).stat().st_mode & 0o777
    assert mode == 0o600


def test_chisel_recovery_dir_is_pruned(home, tmp_path):
    chisel_dir = home / ".ashlar" / "chisel"
    chisel_dir.mkdir(parents=True)
    for i in range(205):
        (chisel_dir / f"stale-{i}.txt").write_text("old")

    lines = [f"debug line {i}" for i in range(50)]
    lines[10] = "warning: trigger a drop"
    src = tmp_path / "log.txt"
    src.write_text("\n".join(lines))
    run(["chisel", "--file", str(src)], home)

    assert len(list(chisel_dir.glob("*.txt"))) <= 200


def test_chisel_record_flag_writes_ledger(home, tmp_path):
    src = tmp_path / "log.txt"
    src.write_text("ERROR: boom\n")

    run(["chisel", "--file", str(src), "--record", "--label", "ci-log"], home)

    ledger = home / ".ashlar" / "ledger.jsonl"
    entry = json.loads(ledger.read_text().splitlines()[0])
    assert entry["label"] == "ci-log"
