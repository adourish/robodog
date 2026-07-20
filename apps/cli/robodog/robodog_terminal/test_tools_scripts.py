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

    # --- 3g. Unix pipe filters | head/tail/wc auto-translate --------------
    # From a real ELSA session: the model looped 4x on `git log ... | head -20`
    # (head isn't a PowerShell cmdlet). Translate to Select-Object so it RUNS,
    # wrapping the producer in parens so it exits 0 (Select-Object -First else
    # kills git -> false non-zero exit).
    print("=== 3g. unix pipe filters (head/tail/wc) ===")
    from robodog_terminal.tools import (
        powershell_translate as _pt2, translate_unix_pipe_filters as _tf)
    if os.name == "nt":
        check(_tf("git log --oneline | head -20")
              == "(git log --oneline) | Select-Object -First 20",
              "| head -20 -> (upstream) | Select-Object -First 20")
        check(_tf("cat x | tail -5") == "(cat x) | Select-Object -Last 5",
              "| tail -5 -> Select-Object -Last 5")
        check(_tf("git log | head") == "(git log) | Select-Object -First 10",
              "bare | head defaults to First 10")
        check(_tf("git log | wc -l")
              == "(git log) | Measure-Object -Line | Select-Object -ExpandProperty Lines",
              "| wc -l -> Measure-Object -Line")
        check(_tf('echo "a | head -5"') == 'echo "a | head -5"',
              "pipe inside quotes is NOT translated")
        check(_tf("type f | head file.txt") == "type f | head file.txt",
              "`head <file>` (a real arg) is NOT a bare filter -> untouched")
        check(_tf("git status") == "git status", "no pipe -> unchanged")
        # combined with &&: parens stay inside the if-block, not across the split
        check(_pt2("cd X && git log --all | head -20")
              == "cd X; if ($?) { (git log --all) | Select-Object -First 20 }",
              "&& + | head: paren-wrapped filter nests inside if ($?)")
        # live: exit code is 0 (parens let git finish) AND output is limited.
        # Needs a git repo — ROOT sits under the robodog working tree.
        git_reg = default_registry(cwd=str(ROOT))
        r_head = git_reg.execute("bash", {"command": "git log --oneline | head -3"})
        check("(exit 0)" in r_head and "not recognized" not in r_head,
              "live: `git log | head -3` runs with exit 0 (no false failure)")
        r_chain = git_reg.execute(
            "bash", {"command": "cd . && git log --oneline | head -2"})
        check("(exit 0)" in r_chain and "COMMAND FAILED" not in r_chain,
              "live: `cd . && git log | head -2` runs clean end-to-end")

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
        # 2>/dev/null -> C:\dev\null (real session: find ... 2>/dev/null | grep)
        h = _hint('find C:\\p -type f -name "*.py" 2>/dev/null | grep idp',
                  "Could not find a part of the path 'C:\\dev\\null'")
        check("HINT" in h and "2>$null" in h, "2>/dev/null -> 2>$null hint")
        # Unix find with -type/-name -> Get-ChildItem
        h = _hint('find C:\\projects\\SERIO -type f -name "*.py"',
                  "find: command not found")
        check("HINT" in h and "Get-ChildItem" in h and "-Filter" in h,
              "unix find -type/-name -> Get-ChildItem hint")
        # no false positives: a mere mention without redirect/failure stays silent
        check(_hint('echo "logs go to /dev/null"', "") == "",
              "bare /dev/null mention (no redirect) gets no hint")
        check(_hint('git log --grep "find -name x"', "") == "",
              "successful command mentioning find gets no hint")

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

    # --- 3f. python_error_hint: json.loads() on an already-parsed value ---
    # From a real ELSA session: the jira skill's run() returns body as a parsed
    # dict, but the model looped 3x on `json.loads(result["body"])` ->
    #   TypeError: the JSON object must be str, bytes or bytearray, not dict
    print("=== 3f. python_error_hint (json.loads on a dict) ===")
    from robodog_terminal.tools import python_error_hint as _peh
    for _t in ("dict", "list"):
        _h = _peh(f"TypeError: the JSON object must be str, bytes or bytearray, not {_t}")
        check("ALREADY a parsed" in _h and _t in _h and "json.loads" in _h,
              f"json.loads-on-{_t} hint says the value is already parsed")
    check(_peh("ValueError: something else") == "", "no hint on an unrelated error")
    reg = fresh_registry()
    res = reg.execute("run_script", {"content": "import json\njson.loads({'a': 1})\n"})
    check("HINT" in res and "ALREADY a parsed dict" in res,
          "run_script surfaces the drop-json.loads hint")

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
