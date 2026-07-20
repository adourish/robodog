# file: robodog_terminal/app.py
"""
Robodog Terminal Mode — entry point.

Wires the UI, the agentic loop, slash commands, and the LLM backend.

Backend selection (in priority order):
  1. --echo flag or ROBODOG_TERMINAL_ECHO=1  -> EchoClient (offline demo)
  2. GATEWAY_ENDPOINT + GATEWAY_ENGINE + GATEWAY_ACCESS_KEY + GATEWAY_SECRET_KEY  -> GatewayClient
  3. otherwise                                 -> EchoClient (with a notice)

Run:
  python -m robodog.robodog_terminal.app            (from robodogcli/)
  python robodog_terminal/app.py                    (from robodogcli/robodog/)
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

try:
    from .llm_client import EchoClient, GatewayClient, LLMClient, OpenAICompatClient, clean_text
    from .tools import default_registry
    from .loop import AgentLoop
    from .ui import UI
    from .agents import register_agent_tool
except ImportError:
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    from robodog_terminal.llm_client import EchoClient, GatewayClient, LLMClient, OpenAICompatClient, clean_text
    from robodog_terminal.tools import default_registry
    from robodog_terminal.loop import AgentLoop
    from robodog_terminal.ui import UI
    from robodog_terminal.agents import register_agent_tool

DEMO_SCRIPT = [
    'I will create a small script for you.\n'
    '<tool name="write_file">\n'
    '  <param name="path">demo.py</param>\n'
    '  <param name="content">print("robodog terminal is alive:", 6 * 7)</param>\n'
    '</tool>',
    'Now running it.\n'
    '<tool name="bash"><param name="command">python demo.py</param></tool>',
    'Done — created demo.py and ran it (it printed 42). Ask me to build or change anything.',
]


# Default model for OpenAI-compatible backends (OpenRouter). Overridable with
# --model or the ROBODOG_MODEL env var.
DEFAULT_MODEL = os.environ.get("ROBODOG_MODEL", "anthropic/claude-sonnet-4.6")

# The runPixel "gateway" backend (a SEMOSS-style enterprise LLM gateway) is fully
# env-driven — no endpoints or engine ids are baked in. Set GATEWAY_ENDPOINT,
# GATEWAY_ENGINE, GATEWAY_ACCESS_KEY, GATEWAY_SECRET_KEY (or --gateway-endpoint /
# --gateway-engine). Credentials may also come from a KeePass entry named by
# GATEWAY_KEEPASS_ENTRY.
KEEPASS_ENTRY = os.environ.get("GATEWAY_KEEPASS_ENTRY", "Gateway")


def _keepass_candidates():
    """
    (db, keyfile, loader_dir) locations to try for the KeePass automation DB.
    Fully env-configurable — no personal paths are baked in:
      ROBODOG_KEEPASS_DB, ROBODOG_KEEPASS_KEYFILE, ROBODOG_KEEPASS_DIR
    Falls back to ~/.robodog/automation-keys.kdbx.
    """
    out = []
    db = os.environ.get("ROBODOG_KEEPASS_DB")
    if db:
        kf = os.environ.get("ROBODOG_KEEPASS_KEYFILE",
                            str(Path(db).with_suffix(".keyfile")))
        out.append((db, kf, os.environ.get("ROBODOG_KEEPASS_DIR")))
    home = Path.home() / ".robodog"
    out.append((str(home / "automation-keys.kdbx"),
                str(home / "automation-keys.keyfile"), str(home)))
    return out


def _load_gateway_keys() -> tuple:
    """
    Resolve (access_key, secret_key) without ever printing them.
    Order: GATEWAY_* env vars -> KeePass automation DB (pykeepass loader, then
    keepassxc-cli fallback, matching a common keyfile pattern).
    """
    access = os.environ.get("GATEWAY_ACCESS_KEY")
    secret = os.environ.get("GATEWAY_SECRET_KEY")
    if access and secret:
        return access, secret, "env"

    candidates = _keepass_candidates()
    for db, keyfile, loader_dir in candidates:
        if not Path(db).exists():
            continue
        # 1) python loader if available (stdout chatter -> stderr for headless mode)
        if loader_dir and Path(loader_dir, "keepass_loader.py").exists():
            try:
                import contextlib
                sys.path.insert(0, loader_dir)
                from keepass_loader import KeePassLoader  # type: ignore
                with contextlib.redirect_stdout(sys.stderr):
                    kp = KeePassLoader(db_path=db, keyfile=keyfile)
                    kp.unlock()
                    creds = kp.get_credentials(title=KEEPASS_ENTRY)
                if creds and creds.get("password"):
                    return creds.get("username"), creds.get("password"), f"keepass:{KEEPASS_ENTRY}"
            except Exception:
                pass
        # 2) keepassxc-cli fallback (self-hosted gateway pattern)
        cli = r"C:\Program Files\KeePassXC\keepassxc-cli.exe"
        if Path(cli).exists():
            import subprocess
            for entry in (f"API/{KEEPASS_ENTRY}", f"Other/{KEEPASS_ENTRY}", KEEPASS_ENTRY):
                try:
                    sec = subprocess.run(
                        [cli, "show", "--key-file", keyfile, "--no-password",
                         "-a", "Password", db, entry],
                        capture_output=True, text=True, timeout=15).stdout.strip()
                    if sec:
                        acc = subprocess.run(
                            [cli, "show", "--key-file", keyfile, "--no-password",
                             "-a", "UserName", db, entry],
                            capture_output=True, text=True, timeout=15).stdout.strip()
                        return acc, sec, f"keepassxc-cli:{entry}"
                except Exception:
                    continue
    return None, None, "not found"


def _load_keepass_entry(title: str):
    """Fetch (username, password, url) from the automation KeePass, or Nones.
    Loader chatter is redirected to stderr so headless (-p) stdout stays clean."""
    import contextlib
    for db, keyfile, loader_dir in _keepass_candidates():
        if not (loader_dir and Path(loader_dir, "keepass_loader.py").exists()
                and Path(db).exists()):
            continue
        try:
            sys.path.insert(0, loader_dir)
            from keepass_loader import KeePassLoader  # type: ignore
            with contextlib.redirect_stdout(sys.stderr):
                kp = KeePassLoader(db_path=db, keyfile=keyfile)
                kp.unlock()
                creds = kp.get_credentials(title=title) or {}
            if creds:
                return creds.get("username"), creds.get("password"), creds.get("url")
        except Exception:
            continue
    return None, None, None


def build_backend(args, on_retry=None) -> tuple:
    """
    Selection order:
      --echo               -> offline scripted demo
      --backend gateway    -> runPixel gateway (env endpoint/engine; keys env->KeePass)
      --backend openrouter/openai -> OpenAI-compat with keys from env or KeePass
      auto (default)       -> gateway if GATEWAY_* env is set, else OpenRouter via
                              KeePass, else gateway via KeePass keys, else echo
    """
    backend = getattr(args, "backend", "auto") or "auto"
    if args.echo or os.environ.get("ROBODOG_TERMINAL_ECHO") == "1" or backend == "echo":
        return EchoClient(script=DEMO_SCRIPT), "echo/demo"

    def make_gateway(source_note):
        endpoint = (os.environ.get("GATEWAY_ENDPOINT")
                    or os.environ.get("GATEWAY_ASYNC_ENDPOINT"))
        engine = os.environ.get("GATEWAY_ENGINE")
        if not endpoint or not engine:
            return None   # no baked-in endpoints; the gateway is fully env-driven
        access, secret, source = _load_gateway_keys()
        if not (access and secret):
            return None
        return (GatewayClient(endpoint=endpoint, engine_id=engine,
                           access_key=access, secret_key=secret,
                           use_history=os.environ.get("GATEWAY_USE_HISTORY") == "1",
                           on_retry=on_retry),
                f"gateway/{engine[:8]} ({source_note or source})")

    def make_openai_compat(entry_title, default_url, model):
        key = os.environ.get("ROBODOG_LLM_KEY")
        url = os.environ.get("ROBODOG_LLM_URL", default_url)
        if not key:
            _, key, kp_url = _load_keepass_entry(entry_title)
            url = os.environ.get("ROBODOG_LLM_URL") or kp_url or default_url
        if not key:
            return None
        return (OpenAICompatClient(base_url=url, api_key=key, model=model,
                                   on_retry=on_retry),
                f"{model}")

    # Normalize here too, not just at /model — a dashed slip typed at the CLI
    # (--model anthropic/claude-sonnet-4-6) or via ROBODOG_MODEL otherwise goes
    # to the wire raw and fails with an opaque "invalid model ID".
    model = _normalize_model_id(getattr(args, "model", None) or os.environ.get(
        "ROBODOG_MODEL", DEFAULT_MODEL))

    if backend == "gateway":
        made = make_gateway(None)
        if made:
            return made
        return EchoClient(script=DEMO_SCRIPT), "echo/demo (no gateway endpoint/keys)"
    if backend == "openrouter":
        made = make_openai_compat("OpenRouter", "https://openrouter.ai/api/v1", model)
        if made:
            return made
        return EchoClient(script=DEMO_SCRIPT), "echo/demo (no OpenRouter key)"
    if backend == "openai":
        made = make_openai_compat("OpenAI", "https://api.openai.com/v1", model)
        if made:
            return made
        return EchoClient(script=DEMO_SCRIPT), "echo/demo (no OpenAI key)"

    # auto: explicit gateway env wins, else OpenRouter (home), else gateway keys, else echo
    if os.environ.get("GATEWAY_ACCESS_KEY") or os.environ.get("GATEWAY_ENDPOINT"):
        made = make_gateway("env")
        if made:
            return made
    made = make_openai_compat("OpenRouter", "https://openrouter.ai/api/v1", model)
    if made:
        return made
    made = make_gateway("keepass")
    if made:
        return made
    return EchoClient(script=DEMO_SCRIPT), "echo/demo (no LLM keys found)"


HELP = """\
Commands:
  /help              show this help
  /model [name]      show or switch the model (live)
  /plan              toggle plan mode (read-only: agent proposes before editing)
  /status            show model, cwd, token usage
  /context           show transcript size breakdown
  /btw <question>    ask a quick side question (sees the convo, adds nothing to it)
  /compact           summarize the conversation to free context
  /clear             reset the conversation
  /rewind [n]        list checkpoints, or undo file changes from prompt n onward
  /resume [id]       list saved sessions, or resume one (id or 'latest')
  /init              generate a ROBODOG.md project guide via the agent
  /doctor            run environment diagnostics
  /keepass [init|set] create or inspect the encrypted key vault
  /skills            list custom commands, skills, and agents (.robodog/…)
  /todos             show the agent's task checklist
  /cwd [path]        show or change working directory
  /open <file|url>   open a file or URL with the OS default app
  /paste             multi-line paste (end with a lone . ) — works in any terminal
  /tools             list available tools
  /exit, /quit       leave

  /bg <prompt>       run a task on a background subagent
  /tasks             list background tasks
  /tail <id>         show recent output of a background task
  /kill <id>         stop a background task

  ! <command>        run a shell command directly (output is shared with the agent)
  @path/to/file      mention a file to inline it into your message

