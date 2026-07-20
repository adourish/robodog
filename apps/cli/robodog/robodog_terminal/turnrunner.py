# file: robodog_terminal/turnrunner.py
"""
Run one agent turn in a worker thread so the REPL stays responsive while the
agent works — the basis for agentic mid-turn interactivity:

  * Ctrl+C  -> cancel the turn (sets the loop's cancel_event)
  * Ctrl+B  -> background it: stop watching and return to the prompt; the turn
               keeps running and reports when it finishes
  * type + Enter during the turn -> the line is QUEUED and run after the turn

The threading/queue mechanism lives here (fully unit-testable via an injected
key source); the raw-key reading lives in app.py's key adapter.
"""
from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from typing import Any, Callable, List, Optional

# A key source is a zero-arg callable polled during the turn. It returns:
#   None                 -> nothing happened
#   "cancel"             -> cancel the running turn
#   "background"         -> detach (leave the turn running)
#   ("input", "<line>")  -> the user queued a follow-up prompt
KeySource = Callable[[], Any]


@dataclass
class TurnOutcome:
    status: str                       # "done" | "cancelled" | "backgrounded"
    result: Any = None                # LoopResult for done/cancelled
    queued: List[str] = field(default_factory=list)  # follow-ups typed during turn


class TurnRunner:
    def __init__(self, loop):
        self.loop = loop
        self._thread: Optional[threading.Thread] = None
        self._done = threading.Event()
        self._result = None
        self._error: Optional[BaseException] = None
        self.queued: List[str] = []

    def running(self) -> bool:
        return self._thread is not None and not self._done.is_set()

    def start(self, prompt: str, cancel_event: threading.Event) -> None:
        """Launch the turn in a daemon thread against loop.run(prompt)."""
        self.loop.cancel_event = cancel_event
        self._done.clear()
        self._result = None
        self._error = None
        self.queued = []

        def _work():
            try:
                self._result = self.loop.run(prompt)
            except BaseException as exc:  # captured, re-raised to the watcher
                self._error = exc
            finally:
                self._done.set()

        self._thread = threading.Thread(target=_work, daemon=True)
        self._thread.start()

    def watch(self, key_source: KeySource, poll: float = 0.03) -> TurnOutcome:
        """
        Block until the turn finishes OR the user backgrounds it. Follow-up
        inputs are accumulated into `queued`. Re-raises a worker exception.
        """
        cancel_event = self.loop.cancel_event
        while True:
            if self._done.is_set():
                if self._error is not None:
                    raise self._error
                return TurnOutcome("done", self._result, list(self.queued))
            try:
                act = key_source()
            except KeyboardInterrupt:
                act = "cancel"
            if act == "cancel":
                if cancel_event is not None:
                    cancel_event.set()
                self._done.wait(timeout=15)
                return TurnOutcome("cancelled", self._result, list(self.queued))
            if act == "background":
                return TurnOutcome("backgrounded", None, list(self.queued))
            if isinstance(act, tuple) and len(act) == 2 and act[0] == "input":
                if act[1]:
                    self.queued.append(act[1])
            time.sleep(poll)

    def join(self, timeout: Optional[float] = None) -> bool:
        """Wait for a (possibly backgrounded) turn to finish. Returns done-ness."""
        return self._done.wait(timeout)

    @property
    def result(self):
        return self._result

    @property
    def error(self):
        return self._error


def make_key_source(ui=None) -> KeySource:
    """
    Raw single-key reader for use during a turn (no prompt_toolkit active here).
    Windows: msvcrt; POSIX: select + cbreak. Ctrl+B -> background, Ctrl+C ->
    cancel, printable chars build a line submitted on Enter. Returns a no-op
    source when stdin is not a usable TTY (tests, pipes, headless).

    `ui` (optional): when given, keystrokes are echoed through its
    mid_input_* methods, which stop the Live spinner first so typed text isn't
    fragmented onto one-char-per-line by the spinner's repaint. Without a ui,
    falls back to raw stdout echo (old behavior).
    """
    import os
    import sys

    if not sys.stdin.isatty():
        return lambda: None

    buf: List[str] = []
    started = [False]   # whether the current line's mid_input_start() has fired

    def _begin():
        if not started[0]:
            started[0] = True
            if ui is not None:
                ui.mid_input_start()

    def _echo(ch: str):
        if ui is not None:
            ui.mid_input_echo(ch)
        else:
            sys.stdout.write(ch)
            sys.stdout.flush()

    def _backspace():
        if ui is not None:
            ui.mid_input_backspace()
        else:
            sys.stdout.write("\b \b")
            sys.stdout.flush()

    def _submit():
        line = "".join(buf).strip()
        buf.clear()
        if started[0]:
            started[0] = False
            if ui is not None:
                ui.mid_input_end()
            else:
                sys.stdout.write("\n")
                sys.stdout.flush()
        return ("input", line)

    if os.name == "nt":
        import msvcrt

        def _src():
            if not msvcrt.kbhit():
                return None
            ch = msvcrt.getwch()
            if ch == "\x02":            # Ctrl+B
                return "background"
            if ch == "\x03":            # Ctrl+C
                return "cancel"
            if ch in ("\r", "\n"):
                return _submit()
            if ch in ("\x08", "\x7f"):  # backspace
                if buf:
                    buf.pop()
                    _backspace()
                return None
            if ch == "\x00" or ch == "\xe0":  # function/arrow prefix — consume next
                if msvcrt.kbhit():
                    msvcrt.getwch()
                return None
            _begin()
            buf.append(ch)
            _echo(ch)
            return None

        return _src

    # POSIX best-effort
    import select

    def _src():
        r, _, _ = select.select([sys.stdin], [], [], 0)
        if not r:
            return None
        ch = sys.stdin.read(1)
        if ch == "\x02":
            return "background"
        if ch == "\x03":
            return "cancel"
        if ch in ("\r", "\n"):
            return _submit()
        if ch in ("\x08", "\x7f"):
            if buf:
                buf.pop()
                _backspace()
            return None
        _begin()
        buf.append(ch)
        _echo(ch)
        return None

    return _src
