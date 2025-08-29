```python
# file: robodog/cli/todo.py
#!/usr/bin/env python3
import os
import re
import json
import logging
from datetime import datetime
from pathlib import Path
from typing import List, Optional
import shutil
import tiktoken   # ← for token counting
from pydantic import BaseModel, RootModel

logger = logging.getLogger(__name__)

TASK_RE = re.compile(r'^(\s*)-\s*\[(?P<status>[ x~])\]\s*(?P<desc>.+)$')
# Allow quoted paths (with spaces) or unquoted tokens
SUB_RE  = re.compile(
    r'^\s*-\s*(?P<key>include|focus):\s*'
    r'(?:pattern=)?(?P<pattern>"[^"]+"|\S+)'
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

    def __init__(self, roots):
        self._roots       = roots
        self._file_lines  = {}
        self._tasks       = []
        self._load_all()

    def _find_files(self):
        out = []
        for r in self._roots:
            for dp, _, fns in os.walk(r):
                if self.FILENAME in fns:
                    out.append(os.path.join(dp, self.FILENAME))
        return out

    def _load_all(self):
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
                indent = m.group(1)
                status = m.group('status')
                desc   = m.group('desc').strip()
                task = {
                    'file':        fn,
                    'line_no':     i,
                    'indent':      indent,
                    'status_char': status,
                    'desc':        desc,
                    'include':     None,
                    'focus':       None,
                    'code':        None,
                }
                j = i + 1
                while j < len(lines) and lines[j].startswith(indent + '  '):
                    ms = SUB_RE.match(lines[j])
                    if ms:
                        key = ms.group('key')
                        pat = ms.group('pattern')
                        rec = bool(ms.group('rec'))
                        task[key] = {'pattern': pat, 'recursive': rec}
                    j += 1
                if j < len(lines) and lines[j].lstrip().startswith('```'):
                    k = j + 1
                    code_lines = []
                    while k < len(lines) and not lines[k].lstrip().startswith('```'):
                        code_lines.append(lines[k])
                        k += 1
                    task['code'] = ''.join(code_lines).rstrip('\n')
                    j = k + 1
                self._tasks.append(task)
                i = j

    @staticmethod
    def _write_file(fn: str, file_lines: List[str]):
        Path(fn).write_text(''.join(file_lines), encoding='utf-8')

    @staticmethod
    def _start_task(task: dict, file_lines_map: dict):
        if STATUS_MAP[task['status_char']] != 'To Do':
            return
        fn, ln, indent, desc = task['file'], task['line_no'], task['indent'], task['desc']
        new_char = REVERSE_STATUS['Doing']
        file_lines_map[fn][ln] = f"{indent}- [{new_char}] {desc}\n"
        stamp = datetime.utcnow().strftime('%Y-%m-%d %H:%M')
        file_lines_map[fn].insert(ln + 1, f"{indent}  - started: {stamp}\n")
        TodoService._write_file(fn, file_lines_map[fn])
        task['status_char'] = new_char

    @staticmethod
    def _complete_task(task: dict, file_lines_map: dict):
        if STATUS_MAP[task['status_char']] != 'Doing':
            return
        fn, ln, indent, desc = task['file'], task['line_no'], task['indent'], task['desc']
        new_char = REVERSE_STATUS['Done']
        file_lines_map[fn][ln] = f"{indent}- [{new_char}] {desc}\n"
        stamp = datetime.utcnow().strftime('%Y-%m-%d %H:%M')
        file_lines_map[fn].insert(ln + 1, f"{indent}  - completed: {stamp}\n")
        TodoService._write_file(fn, file_lines_map[fn])
        task['status_char'] = new_char

    def _resolve_path(self, path: str) -> Optional[str]:
        if os.path.isabs(path) and os.path.isfile(path):
            return path
        for root in self._roots:
            cand = os.path.join(root, path)
            if os.path.isfile(cand):
                return cand
        base = os.path.basename(path)
        for root in self._roots:
            for dp, _, fns in os.walk(root):
                if base in fns:
                    return os.path.join(dp, base)
        return None

    def run_next_task(self, svc):
        self._svc = svc
        self._load_all()
        for t in self._tasks:
            status = STATUS_MAP[t['status_char']]
            print(f"Task: {t['desc']}  Status: {status}")
        todo_tasks = [t for t in self._tasks if STATUS_MAP[t['status_char']] == 'To Do']
        if not todo_tasks:
            print("No To Do tasks found.")
            return
        for task in todo_tasks:
            self._process_one(task, svc, self._file_lines)
        print("✔ All To Do tasks processed.")

    def _process_one(self, task: dict, svc, file_lines_map: dict):
        # start
        TodoService._start_task(task, file_lines_map)
        print(f"→ Starting task: {task['desc']}")
        svc.context = ""
        svc.knowledge = ""
        code_block = task.get('code')
        if code_block:
            svc.knowledge += "\n" + code_block + "\n"

        focus = task.get("focus") or {}
        include = task.get("include") or {}

        # handle quoted focus paths with spaces
        raw_focus = focus.get('pattern', '').strip('"').rstrip('`')
        if raw_focus.startswith('file='):
            raw_focus = raw_focus[len('file='):]

        raw_include = include.get('pattern', '').rstrip('`')
        if raw_include.startswith('pattern='):
            raw_include = raw_include[len('pattern='):]

        include_ans = svc.include(f"pattern={raw_include}" + (" recursive" if include.get('recursive') else "")) or ""
        try:
            enc = tiktoken.encoding_for_model(svc.cur_model)
        except Exception:
            enc = tiktoken.get_encoding("gpt2")
        print(f"Knowledge length: {len(enc.encode(include_ans))} tokens")

        prompt = (
            "knowledge:\n" + include_ans + "\n\n"
            "task A1: " + task['desc'] + "\n\n"
            "task A2: respond with full-file code fences tagged by a leading\n"
            "task A3: tag each code fence with a leading line `# file: <path>`\n"
            "task A4: No diffs, no extra explanation.\n"
        )
        print(f"Prompt token count: {len(enc.encode(prompt))}")
        ai_out = svc.ask(prompt)

        if raw_focus:
            real_focus = self._resolve_path(raw_focus)
            if real_focus is None:
                real_focus = raw_focus if os.path.isabs(raw_focus) else os.path.join(self._roots[0], raw_focus)
                os.makedirs(os.path.dirname(real_focus), exist_ok=True)
                Path(real_focus).write_text('', encoding='utf-8')
                print(f"Created new focus file: {real_focus}")

            backup_folder = getattr(svc, 'backup_folder', None)
            if backup_folder and os.path.exists(real_focus):
                os.makedirs(backup_folder, exist_ok=True)
                ts = datetime.utcnow().strftime('%Y%m%d-%H%M%S')
                base = os.path.basename(real_focus)
                dest = os.path.join(backup_folder, f"{base}-{ts}")
                shutil.copy(real_focus, dest)
                print(f"Backup created: {dest}")

            svc.call_mcp("UPDATE_FILE", {"path": real_focus, "content": ai_out})
            print(f"Updated focus file: {real_focus}")
        else:
            print("No focus file pattern specified; skipping update.")

        TodoService._complete_task(task, file_lines_map)
        print(f"✔ Completed task: {task['desc']}")
