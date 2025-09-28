#!/usr/bin/env python3
import os
import sys
import argparse
import logging
import json
from pprint import pprint
from typing import Optional, Callable, List

# pip install colorlog textual requests tiktoken PyYAML openai playwright pydantic langchain setuptools
import colorlog

from textual.app import App, ComposeResult
from textual.screen import Screen
from textual.containers import Container, VerticalScroll, Horizontal
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
# Subclass RichLog to accept a `height` kwarg
class RichLog(_RichLog):
    def __init__(self, *args, height=None, **kwargs):
        super().__init__(*args, **kwargs)
        if height is not None:
            try:
                self.styles.height = height
            except Exception:
                # fallback if .styles not available
                self._size.height = height


# --------------------------------------------------------------------
# 1) Add run() to RobodogApp so app.run() works again
from textual.app import App, ComposeResult
# … other imports …

class RobodogApp(App):
    """Main Textual App."""
    CSS = """
    Screen {
        background: black;
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
# 2) Silently swallow height= in RichLog subclass

from textual.widgets import RichLog as _RichLog

class RichLog(_RichLog):
    def __init__(self, *args, **kwargs):
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
# 3) Remove the broken render() override and
# 4) Fix query_one() in on_mount()

from textual.screen import Screen
from textual.widgets import Input as _Input, Label, Checkbox, Footer, Header, Button

class DashboardScreen(Screen):
    # Reactive attributes
    task_desc     = reactive("")
    include_spec  = reactive("")
    out_spec      = reactive("")
    plan_spec     = reactive("")
    plan_status   = reactive(" ")
    exec_status   = reactive(" ")
    commit_status = reactive(" ")

    CSS = """
    Screen {
        align: center middle;
        background: black;
        layout: vertical;
    }
    #output-container {
        height: 60vh;
        border: round $primary;
        scrollbar-gutter: stable;
    }
    #task-container {
        height: 20vh;
        layout: horizontal;
        border: round $secondary;
    }
    #command-input {
        height: 20vh;
        layout: horizontal;
    }
    RichLog {
        background: $background;
        color: $text;
        border: none;
    }
    Input {
        border: round $warning;
    }
    Label {
        text-style: bold;
    }
    Checkbox {
        height: 1;
        margin: 0 1;
    }
    Footer {
        background: $background 50%;
        color: $text 50%;
    }
    """

    def __init__(self, svc: RobodogService):
        super().__init__()
        self.svc = svc
        self.output_log = RichLog(id="output-log")      # no more height=1
        self.current_task = None
        self.svc.set_ui_callback(self.update_ui)

    def compose(self) -> ComposeResult:
        yield Header("Robodog CLI", id="title")
        yield Container(
            VerticalScroll(self.output_log, id="output-container"),
            id="output-area"
        )
        # … the rest of your compose() exactly as before …
        yield Footer()

    def on_mount(self) -> None:
        self.load_current_task()
        # focus via CSS selector; no id= kwarg
        self.query_one("#command-input").focus()

    # … everything else unchanged, except remove this entirely:
    #    def render(self):
    #        yield Label(...)
    #        yield Label(...)
    #        …
    # Textual will do the rendering of your widgets for you.

# --------------------------------------------------------------------
# your existing run_ui() remains the same, calling app.run()
def run_ui(svc: RobodogService):
    app = RobodogApp(svc)
    app.run()


# --------------------------------------------------------------------
class RobodogAppb(App):
    """Main Textual App."""
    CSS = """
    Screen {
        background: black;
    }
    """

    def __init__(self, svc: RobodogService):
        super().__init__()
        self.svc = svc

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
        background: black;
        layout: vertical;
    }
    #output-container {
        height: 60vh;
        border: round $primary;
        scrollbar-gutter: stable;
    }
    #task-container {
        height: 20vh;
        layout: horizontal;
        border: round $secondary;
    }
    #command-input {
        height: 20vh;
        layout: horizontal;
    }
    RichLog {
        background: $background;
        color: $text;
        border: none;
    }
    Input {
        border: round $warning;
    }
    Label {
        text-style: bold;
    }
    Checkbox {
        height: 1;
        margin: 0 1;
    }
    Footer {
        background: $background 50%;
        color: $text 50%;
    }
    """

    def __init__(self, svc: RobodogService):
        super().__init__()
        self.svc = svc
        self.output_log = RichLog(id="output-log", height=1)
        self.current_task = None
        # Hook up service → UI callback
        self.svc.set_ui_callback(self.update_ui)

    def compose(self) -> ComposeResult:
        yield Header("Robodog CLI", id="title")
        yield Container(
            VerticalScroll(self.output_log, id="output-container"),
            id="output-area"
        )
        yield Container(
            Horizontal(
                Label("Task: ", id="task-label"),
                _Input(placeholder="Description", id="desc-input", value=self.task_desc),
            ),
            Horizontal(
                TaskStatus("Plan",   id="plan-toggle"),
                TaskStatus("Execute",id="exec-toggle"),
                TaskStatus("Commit", id="commit-toggle"),
                Label("Status: ", id="status-label"),
            ),
            Horizontal(
                Label("Include: ", id="include-label"),
                _Input(placeholder="include spec", id="include-input"),
                Label("Out: ",     id="out-label"),
                _Input(placeholder="out spec", id="out-input"),
            ),
            Horizontal(
                Label("Plan: ", id="plan-label"),
                _Input(placeholder="plan spec", id="plan-input"),
            ),
            id="task-container"
        )
        yield Container(
            _Input(placeholder="Type /command or edit above...", id="command-input"),
            id="command-input"
        )
        yield Footer()

  
    def on_mount(self) -> None:
        self.load_current_task()
        # query by CSS id selector string only
        self.query_one("#command-input").focus()

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
        self.output_log.write(f"> {cmd}")
        self.process_command(cmd)
        event.input.value = ""

    def process_command(self, cmd: str) -> None:
        if cmd.startswith("/todo"):
            self.svc.todo.run_next_task(self.svc)
        elif cmd.startswith("/model "):
            model = cmd.split(" ", 1)[1].strip()
            try:
                self.svc.set_model(model)
                self.output_log.write(f"Model switched to: {model}")
                self.notify(f"Model switched to {model}")
            except ValueError:
                self.output_log.write(f"Unknown model: {model}")
        elif cmd.startswith("/models"):
            models = self.svc.list_models_about()
            self.output_log.write("Available models:")
            for m in models:
                self.output_log.write(f"  {m}")
        elif cmd in ["/plan", "P"]:
            self.toggle_status("plan")
        elif cmd in ["/exec", "E"]:
            self.toggle_status("exec")
        elif cmd in ["/commit", "C"]:
            self.toggle_status("commit")
        else:
            self.output_log.write(f"Unknown command: {cmd}")

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
        self.output_log.write(f"{status_type.capitalize()} status: {new_status}")

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

    def load_current_task(self) -> None:
        if not hasattr(self.svc, 'todo'):
            return
        tasks = self.svc.todo._tasks
        pending = next((t for t in tasks if t.get('status_char') == ' '), None)
        if not pending:
            self.output_log.write("No pending tasks.")
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
        self.output_log.write(f"Loaded task: {self.task_desc[:50]}...")

    def update_ui(self, message: str) -> None:
        self.output_log.write(message)
        self.refresh()

    @on(events.Key)
    async def handle_key(self, event: events.Key) -> None:
        if event.key.lower() == "p":
            self.toggle_status("plan")
        elif event.key.lower() == "e":
            self.toggle_status("exec")
        elif event.key.lower() == "c":
            self.toggle_status("commit")


    def render(self):
        yield Label(f"Task Description: {self.task_desc}", id="current-desc")
        yield Label(f"Plan: [{self.plan_status}]", id="plan-display")
        yield Label(f"Execute: [{self.exec_status}]", id="exec-display")
        yield Label(f"Commit: [{self.commit_status}]",id="commit-display")