Anything else is sent to the agent, which can read/edit files, run commands,
and delegate to subagents.
"""

SLASH_COMMANDS = ["/help", "/model", "/plan", "/status", "/context", "/btw",
                  "/compact", "/clear", "/rewind", "/resume", "/init", "/doctor",
                  "/keepass",
                  "/skills", "/todos", "/cwd", "/open", "/paste", "/tools", "/bg", "/tasks", "/tail",
                  "/kill", "/exit", "/quit"]

INIT_PROMPT = (
    "Analyze this project (list the directory, read key files like README, "
    "package/config files, and main sources) and then WRITE a concise ROBODOG.md "
    "in the project root covering: what the project is, how to build/run/test it, "
    "code layout, and any conventions an AI coding agent should follow. "
    "Keep it under 120 lines."
)


def _expand_mentions(line: str, registry) -> str:
    """
    @-file mentions: '@src/foo.py' inlines the file into the message (clamped)
    and marks it read so the agent may edit it without a separate read_file.
    """
    import re
    out = line
    for m in re.finditer(r"@([\w./\\~-]+)", line):
        rel = m.group(1)
        p = Path(rel).expanduser()
        if not p.is_absolute():
            p = Path(registry.cwd) / rel
        if p.is_file():
            try:
                content = p.read_text(encoding="utf-8", errors="replace")[:20_000]
            except OSError:
                continue
            registry.read_paths.add(str(p))
            out += f"\n\n[content of {rel}]:\n{content}"
    return out


def _open_target(target: str, cwd: str) -> str:
    """Open a file or URL with the OS default handler. 'need to open things'."""
    import subprocess
    t = target.strip()
    is_url = t.startswith(("http://", "https://", "file://", "mailto:"))
    if not is_url:
        p = Path(t)
        if not p.is_absolute():
            p = Path(cwd) / t
        if not p.exists():
            return f"not found: {p}"
        t = str(p)
    try:
        if os.name == "nt":
            os.startfile(t)  # type: ignore[attr-defined]
        elif sys.platform == "darwin":
            subprocess.Popen(["open", t])
        else:
            subprocess.Popen(["xdg-open", t])
        return f"opened {t}"
    except Exception as exc:
        return f"could not open {t}: {exc}"


def _normalize_model_id(raw: str) -> str:
    """
    Clean up a model id typed at /model or --model:
      - drop an inline "# comment" and surrounding whitespace
      - fix the common dashed-version slip on OpenRouter Anthropic ids
        (anthropic/claude-opus-4-8 -> anthropic/claude-opus-4.8), which is the
        internal dash id, not the dotted id OpenRouter actually serves.
    """
    import re
    s = raw.split("#", 1)[0].strip().strip("'\"").strip()
    # claude-<name>-<major>-<minor>  ->  claude-<name>-<major>.<minor>
    s = re.sub(r"(claude-[a-z]+-\d+)-(\d+)", r"\1.\2", s)
    return s


def _mk_turn(role: str, content: str, tool_name: str = ""):
    try:
        from .loop import Turn
    except ImportError:
        from robodog_terminal.loop import Turn
    return Turn(role, content, tool_name=tool_name)


def _make_checkpointer():
    try:
        from .checkpoint import Checkpointer
    except ImportError:
        from robodog_terminal.checkpoint import Checkpointer
    import time as _t
    session_dir = Path.home() / ".robodog" / "checkpoints" / _t.strftime("%Y%m%d-%H%M%S")
    return Checkpointer(session_dir)


INSTRUCTION_FILENAMES = (
    "CLAUDE.md", "CLAUDE.local.md", ".claude/CLAUDE.md",
    "ROBODOG.md", ".robodog.md", "ROBODOG.local.md", ".robodog/ROBODOG.md",
)


def _load_project_instructions(cwd: str) -> str:
    """
    Load agent instruction files into the system context, agentic:
      1. global user file  (~/.robodog/CLAUDE.md or ~/.robodog/ROBODOG.md)
      2. every CLAUDE.md / ROBODOG.md / .robodog.md walking from filesystem
         root DOWN to cwd (so the closest/most-specific file wins by coming last)
    Both CLAUDE.md and ROBODOG.md are honored so existing an agentic coding terminal repos work
    unchanged and robodog-specific overrides are possible.
    """
    parts = []
    seen = set()

    def _add(p: Path, label: str):
        rp = str(p.resolve())
        if rp in seen or not p.is_file():
            return
        seen.add(rp)
        try:
            text = p.read_text(encoding="utf-8", errors="replace")[:8000]
        except OSError:
            return
        if text.strip():
            parts.append(f"INSTRUCTIONS ({label}):\n{text}")

    # 1) global user instructions
    for name in ("CLAUDE.md", "ROBODOG.md"):
        _add(Path.home() / ".robodog" / name, f"~/.robodog/{name}")

    # 2) root -> cwd walk (closest last)
    cwd_path = Path(cwd).resolve()
    chain = list(reversed([cwd_path, *cwd_path.parents]))
    for d in chain:
        for name in INSTRUCTION_FILENAMES:
            _add(d / name, str((d / name)))
    return "\n\n".join(parts)


def _load_local_config():
    """
    Load ~/.robodog/config.env (KEY=VALUE lines) into the environment. This is a
    user-local, gitignored file — NOT shipped — so personal paths (e.g. the
    KeePass DB location) live here instead of in the code. Existing env vars win.
    """
    cfg = Path.home() / ".robodog" / "config.env"
    try:
        if cfg.exists():
            for line in cfg.read_text(encoding="utf-8", errors="replace").splitlines():
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))
    except Exception:
        pass


def main(argv=None) -> int:
    _load_local_config()
    parser = argparse.ArgumentParser(description="Robodog Terminal Mode")
    # -------- backend / model ------------------------------------------
    parser.add_argument("--echo", action="store_true", help="use offline demo backend")
    parser.add_argument("--backend", default="auto",
                        choices=["auto", "gateway", "openrouter", "openai", "echo"],
                        help="LLM backend (default: auto — the gateway env > OpenRouter keepass > the gateway keepass > echo)")
    parser.add_argument("--model", default=None,
                        help="model for openai-compat backends (default anthropic/claude-sonnet-4.6)")
    parser.add_argument("--gateway-endpoint", default=None,
                        help="override the runPixel gateway endpoint URL")
    parser.add_argument("--gateway-engine", default=None,
                        help="override the gateway model engine id")
    # -------- headless / print mode ------------------------------------
    parser.add_argument("-p", "--print", dest="print_prompt", default=None,
                        metavar="PROMPT",
                        help="headless mode: run one agentic turn for PROMPT and exit")
    parser.add_argument("--output-format", default="text", choices=["text", "json"],
                        help="headless output format (default text)")
    # -------- loop tuning ----------------------------------------------
    parser.add_argument("--cwd", default=os.getcwd(), help="working directory")
    parser.add_argument("--max-iterations", type=int, default=25,
                        help="max agentic steps per turn (default 25)")
    parser.add_argument("--max-tokens", type=int, default=8192,
                        help="max completion tokens per LLM call (default 8192)")
    parser.add_argument("--temperature", type=float, default=0.3)
    parser.add_argument("--max-transcript-chars", type=int, default=120_000,
                        help="auto-trim threshold for the running transcript")
    # -------- context / prompt ----------------------------------------
    parser.add_argument("--append-system-prompt", default=None, metavar="TEXT",
                        help="extra instructions appended to the system context")
    parser.add_argument("--no-instructions", action="store_true",
                        help="skip loading CLAUDE.md/ROBODOG.md from cwd")
    # -------- tool gating ----------------------------------------------
    parser.add_argument("--allowed-tools", default=None, metavar="LIST",
                        help="comma-separated tool allowlist (e.g. read_file,glob,grep)")
    parser.add_argument("--disallowed-tools", default=None, metavar="LIST",
                        help="comma-separated tools to remove (e.g. bash)")
    # -------- misc ------------------------------------------------------
    parser.add_argument("--permission-mode", default="yolo", choices=["yolo", "plan"],
                        help="start in plan mode (read-only, propose first) or yolo (default)")
    parser.add_argument("--guard", default="warn", choices=["warn", "confirm"],
                        help="destructive-command handling: warn+proceed (default) or confirm")
    parser.add_argument("--no-verify-edits", action="store_true",
                        help="disable automatic post-edit syntax checking")
    parser.add_argument("--test-command", default=None,
                        help="explicit test command for the run_tests tool")
    parser.add_argument("--resume", default=None, metavar="ID",
                        help="resume a saved session by id (or 'latest')")
    parser.add_argument("--continue", dest="continue_latest", action="store_true",
                        help="resume the most recent session in this project")
    parser.add_argument("--editor", default=None,
                        choices=["file", "vscode", "cursor", "vscodium"],
                        help="editor for clickable file:line jumps (default: file:// "
                             "or $ROBODOG_EDITOR)")
    parser.add_argument("--verbose", action="store_true",
                        help="print full tool results, not one-line summaries")
    parser.add_argument("--version", action="store_true", help="print version and exit")
    args = parser.parse_args(argv)

    if args.version:
        try:
            from . import __version__
        except ImportError:
            from robodog_terminal import __version__
        print(f"robodog-terminal {__version__}")
        return 0
    if args.gateway_endpoint:
        os.environ["GATEWAY_ENDPOINT"] = args.gateway_endpoint
    if args.gateway_engine:
        os.environ["GATEWAY_ENGINE"] = args.gateway_engine

    cwd = str(Path(args.cwd).resolve())
    headless = args.print_prompt is not None
    # SkillsRegistry is created below; build the completer list after discovery.
    ui = UI(model_name="…", cwd=cwd, commands=SLASH_COMMANDS, stderr=headless,
            editor=args.editor)
    # agentic visible retry line: "API error · Retrying in Ns · attempt n/N"
    def on_retry(a, m, d, r):
        ui.spinner_stop()
        ui.dim(f"  ⚠ API error ({r}) · Retrying in {d:.0f}s · attempt {a}/{m}")
    client, model_label = build_backend(args, on_retry=on_retry)
    ui.model_name = model_label
    registry = default_registry(cwd=cwd)

    # Tool gating flags.
    if args.allowed_tools:
        allowed = {t.strip() for t in args.allowed_tools.split(",") if t.strip()}
        registry._tools = {k: v for k, v in registry._tools.items() if k in allowed}
    if args.disallowed_tools:
        for t in args.disallowed_tools.split(","):
            registry._tools.pop(t.strip(), None)

    # Safety layer: per-prompt file checkpoints (/rewind) + diff previews.
    checkpointer = _make_checkpointer()
    registry.checkpointer = checkpointer
    registry.on_diff = lambda path, diff: (ui.spinner_stop(), ui.diff(path, diff))
    # Live-stream long-running command output (streaming bash). Bounded +
    # blank-collapsed by the UI; the model still gets the full text.
    registry.on_bash_line = ui.bash_line
    if args.permission_mode == "plan":
        registry.mode = "plan"
    registry.guard = args.guard
    registry.verify_edits = not args.no_verify_edits
    registry.test_command = args.test_command

    def _confirm_danger(command, reason):
        if headless:
            return False  # never run destructive commands unattended
        ui.spinner_stop()
        ui.error(f"potentially destructive command: {command}")
        try:
            return input("  run it? [y/N]: ").strip().lower() in ("y", "yes")
        except (EOFError, KeyboardInterrupt):
            return False
    registry.on_confirm = _confirm_danger

    # Background task manager (bash + subagents).
    try:
        from .background import BackgroundManager
    except ImportError:
        from robodog_terminal.background import BackgroundManager
    manager = BackgroundManager()

    # Discover user extensions: custom commands, agents, skills (.robodog/…).
    try:
        from .skills import SkillsRegistry
        from . import agents as _agents_mod
    except ImportError:
        from robodog_terminal.skills import SkillsRegistry
        from robodog_terminal import agents as _agents_mod
    skills = SkillsRegistry(cwd=cwd)
    try:
        skills.discover()
        # Merge file-defined custom agents into the built-in agent-type table.
        _agents_mod.AGENT_TYPES.update(skills.agent_type_overrides())
    except Exception as exc:  # never let a bad skill file break startup
        ui.dim(f"(skills discovery skipped: {exc})")

    # Subagents: let the model delegate scoped work to child loops.
    def on_child_event(kind, data):
        if kind == "tool_start":
            ui.dim(f"      ⚙ {data['name']} {str(data.get('args', {}).get('command') or data.get('args', {}).get('path') or '')[:60]}")
    if "agent" not in (args.disallowed_tools or ""):
        register_agent_tool(registry, client, on_child_event=on_child_event,
                            manager=manager)

    def on_event(kind, data):
        if kind == "llm_start":
            ui.spinner_start(f"✳ Thinking… (step {data['iteration']}, ctrl-c to cancel)")
        elif kind == "llm_done":
            ui.spinner_stop()
            if data.get("prose") and data.get("n_calls"):
                # interim reasoning when the model both talks AND calls tools
                ui.assistant(data["prose"])
        elif kind == "tool_start":
            ui.spinner_stop()
            ui.tool_call(data["name"], data["args"])
        elif kind == "tool_done":
            ui.stream_footer()      # report any streamed lines the display capped
            if args.verbose:
                ui.dim(data["result"])
            else:
                ui.tool_result(data["name"], data["result"])

    # Agent task checklist + ask-user tool (headless auto-answers itself).
    try:
        from .tasklist import TaskChecklist, register_task_tools, register_ask_tool
    except ImportError:
        from robodog_terminal.tasklist import TaskChecklist, register_task_tools, register_ask_tool
    checklist = TaskChecklist()
    checklist.on_change = lambda: (ui.spinner_stop(),
                                   [ui.dim(f"  {ln}") for ln in checklist.render_lines()[-6:]])
    register_task_tools(registry, checklist)

    def ask_fn(question, options):
        if headless:
            return options[0] + " (auto-selected: non-interactive)"
        ui.spinner_stop()
        ui.info(f"\n❓ {question}")
        for i, opt in enumerate(options, 1):
            ui.info(f"  {i}. {opt}")
        while True:
            try:
                choice = input("  choose [number]: ").strip()
                idx = int(choice) - 1
                if 0 <= idx < len(options):
                    return options[idx]
            except (ValueError, EOFError):
                pass
            ui.error("enter a number from the list")
    register_ask_tool(registry, ask_fn)

    # Session persistence (JSONL per project, like a modern agentic terminal).
    try:
        from .sessions import SessionStore
    except ImportError:
        from robodog_terminal.sessions import SessionStore
    store = SessionStore(project_dir=cwd)
    session_id = [None]  # boxed: /resume swaps it

    system_suffix = "" if args.no_instructions else _load_project_instructions(cwd)
    if args.append_system_prompt:
        system_suffix = (system_suffix + "\n\n" + args.append_system_prompt).strip()
    loop = AgentLoop(client, registry, max_iterations=args.max_iterations,
                     max_tokens=args.max_tokens, temperature=args.temperature,
                     on_event=on_event, system_suffix=system_suffix)
    loop.max_transcript_chars = args.max_transcript_chars

    # ---- headless print mode (-p) ------------------------------------
    if headless:
        try:
            result = loop.run(args.print_prompt)
        except Exception as exc:
            if args.output_format == "json":
                print(json.dumps({"error": f"{type(exc).__name__}: {exc}"}))
            else:
                print(f"error: {type(exc).__name__}: {exc}", file=sys.stderr)
            return 1
        if args.output_format == "json":
            print(json.dumps({
                "result": result.final_text,
                "iterations": result.iterations,
                "total_tokens": result.total_tokens,
                "model": model_label,
            }))
        else:
            print(result.final_text)
        return 0

    ui.welcome()
    if model_label.startswith("echo"):
        ui.dim("(offline echo backend — set GATEWAY_* env vars for a self-hosted runPixel gateway)")
    if system_suffix:
        ui.dim("(loaded project instructions: CLAUDE.md/ROBODOG.md)")
    if skills.commands or skills.agents or skills.skills:
        ui.dim(f"(extensions: {skills.summary()} — custom /commands, skills, and agents)")
        # extend the input completer with discovered /commands and /skills
        try:
            extra = skills.command_names() + skills.skill_names()
            if ui._session is not None:
                from prompt_toolkit.completion import WordCompleter
                ui._session.completer = WordCompleter(
                    sorted(set(SLASH_COMMANDS + extra)), sentence=True)
        except Exception:
            pass
    if registry.mode == "plan":
        ui.dim("📋 plan mode ON — agent is read-only until you approve a plan")
    prompt_count = 0
    prompt_texts = []

    # --continue / --resume at startup
    startup_resume = ("latest" if args.continue_latest else args.resume)
    if startup_resume:
        sid = store.latest() if startup_resume == "latest" else startup_resume
        data = store.load(sid) if sid else None
        if data:
            for t in data["turns"]:
                loop.history.append(_mk_turn(t["role"], t["content"],
                                             t.get("tool_name", "")))
            session_id[0] = sid
            ui.dim(f"(resumed session {sid} — {len(data['turns'])} turns)")
        else:
            ui.dim("(no session to resume — starting fresh)")

    # Notifier: live "✔ bg1 done" lines + status-bar task count. patch_stdout
    # (inside ui.prompt) makes printing from this thread safe mid-typing.
    import threading as _threading

    def _notifier():
        while True:
            _threading.Event().wait(1.5)
            ui.bg_running = manager.running_count()
            for note in manager.drain_notifications():
                ui.dim(note)
    _threading.Thread(target=_notifier, daemon=True).start()

    # Mid-turn interactivity state.
    try:
        from .turnrunner import TurnRunner, make_key_source
    except ImportError:
        from robodog_terminal.turnrunner import TurnRunner, make_key_source
    pending_prompts = []      # follow-ups queued while a turn ran
    detached = [None]         # a TurnRunner still running in the background
    key_source = make_key_source()
    # startup --resume may have preloaded history; don't re-persist those turns.
    persisted = [len(loop.history)]   # count of loop.history turns already saved

    def finalize_and_show(result):
        """Persist new turns, update counters, and render the answer."""
        if result is None:
            return
        if session_id[0] is None:
            session_id[0] = store.new_session()
        for t in loop.history[persisted[0]:]:
            store.append_turn(session_id[0], t.role, t.content, t.tool_name)
        persisted[0] = len(loop.history)
        store.set_meta(session_id[0], model=ui.model_name,
                       total_tokens=ui.total_tokens + result.total_tokens)
        ui.total_tokens += result.total_tokens
        ui.context_pct = min(99, loop.transcript_chars() * 100
                             // loop.max_transcript_chars)
        ui.assistant(result.final_text)
        dur = getattr(result, "duration", 0.0)
        ui.dim(f"[{result.iterations} steps · {result.total_tokens} tok · {dur:.1f}s]")

    while True:
        # Drain any queued follow-up prompts before reading new input.
        if pending_prompts:
            line = pending_prompts.pop(0)
            preview = line.replace("\n", " ")
            ui.dim(f"› (queued) {preview[:70]}"
                   + (f" … [{line.count(chr(10)) + 1} lines]" if "\n" in line else ""))
        else:
            try:
                line = ui.prompt()
            except (EOFError, KeyboardInterrupt):
                ui.info("\nbye")
                return 0
        # Strip lone UTF-16 surrogates from clipboard pastes at the boundary, so
        # they can't crash any downstream utf-8 encode (HTTP body, session JSONL).
        line = clean_text(line)
        # Confirm a multi-line paste was captured whole (native bracketed paste).
        if line and "\n" in line:
            ui.dim(f"  [pasted {line.count(chr(10)) + 1} lines]")
        if not line:
            continue

        # ---- ! shell passthrough (output shared with the agent) -------
        if line.startswith("!"):
            command = line[1:].strip()
            if not command:
                continue
            result = registry.execute("bash", {"command": command})
            ui.info(result)
            loop.history.append(_mk_turn("user", "I ran a shell command myself:"))
            loop.history.append(_mk_turn("tool", result, "bash"))
            continue

        if line.startswith("/"):
            cmd, _, rest = line[1:].partition(" ")
            cmd = cmd.lower().strip()
            rest = rest.strip()
            if cmd in ("exit", "quit", "q"):
                ui.info("bye")
                return 0
            elif cmd == "help":
                ui.info(HELP)
            elif cmd == "status":
                ui.print_status()
            elif cmd == "context":
                chars = loop.transcript_chars()
                ui.info(f"transcript: {len(loop.history)} turns · ~{chars // 4} tokens "
                        f"({chars} chars) · trim threshold {loop.max_transcript_chars} chars")
            elif cmd == "btw":
                if not rest:
                    ui.error("usage: /btw <question>")
                    continue
                # Side question: full visibility into the conversation, no tools,
                # single answer, and it does NOT touch the conversation history.
                convo = loop._render_prompt() if loop.history else "(no conversation yet)"
                side_prompt = (
                    "You are answering a quick SIDE QUESTION about the ongoing "
                    "coding session below. Answer briefly and directly. Do NOT "
                    "use tools or emit <tool> blocks — just reply in prose.\n\n"
                    f"=== conversation so far ===\n{convo}\n\n"
                    f"=== side question ===\n{rest}")
                ui.spinner_start("✳ (side question…)")
                try:
                    ans = client.complete(side_prompt, max_tokens=1500).text
                except Exception as exc:
                    ui.spinner_stop()
                    ui.error(f"btw failed: {exc}")
                    continue
                ui.spinner_stop()
                ui.info("[btw — not saved to the conversation]")
                ui.assistant(ans)
            elif cmd == "compact":
                if not loop.history:
                    ui.info("nothing to compact.")
                    continue
                ui.spinner_start("✳ Compacting conversation…")
                try:
                    transcript = loop._render_prompt()
                    summary = client.complete(
                        "Summarize this coding-session transcript into a compact "
                        "brief a coding agent can resume from. Keep: the goal, "
                        "decisions, files touched, current state, next steps.\n\n"
                        + transcript,
                        max_tokens=2000).text
                finally:
                    ui.spinner_stop()
                loop.history.clear()
                loop.history.append(_mk_turn("user", f"[conversation summary]\n{summary}"))
                persisted[0] = len(loop.history)
                ui.info("conversation compacted.")
            elif cmd == "clear":
                loop.history.clear()
                persisted[0] = 0
                ui.total_tokens = 0
                ui.info("conversation cleared.")
            elif cmd == "rewind":
                marks = checkpointer.markers()
                if not marks:
                    ui.info("no file changes recorded yet.")
                elif not rest:
                    ui.info("checkpoints (use /rewind <n> to undo from prompt n onward):")
                    for m in sorted(marks):
                        label = prompt_texts[m][:60] if m < len(prompt_texts) else "?"
                        ui.info(f"  {m}: {marks[m]} file change(s) — “{label}”")
                else:
                    try:
                        n = int(rest)
                    except ValueError:
                        ui.error("usage: /rewind <prompt-number>")
                        continue
                    actions = checkpointer.restore(n)
                    for a in actions:
                        ui.info(f"  ↩ {a}")
                    ui.info(f"rewound {len(actions)} file(s) to before prompt {n}.")
            elif cmd == "model":
                if rest:
                    want = _normalize_model_id(rest)
                    if want != rest:
                        ui.dim(f"  (interpreting as {want})")
                    # Live model switch: rebuild the client on the same backend.
                    try:
                        args.model = want
                        new_client, new_label = build_backend(args, on_retry=on_retry)
                        loop.client = new_client
                        client = new_client
                        ui.model_name = new_label
                        ui.info(f"switched to {new_label}")
                    except Exception as exc:
                        ui.error(f"model switch failed: {exc}")
                else:
                    ui.info(f"model: {ui.model_name}")
                    ui.dim("  openrouter: anthropic/claude-opus-4.8 · "
                           "anthropic/claude-sonnet-4.6 · openai/gpt-4o · "
                           "google/gemini-2.0-flash-001")
                    ui.dim("  (tip: OpenRouter IDs use dots, e.g. -4.8 not -4-8)")
            elif cmd == "plan":
                registry.mode = "plan" if registry.mode != "plan" else "yolo"
                if registry.mode == "plan":
                    ui.info("📋 plan mode ON — read-only, agent will propose first")
                else:
                    ui.info("⏵ plan mode OFF — YOLO")
            elif cmd == "init":
                prompt_texts.append("/init")
                checkpointer.set_marker(prompt_count)
                prompt_count += 1
                try:
                    result = loop.run(INIT_PROMPT)
                    ui.assistant(result.final_text)
                except KeyboardInterrupt:
                    ui.spinner_stop()
                    ui.dim("[interrupted]")
            elif cmd == "doctor":
                try:
                    from .doctor import run_doctor, format_report
                except ImportError:
                    from robodog_terminal.doctor import run_doctor, format_report
                _doc_model = _normalize_model_id(
                    getattr(args, "model", None)
                    or os.environ.get("ROBODOG_MODEL", DEFAULT_MODEL))
                ui.info(format_report(run_doctor(
                    ui.cwd, backend=getattr(args, "backend", "") or "",
                    model=_doc_model)))
            elif cmd == "keepass":
                try:
                    from .keepass_setup import handle as _kp_handle
                except ImportError:
                    from robodog_terminal.keepass_setup import handle as _kp_handle
                _kp_ok, _kp_msg = _kp_handle(rest)
                (ui.info if _kp_ok else ui.error)(_kp_msg)
            elif cmd == "todos":
                lines = checklist.render_lines()
                ui.info("\n".join(lines) if lines else "(no tasks)")
            elif cmd == "resume":
                sessions = store.list_sessions()
                if not rest:
                    if not sessions:
                        ui.info("no saved sessions.")
                    for s in sessions[:15]:
                        ui.info(f"  {s['id']}  {s.get('turn_count', 0):3} turns  "
                                f"{(s.get('name') or s.get('first_prompt') or '')[:60]}")
                    ui.dim("  /resume <id>  or  /resume latest")
                else:
                    sid = store.latest() if rest == "latest" else rest
                    data = store.load(sid) if sid else None
                    if not data:
                        ui.error(f"session not found: {rest}")
                    else:
                        loop.history.clear()
                        for t in data["turns"]:
                            loop.history.append(_mk_turn(
                                t["role"], t["content"], t.get("tool_name", "")))
                        session_id[0] = sid
                        persisted[0] = len(loop.history)
                        ui.info(f"resumed {sid} ({len(data['turns'])} turns).")
            elif cmd == "cwd":
                if rest:
                    newp = Path(rest).expanduser().resolve()
                    if newp.is_dir():
                        ui.cwd = str(newp)
                        registry.cwd = newp
                        ui.info(f"cwd -> {newp}")
                    else:
                        ui.error(f"not a directory: {newp}")
                else:
                    ui.info(ui.cwd)
            elif cmd == "tools":
                for name in registry._tools:  # noqa: SLF001 (intentional)
                    ui.info(f"  {name}")
            elif cmd == "open":
                if not rest:
                    ui.error("usage: /open <file-or-url>")
                else:
                    ui.info(_open_target(rest, ui.cwd))
            elif cmd == "paste":
                # Reliable multi-line entry for terminals where bracketed paste
                # doesn't capture the whole block. Paste, then end with a lone '.'.
                ui.info("paste your text, then a line with only '.' to submit "
                        "(Ctrl-C to cancel):")
                buf = []
                while True:
                    try:
                        raw = input()
                    except (EOFError, KeyboardInterrupt):
                        buf = None
                        break
                    if raw.strip() == ".":
                        break
                    buf.append(raw)
                if not buf:
                    ui.info("(paste cancelled)")
                    continue
                block = "\n".join(buf).strip()
                if block:
                    msg = f"{rest}\n{block}" if rest else block
                    pending_prompts.insert(0, msg)   # run it as a normal turn
                else:
                    ui.info("(nothing pasted)")
            elif cmd == "skills":
                if not (skills.commands or skills.skills or skills.agents):
                    ui.info("no extensions found. Add files under "
                            ".robodog/commands, .robodog/skills, .robodog/agents.")
                else:
                    for n, c in sorted(skills.commands.items()):
                        ui.info(f"  /{n}  (command) — {c.description or c.argument_hint}")
                    for n, s in sorted(skills.skills.items()):
                        ui.info(f"  /{n}  (skill) — {s.description}")
                    for n, a in sorted(skills.agents.items()):
                        ui.info(f"  @{n}  (agent) — {a.description}")
            elif skills.get_command(cmd) is not None:
                # Custom slash command: render template + run as an agent turn.
                tmpl = skills.get_command(cmd)
                prompt = tmpl.render(rest, ui.cwd)
                checkpointer.set_marker(prompt_count)
                prompt_texts.append(line)
                prompt_count += 1
                try:
                    result = loop.run(prompt)
                    ui.assistant(result.final_text)
                    ui.total_tokens += result.total_tokens
                except KeyboardInterrupt:
                    ui.spinner_stop()
                    ui.dim("[interrupted]")
            elif skills.get_skill(cmd) is not None:
                # Skill: inject its instructions into the conversation as context.
                sk = skills.get_skill(cmd)
                loop.history.append(_mk_turn("user",
                    f"[skill: {sk.name}]\n{sk.body}"
                    + (f"\n\nUser input: {rest}" if rest else "")))
                ui.info(f"loaded skill '{sk.name}' into context.")
            elif cmd == "bg":
                if not rest:
                    ui.error("usage: /bg <task for a background subagent>")
                else:
                    ui.info(registry.execute(
                        "agent", {"prompt": rest, "background": "true"}))
            elif cmd == "tasks":
                tasks = manager.list()
                if not tasks:
                    ui.info("no background tasks.")
                for t in tasks:
                    dur = f"{(t.ended or __import__('time').time()) - t.started:.0f}s"
                    ui.info(f"  {t.id}  [{t.status:7}]  {t.kind:5}  {dur:>5}  {t.title}")
            elif cmd == "tail":
                ui.info(manager.output(rest.strip() or "bg1"))
            elif cmd == "kill":
                if not rest:
                    ui.error("usage: /kill <task-id>")
                else:
                    ui.info(manager.kill(rest.strip()))
            else:
                ui.error(f"unknown command: /{cmd} (try /help)")
            continue

        # ---- run the agent -------------------------------------------
        # A previously-backgrounded turn shares loop.history, so wait for it to
        # finish before starting a new agent turn (keeps the transcript sane).
        if detached[0] is not None and detached[0].running():
            ui.dim("  (waiting for the backgrounded turn to finish…)")
            detached[0].join()
        if detached[0] is not None:
            finalize_and_show(detached[0].result)
            detached[0] = None

        checkpointer.set_marker(prompt_count)
        prompt_texts.append(line)
        prompt_count += 1
        expanded = _expand_mentions(line, registry)
        if session_id[0] is None:
            session_id[0] = store.new_session()

        runner = TurnRunner(loop)
        runner.start(expanded, _threading.Event())
        if not headless and sys.stdin.isatty():
            ui.dim("  (Ctrl+C cancel · Ctrl+B background · type + Enter to queue)")
        try:
            outcome = runner.watch(key_source)
        except KeyboardInterrupt:
            outcome = runner.watch(lambda: "cancel")
        except Exception as exc:
            ui.spinner_stop()
            ui.error(f"{type(exc).__name__}: {exc}")
            continue

        pending_prompts.extend(outcome.queued)
        if outcome.status == "backgrounded":
            ui.dim("  (turn moved to background — you'll be notified when it finishes)")
            detached[0] = runner
            ui.bg_running = manager.running_count() + 1
            continue
        if outcome.status == "cancelled":
            ui.spinner_stop()
            ui.dim("\n[turn cancelled — context kept; type to continue]")
            continue

        result = outcome.result
        finalize_and_show(result)

        # Plan-mode approval flow: after a read-only plan, offer to implement.
        if registry.mode == "plan" and result.final_text.strip():
            try:
                ans = input("\n  approve plan? [y = implement / n = keep planning]: ").strip().lower()
            except (EOFError, KeyboardInterrupt):
                ans = "n"
            if ans in ("y", "yes"):
                registry.mode = "yolo"
                ui.info("⏵ implementing…")
                checkpointer.set_marker(prompt_count)
                prompt_texts.append("(approved plan)")
                prompt_count += 1
                try:
                    result2 = loop.run("The user approved your plan. Implement it now.")
                    finalize_and_show(result2)
                except KeyboardInterrupt:
                    ui.spinner_stop()
                    ui.dim("[interrupted]")
                registry.mode = "plan"

        # Auto-compact near the context ceiling (an agentic coding terminal behavior).
        if loop.transcript_chars() > int(loop.max_transcript_chars * 0.9):
            ui.dim("(auto-compacting conversation…)")
            try:
                transcript = loop._render_prompt()
                summary = client.complete(
                    "Summarize this coding-session transcript into a compact brief "
                    "a coding agent can resume from. Keep: goal, decisions, files "
                    "touched, current state, next steps.\n\n" + transcript,
                    max_tokens=2000).text
                loop.history.clear()
                loop.history.append(_mk_turn("user", f"[conversation summary]\n{summary}"))
                persisted[0] = len(loop.history)
            except Exception as exc:
                ui.dim(f"(auto-compact skipped: {exc})")


if __name__ == "__main__":
    raise SystemExit(main())
