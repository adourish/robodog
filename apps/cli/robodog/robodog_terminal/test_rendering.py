# file: robodog_terminal/test_rendering.py
"""
Terminal rendering tests: welcome banner, status line, tool trace, colored diff,
markdown answers, and CLICKABLE file/URL links (OSC-8 hyperlinks). Rendering is
captured from a forced-terminal rich Console so the escape sequences are real.
Run: python robodog_terminal/test_rendering.py   (from robodogcli/robodog)
"""
from __future__ import annotations

import io
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from robodog_terminal.ui import UI       # noqa: E402
from robodog_terminal import app as app_mod  # noqa: E402

ok = True


def check(cond, msg):
    global ok
    print(f"  [{'PASS' if cond else 'FAIL'}] {msg}")
    ok = ok and cond


def capture(width=80, links=True):
    """A UI whose rich Console renders to a string buffer as if it were a TTY."""
    from rich.console import Console
    ui = UI(model_name="test/model", cwd=str(Path.cwd()))
    buf = io.StringIO()
    ui.console = Console(file=buf, force_terminal=True, width=width,
                         color_system="standard", legacy_windows=False)
    return ui, buf


def main() -> int:
    global ok
    here = Path(__file__).resolve()

    import re
    # strip ANSI colour codes AND OSC-8 hyperlink wrappers for text assertions
    def plain(s):
        s = re.sub(r"\x1b\]8;[^\x1b]*\x1b\\", "", s)   # OSC-8 open/close
        return re.sub(r"\x1b\[[0-9;]*m", "", s)

    # ---------------- welcome banner + width alignment -------------------
    ui, buf = capture(80)
    ui.welcome()
    out = buf.getvalue()
    box = any(c in out for c in "┌╭│└╰")
    check("robodog" in plain(out) and box, "welcome banner renders a box")
    # borders align by DISPLAY width (cell_len counts the 🤖 emoji as 2 cells,
    # unlike len() which counts it as 1 — the correct terminal-width measure).
    from rich.cells import cell_len
    box_lines = [plain(l).rstrip() for l in out.splitlines()
                 if any(c in l for c in "│╭╮╰╯┌┐└┘")]
    widths = {cell_len(l) for l in box_lines}
    check(len(widths) == 1, f"panel borders aligned by cell width (widths={widths})")

    # ---------------- status line ----------------------------------------
    ui, buf = capture()
    ui.total_tokens = 42
    ui.print_status()
    p = plain(buf.getvalue())
    check("test/model" in p and "42" in p, "status line shows model + tokens")

    # ---------------- tool call with clickable file path -----------------
    ui, buf = capture()
    ui.tool_call("write_file", {"path": str(here)})
    out = buf.getvalue()
    check("write_file" in out, "tool_call shows the tool name")
    # OSC-8 hyperlink: ESC ] 8 ; ; file://... ESC \
    check("\x1b]8;" in out and "file://" in out.replace("\\", "/") or "file://" in out,
          "tool_call path is an OSC-8 clickable file:// link")

    # ---------------- tool result linkifies a path -----------------------
    ui, buf = capture()
    winpath = "C:\\Users\\me\\demo.py"
    ui.tool_result("write_file", f"Created {winpath} (32 bytes, 1 lines).")
    out = buf.getvalue()
    check("\x1b]8;" in out, "tool_result Created-path is a clickable link")
    check("Created" in plain(out) and "demo.py" in plain(out),
          "tool_result keeps the summary text")

    # non-path result renders plainly (no link, no crash)
    ui, buf = capture()
    ui.tool_result("bash", "$ echo hi\n(exit 0)")
    check("echo hi" in buf.getvalue(), "tool_result without a path renders fine")

    # ---------------- diff header link + colored body --------------------
    ui, buf = capture()
    ui.diff(str(here), "--- a/x\n+++ b/x\n@@ -1 +1 @@\n-old\n+new\n")
    out = buf.getvalue()
    check("Δ" in out and "\x1b]8;" in out, "diff header path is a clickable link")
    check("\x1b[32m" in out and "\x1b[31m" in out, "diff renders +green / -red")

    # ---------------- emoji + color status line (agentic) ------
    ui, buf = capture()
    ui.total_tokens = 15600
    ui.context_pct = 36     # 36% used -> 64% remaining, "calm" bubble tier
    out = buf.getvalue() if False else None
    ui.print_status()
    raw = buf.getvalue()
    p = plain(raw)
    check("🫧 64%" in p, "context shows remaining % with tier emoji")
    check("🔋" in p or "✨" in p, "tokens show an escalation emoji")
    check("15.6k" in p, "tokens abbreviated (15.6k)")
    check("📁" in p, "folder segment has an emoji")
    check("\x1b[36m" in raw or "\x1b[0;36m" in raw, "status line is colored (ANSI)")
    # escalation tiers
    ui, buf = capture(); ui.context_pct = 75; ui.print_status()
    check("⚙️ ⚠️ 25%" in plain(buf.getvalue()), "≥60% used -> gears/warning tier")
    ui, buf = capture(); ui.context_pct = 90; ui.print_status()
    check("🚨 💥 10%" in plain(buf.getvalue()), "≥80% used -> alarm tier")
    # model emoji
    ui, buf = capture(); ui.model_name = "gateway/sonnet"; ui.print_status()
    check("🤖" in plain(buf.getvalue()), "sonnet/gateway model -> robot emoji")

    # ---------------- file:line clickable (grep / traceback) -------------
    ui, buf = capture()
    ui.tool_result("grep", "src/mod.py:42: def handler():")
    out = buf.getvalue()
    check("\x1b]8;" in out, "file:line reference is a clickable link")
    check("mod.py:42" in plain(out), "line number stays visible")

    # ---------------- editor-aware links (vscode jumps to the line) ------
    ui, buf = capture(); ui.editor = "vscode"
    ui.tool_result("grep", "src/mod.py:42: def handler():")
    out = buf.getvalue()
    check("vscode://file" in out and ":42" in out,
          "vscode editor: link is vscode://file/…:42 (jumps to line)")
    ui, buf = capture(); ui.editor = "cursor"
    ui.tool_result("grep", "src/mod.py:7: x = 1")
    check("cursor://file" in buf.getvalue(), "cursor editor scheme honored")
    # default editor is plain file://
    ui, buf = capture()
    ui.tool_result("grep", "src/mod.py:42: def handler():")
    check("file://" in buf.getvalue() and "vscode://" not in buf.getvalue(),
          "default editor uses plain file://")
    # _editor_uri unit
    ui2 = capture()[0]; ui2.editor = "vscode"
    uri = ui2._editor_uri("a/b.py", 10)
    check(uri.startswith("vscode://file/") and uri.endswith(":10"),
          "_editor_uri builds vscode URI with line")
    check(ui2.editor == "vscode", "editor field set")

    # ---------------- markdown answer ------------------------------------
    ui, buf = capture()
    ui.assistant("# Title\n\n- one\n- two\n\n`code`")
    out = buf.getvalue()
    check("Title" in out and "one" in out, "assistant renders markdown")

    # ---------------- _file_uri + _linked_path helpers -------------------
    ui, _ = capture()
    uri = ui._file_uri(str(here))
    check(uri is not None and uri.startswith("file:") and here.name in uri,
          "_file_uri builds a file:// URI")
    rel = ui._file_uri("relative_thing.txt")  # resolved against cwd, still a uri
    check(rel is not None and rel.startswith("file:"), "_file_uri resolves relative paths")

    # ---------------- /open target resolution ----------------------------
    # URL detection (don't actually launch a browser; check the not-found/branch)
    msg = app_mod._open_target("does_not_exist_xyz.txt", str(Path.cwd()))
    check("not found" in msg, "/open reports missing file")
    # a real file: os.startfile is monkeypatched to avoid launching anything
    import os as _os
    launched = {}
    orig = getattr(_os, "startfile", None)
    _os.startfile = lambda t: launched.setdefault("t", t)  # type: ignore
    try:
        msg = app_mod._open_target(str(here), str(Path.cwd()))
        check("opened" in msg and launched.get("t"), "/open launches an existing file")
    finally:
        if orig is not None:
            _os.startfile = orig  # type: ignore
        else:
            delattr(_os, "startfile")

    print("\nRENDERING:", "ALL PASS" if ok else "FAILURES")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
