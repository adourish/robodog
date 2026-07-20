# file: robodog_terminal/test_turnrunner.py
"""
Tests for TurnRunner — threaded agent turns with cancel / background / queued
input, driven by an injected key source (no real terminal needed).
Run: python robodog_terminal/test_turnrunner.py   (from robodogcli/robodog)
"""
from __future__ import annotations

import sys
import tempfile
import threading
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from robodog_terminal.turnrunner import TurnRunner, TurnOutcome, make_key_source  # noqa: E402
from robodog_terminal.llm_client import EchoClient                                # noqa: E402
from robodog_terminal.tools import default_registry                               # noqa: E402
from robodog_terminal.loop import AgentLoop                                       # noqa: E402

ok = True


def check(cond, msg):
    global ok
    print(f"  [{'PASS' if cond else 'FAIL'}] {msg}")
    ok = ok and cond


def mk_loop(script, cwd, slow_tool=False):
    return AgentLoop(EchoClient(script=script), default_registry(cwd=cwd))


def main() -> int:
    global ok
    wd = tempfile.mkdtemp(prefix="rd_turn_")

    # ---------------- normal completion ----------------------------------
    loop = mk_loop(["all done, nothing to do"], wd)
    r = TurnRunner(loop)
    r.start("hi", threading.Event())
    out = r.watch(lambda: None)   # no keys -> runs to completion
    check(out.status == "done", "turn completes with status done")
    check(out.result is not None and "done" in out.result.final_text,
          "done outcome carries the LoopResult")
    check(not r.running(), "runner not running after completion")

    # ---------------- queued input during a turn -------------------------
    # A loop that takes a few polls: emit one tool call then finish. We feed
    # an ('input', line) before it finishes; it must be queued, not lost.
    call = '<tool name="list_dir"></tool>'
    loop = mk_loop([call, "finished"], wd)
    r = TurnRunner(loop)
    r.start("go", threading.Event())
    fed = {"done": False}
    def ks_queue():
        if not fed["done"]:
            fed["done"] = True
            return ("input", "follow-up question")
        return None
    out = r.watch(ks_queue, poll=0.005)
    check(out.status == "done", "turn with queued input still completes")
    check(out.queued == ["follow-up question"], "queued input captured")

    # empty queued line is ignored
    loop = mk_loop(["ok"], wd)
    r = TurnRunner(loop)
    r.start("go", threading.Event())
    sent = {"n": 0}
    def ks_empty():
        sent["n"] += 1
        return ("input", "") if sent["n"] == 1 else None
    out = r.watch(ks_empty, poll=0.005)
    check(out.queued == [], "empty queued line ignored")

    # ---------------- cancel ---------------------------------------------
    # A loop that would run many iterations; we cancel immediately.
    alt = ['<tool name="list_dir"><param name="path">.</param></tool>'] * 50
    loop = mk_loop(alt, wd)
    ev = threading.Event()
    r = TurnRunner(loop)
    r.start("loop", ev)
    out = r.watch(lambda: "cancel", poll=0.005)
    check(out.status == "cancelled", "cancel returns cancelled outcome")
    check(ev.is_set(), "cancel set the cancel_event")
    check(not r.running(), "runner stopped after cancel")

    # KeyboardInterrupt from key_source is treated as cancel
    loop = mk_loop(alt, wd)
    ev = threading.Event()
    r = TurnRunner(loop)
    r.start("loop", ev)
    def ks_kbint():
        raise KeyboardInterrupt
    out = r.watch(ks_kbint, poll=0.005)
    check(out.status == "cancelled", "KeyboardInterrupt in key source -> cancel")

    # ---------------- background (detach) --------------------------------
    # Long-ish loop; background it, then join separately.
    # A gated loop blocks until the test releases it, so backgrounding is
    # deterministic (no race with completion, no circuit-breaker involvement).
    class _Result:
        final_text = "eventually done"
        iterations = 1
        total_tokens = 1
        turns = []

    class GatedLoop(AgentLoop):
        def __init__(self, gate):
            super().__init__(EchoClient(), default_registry(cwd=wd))
            self._gate = gate

        def run(self, prompt):
            self._gate.wait(timeout=5)   # stay "running" until released
            return _Result()

    gate = threading.Event()
    loop = GatedLoop(gate)
    r = TurnRunner(loop)
    r.start("long", threading.Event())
    out = r.watch(lambda: "background", poll=0.005)
    check(out.status == "backgrounded", "background returns backgrounded outcome")
    check(out.result is None, "backgrounded outcome has no result yet")
    check(r.running(), "backgrounded turn is still running after detach")
    gate.set()                            # let it finish
    check(r.join(timeout=10), "backgrounded turn finishes when joined")
    check(r.result is not None and "eventually done" in r.result.final_text,
          "result available after background turn completes")

    # ---------------- worker exception surfaces --------------------------
    class Boom(AgentLoop):
        def run(self, prompt):
            raise RuntimeError("kaboom")
    bl = Boom(EchoClient(), default_registry(cwd=wd))
    r = TurnRunner(bl)
    r.start("x", threading.Event())
    raised = False
    try:
        r.watch(lambda: None)
    except RuntimeError as exc:
        raised = "kaboom" in str(exc)
    check(raised, "worker exception re-raised by watch")

    # ---------------- double Ctrl+C: second interrupt force-exits ---------
    # First Ctrl+C -> graceful cancel (set the event, wait for the worker). A
    # SECOND Ctrl+C during that wait must PROPAGATE so the app can force-quit,
    # rather than crashing or hanging. Construct the cancel-wait scenario
    # directly: a runner whose turn hasn't finished (_done not set), whose
    # done-wait raises KeyboardInterrupt (the second Ctrl+C).
    class _FakeLoop:
        def __init__(self):
            self.cancel_event = threading.Event()
    rH = TurnRunner(_FakeLoop())
    rH._thread = threading.Thread(target=lambda: None)  # looks "started"
    # _done is a fresh, UNSET Event -> watch reaches the cancel path
    rH._done.wait = lambda timeout=None: (_ for _ in ()).throw(KeyboardInterrupt())
    propagated = False
    try:
        rH.watch(lambda: "cancel")
    except KeyboardInterrupt:
        propagated = True
    check(propagated, "second Ctrl+C during cancel-wait propagates (force-exit)")
    check(rH.loop.cancel_event.is_set(),
          "cancel_event still set on the force-exit path")

    # single cancel path is unaffected: returns a cancelled outcome, no raise
    loopS = mk_loop(alt, wd)
    rS = TurnRunner(loopS)
    rS.start("go", threading.Event())
    out = rS.watch(lambda: "cancel", poll=0.005)
    check(out.status == "cancelled",
          "single cancel still returns a cancelled outcome (no raise)")

    # ---------------- make_key_source: safe no-op off a TTY --------------
    ks = make_key_source()
    check(ks() is None, "make_key_source is a no-op when stdin is not a TTY")
    ks2 = make_key_source(ui=object())  # ui arg accepted, still no-op off a TTY
    check(ks2() is None, "make_key_source(ui=...) still no-ops off a TTY")

    # ---------------- UI mid-turn typing: spinner suppression ------------
    # The fragmentation bug is a Live spinner repainting over raw keystrokes;
    # the fix is UI._typing gating spinner_start. Exercise that contract.
    from robodog_terminal.ui import UI
    tui = UI(model_name="m", cwd=str(Path(tempfile.gettempdir())))
    tui.console = None
    tui.mid_input_start()
    check(tui._typing is True, "mid_input_start marks typing active")
    tui.spinner_start("Thinking…")
    check(tui._status is None, "spinner suppressed while the user is typing")
    tui.mid_input_end()
    check(tui._typing is False, "mid_input_end clears the typing flag")
    tui.reset_typing()
    check(tui._typing is False, "reset_typing is idempotent")

    print("\nTURNRUNNER:", "ALL PASS" if ok else "FAILURES")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
