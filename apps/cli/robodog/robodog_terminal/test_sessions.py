# file: robodog_terminal/test_sessions.py
"""
Self-test for robodog_terminal/sessions.py (SessionStore) — JSONL session persistence.

Covers every public method and the edge cases: meta line format, turn
roundtrip, meta_update merge, listing order, first_prompt truncation,
corrupt-line tolerance, rename/delete/prune, slug safety, and the
never-raise guarantee of append_turn.

Run:  python robodog_terminal/test_sessions.py        (from robodogcli/robodog/)
"""
from __future__ import annotations

import json
import logging
import os
import re
import sys
import tempfile
import time
from pathlib import Path

# Support both "python -m robodog.robodog_terminal.test_sessions" and direct execution.
try:
    from .sessions import SessionStore
except ImportError:  # direct run: add parent so `terminal` is importable
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    from robodog_terminal.sessions import SessionStore

logging.disable(logging.CRITICAL)  # exercised error paths log; keep output clean


def main() -> int:
    ok = True

    def check(cond, msg):
        nonlocal ok
        status = "PASS" if cond else "FAIL"
        if not cond:
            ok = False
        print(f"  [{status}] {msg}")

    base = tempfile.mkdtemp(prefix="robodog_sessions_")

    # ---- slug generation & default base_dir -----------------------------
    print("=== slug / base_dir ===")
    default_store = SessionStore(r"C:\proj")
    check(default_store.base_dir.parts[-2:] == (".robodog", "projects"),
          "default base_dir is ~/.robodog/projects")

    weird = SessionStore(r"C:\My Projects\robo dog:test!", base_dir=base)
    check(re.fullmatch(r"[A-Za-z0-9-]+", weird.slug) is not None,
          f"slug is filesystem-safe ({weird.slug})")
    wid = weird.new_session()
    check((Path(base) / weird.slug / f"{wid}.jsonl").exists(),
          "session file created under slugged directory")

    # ---- new_session + meta line ----------------------------------------
    print("=== new_session ===")
    store = SessionStore(r"C:\projects\demo app", base_dir=base)
    sid1 = store.new_session(name="first")
    check(re.fullmatch(r"\d{8}-\d{6}-[0-9a-f]{4}", sid1) is not None,
          f"session id format ({sid1})")
    p1 = store.dir / f"{sid1}.jsonl"
    check(p1.exists(), "session file exists")
    meta_line = json.loads(p1.read_text(encoding="utf-8").splitlines()[0])
    check(meta_line["type"] == "meta" and meta_line["id"] == sid1
          and meta_line["name"] == "first"
          and meta_line["project"] == r"C:\projects\demo app"
          and isinstance(meta_line["created"], float),
          "first JSONL line is a complete meta record")

    # ---- append_turn + load roundtrip -----------------------------------
    print("=== append_turn / load roundtrip ===")
    long_prompt = "please refactor the entire persistence layer " * 4  # > 80 chars
    store.append_turn(sid1, "user", long_prompt)
    store.append_turn(sid1, "assistant", "on it")
    store.append_turn(sid1, "tool", "$ dir\n...", tool_name="bash")
    loaded = store.load(sid1)
    check(loaded is not None, "load returns a dict")
    turns = loaded["turns"]
    check([t["role"] for t in turns] == ["user", "assistant", "tool"],
          "turn order preserved")
    check(turns[0]["content"] == long_prompt and turns[1]["content"] == "on it",
          "turn content preserved")
    check(turns[2]["tool_name"] == "bash" and turns[0]["tool_name"] == "",
          "tool_name preserved (and defaults to empty)")
    check(loaded["meta"]["name"] == "first"
          and loaded["meta"]["created"] == meta_line["created"],
          "loaded meta matches the meta line")

    # ---- set_meta merge/override ----------------------------------------
    print("=== set_meta ===")
    store.set_meta(sid1, name="renamed", model="gateway", total_tokens=123)
    m = store.load(sid1)["meta"]
    check(m["name"] == "renamed", "meta_update overrides earlier name")
    check(m["model"] == "gateway" and m["total_tokens"] == 123,
          "meta_update adds new keys")
    check(m["created"] == meta_line["created"], "untouched meta keys survive merge")

    # ---- list_sessions / latest -----------------------------------------
    print("=== list_sessions / latest ===")
    time.sleep(0.05)
    sid2 = store.new_session()  # name defaults to None
    store.append_turn(sid2, "assistant", "hello")  # no user turn
    ls = store.list_sessions()
    check(len(ls) == 2, f"two sessions listed (got {len(ls)})")
    check(ls[0]["id"] == sid2 and ls[1]["id"] == sid1, "newest first")
    e1 = ls[1]
    check(e1["turn_count"] == 3, f"turn_count counted (got {e1['turn_count']})")
    check(e1["first_prompt"] == long_prompt[:80] and len(e1["first_prompt"]) == 80,
          "first_prompt is first user turn truncated to 80 chars")
    check(e1["name"] == "renamed" and e1["created"] == meta_line["created"],
          "listing reflects merged meta")
    check(ls[0]["first_prompt"] == "" and ls[0]["name"] == "",
          "no user turn -> empty first_prompt; None name -> ''")
    check(store.latest() == sid2, "latest() returns most recently modified id")

    # ---- missing-session behavior ---------------------------------------
    print("=== missing sessions ===")
    check(store.load("19990101-000000-dead") is None, "load of missing id -> None")
    check(store.rename("19990101-000000-dead", "x") is False,
          "rename of missing id -> False")
    check(store.delete("19990101-000000-dead") is False,
          "delete of missing id -> False")
    store.set_meta("19990101-000000-dead", name="x")  # must not raise
    check(True, "set_meta on missing id swallows")
    empty = SessionStore("other-project", base_dir=base)
    check(empty.list_sessions() == [], "list_sessions with no project dir -> []")
    check(empty.latest() is None, "latest with no sessions -> None")
    check(empty.prune() == 0, "prune with no project dir -> 0")

    # ---- corrupt line tolerance -----------------------------------------
    print("=== corrupt lines ===")
    with p1.open("a", encoding="utf-8") as fh:
        fh.write("{{{ this is not json\n")
        fh.write("42\n")                       # valid JSON, not a dict
        fh.write("   \n")                      # blank
        fh.write('{"type":"unknown","x":1}\n')  # unknown record type
        fh.write('{"type":"turn"}\n')          # turn missing keys -> defaults
    loaded = store.load(sid1)
    check(loaded is not None and len(loaded["turns"]) == 4,
          "load skips corrupt/unknown lines, keeps valid turns")
    check(loaded["turns"][3] == {"role": "", "content": "", "tool_name": ""},
          "turn with missing keys gets safe defaults")
    check(loaded["meta"]["name"] == "renamed", "meta unaffected by corruption")
    listed1 = next(e for e in store.list_sessions() if e["id"] == sid1)
    check(listed1["turn_count"] == 4, "list_sessions tolerates corrupt lines too")

    # ---- rename ----------------------------------------------------------
    print("=== rename ===")
    check(store.rename(sid1, "final-name") is True, "rename returns True")
    check(store.load(sid1)["meta"]["name"] == "final-name", "rename persisted")

    # ---- append_turn never raises ---------------------------------------
    print("=== append_turn swallow ===")
    sid3 = store.new_session("victim")
    p3 = store.dir / f"{sid3}.jsonl"
    os.remove(p3)
    store.append_turn(sid3, "user", "into the void")  # must not raise
    check(not p3.exists(), "append_turn on deleted file swallows (no recreate)")
    baddir = store.dir / "baddir.jsonl"  # a directory where a file is expected
    baddir.mkdir()
    store.append_turn("baddir", "user", "boom")  # open() fails -> swallowed
    check(True, "append_turn swallows OSError from unwritable path")
    check(store.load("baddir") is None, "load of unreadable path -> None")
    check(len(store.list_sessions()) == 2, "list_sessions skips unreadable entry")

    # ---- delete ----------------------------------------------------------
    print("=== delete ===")
    check(store.delete(sid2) is True, "delete returns True")
    check(store.load(sid2) is None, "deleted session no longer loads")
    check(store.delete(sid2) is False, "second delete returns False")

    # ---- prune -----------------------------------------------------------
    print("=== prune ===")
    sid4 = store.new_session("old-session")
    p4 = store.dir / f"{sid4}.jsonl"
    old = time.time() - 40 * 86400
    os.utime(p4, (old, old))
    os.utime(baddir, (old, old))  # old but undeletable -> exercises error path
    n = store.prune(keep_days=30)
    check(n == 1, f"prune deleted exactly the old session (got {n})")
    check(not p4.exists(), "old session file removed")
    check(store.load(sid1) is not None, "recent session survives prune")
    check(baddir.exists(), "prune swallows unlink errors")
    check(store.prune(keep_days=30) == 0, "second prune deletes nothing")

    # ---- meta-less file falls back to filename --------------------------
    print("=== id fallback ===")
    manual = store.dir / "manualfile.jsonl"
    manual.write_text('{"type":"turn","role":"user","content":"hi","ts":1}\n',
                      encoding="utf-8")
    entry = next(e for e in store.list_sessions() if e["id"] == "manualfile")
    check(entry["created"] == 0.0 and entry["turn_count"] == 1
          and entry["first_prompt"] == "hi",
          "file without meta line lists with stem id and defaults")
    check(store.delete("manualfile") is True, "manual file cleaned up")

    print("\nRESULT:", "ALL PASS" if ok else "FAILURES")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
