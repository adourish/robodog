# file: cli.py
#!/usr/bin/env python3
import os
import sys
import argparse
import logging
import json
from pprint import pprint

# pip install --upgrade requests   tiktoken   PyYAML   openai   playwright   pydantic   langchain setuptools
# support both "python -m robodog.cli" and "python cli.py" invocations:
# third-party for colored logs
# pip install colorlog
import colorlog
logger = logging.getLogger('robodog.mcphandler')
# Enhanced: Add colorama for Windows/PowerShell ANSI support
try:
    import colorama
    
    colorama.init(autoreset=True, strip=False)  # Initialize with strip=False to preserve ANSI even if not needed
    WINDOWS_ANSI_ENABLED = True
    logger.debug("Colorama initialized for ANSI support on Windows/PowerShell", extra={'log_color': 'HIGHLIGHT'})
except ImportError:
    logger.warning("Colorama not installed; install with 'pip install colorama' for better Windows color support", extra={'log_color': 'DELTA'})
    WINDOWS_ANSI_ENABLED = False


# Detect if running in PowerShell (basic check via environment vars)
if os.name == 'nt' and 'PSModulePath' in os.environ:
    POWERSHELL_ENV = True
    logger.info("Detected PowerShell environment; ANSI colors may need colorama for full support", extra={'log_color': 'HIGHLIGHT'})
else:
    POWERSHELL_ENV = False
# cli.py (somewhere near the top)
from service        import RobodogService
from parse_service  import ParseService
from file_service   import FileService
from file_watcher   import FileWatcher
from task_parser    import TaskParser
from task_manager   import TaskManager
from prompt_builder import PromptBuilder
from todo_util           import TodoUtilService
from todo           import TodoService
from diff_service   import DiffService  # newly added
from app            import RobodogApp   # Added import for RobodogApp integration
from dashboard      import Dashboard, TaskSelector, CommitConfirmation, TokenBudgetDisplay, show_shortcuts
# support both "python -m robodog.cli" and "python cli.py" invocations:
try:
    from .service import RobodogService
    from .mcphandler import run_robodogmcp
    from .todo import TodoService
    from .parse_service import ParseService
    from .models import TaskModel, Change, ChangesList, IncludeSpec
    from .file_service import FileService
    from .file_watcher import FileWatcher
    from .task_manager import TaskManager
    from .todo_util           import TodoUtilService
    from .task_parser import TaskParser
    from .prompt_builder import PromptBuilder
    from .throttle_spinner import ThrottledSpinner
    from .app import RobodogApp  # Added relative import for RobodogApp
    from .simple_ui import SimpleUIWrapper  # Simple UI
except ImportError:
    from service import RobodogService
    from mcphandler import run_robodogmcp
    from todo import TodoService
    from parse_service import ParseService
    from models import TaskModel, Change, ChangesList, IncludeSpec
    from file_service import FileService
    from file_watcher import FileWatcher
    from todo_util           import TodoUtilService
    from task_manager import TaskManager
    from task_parser import TaskParser
    from prompt_builder import PromptBuilder
    from throttle_spinner import ThrottledSpinner
    from app import RobodogApp  # Direct import for RobodogApp
    from simple_ui import SimpleUIWrapper  # Simple UI



def print_help():
    cmds = {
        "help":                "show this help",
        "quit or exit":        "exit the application (or Ctrl+C)",
        "status":              "show full dashboard",
        "q":                   "quick status",
        "budget":              "show token budget",
        "shortcuts":           "show keyboard shortcuts",
        "models":              "list configured models",
        "model <name>":        "switch model",
        "key <prov> <key>":    "set API key for provider",
        "getkey <prov>":       "get API key for provider",
        "import <glob>":       "import files into knowledge",
        "export <file>":       "export chat+knowledge snapshot",
        "clear":               "clear chat+knowledge and screen",
        "stash <name>":        "stash state",
        "pop <name>":          "restore stash",
        "list":                "list stashes",
        "temperature <n>":     "set temperature",
        "top_p <n>":           "set top_p",
        "max_tokens <n>":      "set max_tokens",
        "frequency_penalty <n>":"set frequency_penalty",
        "presence_penalty <n>":"set presence_penalty",
        "stream":              "enable streaming",
        "rest":                "disable streaming",
        "folders <dirs>":      "set MCP roots",
        "include":             "include files via MCP",
        "curl":                "fetch web pages / scripts",
        "play":                "run AI-driven Playwright tests",
        "mcp":                 "invoke raw MCP operation",
        "todo":                "select and run task",
    }
    logging.info("Available /commands:")
    for cmd, desc in cmds.items():
        logging.info(f"  /{cmd:<20} — {desc}")

