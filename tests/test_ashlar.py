"""End-to-end tests: invoke bin/ashlar as a subprocess, same as a real user would."""

import importlib.machinery
import importlib.util
import json
import os
import subprocess
import sys
import threading
import time
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


def test_report_by_label_long_label_gets_visible_ellipsis(home):
    long_label = "x" * 40
    run(["record", "--before", "1000", "--after", "500", "--label", long_label], home)

    result = run(["report", "--by-label"], home)
    assert "x" * 28 + "..." in result.stdout
    assert long_label not in result.stdout


def test_report_since_excludes_old_entries(home):
    run(["record", "--before", "1000", "--after", "500", "--label", "recent"], home)

    ledger = home / ".ashlar" / "ledger.jsonl"
    entries = [json.loads(line) for line in ledger.read_text().splitlines()]
    entries[0]["ts"] -= 999_999  # push far into the past
    ledger.write_text("\n".join(json.dumps(e) for e in entries) + "\n")

    result = run(["report", "--since", "1h"], home)
    assert "No stones dressed yet" in result.stdout


def test_record_prunes_entries_older_than_max_ledger_age(home):
    run(["record", "--before", "1000", "--after", "500", "--label", "old"], home)

    ledger = home / ".ashlar" / "ledger.jsonl"
    entries = [json.loads(line) for line in ledger.read_text().splitlines()]
    entries[0]["ts"] -= 999_999  # push far into the past
    ledger.write_text("\n".join(json.dumps(e) for e in entries) + "\n")

    run(["record", "--before", "2000", "--after", "1000", "--label", "new", "--max-ledger-age", "1h"], home)

    remaining = [json.loads(line) for line in ledger.read_text().splitlines()]
    assert len(remaining) == 1
    assert remaining[0]["label"] == "new"


def test_record_max_ledger_age_zero_disables_pruning(home):
    run(["record", "--before", "1000", "--after", "500", "--label", "old"], home)

    ledger = home / ".ashlar" / "ledger.jsonl"
    entries = [json.loads(line) for line in ledger.read_text().splitlines()]
    entries[0]["ts"] -= 999_999  # push far into the past
    ledger.write_text("\n".join(json.dumps(e) for e in entries) + "\n")

    run(["record", "--before", "2000", "--after", "1000", "--label", "new", "--max-ledger-age", "0"], home)

    remaining = [json.loads(line) for line in ledger.read_text().splitlines()]
    assert len(remaining) == 2


def test_record_default_max_ledger_age_keeps_recent_entries(home):
    run(["record", "--before", "1000", "--after", "500", "--label", "recent"], home)
    run(["record", "--before", "2000", "--after", "1000", "--label", "also-recent"], home)

    ledger = home / ".ashlar" / "ledger.jsonl"
    remaining = [json.loads(line) for line in ledger.read_text().splitlines()]
    assert len(remaining) == 2


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
    lines = [f"line{i}" for i in range(50)]
    src.write_text("\n".join(lines) + "\n")
    run(["gavel", "--key", "file.py", "--file", str(src)], home)

    lines[25] = "line25-changed"
    src.write_text("\n".join(lines) + "\n")
    result = run(["gavel", "--key", "file.py", "--file", str(src)], home)

    assert "-line25" in result.stdout
    assert "+line25-changed" in result.stdout
    assert "diffed against cached version" in result.stderr


def test_gavel_near_total_rewrite_sends_full_content_not_diff(home, tmp_path):
    src = tmp_path / "file.py"
    src.write_text("\n".join(f"old line {i}" for i in range(50)) + "\n")
    run(["gavel", "--key", "file.py", "--file", str(src)], home)

    src.write_text("\n".join(f"totally different content {i}" for i in range(50)) + "\n")
    result = run(["gavel", "--key", "file.py", "--file", str(src)], home)

    assert result.stdout == src.read_text()
    assert "near-total rewrite" in result.stderr


def test_gavel_record_flag_writes_ledger(home, tmp_path):
    src = tmp_path / "file.py"
    src.write_text("line1\n")

    run(["gavel", "--key", "file.py", "--file", str(src), "--record"], home)

    ledger = home / ".ashlar" / "ledger.jsonl"
    assert ledger.exists()
    entry = json.loads(ledger.read_text().splitlines()[0])
    assert entry["label"] == "gavel:file.py"


def _load_ashlar_module():
    # bin/ashlar is a script, not a package — exec it as a module to unit-test
    # _locked() directly. A black-box subprocess race (many concurrent `record`
    # calls) doesn't reliably reproduce: process-spawn overhead dwarfs the
    # actual read-modify-write window, so it passes whether or not the lock
    # exists (verified: 60 concurrent calls, 3 trials, zero corruption even
    # with the lock removed). Only a deterministic in-process test has teeth.
    loader = importlib.machinery.SourceFileLoader("ashlar_under_test", str(ASHLAR))
    spec = importlib.util.spec_from_loader(loader.name, loader)
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module


def test_locked_serializes_concurrent_critical_sections(tmp_path):
    ashlar = _load_ashlar_module()
    lock_path = tmp_path / "test.lock"
    holder = threading.Event()
    violations = []

    def worker():
        with ashlar._locked(lock_path):
            if holder.is_set():
                violations.append(True)
            holder.set()
            time.sleep(0.02)
            holder.clear()

    threads = [threading.Thread(target=worker) for _ in range(10)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=5)

    assert not violations


