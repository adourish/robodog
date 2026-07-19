# file: robodog_terminal/test_loop_checkpoint.py
"""
Tests for loop.py (trim, nudge, circuit breaker, cancel) and checkpoint.py
(snapshot/restore/prune/markers) and the tools.py safety layer
(read-before-edit, diff hook, excluded dirs, clamp, param validation).
Run: python robodog_terminal/test_loop_checkpoint.py   (from robodogcli/robodog)
"""
from __future__ import annotations

import sys
import tempfile
import threading
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from robodog_terminal.llm_client import EchoClient          # noqa: E402
from robodog_terminal.tools import default_registry, _clamp  # noqa: E402
from robodog_terminal.loop import AgentLoop, Turn            # noqa: E402
from robodog_terminal.checkpoint import Checkpointer         # noqa: E402

ok = True


def check(cond, msg):
    global ok
    print(f"  [{'PASS' if cond else 'FAIL'}] {msg}")
    ok = ok and cond


def main() -> int:
    global ok
    wd = Path(tempfile.mkdtemp(prefix="rd_lc_"))

    # ---------------- loop: transcript trim ------------------------------
    loop = AgentLoop(EchoClient(script=["done"]), default_registry(cwd=str(wd)))
    loop.max_transcript_chars = 2000
    for i in range(20):
        loop.history.append(Turn("tool", "x" * 500, tool_name="bash"))
    loop.history.append(Turn("user", "latest question"))
    before = loop.transcript_chars()
    loop._trim_history()
    after = loop.transcript_chars()
    check(after < before and after <= 2000 + 500 * 8,
          f"trim reduced transcript {before} -> {after}")
    cleared = sum(1 for t in loop.history if "cleared" in t.content)
    check(cleared > 0, f"old tool outputs cleared ({cleared})")
    check(loop.history[-1].content == "latest question", "recent turns untouched")

    # ---------------- loop: nudge on intent-without-action ----------------
    loop2 = AgentLoop(EchoClient(script=[
        "I'll create the file for you.",       # intent, no tool blocks -> nudge
        "All finished, nothing else needed.",  # real final
    ]), default_registry(cwd=str(wd)))
    r = loop2.run("do something")
    check(r.iterations == 2 and "finished" in r.final_text,
          "nudge forced a second attempt")
    check(any(t.tool_name == "system" and "NO <tool> blocks" in t.content
              for t in r.turns), "nudge turn injected")

    # ---------------- loop: circuit breaker -------------------------------
    bad = '<tool name="read_file"><param name="path">missing.txt</param></tool>'
    loop3 = AgentLoop(EchoClient(script=[bad] * 6), default_registry(cwd=str(wd)))
    r = loop3.run("read it")
    check("aborted" in r.final_text and r.iterations <= 4,
          f"circuit breaker aborted at iter {r.iterations}")
    warns = [t for t in r.turns if t.tool_name == "system" and "WARNING" in t.content]
    check(len(warns) == 1, "single warning before abort")

    # ---------------- loop: cancel_event ----------------------------------
    ev = threading.Event()
    ev.set()
    loop4 = AgentLoop(EchoClient(script=["never"]),
                      default_registry(cwd=str(wd)), cancel_event=ev)
    r = loop4.run("anything")
    check(r.final_text == "[cancelled]" and r.iterations == 0,
          "pre-set cancel_event stops before first LLM call")

    # ---------------- loop: max_iterations exhaustion ---------------------
    call = '<tool name="list_dir"></tool>'
    scripts = [f"{call}{i}" if False else call for i in range(10)]
    # vary args so the circuit breaker doesn't trip: alternate two dirs
    (wd / "d1").mkdir(exist_ok=True)
    (wd / "d2").mkdir(exist_ok=True)
    alt = ['<tool name="list_dir"><param name="path">d1</param></tool>',
           '<tool name="list_dir"><param name="path">d2</param></tool>']
    loop5 = AgentLoop(EchoClient(script=alt * 3), default_registry(cwd=str(wd)),
                      max_iterations=3)
    r = loop5.run("loop forever")
    check("max_iterations" in r.final_text, "max_iterations stop message")

    # ---------------- checkpointer ----------------------------------------
    cp = Checkpointer(wd / ".ckpt")
    f = wd / "file.txt"
    f.write_text("v1", encoding="utf-8")
    cp.set_marker(0)
    cp.snapshot(f)
    f.write_text("v2", encoding="utf-8")
    cp.set_marker(1)
    cp.snapshot(f)
    f.write_text("v3", encoding="utf-8")
    new = wd / "created.txt"
    cp.record_new(new)
    new.write_text("brand new", encoding="utf-8")
    marks = cp.markers()
    check(marks == {0: 1, 1: 2}, f"markers counted per prompt ({marks})")
    acts = cp.restore(1)
    check(f.read_text() == "v2" and not new.exists(),
          "restore(1): v2 restored, created file deleted")
    acts = cp.restore(0)
    check(f.read_text() == "v1", "restore(0): original content back")
    cp.snapshot(wd / "nonexistent.txt")  # no-op path
    check(True, "snapshot of missing file is a no-op")
    # manifest reload
    cp2 = Checkpointer(wd / ".ckpt")
    check(cp2.markers() == marks, "manifest reloads from disk")

    # ---------------- tools: safety layer ---------------------------------
    reg = default_registry(cwd=str(wd))
    diffs = []
    reg.on_diff = lambda p, d: diffs.append(d)
    reg.checkpointer = Checkpointer(wd / ".ckpt2")
    t = wd / "safe.txt"
    t.write_text("hello world", encoding="utf-8")
    r = reg.execute("edit_file", {"path": "safe.txt", "old_string": "hello",
                                  "new_string": "bye"})
    check(r.startswith("ERROR") and "read it first" in r, "edit before read refused")
    r = reg.execute("write_file", {"path": "safe.txt", "content": "x"})
    check(r.startswith("ERROR"), "overwrite before read refused")
    reg.execute("read_file", {"path": "safe.txt"})
    r = reg.execute("edit_file", {"path": "safe.txt", "old_string": "hello",
                                  "new_string": "bye"})
    check("Edited" in r and diffs and "-hello world" in diffs[-1],
          "edit after read + diff emitted")
    r = reg.execute("edit_file", {"path": "safe.txt", "old_string": "zzz",
                                  "new_string": "y"})
    check("not found" in r, "edit: old_string not found error")
    t.write_text("aa aa", encoding="utf-8")
    reg.execute("read_file", {"path": "safe.txt"})
    r = reg.execute("edit_file", {"path": "safe.txt", "old_string": "aa",
                                  "new_string": "b"})
    check("not unique" in r, "edit: ambiguity error")
    r = reg.execute("edit_file", {"path": "safe.txt", "old_string": "aa",
                                  "new_string": "b", "replace_all": "true"})
    check("2 replacement" in r and t.read_text() == "b b", "replace_all works")
    r = reg.execute("edit_file", {"path": "ghost.txt", "old_string": "a",
                                  "new_string": "b"})
    check("not found" in r, "edit missing file error")

    # read_file offset/limit + missing
    big = wd / "big.txt"
    big.write_text("\n".join(f"line{i}" for i in range(10)), encoding="utf-8")
    r = reg.execute("read_file", {"path": "big.txt", "offset": "3", "limit": "2"})
    check("line3" in r and "line4" in r and "line5" not in r,
          "read_file offset+limit")
    r = reg.execute("read_file", {"path": "big.txt", "offset": "8"})
    check("line8" in r and "line9" in r and "line2" not in r, "read_file offset only")
    check(reg.execute("read_file", {"path": "nope.txt"}).startswith("ERROR"),
          "read_file missing error")

    # glob/grep/list_dir branches
    (wd / "node_modules").mkdir(exist_ok=True)
    (wd / "node_modules" / "junk.py").write_text("x=1")
    (wd / "keep.py").write_text("magic_token = 7")
    r = reg.execute("glob", {"pattern": "*.py"})
    check("keep.py" in r and "node_modules" not in r, "glob excludes node_modules")
    check("No files matching" in reg.execute("glob", {"pattern": "*.zzz"}),
          "glob no-match message")
    r = reg.execute("grep", {"pattern": "magic_token", "glob": "*.py"})
    check("keep.py:1" in r, "grep finds match with line number")
    check("No matches" in reg.execute("grep", {"pattern": "zzzz9x"}),
          "grep no-match message")
    check("bad regex" in reg.execute("grep", {"pattern": "([unclosed"}),
          "grep bad regex error")
    check("ERROR" in reg.execute("list_dir", {"path": "missing_dir"}),
          "list_dir missing error")

    # registry misc
    check("unknown tool" in reg.execute("nope", {}), "unknown tool error")
    check("missing required param" in reg.execute("read_file", {}),
          "missing param error")
    clamped = _clamp("z" * 100_000)
    check(len(clamped) < 40_000 and "truncated" in clamped, "clamp truncates")
    cat = reg.catalog()
    check("read_file" in cat and "offset?" in cat.replace(" ", "")
          or "offset" in cat, "catalog lists tools+params")

    print("\nLOOP/CHECKPOINT/TOOLS:", "ALL PASS" if ok else "FAILURES")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
