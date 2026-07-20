# file: robodog_terminal/test_sticky_input.py
"""
Tests for UI.watch_turn_sticky() — the opt-in Claude Code-style fixed bottom
input (ROBODOG_STICKY_INPUT=1). Drives a REAL prompt_toolkit Application via
pipe_input + DummyOutput, so the cross-thread "close the prompt when the turn
finishes" signaling (app.exit via call_soon_threadsafe) is exercised for real.
Run: python robodog_terminal/test_sticky_input.py   (from robodogcli/robodog)
"""
from __future__ import annotations

import contextvars
import sys
import threading
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from prompt_toolkit import PromptSession                        # noqa: E402
from prompt_toolkit.application import create_app_session       # noqa: E402
from prompt_toolkit.input import create_pipe_input              # noqa: E402
from prompt_toolkit.output import DummyOutput                    # noqa: E402
from robodog_terminal.ui import UI, _input_key_bindings          # noqa: E402

ok = True


def check(cond, msg):
    global ok
    print(f"  [{'PASS' if cond else 'FAIL'}] {msg}")
    ok = ok and cond


class FakeLoop:
    def __init__(self):
        self.cancel_event = threading.Event()


class FakeRunner:
    def __init__(self, run_seconds=0.3):
        self.loop = FakeLoop()
        self.queued = []
        self.result = "RESULT"
        self.error = None
        self._done = threading.Event()
        threading.Thread(target=self._work, args=(run_seconds,), daemon=True).start()

    def _work(self, secs):
        time.sleep(secs)
        self._done.set()

    def running(self):
        return not self._done.is_set()

    def join(self, timeout=None):
        return self._done.wait(timeout)


def make_ui(pi):
    ui = UI(model_name="test/model", cwd=str(Path.cwd()))
    ui._session = PromptSession(input=pi, output=DummyOutput(),
                               key_bindings=_input_key_bindings(), multiline=True)
    return ui


def run_in_ctx(fn):
    ctx = contextvars.copy_context()
    th = threading.Thread(target=lambda: ctx.run(fn))
    th.start()
    return th


def main() -> int:
    global ok

    # ---- prompt closes itself when the turn finishes (nothing typed) -----
    with create_pipe_input() as pi, create_app_session(input=pi, output=DummyOutput()):
        ui = make_ui(pi)
        runner = FakeRunner(run_seconds=0.15)
        t0 = time.time()
        outcome = ui.watch_turn_sticky(runner)
        dt = time.time() - t0
        check(outcome.status == "done", "sticky: auto-closes 'done' when the turn finishes")
        check(dt < 3.0, f"sticky: returns promptly after completion ({dt:.2f}s)")
        check(ui._typing is False, "sticky: typing flag cleared after the turn")

    # ---- a typed line is queued; turn completion still closes the prompt --
    box = {}
    with create_pipe_input() as pi, create_app_session(input=pi, output=DummyOutput()):
        ui = make_ui(pi)
        runner = FakeRunner(run_seconds=0.5)
        th = run_in_ctx(lambda: box.__setitem__("o", ui.watch_turn_sticky(runner)))
        time.sleep(0.1)
        pi.send_text("follow-up\r")
        th.join(timeout=6)
        o = box.get("o")
        check(o is not None and not th.is_alive(), "sticky: returned, no hang after a typed line")
        check(o is not None and o.status == "done", "sticky: typed line still ends 'done'")
        check(o is not None and o.queued == ["follow-up"], "sticky: typed follow-up queued")

    # ---- Ctrl+B backgrounds; the turn keeps running ----------------------
    box = {}
    with create_pipe_input() as pi, create_app_session(input=pi, output=DummyOutput()):
        ui = make_ui(pi)
        runner = FakeRunner(run_seconds=5)
        th = run_in_ctx(lambda: box.__setitem__("o", ui.watch_turn_sticky(runner)))
        time.sleep(0.1)
        pi.send_text("\x02")   # Ctrl+B
        th.join(timeout=6)
        o = box.get("o")
        check(o is not None and not th.is_alive(), "sticky: Ctrl+B returns promptly")
        check(o is not None and o.status == "backgrounded", "sticky: Ctrl+B backgrounds the turn")
        check(runner.running(), "sticky: backgrounded turn keeps running")

    # ---- a mid-turn command runs in-place and is NOT queued --------------
    box = {}
    ran = []
    def _on_cmd(line):
        if line.startswith("/doctor"):
            ran.append(line)
            return True          # handled -> not queued
        return False
    with create_pipe_input() as pi, create_app_session(input=pi, output=DummyOutput()):
        ui = make_ui(pi)
        runner = FakeRunner(run_seconds=0.5)
        th = run_in_ctx(lambda: box.__setitem__(
            "o", ui.watch_turn_sticky(runner, on_command=_on_cmd)))
        time.sleep(0.1)
        pi.send_text("/doctor\r")          # a command -> runs in place
        time.sleep(0.1)
        pi.send_text("real follow-up\r")   # a normal line -> queued
        th.join(timeout=6)
        o = box.get("o")
        check(ran == ["/doctor"], "sticky: /doctor ran in-place mid-turn")
        check(o is not None and o.queued == ["real follow-up"],
              "sticky: command NOT queued; the plain line IS queued")

    # ---- non-interactive (no session): just waits, returns done ----------
    ui = UI(model_name="m", cwd=str(Path.cwd()))
    ui._session = None
    runner = FakeRunner(run_seconds=0.1)
    o = ui.watch_turn_sticky(runner)
    check(o.status == "done" and o.result == "RESULT",
          "sticky: non-interactive path waits and returns done")

    print("\nSTICKY INPUT:", "ALL PASS" if ok else "FAILURES")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
