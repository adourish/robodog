# file: robodog/base.py
#!/usr/bin/env python3
"""Base classes and common utilities for robodog services."""
from typing import List, Optional, Dict, Any
from pathlib import Path
import os
import logging

logger = logging.getLogger(__name__)


class BaseService:
    """Base class for all robodog services."""
    
    def __init__(self, roots: List[str] = None):
        self._roots = roots or [os.getcwd()]
    
    @property
    def roots(self) -> List[str]:
        """Get the root directories."""
        return self._roots
    
    @roots.setter
    def roots(self, value: List[str]):
        """Set the root directories."""
        self._roots = value or [os.getcwd()]


class TaskBase:
    """Base class for task-related functionality."""
    
    STATUS_MAP = {' ': 'To Do', '~': 'Doing', 'x': 'Done'}
    REVERSE_STATUS = {v: k for k, v in STATUS_MAP.items()}
    
    @staticmethod
    def format_summary(indent: str, start: str, end: Optional[str] = None,
                      know: Optional[int] = None, prompt: Optional[int] = None,
                      incount: Optional[int] = None, include: Optional[int] = None,
                      cur_model: str = None) -> str:
        """Format a task summary line."""
        parts = [f"started: {start}"]
        if end:
            parts.append(f"completed: {end}")
        if know is not None:
            parts.append(f"knowledge_tokens: {know}")
        if include is not None:
            parts.append(f"include_tokens: {include}")
        if prompt is not None:
            parts.append(f"prompt_tokens: {prompt}")
        if cur_model:
            parts.append(f"cur_model: {cur_model}")
        return f"{indent}  - " + " | ".join(parts) + "\n"

# original file length: 45 lines
# updated file length: 45 lines

# file: robodog/cli.py
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
import colorlog

# support both "python -m robodog.cli" and "python cli.py" invocations:
try:
    from .service import RobodogService
    from .mcphandler import run_robodogmcp
    from .todo import TodoService
    from .parse_service import ParseService
    from .file_service import FileService
    from .task_manager import TaskManager
    from .prompt_builder import PromptBuilder
except ImportError:
    from service import RobodogService
    from mcphandler import run_robodogmcp
    from todo import TodoService
    from parse_service import ParseService
    from file_service import FileService
    from task_manager import TaskManager
    from prompt_builder import PromptBuilder

