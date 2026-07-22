# file: robodog_terminal/test_input.py
"""
Tests for multi-line input handling: bracketed paste captures pasted newlines
whole (like a modern agentic terminal), backslash-continuation, and Alt+Enter / Ctrl+J
newlines — driven through a prompt_toolkit pipe input.
Run: python robodog_terminal/test_input.py   (from robodogcli/robodog)
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from contextlib import contextmanager                        # noqa: E402

from prompt_toolkit.input.defaults import create_pipe_input  # noqa: E402
from prompt_toolkit.output import DummyOutput                # noqa: E402
from prompt_toolkit import PromptSession                     # noqa: E402
import prompt_toolkit.input.defaults as _pt_input_defaults   # noqa: E402
import prompt_toolkit.output.defaults as _pt_output_defaults  # noqa: E402
from robodog_terminal.ui import _input_key_bindings, UI              # noqa: E402

ok = True


@contextmanager
def real_ui_on_a_fake_tty(**ui_kwargs):
    """Construct a REAL UI() with self._interactive forced True, so it takes
    the actual production PromptSession-construction branch in UI.__init__
    (completer, history, style, key_bindings — all of it) instead of the
    plain-input() fallback every other test in this suite exercises. Yields
    (ui, pipe_input) so the caller can inp.send_text(...) and drive it.

    Needed because on Windows, PromptSession() with no explicit input/output
    tries to open a REAL console at construction time and raises
    NoConsoleScreenBufferError under a non-console TTY emulator (mintty/
    git-bash) — so create_input/create_output are patched to return a pipe
    input + DummyOutput instead, exactly as if a real terminal were attached."""
    orig_isatty_in, orig_isatty_out = sys.stdin.isatty, sys.stdout.isatty
    orig_create_input = _pt_input_defaults.create_input
    orig_create_output = _pt_output_defaults.create_output
    sys.stdin.isatty = lambda: True
    sys.stdout.isatty = lambda: True
    _pt_output_defaults.create_output = lambda *a, **k: DummyOutput()
    try:
        with create_pipe_input() as inp:
            _pt_input_defaults.create_input = lambda *a, **k: inp
            try:
                ui = UI(**ui_kwargs)
            finally:
                _pt_input_defaults.create_input = orig_create_input
            yield ui, inp
    finally:
        sys.stdin.isatty, sys.stdout.isatty = orig_isatty_in, orig_isatty_out
        _pt_output_defaults.create_output = orig_create_output


def check(cond, msg):
    global ok
    print(f"  [{'PASS' if cond else 'FAIL'}] {msg}")
    ok = ok and cond


def drive(feed: str, on_cycle_permission=None) -> str:
    """Run one PromptSession.prompt() with `feed` piped as terminal input."""
    with create_pipe_input() as inp:
        inp.send_text(feed)
        session = PromptSession(
            input=inp, output=DummyOutput(),
            multiline=True, key_bindings=_input_key_bindings(on_cycle_permission),
        )
        return session.prompt()


ENTER = "\r"
BP_START = "\x1b[200~"   # bracketed paste begin
BP_END = "\x1b[201~"     # bracketed paste end
SHIFT_TAB = "\x1b[Z"     # CSI Z — the actual terminal escape for Shift+Tab


def main() -> int:
    global ok

    # 1) plain single line submits on Enter
    check(drive("hello world" + ENTER) == "hello world", "single line submits on Enter")

    # 2) bracketed multi-line paste is captured WHOLE, submitted by trailing Enter
    pasted = "def f():\n    return 1\n    # note"
    got = drive(BP_START + pasted + BP_END + ENTER)
    check(got == pasted, "multi-line paste captured whole (3 lines)")
    check(got.count("\n") == 2, "pasted newlines preserved")

    # 3) paste then keep typing, then submit
    got = drive(BP_START + "line A\nline B" + BP_END + " tail" + ENTER)
    check(got == "line A\nline B tail", "can type after a paste before submit")

    # 4) backslash-continuation: '\' + Enter adds a newline instead of submitting
    got = drive("first\\" + ENTER + "second" + ENTER)
    check(got == "first\nsecond", "backslash+Enter continues to next line")

    # 5) Ctrl+J inserts a newline (portable multiline)
    got = drive("a\x0a" + "b" + ENTER)  # \x0a = Ctrl+J
    check(got == "a\nb", "Ctrl+J inserts newline")

    # 6) a normal Enter with no trailing backslash still submits (regression)
    got = drive("no-continuation" + ENTER)
    check(got == "no-continuation", "plain Enter still submits")

    # 7) a paste carrying lone UTF-16 surrogates (Windows console) submits
    #    WITHOUT crashing — the Enter handler strips them before validate/save.
    surrogate = "git branch \udce2\udc80 feature/x"
    got = drive(surrogate + ENTER)
    check("\udce2" not in got and "git branch" in got,
          "surrogate paste submits cleanly (no crash, surrogates stripped)")

    # 8) _SafeFileHistory never raises or writes invalid utf-8 on surrogate input
    import tempfile
    from robodog_terminal.ui import _SafeFileHistory
    hf = Path(tempfile.mkdtemp()) / "hist"
    h = _SafeFileHistory(str(hf))
    raised = False
    try:
        h.store_string("bad \udce2\udc80 line")
    except Exception:
        raised = True
    check(not raised, "_SafeFileHistory.store_string survives surrogates")
    ok_utf8 = True
    try:
        hf.read_bytes().decode("utf-8")
    except Exception:
        ok_utf8 = False
    check(ok_utf8, "_SafeFileHistory writes valid utf-8")

    # ---- @-file completion + slash-command completion --------------------
    import tempfile
    from robodog_terminal.ui import _RobodogCompleter
    from prompt_toolkit.document import Document
    wd = Path(tempfile.mkdtemp())
    (wd / "src").mkdir()
    (wd / "src" / "app.py").write_text("x", encoding="utf-8")
    (wd / "src" / "api.py").write_text("y", encoding="utf-8")
    (wd / "README.md").write_text("z", encoding="utf-8")
    comp = _RobodogCompleter(["/help", "/save", "/stats"], str(wd))

    def _c(t):
        return [x.text for x in comp.get_completions(Document(t, len(t)), None)]

    check("src/" in _c("read @sr"), "@-mention completes a directory")
    check(set(_c("@src/")) == {"app.py", "api.py"},
          "@dir/ completes the files inside it")
    check(_c("@src/app") == ["app.py"], "@ path completes an unambiguous file")
    check("/save" in _c("/s") and "/stats" in _c("/s"),
          "slash-command completion still works")
    check("src/" not in _c("email@"), "an @ mid-word doesn't spew path completions")

    # ---- Shift+Tab permission-mode cycle (real PromptSession, not a mock) --
    # This is the actual code path a live TTY session exercises — the
    # bottom_toolbar/permission-mode work was previously only verified by
    # calling registry.cycle_permission_mode() directly, never through the
    # real key binding. drive() constructs a genuine PromptSession and feeds
    # it the real terminal escape sequence for Shift+Tab (CSI Z), so this is
    # the actual wiring, not a stand-in for it.
    calls = []
    got = drive(SHIFT_TAB + "hello" + ENTER, on_cycle_permission=lambda: calls.append(1))
    check(got == "hello", "typing still works normally around a Shift+Tab press")
    check(len(calls) == 1, "Shift+Tab fires the on_cycle_permission callback exactly once")

    # Pressed twice before submitting -> called twice (no debouncing/dropping).
    calls2 = []
    drive(SHIFT_TAB + SHIFT_TAB + "x" + ENTER, on_cycle_permission=lambda: calls2.append(1))
    check(len(calls2) == 2, "each Shift+Tab press fires its own callback call")

    # Without a callback wired (on_cycle_permission=None, the default — e.g.
    # headless/non-interactive construction), Shift+Tab is simply unbound and
    # never crashes the session.
    got_none = drive(SHIFT_TAB + "safe" + ENTER)
    check(got_none == "safe", "Shift+Tab with no callback wired doesn't crash or eat input")

    # ---- the REAL UI.__init__ wiring, not just the standalone key-bindings
    # function. Every test above (and the shift+tab work when it shipped)
    # only ever exercised _input_key_bindings() directly or called
    # registry.cycle_permission_mode() by hand — UI.__init__'s own
    # `if self._interactive: self._session = PromptSession(...)` branch,
    # including wire_permission_registry()'s _do_cycle_permission closure,
    # had NEVER been constructed by any test (self._interactive is False in
    # every other test in this suite, since piped stdin isn't a TTY).
    class _FakeRegistry:
        def __init__(self):
            self.calls = 0

        def cycle_permission_mode(self):
            self.calls += 1
            return f"label-{self.calls}"

        def permission_mode_label(self):
            return "label-0"

    with real_ui_on_a_fake_tty(model_name="test/model", cwd=".") as (rui, rinp):
        check(rui._session is not None,  # noqa: SLF001
              "UI() with a forced TTY actually builds a real PromptSession")
        reg = _FakeRegistry()
        rui.wire_permission_registry(reg)
        check(rui.permission_label == "label-0",
              "wire_permission_registry seeds the initial label from the registry")
        rinp.send_text(SHIFT_TAB + "typed" + ENTER)
        result = rui._session.prompt()  # noqa: SLF001
        check(result == "typed", "typing still works through the real UI session")
        check(reg.calls == 1,
              "Shift+Tab through the REAL UI-constructed session calls "
              "registry.cycle_permission_mode()")
        check(rui.permission_label == "label-1",
              "…and updates ui.permission_label with what it returned")

    print("\nINPUT:", "ALL PASS" if ok else "FAILURES")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
