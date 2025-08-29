# file: robodog/cli/todo.py
```python
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
SUB_RE  = re.compile(
    r'^\s*-\s*(?P<key>include|focus):\s*'
    r'(?:pattern=)?(?P<pattern>\S+)'
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
                    except Exception as e:
                        logger.exception("Error in watcher run_next_task")
            # detect new files
            for fn in self._find_files():
                if fn not in self._mtimes:
                    self._mtimes[fn] = os.path.getmtime(fn)
                    print(f"New todo file {fn}, running /todo")
                    try:
                        self.run_next_task(self._svc)
                    except Exception:
                        logger.exception("Error in watcher run_next_task")

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
        # keep svc for watcher
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

    # existing _process_one and related methods unchanged...
```

# file: robodog/cli/todo.py
```python
# (full content above, watching logic integrated)
```