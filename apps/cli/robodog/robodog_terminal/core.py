# file: robodog_terminal/core.py
"""
Headless assembly of the robodog agentic core: ToolRegistry + AgentLoop, with
hooks/skills/background/session-store/task-checklist wiring — and ZERO
dependency on ui.py or argparse.

`app.py::main()` is the CLI entrypoint; it builds a `UI`, resolves CLI flags,
and then calls `build_core()` here to assemble everything an agentic turn
needs, passing its UI-bound callbacks (on_diff, on_bash_line, on_confirm, …)
in as plain function arguments. Every one of those touchpoints is optional
and defaults to a safe no-UI behavior (no-op, or auto-pick-the-first-option),
so `build_core()` is also the seam an embedder — a web backend, a chat bot, a
test harness — calls directly to drive robodog's agent loop without a
terminal attached at all:

    from robodog_terminal.core import build_core
    from robodog_terminal.llm_client import EchoClient

    core = build_core(cwd=".", client=EchoClient())
    result = core.loop.run("list the files here")
    print(result.final_text)
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Dict, List, Optional

try:
    from .llm_client import LLMClient
    from .tools import ToolRegistry, default_registry
    from .loop import AgentLoop
    from . import agents as _agents_mod
    from .agents import register_agent_tool
    from .hooks import HookEngine
    from .skills import SkillsRegistry
    from .background import BackgroundManager
    from .tasklist import TaskChecklist, register_task_tools, register_ask_tool
    from .sessions import SessionStore
    from .checkpoint import Checkpointer
except ImportError:  # pragma: no cover - alt import path (see app.py)
    from robodog_terminal.llm_client import LLMClient
    from robodog_terminal.tools import ToolRegistry, default_registry
    from robodog_terminal.loop import AgentLoop
    from robodog_terminal import agents as _agents_mod
    from robodog_terminal.agents import register_agent_tool
    from robodog_terminal.hooks import HookEngine
    from robodog_terminal.skills import SkillsRegistry
    from robodog_terminal.background import BackgroundManager
    from robodog_terminal.tasklist import TaskChecklist, register_task_tools, register_ask_tool
    from robodog_terminal.sessions import SessionStore
    from robodog_terminal.checkpoint import Checkpointer


def _make_checkpointer() -> Checkpointer:
    import time as _t
    session_dir = Path.home() / ".robodog" / "checkpoints" / _t.strftime("%Y%m%d-%H%M%S")
    return Checkpointer(session_dir)


@dataclass
class Core:
    """Everything needed to drive an agentic turn, headless."""
    registry: ToolRegistry
    loop: AgentLoop
    skills: SkillsRegistry
    manager: BackgroundManager
    checklist: TaskChecklist
    store: SessionStore


def build_core(
    cwd: str,
    client: LLMClient,
    *,
    allowed_tools: Optional[List[str]] = None,
    disallowed_tools: Optional[List[str]] = None,
    permission_mode: Optional[str] = None,   # "yolo" | "plan"; None -> settings.json -> "yolo"
    guard: Optional[str] = None,             # "warn" | "confirm"; None -> settings.json -> "warn"
    net_writes: Optional[str] = None,        # "confirm" | "deny" | "allow"
    verify_edits: bool = True,
    test_command: Optional[str] = None,
    system_suffix: str = "",
    max_iterations: int = 25,
    max_tokens: int = 8192,
    temperature: float = 0.3,
    max_transcript_chars: int = 450_000,
    on_diff: Optional[Callable[[str, str], None]] = None,
    on_bash_line: Optional[Callable[[str], None]] = None,
    on_confirm: Optional[Callable[[str, str], bool]] = None,
    on_child_event: Optional[Callable[[str, dict], None]] = None,
    on_event: Optional[Callable[[str, dict], None]] = None,
    ask_fn: Optional[Callable[[str, List[str]], str]] = None,
    on_task_change: Optional[Callable[[], None]] = None,
    log: Optional[Callable[[str], None]] = None,
    checkpointer: Optional[Checkpointer] = None,
) -> Core:
    """Assemble the agentic core for `cwd`, talking to `client`.

    Every UI touchpoint is an optional callback that defaults to a safe
    no-UI behavior: `on_diff`/`on_bash_line`/`on_confirm`/`on_child_event`/
    `on_event`/`on_task_change` default to doing nothing; `ask_fn` (the
    ask_user tool) defaults to auto-picking the first option, same as
    app.py's existing headless (`-p`) fallback; `log` (informational
    startup lines like "(settings: N rules)") defaults to a no-op.
    `checkpointer` defaults to a fresh timestamped one under
    `~/.robodog/checkpoints/` if not supplied.
    """
    log = log or (lambda _msg: None)
    cwd = str(Path(cwd).resolve())
    registry = default_registry(cwd=cwd)

    if allowed_tools:
        allowed = set(allowed_tools)
        registry._tools = {k: v for k, v in registry._tools.items() if k in allowed}  # noqa: SLF001
    if disallowed_tools:
        for t in disallowed_tools:
            registry._tools.pop(t.strip(), None)  # noqa: SLF001

    registry.checkpointer = checkpointer or _make_checkpointer()
    registry.on_diff = on_diff
    registry.on_bash_line = on_bash_line

    # Hooks + permission rules from .robodog/.claude settings.json — loaded
    # BEFORE the permission-mode/guard/net-writes decision below, so its
    # "defaults" block can seed them; an explicit caller-supplied value wins.
    try:
        registry.hooks = HookEngine.load(cwd)
        if registry.hooks.summary():
            log(f"(settings: {registry.hooks.summary()})")
    except Exception as exc:   # a bad settings file must never break startup
        log(f"(hooks/permissions skipped: {exc})")

    cfg_defaults = registry.hooks.defaults if registry.hooks else {}
    perm_mode = permission_mode or cfg_defaults.get("permissionMode") or "yolo"
    if perm_mode == "plan":
        registry.mode = "plan"
    registry.guard = guard or cfg_defaults.get("guard") or "warn"
    if net_writes:
        registry.net_guard = net_writes
    elif cfg_defaults.get("netWrites"):
        registry.net_guard = cfg_defaults["netWrites"]
    registry.verify_edits = verify_edits
    registry.test_command = test_command
    registry.on_confirm = on_confirm

    manager = BackgroundManager()

    # Discover user extensions: custom commands, agents, skills (.robodog/…).
    skills = SkillsRegistry(cwd=cwd)
    try:
        skills.discover()
        _agents_mod.AGENT_TYPES.update(skills.agent_type_overrides())
    except Exception as exc:  # never let a bad skill file break startup
        log(f"(skills discovery skipped: {exc})")

    if not disallowed_tools or "agent" not in disallowed_tools:
        register_agent_tool(registry, client, on_child_event=on_child_event, manager=manager)

    checklist = TaskChecklist()
    checklist.on_change = on_task_change or (lambda: None)
    register_task_tools(registry, checklist)
    register_ask_tool(registry, ask_fn or (lambda question, options: options[0]))

    store = SessionStore(project_dir=cwd)

    loop = AgentLoop(client, registry, max_iterations=max_iterations,
                     max_tokens=max_tokens, temperature=temperature,
                     on_event=on_event, system_suffix=system_suffix)
    loop.max_transcript_chars = max_transcript_chars

    return Core(registry=registry, loop=loop, skills=skills, manager=manager,
                checklist=checklist, store=store)
