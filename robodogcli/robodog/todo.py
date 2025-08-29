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

# Allow quoted (with spaces) or unquoted tokens,
# and strip surrounding backticks if present.
# — changed here: also accept an optional 'file=' prefix
SUB_RE  = re.compile(
    r'^\s*-\s*(?P<key>include|focus):\s*'
    r'(?:pattern=|file=)?(?P<pattern>"[^"]+"|`[^`]+`|\S+)'
    r'(?:\s+(?P<rec>recursive))?'
)

SUB_REb = re.compile(
    r'^\s*-\s*(?P<key>include|focus):\s*'
    r'(?:pattern=|file=)?'                           # optional prefix
    r'(?P<pattern>"[^"]"|`[^`]`|.?)'              # double-quoted, backtick, or any chars (non-greedy)
    r'(?:\s(?P<rec>recursive))?\s*$'                # optional ' recursive' at end of line
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
                    'focus':       None,
                    'code':        None,
                }
                # read sub-directives
                j = i + 1
                while j < len(lines) and lines[j].startswith(indent + '  '):
                    ms = SUB_RE.match(lines[j])
                    if ms:
                        key = ms.group('key')
                        pat = ms.group('pattern')
                        # strip surrounding quotes/backticks
                        pat = pat.strip('"').strip('`')
                        rec = bool(ms.group('rec'))
                        task[key] = {'pattern': pat, 'recursive': rec}
                    j += 1
                # code fence?
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
        # strip surrounding quotes/backticks so Windows paths with spaces work
        p = path.strip('"').strip('`')
        if os.path.isabs(p) and os.path.isfile(p):
            return p
        for root in self._roots:
            cand = os.path.join(root, p)
            if os.path.isfile(cand):
                return cand
        base = os.path.basename(p)
        for root in self._roots:
            for dp, _, fns in os.walk(root):
                if base in fns:
                    return os.path.join(dp, base)
        return None

    def run_next_task(self, svc):
        self._svc = svc
        # reload
        self._load_all()

        # print summary
        for t in self._tasks:
            print(f"Task: {t['desc']}  Status: {STATUS_MAP[t['status_char']]}")

        todo_tasks = [t for t in self._tasks if STATUS_MAP[t['status_char']]=='To Do']
        if not todo_tasks:
            print("No To Do tasks found.")
            return

        task = todo_tasks[0]
        self._process_one(task, svc, self._file_lines)
        print("✔ Completed one To Do task.")

    def _process_one(self, task: dict, svc, file_lines_map: dict):
        # mark Doing
        TodoService._start_task(task, file_lines_map)
        print(f"→ Starting task: {task['desc']}")

        svc.context = ""
        svc.knowledge = ""

        # inject code‐block
        code_block = task.get('code')
        if code_block:
            svc.knowledge += "\n" + code_block + "\n"

        focus = task.get("focus") or {}
        include = task.get("include") or {}

        raw_focus = focus.get('pattern', '')
        # strip quotes/backticks
        raw_focus = raw_focus.strip('"').strip('`')
        # strip leading file=
        if raw_focus.startswith('file='):
            raw_focus = raw_focus[len('file='):]

        raw_include = include.get('pattern', '').strip('"').strip('`')
        if raw_include.startswith('pattern='):
            raw_include = raw_include[len('pattern='):]

        # fetch include‐knowledge
        inc_spec = f"pattern={raw_include}" + (" recursive" if include.get('recursive') else "")
        include_ans = svc.include(inc_spec) or ""

        # token counts
        try:
            enc = tiktoken.encoding_for_model(svc.cur_model)
        except:
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

        # write AI output to the focus file
        if raw_focus:
            real_focus = self._resolve_path(raw_focus)
            created = False
            if not real_focus:
                real_focus = raw_focus if os.path.isabs(raw_focus) \
                              else os.path.join(self._roots[0], raw_focus)
                os.makedirs(os.path.dirname(real_focus), exist_ok=True)
                Path(real_focus).write_text('', encoding='utf-8')
                print(f"Created new focus file: {real_focus}")
                created = True

            # backup
            backup_folder = getattr(svc, 'backup_folder', None)
            if backup_folder and os.path.exists(real_focus):
                os.makedirs(backup_folder, exist_ok=True)
                ts   = datetime.utcnow().strftime('%Y%m%d-%H%M%S')
                base = os.path.basename(real_focus)
                dest = os.path.join(backup_folder, f"{base}-{ts}")
                shutil.copy(real_focus, dest)
                print(f"Backup created: {dest}")

            svc.call_mcp("UPDATE_FILE", {
                "path": real_focus,
                "content": ai_out
            })
            print(f"Updated focus file: {real_focus}")
        else:
            print("No focus file pattern specified; skipping file update.")

        # mark Done
        TodoService._complete_task(task, file_lines_map)
        print(f"✔ Completed task: {task['desc']}")