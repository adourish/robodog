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

    # ---------------- tool-aware result summaries ------------------------
    # read_file returns the WHOLE file line-numbered; the trace must report a
    # count, never echo the content (that was the old behaviour, and it made
    # the transcript unreadable).
    ui, buf = capture()
    body = "\n".join(f"{i}\t# secret line {i}" for i in range(1, 47))
    ui.tool_result("read_file", body)
    p = plain(buf.getvalue())
    check("read 46 lines" in p, "read_file summarizes as a line count")
    check("secret line" not in p, "read_file does NOT echo file content")

    ui, buf = capture()
    ui.tool_result("read_file", "(empty file)")
    check("empty file" in plain(buf.getvalue()), "read_file handles an empty file")

    # failures render red and stay visible
    ui, buf = capture()
    ui.tool_result("read_file", "ERROR: file not found: /nope.txt")
    out = buf.getvalue()
    check("\x1b[31m" in out, "ERROR result renders red, not dim")
    check("file not found" in plain(out), "ERROR text is preserved")

    ui, buf = capture()
    ui.tool_result("bash", "$ pytest\n⚠ COMMAND FAILED (exit 1) — read the error and fix it.\n"
                           "--- stdout ---\nboom\nboom2")
    out = buf.getvalue()
    check("\x1b[31m" in out, "failed command renders red")
    check("failed" in plain(out) and "pytest" in plain(out),
          "failed command keeps the command + failure marker")

    # successful bash reports exit + output size, not the output itself
    ui, buf = capture()
    ui.tool_result("bash", "$ ls\n(exit 0)\n--- stdout ---\na.py\nb.py\nc.py")
    p = plain(buf.getvalue())
    check("exit 0" in p and "3 lines" in p, "bash reports exit status + line count")

    # multi-line content never flows into the trace as a blob
    ui, buf = capture()
    ui.tool_result("list_dir", "a.py\nb.py\nc.py\nd.py")
    p = plain(buf.getvalue())
    check("4 entries" in p, "list_dir summarizes as an entry count")

    ui, buf = capture()
    ui.tool_result("glob", "No files matching '*.zzz' under /tmp.")
    check("No files matching" in plain(buf.getvalue()), "glob keeps its empty message")

    # glob/grep now lead with a count header — the summary uses it (no off-by-one
    # from the header line, and grep doesn't double-report "(+N more)").
    ui, buf = capture()
    ui.tool_result("glob", "75 file(s) matching '*.md':\n" + "\n".join(f"p{i}.md" for i in range(75)))
    p = plain(buf.getvalue())
    check("75 file(s) matching" in p and "76 entr" not in p,
          "glob summary uses the accurate count header (not header+1)")
    ui, buf = capture()
    ui.tool_result("grep", "193 match(es) for /FDA/:\n" + "\n".join(f"f:{i}: FDA" for i in range(193)))
    p = plain(buf.getvalue())
    check("193 match(es)" in p and "more)" not in p,
          "grep summary uses the count header without a redundant '(+N more)'")

    # subagent results: labeled with the child id, ANSWER surfaced (like a
    # modern agentic terminal), boilerplate header NOT echoed
    ui, buf = capture()
    ui.tool_result("agent", "[subagent#3:general finished — 2 steps, 314 tokens]\n"
                            "Findings: module 3 has two dead functions.")
    # collapse rich's soft line-wrapping so the substring check is width-proof
    p = " ".join(plain(buf.getvalue()).split())
    check("#3 general" in p and "2 steps" in p and "314 tok" in p,
          "agent result labeled with child id + steps + tokens")
    check("Findings: module 3 has two dead functions." in p,
          "agent result surfaces the child's ANSWER")
    check("[subagent#" not in p, "agent boilerplate header not echoed")

    # singular step; answer missing -> label only, no crash
    ui, buf = capture()
    ui.tool_result("agent", "[subagent#1:explore finished — 1 step, 40 tokens]")
    p = plain(buf.getvalue())
    check("#1 explore · 1 step · 40 tok" in p, "agent one-step label, no answer line")

    # background-start message falls through to the generic summary
    ui, buf = capture()
    ui.tool_result("agent", "Started background subagent bg1 (general). Continue other work;"
                            " fetch its result later with task_output.")
    check("Started background subagent bg1" in plain(buf.getvalue()),
          "agent background-start message kept verbatim")

    # grep keeps the first hit (clickable) and counts the rest
    ui, buf = capture()
    ui.tool_result("grep", "src/mod.py:42: def handler():\nsrc/x.py:7: y\nsrc/z.py:9: q")
    p = plain(buf.getvalue())
    check("mod.py:42" in p and "+2 more" in p, "grep shows first hit + remaining count")

    # _flatten kills tabs/newlines so nothing can break the single-line trace
    ui, _ = capture()
    check("\n" not in ui._flatten("a\nb\tc") and "a b c" == ui._flatten("a\nb\tc"),
          "_flatten collapses newlines and tabs")

    # ---------------- streamed command output is bounded -----------------
    # A 200-line build log must not flood the transcript.
    ui, buf = capture()
    ui.tool_call("bash", {"command": "big"})
    for i in range(200):
        ui.bash_line(f"log line {i}")
    ui.stream_footer()
    p = plain(buf.getvalue())
    shown = p.count("log line ")
    check(shown == ui.STREAM_LIMIT,
          f"streamed output capped at STREAM_LIMIT ({shown} shown)")
    check("output continues" in p, "capped stream says output continues")
    check("more lines not shown" in p, "footer reports the held-back count")
    check(f"{200 - ui.STREAM_LIMIT} more lines" in p,
          f"held-back count is accurate (200 - {ui.STREAM_LIMIT})")

    # TURN budget: many commands in one turn cap the AGGREGATE live preview
    # (each command still gets its summary) so a turn can't flood the trace.
    ui, buf = capture()
    ui.reset_turn_stream()
    for cmd in range(10):
        ui.tool_call("bash", {"command": f"c{cmd}"})
        for i in range(20):
            ui.bash_line(f"c{cmd} line {i}")
        ui.stream_footer()
    p = plain(buf.getvalue())
    preview = sum(1 for l in p.splitlines() if l.strip().startswith("│") and "…" not in l)
    check(preview <= ui.TURN_STREAM_LIMIT,
          f"turn-level preview capped ({preview} <= {ui.TURN_STREAM_LIMIT}); "
          f"without the cap it would be {10 * ui.STREAM_LIMIT}")

    # stream caps are read at INSTANCE creation (in __init__), so config.env
    # values loaded AFTER the module is imported still take effect.
    import os as _os
    _old = _os.environ.get("ROBODOG_STREAM_LINES")
    _os.environ["ROBODOG_STREAM_LINES"] = "3"
    _os.environ["ROBODOG_TURN_STREAM_LINES"] = "15"
    try:
        u2 = UI(model_name="t/m", cwd=".")
        check(u2.STREAM_LIMIT == 3 and u2.TURN_STREAM_LIMIT == 15,
              "stream caps read from env at __init__ (config.env-loaded-late works)")
    finally:
        if _old is None:
            _os.environ.pop("ROBODOG_STREAM_LINES", None)
        else:
            _os.environ["ROBODOG_STREAM_LINES"] = _old
        _os.environ.pop("ROBODOG_TURN_STREAM_LINES", None)

    # ROBODOG_STREAM_LINES=0 -> summary-only (no live │ lines at all)
    ui, buf = capture()
    ui.STREAM_LIMIT = 0
    ui._reset_stream()
    for i in range(50):
        ui.bash_line(f"quiet {i}")
    ui.stream_footer()
    p = plain(buf.getvalue())
    check("quiet" not in p and "output continues" not in p,
          "STREAM_LIMIT=0 shows no live stream (summary-only)")

    # short output is shown in full, with no cap noise
    ui, buf = capture()
    ui.tool_call("bash", {"command": "small"})
    for i in range(3):
        ui.bash_line(f"only {i}")
    ui.stream_footer()
    p = plain(buf.getvalue())
    check(p.count("only ") == 3, "short output shown in full")
    check("output continues" not in p and "not shown" not in p,
          "short output adds no truncation notice")

    # runs of blank lines collapse (PowerShell emits columns of them)
    ui, buf = capture()
    ui.tool_call("bash", {"command": "ps"})
    ui.bash_line("Mode   Name")
    for _ in range(6):
        ui.bash_line("")
    ui.bash_line("d----  aitools")
    ui.stream_footer()
    body = [l for l in plain(buf.getvalue()).splitlines() if "│" in l]
    blanks = [l for l in body if l.strip().rstrip("│").strip() == ""]
    check(len(blanks) <= 1, f"consecutive blank lines collapsed ({len(blanks)} kept)")
    check(any("aitools" in l for l in body), "content after blanks still shown")

    # leading blank lines never open the stream
    ui, buf = capture()
    ui.tool_call("bash", {"command": "x"})
    ui.bash_line("")
    ui.bash_line("")
    ui.bash_line("first real")
    ui.stream_footer()
    lines = [l for l in plain(buf.getvalue()).splitlines() if "│" in l]
    check(lines and "first real" in lines[0], "leading blanks are dropped")

    # a new tool call resets the window (cap doesn't leak between commands)
    ui, buf = capture()
    ui.tool_call("bash", {"command": "one"})
    for i in range(30):
        ui.bash_line(f"a{i}")
    ui.stream_footer()
    ui.tool_call("bash", {"command": "two"})
    ui.bash_line("fresh line")
    ui.stream_footer()
    check("fresh line" in plain(buf.getvalue()),
          "stream window resets on the next tool call")

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

    # ---------------- git branch in the status line ----------------------
    import subprocess, tempfile as _tf
    with _tf.TemporaryDirectory() as repo:
        def _git(*a):
            subprocess.run(["git", *a], cwd=repo, capture_output=True, text=True)
        _git("init", "-q", "-b", "feature/status-line")
        ui, buf = capture(); ui.cwd = repo; ui.print_status()
        p = plain(buf.getvalue())
        check("🌿 feature/status-line" in p,
              f"status line shows the git branch (got: {p.strip()[:70]})")

        # a slash-containing branch name survives intact
        _git("checkout", "-q", "-b", "release/1.2/rc")
        ui, buf = capture(); ui.cwd = repo; ui.print_status()
        check("release/1.2/rc" in plain(buf.getvalue()),
              "branch names containing slashes are not truncated")

        # switching branches invalidates the mtime-keyed cache
        _git("checkout", "-q", "-b", "second")
        ui2, buf2 = capture(); ui2.cwd = repo; ui2.print_status()
        check("🌿 second" in plain(buf2.getvalue()),
              "branch cache invalidates when HEAD changes")

        # nested subdirectory still resolves the repo by walking up
        sub = Path(repo) / "a" / "b"
        sub.mkdir(parents=True, exist_ok=True)
        ui3, buf3 = capture(); ui3.cwd = str(sub); ui3.print_status()
        check("🌿 second" in plain(buf3.getvalue()),
              "branch resolves from a nested subdirectory")

    # outside a repo the segment is omitted entirely (no empty 🌿)
    with _tf.TemporaryDirectory() as plain_dir:
        ui, buf = capture(); ui.cwd = plain_dir; ui.print_status()
        check("🌿" not in plain(buf.getvalue()),
              "no branch segment outside a git repo")
        check(ui._git_branch() is None, "_git_branch returns None outside a repo")

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

    # ------- status line stays visible mid-turn (folded into spinner) -----
    # Regression: the bottom-toolbar status bar only shows at the idle prompt,
    # so while an agent runs the user lost sight of model/tokens/context. The
    # running spinner is the ONE persistent element mid-turn, so thinking_line()
    # folds the status bar into it. It MUST carry the same segments status_line
    # does, plus the step counter.
    tl_ui = UI(model_name="anthropic/claude-sonnet-4.6", cwd=str(Path.cwd()))
    tl_ui.total_tokens = 15600
    tl_ui.context_pct = 36
    tline = tl_ui.thinking_line(7)
    status = tl_ui.status_line()
    check("step 7" in tline, "thinking_line shows the step counter")
    check("claude-sonnet-4.6" in tline, "thinking_line carries the model")
    check("15.6k" in tline, "thinking_line carries the token count")
    check("64%" in tline, "thinking_line carries the context-remaining %")
    check(all(seg in tline for seg in status.split("  ") if seg.strip()),
          "thinking_line contains every status_line segment")
    check("cancel" in tline.lower(), "thinking_line still tells you how to cancel")

    print("\nRENDERING:", "ALL PASS" if ok else "FAILURES")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
