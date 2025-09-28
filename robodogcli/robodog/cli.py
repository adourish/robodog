# file: cli.py
#!/usr/bin/env python3
import datetime
import os
import sys
import re
import argparse
import logging
import json
from pprint import pprint
from typing import Optional, Callable, List

# pip install colorlog textual requests tiktoken PyYAML openai playwright pydantic langchain setuptools
import colorlog

from textual.app import App, ComposeResult
from textual.screen import Screen
from textual.containers import Container, VerticalScroll, Horizontal, Vertical
from textual.widgets import (
    Static,
    Input as _Input,
    Label,
    Checkbox,
    Footer,
    Header,
    Button,
    Log,
    RichLog as _RichLog,
    ListView,
    ListItem,
)
from textual.reactive import reactive
from textual import on, work, events
from textual.message import Message

# --------------------------------------------------------------------
# Colorama for Windows ANSI
try:
    import colorama
    colorama.init(autoreset=True, strip=False)
    WINDOWS_ANSI_ENABLED = True
except ImportError:
    WINDOWS_ANSI_ENABLED = False

POWERSHELL_ENV = os.name == "nt" and "PSModulePath" in os.environ

# --------------------------------------------------------------------
# Application imports
from service        import RobodogService
from parse_service  import ParseService
from file_service   import FileService
from file_watcher   import FileWatcher
from task_parser    import TaskParser
from task_manager   import TaskManager
from prompt_builder import PromptBuilder
from todo_util      import TodoUtilService
from todo           import TodoService
from diff_service   import DiffService

# try relative imports for module mode
try:
    from .service import RobodogService
    from .mcphandler import run_robodogmcp
    from .todo import TodoService
    from .parse_service import ParseService
    from .models import TaskModel, Change, ChangesList, IncludeSpec
    from .file_service import FileService
    from .file_watcher import FileWatcher
    from .task_manager import TaskManager
    from .todo_util import TodoUtilService
    from .task_parser import TaskParser
    from .prompt_builder import PromptBuilder
    from .throttle_spinner import ThrottledSpinner
except ImportError:
    from mcphandler import run_robodogmcp
    from models import TaskModel, Change, ChangesList, IncludeSpec
    from throttle_spinner import ThrottledSpinner

logger = logging.getLogger('robodog.mcphandler')

# ANSI escape sequence stripper
ANSI_ESCAPE = re.compile(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])')

# --------------------------------------------------------------------
# Custom LogHandler for Textual UI integration
class TextualLogHandler(logging.Handler):
    """Custom handler to route logs to Textual UI output."""
    
    def __init__(self, ui_callback: Optional[Callable] = None):
        super().__init__()
        self.ui_callback = ui_callback
        
    def emit(self, record):
        if self.ui_callback:
            try:
                msg = self.format(record)
                # Strip ANSI escape sequences from the formatted message to prevent garbage in RichLog
                clean_msg = ANSI_ESCAPE.sub('', msg)
                self.ui_callback(clean_msg)
            except Exception:
                pass  # Avoid infinite loops

# --------------------------------------------------------------------
# Monkey-patch Input.__init__ to coerce non-str value → str
_orig_input_init = _Input.__init__

def _patched_input_init(self, *args, value=None, **kwargs):
    if value is not None and not isinstance(value, str):
        try:
            value = str(value)
        except Exception:
            value = ""
    return _orig_input_init(self, *args, value=value, **kwargs)

_Input.__init__ = _patched_input_init

# --------------------------------------------------------------------
# Subclass RichLog to accept a `height` kwarg (silently swallow height=)
class RichLog(_RichLog):
    def __init__(self, *args, height=None, **kwargs):
        # pop off 'height' if someone passed it
        height = kwargs.pop("height", None)
        super().__init__(*args, **kwargs)
        if height is not None:
            try:
                # new style API
                self.styles.height = height
            except Exception:
                # fallback
                self._size.height = height

