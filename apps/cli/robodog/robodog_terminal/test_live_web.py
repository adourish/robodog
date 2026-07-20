# file: robodog_terminal/test_live_web.py
"""
Opt-in LIVE end-to-end tests — real network, real subprocesses, real browser.

    ROBODOG_LIVE=1 python robodog_terminal/test_live_web.py
    ROBODOG_LIVE=1 python robodog_terminal/run_tests.py    (appends this suite)

Covers what the deterministic suite can't:
  1. Parallel web fan-out: subagents fetch several LIVE websites concurrently
     via run_script, and every child comes back attributed with a title.
  2. Polyglot squad: python / powershell / bash children in ONE turn, plus a
     live PyPI API call.
  3. Playwright CLI: a child launches a real browser and captures a page.

Deliberately NOT asserted here: timing/speedup (network jitter makes that
flaky — the concurrency proof lives in test_subagent_stress.py with
deterministic sleeps). Environment-dependent pieces (powershell, bash,
playwright) skip cleanly when absent so the suite is portable.
"""
from __future__ import annotations

import html
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from robodog_terminal.agents import register_agent_tool     # noqa: E402
from robodog_terminal.llm_client import EchoClient           # noqa: E402
from robodog_terminal.loop import AgentLoop                  # noqa: E402
from robodog_terminal.tools import default_registry          # noqa: E402

ok = True


def check(cond, msg):
    global ok
    print(f"  [{'PASS' if cond else 'FAIL'}] {msg}")
    ok = ok and cond


def skip(msg):
    print(f"  [SKIP] {msg}")


def _online() -> bool:
    import urllib.request
    try:
        urllib.request.urlopen("https://pypi.org", timeout=10)
        return True
    except Exception:
        return False


FETCH_CODE = """\
import re, urllib.request
req = urllib.request.Request({url!r}, headers={{"User-Agent": "robodog-live-test"}})
body = urllib.request.urlopen(req, timeout=20).read(65536).decode("utf-8", "replace")
m = re.search(r"<title[^>]*>(.*?)</title>", body, re.S | re.I)
print("FETCHED title:", " ".join((m.group(1) if m else "(no title)").split())[:60])
"""


def _tool(code: str, interpreter: str = "python") -> str:
    return (f'<tool name="run_script"><param name="content">{html.escape(code)}'
            f'</param><param name="interpreter">{interpreter}</param>'
            f'<param name="timeout">90</param></tool>')


def _run_fanout(tasks, marker):
    """Parent fans out one child per task; each child runs its script then
    summarizes any 'RESULT ...' / 'FETCHED ...' line from the tool output."""
    def script(prompt, ctx=""):
        if "TOOL RESULT [agent]" in prompt:
            return "PARENT_DONE"
        if marker in prompt:
            unit = prompt.split(f"{marker} ")[1].split(" ")[0].strip()
            interp, code = tasks[unit]
            if "TOOL RESULT [run_script]" in prompt:
                hits = [h for h in re.findall(r"(?:RESULT|FETCHED) (.+)", prompt)
                        if "{" not in h and "'" not in h[:8]]
                return f"CHILD_OK {unit}: {hits[-1].strip()[:80]}" if hits \
                    else f"CHILD_NORESULT {unit}"
            return _tool(code, interp)
        return "".join(
            f'<tool name="agent"><param name="prompt">{marker} {u} go</param>'
            f'<param name="type">general</param></tool>' for u in sorted(tasks))

    client = EchoClient(script=script)
    reg = default_registry(cwd=tempfile.mkdtemp(prefix="rd_live_"))
    register_agent_tool(reg, client)
    loop = AgentLoop(client, reg, max_iterations=8)
    t0 = time.time()
    res = loop.run("live fan-out")
    wall = time.time() - t0
    children = [t.content for t in loop.history if t.tool_name == "agent"]
    return res, children, wall


