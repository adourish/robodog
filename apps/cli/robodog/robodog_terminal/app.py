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
    from .ui import UI
    from .core import build_core
except ImportError:
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    from robodog_terminal.llm_client import EchoClient, GatewayClient, LLMClient, OpenAICompatClient, clean_text
    from robodog_terminal.ui import UI
    from robodog_terminal.core import build_core

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
        # ROBODOG_KEEPASS_LLM_ENTRY overrides which vault entry supplies the key
        # + base URL, so an existing entry (e.g. 'SEMOSS-Elsa-Dev') can be used
        # without renaming it to the backend's default title.
        entry_title = os.environ.get("ROBODOG_KEEPASS_LLM_ENTRY") or entry_title
        key = os.environ.get("ROBODOG_LLM_KEY")
        url = os.environ.get("ROBODOG_LLM_URL", default_url)
        if not key:
            user, key, kp_url = _load_keepass_entry(entry_title)
            url = os.environ.get("ROBODOG_LLM_URL") or kp_url or default_url
            # Some OpenAI-compatible gateways (SEMOSS/ELSA) want the key as
            # 'access:secret'. When the entry splits them across the username
            # and password fields, ROBODOG_LLM_KEY_FORMAT=user:pass joins them.
            fmt = (os.environ.get("ROBODOG_LLM_KEY_FORMAT") or "").strip().lower()
            if fmt in ("user:pass", "user:password") and user and key and ":" not in key:
                key = f"{user}:{key}"
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
  /config [init]     show effective permission/guard config, or write a starter
                     settings.json ('/config init [--global] [--force]')
  (shift+tab)        cycle permission mode: default -> accept edits -> plan ->
                     bypass permissions (shown in the bottom status bar)
  /theme [name]      show or switch the color theme: default | high-contrast | mono | pip-boy
  /status            show model, cwd, token usage
  /context           show transcript size breakdown
  /stats             session tokens, context %, turns, files read, uptime
  /copy              copy the last answer to the clipboard
  /save <file>       write the last answer to a file
  /net-writes [mode] remote-write approvals: confirm (default) | allow | deny
  /btw <question>    ask a quick side question (sees the convo, adds nothing to it);
                     works mid-turn too — answered in the background, e.g. "are you stuck?"
  /compact           summarize the conversation to free context
  /clear             reset the conversation
  /rewind [n]        list checkpoints, or undo file changes from prompt n onward
  /resume [id]       list saved sessions, or resume one (id or 'latest')
  /init              generate a ROBODOG.md project guide via the agent
  /doctor            run environment diagnostics
  /cert [host]       capture a gateway's TLS chain -> REQUESTS_CA_BUNDLE (private CA)
  /test [agents [N] [big]] reachability probe; `agents N big` stress-tests an N-way fan-out
  /keepass [init|set] create or inspect the encrypted key vault
  /skills            list custom commands, skills, and agents (.robodog/…)
  /todos             show the agent's task checklist
  /cwd [path]        show or change working directory
  /open <file|url>   open a file or URL with the OS default app
  /paste             multi-line paste (end with a lone . ) — works in any terminal
  /tools             list available tools
  /verbose           toggle full tool/subagent output (default: compact summaries)
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

SLASH_COMMANDS = ["/help", "/model", "/theme", "/plan", "/config", "/status", "/context", "/stats",
                  "/net-writes", "/copy", "/save", "/btw",
                  "/compact", "/clear", "/rewind", "/resume", "/init", "/doctor",
                  "/keepass", "/cert", "/test",
                  "/skills", "/todos", "/cwd", "/open", "/paste", "/tools", "/verbose",
                  "/bg", "/tasks", "/tail",
                  "/kill", "/exit", "/quit"]

INIT_PROMPT = (
    "Analyze this project (list the directory, read key files like README, "
    "package/config files, and main sources) and then WRITE a concise ROBODOG.md "
    "in the project root covering: what the project is, how to build/run/test it, "
    "code layout, and any conventions an AI coding agent should follow. "
    "Keep it under 120 lines."
)


def build_btw_prompt(convo: str, question: str, running: bool = False) -> str:
    """Assemble the side-question prompt for /btw. `running=True` (mid-turn use)
    tells the model the session may still be working, so 'are you stuck?'-style
    check-ins get a sensible answer. Never touches the real conversation."""
    note = (" (which may STILL BE RUNNING right now)" if running else "")
    return (
        f"You are answering a quick SIDE QUESTION about the ongoing coding "
        f"session below{note}. Answer briefly and directly. Do NOT use tools or "
        f"emit <tool> blocks — just reply in prose.\n\n"
        f"=== conversation so far ===\n{convo}\n\n"
        f"=== side question ===\n{question}")