def parse_cmd(line):
    parts = line.strip().split()
    return parts[0][1:], parts[1:]


def _init_services(args):

    diff_service = DiffService(60)
    exclude_dirs = set(args.excludeDirs.split(',')) if args.excludeDirs else {"node_modules", "dist", "diffoutput"}

    spin = ThrottledSpinner(interval=0.2)         # or at most once per 50 chunks
    # 1) core Robodog service + parser
    svc    = RobodogService(args.config, exclude_dirs=exclude_dirs,  backupFolder=args.backupFolder, spin=spin)


    # 2) file‐service (for ad hoc file lookups and reads)
    svc.file_service = FileService(roots=args.folders, base_dir=None, backupFolder=args.backupFolder)
    parser = ParseService(base_dir=None, backupFolder=args.backupFolder, diff_service=diff_service, file_service=svc.file_service)
    svc.parse_service = parser
    # Inject file_service into parser and service
    parser.file_service = svc.file_service
    svc.file_service = svc.file_service

    # 3) file‐watcher (used by TaskManager / TodoService to ignore self‐writes)
    watcher = FileWatcher()
    watcher.start()
    svc.file_watcher = watcher

    # 4) task‐parsing + task‐manager (status updates in todo.md)
    task_parser  = TaskParser()
    svc.task_parser = task_parser
    task_manager = TaskManager(
        base=None,
        file_watcher=watcher,
        task_parser=task_parser,
        svc=svc,
        file_service=svc.file_service
    )
    svc.task_manager = task_manager

    # 5) prompt builder for formalizing AI prompts
    svc.prompt_builder = PromptBuilder()
    todo_util = TodoUtilService(args.folders, svc, svc.prompt_builder, svc.task_manager, svc.task_parser, svc.file_watcher, svc.file_service, exclude_dirs=exclude_dirs)

    # 6) todo runner / watcher
    svc.todo = TodoService(args.folders, svc, svc.prompt_builder, svc.task_manager, svc.task_parser, svc.file_watcher, svc.file_service, exclude_dirs=exclude_dirs, todo_util=todo_util)
    
    # 7) Enable agent loop if requested
    if args.agent_loop:
        try:
            from agent_loop import enable_agent_loop
            enable_agent_loop(svc.todo, enable=True)
            logger.info("Agentic loop enabled for incremental task execution", extra={'log_color': 'HIGHLIGHT'})
        except ImportError as e:
            logger.warning(f"Could not enable agent loop: {e}", extra={'log_color': 'DELTA'})

    return svc, parser