def main() -> int:
    global ok
    if os.environ.get("ROBODOG_LIVE") != "1":
        print("LIVE WEB: skipped (set ROBODOG_LIVE=1 to run)")
        return 0
    if not _online():
        print("LIVE WEB: skipped (no network)")
        return 0

    # ---- 1. parallel live-website fan-out --------------------------------
    print("=== 1. parallel live-website fetch (4 subagents) ===")
    SITES = {
        "0": "https://example.com",
        "1": "https://pypi.org",
        "2": "https://en.wikipedia.org/wiki/HTTP",
        "3": "https://www.python.org",
    }
    tasks = {u: ("python", FETCH_CODE.format(url=url)) for u, url in SITES.items()}
    res, children, wall = _run_fanout(tasks, "WEBCHILD")
    n_ok = sum(1 for c in children if c.startswith(
        ("[subagent", "CHILD_OK")) and "CHILD_OK" in c)
    check(len(children) == len(SITES), f"all {len(SITES)} children returned a result slot")
    check(n_ok >= len(SITES) - 1,
          f"fetched {n_ok}/{len(SITES)} live sites with a title (1 flake tolerated)")
    check("PARENT_DONE" in res.final_text, "parent synthesized after the web fan-out")
    check(wall < 90, f"fan-out completed in sane time ({wall:.1f}s)")
    ids = sorted(int(m.group(1)) for c in children
                 for m in [re.search(r"subagent#(\d+):", c)] if m)
    check(len(set(ids)) == len(SITES), f"every child result attributed with a unique id ({ids})")

    # ---- 2. polyglot squad: 3 interpreters + a live API in one turn ------
    print("=== 2. polyglot squad (python + powershell + bash + PyPI API) ===")
    squad = {
        "0": ("python",
              "fibs=[0,1]\n"
              "for _ in range(6): fibs.append(fibs[-1]+fibs[-2])\n"
              "print('RESULT fib8:', fibs[7])"),
        "1": ("python",
              "import json, urllib.request\n"
              "d = json.load(urllib.request.urlopen(\n"
              "    'https://pypi.org/pypi/robodog-terminal/json', timeout=20))\n"
              "print('RESULT pypi latest:', d['info']['version'])"),
    }
    have_ps = os.name == "nt" and shutil.which("powershell")
    if have_ps:
        squad["2"] = ("powershell", "Write-Output \"RESULT cores: $env:NUMBER_OF_PROCESSORS\"")
    else:
        skip("powershell child (not on this platform)")
    if shutil.which("bash"):
        squad["3"] = ("bash", "echo \"RESULT shell: $0 works\"")
    else:
        skip("bash child (bash not on PATH)")

    res, children, wall = _run_fanout(squad, "SQUADCHILD")
    ok_children = [c for c in children if "CHILD_OK" in c]
    check(len(children) == len(squad), f"all {len(squad)} squad children returned")
    check(len(ok_children) == len(squad),
          f"every interpreter/API child produced its RESULT line ({len(ok_children)}/{len(squad)})")
    check(any("fib8: 13" in c for c in children), "python child computed fib(8)=13")
    check(any(re.search(r"pypi latest: \d+\.\d+\.\d+", c) for c in children),
          "PyPI API child returned a real version")
    if have_ps:
        check(any(re.search(r"cores: \d+", c) for c in children),
              "powershell child reported CPU count")
    if "3" in squad:
        check(any("shell:" in c for c in children), "bash child ran")

    # ---- 3. Playwright CLI: a child drives a real browser ----------------
    print("=== 3. Playwright CLI browser capture ===")
    pw_ok = False
    try:
        probe = subprocess.run("npx playwright --version", shell=True,
                               capture_output=True, text=True, timeout=60,
                               cwd=str(Path(__file__).resolve().parents[3]))
        pw_ok = probe.returncode == 0 and "Version" in probe.stdout
    except Exception:
        pass
    if not pw_ok:
        skip("playwright child (npx playwright not available)")
    else:
        shot = Path(tempfile.mkdtemp(prefix="rd_pw_")) / "capture.png"
        repo_root = Path(__file__).resolve().parents[3]
        pw_code = (
            f"cd \"{repo_root}\"\n"
            f"npx playwright screenshot --viewport-size=800,500 "
            f"https://example.com \"{shot}\" 2>&1 | Out-Null\n"
            f"if (Test-Path \"{shot}\") "
            f"{{ Write-Output \"RESULT captured: $((Get-Item \"{shot}\").Length) bytes\" }} "
            f"else {{ Write-Output 'RESULT capture-missing' }}"
        ) if os.name == "nt" else (
            f"cd '{repo_root}' && npx playwright screenshot --viewport-size=800,500 "
            f"https://example.com '{shot}' >/dev/null 2>&1; "
            f"[ -f '{shot}' ] && echo \"RESULT captured: $(stat -c%s '{shot}') bytes\" "
            f"|| echo 'RESULT capture-missing'"
        )
        interp = "powershell" if os.name == "nt" else "bash"
        res, children, wall = _run_fanout({"0": (interp, pw_code)}, "PWCHILD")
        check(any("captured:" in c for c in children),
              "playwright child reports a captured screenshot")
        check(shot.exists() and shot.stat().st_size > 1000,
              f"browser capture exists and is a real image "
              f"({shot.stat().st_size if shot.exists() else 0} bytes)")

    print("\nLIVE WEB:", "ALL PASS" if ok else "FAILURES")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
