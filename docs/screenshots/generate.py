# file: docs/screenshots/generate.py
"""
Regenerate the README screenshots. Every scene is rendered by the REAL UI
code (rich SVG export) driving real components — no mockups. Run after
changing anything in robodog_terminal/ui.py so the docs stay honest:

    python docs/screenshots/generate.py

Then convert SVG -> PNG (headless Chrome):

    python docs/screenshots/generate.py --png
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
