# file: robodog_terminal/test_edit_quality.py
"""
Tests for Pack A — self-healing edits:
post-edit syntax verification, whitespace-tolerant fuzzy edit fallback,
and the atomic multi_edit tool.
Run: python robodog_terminal/test_edit_quality.py   (from robodogcli/robodog)
"""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from robodog_terminal.tools import default_registry, verify_syntax, _fuzzy_find  # noqa: E402

ok = True


def check(cond, msg):
    global ok
    print(f"  [{'PASS' if cond else 'FAIL'}] {msg}")
    ok = ok and cond


def main() -> int:
    global ok
    wd = Path(tempfile.mkdtemp(prefix="rd_edit_"))
    reg = default_registry(cwd=str(wd))

    # ---------------- verify_syntax unit ---------------------------------
    good = wd / "good.py"
    good.write_text("x = 1\nprint(x)\n", encoding="utf-8")
    check(verify_syntax(good) is None, "verify: valid python passes")
    bad = wd / "bad.py"
    bad.write_text("def f(:\n  pass\n", encoding="utf-8")
    check("syntax error" in (verify_syntax(bad) or "").lower(),
          "verify: broken python caught")
    j = wd / "d.json"
    j.write_text('{"a": 1}', encoding="utf-8")
    check(verify_syntax(j) is None, "verify: valid json passes")
    j.write_text('{"a": 1,,}', encoding="utf-8")
    check("json" in (verify_syntax(j) or "").lower(), "verify: broken json caught")
    txt = wd / "notes.txt"
    txt.write_text("anything goes >>> here", encoding="utf-8")
    check(verify_syntax(txt) is None, "verify: non-code extension skipped")

    # ---------------- write_file feeds verify error back -----------------
    r = reg.execute("write_file", {"path": "new.py",
                                   "content": "def broken(\n    pass"})
    check("VERIFY FAILED" in r and "syntax error" in r.lower(),
          "write_file surfaces syntax error to the agent")
    check((wd / "new.py").exists(), "file still written despite verify error")
    r = reg.execute("write_file", {"path": "fine.py", "content": "y = 2\n"})
    check("VERIFY FAILED" not in r and "Created" in r, "clean write: no verify noise")

    # verify can be disabled
    reg.verify_edits = False
    r = reg.execute("write_file", {"path": "new2.py", "content": "def x(\n"})
    check("VERIFY FAILED" not in r, "verify_edits=False suppresses check")
    reg.verify_edits = True

    # ---------------- fuzzy edit fallback --------------------------------
    src = ("def add(a, b):\n"
           "    result = a + b   \n"       # trailing spaces in file
           "    return result\n")
    f = wd / "calc.py"
    f.write_text(src, encoding="utf-8")
    reg.execute("read_file", {"path": "calc.py"})
    # multi-line old_string; the file has trailing spaces after 'a + b' that the
    # model omits, so the exact substring is absent -> fuzzy per-line match wins.
    r = reg.execute("edit_file", {
        "path": "calc.py",
        "old_string": "    result = a + b\n    return result",
        "new_string": "    result = a + b + 1\n    return result"})
    check("whitespace-normalization" in r, "fuzzy fallback matched")
    check("a + b + 1" in f.read_text(), "fuzzy edit applied correct change")
    check("    return result" in f.read_text(), "indentation preserved by fuzzy edit")

    # fuzzy is safe: ambiguous match refuses
    amb = wd / "amb.py"
    amb.write_text("x = 1  \nx = 1\n", encoding="utf-8")
    reg.execute("read_file", {"path": "amb.py"})
    r = reg.execute("edit_file", {"path": "amb.py", "old_string": "x = 1",
                                  "new_string": "x = 2"})
    # exact match count == 2 -> not-unique error (never reaches fuzzy)
    check("not unique" in r, "exact ambiguity still reported")
    # genuinely-absent string
    r = reg.execute("edit_file", {"path": "amb.py", "old_string": "zzz nope",
                                  "new_string": "q"})
    check("not found" in r, "absent old_string still errors")

    # _fuzzy_find ambiguity returns None
    check(_fuzzy_find("a  \na\nfoo\na  \n", "a") is None,
          "_fuzzy_find refuses ambiguous match")

    # ---------------- multi_edit ------------------------------------------
    m = wd / "multi.py"
    m.write_text("A = 1\nB = 2\nC = 3\n", encoding="utf-8")
    reg.execute("read_file", {"path": "multi.py"})
    r = reg.execute("multi_edit", {"path": "multi.py",
                                   "edits": "A = 1>>>A = 10\n===\nC = 3>>>C = 30"})
    check("Applied 2 edits" in r and "atomically" in r, "multi_edit applies all")
    body = m.read_text()
    check("A = 10" in body and "B = 2" in body and "C = 30" in body,
          "multi_edit made both changes, left B alone")

    # atomic: one bad edit -> nothing applied
    m.write_text("A = 1\nB = 2\n", encoding="utf-8")
    reg.execute("read_file", {"path": "multi.py"})
    r = reg.execute("multi_edit", {"path": "multi.py",
                                   "edits": "A = 1>>>A = 99\n===\nZ = 9>>>Z = 0"})
    check("NO changes applied" in r and "edit #2" in r, "multi_edit is atomic on failure")
    check(m.read_text() == "A = 1\nB = 2\n", "file unchanged after atomic failure")

    # multi_edit verify feedback
    m.write_text("val = 1\n", encoding="utf-8")
    reg.execute("read_file", {"path": "multi.py"})
    r = reg.execute("multi_edit", {"path": "multi.py", "edits": "val = 1>>>val = ("})
    check("VERIFY FAILED" in r, "multi_edit runs post-edit verify")

    # bad format
    m.write_text("val = 1\n", encoding="utf-8")
    reg.execute("read_file", {"path": "multi.py"})
    r = reg.execute("multi_edit", {"path": "multi.py", "edits": "no arrow here"})
    check("missing '>>>'" in r, "multi_edit rejects malformed edits")
    r = reg.execute("multi_edit", {"path": "ghost.py", "edits": "a>>>b"})
    check("not found" in r, "multi_edit missing-file error")

    # read-before-edit still enforced
    unread = wd / "unread.py"
    unread.write_text("q = 1\n", encoding="utf-8")
    r = reg.execute("multi_edit", {"path": "unread.py", "edits": "q = 1>>>q = 2"})
    check("read it first" in r, "multi_edit enforces read-before-edit")

    # tool registered + in catalog
    check(reg.get("multi_edit") is not None and "multi_edit" in reg.catalog(),
          "multi_edit registered and catalogued")

    print("\nEDIT QUALITY:", "ALL PASS" if ok else "FAILURES")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