# --------------------------------------------------------------------
def print_help():
    cmds = {
        "help":                "show this help",
        "models":              "list configured models",
        "model <name>":        "switch model",
        # … etc …
        "todo":                "run next To Do task",
    }
    logging.info("Available /commands:")
    for cmd, desc in cmds.items():
        logging.info(f"  /{cmd:<20} — {desc}")

def parse_cmd(line):
    parts = line.strip().split()
    return parts[0][1:], parts[1:]

# … _init_services, interact, enable_powershell_ansi, main, run_ui unchanged …
# (Paste your existing _init_services, main(), run_ui(), etc., below)

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

def enable_powershell_ansi():
    if os.name != 'nt' or not POWERSHELL_ENV:
        return
    try:
        import winreg
        key_path = r"SOFTWARE\Microsoft\Windows\CurrentVersion\Console"
        reg_key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path,
                                 0, winreg.KEY_READ|winreg.KEY_WRITE)
        vt_level, _ = winreg.QueryValueEx(reg_key, "VirtualTerminalLevel")
        if vt_level == 0:
            winreg.SetValueEx(reg_key, "VirtualTerminalLevel", 0, winreg.REG_DWORD, 1)
            print("Enabled VirtualTerminalLevel=1 for ANSI colors.")
        reg_key.Close()
    except Exception as e:
        logger.warning(f"Could not set VirtualTerminalLevel: {e}")

def interact(svc: RobodogService):
    app = RobodogApp(svc)
    app.run()

def run_ui(svc: RobodogService):
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
    parser.add_argument('--log-level', default='INFO',
                        choices=['DEBUG','INFO','WARNING','ERROR','CRITICAL'])
    parser.add_argument('--backupFolder', default=r'c:\temp')
    parser.add_argument('--excludeDirs', default='node_modules,dist,diffout')
    args = parser.parse_args()

    if POWERSHELL_ENV and WINDOWS_ANSI_ENABLED:
        enable_powershell_ansi()

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

    logging.info("Starting robodog")

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
        run_ui(svc)
    finally:
        logging.info("Shutting down MCP server")
        server.shutdown()
        server.server_close()

if __name__ == '__main__':
    main()