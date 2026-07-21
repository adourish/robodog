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
from robodog_terminal.tools import (  # noqa: E402
    default_registry, verify_syntax, _fuzzy_find, edit_not_found_hint,
    find_by_basename)

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

    # editing a NONEXISTENT file points at write_file (self-healing) — from a
    # real session that looped read_file/edit_file on a file that didn't exist
    r = reg.execute("edit_file", {"path": "does_not_exist.md",
                                  "old_string": "a", "new_string": "b"})
    check("file not found" in r and "write_file" in r,
          "edit_file on a missing file -> hint to use write_file")

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

    # ---- diff preview: no-trailing-newline file must not mash two lines ----
    # From a real session: editing the LAST line of a file with no final newline
    # rendered `-old` glued to `+new` on one line (`examples.+**See**`) because
    # difflib emits no `\ No newline` marker and "".join() concatenated them.
    captured = []
    reg.on_diff = lambda p, d: captured.append(d)
    nonl = wd / "nonl.md"
    nonl.write_text("# Title\n**See**: `a/skill.md` for docs.", encoding="utf-8")  # no \n
    reg.execute("read_file", {"path": "nonl.md"})
    reg.execute("edit_file", {"path": "nonl.md",
                              "old_string": "**See**: `a/skill.md` for docs.",
                              "new_string": "**See**: `b/skill.md` for docs."})
    reg.on_diff = None
    check(bool(captured), "edit surfaced a diff")
    d = captured[-1] if captured else ""
    check("for docs.+" not in d and "docs.-" not in d,
          "removed line is not glued to the next added line")
    check(all(ln.startswith(("+", "-", " ", "@", "\\")) or ln == ""
              for ln in d.split("\n")),
          "every diff line is a clean +/-/context/hunk line")
    check("-**See**: `a/skill.md`" in d and "+**See**: `b/skill.md`" in d,
          "both the old and new last lines appear, on their own lines")

    # ---- verify-after-write + byte-faithful writes (4.2) -------------------
    reg.execute("write_file", {"path": "vw.py", "content": "a = 1\nb = 2\n"})
    check((wd / "vw.py").read_bytes() == b"a = 1\nb = 2\n",
          "write_file writes LF byte-faithfully (no \\n->\\r\\n translation)")
    r = reg.execute("write_file", {"path": "crlf.txt", "content": "l1\r\nl2\r\n"})
    check("WRITE NOT VERIFIED" not in r
          and (wd / "crlf.txt").read_bytes() == b"l1\r\nl2\r\n",
          "CRLF content is preserved exactly and verifies clean")

    # ---- freshness: refuse to edit a file changed on disk since read -------
    # Prevents the data-loss class where the agent edits from a stale mental
    # copy and clobbers changes it never saw (Roo #1891, aider #2864).
    import os as _os
    fresh = wd / "fresh.py"
    fresh.write_text("a = 1\n", encoding="utf-8")
    reg.execute("read_file", {"path": "fresh.py"})
    r = reg.execute("edit_file", {"path": "fresh.py", "old_string": "a = 1", "new_string": "a = 2"})
    check("Edited" in r, "read->edit works when the file is unchanged")
    r = reg.execute("edit_file", {"path": "fresh.py", "old_string": "a = 2", "new_string": "a = 3"})
    check("Edited" in r and "CHANGED ON DISK" not in r,
          "consecutive robodog edits don't false-trigger the freshness guard")
    rec = reg.read_paths[str(fresh)]
    _os.utime(fresh, (rec + 100, rec + 100))   # simulate an external edit
    r = reg.execute("edit_file", {"path": "fresh.py", "old_string": "a = 3", "new_string": "a = 4"})
    check("CHANGED ON DISK" in r, "edit refused after the file changed on disk")
    reg.execute("read_file", {"path": "fresh.py"})   # re-read clears staleness
    r = reg.execute("edit_file", {"path": "fresh.py", "old_string": "a = 3", "new_string": "a = 4"})
    check("Edited" in r, "re-reading clears staleness and the edit applies")

    # ---- read_file 'did you mean': right filename, wrong directory ---------
    # From a real ELSA session: the model read_file'd IdpFlowHandler.java etc.
    # in the wrong package dir and got a bare "file not found"; the file lived
    # elsewhere in the tree. Suggest the same-basename path so it jumps to it.
    (wd / "src" / "main" / "aiml").mkdir(parents=True, exist_ok=True)
    (wd / "src" / "main" / "aiml" / "IdpFlowHandler.java").write_text(
        "class IdpFlowHandler {}\n", encoding="utf-8")
    (wd / "node_modules" / "junk").mkdir(parents=True, exist_ok=True)
    (wd / "node_modules" / "junk" / "IdpFlowHandler.java").write_text(
        "noise\n", encoding="utf-8")
    hits = find_by_basename(wd, "IdpFlowHandler.java")
    check(len(hits) == 1 and "aiml" in hits[0] and "node_modules" not in hits[0],
          "find_by_basename locates the file and prunes node_modules")
    check(bool(find_by_basename(wd, "idpflowhandler.JAVA")),
          "find_by_basename is case-insensitive")
    r = reg.execute("read_file", {"path": r"wrong\pkg\IdpFlowHandler.java"})
    check("file not found" in r and "Did you mean" in r and "aiml" in r,
          "read_file miss suggests the same-basename path elsewhere")
    r = reg.execute("read_file", {"path": "no_such_unique_name_zzz.txt"})
    check("Did you mean" not in r,
          "read_file miss with no basename match gives no false suggestion")

    # ---- idempotency: edit already applied (old gone, new present) ----------
    idem = wd / "idem.py"
    idem.write_text("value = 2\n", encoding="utf-8")   # already the target state
    reg.execute("read_file", {"path": "idem.py"})
    r = reg.execute("edit_file", {"path": "idem.py",
                                  "old_string": "value = 1", "new_string": "value = 2"})
    check("old_string not found" in r and "ALREADY present" in r,
          "edit_file flags an already-applied edit instead of a bare 'not found'")

    # ---- edit_not_found_hint: turn "not found" into something actionable ----
    # From a real ELSA session: two edit_file calls looped on a bare
    # "old_string not found" with no way for the model to self-correct.
    src = ("# Skills Index\n"
           "- db-query: run Oracle queries\n"
           "- serio-dev-environment: set up the box\n")
    # (a) line-ending mismatch is named explicitly
    h = edit_not_found_hint(src, "# Skills Index\r\n- db-query: run Oracle queries")
    check("line endings" in h.lower(), "hint: names a CRLF/LF mismatch")
    # (b) present but with stray surrounding whitespace
    h = edit_not_found_hint(src, "   - db-query: run Oracle queries   ")
    check("whitespace" in h.lower(), "hint: flags extra leading/trailing whitespace")
    # (c) otherwise point at the closest actual line + its number
    h = edit_not_found_hint(src, "- db-query: run oracle QUERIES now")
    check("line 2" in h and "db-query" in h,
          "hint: points at the closest actual line with its number")
    # (d) surfaced through edit_file's real error
    idx = wd / "SKILLS_INDEX.md"
    idx.write_text(src, encoding="utf-8")
    reg.execute("read_file", {"path": "SKILLS_INDEX.md"})
    r = reg.execute("edit_file", {"path": "SKILLS_INDEX.md",
                                  "old_string": "- db-query: totally wrong text here",
                                  "new_string": "x"})
    check("old_string not found" in r and "closest line" in r,
          "edit_file error now carries the closest-line hint")
    # (e) empty old_string is called out, not a silent no-op
    check("empty" in edit_not_found_hint(src, "   ").lower(),
          "hint: empty old_string is named")

    print("\nEDIT QUALITY:", "ALL PASS" if ok else "FAILURES")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
