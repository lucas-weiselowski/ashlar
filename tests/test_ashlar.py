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


def test_chisel_recovery_copy_preserves_raw_ansi_codes(home, tmp_path):
    # Regression: the recovery copy is meant to be the actual original output
    # (secret-adjacent, written 0600) -- it must not silently be the
    # ANSI-stripped version chisel used internally for matching/display.
    lines = [f"\x1b[90mdebug noise {i}\x1b[0m" for i in range(500)]
    lines[250] = "\x1b[31mSignature mismatch: build halted (code 77)\x1b[0m"
    src = tmp_path / "dump.txt"
    src.write_bytes("\n".join(lines).encode())

    result = run(["chisel", "--file", str(src), "--max-lines", "20"], home)
    full_path = _extract_recovery_path(result.stdout)
    assert "\x1b[" in Path(full_path).read_text()


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


def test_chisel_strips_ansi_escape_codes(home, tmp_path):
    src = tmp_path / "log.txt"
    src.write_bytes(b"\x1b[31mERROR\x1b[0m: something broke\n")

    result = run(["chisel", "--file", str(src)], home)
    assert "\x1b[" not in result.stdout
    assert "ERROR: something broke" in result.stdout


def test_chisel_ansi_stripping_lets_colorized_repeats_dedup(home, tmp_path):
    lines = ["\x1b[32msame line\x1b[0m" for _ in range(5)]
    src = tmp_path / "log.txt"
    src.write_bytes("\n".join(lines).encode())

    result = run(["chisel", "--file", str(src)], home)
    assert "(×5)" in result.stdout


def test_gavel_ansi_stripping_lets_colorized_output_dedup(home, tmp_path):
    src = tmp_path / "file.py"
    src.write_bytes(b"\x1b[32mline1\x1b[0m\nline2\n")
    run(["gavel", "--key", "file.py", "--file", str(src)], home)

    result = run(["gavel", "--key", "file.py", "--file", str(src)], home)
    assert "<unchanged since last read: file.py>" in result.stdout


def test_chisel_normalize_repeats_collapses_timestamped_lines(home, tmp_path):
    lines = [f"2026-07-14T12:00:{i:02d}Z heartbeat ok" for i in range(10)]
    src = tmp_path / "log.txt"
    src.write_text("\n".join(lines))

    result = run(["chisel", "--file", str(src), "--normalize-repeats"], home)
    assert "(×10)" in result.stdout


def test_chisel_without_normalize_repeats_keeps_timestamped_lines_distinct(home, tmp_path):
    lines = [f"2026-07-14T12:00:{i:02d}Z heartbeat ok" for i in range(10)]
    src = tmp_path / "log.txt"
    src.write_text("\n".join(lines))

    result = run(["chisel", "--file", str(src)], home)
    assert "(×10)" not in result.stdout


def test_chisel_max_line_chars_truncates_oversized_single_line(home, tmp_path):
    huge_line = "x" * 5000
    src = tmp_path / "log.txt"
    src.write_text(huge_line + "\n")

    result = run(["chisel", "--file", str(src), "--max-line-chars", "100"], home)
    assert "chars elided" in result.stdout
    assert len(result.stdout.splitlines()[0]) < 5000


def test_chisel_max_line_chars_keeps_keyword_past_truncation_point(home, tmp_path):
    huge_line = "x" * 3000 + " ValueError: boom"
    src = tmp_path / "log.txt"
    src.write_text(huge_line + "\n")

    result = run(["chisel", "--file", str(src), "--max-line-chars", "100"], home)
    assert "ValueError: boom" in result.stdout


def test_chisel_max_line_chars_default_leaves_normal_lines_untouched(home, tmp_path):
    src = tmp_path / "log.txt"
    src.write_text("a normal short line\n")

    result = run(["chisel", "--file", str(src)], home)
    assert result.stdout == "a normal short line\n"


def test_gavel_handles_non_utf8_input_without_crashing(home, tmp_path):
    src = tmp_path / "binary.dat"
    src.write_bytes(b"line one\n\xff\xfe garbage \nline two\n")

    result = run(["gavel", "--key", "binary.dat", "--file", str(src)], home)
    assert result.returncode == 0


def test_chisel_handles_non_utf8_input_without_crashing(home, tmp_path):
    src = tmp_path / "binary.dat"
    src.write_bytes(b"ERROR: \xff\xfe broke\n")

    result = run(["chisel", "--file", str(src)], home)
    assert result.returncode == 0
    assert "ERROR" in result.stdout


def test_report_skips_malformed_ledger_lines(home):
    run(["record", "--before", "1000", "--after", "500", "--label", "good"], home)

    ledger = home / ".ashlar" / "ledger.jsonl"
    with ledger.open("a") as f:
        f.write("not valid json\n")
        f.write('{"ts": 123}\n')  # missing before/after

    result = run(["report"], home)
    assert "1,000 tokens" in result.stdout


def test_parse_duration_rejects_empty_string(home):
    result = run(["report", "--since", ""], home)
    assert result.returncode != 0
    assert "invalid duration" in result.stderr
