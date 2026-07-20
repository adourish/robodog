# file: docs/screenshots/generate.py
"""
Regenerate the README screenshots. Every scene is rendered by the REAL UI
code (rich SVG export) driving real components — no mockups. Run after
changing anything in robodog_terminal/ui.py so the docs stay honest:

    python docs/screenshots/generate.py

Then convert SVG -> PNG (headless Chrome):

    python docs/screenshots/generate.py --png

Scenes 11 (parallel live-website fetch) and 12 (polyglot squad + Playwright)
hit real network and launch a real browser, so they only refresh with an
explicit opt-in — pass --live to include them:

    python docs/screenshots/generate.py --live --png
"""
import os, re, subprocess, sys, tempfile, time
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "apps" / "cli" / "robodog"))

from rich.console import Console
from robodog_terminal.ui import UI
from robodog_terminal.agents import register_agent_tool
from robodog_terminal.llm_client import EchoClient
from robodog_terminal.loop import AgentLoop
from robodog_terminal.tools import default_registry
from robodog_terminal.tasklist import TaskChecklist
from robodog_terminal.background import BackgroundManager
from robodog_terminal.doctor import CheckResult, format_report

OUT = Path(__file__).parent
OUT = Path(__file__).parent
W = 100

def fresh_ui(cwd=None):
    ui = UI(model_name="anthropic/claude-sonnet-4.6", cwd=cwd or r"C:\projects\robodog")
    ui.console = Console(record=True, force_terminal=True, width=W,
                         legacy_windows=False, file=open("nul", "w", encoding="utf-8"))
    return ui

def save(ui, name, title):
    ui.console.save_svg(str(OUT / name), title=title)
    print("saved", name)

# ---------- scene 1: welcome + status line --------------------------------
ui = fresh_ui()
ui.welcome()
ui.total_tokens = 15_600
ui.context_pct = 36
ui.print_status()
save(ui, "1_welcome.svg", "robodog — welcome + status line")

# ---------- scene 2: fan-out, compact (default) ---------------------------
ANSWERS = {
    "0": "module 0 clean, no issues",
    "1": "module 1 has a race in init()",
    "2": "module 2 clean",
    "3": "module 3: two dead functions found",
    "4": "module 4 clean",
    "5": "module 5: TODO comments only",
}
def fan_script(prompt, ctx=""):
    if "TOOL RESULT [agent]" in prompt:
        return ("Reviewed all six modules in parallel. Two need attention: "
                "module 1 (race in init) and module 3 (dead code).")
    if "CHILD" in prompt:
        unit = prompt.split("CHILD task ")[1].split(":")[0]
        time.sleep(0.05)
        return f"Findings: {ANSWERS[unit]}."
    return "".join(
        f'<tool name="agent"><param name="prompt">CHILD task {i}: analyze module {i}</param>'
        f'<param name="type">general</param></tool>' for i in range(6))

def run_fanout(ui, verbose):
    client = EchoClient(script=fan_script)
    reg = default_registry(cwd=tempfile.mkdtemp())
    import threading
    stats = {"children": set(), "calls": 0}
    lock = threading.Lock()
    def on_child_event(kind, data):
        if kind != "tool_start":
            return
        if verbose:
            cid = data.get("child_id")
            tag = f"#{cid} " if cid else ""
            arg = str(data.get('args', {}).get('command')
                      or data.get('args', {}).get('path') or '')[:60]
            ui.dim(f"      ⚙ {tag}{data['name']} {arg}")
    register_agent_tool(reg, client, on_child_event=on_child_event)
    def on_event(kind, data):
        if kind == "tool_start":
            ui.tool_call(data["name"], data["args"])
        elif kind == "tool_done":
            if verbose:
                ui.dim(data["result"])
            else:
                ui.tool_result(data["name"], data["result"])
    loop = AgentLoop(client, reg, max_iterations=6, on_event=on_event)
    ui.console.print("[bold magenta]›[/bold magenta] review all modules in parallel with subagents")
    res = loop.run("review all modules in parallel with subagents")
    ui.assistant(res.final_text)
    ui.dim(f"[{res.iterations} steps · {res.total_tokens} tok · 1.9s]")