def interact(svc: RobodogService, app_instance: RobodogApp, pipboy_ui=None):  # Modified to accept app_instance and pipboy_ui
    prompt_symbol = lambda: f"[{svc.cur_model}]{'»' if svc.stream else '>'} "
    
    if not pipboy_ui:
        logging.info("robodog CLI — type /help to list commands.")
    
    # Sample messages for RobodogApp integration
    sample_messages = ["echo test", "help", "/help"]  # Predefined sample patterns
    while True:
        try:
            if pipboy_ui:
                # In Pip-Boy mode, UI handles input via callback
                import time
                time.sleep(0.1)
                if not pipboy_ui.running:
                    break
                continue
            else:
                line = input(prompt_symbol()).strip()
        except (EOFError, KeyboardInterrupt):
            logging.info("bye")
            break
        if not line:
            continue

        if line.startswith("/"):
            cmd, args = parse_cmd(line)
            try:
                if cmd == "help":
                    print_help()

                elif cmd == "models":
                    models_list = "\n".join([f"  {m}" for m in svc.list_models_about()])
                    if pipboy_ui:
                        pipboy_ui.set_output(models_list)
                    else:
                        for m in svc.list_models_about():
                            app_instance.display_command(f"  {m}")

                elif cmd == "model":
                    if not args:
                        logging.warning("Usage: /model <model_name>")
                    else:
                        svc.set_model(args[0])
                        logging.info("Model set to: %s", svc.cur_model)

                elif cmd == "key":
                    if len(args) < 2:
                        logging.warning("Usage: /key <provider> <api_key>")
                    else:
                        svc.set_key(args[0], args[1])
                        logging.info("API key for '%s' set.", args[0])

                elif cmd == "getkey":
                    if not args:
                        logging.warning("Usage: /getkey <provider>")
                    else:
                        key = svc.get_key(args[0])
                        logging.info("%s API key: %s", args[0], key or "<none>")

                elif cmd == "folders":
                    if not args:
                        logging.warning("Usage: /folders <dir1> [dir2 …]")
                    else:
                        resp = svc.call_mcp("SET_ROOTS", {"roots": args})
                        logging.info("MCP server roots:")
                        for r in resp.get("roots", []):
                            logging.info("  %s", r)

                elif cmd == "include":
                    if not args:
                        logging.warning("Usage: /include [spec] [prompt]")
                    else:
                        spec_prompt = line[len("/include "):].strip()
                        parts = spec_prompt.split()
                        brk = 1
                        for i, t in enumerate(parts[1:], start=1):
                            if not (t == "recursive" or t.startswith(("file=", "dir=", "pattern="))):
                                brk = i
                                break
                        spec = " ".join(parts[:brk])
                        ptext = " ".join(parts[brk:]) or ""
                        knowledge = svc.include(spec) or ""
                        answer = svc.ask(f"{ptext} {knowledge}".strip())
                        return answer

                elif cmd == "curl":
                    svc.curl(args)

                elif cmd == "play":
                    svc.play(" ".join(args))

                elif cmd == "mcp":
                    if not args:
                        logging.warning("Usage: /mcp OP [JSON]")
                    else:
                        op = args[0].upper()
                        raw = " ".join(args[1:]).strip()
                        payload = {}
                        if raw:
                            payload = json.loads(raw)
                        res = svc.call_mcp(op, payload)
                        pprint(res)

                elif cmd == "import":
                    if not args:
                        logging.warning("Usage: /import <glob>")
                    else:
                        cnt = svc.import_files(args[0])
                        logging.info("Imported %d files.", cnt)

                elif cmd == "export":
                    if not args:
                        logging.warning("Usage: /export <filename>")
                    else:
                        svc.export_snapshot(args[0])
                        logging.info("Exported to %s.", args[0])

                elif cmd == "clear":
                    svc.clear()
                    # Clear the screen
                    os.system('cls' if os.name == 'nt' else 'clear')
                    logging.info("Cleared chat history, knowledge, and screen.")

                elif cmd == "stash":
                    if not args:
                        logging.warning("Usage: /stash <name>")
                    else:
                        svc.stash(args[0])
                        logging.info("Stashed under '%s'.", args[0])

                elif cmd == "pop":
                    if not args:
                        logging.warning("Usage: /pop <name>")
                    else:
                        svc.pop(args[0])
                        logging.info("Popped '%s' into current session.", args[0])

                elif cmd == "list":
                    st = svc.list_stashes()
                    if not st:
                        logging.info("No stashes.")
                    else:
                        logging.info("Stashes:")
                        for name in st:
                            logging.info("  %s", name)

                elif cmd in ("temperature","top_p","max_tokens","frequency_penalty","presence_penalty"):
                    if not args:
                        logging.warning("Usage: /%s <value>", cmd)
                    else:
                        val = float(args[0]) if "." in args[0] else int(args[0])
                        svc.set_param(cmd, val)
                        logging.info("%s set to %s", cmd, val)

                elif cmd == "stream":
                    svc.stream = True
                    logging.info("Switched to streaming mode.")

                elif cmd == "rest":
                    svc.stream = False
                    logging.stream = False
                    logging.info("Switched to REST mode.")

                elif cmd == "status":
                    # Show full dashboard
                    dashboard = Dashboard(svc.todo)
                    dashboard.show_full_dashboard()

                elif cmd == "q":
                    # Quick status
                    dashboard = Dashboard(svc.todo)
                    dashboard.show_quick_status()

                elif cmd == "budget":
                    # Show token budget
                    stats = Dashboard(svc.todo).get_statistics()
                    TokenBudgetDisplay.show(stats['total_tokens'])

                elif cmd == "shortcuts":
                    # Show keyboard shortcuts
                    show_shortcuts()

                elif cmd == "todo":
                    # Interactive task selection
                    selector = TaskSelector(svc.todo)
                    selected_task = selector.show_menu()
                    if selected_task:
                        # Determine which step to run
                        if selected_task.get('plan') == ' ':
                            step = 1
                        elif selected_task.get('llm') == ' ':
                            step = 2
                        elif selected_task.get('commit') == ' ':
                            step = 3
                        else:
                            step = 1
                        
                        logging.info(f"Running task: {selected_task['desc']}")
                        svc.todo._process_one(selected_task, svc, svc.todo._file_lines, step=step)
                        
                        # Show updated status
                        dashboard = Dashboard(svc.todo)
                        dashboard.show_quick_status()
                    
                    # Log app state if needed
                    if hasattr(app_instance, 'get_log'):
                        logs = app_instance.get_log()
                        if logs:
                            logging.info(f"App logs after todo: {len(logs)} entries")

                else:
                    logging.error("unknown /cmd: %s", cmd)

            except Exception:
                logging.exception("Error processing command")

        else:
            # Check for sample messages to route to RobodogApp
            if line in sample_messages:
                logging.info(f"Routing sample message '{line}' to RobodogApp")
                app_instance.display_command(f"Sample: {line}")  # Use display_command for echoing
                app_instance.run_command(line)  # Call run_command for processing
                # Optionally log the app's output
                logs = app_instance.get_log()
                if logs:
                    for log in logs[-2:]:  # Last two for brevity
                        print(f"App: {log}")
            else:
                # Original non-/ handling preserved
                _line = f"\nUser: {line}"
                if pipboy_ui:
                    pipboy_ui.log_status(f"User: {line}", "INFO")
                _resp = svc.ask(_line)
                if pipboy_ui:
                    pipboy_ui.set_output(_resp)
                else:
                    print(f"{_resp}")

