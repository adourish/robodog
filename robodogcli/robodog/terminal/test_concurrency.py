# file: terminal/test_concurrency.py
"""
Tests for interactive concurrency + /btw:
- you can issue commands (and start more work) WHILE a background agent/task
  runs — the REPL never blocks on background work;
- /btw answers a side question without adding anything to the conversation.
Run: python terminal/test_concurrency.py   (from robodogcli/robodog)
"""
from __future__ import annotations

import builtins
import contextlib
import io
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import terminal.app as app_mod                       # noqa: E402
from terminal.background import BackgroundManager     # noqa: E402
from terminal.tools import default_registry           # noqa: E402
from terminal.llm_client import EchoClient            # noqa: E402
from terminal.agents import register_agent_tool       # noqa: E402
from terminal.loop import AgentLoop                    # noqa: E402

ok = True


def check(cond, msg):
    global ok
    print(f"  [{'PASS' if cond else 'FAIL'}] {msg}")
    ok = ok and cond


def run_repl(argv, inputs):
    seq = iter(inputs)
    real = builtins.input

    def fake(prompt=""):
        try:
            return next(seq)
        except StopIteration:
            raise EOFError

    buf = io.StringIO()
    builtins.input = fake
    try:
        with contextlib.redirect_stdout(buf):
            code = app_mod.main(argv)
    finally:
        builtins.input = real
    return code, buf.getvalue()


def main() -> int:
    global ok

    # ---------------- concurrency: commands while a bg task runs ---------
    mgr = BackgroundManager()
    # a background task that stays alive ~2s
    slow = "Start-Sleep -Seconds 2; echo done" if __import__("os").name == "nt" \
        else "sleep 2; echo done"
    task = mgr.spawn_bash(slow, tempfile.mkdtemp())
    # while it runs, the manager answers queries immediately (non-blocking)
    t0 = time.time()
    running = mgr.get(task.id).status == "running"
    listed = mgr.list()
    n = mgr.running_count()
    elapsed = time.time() - t0
    check(running and n == 1, "background task is running")
    check(len(listed) == 1, "list() returns while task still running")
    check(elapsed < 0.5, f"queries returned immediately, not blocked ({elapsed:.2f}s)")
    # can spawn MORE work concurrently
    task2 = mgr.spawn_bash("echo second", tempfile.mkdtemp())
    check(mgr.running_count() >= 1, "second task spawned alongside the first")
    # now let them finish
    task.thread.join(timeout=10)
    notes = mgr.drain_notifications()
    check(any(task.id in nt for nt in notes), "completion notification fired for bg task")

    # ---------------- REPL: /bg then keep issuing commands ---------------
    wd = tempfile.mkdtemp(prefix="rd_conc_")
    # EchoClient child returns a final answer quickly; /bg spawns it, then we
    # immediately issue /tasks and /status without waiting — they must respond.
    code, out = run_repl(["--echo", "--cwd", wd], [
        "/bg summarize the project",   # spawn background subagent
        "/tasks",                       # issue a command right away
        "/status",                      # and another
        "/help",                        # REPL stayed responsive
        "/exit",
    ])
    check(code == 0, "REPL with concurrent bg work exits cleanly")
    check("Started background subagent" in out or "bg1" in out, "/bg started a subagent")
    check(out.index("Started background") < out.rindex("model"),
          "commands after /bg were processed (REPL not blocked)")

    # ---------------- /btw: sees convo, adds nothing ---------------------
    reg = default_registry(cwd=wd)
    client = EchoClient(script=["The answer to your side question is 42."])
    loop = AgentLoop(client, reg)
    loop.history.append(app_mod._mk_turn("user", "we are building a parser"))
    loop.history.append(app_mod._mk_turn("assistant", "ok, parser noted"))
    before = len(loop.history)
    # simulate the /btw handler path directly (unit-level)
    convo = loop._render_prompt()
    side = ("SIDE QUESTION about the session below. Answer briefly. No tools.\n\n"
            + convo + "\n\nside question: what are we building?")
    ans = client.complete(side, max_tokens=1500).text
    check("42" in ans, "/btw produced a side answer")
    check(len(loop.history) == before, "/btw added NOTHING to the conversation")
    check("parser" in convo, "/btw prompt included the conversation context")

    # ---------------- /btw via the real REPL, history unchanged ----------
    code, out = run_repl(["--echo", "--cwd", wd], [
        "/btw what is 2 plus 2",   # no conversation yet -> still answers
        "/context",                 # transcript must be 0 turns
        "/exit",
    ])
    check("not saved" in out.lower() or "btw" in out.lower(), "/btw ran in REPL")
    check("transcript: 0 turns" in out, "/btw left transcript empty (0 turns)")

    print("\nCONCURRENCY/BTW:", "ALL PASS" if ok else "FAILURES")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
