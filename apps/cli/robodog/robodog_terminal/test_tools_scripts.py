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

    # --- 2b. UTF-8 output isn't mojibake'd (em-dash / accents) -----------
    # Regression: a git commit message with `—` showed as `â€"` because the
    # subprocess was decoded with the Windows codepage, not UTF-8.
    if os.name == "nt":
        print("=== 2b. UTF-8 output ===")
        reg = fresh_registry()
        r = reg.execute("bash", {"command": 'Write-Output "handoff — café résumé"'})
        check("—" in r and "café" in r and "â€" not in r,
              "em-dash and accents survive bash output (no mojibake)")
        r = reg.execute("run_script", {"content": 'print("em—dash café")'})
        check("em—dash" in r and "café" in r,
              "run_script python unicode round-trips (PYTHONUTF8)")

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

    # --- 3a. idle note: quiet-but-alive commands get a heads-up, never a kill
    print("=== 3a. idle note (soft, non-killing) ===")
    os.environ["ROBODOG_IDLE_NOTE_SECONDS"] = "1"
    try:
        reg = fresh_registry()
        streamed = []
        reg.on_bash_line = streamed.append
        t0 = time.monotonic()
        result = reg.execute("bash", {"command": "Start-Sleep -Seconds 3; Write-Output done"})
        elapsed = time.monotonic() - t0
        notes = [ln for ln in streamed if "still running" in ln]
        check(len(notes) >= 1, f"idle note fired at least once (got {len(notes)})")
        check("(exit 0)" in result and "done" in result,
              "idle note never kills the process — it still finishes normally")
        check(elapsed < 8, f"finished promptly, not held up by the watchdog ({elapsed:.1f}s)")
    finally:
        del os.environ["ROBODOG_IDLE_NOTE_SECONDS"]

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
        # grep -> Select-String (real session: `... | grep "router"` failed)
        check(_tf('git log | grep "router"') == '(git log) | Select-String "router"',
              "| grep PATTERN -> Select-String PATTERN")
        check(_tf('ls | grep -i "Foo Bar"') == '(ls) | Select-String "Foo Bar"',
              "grep quoted pattern with spaces is preserved intact")
        check(_tf("cmd | grep -v error") == "(cmd) | Select-String -NotMatch error",
              "grep -v -> Select-String -NotMatch")
        # curl -> curl.exe (PowerShell aliases curl to Invoke-WebRequest)
        from robodog_terminal.tools import translate_windows_aliases as _twa
        check(_twa('curl -s -o x -w "%{http_code}" https://a') ==
              'curl.exe -s -o x -w "%{http_code}" https://a',
              "curl with real flags -> curl.exe")
        check(_twa("cd x && curl y") == "cd x && curl.exe y",
              "curl after && -> curl.exe")
        check(_twa("curl.exe already") == "curl.exe already", "curl.exe left alone")
        check(_twa("echo mycurl") == "echo mycurl", "non-command-position curl untouched")
        # standalone `grep PATTERN FILE` (code search) -> Select-String
        check(_twa('grep -n "max_retries" f.py') == 'Select-String -Pattern "max_retries" -Path f.py',
              "standalone grep PATTERN FILE -> Select-String -Path")
        check(_twa("grep -v error log.txt") == "Select-String -NotMatch -Pattern error -Path log.txt",
              "grep -v FILE -> -NotMatch")
        check(_twa("grep -rn foo src/")
              == "Get-ChildItem -Path src/ -Recurse -File -ErrorAction "
                 "SilentlyContinue | Select-String -Pattern foo",
              "recursive grep -r -> Get-ChildItem -Recurse | Select-String")
        check(_twa("cd C:\\p && grep -rn foo src/").endswith(
              "&& Get-ChildItem -Path src/ -Recurse -File -ErrorAction "
              "SilentlyContinue | Select-String -Pattern foo"),
              "grep after `cd X &&` is now translated (was: 'grep not recognized')")
        check(_twa("git log | grep x") == "git log | grep x",
              "the `| grep` pipe filter is NOT touched here (pipe path handles it)")
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
        # cmd.exe `dir /b`, `dir /s /b` -> Get-ChildItem (real session error)
        h = _hint("dir C:\\projects\\fda-serio\\fdaskills /b",
                  "Parameter name: path2 ... DirArgumentError")
        check("HINT" in h and "Get-ChildItem" in h and "-Name" in h,
              "dir /b -> Get-ChildItem -Name hint")
        h = _hint("dir C:\\p\\x /s /b", "DirArgumentError")
        check("HINT" in h and "-Recurse" in h, "dir /s /b -> -Recurse -Name hint")
        check(_hint("git diff HEAD~1", "") == "",
              "a path with a slash flag-like token but no `dir` gets no dir hint")
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
    # src-layout: `No module named 'src'` while a src/ dir exists -> PYTHONPATH hint
    (root / "src").mkdir(exist_ok=True)
    h = _pih("ModuleNotFoundError: No module named 'src'", str(root))
    check("PYTHONPATH" in h and "isn't on Python's path" in h,
          "src-layout miss -> PYTHONPATH / pip install -e hint")
    check(_pih("ModuleNotFoundError: No module named 'src.router'", str(root)) == "",
          "multi-segment miss (submodule) does NOT mis-fire the PYTHONPATH hint")
    # not-installed dev tool (model flipped python vs py -> pytest-less interpreter)
    from robodog_terminal.tools import python_error_hint as _peh2
    h = _peh2("C:\\Python312\\python.exe: No module named pytest")
    check("isn't installed" in h and "pytest" in h and "same interpreter" in h.lower(),
          "not-installed dev tool -> install + same-interpreter hint")
    check(_peh2("No module named 'some_random_pkg'") == "",
          "an unknown module is not treated as a known dev tool")
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

    # --- 3h. npm error hints (non-Node repo) -----------------------------
    # From a real session: the model ran `npm test` in a .NET repo (no
    # package.json) and looped on "Missing script: test".
    print("=== 3h. npm_error_hint ===")
    from robodog_terminal.tools import npm_error_hint as _npm
    check("no 'test' script" in _npm('npm error Missing script: "test"'),
          "missing-script -> names the script + 'not a Node project?'")
    check("no package.json here" in _npm("npm error code ENOENT open package.json"),
          "no package.json -> not-a-Node-project hint")
    check(_npm("some unrelated build failure") == "", "no hint on an unrelated error")

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

    # --- 7a. persistent shell session (Windows bash-tool speedup) ---------
    if os.name == "nt":
        print("=== 7a. persistent shell session ===")
        from robodog_terminal.tools import _PersistentPowerShell

        reg = fresh_registry()
        t0 = time.monotonic()
        r1 = reg.execute("bash", {"command": "Write-Output first-call"})
        first_call_dur = time.monotonic() - t0
        check("first-call" in r1, "first bash call works and starts the session")
        check(reg._shell is not None and reg._shell._alive(),  # noqa: SLF001
              "a persistent shell session is now attached to the registry")

        t0 = time.monotonic()
        r2 = reg.execute("bash", {"command": "Write-Output second-call"})
        second_call_dur = time.monotonic() - t0
        check("second-call" in r2, "second bash call reuses the session")
        check(second_call_dur < first_call_dur,
              f"reused call is faster than the cold-start one "
              f"({second_call_dur:.2f}s < {first_call_dur:.2f}s)")

        # State persists across calls: a bare `cd` sticks (like a real terminal),
        # unlike the old one-shot-per-call behavior.
        other_dir = str(Path(tempfile.mkdtemp(prefix="rd_shell_cd_")))
        reg.execute("bash", {"command": f"Set-Location -LiteralPath '{other_dir}'"})
        r3 = reg.execute("bash", {"command": "(Get-Location).Path"})
        check(other_dir.rstrip("\\/").lower() in r3.replace("\\\\", "\\").lower(),
              f"a bare cd/Set-Location persists to the NEXT call ({r3.strip()[:80]!r})")

        # A `cwd` tool-param override is scoped to just that one call — it must
        # NOT leak into the following call the way a bare `cd` does.
        reg2 = fresh_registry()
        scoped_dir = str(Path(tempfile.mkdtemp(prefix="rd_shell_scoped_")))
        r_scoped = reg2.execute("bash", {"command": "(Get-Location).Path", "cwd": scoped_dir})
        check(scoped_dir.rstrip("\\/").lower() in r_scoped.replace("\\\\", "\\").lower(),
              "a cwd override applies to its own call")
        r_after = reg2.execute("bash", {"command": "(Get-Location).Path"})
        check(scoped_dir.lower() not in r_after.lower(),
              "…but does NOT leak into the next call (unlike a bare cd)")

        # `exit N` — PowerShell (unlike bash) terminates the WHOLE session on a
        # top-level exit, not just the current command. Must be reported as
        # that exit code, not misclassified as a hang/timeout, and the session
        # must recover cleanly on the next call.
        reg3 = fresh_registry()
        r_exit = reg3.execute("bash", {"command": "exit 3"})
        check("COMMAND FAILED (exit 3)" in r_exit,
              "a session-terminating `exit N` reports the real exit code, not a timeout")
        r_recover = reg3.execute("bash", {"command": "Write-Output back-again"})
        check("back-again" in r_recover, "the session transparently restarts on the next call")

        # Feature flag: ROBODOG_PERSISTENT_SHELL=0 falls back to one-shot.
        os.environ["ROBODOG_PERSISTENT_SHELL"] = "0"
        try:
            reg4 = fresh_registry()
            r_off = reg4.execute("bash", {"command": "Write-Output still-works"})
            check("still-works" in r_off and reg4._shell is None,  # noqa: SLF001
                  "ROBODOG_PERSISTENT_SHELL=0 disables the persistent session entirely")
        finally:
            del os.environ["ROBODOG_PERSISTENT_SHELL"]

        # Direct unit test of the class: stderr + exit code together.
        sh = _PersistentPowerShell()
        try:
            rc, out, err, timed_out = sh.run(
                "Write-Output line1; Write-Error boom", None, str(Path.cwd()), 10)
            check(rc == 1 and any("boom" in e for e in err) and out == ["line1"]
                  and not timed_out,
                  f"class-level: mixed stdout/stderr + failing exit code "
                  f"(rc={rc}, out={out}, err has boom={any('boom' in e for e in err)})")
        finally:
            sh.kill()

        # REGRESSION (hit in production): a command whose text contains a
        # literal embedded newline — e.g. `git commit -m "subject\n\nbody"`,
        # a completely ordinary multi-line commit message — used to hang the
        # WHOLE session for the full timeout. PowerShell's parser, upon
        # seeing the opening quote, kept scanning subsequent lines for the
        # closing one; since our own rc-capture/sentinel lines were written
        # right after on the same stdin stream, they got silently swallowed
        # as more of that unterminated string instead of running as separate
        # statements. Fixed by base64-encoding the whole command (like
        # PowerShell's own -EncodedCommand) so embedded newlines/quotes can
        # never be ambiguous on the wire.
        print("=== 7b. persistent shell: embedded-newline command (regression) ===")
        reg5 = fresh_registry()
        # An ordinary multi-line commit-message-shaped command — a literal
        # newline INSIDE a quoted string, exactly what a real
        # `git commit -m "subject\n\nbody"` looks like on the wire.
        multiline_cmd = 'Write-Output "subject\n\nbody line"'
        t0 = time.monotonic()
        r5 = reg5.execute("bash", {"command": multiline_cmd, "timeout": "15"})
        elapsed5 = time.monotonic() - t0
        check(elapsed5 < 5,
              f"a command with an embedded literal newline no longer hangs "
              f"the session ({elapsed5:.1f}s, was a 15s timeout before the fix)")
        check("(exit 0)" in r5 and "subject" in r5 and "body line" in r5,
              "…and its multi-line output is captured correctly")
        # The session must still be alive and usable for the NEXT call too —
        # confirms the fix didn't just avoid the hang by killing the session.
        r5b = reg5.execute("bash", {"command": "Write-Output still-alive"})
        check("still-alive" in r5b, "the session survives an embedded-newline command intact")

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