def main():
    parser = argparse.ArgumentParser(prog="robodog",
        description="Combined MCP file-server + Robodog CLI")
    parser.add_argument('--config', default='config.yaml',
                        help='path to robodog YAML config')
    parser.add_argument('--folders', nargs='+', required=True,
                        help='one or more root folders to serve')
    parser.add_argument('--host', default='127.0.0.1',
                        help='MCP host')
    parser.add_argument('--port', type=int, default=2500,
                        help='MCP port')
    parser.add_argument('--token', required=True,
                        help='MCP auth token')
    parser.add_argument('--cert', default=None,
                        help='Path to SSL certificate file (PEM format)')
    parser.add_argument('--key', default=None,
                        help='Path to SSL private key file (PEM format)')
    parser.add_argument('--model', '-m',
                        help='startup model name')
    parser.add_argument('--log-file', default='robodog.log',
                        help='path to log file')
    parser.add_argument('--log-level', default='ERROR',
                        choices=['DEBUG','INFO','WARNING','ERROR','CRITICAL'],
                        help='set root logging level')
    parser.add_argument('--backupFolder', default=r'c:\temp',
                        help='folder to store focus-file backups')
    parser.add_argument('--excludeDirs', default='node_modules,dist,diffout',
                        help='comma-separated list of directories to exclude')
    parser.add_argument('--diff', action='store_true',
                        help='force unified diff output for updates')
    parser.add_argument('--agent-loop', action='store_true',
                        help='enable agentic loop for incremental task execution')
    parser.add_argument('--pipboy', action='store_true',
                        help='enable refreshing terminal UI (ANSI-based)')
    args = parser.parse_args()

    
    # configure colored logging
    root = logging.getLogger()
    root.setLevel(getattr(logging, args.log_level))
    fmt = colorlog.ColoredFormatter(
        "%(log_color)s%(asctime)s:%(reset)s %(message)s",
        datefmt="%H:%M:%S",
        log_colors={
            "DEBUG":    "cyan",
            "VERBOSE":  "blue",
            "INFO":     "green",
            "WARNING":  "yellow",
            "ERROR":    "red",
            "CRITICAL": "bold_red",
            "NOTICE":   "magenta",
            "SUCCESS":  "white",
            "DELTA":    "yellow",       # New: For deltas/percentages (e.g., file changes)
            "PERCENT":  "green",        # New: For positive percentages/metrics
            "HIGHLIGHT":"cyan",         # New: For key highlights like tokens, summaries
        }
    )
    ch = colorlog.StreamHandler(sys.stdout)
    ch.setFormatter(fmt)
    root.addHandler(ch)


    # Enhanced: Test custom colors on startup if in PowerShell/Windows
    if POWERSHELL_ENV and WINDOWS_ANSI_ENABLED:
        logger.info("PowerShell detected with colorama; testing custom colors...", extra={'log_color': 'HIGHLIGHT'})
        logger.info("Standard INFO (green) and custom HIGHLIGHT (cyan) should show.", extra={'log_color': 'HIGHLIGHT'})
        logger.warning("Standard WARNING (yellow) and custom DELTA (yellow) should match.", extra={'log_color': 'DELTA'})
        logger.debug("Standard DEBUG (cyan) and custom PERCENT (green) for positive changes.", extra={'log_color': 'PERCENT'})
        logger.info("If colors are missing in PowerShell, enable via registry (VirtualTerminalLevel=1) or restart PowerShell.", extra={'log_color': 'HIGHLIGHT'})
    elif POWERSHELL_ENV:
        logger.warning("PowerShell detected without full ANSI support; install colorama for better colors.", extra={'log_color': 'WARNING'})

    logging.info("Starting robodog")

    svc, parser = _init_services(args)
    
    # Apply global diff preference from CLI
    try:
        svc.force_diff = bool(args.diff)
    except Exception:
        pass
    
    # Instantiate RobodogApp instance after services for integration
    app_instance = RobodogApp()
    # Wire UI callbacks for planning messages
    svc.set_ui_callback(app_instance.display_command)
    if hasattr(svc, 'todo') and svc.todo:
        svc.todo.set_ui_callback(app_instance.display_command)
        
    server = run_robodogmcp(
        host    = args.host,
        port    = args.port,
        token   = args.token,
        folders = args.folders,
        svc     = svc,
        cert    = args.cert,
        key     = args.key
    )
    logging.info("MCP server on %s:%d", args.host, args.port)
    if args.cert and args.key:
        logging.info("SSL enabled with provided cert and key")

    svc.mcp_cfg['baseUrl'] = f"http{'s' if args.cert and args.key else ''}://{args.host}:{args.port}"
    svc.mcp_cfg['apiKey']  = args.token
    if args.model:
        svc.set_model(args.model)
        logging.info("Startup model set to %s", svc.cur_model)

    # Initialize Simple UI if requested
    pipboy_ui = None
    if args.pipboy:
        try:
            pipboy_ui = SimpleUIWrapper(svc)
            
            # Set up command callback
            def handle_command(line):
                import io
                import sys
                
                # Debug: verify callback is being called
                pipboy_ui.log_status(f"→ {line[:30]}", "INFO")
                
                if line.startswith("/"):
                    cmd, cmd_args = parse_cmd(line)
                    try:
                        if cmd == "help":
                            # Capture help output
                            old_stdout = sys.stdout
                            sys.stdout = buffer = io.StringIO()
                            print_help()
                            sys.stdout = old_stdout
                            pipboy_ui.set_output(buffer.getvalue())
                            
                        elif cmd == "models":
                            models_list = "Available models:\n"
                            models_list += "\n".join([f"  {m}" for m in svc.list_models_about()])
                            models_list += f"\n\nCurrent model: {svc.cur_model}"
                            pipboy_ui.set_output(models_list)
                            
                        elif cmd == "model":
                            if not cmd_args:
                                pipboy_ui.log_status("Usage: /model <model_name>", "WARNING")
                                available = ", ".join(svc.list_models())
                                pipboy_ui.set_output(f"Available models: {available}")
                            else:
                                try:
                                    old_model = svc.cur_model
                                    svc.set_model(cmd_args[0])
                                    pipboy_ui.update_model_name(svc.cur_model)
                                    pipboy_ui.log_status(f"Model changed: {old_model} → {svc.cur_model}", "SUCCESS")
                                except ValueError as e:
                                    pipboy_ui.log_status(str(e), "ERROR")
                                    available = ", ".join(svc.list_models())
                                    pipboy_ui.set_output(f"Available models: {available}")
                                
                        elif cmd == "key":
                            if len(cmd_args) < 2:
                                pipboy_ui.log_status("Usage: /key <provider> <api_key>", "WARNING")
                            else:
                                svc.set_key(cmd_args[0], cmd_args[1])
                                pipboy_ui.log_status(f"API key for '{cmd_args[0]}' set.", "SUCCESS")
                                
                        elif cmd == "getkey":
                            if not cmd_args:
                                pipboy_ui.log_status("Usage: /getkey <provider>", "WARNING")
                            else:
                                key = svc.get_key(cmd_args[0])
                                pipboy_ui.set_output(f"{cmd_args[0]} API key: {key or '<none>'}")
                                
                        elif cmd == "folders":
                            if not cmd_args:
                                pipboy_ui.log_status("Usage: /folders <dir1> [dir2 ...]", "WARNING")
                            else:
                                resp = svc.call_mcp("SET_ROOTS", {"roots": cmd_args})
                                roots = "\n".join([f"  {r}" for r in resp.get("roots", [])])
                                pipboy_ui.set_output(f"MCP server roots:\n{roots}")
                                
                        elif cmd == "include":
                            if not cmd_args:
                                pipboy_ui.log_status("Usage: /include [spec] [prompt]", "WARNING")
                            else:
                                spec_prompt = line[len("/include "):].strip()
                                parts = spec_prompt.split()
                                brk = 1
                                for i, t in enumerate(parts[1:], start=1):
                                    if not (t == "recursive" or t.startswith(("file=", "dir=", "pattern="))):
                                        brk = i
                                        break
                                spec = " ".join(parts[:brk])
                                ptext = " ".join(parts[brk:]) or ""
                                knowledge = svc.include(spec) or ""
                                answer = svc.ask(f"{ptext} {knowledge}".strip())
                                pipboy_ui.set_output(answer)
                                
                        elif cmd == "curl":
                            if not cmd_args:
                                pipboy_ui.log_status("Usage: /curl <url>", "WARNING")
                            else:
                                pipboy_ui.log_status("/curl command not yet implemented", "WARNING")
                                pipboy_ui.set_output(f"Curl functionality coming soon.\nRequested: {' '.join(cmd_args)}")
                            
                        elif cmd == "play":
                            if not cmd_args:
                                pipboy_ui.log_status("Usage: /play <instructions>", "WARNING")
                            else:
                                pipboy_ui.log_status("/play command not yet implemented", "WARNING")
                                pipboy_ui.set_output(f"Playwright functionality coming soon.\nRequested: {' '.join(cmd_args)}")
                            
                        elif cmd == "mcp":
                            if not cmd_args:
                                pipboy_ui.log_status("Usage: /mcp OP [JSON]", "WARNING")
                            else:
                                op = cmd_args[0].upper()
                                raw = " ".join(cmd_args[1:]).strip()
                                payload = {}
                                if raw:
                                    payload = json.loads(raw)
                                res = svc.call_mcp(op, payload)
                                old_stdout = sys.stdout
                                sys.stdout = buffer = io.StringIO()
                                pprint(res)
                                sys.stdout = old_stdout
                                pipboy_ui.set_output(buffer.getvalue())
                                
                        elif cmd == "import":
                            if not cmd_args:
                                pipboy_ui.log_status("Usage: /import <glob>", "WARNING")
                            else:
                                cnt = svc.import_files(cmd_args[0])
                                pipboy_ui.log_status(f"Imported {cnt} files.", "SUCCESS")
                                
                        elif cmd == "export":
                            if not cmd_args:
                                pipboy_ui.log_status("Usage: /export <filename>", "WARNING")
                            else:
                                svc.export_snapshot(cmd_args[0])
                                pipboy_ui.log_status(f"Exported to {cmd_args[0]}.", "SUCCESS")
                                
                        elif cmd == "clear":
                            svc.clear()
                            pipboy_ui.set_output("")
                            pipboy_ui.log_status("Cleared chat history and knowledge", "INFO")
                            
                        elif cmd == "stash":
                            if not cmd_args:
                                pipboy_ui.log_status("Usage: /stash <name>", "WARNING")
                            else:
                                svc.stash(cmd_args[0])
                                pipboy_ui.log_status(f"Stashed under '{cmd_args[0]}'.", "SUCCESS")
                                
                        elif cmd == "pop":
                            if not cmd_args:
                                pipboy_ui.log_status("Usage: /pop <name>", "WARNING")
                            else:
                                svc.pop(cmd_args[0])
                                pipboy_ui.log_status(f"Popped '{cmd_args[0]}' into current session.", "SUCCESS")
                                
                        elif cmd == "list":
                            st = svc.list_stashes()
                            if not st:
                                pipboy_ui.set_output("No stashes.")
                            else:
                                stashes = "\n".join([f"  {name}" for name in st])
                                pipboy_ui.set_output(f"Stashes:\n{stashes}")
                                
                        elif cmd in ("temperature","top_p","max_tokens","frequency_penalty","presence_penalty"):
                            if not cmd_args:
                                pipboy_ui.log_status(f"Usage: /{cmd} <value>", "WARNING")
                            else:
                                val = float(cmd_args[0]) if "." in cmd_args[0] else int(cmd_args[0])
                                svc.set_param(cmd, val)
                                pipboy_ui.log_status(f"{cmd} set to {val}", "SUCCESS")
                                
                        elif cmd == "stream":
                            svc.stream = True
                            pipboy_ui.log_status("Switched to streaming mode.", "SUCCESS")
                            
                        elif cmd == "rest":
                            svc.stream = False
                            pipboy_ui.log_status("Switched to REST mode.", "SUCCESS")
                            
                        elif cmd == "status":
                            dashboard = Dashboard(svc.todo)
                            old_stdout = sys.stdout
                            sys.stdout = buffer = io.StringIO()
                            dashboard.show_full_dashboard()
                            sys.stdout = old_stdout
                            pipboy_ui.set_output(buffer.getvalue())
                            
                        elif cmd == "q":
                            dashboard = Dashboard(svc.todo)
                            old_stdout = sys.stdout
                            sys.stdout = buffer = io.StringIO()
                            dashboard.show_quick_status()
                            sys.stdout = old_stdout
                            pipboy_ui.set_output(buffer.getvalue())
                            
                        elif cmd == "budget":
                            stats = Dashboard(svc.todo).get_statistics()
                            old_stdout = sys.stdout
                            sys.stdout = buffer = io.StringIO()
                            TokenBudgetDisplay.show(stats['total_tokens'])
                            sys.stdout = old_stdout
                            pipboy_ui.set_output(buffer.getvalue())
                            
                        elif cmd == "shortcuts":
                            old_stdout = sys.stdout
                            sys.stdout = buffer = io.StringIO()
                            show_shortcuts()
                            sys.stdout = old_stdout
                            pipboy_ui.set_output(buffer.getvalue())
                        
                        elif cmd == "map":
                            # Code mapping commands
                            if not cmd_args:
                                pipboy_ui.log_status("Usage: /map <scan|find|context|save|load>", "WARNING")
                                pipboy_ui.set_output("Code Map Commands:\n/map scan - Scan codebase\n/map find <name> - Find definition\n/map context <task> - Get context for task\n/map save <file> - Save map\n/map load <file> - Load map")
                            elif cmd_args[0] == "scan":
                                pipboy_ui.log_status("Scanning codebase...", "INFO")
                                file_maps = svc.code_mapper.scan_codebase()
                                pipboy_ui.log_status(f"Scanned {len(file_maps)} files", "SUCCESS")
                                pipboy_ui.set_output(f"Code Map Created:\n{len(file_maps)} files mapped\n{len(svc.code_mapper.index['classes'])} classes\n{len(svc.code_mapper.index['functions'])} functions")
                            elif cmd_args[0] == "find":
                                if len(cmd_args) < 2:
                                    pipboy_ui.log_status("Usage: /map find <name>", "WARNING")
                                else:
                                    name = cmd_args[1]
                                    results = svc.code_mapper.find_definition(name)
                                    if not results:
                                        pipboy_ui.set_output(f"No definition found for '{name}'")
                                    else:
                                        output = f"Found {len(results)} definition(s) for '{name}':\n\n"
                                        for r in results:
                                            output += f"{r['type']}: {r['name']}\n"
                                            output += f"  File: {os.path.basename(r['file'])}:{r['line_start']}\n"
                                            if r.get('docstring'):
                                                output += f"  Doc: {r['docstring'][:60]}...\n"
                                        pipboy_ui.set_output(output)
                            elif cmd_args[0] == "context":
                                if len(cmd_args) < 2:
                                    pipboy_ui.log_status("Usage: /map context <task_description>", "WARNING")
                                else:
                                    task_desc = " ".join(cmd_args[1:])
                                    context = svc.code_mapper.get_context_for_task(task_desc)
                                    output = f"Context for: {task_desc}\n\n"
                                    output += f"Keywords: {', '.join(context['keywords'])}\n"
                                    output += f"Relevant files: {context['total_files']}\n\n"
                                    for file_path, info in list(context['relevant_files'].items())[:5]:
                                        output += f"[{info['score']}] {os.path.basename(file_path)}\n"
                                        summary = info['summary']
                                        if summary['classes']:
                                            output += f"  Classes: {', '.join(summary['classes'][:3])}\n"
                                        if summary['functions']:
                                            output += f"  Functions: {', '.join(summary['functions'][:3])}\n"
                                    pipboy_ui.set_output(output)
                            elif cmd_args[0] == "save":
                                if len(cmd_args) < 2:
                                    pipboy_ui.log_status("Usage: /map save <filename>", "WARNING")
                                else:
                                    filename = cmd_args[1]
                                    svc.code_mapper.save_map(filename)
                                    pipboy_ui.log_status(f"Saved map to {filename}", "SUCCESS")
                                    pipboy_ui.set_output(f"Code map saved to:\n{filename}")
                            elif cmd_args[0] == "load":
                                if len(cmd_args) < 2:
                                    pipboy_ui.log_status("Usage: /map load <filename>", "WARNING")
                                else:
                                    filename = cmd_args[1]
                                    svc.code_mapper.load_map(filename)
                                    pipboy_ui.log_status(f"Loaded map from {filename}", "SUCCESS")
                                    pipboy_ui.set_output(f"Code map loaded:\n{len(svc.code_mapper.file_maps)} files")
                            else:
                                pipboy_ui.log_status("Unknown map subcommand", "WARNING")
                                pipboy_ui.set_output("Map commands:\n/map scan\n/map find <name>\n/map context <task>\n/map save <file>\n/map load <file>")
                            
                        elif cmd == "todo":
                            # Todo management commands
                            if not cmd_args:
                                # List all tasks
                                tasks = svc.todo_mgr.list_tasks()
                                if not tasks:
                                    pipboy_ui.set_output("No tasks found.\n\nUse: /todo add <description> to create a task")
                                else:
                                    output = f"Found {len(tasks)} tasks:\n\n"
                                    for task in tasks[:10]:  # Show first 10
                                        # Show three-bracket format
                                        p = task.get('plan_status', 'To Do')
                                        l = task.get('llm_status', 'To Do')
                                        c = task.get('commit_status', 'To Do')
                                        status_map = {'To Do': ' ', 'Doing': '~', 'Done': 'x', 'Ignore': '-'}
                                        p_char = status_map.get(p, ' ')
                                        l_char = status_map.get(l, ' ')
                                        c_char = status_map.get(c, ' ')
                                        output += f"[{p_char}][{l_char}][{c_char}] {task['description']}\n"
                                        output += f"    Plan:{p} LLM:{l} Commit:{c}\n"
                                        output += f"    {os.path.basename(task['file'])}:{task['line_number']}\n"
                                    if len(tasks) > 10:
                                        output += f"\n... and {len(tasks) - 10} more"
                                    pipboy_ui.set_output(output)
                            elif cmd_args[0] == "add":
                                # Add a new task
                                if len(cmd_args) < 2:
                                    pipboy_ui.log_status("Usage: /todo add <description>", "WARNING")
                                else:
                                    desc = " ".join(cmd_args[1:])
                                    result = svc.todo_mgr.add_task(desc)
                                    pipboy_ui.log_status(f"Task added to {os.path.basename(result['path'])}", "SUCCESS")
                                    pipboy_ui.set_output(f"Added task:\n{result['line']}\n\nFile: {result['path']}\nLine: {result['line_number']}")
                            elif cmd_args[0] == "stats":
                                # Show statistics
                                stats = svc.todo_mgr.get_statistics()
                                output = f"Todo Statistics:\n\n"
                                output += f"Total: {stats['total']}\n"
                                output += f"To Do: {stats['todo']}\n"
                                output += f"Doing: {stats['doing']}\n"
                                output += f"Done: {stats['done']}\n"
                                output += f"Ignore: {stats['ignore']}\n\n"
                                if stats['by_file']:
                                    output += "By File:\n"
                                    for file, count in stats['by_file'].items():
                                        output += f"  {os.path.basename(file)}: {count}\n"
                                pipboy_ui.set_output(output)
                            elif cmd_args[0] == "files":
                                # List todo files
                                files = svc.todo_mgr.find_todo_files()
                                if not files:
                                    pipboy_ui.set_output("No todo.md files found")
                                else:
                                    output = f"Found {len(files)} todo.md files:\n\n"
                                    for f in files:
                                        output += f"  {f}\n"
                                    pipboy_ui.set_output(output)
                            elif cmd_args[0] == "create":
                                # Create a new todo.md
                                path = cmd_args[1] if len(cmd_args) > 1 else None
                                created = svc.todo_mgr.create_todo_file(path)
                                pipboy_ui.log_status(f"Created {os.path.basename(created)}", "SUCCESS")
                                pipboy_ui.set_output(f"Created todo.md at:\n{created}")
                            else:
                                pipboy_ui.log_status("Unknown todo subcommand", "WARNING")
                                pipboy_ui.set_output("Todo commands:\n/todo - list tasks\n/todo add <desc> - add task\n/todo stats - show statistics\n/todo files - list todo files\n/todo create [path] - create todo.md")
                        
                        elif cmd == "test":
                            # Test command to verify UI is working
                            pipboy_ui.log_status("Test command executed", "SUCCESS")
                            pipboy_ui.set_output("UI Test Output\n\nIf you can see this, the OUTPUT panel is working!\nStatus messages appear in the STATUS panel above.")
                            
                        else:
                            pipboy_ui.log_status(f"Unknown command: /{cmd}", "WARNING")
                            pipboy_ui.set_output(f"Unknown command: /{cmd}\n\nType /help to see all available commands.")
                            
                    except Exception as e:
                        pipboy_ui.log_status(f"Error: {str(e)}", "ERROR")
                        import traceback
                        pipboy_ui.set_output(traceback.format_exc())
                else:
                    # Regular message to AI
                    _line = f"\nUser: {line}"
                    pipboy_ui.log_status(f"Asking AI: {line}", "INFO")
                    _resp = svc.ask(_line)
                    pipboy_ui.set_output(_resp)
            
            logging.info("Starting Simple UI...")
            pipboy_ui.start()
            
            # Set callback AFTER UI starts so app exists
            pipboy_ui.set_command_callback(handle_command)
            
            pipboy_ui.log_status("ROBODOG SYSTEM ONLINE", "SUCCESS")
            pipboy_ui.log_status(f"Model: {svc.cur_model}", "INFO")
            pipboy_ui.log_status("Type /help for commands", "INFO")
        except Exception as e:
            logging.error(f"Failed to start Simple UI: {e}")
            pipboy_ui = None

    try:
        if pipboy_ui:
            # In Simple UI mode, wait for UI to close
            pipboy_ui.wait()
        else:
            # Traditional CLI mode
            interact(svc, app_instance, pipboy_ui)  # Pass pipboy_ui to interact
    finally:
        logging.info("Shutting down MCP server")
        server.shutdown()
        server.server_close()

if __name__ == '__main__':
    main()

# Original file length: 466 lines
# Updated file length: 502 lines