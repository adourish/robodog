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



def print_help():
    cmds = {
        "help":                "show this help",
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
        "todo":                "run next To Do task",
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
        svc=svc
    )
    svc.task_manager = task_manager

    # 5) prompt builder for formalizing AI prompts
    svc.prompt_builder = PromptBuilder()
    todo_util = TodoUtilService(args.folders, svc, svc.prompt_builder, svc.task_manager, svc.task_parser, svc.file_watcher, svc.file_service, exclude_dirs=exclude_dirs)

    # 6) todo runner / watcher
    svc.todo = TodoService(args.folders, svc, svc.prompt_builder, svc.task_manager, svc.task_parser, svc.file_watcher, svc.file_service, exclude_dirs=exclude_dirs, todo_util=todo_util)



    return svc, parser

def interact(svc: RobodogService, app_instance: RobodogApp):  # Modified to accept app_instance
    prompt_symbol = lambda: f"[{svc.cur_model}]{'»' if svc.stream else '>'} "
    logging.info("robodog CLI — type /help to list commands.")
    # Sample messages for RobodogApp integration
    sample_messages = ["echo test", "help", "/help"]  # Predefined sample patterns
    while True:
        try:
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
                    for m in svc.list_models_about():
                        logging.info("  %s", m)

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

                elif cmd == "todo":
                    # Optionally integrate app log for /todo
                    svc.todo.run_next_task(svc)
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
                _resp = svc.ask(_line)
                print(f"{_resp}")

def enable_powershell_ansi():
    """
    Attempt to enable virtual terminal processing for ANSI colors in PowerShell on Windows.
    Checks and sets the registry key if possible (requires admin rights; otherwise, warn).
    This is to fix color issues in PowerShell 5.1 and earlier without external tweaks.
    """
    if os.name != 'nt' or not POWERSHELL_ENV:
        return
    try:
        import winreg
        key_path = r"SOFTWARE\Microsoft\Windows\CurrentVersion\Console"
        reg_key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path, 0, winreg.KEY_READ | winreg.KEY_WRITE)
        vt_level, vt_type = winreg.QueryValueEx(reg_key, "VirtualTerminalLevel")
        if vt_level == 0:
            winreg.SetValueEx(reg_key, "VirtualTerminalLevel", 0, winreg.REG_DWORD, 1)
            print("Enabled VirtualTerminalLevel=1 for ANSI colors in PowerShell. Restart PowerShell for changes to take effect.")
        else:
            print(f"VirtualTerminalLevel already set to {vt_level}. Colors should work.")
        winreg.CloseKey(reg_key)
    except ImportError:
        logger.warning("winreg module available only on Windows.")
    except PermissionError:
        logger.warning("Requires admin to set VirtualTerminalLevel. Run PowerShell as admin once to fix colors, or enable manually via registry.")
    except Exception as e:
        logger.warning(f"Could not set VirtualTerminalLevel: {e}. ANSI colors may not display.")

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
    args = parser.parse_args()

    # Enhanced: Enable Virtual Terminal for ANSI colors in PowerShell
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
    
    # Instantiate RobodogApp instance after services for integration
    app_instance = RobodogApp()
    app_instance.run()
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

    try:
        interact(svc, app_instance)  # Pass app_instance to interact
    finally:
        logging.info("Shutting down MCP server")
        server.shutdown()
        server.server_close()

if __name__ == '__main__':
    main()

# Original file length: 466 lines
# Updated file length: 502 lines