def _expand_mentions(line: str, registry) -> str:
    """
    @-mentions:
      '@src/foo.py'  -> inlines the file (clamped) and marks it read so the agent
                        may edit it without a separate read_file.
      '@src/'  or a directory -> lists the files under it (pruned + capped) so the
                        agent gets an overview without a tool call.
    """
    import os
    import re
    try:
        from .tools import EXCLUDE_DIRS
    except ImportError:
        from robodog_terminal.tools import EXCLUDE_DIRS
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
            registry._mark_read(p)
            out += f"\n\n[content of {rel}]:\n{content}"
        elif p.is_dir():
            files, capped = [], False
            for dirpath, dirnames, filenames in os.walk(str(p)):
                dirnames[:] = [d for d in dirnames
                               if d not in EXCLUDE_DIRS and not d.endswith(".egg-info")]
                for fn in sorted(filenames):
                    full = Path(dirpath) / fn
                    try:
                        files.append(str(full.relative_to(p)).replace("\\", "/"))
                    except ValueError:
                        files.append(fn)
                    if len(files) >= 200:
                        capped = True
                        break
                if capped:
                    break
            listing = "\n".join(files) or "(empty)"
            more = "\n… (list truncated at 200)" if capped else ""
            out += f"\n\n[files under {rel.rstrip('/')}/ ]:\n{listing}{more}"
    return out


def _copy_to_clipboard(text: str) -> bool:
    """Copy `text` to the OS clipboard via the platform tool (no extra dep).
    Returns True on success. Windows: clip; macOS: pbcopy; Linux: xclip/xsel/wl-copy."""
    import subprocess
    if os.name == "nt":
        cmds = [["clip"]]
    elif sys.platform == "darwin":
        cmds = [["pbcopy"]]
    else:
        cmds = [["wl-copy"], ["xclip", "-selection", "clipboard"], ["xsel", "-b", "-i"]]
    data = text.encode("utf-8", "replace")
    for cmd in cmds:
        try:
            p = subprocess.run(cmd, input=data, timeout=5)
            if p.returncode == 0:
                return True
        except (OSError, subprocess.SubprocessError):
            continue
    return False


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


def _blocking_threads() -> list:
    """Non-daemon, non-main threads still alive — these BLOCK a clean exit.
    Parallel subagents run in a ThreadPoolExecutor whose workers are non-daemon
    and get joined at interpreter shutdown; if one is wedged in a network retry,
    a normal exit hangs on that join. (TurnRunner workers, the rich spinner, and
    patch_stdout's flush thread are all daemon, so they don't count.)"""
    import threading
    main = threading.main_thread()
    return [t for t in threading.enumerate()
            if t is not main and t.is_alive() and not t.daemon]


