# file: robodog_terminal/test_tools_scripts.py
"""
Tests for streaming bash + run_script in robodog_terminal/tools.py.

Covers: line-streaming via reg.on_bash_line, stderr capture, timeout with
process-tree kill, the background-param stub, run_script for python and
powershell, run_script timeout, and a regression run of robodog_terminal/selftest.py.

Run:  python robodog_terminal/test_tools_scripts.py    (from robodogcli/robodog/)
"""
from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

# Same import style as selftest.py: direct run adds parent so `terminal` imports.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from robodog_terminal.tools import default_registry  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent  # C:\projects\robodog\robodogcli\robodog

_ok = True


def check(cond, msg):
    global _ok
    status = "PASS" if cond else "FAIL"
    if not cond:
        _ok = False
    print(f"  [{status}] {msg}")


def fresh_registry():
    workdir = Path(tempfile.mkdtemp(prefix="robodog_toolstest_"))
    return default_registry(cwd=str(workdir))


def main() -> int:
    # --- 1. bash streaming: 3 lines, in order, via on_bash_line ----------
    print("=== 1. bash streaming ===")
    reg = fresh_registry()
    streamed = []
    reg.on_bash_line = streamed.append
    result = reg.execute("bash", {"command": "echo a; echo b; echo c"})
    check("(exit 0)" in result, "result contains (exit 0)")
    for ln in ("a", "b", "c"):
        check(ln in result, f"result contains line '{ln}'")
    got = [ln for ln in streamed if ln in ("a", "b", "c")]
    check(got == ["a", "b", "c"],
          f"on_bash_line collected all 3 lines in order (got {got})")

    # --- 2. bash stderr captured -----------------------------------------
    print("=== 2. bash stderr ===")
    reg = fresh_registry()
    result = reg.execute("bash", {"command": "Write-Error nope"})
    check("--- stderr ---" in result, "result contains stderr section")
    check("nope" in result, "stderr text 'nope' captured")

    # --- 3. bash timeout with tree kill ----------------------------------
    print("=== 3. bash timeout tree-kill ===")
    reg = fresh_registry()
    t0 = time.monotonic()
    result = reg.execute("bash", {"command": "Start-Sleep -Seconds 30",
                                  "timeout": "3"})
    elapsed = time.monotonic() - t0
    check("ERROR: command timed out after 3s (process tree killed)" in result,
          "timeout returns tree-kill ERROR message")
    check(elapsed < 8, f"timeout returned quickly ({elapsed:.1f}s < 8s)")

    # --- 3b. PowerShell && is auto-translated and RUNS -------------------
    # A model that chains with && on Windows used to loop on the parser error;
    # now the chain is rewritten to PowerShell and actually runs.
    if os.name == "nt":
        print("=== 3b. && auto-translate (live) ===")
        reg = fresh_registry()
        result = reg.execute("bash", {"command": "echo aaa && echo bbb"})
        check("aaa" in result and "bbb" in result and "(exit 0)" in result,
              "&& auto-translated -> both commands run, no error")
        ok_result = reg.execute("bash", {"command": "echo fine"})
        check("HINT" not in ok_result, "no hint on a clean command")

    # --- 3c. shell_syntax_hint() directly (host-PATH-independent) ---------
    # The real ELSA session looped on Unix pipes (`| head`, `| wc -l`) and
    # cmd.exe (`if not exist ... mkdir`). Test the classifier against the
    # ACTUAL error text those produce, without depending on whether Git's
    # head/wc happen to be on this machine's PATH.
    # --- 3d. powershell_translate: && / || auto-fix -----------------------
    # From a real session: the model looped on `cd X && git status` (invalid in
    # PowerShell) and even hallucinated success. We rewrite the chain so it runs.
    print("=== 3d. powershell_translate ===")
    from robodog_terminal.tools import powershell_translate as _pt
    if os.name == "nt":
        check(_pt("cd X && git status") == "cd X; if ($?) { git status }",
              "&& -> nested if ($?) (preserves conditional)")
        check(_pt("a && b && c") == "a; if ($?) { b; if ($?) { c } }",
              "&&-chain nests correctly")
        check(_pt("cd X || echo no") == "cd X; if (-not $?) { echo no }",
              "|| -> if (-not $?)")
        check(_pt('echo "a && b"') == 'echo "a && b"',
              "&& inside quotes is NOT translated")
        check(_pt("git status") == "git status", "no operator -> unchanged")
        check(_pt("a && b || c") == "a && b || c", "mixed &&/|| left alone")
        # end-to-end: a real && command actually runs now
        r_run = reg.execute("bash", {"command": "cd . && echo CHAINED_OK"})
        check("CHAINED_OK" in r_run and "(exit 0)" in r_run,
              "live: `cd . && echo` runs (translated) instead of erroring")

    print("=== 3c. shell_syntax_hint classifier ===")
    from robodog_terminal.tools import shell_syntax_hint as _hint
    if os.name == "nt":
        NR = "The term '{}' is not recognized as the name of a cmdlet"
        h = _hint("git log --oneline | head -20", NR.format("head"))
        check("HINT" in h and "Select-Object -First" in h, "head pipe -> hint")
        h = _hint("git log --oneline --graph --all | wc -l", NR.format("wc"))
        check("HINT" in h and "Measure-Object" in h, "wc pipe -> Measure-Object hint")
        h = _hint("cat x | tail -5", NR.format("tail"))
        check("HINT" in h and "-Last N" in h, "tail pipe -> -Last hint")
        h = _hint('if not exist "docs" mkdir "docs"', "")
        check("HINT" in h and "Test-Path" in h and "New-Item" in h,
              "cmd.exe 'if not exist' -> Test-Path/New-Item hint")
        h = _hint("echo a && echo b", "The token '&&' is not a valid statement separator")
        check("HINT" in h and "`;`" in h, "&& -> ; hint")
        check(_hint("git log --oneline -20", "") == "",
              "a clean command gets no hint")

    # --- 3e. python_import_hint: hyphenated skill dir -> importlib ---------
    # From a real ELSA session: the model looped 3× on
    #   from fdaskills.jira.jira_call.main import run
    #   ModuleNotFoundError: No module named 'fdaskills.jira.jira_call'
    # because the directory is `jira-call` (hyphen), not importable by name.
    print("=== 3e. python_import_hint (hyphen skill dir) ===")
    from robodog_terminal.tools import python_import_hint as _pih
    skill_reg = fresh_registry()
    root = Path(skill_reg.cwd)
    (root / "fdaskills" / "jira" / "jira-call").mkdir(parents=True)
    (root / "fdaskills" / "jira" / "jira-call" / "main.py").write_text(
        "def run():\n    return 1\n", encoding="utf-8")
    (root / "fdaskills" / "__init__.py").write_text("", encoding="utf-8")
    (root / "fdaskills" / "jira" / "__init__.py").write_text("", encoding="utf-8")
    stderr = ("Traceback (most recent call last):\n"
              "  File \"x.py\", line 3, in <module>\n"
              "    from fdaskills.jira.jira_call.main import run\n"
              "ModuleNotFoundError: No module named 'fdaskills.jira.jira_call'")
    h = _pih(stderr, str(root))
    check("jira-call" in h and "importlib" in h and "spec_from_file_location" in h,
          "hint names the hyphen dir and points at importlib")
    check("main.py" in h, "hint targets the skill's main.py")
    # no false positives
    check(_pih("ModuleNotFoundError: No module named 'totally_absent'", str(root)) == "",
          "no hint when the module maps to no directory")
    check(_pih("ZeroDivisionError: division by zero", str(root)) == "",
          "no hint on an unrelated traceback")
    # end-to-end: the hint rides along on the failed run_script result
    content = ("import sys\n"
               f"sys.path.insert(0, r'{root}')\n"
               "from fdaskills.jira.jira_call.main import run\n")
    res = skill_reg.execute("run_script", {"content": content})
    check("No module named 'fdaskills.jira.jira_call'" in res
          and "HINT" in res and "jira-call" in res,
          "run_script surfaces the importlib hint on the real failure")

    # --- 4. bash background param stub -----------------------------------
    print("=== 4. bash background stub ===")
    reg = fresh_registry()
    result = reg.execute("bash", {"command": "echo hi", "background": "true"})
    check(result == ("ERROR: background execution is not available yet — "
                     "run in foreground or split the work."),
          "background=true returns the stub ERROR string")

    # --- 5. run_script python --------------------------------------------
    print("=== 5. run_script python ===")
    reg = fresh_registry()
    streamed = []
    reg.on_bash_line = streamed.append
    result = reg.execute("run_script", {"content": 'print("from-script", 6*7)'})
    check("$ run_script(python)" in result, "shows $ run_script(python) header")
    check("(exit 0)" in result, "python script exited 0")
    check("from-script 42" in result, "result contains from-script 42")
    check(any("from-script 42" in ln for ln in streamed),
          "script output was streamed via on_bash_line")

    # --- 6. run_script powershell ----------------------------------------
    print("=== 6. run_script powershell ===")
    reg = fresh_registry()
    result = reg.execute("run_script", {"content": 'Write-Output "ps-works"',
                                        "interpreter": "powershell"})
    check("$ run_script(powershell)" in result, "shows $ run_script(powershell) header")
    check("ps-works" in result, "result contains ps-works")

    # --- 7. run_script timeout -------------------------------------------
    print("=== 7. run_script timeout ===")
    reg = fresh_registry()
    t0 = time.monotonic()
    result = reg.execute("run_script", {"content": "import time; time.sleep(30)",
                                        "timeout": "3"})
    elapsed = time.monotonic() - t0
    check("ERROR: command timed out after 3s (process tree killed)" in result,
          "run_script timeout returns tree-kill ERROR message")
    check(elapsed < 8, f"run_script timeout returned quickly ({elapsed:.1f}s < 8s)")

    # --- 8. regression: selftest still passes ----------------------------
    print("=== 8. selftest regression ===")
    proc = subprocess.run(
        [sys.executable, "robodog_terminal/selftest.py"],
        cwd=str(ROOT), capture_output=True, text=True, timeout=300,
    )
    check(proc.returncode == 0,
          f"robodog_terminal/selftest.py exits 0 (got {proc.returncode})")
    if proc.returncode != 0:
        print(proc.stdout[-2000:])
        print(proc.stderr[-2000:])

    print("\nRESULT:", "ALL PASS" if _ok else "FAILURES")
    return 0 if _ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