# --------------------------------------------------------------------
# RobodogApp with synchronous run()
class RobodogApp(App):
    """Main Textual App with Pip-Boy theme."""
    CSS = """
    Screen {
        background: #001100;
        color: #00ff00;
    }
    Container {
        border: round #00aa00;
        background: #002200;
    }
    #output-container {
        height: 2fr;
        max-height: 70vh;
        border: round #00ff00;
        scrollbar-gutter: stable;
        background: #000a00;
    }
    #command-container {
        height: 0.5fr;
        layout: horizontal;
        border: round #ffaa00;
        background: #332200;
    }
    #task-container {
        height: 1fr;
        layout: vertical;
        border: round #00aa88;
        background: #003322;
    }
    RichLog {
        background: #000a00;
        color: #00ff00;
        border: none;
        scrollbar-gutter: stable;
    }
    Input {
        border: round #ffaa00;
        height: 1;
        background: #332200;
        color: #ffff00;
    }
    Label {
        text-style: bold;
        color: #ffaa00;
    }
    TaskStatus {
        height: 1;
        margin: 0 1;
        color: #00ff00;
    }
    Footer {
        background: #003300;
        color: #88ff88;
    }
    Header {
        background: #003300;
        color: #88ff88;
        text-style: bold;
    }
    Vertical {
        layout: vertical;
        height: 1fr;
    }
    Horizontal {
        layout: horizontal;
        height: auto;
    }
    """

    def __init__(self, svc: RobodogService):
        super().__init__()
        self.svc = svc

    def run(self):
        """Synchronous wrapper around the new async API."""
        import asyncio
        # In recent Textual versions `.run()` was removed in favor of `.run_async()`,
        # so we add it back here for backwards compatibility.
        asyncio.run(self.run_async())

    def compose(self) -> ComposeResult:
        yield DashboardScreen(self.svc)

# --------------------------------------------------------------------
class TaskStatus(Checkbox):
    """Checkbox for task status (Plan, Execute, Commit)."""
    DEFAULT_CSS = """
    TaskStatus {
        height: 1;
        margin: 1;
    }
    TaskStatus > .checkbox-icon {
        text-style: bold;
    }
    """

    def __init__(self, label: str, status: str = " ", id: str = None):
        super().__init__(label, value=False, id=id)
        self.status = status

    def render(self):
        if self.status == " ":
            icon = "⬜"
        elif self.status == "~":
            icon = "🔄"
        elif self.status == "x":
            icon = "✅"
        else:
            icon = "❓"
        return f"[{icon}] {self.label}"