def test_gavel_prunes_stale_cache_entries(home, tmp_path):
    stale_src = tmp_path / "stale.py"
    stale_src.write_text("old\n")
    run(["gavel", "--key", "stale.py", "--file", str(stale_src)], home)

    cache_dir = home / ".ashlar" / "gavel"
    stale_cache = next(cache_dir.glob("*.txt"))
    old_mtime = time.time() - 40 * 86400  # older than the 30d default
    os.utime(stale_cache, (old_mtime, old_mtime))

    fresh_src = tmp_path / "fresh.py"
    fresh_src.write_text("new\n")
    run(["gavel", "--key", "fresh.py", "--file", str(fresh_src)], home)

    assert not stale_cache.exists()
    assert len(list(cache_dir.glob("*.txt"))) == 1


def test_gavel_max_cache_age_zero_disables_pruning(home, tmp_path):
    stale_src = tmp_path / "stale.py"
    stale_src.write_text("old\n")
    run(["gavel", "--key", "stale.py", "--file", str(stale_src)], home)

    cache_dir = home / ".ashlar" / "gavel"
    stale_cache = next(cache_dir.glob("*.txt"))
    old_mtime = time.time() - 999 * 86400
    os.utime(stale_cache, (old_mtime, old_mtime))

    fresh_src = tmp_path / "fresh.py"
    fresh_src.write_text("new\n")
    run(["gavel", "--key", "fresh.py", "--file", str(fresh_src), "--max-cache-age", "0"], home)

    assert stale_cache.exists()


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


def test_chisel_default_behavior_unchanged_without_keep_pattern(home, tmp_path):
    lines = [f"debug line {i}" for i in range(20)]
    lines[10] = "ERROR: something broke"
    src = tmp_path / "log.txt"
    src.write_text("\n".join(lines))

    result = run(["chisel", "--file", str(src), "--context", "0"], home)
    assert "ERROR: something broke" in result.stdout
    assert "debug line 0" not in result.stdout


def test_chisel_drops_term_missing_from_builtin_keyword_list(home, tmp_path):
    lines = [f"debug line {i}" for i in range(20)]
    lines[5] = "ERROR: unrelated failure"  # gives the filter something to match,
    lines[10] = "process died: segfault at 0xdeadbeef"  # so this line isn't kept by the "nothing matched" fallback
    src = tmp_path / "log.txt"
    src.write_text("\n".join(lines))

    result = run(["chisel", "--file", str(src), "--context", "0"], home)
    # "segfault" isn't in the built-in LOAD_BEARING_RE keyword list, so without
    # --keep-pattern this line has nothing else to match and gets dropped.
    assert "segfault" not in result.stdout


def test_chisel_keep_pattern_adds_coverage_for_missed_term(home, tmp_path):
    lines = [f"debug line {i}" for i in range(20)]
    lines[10] = "process died: segfault at 0xdeadbeef"
    src = tmp_path / "log.txt"
    src.write_text("\n".join(lines))

    result = run(["chisel", "--file", str(src), "--context", "0", "--keep-pattern", "segfault"], home)
    assert "segfault at 0xdeadbeef" in result.stdout
    assert "debug line 0" not in result.stdout


def test_chisel_keep_pattern_is_additive_not_replacing_builtin_list(home, tmp_path):
    lines = [f"debug line {i}" for i in range(20)]
    lines[5] = "ERROR: something broke"
    lines[10] = "process died: segfault at 0xdeadbeef"
    src = tmp_path / "log.txt"
    src.write_text("\n".join(lines))

    result = run(["chisel", "--file", str(src), "--context", "0", "--keep-pattern", "segfault"], home)
    # Both the built-in match and the custom pattern's match survive.
    assert "ERROR: something broke" in result.stdout
    assert "segfault at 0xdeadbeef" in result.stdout


def test_chisel_keep_pattern_is_case_insensitive(home, tmp_path):
    src = tmp_path / "log.txt"
    src.write_text("debug line 0\nSEGFAULT in worker\ndebug line 2\n")

    result = run(["chisel", "--file", str(src), "--context", "0", "--keep-pattern", "segfault"], home)
    assert "SEGFAULT in worker" in result.stdout


def test_chisel_keep_pattern_repeatable_flag(home, tmp_path):
    lines = [f"debug line {i}" for i in range(20)]
    lines[3] = "process died: segfault at 0xdeadbeef"
    lines[15] = "kernel: oom-killer invoked"
    src = tmp_path / "log.txt"
    src.write_text("\n".join(lines))

    result = run(
        ["chisel", "--file", str(src), "--context", "0", "--keep-pattern", "segfault", "--keep-pattern", "oom-killer"],
        home,
    )
    assert "segfault at 0xdeadbeef" in result.stdout
    assert "oom-killer invoked" in result.stdout


def test_chisel_keep_pattern_invalid_regex_errors_cleanly(home, tmp_path):
    src = tmp_path / "log.txt"
    src.write_text("debug line 0\n")

    result = run(["chisel", "--file", str(src), "--keep-pattern", "("], home)
    assert result.returncode != 0
    assert "invalid --keep-pattern regex" in result.stderr
