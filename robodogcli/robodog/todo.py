#!/usr/bin/env python3
import os
import re
import json
import logging
from datetime import datetime
from pathlib import Path
from typing import List, Optional

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
    end_line: Optional[int]  # None means full overwrite
    new_content: str


class ChangesList(RootModel[List[Change]]):
    pass


class TodoService:
    FILENAME = 'todo.md'

    def __init__(self, roots):
        self._roots       = roots
        self._file_lines  = {}   # file → list[str]
        self._tasks       = []   # list[dict]
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
                    'focus':       None
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
                self._tasks.append(task)
                i = j

    @staticmethod
    def _write_file(fn: str, file_lines: List[str]):
        Path(fn).write_text(''.join(file_lines), encoding='utf-8')

    @staticmethod
    def _start_task(task: dict, file_lines_map: dict):
        if STATUS_MAP[task['status_char']] != 'To Do':
            return
        fn = task['file']; ln = task['line_no']
        indent = task['indent']; desc = task['desc']
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
        fn = task['file']; ln = task['line_no']
        indent = task['indent']; desc = task['desc']
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

    def _apply_change(self, svc, change: Change):
        real = self._resolve_path(change.path)
        if not real:
            raise FileNotFoundError(f"Cannot find file: {change.path}")
        svc.call_mcp("UPDATE_FILE", {
            "path": real,
            "content": change.new_content
        })
        print(f"Replaced entire file: {real}")

    @staticmethod
    def parse_llm_output(text: str) -> List[Change]:
        changes: List[Change] = []
        fence_re = re.compile(r'```(?:[\w+-]*)\n([\s\S]*?)```')
        for block in fence_re.findall(text):
            lines = block.splitlines()
            if not lines:
                continue
            first = lines[0].strip().lower()
            if first.startswith('# file:'):
                path = lines[0].split(':', 1)[1].strip()
                content = "\n".join(lines[1:]).rstrip('\n') + '\n'
                changes.append(Change(
                    path=path,
                    start_line=1,
                    end_line=None,
                    new_content=content
                ))
        return changes

    def run_next_task(self, svc):
        # 1) reload tasks and file‐buffer
        self._load_all()
        _tasks      = self._tasks
        _file_lines = self._file_lines

        # 2) log every task
        for t in _tasks:
            status = STATUS_MAP[t['status_char']]
            print(f"Task: {t['desc']}  Status: {status}")

        # 3) collect all To Do tasks
        todo_tasks = [t for t in _tasks if STATUS_MAP[t['status_char']] == 'To Do']
        if not todo_tasks:
            print("No To Do tasks found.")
            return

        # 4) process each one, passing the file_lines_map
        for task in todo_tasks:
            self._process_one(task, svc, _file_lines)

        print("✔ All To Do tasks processed.")

    def _process_one(self, task: dict, svc, file_lines_map: dict):
        # mark Doing
        TodoService._start_task(task, file_lines_map)
        print(f"→ Starting task: {task['desc']}")

        # clear context and knowledge at the start of each task
        svc.context = ""
        svc.knowledge = ""

        # prepare include/focus directives
        focus = task.get("focus") or {}
        include = task.get("include") or {}
        focus_str = f"pattern={focus.get('pattern','')}" + (" recursive" if focus.get('recursive') else "")
        include_str = f"pattern={include.get('pattern','')}" + (" recursive" if include.get('recursive') else "")

        # fetch context via include (ensure we get a string back)
        focus_ans = svc.include(focus_str) or ""
        include_ans = svc.include(include_str) or ""

        # token‐count the knowledge
        try:
            enc = tiktoken.encoding_for_model(svc.cur_model)
        except Exception:
            enc = tiktoken.get_encoding("gpt2")
        knowledge_tokens = len(enc.encode(include_ans))
        print(f"Knowledge length: {knowledge_tokens} tokens")

        # build the prompt
        prompt = (
            "knowledge:\n" + include_ans + "\n\n"
            "task A1: " + task['desc'] + "\n\n"
            "task A2: respond with full-file code fences tagged by a leading\n"
            "task A3: tag each code fence with a leading line `# file: <path>`\n"
            "task A4: No diffs, no extra explanation.\n"
        )

        # token count for the prompt
        try:
            enc = tiktoken.encoding_for_model(svc.cur_model)
        except Exception:
            enc = tiktoken.get_encoding("gpt2")
        prompt_tokens = len(enc.encode(prompt))
        print(f"Prompt token count: {prompt_tokens}")
        ai_out = svc.ask(prompt)
        self._apply_change(svc, ai_out)
        TodoService._complete_task(task, file_lines_map)
        print(f"✔ Completed task: {task['desc']}")