def print_help():
    cmds = {
        "help":                "show this help",
        "models":              "list configured models",
        "model <name>":        "switch model",
        "key <prov> <key>":    "set API key for provider",
        "getkey <prov>":       "get API key for provider",
        "import <glob>":       "import files into knowledge",
        "export <file>":       "export chat+knowledge snapshot",
        "clear":               "clear chat+knowledge",
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

def interact(svc: RobodogService):
    prompt_symbol = lambda: f"[{svc.cur_model}]{'»' if svc.stream else '>'} "
    logging.info("robodog CLI — type /help to list commands.")
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
                        print(answer)

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
                    logging.info("Cleared chat history and knowledge.")

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
                    logging.info("Switched to REST mode.")

                elif cmd == "todo":
                    svc.todo.run_next_task(svc)

                else:
                    logging.error("unknown /cmd: %s", cmd)

            except Exception:
                logging.exception("Error processing command")

        else:
            _line = f"\nUser: {line}"
            _resp = svc.ask(_line)
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
    parser.add_argument('--model', '-m',
                        help='startup model name')
    parser.add_argument('--log-file', default='robodog.log',
                        help='path to log file')
    parser.add_argument('--log-level', default='INFO',
                        choices=['DEBUG','INFO','WARNING','ERROR','CRITICAL'],
                        help='set root logging level')
    parser.add_argument('--backupFolder', default=r'c:\temp',
                        help='folder to store focus-file backups')
    args = parser.parse_args()

    # configure colored logging
    root = logging.getLogger()
    root.setLevel(getattr(logging, args.log_level))
    fmt = colorlog.ColoredFormatter(
        "%(log_color)s[%(asctime)s] %(levelname)s:%(reset)s %(message)s",
        log_colors={
            "DEBUG":    "cyan",
            "INFO":     "green",
            "WARNING":  "yellow",
            "ERROR":    "red",
            "CRITICAL": "bold_red",
        }
    )
    ch = colorlog.StreamHandler(sys.stdout)
    ch.setFormatter(fmt)
    root.addHandler(ch)
    fh = logging.FileHandler(args.log_file)
    fh.setFormatter(logging.Formatter('[%(asctime)s] %(levelname)s: %(message)s'))
    root.addHandler(fh)

    logging.info("Starting robodog")

    # Initialize services
    svc = RobodogService(args.config)
    parse_service = ParseService()
    file_service = FileService(args.folders)
    task_manager = TaskManager()
    prompt_builder = PromptBuilder()
    
    # Initialize todo service with all dependencies
    svc.todo = TodoService(args.folders, svc, file_service, task_manager, parse_service, prompt_builder)
    svc.backup_folder = args.backupFolder

    server = run_robodogmcp(
        host    = args.host,
        port    = args.port,
        token   = args.token,
        folders = args.folders,
        svc     = svc
    )
    logging.info("MCP server on %s:%d", args.host, args.port)

    svc.mcp_cfg['baseUrl'] = f"http://{args.host}:{args.port}"
    svc.mcp_cfg['apiKey']  = args.token
    if args.model:
        svc.set_model(args.model)
        logging.info("Startup model set to %s", svc.cur_model)

    try:
        interact(svc)
    finally:
        logging.info("Shutting down MCP server")
        server.shutdown()
        server.server_close()

if __name__ == '__main__':
    main()

# original file length: 217 lines
# updated file length: 228 lines

# file: robodog/file_service.py
#!/usr/bin/env python3
"""File operations and path resolution service."""
import os
import logging
from typing import List, Optional
from pathlib import Path

logger = logging.getLogger(__name__)


class FileService:
    """Handles file operations and path resolution."""
    
    def __init__(self, roots: List[str], base_dir: str = None):
        self._roots = roots
        self._base_dir = base_dir
    
    @property
    def base_dir(self) -> Optional[str]:
        return self._base_dir
    
    @base_dir.setter
    def base_dir(self, value: str):
        self._base_dir = value
    
    def find_files_by_pattern(self, pattern: str, recursive: bool, svc=None) -> List[str]:
        """Find files matching the given glob pattern."""
        if svc:
            return svc.search_files(patterns=pattern, recursive=recursive, roots=self._roots)
        return []
    
    def find_matching_file(self, filename: str, include_spec: dict, svc=None) -> Optional[Path]:
        """Find a file by name based on the include pattern."""
        files = self.find_files_by_pattern(
            include_spec['pattern'], 
            include_spec.get('recursive', False),
            svc
        )
        for f in files:
            if Path(f).name == filename:
                return Path(f)
        return None
    
    def resolve_path(self, frag: str) -> Optional[Path]:
        """Resolve a file fragment to an absolute path."""
        if not frag:
            return None
        
        f = frag.strip('"').strip('`')
        
        # Simple filename in base_dir
        if self._base_dir and not any(sep in f for sep in (os.sep,'/','\\')):
            candidate = Path(self._base_dir) / f
            return candidate.resolve()
        
        # Path with separators in base_dir
        if self._base_dir and any(sep in f for sep in ('/','\\')):
            candidate = Path(self._base_dir) / Path(f)
            candidate.parent.mkdir(parents=True, exist_ok=True)
            return candidate.resolve()
        
        # Search in roots
        search_roots = ([self._base_dir] if self._base_dir else []) + self._roots
        for root in search_roots:
            cand = Path(root) / f
            if cand.is_file():
                return cand.resolve()
        
        # Create in first root
        p = Path(f)
        base = Path(self._roots[0]) / p.parent
        base.mkdir(parents=True, exist_ok=True)
        return (base / p.name).resolve()
    
    def safe_read_file(self, path: Path) -> str:
        """Safely read a file, handling binary files and encoding issues."""
        logger.debug(f"Safe read of: {path.absolute()}")
        try:
            # Check for binary content
            with open(path, 'rb') as bf:
                if b'\x00' in bf.read(1024):
                    raise UnicodeDecodeError("binary", b"", 0, 1, "null")
            return path.read_text(encoding='utf-8')
        except UnicodeDecodeError:
            try:
                return path.read_text(encoding='utf-8', errors='ignore')
            except:
                return ""
        except:
            return ""

# original file length: 82 lines
# updated file length: 82 lines

# file: robodog/file_watcher.py
#!/usr/bin/env python3
"""File watching service for monitoring todo.md changes."""
import os
import time
import threading
import logging
from typing import Dict, Callable, Any
from pathlib import Path

logger = logging.getLogger(__name__)


class FileWatcher:
    """Watches files for changes and triggers callbacks."""
    
    def __init__(self):
        self._mtimes: Dict[str, float] = {}
        self._watch_ignore: Dict[str, float] = {}
        self._callbacks: Dict[str, Callable] = {}
        self._running = False
        self._thread = None
    
    def add_file(self, filepath: str, callback: Callable[[str], None]):
        """Add a file to watch with a callback."""
        self._callbacks[filepath] = callback
        try:
            self._mtimes[filepath] = os.path.getmtime(filepath)
        except OSError:
            self._mtimes[filepath] = 0
    
    def ignore_next_change(self, filepath: str):
        """Ignore the next change to a file (for our own writes)."""
        try:
            self._watch_ignore[filepath] = os.path.getmtime(filepath)
        except OSError:
            pass
    
    def start(self):
        """Start the file watcher thread."""
        if self._running:
            return
        
        self._running = True
        self._thread = threading.Thread(target=self._watch_loop, daemon=True)
        self._thread.start()
    
    def stop(self):
        """Stop the file watcher thread."""
        self._running = False
        if self._thread:
            self._thread.join()
    
    def _watch_loop(self):
        """Main watch loop that runs in a separate thread."""
        while self._running:
            for filepath, callback in self._callbacks.items():
                try:
                    mtime = os.path.getmtime(filepath)
                except OSError:
                    continue
                
                # Check if we should ignore this change
                ignore_time = self._watch_ignore.get(filepath)
                if ignore_time and abs(mtime - ignore_time) < 0.001:
                    self._watch_ignore.pop(filepath, None)
                    continue
                
                # Check if file has been modified
                if self._mtimes.get(filepath, 0) and mtime > self._mtimes[filepath]:
                    logger.debug(f"Detected change in {filepath}")
                    try:
                        callback(filepath)
                    except Exception as e:
                        logger.error(f"Error in file watch callback: {e}")
                
                # Update stored mtime
                self._mtimes[filepath] = mtime
            
            time.sleep(1)

# original file length: 71 lines
# updated file length: 71 lines

# file: robodog/mcphandler.py
#!/usr/bin/env python3
import os
import json
import threading
import socketserver
import fnmatch
import hashlib
import shutil
import logging

try:
    from .service import RobodogService
except ImportError:
    from service import RobodogService

logger = logging.getLogger('robodog.mcphandler')

ROOTS   = []
TOKEN   = None
SERVICE = None

class MCPHandler(socketserver.StreamRequestHandler):
    def handle(self):
        raw = self.rfile.readline()
        if not raw:
            return
        first = raw.decode('utf-8', errors='ignore').rstrip('\r\n')
        # detect HTTP vs raw MCP
        is_http = first.upper().startswith(("GET ","POST ","OPTIONS ")) and "HTTP/" in first
        if is_http:
            return self._handle_http(first)
        # raw MCP
        op, _, arg = first.partition(" ")
        try:
            payload = json.loads(arg) if arg.strip() else {}
        except json.JSONDecodeError:
            return self._write_json({"status":"error","error":"Invalid JSON payload"})
        resp = self._dispatch(op.upper(), payload)
        self._write_json(resp)

    def _handle_http(self, first_line):
        # parse HTTP request + CORS + auth + body
        try:
            method, uri, version = first_line.split(None, 2)
        except ValueError:
            return
        headers = {}
        # read headers
        while True:
            line = self.rfile.readline().decode('utf-8', errors='ignore')
            if not line or line in ('\r\n','\n'):
                break
            key, val = line.split(":",1)
            headers[key.lower().strip()] = val.strip()

        if method.upper() == 'OPTIONS':
            resp = [
                "HTTP/1.1 204 No Content",
                "Access-Control-Allow-Origin: *",
                "Access-Control-Allow-Methods: POST, OPTIONS",
                "Access-Control-Allow-Headers: Content-Type, Authorization",
                "Connection: close", "", ""
            ]
            self.wfile.write(("\r\n".join(resp)).encode('utf-8'))
            return

        if method.upper() != 'POST':
            resp = [
                "HTTP/1.1 405 Method Not Allowed",
                "Access-Control-Allow-Origin: *",
                "Allow: POST, OPTIONS",
                "Connection: close", "", "Only POST supported"
            ]
            self.wfile.write(("\r\n".join(resp)).encode('utf-8'))
            return

        # auth
        if headers.get('authorization') != f"Bearer {TOKEN}":
            body = json.dumps({"status":"error","error":"Authentication required"})
            resp = [
                "HTTP/1.1 401 Unauthorized",
                "Access-Control-Allow-Origin: *",
                "Content-Type: application/json",
                f"Content-Length: {len(body)}",
                "Connection: close", "", body
            ]
            self.wfile.write(("\r\n".join(resp)).encode('utf-8'))
            return

        length = int(headers.get('content-length','0'))
        body_raw = self.rfile.read(length).decode('utf-8', errors='ignore')
        op, _, arg = body_raw.partition(" ")
        try:
            payload = json.loads(arg) if arg.strip() else {}
        except json.JSONDecodeError:
            result = {"status":"error","error":"Invalid JSON payload"}
        else:
            result = self._dispatch(op.upper(), payload)

        body = json.dumps(result, ensure_ascii=False)
        resp = [
            "HTTP/1.1 200 OK",
            "Access-Control-Allow-Origin: *",
            "Content-Type: application/json; charset=utf-8",
            f"Content-Length: {len(body.encode('utf-8'))}",
            "Connection: close", "", body
        ]
        self.wfile.write(("\r\n".join(resp)).encode('utf-8'))

    def _write_json(self, obj):
        data = json.dumps(obj) + "\n"
        self.wfile.write(data.encode('utf-8'))

    def _dispatch(self, op, p):
        try:
            # --- file‐service ops ---
            if op == "HELP":
                return {"status":"ok","commands":[
                    "LIST_FILES","GET_ALL_CONTENTS","READ_FILE","UPDATE_FILE",
                    "CREATE_FILE","DELETE_FILE","APPEND_FILE","CREATE_DIR",
                    "DELETE_DIR","RENAME","MOVE","COPY_FILE","SEARCH",
                    "CHECKSUM","TODO","INCLUDE","CURL","PLAY",
                    "QUIT","EXIT"
                ]}

            if op == "SET_ROOTS":
                roots = p.get("roots")
                if not isinstance(roots, list):
                    raise ValueError("Missing 'roots' list")
                absr = [os.path.abspath(r) for r in roots]
                for r in absr:
                    if not os.path.isdir(r):
                        raise FileNotFoundError(f"Not a directory: {r}")
                global ROOTS; ROOTS = absr
                return {"status":"ok","roots":ROOTS}

            if op == "LIST_FILES":
                files = SERVICE.list_files(ROOTS)
                return {"status":"ok","files":files}

            if op == "GET_ALL_CONTENTS":
                contents = SERVICE.get_all_contents(ROOTS)
                return {"status":"ok","contents":contents}

            if op == "READ_FILE":
                path = p.get("path") or ""
                if not path: raise ValueError("Missing 'path'")
                data = SERVICE.read_file(path)
                return {"status":"ok","path":path,"content":data}

            if op == "UPDATE_FILE":
                path = p.get("path") or ""
                if not path: raise ValueError("Missing 'path'")
                content = p.get("content","")
                if not os.path.exists(path):
                    SERVICE.create_file(path, content)
                else:
                    SERVICE.update_file(path, content)
                return {"status":"ok","path":path}

            if op == "CREATE_FILE":
                path = p.get("path") or ""
                content = p.get("content","")
                if not path: raise ValueError("Missing 'path'")
                SERVICE.create_file(path, content)
                return {"status":"ok","path":path}

            if op == "DELETE_FILE":
                path = p.get("path") or ""
                if not path: raise ValueError("Missing 'path'")
                SERVICE.delete_file(path)
                return {"status":"ok","path":path}

            if op == "APPEND_FILE":
                path = p.get("path") or ""
                content = p.get("content","")
                if not path: raise ValueError("Missing 'path'")
                SERVICE.append_file(path, content)
                return {"status":"ok","path":path}

            if op == "CREATE_DIR":
                path = p.get("path") or ""
                mode = p.get("mode", 0o755)
                if not path: raise ValueError("Missing 'path'")
                SERVICE.create_dir(path, mode)
                return {"status":"ok","path":path}

            if op == "DELETE_DIR":
                path = p.get("path") or ""
                rec  = bool(p.get("recursive", False))
                if not path: raise ValueError("Missing 'path'")
                SERVICE.delete_dir(path, rec)
                return {"status":"ok","path":path}

            if op in ("RENAME","MOVE"):
                src = p.get("src") or p.get("path")
                dst = p.get("dst") or p.get("dest")
                if not src or not dst:
                    raise ValueError("Missing 'src' or 'dst'")
                SERVICE.rename(src, dst)
                return {"status":"ok","src":src,"dst":dst}

            if op == "COPY_FILE":
                src = p.get("src")
                dst = p.get("dst")
                if not src or not dst:
                    raise ValueError("Missing 'src' or 'dst'")
                SERVICE.copy_file(src, dst)
                return {"status":"ok","src":src,"dst":dst}

            if op == "SEARCH":
                patt = p.get("pattern","*")
                rec  = bool(p.get("recursive", True))
                excl = p.get("exclude", None)
                roots = ROOTS if not p.get("root") else [p.get("root")]
                found = SERVICE.search_files(patterns=patt, recursive=rec,
                                             roots=roots, exclude_dirs=excl)
                return {"status":"ok","matches":found}

            if op == "CHECKSUM":
                path = p.get("path") or ""
                if not path: raise ValueError("Missing 'path'")
                cs = SERVICE.checksum(path)
                return {"status":"ok","path":path,"checksum":cs}

            # --- todo ---
            if op == "TODO":
                SERVICE.todo.run_next_task(SERVICE)
                return {"status":"ok"}

            if op == "LIST_TODO_TASKS":
                SERVICE.todo._load_all()  # Load tasks from todo.py's TodoService
                tasks = SERVICE.todo._tasks  # Get the list of tasks
                return {"status":"ok", "tasks": tasks}  # Return as a list of dicts
        
            # --- include/ask ---
            if op == "INCLUDE":
                spec   = p.get("spec","")
                prompt = p.get("prompt","")
                know   = SERVICE.include(spec) or ""
                result = {"status":"ok","knowledge":know}
                if prompt:
                    ans = SERVICE.ask(f"{prompt} {know}".strip())
                    result["answer"] = ans
                return result

            # --- passthrough LLM/meta ---
            if op == "ASK":
                prompt = p.get("prompt")
                if prompt is None: raise ValueError("Missing 'prompt'")
                resp = SERVICE.ask(prompt)
                return {"status":"ok","response":resp}

            if op == "LIST_MODELS":
                return {"status":"ok","models":SERVICE.list_models()}

            if op == "SET_MODEL":
                m = p.get("model")
                SERVICE.set_model(m)
                return {"status":"ok","model":m}

            if op == "SET_KEY":
                prov, key = p.get("provider"), p.get("key")
                SERVICE.set_key(prov, key)
                return {"status":"ok","provider":prov}

            if op == "GET_KEY":
                prov = p.get("provider")
                key  = SERVICE.get_key(prov)
                return {"status":"ok","provider":prov,"key":key}

            if op == "STASH":
                name = p.get("name")
                SERVICE.stash(name)
                return {"status":"ok","stashed":name}

            if op == "POP":
                name = p.get("name")
                SERVICE.pop(name)
                return {"status":"ok","popped":name}

            if op == "LIST_STASHES":
                return {"status":"ok","stashes":SERVICE.list_stashes()}

            if op == "CLEAR":
                SERVICE.clear()
                return {"status":"ok"}

            if op == "IMPORT_FILES":
                cnt = SERVICE.import_files(p.get("pattern",""))
                return {"status":"ok","imported":cnt}

            if op == "EXPORT_SNAPSHOT":
                fn = p.get("filename")
                SERVICE.export_snapshot(fn)
                return {"status":"ok","snapshot":fn}

            if op == "SET_PARAM":
                SERVICE.set_param(p.get("key"), p.get("value"))
                return {"status":"ok"}

            if op == "CURL":
                SERVICE.curl(p.get("tokens", []))
                return {"status":"ok"}

            if op == "PLAY":
                SERVICE.play(p.get("instructions",""))
                return {"status":"ok"}

            if op in ("QUIT","EXIT"):
                return {"status":"ok","message":"Goodbye!"}

            raise ValueError(f"Unknown command '{op}'")

        except Exception as e:
            return {"status":"error","error": str(e)}

class ThreadedTCPServer(socketserver.ThreadingMixIn, socketserver.TCPServer):
    daemon_threads      = True
    allow_reuse_address = True

def run_robodogmcp(host: str, port: int, token: str,
                   folders: list, svc: RobodogService):
    """
    Launch a threaded MCP server on (host,port) with bearer‐auth and
    hook into the provided RobodogService instance.
    """
    global TOKEN, ROOTS, SERVICE
    TOKEN   = token
    SERVICE = svc
    ROOTS   = [os.path.abspath(f) for f in folders]
    server  = ThreadedTCPServer((host, port), MCPHandler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server

# original file length: 222 lines
# updated file length: 227 lines

# file: robodog/models.py
#!/usr/bin/env python3
"""Pydantic models for robodog."""
from typing import List, Optional
from pydantic import BaseModel, RootModel


class Change(BaseModel):
    """Represents a file change."""
    path: str
    start_line: int
    end_line: Optional[int]
    new_content: str


class ChangesList(RootModel[List[Change]]):
    """List of changes."""
    pass


class TaskModel(BaseModel):
    """Task model for validation."""
    file: str
    line_no: int
    indent: str
    status_char: str
    write_flag: Optional[str]
    desc: str
    include: Optional[dict] = None
    out: Optional[dict] = None
    knowledge: str = ""
    
    # Private fields for tracking
    _start_stamp: Optional[str] = None
    _know_tokens: int = 0
    _in_tokens: int = 0
    _prompt_tokens: int = 0
    _include_tokens: int = 0


class IncludeSpec(BaseModel):
    """Include specification model."""
    pattern: str
    recursive: bool = False

# original file length: 35 lines
# updated file length: 35 lines

# file: robodog/parse_service.py
#!/usr/bin/env python3
import re
import json
import yaml
import xml.etree.ElementTree as ET
from typing import List, Dict, Tuple, Optional
from pathlib import Path
import logging

logger = logging.getLogger(__name__)

class ParsingError(Exception):
    """Custom exception for parsing errors."""
    pass

class ParseService:
    def __init__(self):
        # Regex patterns for different formats
        self.section_pattern = re.compile(r'^#\s*file:\s*(.+)$', re.MULTILINE | re.IGNORECASE)
        self.md_fenced_pattern = re.compile(r'```([^\n]*)\n(.*?)\n```', re.DOTALL)
        self.filename_pattern = re.compile(r'^([^:]+):\s*(.*)$', re.MULTILINE)

    def parse_llm_output(self, llm_output: str) -> List[Dict[str, str]]:
        """
        Parse LLM output into a list of objects, each with 'filename' and 'content'.
        
        Supports multiple formats with error handling.
        
        Returns:
            List of dicts: [{'filename': str, 'content': str, 'tokens': int}]
            
        Raises:
            ParsingError: If no valid content could be parsed
        """
        logger.info(f"Starting parse of LLM output ({len(llm_output)} chars)")

        try:
            # Try formats in order of most common/reliable
            if self._is_section_format(llm_output):
                logger.debug("Detected section format")
                return self._parse_section_format(llm_output)
            elif self._is_json_format(llm_output):
                logger.debug("Detected JSON format")
                return self._parse_json_format(llm_output)
            elif self._is_yaml_format(llm_output):
                logger.debug("Detected YAML format")
                return self._parse_yaml_format(llm_output)
            elif self._is_xml_format(llm_output):
                logger.debug("Detected XML format")
                return self._parse_xml_format(llm_output)
            elif self._is_md_fenced_format(llm_output):
                logger.debug("Detected Markdown fenced format")
                return self._parse_md_fenced_format(llm_output)
            else:
                logger.info("No specific format detected, trying generic parsing")
                return self._parse_generic_format(llm_output)
        except Exception as e:
            logger.error(f"Parsing error: {e}")
            # Fallback to best-effort parsing
            try:
                return self._parse_fallback(llm_output)
            except Exception as fallback_e:
                logger.error(f"Fallback parsing also failed: {fallback_e}")
                raise ParsingError(f"Could not parse LLM output: {e}")

    def _is_section_format(self, output: str) -> bool:
        """Check if output follows # file: <filename> format."""
        return bool(self.section_pattern.search(output))

    def _is_json_format(self, output: str) -> bool:
        """Check if output is valid JSON with expected structure."""
        stripped = output.strip()
        if not stripped.startswith('{') and not stripped.startswith('['):
            return False
        try:
            parsed = json.loads(stripped)
            return isinstance(parsed, dict) and 'files' in parsed
        except (json.JSONDecodeError, TypeError):
            return False

    def _is_yaml_format(self, output: str) -> bool:
        """Check if output is valid YAML with expected structure."""
        try:
            parsed = yaml.safe_load(output)
            return isinstance(parsed, dict) and 'files' in parsed
        except (yaml.YAMLError, TypeError):
            return False

    def _is_xml_format(self, output: str) -> bool:
        """Check if output is valid XML with files structure."""
        stripped = output.strip()
        if not stripped.startswith('<'):
            return False
        try:
            root = ET.fromstring(stripped)
            return root.tag == 'files' and len(root) > 0 and root[0].tag == 'file'
        except ET.ParseError:
            return False

    def _is_md_fenced_format(self, output: str) -> bool:
        """Check if output contains Markdown fenced code blocks."""
        return bool(self.md_fenced_pattern.search(output))

    def _parse_section_format(self, output: str) -> List[Dict[str, str]]:
        """Parse # file: <filename> format."""
        matches = list(self.section_pattern.finditer(output))
        parsed_objects = []
        
        for i, match in enumerate(matches):
            filename = match.group(1).strip()
            if not filename:
                logger.warning(f"Empty filename at match {i}, skipping")
                continue
                
            start_pos = match.end()
            end_pos = matches[i + 1].start() if i + 1 < len(matches) else len(output)
            
            content = output[start_pos:end_pos].strip()
            
            # Validate content
            if not self._validate_filename(filename):
                logger.warning(f"Invalid filename: {filename}, skipping")
                continue
                
            parsed_objects.append({
                'filename': filename,
                'content': content,
                'tokens': len(content.split())
            })
        
        logger.info(f"Parsed {len(parsed_objects)} files from section format")
        return parsed_objects

    def _parse_json_format(self, output: str) -> List[Dict[str, str]]:
        """Parse JSON format: {"files": [...]}"""
        parsed = json.loads(output.strip())
        files = parsed.get('files', [])
        
        if not isinstance(files, list):
            raise ParsingError("JSON 'files' field must be an array")
        
        parsed_objects = []
        for item in files:
            filename = item.get('filename', '').strip()
            content = item.get('content', '').strip()
            
            if not self._validate_filename(filename):
                logger.warning(f"Invalid filename: {filename}, skipping")
                continue
                
            parsed_objects.append({
                'filename': filename,
                'content': content,
                'tokens': len(content.split())
            })
        
        logger.info(f"Parsed {len(parsed_objects)} files from JSON format")
        return parsed_objects

    def _parse_yaml_format(self, output: str) -> List[Dict[str, str]]:
        """Parse YAML format: files:\n  - filename: ...\n    content: ..."""
        parsed = yaml.safe_load(output)
        files = parsed.get('files', [])
        
        if not isinstance(files, list):
            raise ParsingError("YAML 'files' field must be a list")
        
        parsed_objects = []
        for item in files:
            filename = item.get('filename', '').strip()
            content = item.get('content', '').strip()
            
            if not self._validate_filename(filename):
                logger.warning(f"Invalid filename: {filename}, skipping")
                continue
                
            parsed_objects.append({
                'filename': filename,
                'content': content,
                'tokens': len(content.split())
            })
        
        logger.info(f"Parsed {len(parsed_objects)} files from YAML format")
        return parsed_objects

    def _parse_xml_format(self, output: str) -> List[Dict[str, str]]:
        """Parse XML format: <files><file>...</file></files>"""
        root = ET.fromstring(output.strip())
        
        if root.tag != 'files':
            raise ParsingError("Root element must be 'files'")
        
        parsed_objects = []
        for file_elem in root.findall('file'):
            filename_elem = file_elem.find('filename')
            content_elem = file_elem.find('content')
            
            if filename_elem is None or content_elem is None:
                continue
                
            filename = filename_elem.text.strip() if filename_elem.text else ''
            content = content_elem.text.strip() if content_elem.text else ''
            
            if not self._validate_filename(filename):
                logger.warning(f"Invalid filename: {filename}, skipping")
                continue
                
            parsed_objects.append({
                'filename': filename,
                'content': content,
                'tokens': len(content.split())
            })
        
        logger.info(f"Parsed {len(parsed_objects)} files from XML format")
        return parsed_objects

    def _parse_md_fenced_format(self, output: str) -> List[Dict[str, str]]:
        """Parse Markdown fenced code blocks."""
        matches = self.md_fenced_pattern.findall(output)
        parsed_objects = []
        
        for info, content in matches:
            filename = info.strip() if info else "unnamed"
            
            if not self._validate_filename(filename):
                logger.warning(f"Invalid filename: {filename}, skipping")
                continue
                
            parsed_objects.append({
                'filename': filename,
                'content': content.strip(),
                'tokens': len(content.split())
            })
        
        logger.info(f"Parsed {len(parsed_objects)} files from Markdown fenced format")
        return parsed_objects

    def _parse_generic_format(self, output: str) -> List[Dict[str, str]]:
        """Best-effort parsing for unrecognized formats."""
        lines = output.split('\n')
        parsed_objects = []
        current_filename = None
        content_lines = []
        
        for line in lines:
            match = self.filename_pattern.match(line)
            if match:
                # Save previous file if exists
                if current_filename and content_lines:
                    content = '\n'.join(content_lines).strip()
                    if self._validate_filename(current_filename):
                        parsed_objects.append({
                            'filename': current_filename,
                            'content': content,
                            'tokens': len(content.split())
                        })
                    content_lines = []
                
                current_filename = match.group(1).strip()
                content_lines.append(match.group(2).strip())
            elif current_filename and line.strip():
                content_lines.append(line.strip())
        
        # Save last file
        if current_filename and content_lines:
            content = '\n'.join(content_lines).strip()
            if self._validate_filename(current_filename):
                parsed_objects.append({
                    'filename': current_filename,
                    'content': content,
                    'tokens': len(content.split())
                })
        
        if not parsed_objects:
            raise ParsingError("No valid files found in generic parsing")
        
        logger.info(f"Parsed {len(parsed_objects)} files from generic format")
        return parsed_objects

    def _parse_fallback(self, output: str) -> List[Dict[str, str]]:
        """Ultimate fallback: treat entire output as single file."""
        logger.warning("Using fallback parser - treating output as single file")
        return [{
            'filename': 'generated.txt',
            'content': output.strip(),
            'tokens': len(output.split())
        }]

    def _validate_filename(self, filename: str) -> bool:
        """Validate filename for safety."""
        if not filename or len(filename) > 255:
            return False
        
        # Check for invalid characters
        invalid_chars = ['<>:"/\\|?*']
        for char in invalid_chars:
            if char in filename:
                return False
        
        # Check for path traversal attempts
        if '..' in filename or filename.startswith('/'):
            return False
        
        return True

    def write_parsed_files(self, parsed_objects: List[Dict[str, str]], base_dir: str = '.'):
        """
        Write parsed files to disk.
        
        Args:
            parsed_objects: List of file objects from parse_llm_output
            base_dir: Base directory to write files to
            
        Returns:
            Dict with success count and error list
        """
        success_count = 0
        errors = []
        base_path = Path(base_dir)
        
        for obj in parsed_objects:
            try:
                filepath = base_path / obj['filename']
                filepath.parent.mkdir(parents=True, exist_ok=True)
                filepath.write_text(obj['content'], encoding='utf-8')
                success_count += 1
                logger.info(f"Written file: {filepath} ({obj['tokens']} tokens)")
            except Exception as e:
                error_msg = f"Failed to write {obj['filename']}: {e}"
                logger.error(error_msg)
                errors.append(error_msg)
        
        logger.info(f"Successfully wrote {success_count} files")
        if errors:
            logger.warning(f"Errors encountered: {len(errors)}")
        
        return {
            'success_count': success_count,
            'errors': errors
        }

# original file length: 256 lines
# updated file length: 256 lines

# file: robodog/prompt_builder.py
#!/usr/bin/env python3
"""Prompt building service for AI interactions."""
import logging
from typing import Dict, Any

logger = logging.getLogger(__name__)


class PromptBuilder:
    """Builds prompts for AI interactions."""
    
    @staticmethod
    def build_task_prompt(task: Dict[str, Any], include_text: str, input_text: str = "") -> str:
        """Build a prompt for a task execution."""
        parts = [
            "Instructions:",
            "A. Produce one or more complete, runnable code files.",
            "B. For each file, begin with exactly:  # file: <filename>  (use only filenames provided in the task; do not guess or infer).",
            "C. Immediately following that line, emit the full file content—including all imports, definitions, and boilerplate—so it can be copied into a file and run.",
            "D. If multiple files are needed, separate them with a single blank line.",
            "E. You can find the <filename.ext> in the Included files knowledge. You will need to modify these files based on the task description and task knowledge.",
            "G. Use the Task description, included knowledge, and any task-specific knowledge when generating each file.",
            "H. Verify that every file is syntactically correct, self-contained, and immediately executable.",
            "I. Add a comment with the original file length and the updated file length.",
            "J. Only change code that must be changed. Do not remove logging. Do not refactor code unless needed for the task.",
            f"Task description: {task['desc']}",
            ""
        ]
        
        if include_text:
            parts.append(f"Included files knowledge:\n{include_text}")
        
        if task.get('knowledge'):
            parts.append(f"Task knowledge:\n{task['knowledge']}")
        
        return "\n".join(parts)

# original file length: 29 lines
# updated file length: 29 lines

# file: robodog/service.py
#!/usr/bin/env python3
import os
import re
import json
import shutil
import fnmatch
import hashlib
import sys
import threading
import concurrent.futures
import asyncio
from pathlib import Path
import requests
import tiktoken
import yaml
from openai import OpenAI
from playwright.async_api import async_playwright
import logging
from typing import List, Optional
logger = logging.getLogger('robodog.service')

class RobodogService:
    def __init__(self, config_path: str, api_key: str = None):
        # --- load YAML config and LLM setup ---
        self._load_config(config_path)
        # --- ensure we always have a _roots attribute ---
        #    If svc.todo is set later by the CLI, include() will pick up svc.todo._roots.
        #    Otherwise we default to cwd.
        self._roots = [os.getcwd()]
        self.stashes = {}
        self._init_llm(api_key)

    def _load_config(self, config_path):
        data = yaml.safe_load(open(config_path, 'r', encoding='utf-8'))
        cfg = data.get("configs", {})
        self.providers = {p["provider"]: p for p in cfg.get("providers", [])}
        self.models = cfg.get("models", [])
        self.mcp_cfg = cfg.get("mcpServer", {})
        self.cur_model = self.models[0]["model"]
        self.stream = self.models[0].get("stream", True)
        self.temperature = 1.0
        self.top_p = 1.0
        self.max_tokens = 1024
        self.frequency_penalty = 0.0
        self.presence_penalty = 0.0

    def _init_llm(self, api_key):
        provider_name = self.model_provider(self.cur_model)
        provider_cfg = self.providers.get(provider_name)

        if not provider_cfg:
            raise RuntimeError(f"No configuration found for provider: {provider_name}")

        self.api_key = (
            api_key
            or os.getenv("OPENAI_API_KEY")
            or provider_cfg.get("apiKey")
        )

        if not self.api_key:
            raise RuntimeError("Missing API key")

        base_url = provider_cfg.get("baseUrl")
        if not base_url:
            raise RuntimeError(f"Missing baseUrl for provider: {provider_name}")

        # Initialize OpenAI client with provider's base URL
        self.client = OpenAI(
            api_key=self.api_key,
            base_url=base_url  # Ensure proper v1 endpoint
        )

    def get_cur_model(self):
        return self.cur_model
    
    def model_provider(self, model_name):
        for m in self.models:
            if m["model"] == model_name:
                return m["provider"]
        return None

    # ————————————————————————————————————————————————————————————
    # CORE LLM /