# file: robodog_terminal/run_tests.py
"""
Master test runner for the Robodog Terminal package.
Runs every suite as a subprocess IN PARALLEL, prints a summary, exits non-zero
on any failure.

Run:  python robodog_terminal/run_tests.py            (from robodogcli/robodog)
      python robodog_terminal/run_tests.py --coverage (line coverage via coverage.py)

Suites run concurrently (ThreadPoolExecutor — each thread just blocks on its
own subprocess, so this is about overlapping wall-clock wait time, not CPU).
Profiled: 25 suites took ~90-95s sequential on a 16-core box, dominated by
subprocess/PowerShell spin-up inside the slower suites; none of them touch
shared mutable state (the few that reference ~/.robodog are either read-only
assertions or timestamp-namespaced), so parallelizing is safe. Override the
worker count with ROBODOG_TEST_WORKERS if a box is more resource-constrained.
"""
from __future__ import annotations

import os
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent

SUITES = [
    "selftest.py",            # loop + tools + subagents E2E (echo backend)
    "test_toolcall.py",       # parser hardening
    "test_tools_scripts.py",  # streaming bash, tree-kill, run_script
    "test_background.py",     # BackgroundManager
    "test_sessions.py",       # session persistence
    "test_doctor.py",         # /doctor diagnostics
    "test_keepass_setup.py",  # /keepass vault bootstrap (temp dirs, never ~/.robodog)
    "test_tasklist.py",       # checklist + ask_user tools
    "test_edit_quality.py",   # post-edit verify, fuzzy match, multi_edit
    "test_command_reaction.py",  # exit-code salience, run_tests, danger guard
    "test_input.py",          # multiline paste, backslash-continuation
    "test_skills.py",         # custom commands / agents / skills discovery
    "test_hooks.py",          # settings.json permissions + Pre/Post/Stop hooks
    "test_certs.py",          # /cert TLS chain capture for private-CA gateways
    "test_sticky_input.py",   # opt-in sticky bottom input (watch_turn_sticky)
    "test_concurrency.py",    # bg concurrency + /btw side questions
    "test_subagent_stress.py",  # fan-out concurrency, failure isolation, bg storm, cancel-under-load
    "test_turnrunner.py",     # threaded turns: cancel/background/queue
    "test_rendering.py",      # banner, status, diff, markdown, clickable links, /open
    "test_llm_client.py",     # the gateway/OpenAI-compat wire + retry + factory
    "test_loop_checkpoint.py",# loop trim/nudge/breaker/cancel + checkpointer + tool safety
    "test_app.py",            # headless -p, CLI flags, interactive REPL drive, agents bg
    "test_integration.py",    # plan mode, @-mentions, bg-bash hook, wiring
    "test_regressions.py",    # one assertion per REAL live-session failure scenario
    "test_core.py",           # build_core(): no-UI embedding seam, safe defaults, gating
]

# Opt-in LIVE suites (network / real browser / real LLM). Off by default so
# the standard suite stays fast, deterministic, and keyless.
#   ROBODOG_PERF=1 python robodog_terminal/run_tests.py   (live LLM benchmark)
#   ROBODOG_LIVE=1 python robodog_terminal/run_tests.py   (live web/API/playwright E2E)
if os.environ.get("ROBODOG_PERF") == "1":
    SUITES.append("perf_fanout.py")   # live subagent fan-out concurrency benchmark
if os.environ.get("ROBODOG_LIVE") == "1":
    SUITES.append("test_live_web.py")  # parallel live-site fetch, polyglot squad, playwright


def _run_one(suite: str, use_cov: bool):
    """Run a single suite as a subprocess. Returns (suite, passed_or_None, dur,
    stdout, stderr). `passed` is None for a missing file (never attempted)."""
    path = HERE / suite
    if not path.exists():
        return suite, None, 0.0, "", ""
    cmd = [sys.executable]
    if use_cov:
        # --parallel-mode: each subprocess writes its own uniquely-suffixed
        # .coverage.* data file instead of one shared file — required for
        # concurrent writers (plain --append is NOT safe to race across
        # processes). Combined back into one file in main() after they finish.
        cmd += ["-m", "coverage", "run", "--parallel-mode",
                f"--include={HERE}/*", "--omit=*/test_*,*/selftest.py,*/run_tests.py"]
    cmd.append(str(path))
    t = time.time()
    proc = subprocess.run(cmd, cwd=str(ROOT), capture_output=True, text=True)
    return suite, proc.returncode == 0, time.time() - t, proc.stdout or "", proc.stderr or ""


def main() -> int:
    use_cov = "--coverage" in sys.argv
    try:
        workers = int(os.environ.get("ROBODOG_TEST_WORKERS", "8"))
    except ValueError:
        workers = 8
    workers = max(1, min(workers, len(SUITES)))

    t0 = time.time()
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(_run_one, suite, use_cov): i
                   for i, suite in enumerate(SUITES)}
        raw = [None] * len(SUITES)
        for fut in futures:
            raw[futures[fut]] = fut.result()

    # Print any failures in the suites' declared order (not completion order)
    # so output stays reproducible run-to-run.
    results = []
    for suite, passed, dur, out, err in raw:
        results.append((suite, passed, dur))
        if passed is False:
            print(f"--- {suite} FAILED ---")
            print(out[-2000:])
            print(err[-1000:])

    print("\n===== SUMMARY =====")
    failed = 0
    for suite, passed, dur in results:
        if passed is None:
            print(f"  [SKIP] {suite} (missing)")
        elif passed:
            print(f"  [PASS] {suite} ({dur:.1f}s)")
        else:
            print(f"  [FAIL] {suite} ({dur:.1f}s)")
            failed += 1
    total = sum(1 for _, p, _ in results if p is not None)
    print(f"  {total - failed}/{total} suites passed in {time.time() - t0:.1f}s "
          f"({workers} workers)")

    if use_cov:
        subprocess.run([sys.executable, "-m", "coverage", "combine"], cwd=str(ROOT))
        subprocess.run([sys.executable, "-m", "coverage", "report",
                        "--show-missing", f"--include={HERE}/*",
                        "--omit=*/test_*,*/selftest.py,*/run_tests.py"],
                       cwd=str(ROOT))
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
