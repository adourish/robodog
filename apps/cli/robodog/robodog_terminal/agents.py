# file: robodog_terminal/agents.py
"""
Subagents: an `agent` tool the model can call to delegate scoped work to a
child agent with its OWN context (a modern agentic terminal's Agent/Task tool).

Why this matters on the gateway especially: the parent re-sends its whole transcript
every iteration, so delegating a search/read-heavy job to a child — whose
transcript is DISCARDED, with only its final text returned as the tool result —
keeps the parent's context (and token bill) small.

Phase A (this file): foreground subagents — the child loop runs synchronously
inside the parent's tool call.
Phase B (later, needs background.py): background=true + task_output polling.

Depth cap = 1: child registries are built WITHOUT the `agent` tool, so
subagents cannot spawn subagents.
"""
from __future__ import annotations

from typing import Callable, Dict, Optional

from .loop import AgentLoop
from .tools import Tool, ToolParam, ToolRegistry, default_registry

AGENT_TYPES: Dict[str, dict] = {
    "explore": {
        "tools": ["read_file", "glob", "grep", "list_dir"],  # read-only
        "max_iterations": 10,
        "note": (
            "You are a READ-ONLY exploration subagent. Investigate the codebase to "
            "answer the delegated question. You cannot modify files or run commands. "
            "Your FINAL message (no tool blocks) must contain your complete findings — "
            "it is the only thing returned to the caller."
        ),
    },
    "general": {
        "tools": None,  # all tools (minus `agent` itself)
        "max_iterations": 25,
        "note": (
            "You are a subagent completing a delegated task. Work autonomously until "
            "done. Your FINAL message (no tool blocks) must summarize what you did and "
            "the outcome — it is the only thing returned to the caller."
        ),
    },
}


def _child_registry(parent: ToolRegistry, agent_type: str) -> ToolRegistry:
    """Fresh registry for the child: same cwd, filtered tools, never `agent`."""
    child = default_registry(cwd=str(parent.cwd))
    allowed = AGENT_TYPES[agent_type]["tools"]
    child._tools = {
        name: tool
        for name, tool in child._tools.items()
        if name != "agent" and (allowed is None or name in allowed)
    }
    return child


def register_agent_tool(
    registry: ToolRegistry,
    client,
    on_child_event: Optional[Callable[[str, dict], None]] = None,
    manager=None,
) -> None:
    """
    Add the `agent` tool to `registry`. `client` is the shared LLMClient
    (the client layer's semaphore caps the gateway concurrency). `on_child_event`
    receives the child loop's events for indented rendering. `manager` is an
    optional BackgroundManager enabling background=true subagents + the
    task_output tool.
    """

    import itertools
    import threading as _threading
    _child_seq = itertools.count(1)
    _seq_lock = _threading.Lock()

    def _make_child(agent_type: str, cancel_event=None, events=None,
                    child_id: int = 0):
        cfg = AGENT_TYPES[agent_type]
        base = events or on_child_event or (lambda k, d: None)

        # Enrich every child event with which child it came from, so the UI
        # can attribute (or aggregate) lines instead of printing them blind.
        def tagged(kind, data):
            base(kind, dict(data, child_id=child_id, agent_type=agent_type))

        return AgentLoop(
            client,
            _child_registry(registry, agent_type),
            max_iterations=cfg["max_iterations"],
            on_event=tagged,
            system_suffix=cfg["note"],
            cancel_event=cancel_event,
        )

    def _agent(args: Dict[str, str]) -> str:
        prompt = args["prompt"]
        agent_type = (args.get("type") or "general").strip().lower()
        background = str(args.get("background", "")).lower() in ("1", "true", "yes")
        if agent_type not in AGENT_TYPES:
            return (f"ERROR: unknown agent type '{agent_type}'. "
                    f"Available: {', '.join(AGENT_TYPES)}")
        with _seq_lock:
            child_id = next(_child_seq)

        if background:
            if manager is None:
                return ("ERROR: background subagents unavailable (no manager); "
                        "run in foreground by omitting the background param.")

            def target(task):
                child = _make_child(
                    agent_type, cancel_event=task.cancel_event,
                    events=lambda k, d: task.emit(
                        f"⚙ {d.get('name', '')} " if k == "tool_start" else "")
                    if k == "tool_start" else None,
                    child_id=child_id)
                res = child.run(prompt)
                return res.final_text

            bg = manager.spawn("agent", f"{agent_type}: {prompt[:50]}", target)
            return (f"Started background subagent {bg.id} ({agent_type}). "
                    f"Continue other work; fetch its result later with "
                    f'<tool name="task_output"><param name="id">{bg.id}</param></tool>.')

        # Lifecycle events so the UI can show live fan-out progress + how many
        # subagents are actually in-flight (which reveals the concurrency cap).
        emit = on_child_event or (lambda k, d: None)
        emit("agent_spawn", {"child_id": child_id, "agent_type": agent_type})
        try:
            child = _make_child(agent_type, child_id=child_id)
            result = child.run(prompt)
        finally:
            emit("agent_done", {"child_id": child_id, "agent_type": agent_type})
        return (
            f"[subagent#{child_id}:{agent_type} finished — {result.iterations} steps, "
            f"{result.total_tokens} tokens]\n{result.final_text}"
        )

    registry.register(Tool(
        name="agent",
        description=(
            "Delegate a scoped task to a subagent with its own fresh context. "
            "Use type=explore for read-only codebase investigation (searching, "
            "reading, summarizing) and type=general for delegated work that may "
            "edit files or run commands. The subagent's final message is returned "
            "to you; its intermediate work is not. Subagents cannot spawn subagents. "
            "PARALLEL FAN-OUT: to run subagents in parallel, emit SEVERAL agent "
            "calls (foreground, background NOT set) in ONE response — they run "
            "concurrently and all results return together in that same turn. "
            "Do NOT use background=true for parallelism; background is only for "
            "detaching a long task to poll later with task_output."
        ),
        params=[
            ToolParam("prompt", "Complete, self-contained task description for the subagent."),
            ToolParam("type", "explore | general (default general).", required=False),
            ToolParam("background", "true to run concurrently (default false).", required=False),
        ],
        handler=_agent,
        mutating=True,  # general-type children can mutate
    ))

    if manager is not None:
        def _task_output(args: Dict[str, str]) -> str:
            task_id = args["id"].strip()
            task = manager.get(task_id)
            if task is None:
                return f"ERROR: no such task '{task_id}'."
            if task.status == "running":
                tail = manager.output(task_id, tail=10)
                return (f"{task_id} still running ({task.kind}). Recent output:\n{tail}"
                        if tail.strip() else f"{task_id} still running ({task.kind}).")
            return f"{task_id} {task.status}.\n{task.result or manager.output(task_id)}"

        registry.register(Tool(
            name="task_output",
            description="Get the status/result of a background task or subagent by id.",
            params=[ToolParam("id", "Task id, e.g. bg1.")],
            handler=_task_output,
        ))
