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
    result = run(["chisel", "--file", str(src)], home)

    assert len(list(chisel_dir.glob("*.txt"))) <= 200
    # Pruning must never evict the file this same run just pointed the
    # recovery marker at — only mtime-ordering bugs would let that slip past
    # a bare count check.
    full_path = _extract_recovery_path(result.stdout)
    assert Path(full_path).exists()


def test_chisel_record_flag_writes_ledger(home, tmp_path):
    src = tmp_path / "log.txt"
    src.write_text("ERROR: boom\n")

    run(["chisel", "--file", str(src), "--record", "--label", "ci-log"], home)

    ledger = home / ".ashlar" / "ledger.jsonl"
    entry = json.loads(ledger.read_text().splitlines()[0])
    assert entry["label"] == "ci-log"


def test_chisel_keeps_camelcase_exception_lines(home, tmp_path):
    # Regression: a bare \b(exception|error)\b never matches inside a glued
    # identifier like NullPointerException — no word boundary exists between
    # lowercase and uppercase letters. That silently dropped real stack traces.
    lines = [f"debug line {i}" for i in range(20)]
    lines[10] = "Caused by: java.lang.NullPointerException"
    src = tmp_path / "log.txt"
    src.write_text("\n".join(lines))

    result = run(["chisel", "--file", str(src), "--context", "1"], home)
    assert "NullPointerException" in result.stdout


def test_chisel_keeps_plural_and_gerund_forms(home, tmp_path):
    # Regression: \bwarn(?:ing)?\b misses "warnings" (trailing 's' blocks the
    # boundary), \bfail(?:ed|ure)?\b misses "failing"/"fails".
    lines = [f"debug line {i}" for i in range(20)]
    lines[5] = "3 warnings generated"
    lines[15] = "test suite is failing"
    src = tmp_path / "log.txt"
    src.write_text("\n".join(lines))

    result = run(["chisel", "--file", str(src), "--context", "0"], home)
    assert "3 warnings generated" in result.stdout
    assert "test suite is failing" in result.stdout


def test_chisel_strips_ansi_escape_codes(home, tmp_path):
    src = tmp_path / "log.txt"
    src.write_text("\x1b[31mERROR: boom\x1b[0m\n")

    result = run(["chisel", "--file", str(src)], home)
    assert result.stdout == "ERROR: boom\n"
    assert "\x1b[" not in result.stdout


def test_chisel_finds_keyword_buried_in_oversized_line(home, tmp_path):
    # Regression: if keyword matching ran on already-truncated lines, a
    # load-bearing word sitting in the elided middle of a huge line (the
    # exact case --max-line-chars targets) would never even qualify that
    # line for inclusion — it'd be excluded outright, same as any other
    # non-matching line, with no trace in the output. A distractor match
    # elsewhere (line 5) keeps `keep` non-empty-but-selective so the huge
    # line's fate actually depends on its own match, not the empty-keep
    # fallback that keeps everything.
    padding = "x" * 3000
    lines = [f"debug line {i}" for i in range(50)]
    lines[5] = "ERROR: canary"
    lines[30] = f"{padding} FATAL: buried in the middle {padding}"
    src = tmp_path / "blob.log"
    src.write_text("\n".join(lines))

    result = run(["chisel", "--file", str(src), "--max-line-chars", "100", "--context", "0"], home)
    assert "ERROR: canary" in result.stdout
    # The buried-keyword line was selected (self-matched pre-truncation) and
    # then truncated for display — its presence, truncated, is the signal.
    assert "chars elided" in result.stdout
    # Neighbors of both matches are absent — proves this is selective
    # inclusion (matching worked), not the empty-keep fallback that would
    # keep every line in the file regardless.
    assert "debug line 4" not in result.stdout
    assert "debug line 29" not in result.stdout


def test_chisel_truncates_oversized_single_line(home, tmp_path):
    # Regression: a single huge line (minified JSON, base64 blob) has no
    # newlines, so line-based collapsing/--max-lines truncation never engage —
    # it sailed through completely uncompacted.
    src = tmp_path / "blob.json"
    src.write_text("x" * 5000)

    result = run(["chisel", "--file", str(src), "--max-line-chars", "100"], home)
    assert "chars elided" in result.stdout
    assert len(result.stdout) < 1000
    assert "full original at" in result.stdout


