# file: terminal/tasklist.py
"""
Agent task checklist + ask-user tool for terminal mode.

Two Claude Code-style features in one module:

A) TaskChecklist — the visible plan the model maintains while doing multi-step
   work (Claude Code's TaskCreate/TaskUpdate). `register_task_tools` exposes it
   to the model as task_add / task_update / task_list.

B) register_ask_tool — an ask_user(question, options) tool (Claude Code's
   AskUserQuestion) that routes a multiple-choice question to the app-supplied
   `ask_fn` (interactive UI or headless auto-answer).
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Callable, Dict, List, Optional

try:
    from .tools import Tool, ToolParam, ToolRegistry
except ImportError:  # direct run: `terminal` package on sys.path
    from terminal.tools import Tool, ToolParam, ToolRegistry

logger = logging.getLogger(__name__)

VALID_STATUSES = ("pending", "in_progress", "completed")

_STATUS_SYMBOL = {
    "pending": "[ ]",
    "in_progress": "[~]",
    "completed": "[x]",
}


@dataclass
class TaskItem:
    id: int
    subject: str
    status: str = "pending"  # pending | in_progress | completed


class TaskChecklist:
    """An ordered, mutable checklist of TaskItems with a UI change hook."""

    def __init__(self) -> None:
        self._items: List[TaskItem] = []
        self._next_id: int = 1
        # UI hook: called (no args) after any mutation. Exceptions are swallowed.
        self.on_change: Optional[Callable[[], None]] = None

    # ---- internals ------------------------------------------------------
    def _notify(self) -> None:
        cb = self.on_change
        if cb is not None:
            try:
                cb()
            except Exception:
                logger.exception("TaskChecklist.on_change hook raised")

    def _find(self, task_id: int) -> Optional[TaskItem]:
        for item in self._items:
            if item.id == task_id:
                return item
        return None

    # ---- mutations ------------------------------------------------------
    def add(self, subject: str) -> TaskItem:
        """Append a new pending task. Ids start at 1 and never reuse."""
        item = TaskItem(id=self._next_id, subject=subject, status="pending")
        self._next_id += 1
        self._items.append(item)
        logger.debug("task added: #%d %s", item.id, item.subject)
        self._notify()
        return item

    def update(self, task_id: int, status: Optional[str] = None,
               subject: Optional[str] = None) -> str:
        """Change a task's status and/or subject. Returns a confirmation
        string, or 'ERROR: ...' for a bad id or status."""
        item = self._find(task_id)
        if item is None:
            return f"ERROR: no task with id {task_id}."
        if status is not None and status not in VALID_STATUSES:
            return (f"ERROR: invalid status '{status}'. "
                    f"Use one of: {', '.join(VALID_STATUSES)}.")
        changes: List[str] = []
        if status is not None:
            item.status = status
            changes.append(f"status={status}")
        if subject is not None:
            item.subject = subject
            changes.append(f"subject={subject!r}")
        logger.debug("task #%d updated: %s", task_id, ", ".join(changes) or "no-op")
        self._notify()
        return f"Updated task #{task_id}" + (f" ({', '.join(changes)})" if changes else "") + "."

    def clear(self) -> None:
        """Remove all tasks and reset the id counter."""
        self._items.clear()
        self._next_id = 1
        self._notify()

    # ---- views ----------------------------------------------------------
    def items(self) -> List[TaskItem]:
        return list(self._items)

    def render_lines(self) -> List[str]:
        """One line per task: '[ ] subject' / '[~] subject' / '[x] subject'."""
        return [f"{_STATUS_SYMBOL[i.status]} {i.subject}" for i in self._items]

    def summary(self) -> str:
        """e.g. '2/5 done, 1 in progress'."""
        total = len(self._items)
        done = sum(1 for i in self._items if i.status == "completed")
        in_prog = sum(1 for i in self._items if i.status == "in_progress")
        return f"{done}/{total} done, {in_prog} in progress"


# ========================================================================
# Tool registration
# ========================================================================
_PLAN_HINT = ("Maintain a visible plan for multi-step work: create tasks up "
              "front, mark in_progress when starting one, completed when done.")


def register_task_tools(registry: ToolRegistry, checklist: TaskChecklist) -> None:
    """Register task_add / task_update / task_list on the given registry."""

    def _rendered() -> str:
        lines = checklist.render_lines()
        return "\n".join(lines) if lines else "(no tasks)"

    def _task_add(args: Dict[str, str]) -> str:
        subjects = [ln.strip() for ln in args["subjects"].splitlines() if ln.strip()]
        if not subjects:
            return "ERROR: 'subjects' is empty - provide one task subject per line."
        for subject in subjects:
            checklist.add(subject)
        return _rendered()

    registry.register(Tool(
        name="task_add",
        description=(f"{_PLAN_HINT} Creates one task per line of 'subjects' "
                     f"(so a whole plan can be created in one call). "
                     f"Returns the rendered checklist."),
        params=[
            ToolParam("subjects", "Task subjects, one per line."),
        ],
        handler=_task_add,
    ))

    def _task_update(args: Dict[str, str]) -> str:
        try:
            task_id = int(str(args["id"]).strip())
        except ValueError:
            return f"ERROR: 'id' must be an integer, got {args['id']!r}."
        result = checklist.update(task_id, status=args["status"])
        if result.startswith("ERROR"):
            return result
        return _rendered()

    registry.register(Tool(
        name="task_update",
        description=(f"{_PLAN_HINT} Sets a task's status "
                     f"(pending|in_progress|completed). "
                     f"Returns the rendered checklist."),
        params=[
            ToolParam("id", "Task id (from task_add / task_list)."),
            ToolParam("status", "New status: pending | in_progress | completed."),
        ],
        handler=_task_update,
    ))

    def _task_list(args: Dict[str, str]) -> str:
        return _rendered()

    registry.register(Tool(
        name="task_list",
        description=f"{_PLAN_HINT} Shows the current checklist.",
        params=[],
        handler=_task_list,
    ))


def register_ask_tool(registry: ToolRegistry,
                      ask_fn: Callable[[str, List[str]], str]) -> None:
    """Register ask_user(question, options). `options` is pipe-separated
    ('Option A|Option B|Option C', 2-6 options). ask_fn(question, options_list)
    -> str is injected by the app (interactive UI or headless auto-answer)."""

    def _ask_user(args: Dict[str, str]) -> str:
        question = args["question"]
        options = [o.strip() for o in args["options"].split("|") if o.strip()]
        if len(options) < 2:
            return ("ERROR: provide at least 2 options, pipe-separated, "
                    "e.g. 'Option A|Option B'.")
        try:
            choice = ask_fn(question, options)
        except Exception as exc:
            logger.exception("ask_fn raised while asking the user")
            return f"ERROR: could not ask the user: {exc}"
        return f"User chose: {choice}"

    registry.register(Tool(
        name="ask_user",
        description=("Ask the user a multiple-choice question when a decision "
                     "genuinely needs their input. Use sparingly."),
        params=[
            ToolParam("question", "The question to ask the user."),
            ToolParam("options", "2-6 choices, pipe-separated: 'Option A|Option B'."),
        ],
        handler=_ask_user,
    ))