# --------------------------------------------------------------------
class DashboardScreen(Screen):
    # Reactive attributes MUST be declared at class level
    task_desc    = reactive("")
    include_spec = reactive("")
    out_spec     = reactive("")
    plan_spec    = reactive("")
    plan_status  = reactive(" ")
    exec_status  = reactive(" ")
    commit_status= reactive(" ")

    CSS = """
    Screen {
        align: center middle;
        background: #001100;
        layout: vertical;
        color: #00ff00;
    }
    #output-container {
        height: 2fr;
        max-height: 70vh;
        border: round #00ff00;
        scrollbar-gutter: stable;
        background: #000a00;
    }
    #command-container {
        height: 0.5fr;
        layout: horizontal;
        border: round #ffaa00;
        background: #332200;
    }
    #task-container {
        height: 1fr;
        layout: vertical;
        border: round #00aa88;
        background: #003322;
    }
    RichLog {
        background: #000a00;
        color: #00ff00;
        border: none;
    }
    Input {
        border: round #ffaa00;
        height: 1;
        background: #332200;
        color: #ffff00;
    }
    Label {
        text-style: bold;
        color: #ffaa00;
    }
    Checkbox {
        height: 1;
        margin: 0 1;
        color: #00ff00;
    }
    Footer {
        background: #003300;
        color: #88ff88;
    }
    Header {
        background: #003300;
        color: #88ff88;
        text-style: bold;
    }
    Vertical {
        layout: vertical;
        height: 1fr;
    }
    """

    def __init__(self, svc: RobodogService):
        super().__init__()
        self.svc = svc
        self.output_log = RichLog(id="output-log")
        self.current_task = None
        self.textual_handler = None
        # Hook up service → UI callback
        self.svc.set_ui_callback(self.update_ui)
        # Wire TodoService if available
        if hasattr(self.svc, "todo"):
            self.svc.todo.set_ui_callback(self.update_ui)

    def compose(self) -> ComposeResult:
        # Main vertical layout with Pip-Boy theme
        yield Header("🤖 ROBODOG TERMINAL v2.0 - PIP-BOY INTERFACE", id="title")
        yield Vertical(
            # Output log section (top, larger)
            Container(
                Label("📟 OUTPUT CONSOLE", id="output-label"),
                VerticalScroll(self.output_log),
                id="output-container",
                classes="output-section"
            ),
            # Task controls section (middle)
            Container(
                Label("🎯 TASK CONTROL PANEL", id="task-panel-label"),
                Horizontal(
                    Label("Task:", id="task-label"),
                    _Input(placeholder="Task Description", id="desc-input", value=self.task_desc),
                ),
                Horizontal(
                    TaskStatus("Plan",   id="plan-toggle", status=self.plan_status),
                    TaskStatus("Execute",id="exec-toggle", status=self.exec_status),
                    TaskStatus("Commit", id="commit-toggle", status=self.commit_status),
                ),
                Horizontal(
                    Label("Include:", id="include-label"),
                    _Input(placeholder="*.py", id="include-input", value=self.include_spec),
                    Label("Out:", id="out-label"),
                    _Input(placeholder="out.py", id="out-input", value=self.out_spec),
                ),
                Horizontal(
                    Label("Plan:", id="plan-label"),
                    _Input(placeholder="plan.md", id="plan-input", value=self.plan_spec),
                ),
                id="task-container"
            ),
            # Command input section (bottom, fixed height)
            Container(
                Label("💻 COMMAND TERMINAL", id="command-label"),
                Horizontal(
                    _Input(placeholder="Type /command (e.g., /models, /todo, /help)...", id="command-input"),
                ),
                id="command-container"
            ),
            id="main-layout"
        )


    def on_mount(self) -> None:
        self.setup_logging()
        self.update_ui("🚀 ROBODOG TERMINAL INITIALIZING...")
        self.update_ui("📡 Loading task management services...")
        self.refresh()  # Initial refresh
        self.load_current_task()
        self.update_ui("✅ SYSTEM READY - AWAITING COMMANDS")
        self.update_ui("💡 Type /help for available commands")
        self.refresh()  # Post-load refresh
        # Focus on command input
        self.query_one("#command-input").focus()
        self.refresh()  # Final refresh to ensure full render
        self.update_ui("🎮 COMMAND TERMINAL ACTIVE")

    def setup_logging(self):
        """Setup TextualLogHandler to route logs to UI output."""
        self.textual_handler = TextualLogHandler(self.update_ui)
        formatter = colorlog.ColoredFormatter(
            "%(log_color)s[%(levelname)s]%(reset)s %(message)s",
            log_colors={
                "DEBUG":    "cyan",
                "INFO":     "green", 
                "WARNING":  "yellow",
                "ERROR":    "red",
                "CRITICAL": "bold_red",
                "DELTA":    "yellow",
                "PERCENT":  "green",
                "HIGHLIGHT":"cyan",
            }
        )
        self.textual_handler.setFormatter(formatter)
        self.textual_handler.setLevel(logging.INFO)
        
        # Add to root logger
        root = logging.getLogger()
        root.addHandler(self.textual_handler)
        
        # Also add to specific loggers
        for logger_name in ['robodog.service', 'robodog.todo', 'robodog.parse_service', 
                           'robodog.file_service', 'robodog.diff_service']:
            specific_logger = logging.getLogger(logger_name)
            specific_logger.addHandler(self.textual_handler)

    def load_current_task(self) -> None:
        if not hasattr(self.svc, 'todo'):
            self.update_ui("⚠️ Todo service not initialized.")
            return
        tasks = self.svc.todo._tasks
        pending = next((t for t in tasks if t.get('status_char') == ' '), None)
        if not pending:
            self.update_ui("📋 No pending tasks. Ready for new commands.")
            return
        self.current_task = pending
        self.task_desc    = pending.get('desc', "")
        inc = pending.get('include')
        out = pending.get('out')
        plan = pending.get('plan')
        self.include_spec = inc.get('pattern', "") if inc else ""
        self.out_spec     = out.get('pattern', "") if out else ""
        self.plan_spec    = plan.get('pattern', "") if plan else ""
        self.plan_status  = pending.get('plan_flag', " ")
        self.exec_status  = pending.get('status_char', " ")
        self.commit_status= pending.get('write_flag', " ")
        # Update reactive widgets
        self.query_one("#plan-toggle", TaskStatus).status = self.plan_status
        self.query_one("#exec-toggle", TaskStatus).status = self.exec_status
        self.query_one("#commit-toggle", TaskStatus).status = self.commit_status
        self.update_ui(f"📌 Loaded task: {self.task_desc[:50]}...")
        self.refresh()

    def update_ui(self, message: str) -> None:
        """Update UI with formatted message and timestamp."""
        timestamp = datetime.datetime.now().strftime("%H:%M:%S")
        formatted_msg = f"[{timestamp}] {message}"
        self.output_log.write(formatted_msg)
        #self.refresh()
        # Auto-scroll to bottom
        self.call_later(lambda: self.output_log.action_scroll_end())

    @on(_Input.Submitted, "#desc-input")
    def update_description(self, event: _Input.Submitted) -> None:
        self.task_desc = event.input.value
        self.update_task("desc", self.task_desc)

    @on(_Input.Submitted, "#include-input")
    def update_include(self, event: _Input.Submitted) -> None:
        self.include_spec = event.input.value
        self.update_task("include", self.include_spec)

    @on(_Input.Submitted, "#out-input")
    def update_out(self, event: _Input.Submitted) -> None:
        self.out_spec = event.input.value
        self.update_task("out", self.out_spec)

    @on(_Input.Submitted, "#plan-input")
    def update_plan(self, event: _Input.Submitted) -> None:
        self.plan_spec = event.input.value
        self.update_task("plan", self.plan_spec)

    @on(_Input.Submitted, "#command-input")
    def handle_command(self, event: _Input.Submitted) -> None:
        cmd = event.input.value.strip()
        self.update_ui(f"💻 > {cmd}")
        self.process_command(cmd)
        event.input.value = ""  # Clear input
        self.query_one("#command-input").focus()  # Re-focus
        self.refresh()  # Final refresh

    def process_command(self, cmd: str) -> None:
        # Command mapping for slash commands
        cmds = {
            "todo": "run next To Do task",
            "model <name>": "switch model",
            "models": "list configured models",
            "plan": "toggle plan status",
            "exec": "toggle exec status",
            "commit": "toggle commit status",
            "help": "show this help",
        }
        
        if cmd.startswith("/"):
            # Handle slash commands: split and route based on cmd
            parts = cmd[1:].strip().split(maxsplit=1)  # Split at most once for /model <name>
            cmd_key = parts[0]
            cmd_arg = parts[1] if len(parts) > 1 else None

            if cmd_key in cmds:
                if cmd_key == "help":
                    self.update_ui("📚 AVAILABLE COMMANDS:")
                    for key, desc in cmds.items():
                        self.update_ui(f"   /{key:<20} — {desc}")
                elif cmd_key == "models":
                    models = self.svc.list_models_about()
                    self.update_ui("🤖 AVAILABLE MODELS:")
                    for m in models:
                        self.update_ui(f"   {m}")
                elif cmd_key == "model" and cmd_arg:
                    model = cmd_arg.strip()
                    try:
                        self.svc.set_model(model)
                        self.update_ui(f"🔄 Model switched to: {model}")
                        self.notify(f"Model switched to {model}")
                    except ValueError:
                        self.update_ui(f"❌ Unknown model: {model}")
                elif cmd_key == "todo":
                    self.update_ui("🔧 Running next todo task...")
                    self.svc.todo.run_next_task(self.svc)
                elif cmd_key == "plan":
                    self.toggle_status("plan")
                elif cmd_key == "exec":
                    self.toggle_status("exec")
                elif cmd_key == "commit":
                    self.toggle_status("commit")
                else:
                    self.update_ui(f"❓ Unknown command: /{cmd_key}")
            else:
                self.update_ui(f"❓ Unknown slash command: /{cmd_key}")
        else:
            # Legacy non-slash handling: treat as regular input or log
            self.update_ui(f"📝 Legacy command: {cmd} (use / for slash commands)")
        self.refresh()  # Ensure UI updates after command processing

    def toggle_status(self, status_type: str) -> None:
        current = getattr(self, f"{status_type}_status")
        if current == " ":
            new_status = "~"
        elif current == "~":
            new_status = "x"
        else:
            new_status = " "
        setattr(self, f"{status_type}_status", new_status)
        self.update_task(status_type, new_status)
        self.update_ui(f"🔧 {status_type.capitalize()} status: {new_status}")
        # Update reactive widgets
        if status_type == "plan":
            self.query_one("#plan-toggle", TaskStatus).status = new_status
        elif status_type == "exec":
            self.query_one("#exec-toggle", TaskStatus).status = new_status
        elif status_type == "commit":
            self.query_one("#commit-toggle", TaskStatus).status = new_status
        self.refresh()  # Refresh to update reactive TaskStatus widgets

    def update_task(self, field: str, value: str) -> None:
        if not self.current_task:
            return
        if field in ["plan", "exec", "commit"]:
            self.current_task[field + "_flag"] = value
        else:
            self.current_task[field] = value
        # rebuild and save
        self.svc.todo._todo_util._rebuild_task_line(self.current_task)
        self.svc.todo._load_all()
        self.update_ui(f"💾 Updated task {field}: {value}")
        self.refresh()  # Refresh UI after task update

    @on(events.Key)
    async def handle_key(self, event: events.Key) -> None:
        if event.key.lower() == "p":
            self.toggle_status("plan")
        elif event.key.lower() == "e":
            self.toggle_status("exec")
        elif event.key.lower() == "c":
            self.toggle_status("commit")

