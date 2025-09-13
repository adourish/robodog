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
                    ans = svc.todo.run_next_task(svc)
                    if ans:
                        print(ans)

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

# original file length: 228 lines
# updated file length: 230 lines


# file: robodog/todo.py
#!/usr/bin/env python3
import os
import re
import time
import threading
import logging
import shutil
from datetime import datetime
from pathlib import Path
from typing import List, Optional

import tiktoken
from pydantic import BaseModel, RootModel
import yaml   # ensure PyYAML is installed

try:
    from .parse_service import ParseService
except ImportError:
    from parse_service import ParseService

logger = logging.getLogger(__name__)

# Updated TASK_RE to capture optional second‐bracket 'write' flag,
# allowing "[x][ ]" or "[x] [ ]" with optional whitespace between brackets
TASK_RE = re.compile(
    r'^(\s*)-\s*'                  # indent + "- "
    r'\[(?P<status>[ x~])\]'       # first [status]
    r'(?:\s*\[(?P<write>[ x~-])\])?'  # optional [write_flag], whitespace allowed
    r'\s*(?P<desc>.+)$'            # space + desc
)
SUB_RE = re.compile(
    r'^\s*-\s*(?P<key>include|out|in|focus):\s*'
    r'(?:pattern=|file=)?(?P<pattern>"[^"]+"|`[^`]+`|\S+)'
    r'(?:\s+(?P<rec>recursive))?'
)

STATUS_MAP     = {' ': 'To Do', '~': 'Doing', 'x': 'Done'}
REVERSE_STATUS = {v: k for k, v in STATUS_MAP.items()}

class Change(BaseModel):
    path: str
    start_line: int
    end_line: Optional[int]
    new_content: str

class ChangesList(RootModel[List[Change]]):
    pass