```

# file: robodog/cli/todo.py
#!/usr/bin/env python3
import os
import re
import json
import logging
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import List, Optional
import shutil
import tiktoken   # ← for token counting
from pydantic import BaseModel, RootModel

logger = logging.getLogger(__name__)

TASK_RE = re.compile(r'^(\s*)-\s*\[(?P<status>[ x~])\]\s*(?P<desc>.+)$')
# Allow quoted paths (with spaces) or unquoted tokens
SUB_RE  = re.compile(
    r'^\s*-\s*(?P<key>include|focus):\s*'
    r'(?:pattern=)?(?P<pattern>"[^"]+"|\S+)'
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
    POLL_INTERVAL = 1.0

    def __init__(self, roots):
        self._roots       = roots
        self._file_lines  = {}
        self._tasks       = []
        self._mtimes      = {}
        self._load_all()
        self._start_watcher()

    def _find_files(self):
        out = []
        for r in self._roots:
            for dp, _, fns in os.walk(r):
                if self.FILENAME in fns:
                    out.append(os.path.join(dp, self.FILENAME))
        return out

    def _load_all(self):
        self._file_lines.clear()
        self._tasks.clear()
        for fn in self._find_files():
            lines = Path(fn).read_text(encoding='utf-8').splitlines(keepends=True)
            self._file_lines[fn] = lines
            self._mtimes[fn] = os.path.getmtime(fn)
            i = 0
            while i < len(lines):
                m = TASK_RE.match(lines[i])
                if not m:
                    i += 1
                    continue
                indent = m.group(1)
                status = m.group('status')
                desc   = m.group('desc').strip()
                task = {
                    'file':        fn,
                    'line_no':     i,
                    'indent':      indent,
                    'status_char': status,
                    'desc':        desc,
                    'include':     None,
                    'focus':       None,
                    'code':        None,
                }
                j = i + 1
                while j < len(lines) and lines[j].startswith(indent + '  '):
                    ms = SUB_RE.match(lines[j])
                    if ms:
                        key = ms.group('key')
                        pat = ms.group('pattern').strip('"')
                        rec = bool(ms.group('rec'))
                        task[key] = {'pattern': pat, 'recursive': rec}
                    j += 1
                if j < len(lines) and lines[j].lstrip().startswith('```'):
                    k = j + 1
                    code_lines = []
                    while k < len(lines) and not lines[k].lstrip().startswith('```'):
                        code_lines.append(lines[k])
                        k += 1
                    task['code'] = ''.join(code_lines).rstrip('\n')
                    j = k + 1
                self._tasks.append(task)
                i = j

    @staticmethod
    def _write_file(fn: str, file_lines: List[str]):
        Path(fn).write_text(''.join(file_lines), encoding='utf-8')

    @staticmethod
    def _start_task(task: dict, file_lines_map: dict):
        if STATUS_MAP[task['status_char']] != 'To Do':
            return
        fn, ln, indent, desc = task['file'], task['line_no'], task['indent'], task['desc']
        new_char = REVERSE_STATUS['Doing']
        file_lines_map[fn][ln] = f"{indent}- [{new_char}] {desc}\n"
        stamp = datetime.utcnow().strftime('%Y-%m-%d %H:%M')
        file_lines_map[fn].insert(ln + 1, f"{indent}  - started: {stamp}\n")
        TodoService._write_file(fn, file_lines_map[fn])
        task['status_char'] = new_char

    @staticmethod
    def _complete_task(task: dict, file_lines_map: dict):
        if STATUS_MAP[task['status_char']] != 'Doing':
            return
        fn, ln, indent, desc = task['file'], task['line_no'], task['indent'], task['desc']
        new_char = REVERSE_STATUS['Done']
        file_lines_map[fn][ln] = f"{indent}- [{new_char}] {desc}\n"
        stamp = datetime.utcnow().strftime('%Y-%m-%d %H:%M')
        file_lines_map[fn].insert(ln + 1, f"{indent}  - completed: {stamp}\n")
        TodoService._write_file(fn, file_lines_map[fn])
        task['status_char'] = new_char

    def _resolve_path(self, path: str) -> Optional[str]:
        # strip surrounding quotes so that Windows paths with spaces work
        path = path.strip('"')
        if os.path.isabs(path) and os.path.isfile(path):
            return path
        for root in self._roots:
            cand = os.path.join(root, path)
            if os.path.isfile(cand):
                return cand
        base = os.path.basename(path)
        for root in self._roots:
            for dp, _, fns in os.walk(root):
                if base in fns:
                    return os.path.join(dp, base)
        return None

    def _start_watcher(self):
        t = threading.Thread(target=self._watch_loop, daemon=True)
        t.start()

    def _watch_loop(self):
        while True:
            time.sleep(self.POLL_INTERVAL)
            for fn, last in list(self._mtimes.items()):
                try:
                    m = os.path.getmtime(fn)
                except FileNotFoundError:
                    continue
                if m != last:
                    self._mtimes[fn] = m
                    print(f"Detected change in {fn}, running /todo")
                    try:
                        self.run_next_task(self._svc)
                    except Exception:
                        logger.exception("Error in watcher run_next_task")
            for fn in self._find_files():
                if fn not in self._mtimes:
                    self._mtimes[fn] = os.path.getmtime(fn)
                    print(f"New todo file {fn}, running /todo")
                    try:
                        self.run_next_task(self._svc)
                    except Exception:
                        logger.exception("Error in watcher run_next_task")

    def run_next_task(self, svc):
        self._svc = svc
        self._load_all()
        for t in self._tasks:
            status = STATUS_MAP[t['status_char']]
            print(f"Task: {t['desc']}  Status: {status}")
        todo_tasks = [t for t in self._tasks if STATUS_MAP[t['status_char']] == 'To Do']
        if not todo_tasks:
            print("No To Do tasks found.")
            return
        for task in todo_tasks:
            self._process_one(task, svc, self._file_lines)
        print("✔ All To Do tasks processed.")

    def _process_one(self, task: dict, svc, file_lines_map: dict):
        # mark Doing
        TodoService._start_task(task, file_lines_map)
        print(f"→ Starting task: {task['desc']}")

        # clear context and knowledge
        svc.context = ""
        svc.knowledge = ""

        # inject code‐block if any
        code_block = task.get('code')
        if code_block:
            svc.knowledge += "\n" + code_block + "\n"

        # prepare and clean include/focus directives
        focus = task.get("focus") or {}
        include = task.get("include") or {}

        # strip off quotes so spaces in path are handled
        raw_focus = focus.get('pattern', '').strip('"')
        if raw_focus.startswith('file='):
            raw_focus = raw_focus[len('file='):]

        raw_include = include.get('pattern', '')

        # fetch knowledge
        include_ans = svc.include(f"pattern={raw_include}" + (" recursive" if include.get('recursive') else "")) or ""
        try:
            enc = tiktoken.encoding_for_model(svc.cur_model)
        except:
            enc = tiktoken.get_encoding("gpt2")
        print(f"Knowledge length: {len(enc.encode(include_ans))} tokens")

        # build prompt
        prompt = (
            "knowledge:\n" + include_ans + "\n\n"
            "task A1: " + task['desc'] + "\n\n"
            "task A2: respond with full-file code fences tagged by a leading\n"
            "task A3: tag each code fence with a leading line `# file: <path>`\n"
            "task A4: No diffs, no extra explanation.\n"
        )
        print(f"Prompt token count: {len(enc.encode(prompt))}")

        ai_out = svc.ask(prompt)

        # write to focus file
        if raw_focus:
            real_focus = self._resolve_path(raw_focus)
            if not real_focus:
                real_focus = raw_focus if os.path.isabs(raw_focus) else os.path.join(self._roots[0], raw_focus)
                os.makedirs(os.path.dirname(real_focus), exist_ok=True)
                Path(real_focus).write_text('', encoding='utf-8')
                print(f"Created new focus file: {real_focus}")

            backup_folder = getattr(svc, 'backup_folder', None)
            if backup_folder and os.path.exists(real_focus):
                os.makedirs(backup_folder, exist_ok=True)
                ts = datetime.utcnow().strftime('%Y%m%d-%H%M%S')
                base = os.path.basename(real_focus)
                dst = os.path.join(backup_folder, f"{base}-{ts}")
                shutil.copy(real_focus, dst)
                print(f"Backup created: {dst}")

            svc.call_mcp("UPDATE_FILE", {"path": real_focus, "content": ai_out})
            print(f"Updated focus file: {real_focus}")
        else:
            print("No focus file specified; skipping.")

        # complete
        TodoService._complete_task(task, file_lines_map)
        print(f"✔ Completed task: {task['desc']}")
