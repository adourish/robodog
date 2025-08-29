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
                        rec = bool(ms.group('rec'))
                        task[key] = {'pattern': pat, 'recursive': rec}
                    j += 1
                # check for a following code fence
                if j < len(lines) and lines[j].lstrip().startswith('```'):
                    # we've found a fence (``` or ```code)
                    fence_line = lines[j]
                    k = j + 1
                    code_lines = []
                    while k < len(lines) and not lines[k].lstrip().startswith('```'):
                        code_lines.append(lines[k])
                        k += 1
                    task['code'] = ''.join(code_lines).rstrip('\n')
                    # advance j past the closing fence
                    j = k + 1
                # store task and advance
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

        # strip off any "file=" prefix or stray backticks
        raw_focus = focus.get('pattern', '').rstrip('`')
        if raw_focus.startswith('file='):
            raw_focus = raw_focus[len('file='):]
        raw_include = include.get('pattern', '').rstrip('`')
        if raw_include.startswith('pattern='):
            raw_include = raw_include[len('pattern='):]

        focus_str   = f"pattern={raw_focus}"   + (" recursive" if focus.get('recursive') else "")
        include_str = f"pattern={raw_include}" + (" recursive" if include.get('recursive') else "")

        # fetch context via include (drop return)
        _ = svc.include(focus_str)
        include_ans = svc.include(include_str) or ""

        # count tokens for knowledge
        try:
            enc = tiktoken.encoding_for_model(svc.cur_model)
        except Exception:
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

        # get AI output
        ai_out = svc.ask(prompt)

        # now write AI output to the focus file (create/backup/update)
        if raw_focus:
            real_focus = self._resolve_path(raw_focus)
            created = False
            if not real_focus:
                # make a brand‐new focus file
                real_focus = raw_focus if os.path.isabs(raw_focus) \
                              else os.path.join(self._roots[0], raw_focus)
                os.makedirs(os.path.dirname(real_focus), exist_ok=True)
                Path(real_focus).write_text('', encoding='utf-8')
                print(f"Created new focus file: {real_focus}")
                created = True

            # backup if requested
            backup_folder = getattr(svc, 'backup_folder', None)
            if backup_folder and os.path.exists(real_focus):
                os.makedirs(backup_folder, exist_ok=True)
                ts   = datetime.utcnow().strftime('%Y%m%d-%H%M%S')
                base = os.path.basename(real_focus)
                dest = os.path.join(backup_folder, f"{base}-{ts}")
                shutil.copy(real_focus, dest)
                print(f"Backup created: {dest}")

            # push update via MCP
            svc.call_mcp("UPDATE_FILE", {
                "path": real_focus,
                "content": ai_out
            })
            print(f"Updated focus file: {real_focus}")
        else:
            print("No focus file pattern specified; skipping file update.")

        # finally mark task Done
        TodoService._complete_task(task, file_lines_map)
        print(f"✔ Completed task: {task['desc']}")
        
    def _process_oned(self, task: dict, svc, file_lines_map: dict):
        # mark Doing
        TodoService._start_task(task, file_lines_map)
        print(f"→ Starting task: {task['desc']}")

        # clear context and knowledge at the start of each task
        svc.context = ""
        svc.knowledge = ""

        # inject any code‐block from the todo.md into knowledge
        code_block = task.get('code')
        if code_block:
            svc.knowledge += "\n" + code_block + "\n"

        # prepare include/focus directives
        focus = task.get("focus") or {}
        include = task.get("include") or {}
        focus_str = f"pattern={focus.get('pattern','')}" + (" recursive" if focus.get('recursive') else "")
        include_str = f"pattern={include.get('pattern','')}" + (" recursive" if include.get('recursive') else "")

        # fetch context via include (ensure we get a string back)
        _ = svc.include(focus_str)  # focus may be used inside AI prompt
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

        # get AI output
        ai_out = svc.ask(prompt)

        # write AI output directly to the focus file, but first make sure it exists
        pattern = focus.get('pattern')
        if pattern:
            real_focus = self._resolve_path(pattern)
            created = False
            if not real_focus:
                # create new focus file under the first root
                if os.path.isabs(pattern):
                    real_focus = pattern
                else:
                    real_focus = os.path.join(self._roots[0], pattern)
                os.makedirs(os.path.dirname(real_focus), exist_ok=True)
                # create empty file
                Path(real_focus).write_text('', encoding='utf-8')
                print(f"Created new focus file: {real_focus}")
                created = True

            # backup existing file (or newly created empty file) if backup_folder is set
            backup_folder = getattr(svc, 'backup_folder', None)
            if backup_folder and os.path.exists(real_focus):
                os.makedirs(backup_folder, exist_ok=True)
                ts = datetime.utcnow().strftime('%Y%m%d-%H%M%S')
                base = os.path.basename(real_focus)
                backup_name = f"{base}-{ts}"
                dest = os.path.join(backup_folder, backup_name)
                shutil.copy(real_focus, dest)
                print(f"Backup created: {dest}")

            # now update via MCP
            svc.call_mcp("UPDATE_FILE", {
                "path": real_focus,
                "content": ai_out
            })
            print(f"Updated focus file: {real_focus}")
        else:
            print("No focus file pattern specified; skipping file update.")

        # finally mark task Done
        TodoService._complete_task(task, file_lines_map)
        print(f"✔ Completed task: {task['desc']}")

    def _process_onec(self, task: dict, svc, file_lines_map: dict):
        # mark Doing
        TodoService._start_task(task, file_lines_map)
        print(f"→ Starting task: {task['desc']}")

        # clear context and knowledge at the start of each task
        svc.context = ""
        svc.knowledge = ""

        # inject any code‐block from the todo.md into knowledge
        code_block = task.get('code')
        if code_block:
            svc.knowledge += "\n" + code_block + "\n"

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

        # get AI output
        ai_out = svc.ask(prompt)

        # write AI output directly to the focus file, but first make a dated backup
        pattern = focus.get('pattern')
        if pattern:
            real_focus = self._resolve_path(pattern)
            if real_focus:
                backup_folder = getattr(svc, 'backup_folder', None)
                if backup_folder:
                    os.makedirs(backup_folder, exist_ok=True)
                    ts = datetime.utcnow().strftime('%Y%m%d-%H%M%S')
                    base = os.path.basename(real_focus)
                    backup_name = f"{base}-{ts}"
                    dest = os.path.join(backup_folder, backup_name)
                    shutil.copy(real_focus, dest)
                    print(f"Backup created: {dest}")
                svc.call_mcp("UPDATE_FILE", {
                    "path": real_focus,
                    "content": ai_out
                })
                print(f"Updated focus file: {real_focus}")
            else:
                print(f"Focus file not found for pattern: {pattern}")
        else:
            print("No focus file pattern specified; skipping file update.")

        # finally mark task Done
        TodoService._complete_task(task, file_lines_map)
        print(f"✔ Completed task: {task['desc']}")


        # mark Doing
        TodoService._start_task(task, file_lines_map)
        print(f"→ Starting task: {task['desc']}")

        # clear context and knowledge at the start of each task
        svc.context = ""
        svc.knowledge = ""

        # inject any code‐block from the todo.md into knowledge
        code_block = task.get('code')
        if code_block:
            svc.knowledge += "\n" + code_block + "\n"

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

        # get AI output
        ai_out = svc.ask(prompt)

        # write AI output directly to the focus file
        pattern = focus.get('pattern')
        if pattern:
            real_focus = self._resolve_path(pattern)
            if real_focus:
                svc.call_mcp("UPDATE_FILE", {
                    "path": real_focus,
                    "content": ai_out
                })
                print(f"Updated focus file: {real_focus}")
            else:
                print(f"Focus file not found for pattern: {pattern}")
        else:
            print("No focus file pattern specified; skipping file update.")

        # finally mark task Done
        TodoService._complete_task(task, file_lines_map)
        print(f"✔ Completed task: {task['desc']}")