class TodoService:
    FILENAME = 'todo.md'

    def __init__(self, roots: List[str], svc=None):
        self._roots        = roots
        self._file_lines   = {}
        self._tasks        = []
        self._mtimes       = {}
        self._watch_ignore = {}
        self._svc          = svc
        self.parser        = ParseService()
        self._processed    = set()  # track manually processed tasks

        # MVP: parse a `base:` directive from front-matter
        self._base_dir = self._parse_base_dir()

        self._load_all()
        for fn in self._find_files():
            try:
                self._mtimes[fn] = os.path.getmtime(fn)
            except:
                pass

        threading.Thread(target=self._watch_loop, daemon=True).start()

    def _parse_base_dir(self) -> Optional[str]:
        for fn in self._find_files():
            text = Path(fn).read_text(encoding='utf-8')
            lines = text.splitlines()
            if not lines or lines[0].strip() != '---':
                continue
            try:
                end_idx = lines.index('---', 1)
            except ValueError:
                continue
            for lm in lines[1:end_idx]:
                stripped = lm.strip()
                if stripped.startswith('base:'):
                    _, _, val = stripped.partition(':')
                    base = val.strip()
                    if base:
                        return os.path.normpath(base)
        return None

    def _find_files(self) -> List[str]:
        out = []
        for r in self._roots:
            for dp, _, fns in os.walk(r):
                if self.FILENAME in fns:
                    out.append(os.path.join(dp, self.FILENAME))
        return out

    def _find_files_by_pattern(self, pattern: str, recursive: bool) -> List[str]:
        """Find files matching the given glob pattern."""
        if self._svc:
            return self._svc.search_files(patterns=pattern, recursive=recursive, roots=self._roots)
        return []

    def _find_matching_file(self, filename: str, include_spec: dict) -> Optional[Path]:
        """Find a file by name based on the include pattern."""
        files = self._find_files_by_pattern(include_spec['pattern'], include_spec.get('recursive', False))
        for f in files:
            if Path(f).name == filename:
                return Path(f)
        return None

    def _load_all(self):
        """
        Parse each todo.md into tasks, capturing optional second‐bracket
        write‐flag and any adjacent ```knowledge``` block.
        """
        self._file_lines.clear()
        self._tasks.clear()
        for fn in self._find_files():
            lines = Path(fn).read_text(encoding='utf-8').splitlines(keepends=True)
            self._file_lines[fn] = lines
            i = 0
            while i < len(lines):
                m = TASK_RE.match(lines[i])
                if not m:
                    i += 1
                    continue

                indent     = m.group(1)
                status     = m.group('status')
                write_flag = m.group('write')  # may be None, ' ', '~', or 'x'
                desc       = m.group('desc').strip()
                task       = {
                    'file': fn,
                    'line_no': i,
                    'indent': indent,
                    'status_char': status,
                    'write_flag': write_flag,
                    'desc': desc,
                    'include': None,
                    'in': None,
                    'out': None,
                    'knowledge': '',
                    '_start_stamp': None,
                    '_know_tokens': 0,
                    '_in_tokens': 0,
                    '_prompt_tokens': 0,
                    '_include_tokens': 0,
                }

                # scan sub‐entries (include, in, focus)
                j = i + 1
                while j < len(lines) and lines[j].startswith(indent + '  '):
                    sub = SUB_RE.match(lines[j])
                    if sub:
                        key = sub.group('key')
                        pat = sub.group('pattern').strip('"').strip('`')
                        rec = bool(sub.group('rec'))
                        if key == 'focus':
                            task['out'] = {'pattern': pat, 'recursive': rec}
                        else:
                            task[key] = {'pattern': pat, 'recursive': rec}
                    j += 1

                # capture ```knowledge``` fence immediately after task
                if j < len(lines) and lines[j].lstrip().startswith('```knowledge'):
                    fence = []
                    j += 1
                    while j < len(lines) and not lines[j].startswith('```'):
                        fence.append(lines[j])
                        j += 1
                    task['knowledge'] = ''.join(fence)
                    j += 1  # skip closing ``` line

                self._tasks.append(task)
                i = j

    def _watch_loop(self):
        # monitor external edits to todo.md
        while True:
            for fn in self._find_files():
                try:
                    mtime = os.path.getmtime(fn)
                except OSError:
                    continue

                # ignore our own writes
                ignore_time = self._watch_ignore.get(fn)
                if ignore_time and abs(mtime - ignore_time) < 0.001:
                    self._watch_ignore.pop(fn, None)
                # new external change?
                elif self._mtimes.get(fn) and mtime > self._mtimes[fn]:
                    logger.debug(f"Detected external change in {fn}, reloading tasks")
                    if not self._svc:
                        continue

                    try:
                        # re-parse all todo.md into self._tasks
                        self._load_all()

                        # 1) tasks to "write": Done + write_flag == To Do
                        write_list = [
                            t for t in self._tasks
                            if STATUS_MAP.get(t['status_char']) == 'Done'
                            and STATUS_MAP.get(t.get('write_flag',' ')) == 'To Do'
                        ]
                        for task in write_list:
                            logger.info(f"Re-emitting output for task: {task['desc']}")
                            self._process_manual_done(self._svc)

                        # 2) tasks still To Do
                        todo_list = [
                            t for t in self._tasks
                            if STATUS_MAP.get(t['status_char']) == 'To Do'
                        ]
                        if todo_list:
                            logger.info("New To Do tasks found, running next")
                            self.run_next_task(self._svc)

                    except Exception as e:
                        logger.error(f"watch loop error: {e}")

                # update stored mtime
                self._mtimes[fn] = mtime

            time.sleep(1)

    def run_next_task(self, svc):
        self._svc = svc
        self._load_all()
        todo = [t for t in self._tasks
                if STATUS_MAP[t['status_char']] == 'To Do']
        if not todo:
            logger.info("No To Do tasks found.")
            return
        ai_out = self._process_one(todo[0], svc, self._file_lines)
        logger.info("Completed one To Do task")
        return ai_out

    def _gather_include_knowledge(self, task: dict, svc) -> str:
        inc = task.get('include') or {}
        spec = inc.get('pattern','')
        if not spec:
            return ""
        rec = " recursive" if inc.get('recursive') else ""
        full_spec = f"pattern={spec}{rec}"
        try:
            know = svc.include(full_spec) or ""
            return know
        except Exception as e:
            logger.error(f"Include failed for spec='{full_spec}': {e}")
            return ""

    def _report_parsed_files(self, parsed_files: List[dict], task: dict = None) -> int:
        for parsed in parsed_files:
            orig_name = Path(parsed['filename']).name
            orig_tokens = parsed.get('tokens', 0)
            new_path = None
            new_tokens = 0
            if task and task.get('include'):
                new_path = self._find_matching_file(orig_name, task['include'])
            try:
                if new_path and new_path.exists():
                    content = self._safe_read_file(new_path)
                    new_tokens = len(content.split())
                change = 0.0
                if orig_tokens:
                    change = abs(new_tokens - orig_tokens) / orig_tokens * 100
                msg = f"Compare: '{orig_name}' -> {new_path} | tokens(orig/new) = {orig_tokens}/{new_tokens} | delta={change:.1f}%"
                if change > 40.0:
                    logger.error(msg + " (delta > 40%)")
                    return -2
                elif change > 20.0:
                    logger.warning(msg + " (delta > 20%)")
                    return -1
                else:
                    logger.info(msg)
            except Exception as e:
                logger.error(f"Error reporting parsed file '{orig_name}': {e}")
        return 0

    def _write_full_ai_output(self, svc, task, ai_out):
        out_pat = task.get('out', {}).get('pattern','')
        if not out_pat:
            return
        out_path = self._resolve_path(out_pat)
        logger.info(f"Write: {out_path} ({len(ai_out.split())} tokens)")
        if out_path:
            self._backup_and_write_output(svc, out_path, ai_out)

    def _process_one(self, task: dict, svc, file_lines_map: dict):
        basedir = Path(task['file']).parent
        self._base_dir = str(basedir)
        logger.info(f"Base dir: {self._base_dir}")
        include_text = self._gather_include_knowledge(task, svc)
        task['_include_tokens'] = len(include_text.split())
        logger.info(f"Include tokens: {task['_include_tokens']}")
        knowledge_text = task.get('knowledge') or ""
        task['_know_tokens'] = len(knowledge_text.split())
        logger.info(f"Knowledge tokens: {task['_know_tokens']}")
        prompt = PromptBuilder.build_task_prompt(task, include_text, "")
        task['_prompt_tokens'] = len(prompt.split())
        logger.info(f"Prompt tokens: {task['_prompt_tokens']}")
        cur_model = svc.get_cur_model()
        TaskManager().start_task(task, file_lines_map, cur_model)

        try:
            ai_out = svc.ask(prompt)
        except Exception as e:
            logger.error(f"LLM call failed: {e}")
            ai_out = ""

        try:
            parsed_files = self.parser.parse_llm_output(ai_out) if ai_out else []
        except Exception as e:
            logger.error(f"Parsing AI output failed: {e}")
            parsed_files = []

        if parsed_files:
            self._report_parsed_files(parsed_files, task)
            self._write_full_ai_output(svc, task, ai_out)
        else:
            logger.info("No parsed files to report.")

        TaskManager().complete_task(task, file_lines_map, cur_model)
        return ai_out

    # ... (remaining helper methods unchanged) ...

__all_classes__ = ["Change","ChangesList","TodoService"]

# original file length: 350 lines
# updated file length: 352 lines