```

```python
# file: robodog/cli/mcphandler.py
#!/usr/bin/env python3
import os
import json
import threading
import socketserver
import fnmatch
import hashlib
import shutil
from service import RobodogService
import logging

logger = logging.getLogger('robodog.mcphandler')
ROOTS   = []
TOKEN   = None
SERVICE = None

class MCPHandler(socketserver.StreamRequestHandler):
    def _dispatch(self, op, p):
        try:
            if op == 'READ_FILE':
                raw_path = p.get("path")
                if not raw_path:
                    raise ValueError("Missing 'path'")
                path = raw_path.strip('"')
                content = SERVICE.read_file(path)
                return {"status":"ok","path":path,"content":content}

            if op == 'UPDATE_FILE':
                raw_path = p.get("path")
                if not raw_path:
                    raise ValueError("Missing 'path'")
                path = raw_path.strip('"')
                content = p.get("content", "")
                if not os.path.exists(path):
                    os.makedirs(os.path.dirname(path), exist_ok=True)
                    SERVICE.create_file(path, content)
                else:
                    SERVICE.update_file(path, content)
                return {"status":"ok","path":path}

            # ... other ops unchanged ...

        except Exception as e:
            return {"status":"error","error":str(e)}

class ThreadedTCPServer(socketserver.ThreadingMixIn, socketserver.TCPServer):
    daemon_threads      = True
    allow_reuse_address = True

def run_robodogmcp(host: str, port: int, token: str,
                   folders: list, svc: RobodogService):
    global TOKEN, ROOTS, SERVICE
    TOKEN   = token
    SERVICE = svc
    ROOTS   = [os.path.abspath(f) for f in folders]
    server  = ThreadedTCPServer((host, port), MCPHandler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server
```

```python
# file: robodog/__init__.py
__version__ = "2.6.11"
```