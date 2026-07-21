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
        "/stats",
        "/net-writes",           # show current mode
        "/net-writes allow",     # switch mode at runtime
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
        "/verbose",              # ON
        "/verbose",              # OFF
        "/test agents 3 big",    # aggressive subagent-path probe (echo backend)
        "! echo bang-works",
        "/model fresh-echo",     # rebuild client -> fresh demo script
        "run demo",              # real agent turn: write demo.py + bash + final
        "/copy",                 # copy the last answer to the clipboard
        "/save answer.txt",      # write the last answer to a file
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
    check("session stats" in out and "uptime" in out, "/stats shows a session summary")
    check("est. cost:" in out, "/stats shows an estimated cost line")
    check("saved the last answer to" in out and (Path(wd5) / "answer.txt").exists(),
          "/save writes the last answer to a file")
    check("copied the last answer" in out or "clipboard" in out,
          "/copy reports copying the last answer (or a clipboard-tool note)")
    check("network-write guard" in out and "set to 'allow'" in out,
          "/net-writes shows current mode and switches at runtime")
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
    check("verbose output ON" in out and "verbose output OFF" in out,
          "/verbose toggles on and off")
    check("subagents ok" in out and "3/3" in out and "per-agent" in out
          and "big prompt" in out,
          "/test agents N big runs a sized fan-out and reports N/N ok + timing stats")

    # ---- /rewind is atomic: reverts files AND the transcript (5.6) --------
    wd6 = tempfile.mkdtemp(prefix="rd_app_rewind_")
    code, out = run_main(["--echo", "--cwd", wd6],
                         inputs=["build the demo", "/rewind 0", "/exit"])
    check(code == 0, "rewind drive exits cleanly")
    check(not (Path(wd6) / "demo.py").exists(),
          "/rewind 0 deleted the created demo.py")
    check("dropped" in out and "conversation turn" in out,
          "/rewind also rewinds the conversation transcript (files+context atomic)")

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

    # ---- --model is normalized at STARTUP too (not just /model) ----------
    import os as _os
    import types as _types
    _dash_args = _types.SimpleNamespace(
        echo=False, backend="openrouter", model="anthropic/claude-sonnet-4-6")
    _saved_key = _os.environ.get("ROBODOG_LLM_KEY")
    _os.environ["ROBODOG_LLM_KEY"] = "test-key-not-real"
    try:
        client, label = app_mod.build_backend(_dash_args)
        check(getattr(client, "model", "") == "anthropic/claude-sonnet-4.6",
              "build_backend normalizes a dashed --model at startup")
        check("4.6" in label, "backend label shows the normalized id")
    finally:
        if _saved_key is None:
            _os.environ.pop("ROBODOG_LLM_KEY", None)
        else:
            _os.environ["ROBODOG_LLM_KEY"] = _saved_key

    # ---- custom KeePass entry title + user:pass key join -----------------
    # For gateways like SEMOSS/ELSA: point at an existing entry and join
    # access:secret from its username/password fields.
    _kp_saved = app_mod._load_keepass_entry
    _clear = ["ROBODOG_LLM_KEY", "ROBODOG_LLM_URL", "ROBODOG_KEEPASS_LLM_ENTRY",
              "ROBODOG_LLM_KEY_FORMAT"]
    _saved_env = {k: _os.environ.get(k) for k in _clear}

    def _restore_env():
        for k, v in _saved_env.items():
            if v is None:
                _os.environ.pop(k, None)
            else:
                _os.environ[k] = v

    def _fake_kp(title):
        if title == "SEMOSS-Elsa-Dev":
            return ("ACCESS-ID", "SECRET", "https://elsa.example/Monolith/api/model/openai")
        if title == "OpenAI":
            return ("robodog", "sk-plain", "https://api.openai.com/v1")
        return (None, None, None)

    try:
        app_mod._load_keepass_entry = _fake_kp
        _oa_args = _types.SimpleNamespace(echo=False, backend="openai", model="engine-x")
        for k in _clear:
            _os.environ.pop(k, None)

        _os.environ["ROBODOG_KEEPASS_LLM_ENTRY"] = "SEMOSS-Elsa-Dev"
        _os.environ["ROBODOG_LLM_KEY_FORMAT"] = "user:pass"
        client, _ = app_mod.build_backend(_oa_args)
        check(client.api_key == "ACCESS-ID:SECRET",
              "custom entry + user:pass joins access:secret from the vault")
        check("elsa.example" in client.url,
              "base URL taken from the custom entry's URL field")

        # default OpenAI entry is unaffected — no spurious username join
        for k in _clear:
            _os.environ.pop(k, None)
        client, _ = app_mod.build_backend(_oa_args)
        check(client.api_key == "sk-plain",
              "default entry key unchanged when no format/entry override set")
    finally:
        app_mod._load_keepass_entry = _kp_saved
        _restore_env()

    # ---- _hard_quit: clean return normally, os._exit when threads block --
    import threading as _threading
    # (a) nothing blocking -> returns the code, does NOT call os._exit
    _saved_exit = _os._exit
    called = {"code": None}
    _os._exit = lambda c: called.__setitem__("code", c)
    try:
        rc = app_mod._hard_quit(ui=None, code=0)
        check(rc == 0 and called["code"] is None,
              "_hard_quit returns cleanly when no non-daemon threads block exit")

        # (b) a live non-daemon thread present -> os._exit IS invoked
        gate = _threading.Event()
        blocker = _threading.Thread(target=lambda: gate.wait(5), daemon=False)
        blocker.start()
        try:
            # give it a moment to be enumerable
            time.sleep(0.05)
            app_mod._hard_quit(ui=None, code=0)
            check(called["code"] == 0,
                  "_hard_quit calls os._exit when a non-daemon thread would block")
        finally:
            gate.set()
            blocker.join(timeout=5)
    finally:
        _os._exit = _saved_exit

    # ---------- /btw side-question prompt builder --------------------------
    # /btw asks the model a question WITHOUT touching the conversation. Mid-turn
    # use (running=True) tells the model the session may still be working, so
    # "are you stuck?" gets a sensible answer. The convo + question are embedded.
    p = app_mod.build_btw_prompt("USER: fix the bug\nASSISTANT: on it", "are you stuck?")
    check("SIDE QUESTION" in p, "btw prompt frames it as a side question")
    check("fix the bug" in p and "are you stuck?" in p,
          "btw prompt embeds the conversation and the question")
    check("Do NOT use tools" in p, "btw prompt forbids tool calls")
    check("STILL BE RUNNING" not in p, "non-running btw prompt omits the running note")
    p_run = app_mod.build_btw_prompt("USER: build it", "are you stuck?", running=True)
    check("STILL BE RUNNING" in p_run,
          "mid-turn btw prompt tells the model the session may still be running")

    # "btw" is in the mid-turn-safe command set so it works while an agent runs.
    src = Path(app_mod.__file__).read_text(encoding="utf-8")
    check('"btw"' in src and "SAFE_MIDTURN" in src, "btw registered for mid-turn use")

    print("\nAPP:", "ALL PASS" if ok else "FAILURES")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