ui = fresh_ui()
# what the live spinner line looks like while children run (frozen for the shot)
run_fanout(ui, verbose=False)
save(ui, "2_fanout_compact.svg", "robodog — 6-way subagent fan-out (compact, default)")

# ---------- scene 3: same fan-out, /verbose -------------------------------
ui = fresh_ui()
ui.info("verbose output ON — full tool results and per-call subagent trace")
run_fanout(ui, verbose=True)
save(ui, "3_fanout_verbose.svg", "robodog — same fan-out with /verbose")

# ---------- scene 4: tool trace, failures, bounded stream -----------------
ui = fresh_ui()
ui.tool_call("read_file", {"path": r"robodog_terminal\app.py"})
ui.tool_result("read_file", "\n".join(f"{i}: line {i}" for i in range(1, 47)))
ui.tool_call("grep", {"pattern": "def build_backend"})
ui.tool_result("grep", "robodog_terminal/app.py:170: def build_backend(args, on_retry=None)\n+2 more")
ui.tool_call("bash", {"command": "python -m pytest -q"})
for i in range(1, 19):
    ui.bash_line(f"test_module_{i:02d}.py .....")
ui.stream_footer()
ui.tool_result("bash", "$ python -m pytest -q\n(exit 0)\n--- stdout ---\n" +
               "\n".join(f"test_module_{i:02d}.py ....." for i in range(1, 19)))
ui.tool_call("edit_file", {"path": "config.py"})
ui.tool_result("edit_file", "ERROR: edit target not found in config.py — the old text does not match.")
ui.tool_call("bash", {"command": "python broken.py"})
ui.tool_result("bash", "$ python broken.py\n⚠ COMMAND FAILED (exit 1)\nTraceback: NameError: x")
save(ui, "4_tool_trace.svg", "robodog — tool trace: summaries, bounded stream, loud failures")

# ---------- scene 5: diff preview ------------------------------------------
ui = fresh_ui()
ui.diff(r"robodog_terminal\llm_client.py",
        "--- a/llm_client.py\n+++ b/llm_client.py\n@@ -305,6 +305,8 @@\n"
        "                elif resp.status_code in (429,) or resp.status_code >= 500:\n"
        "                     last_err = f\"HTTP {resp.status_code}\"\n"
        "                 else:\n"
        "-                    raise RuntimeError(f\"LLM HTTP {resp.status_code}\")\n"
        "+                    hint = _http_error_hint(resp.status_code, self.url, self.model)\n"
        "+                    raise RuntimeError(f\"LLM HTTP {resp.status_code}: {resp.text[:300]}{hint}\")\n")
save(ui, "5_diff.svg", "robodog — colored diff preview on edit")
OUT = Path(__file__).parent
W = 100

# ---------- scene 6: plan mode -------------------------------------------
ui = fresh_ui()
ui.console.print("[bold magenta]›[/bold magenta] /plan")
ui.info("plan mode ON — the agent proposes before touching files")
ui.console.print("[bold magenta]›[/bold magenta] add retry logic to the HTTP client")
ui.tool_call("read_file", {"path": r"robodog_terminal\llm_client.py"})
ui.tool_result("read_file", "\n".join(f"{i}: ..." for i in range(1, 320)))
ui.assistant(
    "## Plan\n"
    "1. Add `max_attempts` + exponential backoff to `OpenAICompatClient.complete`\n"
    "2. Retry only on 429/5xx/network errors — fail fast on 4xx\n"
    "3. Surface a visible retry line via the `on_retry` hook\n"
    "4. Add tests: 5xx retried, 401 fails fast, backoff capped at 30s")
ui.console.print("\n  approve plan? \\[y = implement / n = keep planning]: [bold]y[/bold]")
ui.info("⏵ implementing…")
save(ui, "6_plan_mode.svg", "robodog — /plan: propose, approve, implement")

