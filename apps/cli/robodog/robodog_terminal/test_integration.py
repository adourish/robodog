# file: robodog_terminal/test_integration.py
"""
Integration tests for terminal-mode features wired in app.py:
plan mode, @-file mentions, background-bash hook, session round-trip,
ask-user tool via registry, task checklist rendering, headless plumbing.
Run: python robodog_terminal/test_integration.py   (from robodogcli/robodog)
"""
from __future__ import annotations

import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from robodog_terminal.tools import default_registry            # noqa: E402
from robodog_terminal.llm_client import EchoClient             # noqa: E402
from robodog_terminal.loop import AgentLoop                    # noqa: E402
from robodog_terminal.background import BackgroundManager      # noqa: E402
from robodog_terminal.tasklist import (TaskChecklist,          # noqa: E402
                               register_task_tools, register_ask_tool)

ok = True


def check(cond, msg):
    global ok
    print(f"  [{'PASS' if cond else 'FAIL'}] {msg}")
    ok = ok and cond


def main() -> int:
    wd = Path(tempfile.mkdtemp(prefix="rd_integ_"))

    # ---------------- plan mode -----------------------------------------
    reg = default_registry(cwd=str(wd))
    reg.mode = "plan"
    r = reg.execute("write_file", {"path": "x.txt", "content": "hi"})
    check(r.startswith("ERROR") and "plan mode" in r, "plan mode blocks write_file")
    r = reg.execute("bash", {"command": "echo hi"})
    check(r.startswith("ERROR") and "plan mode" in r, "plan mode blocks bash")
    r = reg.execute("list_dir", {})
    check(not r.startswith("ERROR"), "plan mode allows read tools")
    check("PLAN MODE IS ACTIVE" in reg.catalog(), "catalog announces plan mode")
    reg.mode = "yolo"
    r = reg.execute("write_file", {"path": "x.txt", "content": "hi"})
    check("Created" in r, "yolo mode allows write again")
    check("PLAN MODE" not in reg.catalog(), "catalog note removed in yolo")

    # ---------------- @-mentions ----------------------------------------
    from robodog_terminal.app import _expand_mentions
    (wd / "notes.txt").write_text("SECRET-MARKER-42", encoding="utf-8")
    msg = _expand_mentions("please look at @notes.txt and fix", reg)
    check("SECRET-MARKER-42" in msg, "@-mention inlines file content")
    check(str(wd / "notes.txt") in reg.read_paths, "@-mention marks file as read")
    msg2 = _expand_mentions("no mention here", reg)
    check(msg2 == "no mention here", "no-mention message unchanged")
    msg3 = _expand_mentions("bad @missing_file.xyz ref", reg)
    check(msg3 == "bad @missing_file.xyz ref", "missing file mention ignored")

    # ---------------- background bash via hook ---------------------------
    mgr = BackgroundManager()
    reg.background_spawn = lambda cmd, cwd: (
        f"Started background task {mgr.spawn_bash(cmd, cwd).id}.")
    r = reg.execute("bash", {"command": "echo bg-line-works", "background": "true"})
    check("Started background task bg1" in r, "bash background=true spawns via manager")
    for _ in range(50):
        if mgr.get("bg1").status != "running":
            break
        time.sleep(0.1)
    check("bg-line-works" in mgr.output("bg1"), "background bash output captured")
    reg.background_spawn = None
    r = reg.execute("bash", {"command": "echo x", "background": "true"})
    check(r.startswith("ERROR"), "background without manager returns stub error")

    # ---------------- sessions round-trip --------------------------------
    from robodog_terminal.sessions import SessionStore
    store = SessionStore(project_dir=str(wd), base_dir=str(wd / ".sess"))
    sid = store.new_session()
    store.append_turn(sid, "user", "hello world")
    store.append_turn(sid, "assistant", "hi there")
    store.append_turn(sid, "tool", "$ echo hi", tool_name="bash")
    data = store.load(sid)
    check(data is not None and len(data["turns"]) == 3, "session stores 3 turns")
    check(data["turns"][2]["tool_name"] == "bash", "tool_name round-trips")
    check(store.latest() == sid, "latest() finds the session")
    listing = store.list_sessions()
    check(listing and listing[0]["first_prompt"].startswith("hello world"),
          "list_sessions shows first prompt")

    # resume into a fresh loop (as /resume does)
    from robodog_terminal.loop import Turn
    loop = AgentLoop(EchoClient(), default_registry(cwd=str(wd)))
    for t in data["turns"]:
        loop.history.append(Turn(t["role"], t["content"],
                                 tool_name=t.get("tool_name", "")))
    check(len(loop.history) == 3 and loop.history[0].content == "hello world",
          "resume rebuilds loop history")

    # ---------------- checklist + ask tools on a real registry -----------
    reg2 = default_registry(cwd=str(wd))
    cl = TaskChecklist()
    register_task_tools(reg2, cl)
    register_ask_tool(reg2, lambda q, opts: opts[-1])
    reg2.execute("task_add", {"subjects": "step one\nstep two"})
    reg2.execute("task_update", {"id": "1", "status": "completed"})
    lines = cl.render_lines()
    check(lines[0].startswith("[x]") and lines[1].startswith("[ ]"),
          "checklist renders statuses")
    r = reg2.execute("ask_user", {"question": "Which?", "options": "A|B|C"})
    check(r == "User chose: C", "ask_user returns injected choice")

    # ---------------- doctor runs clean ----------------------------------
    from robodog_terminal.doctor import run_doctor, format_report
    results = run_doctor(str(wd))
    check(len(results) >= 10, f"doctor runs {len(results)} checks")
    rep = format_report(results)
    check("ok" in rep.lower() and not any(
        "sk-" in r.detail for r in results), "doctor report clean, no secrets")

    print("\nINTEGRATION:", "ALL PASS" if ok else "FAILURES")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
