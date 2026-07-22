# file: robodog_terminal/run_tests.py
"""
Master test runner for the Robodog Terminal package.
Runs every suite as a subprocess, prints a summary, exits non-zero on any failure.

Run:  python robodog_terminal/run_tests.py            (from robodogcli/robodog)
      python robodog_terminal/run_tests.py --coverage (line coverage via coverage.py)
"""
from __future__ import annotations

import os
import subprocess
import sys
import time
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


def main() -> int:
    use_cov = "--coverage" in sys.argv
    results = []
    t0 = time.time()
    for suite in SUITES:
        path = HERE / suite
        if not path.exists():
            results.append((suite, None, 0.0))
            continue
        cmd = [sys.executable]
        if use_cov:
            cmd += ["-m", "coverage", "run", "--append",
                    f"--include={HERE}/*", "--omit=*/test_*,*/selftest.py,*/run_tests.py"]
        cmd.append(str(path))
        t = time.time()
        proc = subprocess.run(cmd, cwd=str(ROOT), capture_output=True, text=True)
        results.append((suite, proc.returncode == 0, time.time() - t))
        if proc.returncode != 0:
            print(f"--- {suite} FAILED ---")
            print((proc.stdout or "")[-2000:])
            print((proc.stderr or "")[-1000:])

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
    print(f"  {total - failed}/{total} suites passed in {time.time() - t0:.1f}s")

    if use_cov:
        subprocess.run([sys.executable, "-m", "coverage", "report",
                        "--show-missing", f"--include={HERE}/*",
                        "--omit=*/test_*,*/selftest.py,*/run_tests.py"],
                       cwd=str(ROOT))
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