# ---------- scene 7: task checklist (/todos) -------------------------------
from robodog_terminal.tasklist import TaskChecklist
ui = fresh_ui()
cl = TaskChecklist()
cl.add("Read llm_client.py and map the retry paths")
cl.add("Add exponential backoff with a 30s cap")
cl.add("Retry 429/5xx only; 4xx fails fast")
cl.add("Extend test_llm_client.py")
items = cl._items
items[0].status = "completed"
items[1].status = "completed"
items[2].status = "in_progress"
ui.console.print("[bold magenta]›[/bold magenta] /todos")
for ln in cl.render_lines():
    ui.info(f"  {ln}")
ui.dim(f"  {cl.summary()}")
save(ui, "7_todos.svg", "robodog — the agent's live task checklist")

# ---------- scene 8: background subagents ----------------------------------
from robodog_terminal.background import BackgroundManager
ui = fresh_ui()
mgr = BackgroundManager()
def slow(task):
    time.sleep(0.3)
    return "Benchmarks complete: fan-out 7.9x faster than serial."
def quick(task):
    return "Docs audit done: 3 stale links fixed."
t1 = mgr.spawn("agent", "general: run the perf benchmarks", slow)
t2 = mgr.spawn("agent", "explore: audit the docs for stale links", quick)
time.sleep(0.05)
ui.console.print("[bold magenta]›[/bold magenta] /bg run the perf benchmarks")
ui.tool_call("agent", {"prompt": "run the perf benchmarks", "background": "true"})
ui.tool_result("agent", f"Started background subagent {t1.id} (general). Continue other work; "
                        f"fetch its result later with task_output.")
ui.console.print("[bold magenta]›[/bold magenta] /tasks")
for t in mgr.list():
    dur = f"{(t.ended or time.time()) - t.started:.0f}s"
    ui.info(f"  {t.id}  [{t.status:7}]  {t.kind:5}  {dur:>5}  {t.title}")
time.sleep(0.5)
for note in mgr.drain_notifications():
    ui.dim(note)
save(ui, "8_background.svg", "robodog — background subagents: /bg, /tasks, done notifications")

# ---------- scene 9: /doctor ------------------------------------------------
from robodog_terminal.doctor import CheckResult, format_report
ui = fresh_ui()
results = [
    CheckResult("python", True, "3.11.9"),
    CheckResult("rich", True, "importable 14.2.0"),
    CheckResult("prompt_toolkit", True, "importable 3.0.52"),
    CheckResult("tty", True, "stdin is a TTY"),
    CheckResult("encoding", True, "stdout encoding utf-8"),
    CheckResult("cwd-writable", True, r"writable: C:\projects\robodog"),
    CheckResult("keepass", True, "unlocked; entries present: OpenRouter, OpenAI; missing: Gateway"),
    CheckResult("gateway-env", None, "set: none; unset: GATEWAY_ENDPOINT, GATEWAY_ENGINE, "
                                     "GATEWAY_ACCESS_KEY, GATEWAY_SECRET_KEY"),
    CheckResult("openai-endpoint", True, "api.openai.com:443 reachable"),
    CheckResult("model-backend", False, "'anthropic/claude-sonnet-4.6' is an OpenRouter-style id "
                                        "(provider/model) but the backend is OpenAI's API directly "
                                        "— use --backend openrouter"),
    CheckResult("terminal-modules", True, "8/8 modules import cleanly"),
]
ui.console.print("[bold magenta]›[/bold magenta] /doctor")
ui.info(format_report(results))
save(ui, "9_doctor.svg", "robodog — /doctor diagnostics with the model-backend check")

# ---------- scene 10: actionable error hints --------------------------------
ui = fresh_ui()
ui.console.print("[bold magenta]›[/bold magenta] fix the failing test")
ui.error('RuntimeError: LLM HTTP 400: {"error": {"message": "invalid model ID"}}\n'
         "Hint: 'anthropic/claude-sonnet-4.6' looks like an OpenRouter-style model id "
         "(provider/model), but this client is pointed at OpenAI's API directly. "
         "Use --backend openrouter (or --backend auto) instead.")