def test_chisel_normalize_repeats_collapses_timestamped_duplicates(home, tmp_path):
    lines = [f"2024-01-01T00:00:{i:02d}Z heartbeat OK" for i in range(10)]
    src = tmp_path / "log.txt"
    src.write_text("\n".join(lines))

    result = run(["chisel", "--file", str(src), "--normalize-repeats"], home)
    assert "(×10)" in result.stdout

    # Without the flag, none of these are byte-identical, so nothing collapses.
    result_default = run(["chisel", "--file", str(src)], home)
    assert "(×10)" not in result_default.stdout


def test_chisel_rejects_invalid_max_lines(home, tmp_path):
    src = tmp_path / "log.txt"
    src.write_text("line\n")

    result = run(["chisel", "--file", str(src), "--max-lines", "0"], home)
    assert result.returncode != 0


def test_chisel_rejects_negative_context(home, tmp_path):
    src = tmp_path / "log.txt"
    src.write_text("line\n")

    result = run(["chisel", "--file", str(src), "--context", "-1"], home)
    assert result.returncode != 0


def test_chisel_handles_invalid_utf8_without_crashing(home, tmp_path):
    src = tmp_path / "binary.log"
    src.write_bytes(b"before\xff\xfeafter ERROR: boom\n")

    result = run(["chisel", "--file", str(src)], home)
    assert result.returncode == 0
    assert "ERROR: boom" in result.stdout


def test_gavel_strips_ansi_escape_codes(home, tmp_path):
    src = tmp_path / "colored.log"
    src.write_text("\x1b[31mERROR: boom\x1b[0m\n")
    run(["gavel", "--key", "colored.log", "--file", str(src)], home)

    # A second read that differs only by color codes must read as unchanged —
    # ANSI stripping happens before both the cache write and the compare.
    src.write_text("\x1b[32mERROR: boom\x1b[0m\n")
    result = run(["gavel", "--key", "colored.log", "--file", str(src)], home)

    assert "<unchanged since last read: colored.log>" in result.stdout
    assert "identical to cached version" in result.stderr


def test_gavel_diff_fallback_when_diff_not_smaller(home, tmp_path):
    # Regression: near-total rewrites (e.g. a timestamp on every line) can
    # make the unified diff bigger than the source — defeats the point.
    src = tmp_path / "log.txt"
    old_lines = [f"2024-01-01T00:00:{i:02d}Z line {i}" for i in range(200)]
    src.write_text("\n".join(old_lines))
    run(["gavel", "--key", "log.txt", "--file", str(src)], home)

    new_lines = [f"2024-01-01T00:01:{i:02d}Z line {i}" for i in range(200)]
    src.write_text("\n".join(new_lines))
    result = run(["gavel", "--key", "log.txt", "--file", str(src)], home)

    assert "diff not smaller than source" in result.stderr
    assert result.stdout == "\n".join(new_lines)


def test_gavel_small_diff_still_shown_despite_overhead(home, tmp_path):
    # The fallback above must not swallow the documented "tiny input" case —
    # SKILL.md explicitly says small diffs can cost more than the source and
    # that's expected, reported honestly, not papered over.
    src = tmp_path / "file.py"
    src.write_text("line1\nline2\n")
    run(["gavel", "--key", "file.py", "--file", str(src)], home)

    src.write_text("line1\nline2-changed\n")
    result = run(["gavel", "--key", "file.py", "--file", str(src)], home)
    assert "-line2" in result.stdout
    assert "+line2-changed" in result.stdout


def test_gavel_cache_key_uses_full_digest(home, tmp_path):
    src = tmp_path / "file.py"
    src.write_text("line1\n")
    run(["gavel", "--key", "file.py", "--file", str(src)], home)

    cache_files = list((home / ".ashlar" / "gavel").glob("*.txt"))
    assert len(cache_files) == 1
    assert len(cache_files[0].stem) == 64  # full sha256 hex digest, not truncated


def test_report_skips_corrupted_ledger_line(home, tmp_path):
    run(["record", "--before", "1000", "--after", "500", "--label", "good"], home)

    ledger = home / ".ashlar" / "ledger.jsonl"
    with ledger.open("a") as f:
        f.write("{not valid json\n")
        f.write(json.dumps({"ts": 123}) + "\n")  # missing before/after

    result = run(["report"], home)
    assert result.returncode == 0
    assert "1,000 tokens" in result.stdout


def test_report_since_rejects_empty_duration(home):
    result = run(["report", "--since", ""], home)
    assert result.returncode != 0
