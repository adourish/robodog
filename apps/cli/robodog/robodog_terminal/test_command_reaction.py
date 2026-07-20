# file: robodog_terminal/test_command_reaction.py
"""
Tests for Pack B — command reaction:
exit-code salience on failure, run_tests summary + auto-detect,
dangerous-command classification + guard (warn vs confirm).
Run: python robodog_terminal/test_command_reaction.py   (from robodogcli/robodog)
"""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from robodog_terminal.tools import (  # noqa: E402
    default_registry, classify_danger, classify_network_mutation)

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

    # ---- read-only git must NOT trip the danger guard (false-positive) ----
    # From a real session: `--format` matched the disk-`format` pattern, so
    # every `git log --format=...` fired the destructive-command warning.
    for safe in ('git log --format="%H %ad %an %s" --date=short --all',
                 "git log --oneline -20", "git show 7b4a1a0 --stat",
                 "git diff main feature/llm-timeout",
                 "dotnet format --verify-no-changes"):
        check(classify_danger(safe) is None,
              f"read-only command not flagged: {safe[:35]}")
    # but a real disk format still is
    check(classify_danger("format C:") is not None, "disk 'format C:' still flagged")
    check(classify_danger("format /q d:") is not None, "'format /q' still flagged")

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

    # ---------------- OUTWARD-FACING network-write guard -----------------
    # Regression: an agent closed Jira tickets via run_script POSTing to the
    # /transitions endpoint with NO confirmation (run_script was unguarded).
    # Network writes must confirm by default and BLOCK when unconfirmable.
    JIRA_CLOSE = ('result = mod.run({"method": "POST", '
                  '"path": "/rest/api/2/issue/SERIO-38490/transitions", '
                  '"body": {"transition": {"id": "41"}}})')
    check(classify_network_mutation(JIRA_CLOSE) is not None,
          "classify_network_mutation flags a POST-to-transitions close")
    check(classify_network_mutation("requests.delete(url)") is not None,
          "DELETE flagged")
    check(classify_network_mutation('mod.run({"method": "GET", "path": "/x"})') is None,
          "a GET (read) is NOT flagged")
    check(classify_network_mutation("git log --oneline | head -5") is None,
          "an ordinary shell command is NOT flagged")

    # default net_guard = confirm; no confirmer (subagent/headless) -> BLOCK
    reg.net_guard = "confirm"; reg.on_confirm = None
    r = reg.execute("run_script", {"content": JIRA_CLOSE})
    check(r.startswith("BLOCKED") and "confirmation" in r,
          "run_script network write BLOCKS when it can't confirm (fail-safe)")
    # bash path is guarded too
    r = reg.execute("bash", {"command": "curl -X POST https://sde.fda.gov/close"})
    check(r.startswith("BLOCKED"), "bash network write blocked without a confirmer")
    # deny mode: always block, even with a confirmer present
    reg.net_guard = "deny"; reg.on_confirm = lambda c, why: True
    r = reg.execute("run_script", {"content": JIRA_CLOSE})
    check(r.startswith("BLOCKED") and "denied" in r, "deny mode blocks outright")
    # confirm + user declines -> blocked; user approves -> runs
    reg.net_guard = "confirm"; reg.on_confirm = lambda c, why: False
    r = reg.execute("run_script", {"content": JIRA_CLOSE})
    check(r.startswith("BLOCKED") and "declined" in r, "confirm+decline blocks write")
    reg.on_confirm = lambda c, why: True
    r = reg.execute("run_script", {"content": '# method="POST"\nprint("ran-ok")'})
    check("BLOCKED" not in r and "ran-ok" in r, "confirm+approve lets the write run")
    # allow mode: unattended writes permitted (opt-in)
    reg.net_guard = "allow"; reg.on_confirm = None
    r = reg.execute("run_script", {"content": 'print("net allow path")'})
    check("BLOCKED" not in r and "net allow" in r, "allow mode permits unattended")
    reg.net_guard = "confirm"; reg.on_confirm = lambda c, why: True

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