def _hard_quit(ui=None, code: int = 0) -> int:
    """Print 'bye', then exit. If worker threads would block a clean shutdown
    (a stuck subagent fan-out), terminate immediately via os._exit so the user
    actually gets out — "bye" printed but hung otherwise. Sessions persist
    per-turn, so nothing committed is lost. If nothing is blocking, returns the
    code so the caller can `return` cleanly (keeps in-process/test use sane)."""
    try:
        if ui is not None:
            try:
                ui.reset_typing()
                ui.spinner_stop()
            except Exception:
                pass
            ui.info("\nbye")
        else:
            print("\nbye")
        sys.stdout.flush()
        sys.stderr.flush()
    except Exception:
        pass
    if _blocking_threads():
        os._exit(code)
    return code


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
    parser.add_argument("--permission-mode", default=None, choices=["yolo", "plan"],
                        help="start in plan mode (read-only, propose first) or yolo. "
                             "Default: settings.json 'defaults.permissionMode', else yolo.")
    parser.add_argument("--guard", default=None, choices=["warn", "confirm"],
                        help="destructive-command handling: warn+proceed or confirm. "
                             "Default: settings.json 'defaults.guard', else warn.")
    parser.add_argument("--net-writes", default=None,
                        choices=["confirm", "deny", "allow"],
                        help="outward-facing network writes (POST/PUT/DELETE to a "
                             "remote API, e.g. closing a Jira ticket): confirm "
                             "(default), deny (block all), or allow (unattended). "
                             "Overrides ROBODOG_NET_WRITES.")
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
    parser.add_argument("--theme", default=None,
                        choices=["default", "high-contrast", "mono", "pip-boy"],
                        help="color theme (default: $ROBODOG_THEME or 'default'; "
                             "'mono' disables ANSI color entirely; 'pip-boy' is a "
                             "green monochrome CRT look)")
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
            editor=args.editor, theme=args.theme)
    # agentic visible retry line: "API error · Retrying in Ns · attempt n/N"
    def on_retry(a, m, d, r):
        ui.spinner_stop()
        ui.dim(f"  ⚠ API error ({r}) · Retrying in {d:.0f}s · attempt {a}/{m}")
    client, model_label = build_backend(args, on_retry=on_retry)
    ui.model_name = model_label
    # Tool gating flags, parsed into lists (build_core applies them to the registry).
    allowed_tools = ([t.strip() for t in args.allowed_tools.split(",") if t.strip()]
                    if args.allowed_tools else None)
    disallowed_tools = ([t.strip() for t in args.disallowed_tools.split(",") if t.strip()]
                       if args.disallowed_tools else None)

    def on_diff(path, diff):
        ui.spinner_stop()
        ui.diff(path, diff)

    # Live-toggleable verbosity (/verbose flips it; --verbose sets the start).
    verbose = [bool(args.verbose)]

    # Subagents: a summary line of what's happening (like a modern agentic
    # terminal), not one line per child tool call. Children run concurrently in
    # worker threads, so the counters are lock-guarded; /verbose restores the
    # full per-event feed.
    import threading as _cthreading
    child_stats = {"children": set(), "calls": 0, "inflight": 0}
    child_lock = _cthreading.Lock()

    def _fanout_spinner():
        from robodog_terminal.llm_client import _effective_max_concurrency
        with child_lock:
            n = len(child_stats["children"])
            inflight, calls = child_stats["inflight"], child_stats["calls"]
        cap = _effective_max_concurrency()
        # `inflight/n` = subagents still running of the total spawned. The cap is
        # on MODEL-call concurrency (shown separately so it doesn't read as a
        # limit on the subagent count).
        label = (f"✳ {inflight}/{n} subagent{'' if n == 1 else 's'} running"
                 f" · {calls} tool call{'' if calls == 1 else 's'}")
        if cap > 0:
            label += f" · model cap {cap}"
        ui.spinner_update(label)

    def on_child_event(kind, data):
        if kind == "agent_spawn":
            with child_lock:
                child_stats["children"].add(data.get("child_id"))
                child_stats["inflight"] += 1
            ui.spinner_start("✳ subagents starting…")
            _fanout_spinner()
            return
        if kind == "agent_done":
            with child_lock:
                child_stats["inflight"] = max(0, child_stats["inflight"] - 1)
            _fanout_spinner()
            return
        if kind != "tool_start":
            return
        if verbose[0]:
            cid = data.get("child_id")
            tag = f"#{cid} " if cid else ""
            arg = str(data.get('args', {}).get('command')
                      or data.get('args', {}).get('path') or '')[:60]
            ui.dim(f"      ⚙ {tag}{data['name']} {arg}")
            return
        with child_lock:
            child_stats["calls"] += 1
        _fanout_spinner()

    def on_event(kind, data):
        if kind == "llm_start":
            with child_lock:      # new parent step: reset the fan-out counters
                child_stats["children"].clear()
                child_stats["calls"] = 0
                child_stats["inflight"] = 0
            # Spinner carries the status bar so it stays visible mid-turn.
            ui.spinner_start(ui.thinking_line(data["iteration"]))
        elif kind == "llm_error":
            ui.spinner_stop()
            if data.get("will_retry"):
                ui.dim(f"  ⚠ backend error ({data.get('error', '')}) — "
                       "retrying the step once…")
            else:
                ui.dim("  ⚠ backend still unreachable — ending the turn "
                       "(your context is kept; try again)")
        elif kind == "llm_done":
            ui.spinner_stop()
            if data.get("prose") and data.get("n_calls"):
                # Interim reasoning shown between tool calls. Cap it: some models
                # (esp. weaker gateways) regurgitate whole tool results as prose,
                # flooding the trace. The FINAL answer is always shown in full;
                # this only trims mid-turn chatter. /verbose shows it all.
                prose = data["prose"]
                if not verbose[0] and len(prose) > 600:
                    prose = prose[:600].rstrip() + f"  …[+{len(prose) - 600} chars, /verbose for all]"
                ui.assistant(prose)
        elif kind == "tool_start":
            ui.spinner_stop()
            ui.tool_call(data["name"], data["args"])
        elif kind == "tool_done":
            ui.spinner_stop()       # the fan-out summary spinner, if running
            ui.stream_footer()      # report any streamed lines the display capped
            if verbose[0]:
                ui.dim(data["result"])
            else:
                ui.tool_result(data["name"], data["result"])

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

    def on_task_change():
        # `checklist` resolves via closure late-binding to core.checklist below.
        ui.spinner_stop()
        for ln in checklist.render_lines()[-6:]:
            ui.dim(f"  {ln}")

    system_suffix = "" if args.no_instructions else _load_project_instructions(cwd)
    if args.append_system_prompt:
        system_suffix = (system_suffix + "\n\n" + args.append_system_prompt).strip()

    # Assemble the agentic core (ToolRegistry + AgentLoop + hooks/skills/
    # background/session wiring) — see core.py. Every UI touchpoint above is
    # just a plain callback passed in; build_core itself has no UI dependency,
    # so it's also the seam an embedder calls directly (no terminal attached).
    core = build_core(
        cwd, client,
        allowed_tools=allowed_tools, disallowed_tools=disallowed_tools,
        permission_mode=args.permission_mode, guard=args.guard,
        net_writes=args.net_writes, verify_edits=not args.no_verify_edits,
        test_command=args.test_command, system_suffix=system_suffix,
        max_iterations=args.max_iterations, max_tokens=args.max_tokens,
        temperature=args.temperature, max_transcript_chars=args.max_transcript_chars,
        on_diff=on_diff, on_bash_line=ui.bash_line, on_child_event=on_child_event,
        on_event=on_event, ask_fn=ask_fn, on_task_change=on_task_change, log=ui.dim,
    )
    registry, loop, skills, manager, checklist, store = (
        core.registry, core.loop, core.skills, core.manager, core.checklist, core.store)
    checkpointer = registry.checkpointer   # build_core made one; /rewind uses it directly
    session_id = [None]  # boxed: /resume swaps it

    if registry.net_guard == "deny":
        ui.dim("🛡 network writes: DENIED (read-only for external APIs)")
    elif registry.net_guard == "allow":
        ui.dim("⚠ network writes: ALLOWED unattended (POST/PUT/DELETE not gated)")
    else:
        ui.dim("🛡 network writes require confirmation (Jira/API POST/PUT/DELETE)")

    # Shift+Tab permission-mode cycle + its status-bar label.
    ui.wire_permission_registry(registry)

    def _confirm_danger(command, reason):
        # Already approved "always" for this kind of action this session.
        if reason in registry.session_allow:
            return True
        if headless:
            return False  # never run destructive/outward commands unattended
        ui.spinner_stop()
        ui.warn(f"⏸ needs your approval: {reason}")
        ui.dim(f"  {command[:300]}")
        try:
            ans = input("  run it? [y]es / [N]o / [a]lways this session: ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            return False
        if ans in ("a", "always"):
            registry.session_allow.add(reason)   # don't ask again this session
            return True
        return ans in ("y", "yes")
    registry.on_confirm = _confirm_danger

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
        if registry.hooks is not None:
            registry.hooks.run_stop()
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
    # marker (prompt index) -> len(loop.history) BEFORE that prompt ran, so
    # /rewind can drop the conversation turns from that prompt onward (keeping the
    # model's context in sync with the reverted files).
    history_marks: dict = {}
    import time as _time
    _session_start = _time.time()
    cost_tokens = {"in": 0, "out": 0}   # session input/output tokens for /stats cost
    last_answer = [""]                  # most recent final answer (for /copy, /save)

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

    # Read-only slash commands that are safe to run WHILE an agent turn is in
    # flight (they don't touch loop.history, the client, or checkpoints).
    SAFE_MIDTURN = {"doctor", "status", "context", "tools", "tasks", "tail",
                    "help", "verbose", "todos", "skills", "btw"}

    def _btw_background(question: str):
        """Answer a /btw side question WITHOUT blocking the turn: snapshot the
        conversation, ask the model on a daemon thread, print the answer when
        it lands. Used mid-turn so you can check in on a working agent."""
        try:
            convo = loop._render_prompt() if loop.history else "(no conversation yet)"
        except Exception:
            convo = "(conversation unavailable)"
        side_prompt = build_btw_prompt(convo, question, running=True)

        def _work():
            try:
                ans = client.complete(side_prompt, max_tokens=1200).text
            except Exception as exc:
                ui.dim(f"  [btw failed: {type(exc).__name__}]")
                return
            ui.info("\n[btw — not part of the conversation]")
            ui.assistant(ans)
        _threading.Thread(target=_work, daemon=True).start()
        ui.dim("  [btw: asking in the background — the answer will appear when ready]")

    def midturn_command(line: str) -> bool:
        """If `line` is a safe read-only slash command, run it NOW (while the
        agent works) and return True so it isn't queued for the agent. Anything
        else returns False -> queued as a follow-up. Never raises: a race on
        shared state degrades to a dim note, not a crash."""
        if not line or not line.startswith("/"):
            return False
        cmd, _, rest = line[1:].partition(" ")
        cmd, rest = cmd.lower().strip(), rest.strip()
        if cmd not in SAFE_MIDTURN:
            return False
        try:
            if cmd == "help":
                ui.info(HELP)
            elif cmd == "status":
                ui.print_status()
            elif cmd == "context":
                chars = loop.transcript_chars()
                ui.info(f"transcript: {len(loop.history)} turns · ~{chars // 4} tokens "
                        f"({chars} chars)")
            elif cmd == "doctor":
                try:
                    from .doctor import run_doctor, format_report
                except ImportError:
                    from robodog_terminal.doctor import run_doctor, format_report
                _dm = _normalize_model_id(getattr(args, "model", None)
                                          or os.environ.get("ROBODOG_MODEL", DEFAULT_MODEL))
                ui.info(format_report(run_doctor(
                    ui.cwd, backend=getattr(args, "backend", "") or "", model=_dm)))
            elif cmd == "tools":
                for name in list(registry._tools):  # noqa: SLF001
                    ui.info(f"  {name}")
            elif cmd == "verbose":
                verbose[0] = not verbose[0]
                ui.info(f"verbose output {'ON' if verbose[0] else 'OFF'}")
            elif cmd == "todos":
                lines = checklist.render_lines()
                ui.info("\n".join(lines) if lines else "(no tasks)")
            elif cmd == "skills":
                ui.info(f"extensions: {skills.summary()}")
            elif cmd == "tasks":
                tasks = manager.list()
                if not tasks:
                    ui.info("no background tasks.")
                for t in tasks:
                    ui.info(f"  {t.id}  [{t.status}]  {t.kind}  {t.title}")
            elif cmd == "tail":
                ui.info(manager.output(rest or "bg1"))
            elif cmd == "btw":
                if not rest:
                    ui.info("usage: /btw <question>  (answered in the background)")
                else:
                    _btw_background(rest)
        except Exception as exc:   # a race with the worker must never crash the REPL
            ui.dim(f"  (/{cmd} unavailable mid-turn: {type(exc).__name__})")
        return True

    key_source = make_key_source(ui, on_command=midturn_command)
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
        cost_tokens["in"] += getattr(result, "prompt_tokens", 0) or 0
        cost_tokens["out"] += getattr(result, "completion_tokens", 0) or 0
        ui.context_pct = min(99, loop.transcript_chars() * 100
                             // loop.max_transcript_chars)
        ui.assistant(result.final_text)
        last_answer[0] = result.final_text or ""
        dur = getattr(result, "duration", 0.0)
        ui.dim(f"[{result.iterations} steps · {result.total_tokens} tok · {dur:.1f}s]")
        if registry.hooks is not None:
            registry.hooks.run_stop()   # Stop hooks: the agent turn finished

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
                # Idle quit — hard-exit if a backgrounded turn's subagents are
                # stuck and would block a clean shutdown.
                return _hard_quit(ui)
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
                return _hard_quit(ui)
            elif cmd == "help":
                ui.info(HELP)
            elif cmd == "status":
                ui.print_status()
            elif cmd == "context":
                chars = loop.transcript_chars()
                ui.info(f"transcript: {len(loop.history)} turns · ~{chars // 4} tokens "
                        f"({chars} chars) · trim threshold {loop.max_transcript_chars} chars")
            elif cmd == "stats":
                chars = loop.transcript_chars()
                pct = min(99, chars * 100 // max(1, loop.max_transcript_chars))
                elapsed = int(_time.time() - _session_start)
                mm, ss = divmod(elapsed, 60)
                files = len(getattr(registry, "read_paths", {}) or {})
                from robodog_terminal.llm_client import estimate_cost as _cost
                _c = _cost(model_label, cost_tokens["in"], cost_tokens["out"])
                cost_line = (f"~${_c:.4f} (in {cost_tokens['in']:,} / out {cost_tokens['out']:,})"
                             if _c is not None else
                             f"— (no price for this model; in {cost_tokens['in']:,} / "
                             f"out {cost_tokens['out']:,})")
                ui.info(
                    f"session stats\n"
                    f"  model:       {model_label}\n"
                    f"  tokens:      {ui.total_tokens:,} this session\n"
                    f"  est. cost:   {cost_line}\n"
                    f"  context:     ~{chars // 4:,} tokens ({pct}% of the trim window)\n"
                    f"  turns:       {prompt_count} prompts · {len(loop.history)} history entries\n"
                    f"  files read:  {files}\n"
                    f"  uptime:      {mm}m {ss}s")
            elif cmd == "copy":
                if not last_answer[0].strip():
                    ui.info("nothing to copy yet — no answer this session.")
                elif _copy_to_clipboard(last_answer[0]):
                    ui.info(f"copied the last answer to the clipboard "
                            f"({len(last_answer[0]):,} chars).")
                else:
                    ui.error("couldn't reach a clipboard tool (clip/pbcopy/xclip). "
                             "Use /save <file> instead.")
            elif cmd == "save":
                if not last_answer[0].strip():
                    ui.info("nothing to save yet — no answer this session.")
                elif not rest:
                    ui.error("usage: /save <file>")
                else:
                    dest = Path(rest).expanduser()
                    if not dest.is_absolute():
                        dest = Path(registry.cwd) / rest
                    try:
                        dest.parent.mkdir(parents=True, exist_ok=True)
                        with open(dest, "w", encoding="utf-8", newline="") as _fh:
                            _fh.write(last_answer[0])
                        ui.info(f"saved the last answer to {dest} "
                                f"({len(last_answer[0]):,} chars).")
                    except OSError as exc:
                        ui.error(f"could not save: {exc}")
            elif cmd in ("net-writes", "netwrites", "allow"):
                mode = rest.lower().strip()
                if mode not in ("confirm", "deny", "allow"):
                    ui.info(f"network-write guard: {registry.net_guard}\n"
                            f"  /net-writes confirm  — ask before each remote write (default)\n"
                            f"  /net-writes allow    — permit remote writes without asking\n"
                            f"  /net-writes deny     — block all remote writes\n"
                            f"  (also: choose 'a' at a prompt to always-allow that one action; "
                            f"local commands are governed by --guard)")
                else:
                    registry.net_guard = mode
                    registry.session_allow.clear()   # a mode change resets remembered approvals
                    ui.info(f"network-write guard set to '{mode}' for this session.")
            elif cmd == "btw":
                if not rest:
                    ui.error("usage: /btw <question>")
                    continue
                # Side question: full visibility into the conversation, no tools,
                # single answer, and it does NOT touch the conversation history.
                convo = loop._render_prompt() if loop.history else "(no conversation yet)"
                side_prompt = build_btw_prompt(convo, rest)
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
                before = loop.transcript_chars()
                ui.spinner_start("✳ Compacting conversation…")
                try:
                    did = loop.compact()
                finally:
                    ui.spinner_stop()
                if did:
                    persisted[0] = len(loop.history)
                    after = loop.transcript_chars()
                    ui.info(f"conversation compacted (~{before // 4} → {after // 4} "
                            f"tokens; goal + recent turns kept verbatim).")
                else:
                    ui.info("nothing to compact yet (too short, or it wouldn't shrink).")
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
                    # Also rewind the CONVERSATION to before prompt n, so the model's
                    # context matches the reverted files (atomic files+transcript undo).
                    convo_note = ""
                    mark = history_marks.get(n)
                    if mark is not None and mark <= len(loop.history):
                        dropped = len(loop.history) - mark
                        if dropped > 0:
                            del loop.history[mark:]
                            persisted[0] = min(persisted[0], len(loop.history))
                            convo_note = f" and dropped {dropped} conversation turn(s)"
                    ui.info(f"rewound {len(actions)} file(s) to before prompt {n}{convo_note}.")
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
            elif cmd == "theme":
                if rest:
                    if ui.set_theme(rest):
                        ui.info(f"theme switched to '{ui.theme}'")
                    else:
                        ui.error(f"unknown theme '{rest}'. "
                                 f"available: {', '.join(sorted(ui._THEMES))}")  # noqa: SLF001
                else:
                    ui.info(f"theme: {ui.theme}")
                    ui.dim(f"  available: {', '.join(sorted(ui._THEMES))}")  # noqa: SLF001
            elif cmd == "plan":
                registry.mode = "plan" if registry.mode != "plan" else "yolo"
                ui.permission_label = registry.permission_mode_label()
                if registry.mode == "plan":
                    ui.info("📋 plan mode ON — read-only, agent will propose first")
                else:
                    ui.info("⏵ plan mode OFF — YOLO")
            elif cmd == "config":
                parts = rest.split()
                sub = parts[0].lower() if parts else ""
                if sub == "init":
                    flags = {p.lower() for p in parts[1:]}
                    is_global = "--global" in flags
                    force = "--force" in flags
                    target = (Path.home() if is_global else Path(ui.cwd)) / ".robodog" / "settings.json"
                    try:
                        from .hooks import write_default_settings
                    except ImportError:
                        from robodog_terminal.hooks import write_default_settings
                    if write_default_settings(target, force=force):
                        ui.info(f"wrote defaults to {target}")
                        ui.dim("  restart robodog (or /config) to see it take effect")
                    else:
                        ui.error(f"{target} already exists "
                                 f"(use '/config init --force' to overwrite)")
                else:
                    ui.info(f"permission mode: {registry.permission_mode_label()}")
                    ui.info(f"  guard={registry.guard}  net-writes={registry.net_guard}  "
                            f"verify-edits={registry.verify_edits}")
                    srcs = registry.hooks.sources if registry.hooks else []
                    ui.info(f"  settings.json: {', '.join(srcs) if srcs else '(none found)'}")
                    ui.dim("  /config init [--global] [--force]  write a starter settings.json")
            elif cmd == "init":
                prompt_texts.append("/init")
                history_marks[prompt_count] = len(loop.history)
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
            elif cmd == "cert":
                try:
                    from .certs import handle as _cert_handle
                except ImportError:
                    from robodog_terminal.certs import handle as _cert_handle
                _c_ok, _c_msg = _cert_handle(rest)
                (ui.info if _c_ok else ui.error)(_c_msg)
            elif cmd == "test" and rest.split()[0:1] == ["agents"]:
                # Aggressive subagent-path probe: /test agents [N] [small|big|huge].
                # N parallel subagents (default 2, up to 16); the size pads each
                # prompt to reproduce the LARGE-context requests your explore
                # agents actually send — that's what times out, not tiny ones.
                import concurrent.futures as _cf
                import time as _t
                parts = rest.split()
                try:
                    n = max(1, min(16, int(parts[1]))) if len(parts) > 1 else 2
                except ValueError:
                    n = 2
                size = (parts[2].lower() if len(parts) > 2 else "small")
                # ~4 chars/token; pad to approximate a big explore context.
                # size is a named tier OR a raw token count ('/test agents 4 30000').
                if size.isdigit():
                    pad_tokens = min(200_000, int(size))
                    size = f"{pad_tokens}tok"
                else:
                    pad_tokens = {"small": 0, "big": 4000, "huge": 12000}.get(size, 0)
                filler = ("The quick brown fox jumps over the lazy dog. "
                          * ((pad_tokens * 4 // 44) + 1))[:pad_tokens * 4] if pad_tokens else ""
                prompt = ((f"[reference text, ignore it]\n{filler}\n\n" if filler else "")
                          + "Reply with the single word: ready. Use no tools.")
                approx_tok = len(prompt) // 4
                ui.info(f"probing the subagent path — {n} parallel agents, "
                        f"{size} prompt (~{approx_tok} tokens each)…")

                def _one(i):
                    t0 = _t.time()
                    try:
                        r = registry.execute("agent",
                                              {"prompt": prompt, "type": "general"})
                        return (i, "ERROR" not in r[:6], _t.time() - t0,
                                r.splitlines()[0][:70])
                    except Exception as exc:
                        return (i, False, _t.time() - t0, f"{type(exc).__name__}: {exc}")

                try:
                    from .llm_client import _effective_max_concurrency as _emc
                except ImportError:
                    from robodog_terminal.llm_client import _effective_max_concurrency as _emc
                _cap = _emc() or "unlimited"
                t0 = _t.time()
                with _cf.ThreadPoolExecutor(max_workers=n) as _ex:
                    results = sorted(_ex.map(_one, range(n)))
                total = _t.time() - t0
                good = sum(1 for _, ok2, _, _ in results if ok2)
                times = [dt for _, _, dt, _ in results]
                stats = (f"per-agent {min(times):.1f}s min / "
                         f"{sum(times)/len(times):.1f}s avg / {max(times):.1f}s max")
                (ui.info if good == n else ui.error)(
                    f"{good}/{n} subagents ok in {total:.1f}s wall (cap {_cap}); {stats}")
                for i, ok2, dt, det in results:
                    ui.info(f"  #{i + 1} {'✓' if ok2 else '✗'} {dt:.1f}s — {det}")
                if good < n:
                    ui.dim("  (failures at this size/concurrency = the gateway can't keep "
                           "up. Raise ROBODOG_LLM_TIMEOUT, lower concurrency, or shrink "
                           "the real prompts.)")
            elif cmd == "test":
                # One-shot TIMED probe (no retries) so you can see the exact
                # phase + latency: connect vs read timeout vs HTTP error.
                if model_label.startswith("echo"):
                    ui.error("backend is echo/demo — no key resolved. Run /doctor "
                             "to see which layer is missing. (Try /test agents to "
                             "exercise the subagent path in any backend.)")
                elif hasattr(client, "diagnose"):
                    ui.spinner_start("✳ probing the backend (single request)…")
                    r = client.diagnose("Reply with the single word: pong.")
                    ui.spinner_stop()
                    mark = "✓" if r.get("ok") else "✗"
                    (ui.info if r.get("ok") else ui.error)(
                        f"{mark} {model_label}: {r.get('detail', '')}")
                else:
                    ui.spinner_start("✳ testing the connection…")
                    try:
                        ans = client.complete("Reply with the single word: pong.",
                                              max_tokens=5).text
                        ui.spinner_stop()
                        ui.info(f"✓ connected to {model_label} — reply: "
                                f"{ans.strip()[:60] or '(empty)'}")
                    except Exception as exc:
                        ui.spinner_stop()
                        ui.error(f"connection test failed: {type(exc).__name__}: {exc}")
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
            elif cmd == "verbose":
                verbose[0] = not verbose[0]
                ui.info(f"verbose output {'ON — full tool results and per-call subagent trace' if verbose[0] else 'OFF — compact summaries'}")
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
                history_marks[prompt_count] = len(loop.history)
                checkpointer.set_marker(prompt_count)
                prompt_texts.append(line)
                prompt_count += 1
                try:
                    result = loop.run(prompt)
                    ui.assistant(result.final_text)
                    ui.total_tokens += result.total_tokens
                    cost_tokens["in"] += getattr(result, "prompt_tokens", 0) or 0
                    cost_tokens["out"] += getattr(result, "completion_tokens", 0) or 0
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

        history_marks[prompt_count] = len(loop.history)
        checkpointer.set_marker(prompt_count)
        prompt_texts.append(line)
        prompt_count += 1
        expanded = _expand_mentions(line, registry)
        # Auto-inject skills whose trigger keywords appear in the message
        # (conditional context — costs nothing until it's relevant).
        for _sk in skills.triggered(line):
            ui.dim(f"(+ skill '{_sk.name}' — matched a trigger keyword)")
            expanded += f"\n\n[skill: {_sk.name}]\n{_sk.body}"
        if session_id[0] is None:
            session_id[0] = store.new_session()

        ui.reset_turn_stream()   # fresh per-turn live-preview budget
        runner = TurnRunner(loop)
        runner.start(expanded, _threading.Event())
        if not headless and sys.stdin.isatty():
            # The bottom-toolbar status bar only shows at the idle prompt; print
            # it as a header so model/tokens/context/branch stay visible while
            # the agent works.
            ui.print_status()
            ui.dim("  (Ctrl+C cancel · Ctrl+B background · /doctor,/status,… run now "
                   "· other text queues)")
        # Opt-in sticky mid-turn input (ROBODOG_STICKY_INPUT=1): a fixed bottom
        # prompt while the agent works, output scrolling above. Falls back to
        # the raw key reader by default.
        _sticky = (os.environ.get("ROBODOG_STICKY_INPUT") == "1"
                   and not headless and sys.stdin.isatty()
                   and getattr(ui, "_session", None) is not None)
        try:
            if _sticky:
                outcome = ui.watch_turn_sticky(runner, on_command=midturn_command)
            else:
                outcome = runner.watch(key_source)
        except KeyboardInterrupt:
            # A SECOND Ctrl+C escaped the cancel wait — force-quit NOW, even if
            # subagent worker threads are wedged in a network retry.
            return _hard_quit(ui)
        except Exception as exc:
            ui.reset_typing()
            ui.spinner_stop()
            ui.error(f"{type(exc).__name__}: {exc}")
            continue
        ui.reset_typing()   # never leave the spinner suppressed after a turn

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

        # Auto-compact near the context ceiling (keeps the goal + recent turns
        # verbatim, summarizes the middle — see AgentLoop.compact).
        if loop.transcript_chars() > int(loop.max_transcript_chars * 0.9):
            ui.dim("(auto-compacting conversation…)")
            try:
                if loop.compact():
                    persisted[0] = len(loop.history)
            except Exception as exc:
                ui.dim(f"(auto-compact skipped: {exc})")


if __name__ == "__main__":
    raise SystemExit(main())
