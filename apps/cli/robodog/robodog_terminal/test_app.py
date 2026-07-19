# file: robodog_terminal/test_app.py
"""
In-process tests for app.py: headless -p (text/json), --version, backend
selection, and a full scripted drive of the interactive REPL (slash commands,
! passthrough, plan approval, sessions, rewind) using the echo backend.
Also covers agents.py background mode + task_output.
Run: python robodog_terminal/test_app.py   (from robodogcli/robodog)
"""
from __future__ import annotations

import builtins
import contextlib
import io
import json
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import robodog_terminal.app as app_mod  # noqa: E402

ok = True


def check(cond, msg):
    global ok
    print(f"  [{'PASS' if cond else 'FAIL'}] {msg}")
    ok = ok and cond


def run_main(argv, inputs=None):
    """Run app_mod.main(argv) capturing stdout; feed scripted input()."""
    seq = iter(inputs or [])
    real_input = builtins.input

    def fake_input(prompt=""):
        try:
            return next(seq)
        except StopIteration:
            raise EOFError

    buf = io.StringIO()
    builtins.input = fake_input
    try:
        with contextlib.redirect_stdout(buf):
            code = app_mod.main(argv)
    finally:
        builtins.input = real_input
    return code, buf.getvalue()


def main() -> int:
    global ok
    wd = tempfile.mkdtemp(prefix="rd_app_")

    # ---------------- --version -----------------------------------------
    code, out = run_main(["--version"])
    check(code == 0 and "robodog-terminal" in out, "--version prints and exits 0")

    # ---------------- headless json --------------------------------------
    code, out = run_main(["--echo", "-p", "demo", "--output-format", "json",
                          "--cwd", wd])
    data = json.loads(out.strip().splitlines()[-1])
    check(code == 0 and data["iterations"] == 3 and "model" in data,
          "headless json: 3 demo iterations")
    check((Path(wd) / "demo.py").exists(), "headless run created demo.py")

    # ---------------- headless text --------------------------------------
    wd2 = tempfile.mkdtemp(prefix="rd_app2_")
    code, out = run_main(["--echo", "-p", "demo", "--cwd", wd2])
    check(code == 0 and "42" in out, "headless text prints final answer")

    # ---------------- tool gating flags -----------------------------------
    wd3 = tempfile.mkdtemp(prefix="rd_app3_")
    code, out = run_main(["--echo", "-p", "demo", "--cwd", wd3,
                          "--disallowed-tools", "bash,run_script",
                          "--no-instructions",
                          "--append-system-prompt", "extra rules"])
    check(code == 0, "disallowed-tools + append-system-prompt run completes")
    wd4 = tempfile.mkdtemp(prefix="rd_app4_")
    code, out = run_main(["--echo", "-p", "demo", "--cwd", wd4,
                          "--allowed-tools", "read_file,list_dir"])
    check(code == 0, "allowed-tools whitelist run completes")

    # ---------------- interactive REPL drive ------------------------------
    wd5 = tempfile.mkdtemp(prefix="rd_app5_")
    (Path(wd5) / "CLAUDE.md").write_text("Project rule: be nice.", encoding="utf-8")
    inputs = [
        "/help",
        "/status",
        "/context",
        "/tools",
        "/model",                # show
        "/model gpt-4o",         # live switch (echo backend rebuild)
        "/plan",                 # ON
        "plan something",        # agent turn in plan mode (echo final)
        "n",                     # reject plan
        "/plan",                 # OFF
        "/todos",
        "/tasks",
        "/tail",
        "/kill",                 # usage error
        "/kill bg99",            # unknown id
        "/rewind",               # nothing yet
        "/resume",               # list (session exists from plan turn)
        "/cwd",
        "/cwd Z:\\definitely_missing_dir",
        "! echo bang-works",
        "/model fresh-echo",     # rebuild client -> fresh demo script
        "run demo",              # real agent turn: write demo.py + bash + final
        "/rewind",               # now lists the checkpoint marker
        "/compact",              # summarizes via echo client
        "/clear",
        "/compact",              # nothing to compact
        "/resume latest",        # resume the saved session
        "/badcmd",
        "/exit",
    ]
    code, out = run_main(["--echo", "--cwd", wd5], inputs=inputs)
    check(code == 0, "interactive drive exits cleanly")
    check("Robodog Terminal" in out, "welcome banner shown")
    check("project instructions" in out, "CLAUDE.md loading announced")
    check("plan mode ON" in out and "plan mode OFF" in out, "/plan toggles")
    check("switched to" in out, "/model live switch")
    check("bang-works" in out, "! passthrough ran")
    check("no background tasks" in out, "/tasks empty listing")
    check("usage: /kill" in out, "/kill usage error")
    check("file change" in out or "checkpoints" in out, "/rewind lists checkpoints")
    check((Path(wd5) / "demo.py").exists(), "agent turn created demo.py")
    check("conversation compacted" in out, "/compact works")
    check("nothing to compact" in out, "/compact empty branch")
    check("resumed" in out, "/resume latest works")
    check("unknown command" in out, "unknown command error")
    check("transcript:" in out, "/context reports")

    # session actually persisted turns
    from robodog_terminal.sessions import SessionStore
    store = SessionStore(project_dir=str(Path(wd5).resolve()))
    sessions = store.list_sessions()
    check(len(sessions) >= 1 and sessions[0]["turn_count"] >= 2,
          f"session persisted with turns ({sessions and sessions[0]['turn_count']})")

    # ---------------- startup --continue + /bg + /init + approve-plan ----
    inputs2 = [
        "/bg investigate the demo",   # background subagent via command
        "/tasks",
        "/plan",
        "make another plan",          # plan turn (echo final)
        "y",                          # APPROVE -> implementation turn runs
        "/exit",
    ]
    code, out = run_main(["--echo", "--cwd", wd5, "--continue"], inputs=inputs2)
    check(code == 0, "second run exits cleanly")
    check("resumed session" in out, "--continue resumes previous session at startup")
    check("Started background subagent" in out or "bg1" in out,
          "/bg spawns background subagent")
    check("implementing" in out, "plan approval 'y' triggers implementation")

    wd6 = tempfile.mkdtemp(prefix="rd_app6_")
    code, out = run_main(["--echo", "--cwd", wd6, "--permission-mode", "plan"],
                         inputs=["/plan", "/exit"])
    check(code == 0 and "plan mode ON" in out,
          "--permission-mode plan starts read-only")

    code, out = run_main(["--echo", "--cwd", wd6, "--resume", "nonexistent-id"],
                         inputs=["/exit"])
    check("no session to resume" in out, "--resume with bad id falls back fresh")

    # ---------------- checkpoint prune + corrupt manifest ----------------
    from robodog_terminal.checkpoint import Checkpointer, MAX_SNAPSHOTS
    cw = Path(tempfile.mkdtemp(prefix="rd_ck_"))
    cp = Checkpointer(cw / "ck")
    (cw / "ck" / "manifest.jsonl").write_text('{"broken json\n', encoding="utf-8")
    cp2 = Checkpointer(cw / "ck")  # tolerant load
    check(cp2.markers() == {}, "checkpointer tolerates corrupt manifest line")
    f = cw / "many.txt"
    for i in range(MAX_SNAPSHOTS + 5):
        f.write_text(f"v{i}", encoding="utf-8")
        cp2.snapshot(f)
    live = [e for e in cp2._entries if e["snap"]]
    check(len(live) <= MAX_SNAPSHOTS, f"prune caps snapshots at {MAX_SNAPSHOTS}")

    # ---------------- background bash timeout path ------------------------
    from robodog_terminal.background import BackgroundManager as BM
    bm = BM()
    t0 = time.time()
    task = bm.spawn_bash("Start-Sleep -Seconds 30", str(cw), timeout=2)
    task.thread.join(timeout=15)
    check(task.status in ("done", "failed", "killed") and time.time() - t0 < 15,
          f"spawn_bash timeout enforced ({task.status})")

    # ---------------- agents.py background + task_output ------------------
    from robodog_terminal.tools import default_registry
    from robodog_terminal.llm_client import EchoClient
    from robodog_terminal.agents import register_agent_tool
    from robodog_terminal.background import BackgroundManager
    reg = default_registry(cwd=wd)
    mgr = BackgroundManager()
    register_agent_tool(reg, EchoClient(script=["child answer DONE-77"]),
                        manager=mgr)
    r = reg.execute("agent", {"prompt": "x", "type": "bogus"})
    check("unknown agent type" in r, "agent: unknown type error")
    r = reg.execute("agent", {"prompt": "solve it", "background": "true"})
    check("bg1" in r, "agent background spawns bg1")
    r = reg.execute("task_output", {"id": "bg1"})
    check("running" in r or "done" in r, "task_output while running/done")
    for _ in range(50):
        if mgr.get("bg1").status != "running":
            break
        time.sleep(0.1)
    r = reg.execute("task_output", {"id": "bg1"})
    check("done" in r and "DONE-77" in r, "task_output returns child result")
    check("no such task" in reg.execute("task_output", {"id": "bg9"}),
          "task_output unknown id")
    # no manager -> background refused
    reg2 = default_registry(cwd=wd)
    register_agent_tool(reg2, EchoClient(script=["x"]))
    r = reg2.execute("agent", {"prompt": "x", "background": "true"})
    check("unavailable" in r, "agent background without manager refused")
    check(reg2.get("task_output") is None, "task_output absent without manager")

    # ---- _normalize_model_id --------------------------------------------
    n = app_mod._normalize_model_id
    check(n("anthropic/claude-opus-4-8") == "anthropic/claude-opus-4.8",
          "model id: dashed anthropic version -> dotted")
    check(n("anthropic/claude-opus-4-8   # switch live") == "anthropic/claude-opus-4.8",
          "model id: inline # comment stripped")
    check(n("anthropic/claude-sonnet-4-6") == "anthropic/claude-sonnet-4.6",
          "model id: sonnet dashed -> dotted")
    check(n("anthropic/claude-opus-4.8") == "anthropic/claude-opus-4.8",
          "model id: already-dotted unchanged")
    check(n("openai/gpt-4o") == "openai/gpt-4o", "model id: non-anthropic untouched")
    check(n("'gpt-4o'") == "gpt-4o", "model id: surrounding quotes stripped")
    check(n("anthropic/claude-opus-4.8-fast") == "anthropic/claude-opus-4.8-fast",
          "model id: -fast suffix preserved")

    print("\nAPP:", "ALL PASS" if ok else "FAILURES")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
