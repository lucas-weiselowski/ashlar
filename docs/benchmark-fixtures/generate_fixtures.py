#!/usr/bin/env python3
"""Regenerate the 6 synthetic fixtures used in docs/benchmark-report-v2.html.

Deterministic (random.seed pinned per scenario) — re-running this produces
byte-identical output to what the v2 benchmark run measured. Requires
bin/ashlar's own source as the base for the 3 gavel scenarios; run from
anywhere, output always goes to the current directory.
"""

import random
import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
ASHLAR_SRC = REPO_ROOT / "bin" / "ashlar"


def gavel_fixtures():
    base = ASHLAR_SRC.read_text()
    Path("file_v1.py").write_text(base)

    # Scenario 2: single-line edit (version bump) — small, realistic repeat-read diff.
    Path("file_v2_singleline.py").write_text(base.replace('__version__ = "0.2.0"', '__version__ = "0.2.1"'))

    # Scenario 3: ~50% rewrite — second half of the file replaced with unrelated
    # placeholder lines, so a unified diff shares little context with the original.
    lines = base.splitlines(keepends=True)
    half = len(lines) // 2
    rewritten = lines[:half] + [
        f"# rewritten_line_{i}: placeholder_logic_{i} = compute_something_new({i}, mode='v2')\n"
        for i in range(half, len(lines))
    ]
    Path("file_v3_rewrite.py").write_text("".join(rewritten))


def verbose_testrun():
    random.seed(42)
    mods = ["auth", "parser", "cache", "router", "db", "utils", "handlers", "middleware"]
    lines = [
        f"tests/test_{random.choice(mods)}.py::test_case_{i} PASSED [{i / 480 * 100:5.1f}%]" for i in range(1, 480)
    ]
    lines.insert(250, "tests/test_auth.py::test_token_refresh_expired FAILED [ 52.1%]")
    lines += [
        "",
        "=================================== FAILURES ===================================",
        "_________________________ test_token_refresh_expired ___________________________",
        "",
        "    def test_token_refresh_expired():",
        "        token = issue_token(ttl=-1)",
        ">       assert refresh(token).ok",
        "E       AssertionError: assert False",
        "E        +  where False = <bound method Result.ok of Result(ok=False, err='expired')>.ok",
        "",
        "tests/test_auth.py:88: AssertionError",
        "=========================== 1 failed, 479 passed in 4.21s ===========================",
    ]
    Path("verbose_testrun.log").write_text("\n".join(lines) + "\n")


def grep_dump():
    random.seed(7)
    files = [
        "src/auth/session.py",
        "src/auth/token.py",
        "src/db/pool.py",
        "src/api/routes.py",
        "src/cache/redis_client.py",
        "src/utils/log.py",
        "src/handlers/webhook.py",
    ]
    # Deliberately no error/warning/exception-shaped terms — a generic grep dump
    # for a symbol name shouldn't accidentally trip chisel's keyword filter.
    terms = [
        "import requests",
        "def handle_request(",
        "log.debug(",
        "# TODO: cleanup",
        "return response",
        "class Handler:",
        "self.client = Client()",
        "if not token:",
        "config.get(",
        "session.commit()",
    ]
    lines = [f"{random.choice(files)}:{random.randint(1, 900)}:{random.choice(terms)}" for _ in range(750)]
    # Load-bearing but keyword-free comment, planted mid-list — the known
    # "semantic, not exact" chisel limitation (see benchmark report findings).
    lines.insert(
        375,
        "src/cache/redis_client.py:212:# NOTE: importing db.pool here risks a "
        "circular dependency with auth.session, do not add more cross-imports",
    )
    Path("grep_dump.log").write_text("\n".join(lines) + "\n")


def build_log():
    steps = [
        "Compiling module",
        "Linking object",
        "Running codegen for",
        "Bundling asset",
        "Optimizing chunk",
        "Resolving dependency",
        "Type-checking file",
    ]
    mods = [f"module_{i:03d}" for i in range(1, 700)]
    lines = [f"[{i:04d}] {steps[i % len(steps)]} {m}.ts ... ok ({(i * 7) % 400 + 10}ms)" for i, m in enumerate(mods)]
    lines += [
        "",
        "Traceback (most recent call last):",
        '  File "build_pipeline.py", line 214, in run_build',
        "    result = compile_module(entry)",
        '  File "build_pipeline.py", line 88, in compile_module',
        "    config = load_config(entry.config_path)",
        '  File "config_loader.py", line 41, in load_config',
        "    raise ConfigValidationError(f\"missing required key 'target' in {path}\")",
        # CamelCase exception name with no word boundary before "Error" — the
        # exact case LOAD_BEARING_RE's second alternative was added to catch.
        "ConfigValidationError: missing required key 'target' in modules/module_142/build.json",
        "Build FAILED after 700 modules",
    ]
    Path("build_log.log").write_text("\n".join(lines) + "\n")


def run_scenarios():
    """Feed each fixture through gavel/chisel and record to the ledger, matching
    the exact commands docs/benchmark-report-v2.html's Method section describes."""
    ashlar = str(ASHLAR_SRC)
    key = "bench-v2-file"

    # Reset the gavel cache key to file_v1 before each scenario so every repeat-read
    # comparison is against the same known baseline, not whatever ran before it.
    subprocess.run([ashlar, "gavel", "--key", key, "--file", "file_v1.py"], stdout=subprocess.DEVNULL)
    subprocess.run(
        [
            ashlar,
            "gavel",
            "--key",
            key,
            "--file",
            "file_v1.py",
            "--record",
            "--label",
            "bench:gavel-unchanged-repeat-v2",
        ]
    )

    subprocess.run([ashlar, "gavel", "--key", key, "--file", "file_v1.py"], stdout=subprocess.DEVNULL)
    subprocess.run(
        [
            ashlar,
            "gavel",
            "--key",
            key,
            "--file",
            "file_v2_singleline.py",
            "--record",
            "--label",
            "bench:gavel-small-diff-v2",
        ]
    )

    subprocess.run([ashlar, "gavel", "--key", key, "--file", "file_v1.py"], stdout=subprocess.DEVNULL)
    subprocess.run(
        [
            ashlar,
            "gavel",
            "--key",
            key,
            "--file",
            "file_v3_rewrite.py",
            "--record",
            "--label",
            "bench:gavel-large-diff-v2",
        ]
    )

    subprocess.run(
        [
            ashlar,
            "chisel",
            "--file",
            "verbose_testrun.log",
            "--max-lines",
            "80",
            "--record",
            "--label",
            "bench:chisel-verbose-testrun-v2",
        ]
    )
    subprocess.run(
        [
            ashlar,
            "chisel",
            "--file",
            "grep_dump.log",
            "--max-lines",
            "80",
            "--record",
            "--label",
            "bench:chisel-grep-dump-v2b",
        ]
    )
    subprocess.run(
        [
            ashlar,
            "chisel",
            "--file",
            "build_log.log",
            "--max-lines",
            "80",
            "--record",
            "--label",
            "bench:chisel-stacktrace-log-v2",
        ]
    )


if __name__ == "__main__":
    gavel_fixtures()
    verbose_testrun()
    grep_dump()
    build_log()
    run_scenarios()
    print("Fixtures written to the current directory. Read them back with:")
    print("  ashlar report --by-label | grep -E 'bench:.*-v2'")