# --------------------------------------------------------------------
def run_ui(svc: RobodogService):
    app = RobodogApp(svc)
    app.run()

# --------------------------------------------------------------------
def _init_services(args):
    diff_service = DiffService(60)
    exclude_dirs = set(args.excludeDirs.split(',')) if args.excludeDirs else {"node_modules", "dist", "diffoutput"}
    spin = ThrottledSpinner(interval=0.2)
    svc = RobodogService(args.config, exclude_dirs=exclude_dirs, backupFolder=args.backupFolder, spin=spin)
    svc.file_service = FileService(roots=args.folders, base_dir=None, backupFolder=args.backupFolder)
    parser = ParseService(base_dir=None, backupFolder=args.backupFolder,
                          diff_service=diff_service, file_service=svc.file_service)
    svc.parse_service = parser
    watcher = FileWatcher(); watcher.start(); svc.file_watcher = watcher
    task_parser = TaskParser(); svc.task_parser = task_parser
    task_manager = TaskManager(base=None, file_watcher=watcher,
                               task_parser=task_parser, svc=svc)
    svc.task_manager = task_manager
    svc.prompt_builder = PromptBuilder()
    todo_util = TodoUtilService(args.folders, svc, svc.prompt_builder,
                                svc.task_manager, svc.task_parser,
                                svc.file_watcher, svc.file_service,
                                exclude_dirs=exclude_dirs)
    svc.todo = TodoService(args.folders, svc, svc.prompt_builder,
                           svc.task_manager, svc.task_parser,
                           svc.file_watcher, svc.file_service,
                           exclude_dirs=exclude_dirs, todo_util=todo_util)
    return svc, parser

