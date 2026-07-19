# file: robodog_terminal/test_input.py
"""
Tests for multi-line input handling: bracketed paste captures pasted newlines
whole (like Claude Code), backslash-continuation, and Alt+Enter / Ctrl+J
newlines — driven through a prompt_toolkit pipe input.
Run: python robodog_terminal/test_input.py   (from robodogcli/robodog)
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from prompt_toolkit.input.defaults import create_pipe_input  # noqa: E402
from prompt_toolkit.output import DummyOutput                # noqa: E402
from prompt_toolkit import PromptSession                     # noqa: E402
from robodog_terminal.ui import _input_key_bindings                  # noqa: E402

ok = True


def check(cond, msg):
    global ok
    print(f"  [{'PASS' if cond else 'FAIL'}] {msg}")
    ok = ok and cond


def drive(feed: str) -> str:
    """Run one PromptSession.prompt() with `feed` piped as terminal input."""
    with create_pipe_input() as inp:
        inp.send_text(feed)
        session = PromptSession(
            input=inp, output=DummyOutput(),
            multiline=True, key_bindings=_input_key_bindings(),
        )
        return session.prompt()


ENTER = "\r"
BP_START = "\x1b[200~"   # bracketed paste begin
BP_END = "\x1b[201~"     # bracketed paste end


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

    print("\nINPUT:", "ALL PASS" if ok else "FAILURES")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
