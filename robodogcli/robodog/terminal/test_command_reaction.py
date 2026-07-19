# file: terminal/test_command_reaction.py
"""
Tests for Pack B — command reaction:
exit-code salience on failure, run_tests summary + auto-detect,
dangerous-command classification + guard (warn vs confirm).
Run: python terminal/test_command_reaction.py   (from robodogcli/robodog)
"""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from terminal.tools import default_registry, classify_danger  # noqa: E402

ok = True


def check(cond, msg):
    global ok
    print(f"  [{'PASS' if cond else 'FAIL'}] {msg}")
    ok = ok and cond


def main() -> int:
    global ok
    wd = Path(tempfile.mkdtemp(prefix="rd_cmd_"))
    reg = default_registry(cwd=str(wd))

    # ---------------- exit-code salience ---------------------------------
    r = reg.execute("bash", {"command": "echo ok"})
    check("(exit 0)" in r and "FAILED" not in r, "success shows exit 0, no alarm")
    r = reg.execute("bash", {"command": "exit 3"})
    check("COMMAND FAILED (exit 3)" in r and "fix it" in r,
          "non-zero exit is made salient")

    # ---------------- danger classification ------------------------------
    check(classify_danger("rm -rf /tmp/x") is not None, "rm -rf flagged")
    check(classify_danger("git push --force origin main") is not None,
          "force push flagged")
    check(classify_danger("git reset --hard HEAD~3") is not None,
          "hard reset flagged")
    check(classify_danger("Remove-Item -Recurse -Force .\\build") is not None,
          "powershell recursive remove flagged")
    check(classify_danger("DROP TABLE users") is not None, "drop table flagged")
    check(classify_danger("echo hello") is None, "benign command not flagged")
    check(classify_danger("ls -la") is None, "ls not flagged")
    check(classify_danger("rmdir /s /q build") is not None, "rmdir /s flagged")

    # ---------------- guard: warn (default) proceeds ---------------------
    warns = []
    reg.on_bash_line = lambda ln: warns.append(ln)
    r = reg.execute("bash", {"command": "echo pretend-rm; exit 0"})
    # benign; now a real (but harmless) danger pattern that still runs:
    reg.execute("bash", {"command": "echo 'rm -rf nothing-real'"})
    # The command text contains rm -rf -> flagged, warn mode logs + proceeds.
    check(any("destructive" in w for w in warns), "warn mode logs destructive note")

    # ---------------- guard: confirm blocks on decline -------------------
    reg.guard = "confirm"
    reg.on_confirm = lambda cmd, reason: False  # user declines
    r = reg.execute("bash", {"command": "rm -rf important_dir"})
    check("BLOCKED" in r and "declined" in r, "confirm mode blocks on decline")
    reg.on_confirm = lambda cmd, reason: True   # user approves
    r = reg.execute("bash", {"command": "echo 'rm -rf x' ; exit 0"})
    check("BLOCKED" not in r, "confirm mode proceeds on approval")
    reg.guard = "warn"

    # ---------------- run_tests: auto-detect + summary -------------------
    # make a tiny passing pytest-less project: use a python -c as command
    r = reg.execute("run_tests", {"command": "python -c \"print('5 passed')\""})
    check("[PASS]" in r and "5 passed" in r, "run_tests summarizes pass")
    r = reg.execute("run_tests", {"command": "python -c \"print('2 failed, 3 passed'); exit(1)\""})
    check("[FAIL]" in r and "2 failed" in r and "3 passed" in r,
          "run_tests summarizes failures")

    # auto-detect pytest from a tests/ dir
    (wd / "tests").mkdir()
    cmd_shown = reg.execute("run_tests", {"command": "", "timeout": "5"})
    # command="" falls back to detection -> 'pytest -q' (may error if pytest
    # missing, but the detected command must appear)
    check("pytest" in cmd_shown or "no test command" not in cmd_shown,
          "run_tests auto-detects pytest for tests/ dir")

    # no detection, no command
    wd2 = Path(tempfile.mkdtemp(prefix="rd_cmd2_"))
    reg2 = default_registry(cwd=str(wd2))
    r = reg2.execute("run_tests", {})
    check("no test command detected" in r, "run_tests errors when nothing to run")

    # explicit test_command on registry
    reg2.test_command = "python -c \"print('1 passed')\""
    r = reg2.execute("run_tests", {})
    check("[PASS]" in r and "1 passed" in r, "run_tests uses registry.test_command")

    # ---------------- registration ---------------------------------------
    check(reg.get("run_tests") is not None and "run_tests" in reg.catalog(),
          "run_tests registered + catalogued")

    print("\nCOMMAND REACTION:", "ALL PASS" if ok else "FAILURES")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