def interact(svc: RobodogService):
    app = RobodogApp(svc)
    app.run()

def main():
    parser = argparse.ArgumentParser(prog="robodog",
        description="Combined MCP file-server + Robodog CLI")
    parser.add_argument('--config', default='config.yaml')
    parser.add_argument('--folders', nargs='+', required=True)
    parser.add_argument('--host', default='127.0.0.1')
    parser.add_argument('--port', type=int, default=2500)
    parser.add_argument('--token', required=True)
    parser.add_argument('--cert', default=None)
    parser.add_argument('--key', default=None)
    parser.add_argument('--model', '-m')
    parser.add_argument('--log-file', default='robodog.log')
    parser.add_argument('--log-level', default='ERROR',
                        choices=['DEBUG','INFO','WARNING','ERROR','CRITICAL'])
    parser.add_argument('--backupFolder', default=r'c:\temp')
    parser.add_argument('--excludeDirs', default='node_modules,dist,diffout')
    args = parser.parse_args()


    # configure colored logging
    root = logging.getLogger()
    root.setLevel(getattr(logging, args.log_level))
    fmt = colorlog.ColoredFormatter(
        "%(log_color)s%(asctime)s:%(reset)s %(message)s",
        datefmt="%H:%M:%S",
        log_colors={
            "DEBUG":    "cyan",
            "INFO":     "green",
            "WARNING":  "yellow",
            "ERROR":    "red",
            "CRITICAL": "bold_red",
            "DELTA":    "yellow",
            "PERCENT":  "green",
            "HIGHLIGHT":"cyan",
        }
    )
    ch = colorlog.StreamHandler(sys.stdout)
    ch.setFormatter(fmt)
    root.addHandler(ch)

    # Keep file handler for logging
    file_handler = logging.FileHandler(args.log_file)
    file_handler.setFormatter(fmt)
    root.addHandler(file_handler)
    
    # Reduce console handler during UI but keep for startup
    logger.setLevel(logging.INFO)

    logging.info("🚀 Starting robodog with Pip-Boy UI")

    svc, parser = _init_services(args)
    server = run_robodogmcp(
        host    = args.host,
        port    = args.port,
        token   = args.token,
        folders = args.folders,
        svc     = svc,
        cert    = args.cert,
        key     = args.key
    )
    svc.mcp_cfg['baseUrl'] = f"http{'s' if args.cert and args.key else ''}://{args.host}:{args.port}"
    svc.mcp_cfg['apiKey']  = args.token
    if args.model:
        svc.set_model(args.model)
        logging.info("Startup model set to %s", svc.cur_model)

    try:
        # Remove console handler before UI to prevent conflicts
        root.removeHandler(ch)
        run_ui(svc)
    finally:
        logging.info("Shutting down MCP server")
        server.shutdown()
        server.server_close()
        # Restore console handler after UI
        root.addHandler(ch)
        logger.setLevel(getattr(logging, args.log_level))

if __name__ == '__main__':
    main()

# Original file length: 786 lines
# Updated file length: 853 lines