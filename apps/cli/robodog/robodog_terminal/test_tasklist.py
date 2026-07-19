# file: robodog_terminal/test_tasklist.py
"""
Self-test for robodog_terminal/tasklist.py: TaskChecklist, register_task_tools, and
register_ask_tool. Exercises every method and branch against a real
ToolRegistry from robodog_terminal.tools.default_registry.

Run:  python robodog_terminal/test_tasklist.py         (from robodogcli/robodog/)
   or: python -m robodog.robodog_terminal.test_tasklist (from robodogcli/)
"""
from __future__ import annotations

import logging
import sys
import tempfile
from pathlib import Path

logging.disable(logging.CRITICAL)  # expected hook/ask_fn errors are part of the test

try:
    from .tools import default_registry
    from .tasklist import (TaskChecklist, TaskItem, register_ask_tool,
                           register_task_tools)
except ImportError:  # direct run: add parent so `terminal` is importable
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    from robodog_terminal.tools import default_registry
    from robodog_terminal.tasklist import (TaskChecklist, TaskItem, register_ask_tool,
                                   register_task_tools)


def main() -> int:
    ok = True

    def check(cond: bool, msg: str) -> None:
        nonlocal ok
        status = "PASS" if cond else "FAIL"
        if not cond:
            ok = False
        print(f"  [{status}] {msg}")

    # ================= TaskChecklist direct API ==========================
    print("=== TaskChecklist API ===")
    cl = TaskChecklist()
    changes: list = []
    cl.on_change = lambda: changes.append(1)

    t1 = cl.add("first task")
    t2 = cl.add("second task")
    t3 = cl.add("third task")
    check(isinstance(t1, TaskItem), "add returns a TaskItem")
    check((t1.id, t2.id, t3.id) == (1, 2, 3), "ids start at 1 and increment")
    check(t1.status == "pending", "new tasks are pending")
    check(len(changes) == 3, "on_change fired for each add")

    # status transitions
    r = cl.update(1, status="in_progress")
    check(r.startswith("Updated task #1"), f"update to in_progress confirms ({r!r})")
    check(cl.items()[0].status == "in_progress", "status stored as in_progress")
    r = cl.update(1, status="completed")
    check(cl.items()[0].status == "completed", "status transitioned to completed")
    r = cl.update(2, status="pending")
    check(cl.items()[1].status == "pending", "explicit pending status accepted")

    # subject rename
    r = cl.update(3, subject="renamed third")
    check(r.startswith("Updated task #3"), "subject rename confirms")
    check(cl.items()[2].subject == "renamed third", "subject was renamed")

    # bad id / bad status
    r = cl.update(99, status="completed")
    check(r.startswith("ERROR") and "99" in r, f"bad id returns ERROR ({r!r})")
    r = cl.update(1, status="donezo")
    check(r.startswith("ERROR") and "donezo" in r, f"bad status returns ERROR ({r!r})")
    check(cl.items()[0].status == "completed", "bad status did not mutate the task")

    # update with neither status nor subject (no-op branch)
    r = cl.update(2)
    check(r == "Updated task #2.", f"no-field update returns bare confirmation ({r!r})")

    # items() returns a copy
    snapshot = cl.items()
    snapshot.append(TaskItem(id=999, subject="ghost", status="pending"))
    check(len(cl.items()) == 3, "items() returns a copy, not the live list")

    # render_lines symbols for all three states
    cl.update(2, status="in_progress")
    lines = cl.render_lines()
    check(lines == ["[x] first task", "[~] second task", "[ ] renamed third"],
          f"render_lines shows [x]/[~]/[ ] correctly ({lines!r})")

    # summary
    check(cl.summary() == "1/3 done, 1 in progress",
          f"summary counts done + in progress ({cl.summary()!r})")

    # on_change fires on update and clear; raising hook doesn't break mutation
    n_before = len(changes)
    cl.update(3, status="in_progress")
    check(len(changes) == n_before + 1, "on_change fired on update")

    def _boom() -> None:
        raise RuntimeError("UI exploded")

    cl.on_change = _boom
    r = cl.update(3, status="completed")
    check(r.startswith("Updated"), "raising on_change does not break update")
    check(cl.items()[2].status == "completed", "mutation applied despite hook error")
    t4 = cl.add("fourth task")
    check(t4.id == 4, "raising on_change does not break add")
    cl.clear()  # must not raise either
    check(cl.items() == [], "clear removed all tasks (with raising hook)")

    cl.on_change = lambda: changes.append("cleared")
    cl.add("temp")
    cl.clear()
    check(changes[-1] == "cleared", "on_change fired on clear")
    check(cl.summary() == "0/0 done, 0 in progress", "summary on empty checklist")
    check(cl.render_lines() == [], "render_lines on empty checklist")
    t = cl.add("post-clear task")
    check(t.id == 1, "clear resets id counter to 1")
    cl.clear()

    # ================= tools via a real ToolRegistry =====================
    print("\n=== task tools via ToolRegistry ===")
    workdir = tempfile.mkdtemp(prefix="robodog_tasklist_test_")
    reg = default_registry(cwd=workdir)
    register_task_tools(reg, cl)

    # task_list empty
    r = reg.execute("task_list", {})
    check(r == "(no tasks)", f"task_list empty -> '(no tasks)' ({r!r})")

    # task_add multi-line creates several tasks, returns rendered list
    r = reg.execute("task_add", {"subjects": "plan step one\n  plan step two  \n\nplan step three"})
    check(len(cl.items()) == 3, "task_add multi-line created 3 tasks")
    check(r == "[ ] plan step one\n[ ] plan step two\n[ ] plan step three",
          f"task_add returns rendered checklist, whitespace trimmed ({r!r})")

    # task_add with empty subjects
    r = reg.execute("task_add", {"subjects": "\n  \n"})
    check(r.startswith("ERROR"), f"task_add with blank subjects -> ERROR ({r!r})")

    # task_add missing required param (registry-level validation)
    r = reg.execute("task_add", {})
    check(r.startswith("ERROR: missing required param"),
          f"task_add without subjects -> missing-param ERROR ({r!r})")

    # task_update via registry
    r = reg.execute("task_update", {"id": "2", "status": "in_progress"})
    check("[~] plan step two" in r, f"task_update in_progress reflected ({r!r})")
    r = reg.execute("task_update", {"id": "1", "status": "completed"})
    check(r.splitlines()[0] == "[x] plan step one", "task_update completed reflected")
    r = reg.execute("task_update", {"id": "77", "status": "completed"})
    check(r.startswith("ERROR"), f"task_update bad id -> ERROR ({r!r})")
    r = reg.execute("task_update", {"id": "1", "status": "nope"})
    check(r.startswith("ERROR"), f"task_update bad status -> ERROR ({r!r})")
    r = reg.execute("task_update", {"id": "abc", "status": "completed"})
    check(r.startswith("ERROR") and "integer" in r,
          f"task_update non-integer id -> ERROR ({r!r})")

    # task_list non-empty
    r = reg.execute("task_list", {})
    check(r == "[x] plan step one\n[~] plan step two\n[ ] plan step three",
          f"task_list shows current state ({r!r})")

    # ================= ask_user tool =====================================
    print("\n=== ask_user tool ===")
    asked: list = []

    def fake_ask(question: str, options: list) -> str:
        asked.append((question, options))
        return options[1]

    register_ask_tool(reg, fake_ask)

    r = reg.execute("ask_user",
                    {"question": "Which color?", "options": " Red | Green |Blue"})
    check(r == "User chose: Green", f"ask_user happy path ({r!r})")
    check(asked == [("Which color?", ["Red", "Green", "Blue"])],
          f"options parsing trims whitespace ({asked!r})")

    r = reg.execute("ask_user", {"question": "Proceed?", "options": "OnlyOne"})
    check(r.startswith("ERROR") and "at least 2" in r,
          f"single option -> ERROR ({r!r})")
    check(len(asked) == 1, "ask_fn not called for a single option")

    r = reg.execute("ask_user", {"question": "Proceed?", "options": " | |  "})
    check(r.startswith("ERROR"), f"all-blank options -> ERROR ({r!r})")

    def raising_ask(question: str, options: list) -> str:
        raise TimeoutError("user walked away")

    reg2 = default_registry(cwd=workdir)
    register_ask_tool(reg2, raising_ask)
    r = reg2.execute("ask_user", {"question": "Hello?", "options": "A|B"})
    check(r == "ERROR: could not ask the user: user walked away",
          f"raising ask_fn -> ERROR string ({r!r})")

    r = reg.execute("ask_user", {"question": "Hi"})
    check(r.startswith("ERROR: missing required param"),
          f"ask_user without options -> missing-param ERROR ({r!r})")

    # tools appear in the catalog the model reads
    cat = reg.catalog()
    check(all(name in cat for name in ("task_add", "task_update", "task_list", "ask_user")),
          "all four tools appear in the registry catalog")

    print("\nRESULT:", "ALL PASS" if ok else "FAILURES")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
