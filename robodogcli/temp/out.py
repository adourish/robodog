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
# pip install colorlog
import colorlog

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
    from .task_parser import TaskParser
    from .prompt_builder import PromptBuilder
except ImportError:
    from service import RobodogService
    from mcphandler import run_robodogmcp
    from todo import TodoService
    from parse_service import ParseService
    from models import TaskModel, Change, ChangesList, IncludeSpec
    from file_service import FileService
    from file_watcher import FileWatcher
    from task_manager import TaskManager
    from task_parser import TaskParser
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

    svc = RobodogService(args.config)
    parser = ParseService()
    svc.todo = TodoService(args.folders, svc)
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

try:
    from .file_service import FileService
    from .task_manager import TaskManager
    from .prompt_builder import PromptBuilder
except ImportError:
    from file_service import FileService
    from task_manager import TaskManager
    from prompt_builder import PromptBuilder

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
        
        # Initialize services
        self.file_service = FileService(self._roots)
        self.task_manager = TaskManager()
        self.prompt_builder = PromptBuilder()

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
    # CORE LLM / CHAT
    def ask(self, prompt: str) -> str:
        logger.debug(f"ask {prompt!r}")
        messages = [{"role": "user", "content": prompt}]
        resp = self.client.chat.completions.create(
            model=self.cur_model,
            messages=messages,
            temperature=self.temperature,
            top_p=self.top_p,
            frequency_penalty=self.frequency_penalty,
            presence_penalty=self.presence_penalty,
            stream=self.stream,
        )
        spinner = [
            "[•-----]",
            "[-•----]",
            "[--•---]",
            "[---•--]",
            "[----•-]",
            "[-----•]",
            "[----•-]",
            "[---•--]",
            "[--•---]",
            "[-•----]",
            "[•-----]",
            "[-•----]",
            "[--•---]",
            "[---•--]",
            "[----•-]",
            "[-----•]",
            "[----•-]",
            "[---•--]",
            "[--•---]",
            "[-•----]",
            "[•-----]",
            "[-•----]",
            "[--•---]",
            "[---•--]",
            "[----•-]",
            "[-----•]",
            "[----•-]",
            "[---•--]",
            "[--•---]",
            "[-•----]",
        ]
        idx    = 0
        answer = ""
        if self.stream:
            for chunk in resp:
                # accumulate the streamed text
                delta = getattr(chunk.choices[0].delta, "content", None)
                if delta:
                    answer += delta

                # grab the last line (or everything if no newline yet)
                last_line = answer.splitlines()[-1] if "\n" in answer else answer

                # pick our fighter‐vs‐fighter frame
                frame = spinner[idx % len(spinner)]

                # print: [fighters]  [up to 60 chars of last_line][… if truncated]
                sys.stdout.write(
                    f"\r{frame}  {last_line[:60]}{'…' if len(last_line) > 60 else ''}"
                )
                sys.stdout.flush()
                sys.stdout.write(f"\x1b]0;{last_line[:60].strip()}…\x07")
                sys.stdout.flush()
                idx += 1

            # done streaming!
            sys.stdout.write("\n")
        else:
            answer = resp.choices[0].message.content.strip()
        return answer

    # ————————————————————————————————————————————————————————————
    # MODEL / KEY MANAGEMENT
    def list_models(self):
        return [m["model"] for m in self.models]
    
    def list_models_about(self):
        return [m["model"] + ": " + m["about"] for m in self.models]

    def set_model(self, model_name: str):
        if model_name not in self.list_models():
            raise ValueError(f"Unknown model: {model_name}")
        self.cur_model = model_name
        self._init_llm(None)

    def set_key(self, provider: str, key: str):
        if provider not in self.providers:
            raise KeyError(f"No such provider {provider}")
        self.providers[provider]["apiKey"] = key

    def get_key(self, provider: str):
        return self.providers.get(provider, {}).get("apiKey")

    # ————————————————————————————————————————————————————————————
    # STASH / POP / LIST / CLEAR / IMPORT / EXPORT
    def stash(self, name: str):
        self.stashes[name] = str

    def pop(self, name: str):
        if name not in self.stashes:
            raise KeyError(f"No stash {name}")
        return self.stashes[name]

    def list_stashes(self):
        return list(self.stashes.keys())

    def clear(self):
        pass

    def import_files(self, glob_pattern: str) -> int:
        count = 0
        knowledge = ""
        for fn in __import__('glob').glob(glob_pattern, recursive=True):
            try:
                txt = open(fn, 'r', encoding='utf-8', errors='ignore').read()
                knowledge += f"\n\n--- {fn} ---\n{txt}"
                count += 1
            except:
                pass
        return knowledge

    def export_snapshot(self, filename: str):
        with open(filename, 'w', encoding='utf-8') as f:
            f.write("=== Chat History ===\n" + getattr(self, 'context', '') + "\n")
            f.write("=== Knowledge ===\n" + getattr(self, 'knowledge', '') + "\n")

    # ————————————————————————————————————————————————————————————
    # NUMERIC PARAMS
    def set_param(self, key: str, value):
        if not hasattr(self, key):
            raise KeyError(f"No such param {key}")
        setattr(self, key, value)

    # ————————————————————————————————————————————————————————————
    # MCP CLIENT (used by CLI to reach server)
    def call_mcp(self, op: str, payload: dict, timeout: float = 30.0) -> dict:
        url = self.mcp_cfg["baseUrl"]
        headers = {
            "Content-Type": "text/plain",
            "Authorization": f"Bearer {self.mcp_cfg['apiKey']}"
        }
        body = f"{op} {json.dumps(payload)}\n"
        r = requests.post(url, headers=headers, data=body, timeout=timeout)
        r.raise_for_status()
        return json.loads(r.text.strip().splitlines()[-1])

    # ————————————————————————————————————————————————————————————
    # /INCLUDE IMPLEMENTATION
    def parse_include(self, text: str) -> dict:
        parts = text.strip().split()
        cmd = {"type": None, "file": None, "dir": None, "pattern": "*", "recursive": False}
        if not parts:
            return cmd
        p0 = parts[0]
        if p0 == "all":
            cmd["type"] = "all"
        elif p0.startswith("file="):
            spec = p0[5:]
            if re.search(r"[*?\[]", spec):
                cmd.update(type="pattern", pattern=spec, recursive=True)
            else:
                cmd.update(type="file", file=spec)
        elif p0.startswith("dir="):
            spec = p0[4:]
            cmd.update(type="dir", dir=spec)
            for p in parts[1:]:
                if p.startswith("pattern="):
                    cmd["pattern"] = p.split("=", 1)[1]
                if p == "recursive":
                    cmd["recursive"] = True
            if re.search(r"[*?\[]", spec):
                cmd.update(type="pattern", pattern=spec, recursive=True)
        elif p0.startswith("pattern="):
            cmd.update(type="pattern", pattern=p0.split("=", 1)[1], recursive=True)
        return cmd

    def include(self, spec_text: str, prompt: str = None):
        inc = self.parse_include(spec_text)
        knowledge = ""
        searches = []
        if inc["type"] == "dir":
            searches.append({
                "root": inc["dir"],
                "pattern": inc["pattern"],
                "recursive": inc["recursive"]
            })
        else:
            pat = inc["pattern"] if inc["type"] == "pattern" else (inc["file"] or "*")
            searches.append({"pattern": pat, "recursive": True})

        matches = []
        for p in searches:
            root = p.get("root")
            # fix: pick up __roots injected from CLI's TodoService, or default to cwd
            if root:
                roots = [root]
            elif hasattr(self, 'todo') and getattr(self.todo, '_roots', None):
                roots = self.todo._roots
            else:
                roots = self._roots

            found = self.search_files(
                patterns=p.get("pattern", "*"),
                recursive=p.get("recursive", True),
                roots=roots
            )
            matches.extend(found)

        if not matches:
            return None

        included_txts = []

        def _read(path):
            content = self.read_file(path)
            return path, content

        with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
            for path, txt in pool.map(_read, matches):
                try:
                    enc = tiktoken.encoding_for_model(self.cur_model)
                except:
                    enc = tiktoken.get_encoding("gpt2")
                wc = len(txt.split())
                tc = len(enc.encode(txt))
                logger.info(f"Included: {path} ({tc} tokens)")
                included_txts.append("# file: " + path)
                included_txts.append(txt)
                combined = "\n".join(included_txts)
                knowledge += "\n" + combined + "\n"

        return knowledge

    # Default exclude directories
    DEFAULT_EXCLUDE_DIRS = {"node_modules", "dist"}

    def search_files(self, patterns="*", recursive=True, roots=None, exclude_dirs=None):
        if isinstance(patterns, str):
            patterns = patterns.split("|")
        else:
            patterns = list(patterns)
        exclude_dirs = set(exclude_dirs or self.DEFAULT_EXCLUDE_DIRS)
        matches = []
        for root in roots or []:
            if not os.path.isdir(root):
                continue
            if recursive:
                for dirpath, dirnames, filenames in os.walk(root):
                    dirnames[:] = [d for d in dirnames if d not in exclude_dirs]
                    for fn in filenames:
                        full = os.path.join(dirpath, fn)
                        for pat in patterns:
                            if fnmatch.fnmatch(full, pat) or fnmatch.fnmatch(fn, pat):
                                matches.append(full)
                                break
            else:
                for fn in os.listdir(root):
                    full = os.path.join(root, fn)
                    if not os.path.isfile(full) or fn in exclude_dirs:
                        continue
                    for pat in patterns:
                        if fnmatch.fnmatch(full, pat) or fnmatch.fnmatch(fn, pat):
                            matches.append(full)
                            break
        return matches

    # ————————————————————————————————————————————————————————————
    # /CURL IMPLEMENTATION
    def curl(self, tokens: list):
        pass

    # ————————————————————————————————————————————————————————————
    # /PLAY IMPLEMENTATION
    def play(self, instructions: str):
        pass

    # ————————————————————————————————————————————————————————————
    # MCP-SERVER FILE-OPS
    def read_file(self, path: str):
        return open(path, 'r', encoding='utf-8').read()

    def update_file(self, path: str, content: str):
        open(path, 'w', encoding='utf-8').write(content)

    def create_file(self, path: str, content: str = ""):
        os.makedirs(os.path.dirname(path), exist_ok=True)
        open(path, 'w', encoding='utf-8').write(content)

    def delete_file(self, path: str):
        os.remove(path)

    def append_file(self, path: str, content: str):
        open(path, 'a', encoding='utf-8').write(content)

    def create_dir(self, path: str, mode: int = 0o755):
        os.makedirs(path, mode, exist_ok=True)

    def delete_dir(self, path: str, recursive: bool = False):
        if recursive:
            shutil.rmtree(path)
        else:
            os.rmdir(path)

    def rename(self, src: str, dst: str):
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        os.rename(src, dst)

    def copy_file(self, src: str, dst: str):
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        shutil.copy2(src, dst)

    def list_files(self, roots: List[str]) -> List[str]:
        """List all files in the given roots."""
        files = []
        for root in roots:
            for dirpath, dirnames, filenames in os.walk(root):
                for filename in filenames:
                    files.append(os.path.join(dirpath, filename))
        return files

    def get_all_contents(self, roots: List[str]) -> str:
        """Get contents of all files in roots."""
        contents = []
        files = self.list_files(roots)
        for filepath in files:
            try:
                content = self.read_file(filepath)
                contents.append(f"# file: {filepath}\n{content}")
            except Exception as e:
                logger.warning(f"Could not read {filepath}: {e}")
        return "\n\n".join(contents)

    def checksum(self, path: str):
        h = hashlib.sha256()
        with open(path, 'rb') as f:
            for chunk in iter(lambda: f.read(8192), b''):
                h.update(chunk)
        return h.hexdigest()

# original file length: 261 lines
# updated file length: 284 lines