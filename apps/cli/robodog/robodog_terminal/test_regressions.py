# file: robodog_terminal/test_regressions.py
"""
Regression suite — one assertion per REAL failure scenario observed in live
ELSA / OpenRouter sessions (0.3.16 -> present). Each check is tagged with the
symptom the user hit, so a future change that reintroduces the failure trips a
named test. Pure-function level where possible (fast, deterministic); a few use a
real registry against temp files.

These are deliberately DUPLICATED at a high level with the deeper per-module
suites — this file is the single auditable "these must never come back" list.

Run:  python robodog_terminal/test_regressions.py   (from apps/cli/robodog)
"""
from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from robodog_terminal import tools as T                       # noqa: E402
from robodog_terminal.tools import default_registry           # noqa: E402
from robodog_terminal.toolcall import parse_tool_calls        # noqa: E402

ok = True


def check(cond, msg):
    global ok
    print(f"  [{'PASS' if cond else 'FAIL'}] {msg}")
    ok = ok and bool(cond)


def _reg(files=None):
    wd = Path(tempfile.mkdtemp(prefix="rd_regr_"))
    for rel, content in (files or {}).items():
        p = wd / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")
    return default_registry(cwd=str(wd)), wd


def main() -> int:
    win = os.name == "nt"

    # ============ A. PowerShell / shell auto-translation (Windows) ============
    print("=== A. shell translation (Windows-only) ===")
    if win:
        pt, twa = T.powershell_translate, T.translate_windows_aliases
        check(pt("cd X && git status") == "cd X; if ($?) { git status }",
              "`cd X && git status` loop -> if ($?)  [ELSA hallucinated success]")
        check(pt("git log | head -20") == "(git log) | Select-Object -First 20",
              "`| head -20` (head not a cmdlet) -> Select-Object -First 20")
        check(pt("cat x | tail -5") == "(cat x) | Select-Object -Last 5",
              "`| tail -5` -> Select-Object -Last 5")
        check("Measure-Object" in pt("git log | wc -l"), "`| wc -l` -> Measure-Object")
        check(pt('git log | grep "x"') == '(git log) | Select-String "x"',
              "`| grep x` -> Select-String")
        check(twa('grep -n "max_retries" f.py')
              == 'Select-String -Pattern "max_retries" -Path f.py',
              "standalone `grep PATTERN FILE` -> Select-String -Path")
        # `| grep -n PATTERN` (flags in a PIPE) must NOT be mis-split into
        # -Pattern <flag> -Path <pattern> (produced 'Missing argument for Pattern').
        g = pt('cat r.js | grep -n "resolveModule" | head -10')
        check("Select-String \"resolveModule\"" in g and "-Path" not in g,
              "`| grep -n P` keeps P as pattern, no bogus -Path (was: broken cmd)")
        check(twa('git log | grep -i "fix"').count("-Path") == 0,
              "grep flags in a pipe never invent a -Path file arg")
        # standalone head/tail with ONE file -> Get-Content (Windows has neither).
        check(twa("head -20 out.log") == "Get-Content out.log -TotalCount 20",
              "standalone `head -N FILE` -> Get-Content -TotalCount")
        check(twa("tail -n 5 server.log") == "Get-Content server.log -Tail 5",
              "standalone `tail -n N FILE` -> Get-Content -Tail")
        check(twa("head -5 a.js b.js") == "head -5 a.js b.js",
              "multi-file head is left alone (no clean equivalent)")
        check(twa("curl -s -o x https://a") == "curl.exe -s -o x https://a",
              "`curl` (PS alias for Invoke-WebRequest) -> curl.exe")
        # `2>nul` (cmd null device) BREAKS PowerShell ("device that was not a
        # file") — now auto-translated to 2>$null so the command runs.
        check(T.translate_null_redirects("dir /s /b *Seizure* 2>nul")
              == "dir /s /b *Seizure* 2>$null",
              "`2>nul` (reserved DOS device) -> 2>$null (auto-translated)")
        check(T.translate_null_redirects("git log 2>/dev/null") == "git log 2>$null",
              "`2>/dev/null` -> 2>$null (auto-translated)")
        check(T.translate_null_redirects("echo 2>&1") == "echo 2>&1",
              "`2>&1` is NOT mistaken for a null redirect")
        # QUOTE-SAFETY: a redirect token INSIDE a quoted string (commit message,
        # echo, doc) must NOT be rewritten — only the real redirect outside quotes.
        check(T.translate_null_redirects('git commit -m "handle 2>/dev/null path"')
              == 'git commit -m "handle 2>/dev/null path"',
              "`2>/dev/null` inside a quoted commit message is NOT corrupted")
        check(T.translate_null_redirects('echo "log 2>nul" 2>nul')
              == 'echo "log 2>nul" 2>$null',
              "quoted `2>nul` preserved; the real trailing `2>nul` still translates")
        check(T.translate_windows_aliases('echo "then; curl the api"')
              == 'echo "then; curl the api"',
              "`curl` inside a quoted string is NOT rewritten to curl.exe")
        h = T.shell_syntax_hint("dir x 2>nul",
                                "FileStream was asked to open a device that was not a file")
        check("$null" in h, "leftover `nul` device error -> $null fallback hint")
        check("Get-ChildItem" in T.shell_syntax_hint("find . -type f -name x",
                                                      "find: command not found"),
              "unix `find -type` -> Get-ChildItem hint")
        check(T.shell_syntax_hint("dir C:\\x /b", "DirArgumentError path2")
              and not T.shell_syntax_hint("dir C:\\x /b", "(exit 0)\na.txt"),
              "`dir /b` hint fires on the dir error, NOT on a translated success")
        # single-path `dir /b` / `dir /s /b` now auto-translate (model ignored the
        # hint 3x; "Second path fragment must not be a drive" on every try).
        check(T.translate_dir_switches('dir "C:\\p\\svc" /b 2>&1')
              == 'Get-ChildItem "C:\\p\\svc" -Name 2>&1',
              "`dir PATH /b` -> Get-ChildItem PATH -Name (redirect preserved)")
        check("-Recurse" in T.translate_dir_switches('dir "C:\\p" /s /b')
              and "-Name" in T.translate_dir_switches('dir "C:\\p" /s /b'),
              "`dir PATH /s /b` -> Get-ChildItem PATH -Recurse -Name")
        check(T.translate_dir_switches("dir /s /b *a* *b* 2>nul")
              == "dir /s /b *a* *b* 2>nul",
              "multi-glob `dir` is left for the hint (GCI can't take 2 filespecs)")
        check(T.translate_dir_switches("dir C:\\p") == "dir C:\\p",
              "plain `dir` (no cmd switch) is untouched — it works in PowerShell")
        # `Get-Content`/`cat` on a missing path (bash-read of an ASSUMED file) gets
        # the same did-you-mean + read_file nudge that read_file gives.
        preg, pwd = _reg({"config/babel.config.cjs": "x"})
        ph = T.shell_path_not_found_hint(
            "Get-Content babel.config.cjs",
            r"Get-Content : Cannot find path 'Z:\x\babel.config.cjs' because it "
            r"does not exist.", str(pwd))
        check("Did you mean" in ph and "babel.config.cjs" in ph
              and "read_file tool" in ph,
              "bash `Get-Content missing` -> did-you-mean + read_file nudge")

    # ============ B. Prompted tool-call parsing ============
    print("=== B. tool-call parsing ===")
    c, _ = parse_tool_calls('<tool name="bash"><param name="command">ls C:/x'
                            '</parameter><param name="interpreter">powershell</parameter></tool>')
    check(c and c[0].args.get("command") == "ls C:/x"
          and c[0].args.get("interpreter") == "powershell",
          "`</parameter>` close (Anthropic tag) doesn't drop/contaminate the value")
    c, _ = parse_tool_calls('<function_calls><invoke name="list_dir">'
                            '<parameter name="path">.</parameter></invoke></function_calls>')
    check(c and c[0].name == "list_dir", "Anthropic `<invoke>` format parses; wrapper stripped")
    c, _ = parse_tool_calls('<think>reason</think><tool name="glob">'
                            '<param name="pattern">*.py</param></tool>')
    check(c and c[0].name == "glob", "`<think>` reasoning stripped; tool after it parses")
    c, _ = parse_tool_calls('{"name":"bash","arguments":{"command":"echo hi"}}')
    check(c and c[0].args.get("command") == "echo hi", "JSON tool call parsed (Qwen/GLM shape)")
    c, _ = parse_tool_calls(r'<tool name="bash"><param name="command">'
                            r'Get-Content C:\x\nodeids</param></tool>')
    check(c and c[0].args["command"] == r"Get-Content C:\x\nodeids",
          r"Windows path `\nodeids` NOT mangled by the \n/\t escape-decode")

    # ============ C. Loop recovery (reflection / breakers) ============
    print("=== C. loop recovery ===")
    from robodog_terminal.toolcall import has_unclosed_tool_call, looks_like_attempted_tool
    check(has_unclosed_tool_call('<tool name="bash"><param name="command">ls'),
          "truncated (unclosed) tool call detected -> re-emit, not 'no tool'")
    check(looks_like_attempted_tool("<function_calls> broke it"),
          "tool-shaped-but-unparsed -> format-reminder reflection")
    reg, _ = _reg()
    r = reg.execute("write_files", {"path": "x"})
    check("Did you mean 'write_file'" in r, "hallucinated tool name -> closest-match suggestion")

    # ============ D. File/dir tools — misses become recoveries ============
    print("=== D. file/dir recovery ===")
    reg, wd = _reg({"docs/runbooks/RUNBOOK-build-run-serioplus.md": "x",
                    "docs/runbooks/RUNBOOK-run-serio.md": "y",
                    "src/main/A.java": "z", "note.py": "value = 2\n"})
    r = reg.execute("read_file", {"path": "docs/runbooks/RUNBOOK-serioplus-stack.md"})
    check("Did you mean" in r and "RUNBOOK-build-run-serioplus" in r,
          "read_file near-miss -> fuzzy sibling (RUNBOOK case)")
    (wd / "srcx" / "test").mkdir(parents=True)
    r = reg.execute("list_dir", {"path": "srcx/tests"})
    check("Did you mean" in r and "test" in r, "list_dir near-miss subdir -> src/test")
    r = reg.execute("list_dir", {"path": "note.py"})
    check("is a file" in r and "read_file" in r, "list_dir on a file -> use read_file")
    # glob that matches nothing orients the model with what IS there (it globbed
    # *.test.js, got nothing, then read 12 files it only ASSUMED existed).
    (wd / "suite").mkdir()
    (wd / "suite" / "chatHandler.js").write_text("x")
    r = reg.execute("glob", {"path": "suite", "pattern": "*.test.js"})
    check("No files matching" in r and "chatHandler.js" in r and "ARE present" in r,
          "glob with 0 matches shows the files that DO exist (not a bare 'no files')")
    (wd / "node_modules" / "pkg").mkdir(parents=True)
    (wd / "node_modules" / "pkg" / "d.test.js").write_text("x")
    r = reg.execute("glob", {"path": ".", "pattern": "*.test.js"})
    check("node_modules" not in r, "glob prunes node_modules (never descends into it)")
    reg.execute("read_file", {"path": "note.py"})
    r = reg.execute("edit_file", {"path": "note.py", "old_string": "value = 1",
                                  "new_string": "value = 2"})
    check("ALREADY present" in r, "edit already-applied (idempotency) -> stop retrying")
    r = reg.execute("edit_file", {"path": "note.py", "old_string": "valeu = 9",
                                  "new_string": "z"})
    check("closest line" in r, "edit old_string typo -> closest-line hint")
    # freshness
    f = wd / "note.py"
    rec = reg.read_paths[str(f)]
    os.utime(f, (rec + 100, rec + 100))
    r = reg.execute("edit_file", {"path": "note.py", "old_string": "value = 2", "new_string": "q"})
    check("CHANGED ON DISK" in r, "edit a file changed on disk since read -> refuse")
    # byte-faithful write + verify-after-write
    reg.execute("write_file", {"path": "crlf.txt", "content": "a\r\nb\r\n"})
    check((wd / "crlf.txt").read_bytes() == b"a\r\nb\r\n", "CRLF content written byte-faithfully")
    # missing required param -> shows the format
    r = reg.execute("write_file", {"path": "y.txt"})
    check('<param name="content">' in r and "missing required" in r,
          "missing required param -> shows the exact skeleton to emit")

    # ============ E. Command-error self-heal hints ============
    print("=== E. error hints ===")
    check("json.loads" in T.python_error_hint(
        "TypeError: the JSON object must be str, bytes or bytearray, not dict"),
        "`json.loads(dict)` -> value already parsed, drop json.loads")
    hreg, hwd = _reg()
    (hwd / "fdaskills" / "jira" / "jira-call").mkdir(parents=True)
    (hwd / "fdaskills" / "jira" / "jira-call" / "main.py").write_text("x")
    check("importlib" in T.python_import_hint(
        "ModuleNotFoundError: No module named 'fdaskills.jira.jira_call'", str(hwd)),
        "hyphenated skill dir (jira_call -> jira-call) -> importlib hint")
    (hwd / "src").mkdir(exist_ok=True)
    check("PYTHONPATH" in T.python_import_hint(
        "ModuleNotFoundError: No module named 'src'", str(hwd)),
        "src-layout `No module named 'src'` -> PYTHONPATH hint")
    check("pytest" in T.python_error_hint("C:\\Py\\python.exe: No module named pytest"),
          "`No module named pytest` -> install / same-interpreter hint")
    check("Node project" in T.npm_error_hint('npm error Missing script: "test"'),
          "`npm Missing script: test` in a non-Node repo -> hint")
    # Maven COMPILE failure vs TEST failure (SERIOPlus `mvn test` on code that
    # doesn't build — package/DTO missing — never ran a test).
    check("NO tests ran" in T.maven_error_hint(
        "[ERROR] COMPILATION ERROR :\n[ERROR] package gov.fda.x.dto does not exist\n"
        "[INFO] BUILD FAILURE\n[ERROR] ...maven-compiler-plugin:3.11.0:compile"),
        "mvn compile failure -> 'code doesn't build, no tests ran', not a test bug")
    check("surefire-reports" in T.maven_error_hint(
        "Tests run: 5, Failures: 2, Errors: 0\nThere are test failures.\nBUILD FAILURE"),
        "mvn compiled-but-tests-failed -> point at surefire-reports")
    check("missing method `loadLicense`" in T.maven_error_hint(
        "cannot find symbol\n  symbol:   method loadLicense\nBUILD FAILURE\n"
        "maven-compiler-plugin:compile"),
        "mvn compile error names a missing METHOD (not just a class)")
    if win:
        check("isn't grep" in T.findstr_syntax_hint(r'findstr /n "a\|b\|c" f.java')
              and T.findstr_syntax_hint('findstr "plain" f.java') == "",
              "`findstr \\|` (GNU alternation) -> use /c: or Select-String hint")
    check(T.maven_error_hint("BUILD SUCCESS\nTests run: 5, Failures: 0") == "",
          "a passing Maven build gets no error hint")
    # pytest COLLECTION error vs test failure (Shared-AI-Service thrash):
    check("pip install fastapi" in T.pytest_error_hint(
        "=== ERRORS ===\nERROR collecting tests/unit/test_models.py\n"
        "ImportError while importing test module\n"
        "ModuleNotFoundError: No module named 'fastapi'"),
        "pytest collection ImportError -> 'install dep / fix sys.path', not a failure")
    check("import-mode=importlib" in T.pytest_error_hint(
        "import file mismatch: ... not the same as the test file we want to collect"),
        "pytest duplicate-basename import mismatch -> --import-mode=importlib hint")
    check(T.pytest_error_hint(
        "FAILED tests/unit/test_a.py::t - assert 422 == 200\n1 failed, 3 passed") == "",
        "ordinary pytest assertion failure is NOT mistaken for a collection error")

    # ============ F. Safety — outward-facing writes gated ============
    print("=== F. safety guard ===")
    check(T.classify_network_mutation(
        'mod.run({"method": "POST", "path": "/rest/api/2/issue/SERIO-1/transitions"})'),
        "Jira POST /transitions (the ticket-close incident) is flagged")
    check(T.classify_network_mutation("git push --force origin main"),
          "`git push --force` (Gemini incident class) is flagged")
    check(T.classify_network_mutation('mod.run({"method": "GET", "path": "/x"})') is None,
          "a GET (read) is NOT flagged")
    sreg, _ = _reg()
    sreg.net_guard = "confirm"; sreg.on_confirm = None   # headless/subagent
    r = sreg.execute("run_script", {"content": 'requests.post("http://x/close")'})
    check(r.startswith("BLOCKED"), "network write with no confirmer -> fail-safe BLOCK")
    sreg.register(T.Tool(name="brand_new", description="x",
                         params=[T.ToolParam("command", "c")], handler=lambda a: "ran"))
    r = sreg.execute("brand_new", {"command": 'requests.delete("http://x")'})
    check(r.startswith("BLOCKED"), "a NEW tool is guarded by default (fail-safe)")

    # ============ G. Gateway resilience ============
    print("=== G. gateway resilience ===")
    from robodog_terminal.llm_client import (_parse_retry_after, _backoff_delay,
                                             _http_error_hint, estimate_cost)
    check(_parse_retry_after("5") == 5.0 and _parse_retry_after("junk") is None,
          "Retry-After parsed (seconds / garbage-safe)")
    check(all(0.5 <= _backoff_delay(a) <= 60.0 for a in range(1, 6)),
          "jittered backoff bounded to [0.5, 60]s")
    check("isn't available on this provider" in _http_error_hint(
        404, "https://openrouter.ai/api", "anthropic/claude-3.5-haiku",
        '{"error":{"message":"No endpoints found for anthropic/claude-3.5-haiku."}}'),
        "404 `No endpoints for <model>` -> model-slug hint (not base-URL)")
    check(estimate_cost("anthropic/claude-sonnet-4.6", 1_000_000, 0) == 3.0
          and estimate_cost("8405ac40-gateway-model", 100, 100) is None,
          "cost estimate: priced model + None for a gateway/unknown model")

    print("\nREGRESSIONS:", "ALL PASS" if ok else "FAILURES")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