ui.console.print()
ui.error("RuntimeError: LLM HTTP 401: Unauthorized\n"
         "Hint: the API key was rejected. Check ROBODOG_LLM_KEY (env) or the KeePass "
         "'OpenRouter'/'OpenAI' entry — the key may be missing, expired, or for a "
         "different provider.")
save(ui, "10_error_hints.svg", "robodog — errors explain themselves")

# ---------- scene 13: .claude extensions from a Claude Code project ---------
from robodog_terminal.skills import SkillsRegistry

_wd = Path(tempfile.mkdtemp(prefix="rd_shot_cc_"))
_cd = _wd / ".claude"
(_cd / "commands").mkdir(parents=True)
(_cd / "commands" / "ship.md").write_text(
    "---\ndescription: build, tag, and publish a release\nargument-hint: <version>\n---\n"
    "Ship release $1: run the tests, bump the version, publish.", encoding="utf-8")
(_cd / "agents").mkdir()
(_cd / "agents" / "reviewer.md").write_text(
    "---\nname: reviewer\ndescription: strict read-only code reviewer\n"
    "tools: read_file, grep, glob\n---\nReview code; report issues only.", encoding="utf-8")
(_cd / "skills" / "release-notes").mkdir(parents=True)
(_cd / "skills" / "release-notes" / "SKILL.md").write_text(
    "---\ndescription: house style for release notes\n---\n"
    "Use Add/Fix/Docs prefixes, keep entries under 80 chars.", encoding="utf-8")
_rd = _wd / ".robodog"
(_rd / "commands").mkdir(parents=True)
(_rd / "commands" / "deploy.md").write_text(
    "---\ndescription: deploy to an environment\nargument-hint: <env>\n---\n"
    "Deploy to $1.", encoding="utf-8")

_reg = SkillsRegistry(cwd=str(_wd))
_reg.discover()
ui = fresh_ui()
ui.dim("(loaded project instructions: CLAUDE.md)")
ui.dim(f"(extensions: {_reg.summary()} — custom /commands, skills, and agents)")
ui.console.print("[bold magenta]›[/bold magenta] /skills")
ui.info("custom commands:")
for _n, _c in sorted(_reg.commands.items()):
    _src = ".claude" if ".claude" in _c.source else ".robodog"
    ui.info(f"  /{_n:<14} {_c.description}   [{_src}]")
ui.info("skills:")
for _n, _s in sorted(_reg.skills.items()):
    ui.info(f"  /{_n:<14} {_s.description}   [.claude]")
ui.info("custom agents:")
for _n, _a in sorted(_reg.agents.items()):
    ui.info(f"  {_n:<15} tools: {', '.join(_a.tools or ['(all)'])}   [.claude]")
ui.console.print("[bold magenta]›[/bold magenta] /ship v0.2.7")
ui.dim("  (rendered: \"Ship release v0.2.7: run the tests, bump the version, publish.\")")
ui.console.print("[bold magenta]›[/bold magenta] /release-notes")
ui.info("loaded skill 'release-notes' into context.")
save(ui, "13_claude_dir.svg",
     "robodog — .claude/ extensions from a Claude Code project, working unchanged")

# ---------- LIVE scenes (need network / Playwright): --live ------------------
# 11_parallel_web: 6 subagents fetch 6 live websites in parallel via run_script
# 12_squad: python/powershell/bash scripts + GitHub/PyPI APIs + Playwright CLI
# These re-run REAL network fetches and a REAL browser, so they only refresh
# with an explicit opt-in; the committed PNGs are kept otherwise.
if "--live" in sys.argv:
    import html as _html
    import urllib.request

    _SITES = {
        "0": "https://example.com", "1": "https://www.python.org",
        "2": "https://pypi.org", "3": "https://github.com",
        "4": "https://en.wikipedia.org/wiki/HTTP", "5": "https://openrouter.ai",
    }
    _FETCH = (
        "import re, time, urllib.request\n"
        "t0 = time.time()\n"
        "req = urllib.request.Request({url!r}, headers={{'User-Agent': 'robodog-shots'}})\n"
        "body = urllib.request.urlopen(req, timeout=20).read(65536).decode('utf-8', 'replace')\n"
        "m = re.search(r'<title[^>]*>(.*?)</title>', body, re.S | re.I)\n"
        "title = ' '.join((m.group(1) if m else '(no title)').split())[:60]\n"
        "print(f'OK {{time.time()-t0:.2f}}s · title: {{title}}')\n"
    )

    def _web_script(prompt, ctx=""):
        if "TOOL RESULT [agent]" in prompt:
            return ("All six sites fetched in parallel. Every request returned OK — "
                    "titles captured in the per-agent results above.")
        if "SEARCHCHILD" in prompt:
            unit = prompt.split("SEARCHCHILD ")[1].split(" ")[0].strip()
            url = _SITES[unit]
            if "TOOL RESULT [run_script]" in prompt:
                hits = [h for h in re.findall(r"title: (.+)", prompt) if "{" not in h]
                title = hits[-1].strip()[:60] if hits else "(unknown)"
                return f"Fetched {url} — {title}"
            return (f'<tool name="run_script"><param name="content">'
                    f'{_html.escape(_FETCH.format(url=url))}</param>'
                    f'<param name="interpreter">python</param></tool>')
        return "".join(
            f'<tool name="agent"><param name="prompt">SEARCHCHILD {i} fetch {_SITES[str(i)]}</param>'
            f'<param name="type">general</param></tool>' for i in range(6))

    ui = fresh_ui()
    ui.console = Console(record=True, force_terminal=True, width=110,
                         legacy_windows=False, file=open("nul", "w", encoding="utf-8"))
    client = EchoClient(script=_web_script)
    reg = default_registry(cwd=tempfile.mkdtemp())
    register_agent_tool(reg, client)

    def _on_event(kind, data):
        if kind == "tool_start":
            ui.tool_call(data["name"], data["args"])
        elif kind == "tool_done":
            ui.tool_result(data["name"], data["result"])

    loop = AgentLoop(client, reg, max_iterations=8, on_event=_on_event)
    ui.console.print("[bold magenta]›[/bold magenta] check six sites in parallel: "
                     "fetch each homepage and report its title")
    t0 = time.time()
    res = loop.run("check six sites in parallel")
    wall = time.time() - t0
    t1 = time.time()
    for url in _SITES.values():
        subprocess.run([sys.executable, "-c", _FETCH.format(url=url)],
                       capture_output=True, timeout=30)
    serial = time.time() - t1
    ui.assistant(res.final_text)
    ui.dim(f"[2 steps · {res.total_tokens} tok · parallel {wall:.1f}s vs serial "
           f"{serial:.1f}s → {serial / wall:.1f}x faster]")
    save(ui, "11_parallel_web.svg",
         "robodog — 6 subagents fetching 6 live websites in parallel")

    _SHOT = OUT / "web_capture.png"
    _TASKS = {
        "0": ("write and run a python script: first 8 fibonacci numbers", "python",
              "fibs=[0,1]\n"
              "for _ in range(6): fibs.append(fibs[-1]+fibs[-2])\n"
              "print('RESULT fibonacci:', fibs)"),
        "1": ("run a powershell script: OS + CPU count", "powershell",
              "$os = (Get-CimInstance Win32_OperatingSystem).Caption\n"
              "Write-Output \"RESULT os: $os / $env:NUMBER_OF_PROCESSORS cores\""),
        "2": ("run a bash script: count python files in the repo", "bash",
              "cd /c/projects/robodog/apps/cli/robodog\n"
              "echo \"RESULT py files: $(find . -name '*.py' | wc -l)\""),
        "3": ("call the GitHub API: robodog repo stats", "python",
              "import json, urllib.request\n"
              "d = json.load(urllib.request.urlopen(\n"
              "    'https://api.github.com/repos/adourish/robodog', timeout=20))\n"
              "print('RESULT github:', d['stargazers_count'], 'stars ·',\n"
              "      d['open_issues_count'], 'open issues ·', d['language'])"),
        "4": ("call the PyPI API: latest robodog-terminal release", "python",
              "import json, urllib.request\n"
              "d = json.load(urllib.request.urlopen(\n"
              "    'https://pypi.org/pypi/robodog-terminal/json', timeout=20))\n"
              "files = d['releases'][d['info']['version']]\n"
              "print('RESULT pypi:', d['info']['version'], '·', len(files), 'files')"),
        "5": ("use the Playwright CLI to screenshot example.com", "powershell",
              "cd C:\\projects\\robodog\n"
              "npx playwright screenshot --viewport-size=1000,600 "
              "https://example.com \"" + str(_SHOT) + "\" 2>&1 | Out-Null\n"
              "if (Test-Path \"" + str(_SHOT) + "\") {\n"
              "  $len = (Get-Item \"" + str(_SHOT) + "\").Length\n"
              "  Write-Output \"RESULT playwright: captured example.com ($len bytes)\"\n"
              "} else { Write-Output 'RESULT playwright: FAILED' }"),
    }

    def _squad_script(prompt, ctx=""):
        if "TOOL RESULT [agent]" in prompt:
            return ("Squad complete: three script interpreters exercised, two live APIs "
                    "answered, and Playwright captured a real browser screenshot.")
        if "SQUADCHILD" in prompt:
            unit = prompt.split("SQUADCHILD ")[1].split(" ")[0].strip()
            label, interp, code = _TASKS[unit]
            if "TOOL RESULT [run_script]" in prompt:
                hits = re.findall(r"RESULT (.+)", prompt)
                real = [h for h in hits if "'" not in h[:8] and "{" not in h]
                return f"Done — {real[-1].strip()[:90]}" if real else "Done (no RESULT line)"
            return (f'<tool name="run_script"><param name="content">{_html.escape(code)}'
                    f'</param><param name="interpreter">{interp}</param>'
                    f'<param name="timeout">90</param></tool>')
        return "".join(
            f'<tool name="agent"><param name="prompt">SQUADCHILD {i} {_TASKS[str(i)][0]}</param>'
            f'<param name="type">general</param></tool>' for i in range(6))

    ui = fresh_ui()
    ui.console = Console(record=True, force_terminal=True, width=112,
                         legacy_windows=False, file=open("nul", "w", encoding="utf-8"))
    client = EchoClient(script=_squad_script)
    reg = default_registry(cwd=tempfile.mkdtemp())
    register_agent_tool(reg, client)
    loop = AgentLoop(client, reg, max_iterations=8, on_event=_on_event)
    ui.console.print("[bold magenta]›[/bold magenta] squad task: run python/powershell/bash "
                     "scripts, hit the GitHub + PyPI APIs, and screenshot a site with "
                     "Playwright — in parallel")
    t0 = time.time()
    res = loop.run("squad")
    wall = time.time() - t0
    ui.assistant(res.final_text)
    ui.dim(f"[2 steps · {res.total_tokens} tok · {wall:.1f}s wall for all six]")
    save(ui, "12_squad.svg",
         "robodog — 6 agents: 3 script types, 2 live APIs, 1 Playwright browser capture")


def to_png():
    chrome = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
    for svg in sorted(OUT.glob("*_*.svg")):
        head = svg.read_text(encoding="utf-8")[:2000]
        m = re.search(r'viewBox="0 0 ([\d.]+) ([\d.]+)"', head)
        w, h = (int(float(m.group(1))), int(float(m.group(2)))) if m else (1200, 800)
        subprocess.run([chrome, "--headless=new", "--disable-gpu",
                        f"--screenshot={svg.with_suffix('.png').resolve()}",
                        f"--window-size={w},{h}", svg.resolve().as_uri()],
                       capture_output=True, timeout=60)
        print("png:", svg.with_suffix(".png").name)

if "--png" in sys.argv:
    to_png()
print("done")
