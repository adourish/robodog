#!/usr/bin/env python3
import os
import re
import time
import threading
import logging
import shutil
import sys
from datetime import datetime
from pathlib import Path
from typing import List, Optional

import tiktoken
from pydantic import BaseModel, RootModel

logger = logging.getLogger(__name__)

# regexes for parsing markdown tasks
TASK_RE = re.compile(r'^(\s*)-\s*\[(?P<status>[ x~])\]\s*(?P<desc>.+)$')
SUB_RE  = re.compile(
    r'^\s*-\s*(?P<key>include|focus):\s*'
    r'(?:pattern=|file=)?(?P<pattern>"[^"]+"|`[^`]+`|\S+)'
    r'(?:\s+(?P<rec>recursive))?'
)

STATUS_MAP     = {' ': 'To Do', '~': 'Doing', 'x': 'Done'}
REVERSE_STATUS = {v: k for k, v in STATUS_MAP.items()}

if sys.platform.startswith("win"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except AttributeError:
        import io
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
        sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")


class Change(BaseModel):
    path: str
    start_line: int
    end_line: Optional[int]
    new_content: str


class ChangesList(RootModel[List[Change]]):
    pass


class TodoService:
    FILENAME = 'todo.md'

    def __init__(self, roots: List[str]):
        self._roots        = roots
        self._file_lines   = {}
        self._tasks        = []
        self._mtimes       = {}
        self._watch_ignore = {}
        self._svc          = None

        self._load_all()
        for fn in self._find_files():
            try:
                self._mtimes[fn] = os.path.getmtime(fn)
            except Exception:
                pass

        threading.Thread(target=self._watch_loop, daemon=True).start()

    def _find_files(self) -> List[str]:
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
                    'file': fn,
                    'line_no': i,
                    'indent': indent,
                    'status_char': status,
                    'desc': desc,
                    'include': None,
                    'focus': None,
                    'code': None,
                }

                j = i + 1
                while j < len(lines) and lines[j].startswith(indent + '  '):
                    ms = SUB_RE.match(lines[j])
                    if ms:
                        key = ms.group('key')
                        pat = ms.group('pattern').strip('"').strip('`')
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

    def _watch_loop(self):
        while True:
            for fn in self._find_files():
                try:
                    mtime = os.path.getmtime(fn)
                except Exception:
                    continue

                last   = self._mtimes.get(fn)
                ignore = self._watch_ignore.get(fn)

                if ignore and abs(mtime - ignore) < 0.001:
                    self._watch_ignore.pop(fn, None)
                elif last and mtime > last:
                    logger.info(f"Detected external change in {fn}, running /todo")
                    try:
                        if self._svc:
                            self.run_next_task(self._svc)
                    except Exception as e:
                        logger.error(f"watch loop error: {e}")

                self._mtimes[fn] = mtime

            time.sleep(1)

    @staticmethod
    def _write_file(fn: str, file_lines: List[str]):
        Path(fn).write_text(''.join(file_lines), encoding='utf-8')

    @staticmethod
    def _start_task(task: dict, file_lines_map: dict):
        if STATUS_MAP[task['status_char']] != 'To Do':
            return
        fn, ln = task['file'], task['line_no']
        indent, desc = task['indent'], task['desc']
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
        fn, ln = task['file'], task['line_no']
        indent, desc = task['indent'], task['desc']
        new_char = REVERSE_STATUS['Done']

        file_lines_map[fn][ln] = f"{indent}- [{new_char}] {desc}\n"
        stamp = datetime.utcnow().strftime('%Y-%m-%d %H:%M')
        file_lines_map[fn].insert(ln + 1, f"{indent}  - completed: {stamp}\n")
        TodoService._write_file(fn, file_lines_map[fn])
        task['status_char'] = new_char

    def run_next_task(self, svc):
        self._svc = svc

        self._load_all()
        for t in self._tasks:
            logger.debug(f"Task: {t['desc']}  Status: {STATUS_MAP[t['status_char']]}")

        todo = [t for t in self._tasks if STATUS_MAP[t['status_char']] == 'To Do']
        if not todo:
            logger.info("No To Do tasks found.")
            return
        else:
            logger.info(f"Task: {t['desc']}  Status: {STATUS_MAP[t['status_char']]}")

        self._process_one(todo[0], svc, self._file_lines)
        logger.info("Completed one To Do task")

    def _get_token_count(self, text: str) -> int:
        try:
            return len(text.split())
        except Exception:
            return 0


    def _gather_include_knowledge(self, include: dict, svc) -> str:
        raw = include.get('pattern', '').strip('"').strip('`')
        if raw.startswith('pattern='):
            raw = raw[len('pattern='):]
        spec = f"pattern={raw}" + (" recursive" if include.get('recursive') else "")
        logger.info("Gather include knowledge:" + spec)
        return svc.include(spec) or ""

    def _resolve_path(self, path: str) -> Optional[str]:
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

    def _apply_focus(self, raw_focus: str, ai_out: str, svc):
        real = self._resolve_path(raw_focus) or (
            raw_focus if os.path.isabs(raw_focus) else os.path.join(self._roots[0], raw_focus)
        )
        if not os.path.exists(real):
            os.makedirs(os.path.dirname(real), exist_ok=True)
            Path(real).write_text('', encoding='utf-8')
            logger.info(f"Created new focus file: {real}")

        backup = getattr(svc, 'backup_folder', None)
        if backup and os.path.exists(real):
            os.makedirs(backup, exist_ok=True)
            ts = datetime.utcnow().strftime('%Y%m%d-%H%M%S')
            dest = os.path.join(backup, f"{Path(real).name}-{ts}")
            shutil.copy(real, dest)
            logger.info(f"Backup created: {dest}")

        svc.call_mcp("UPDATE_FILE", {"path": real, "content": ai_out})
        logger.info(f"Updated focus file: {real}")
        try:
            m_after = os.path.getmtime(real)
            self._watch_ignore[real] = m_after
        except OSError:
            pass

    def _process_one(self, task: dict, svc, file_lines_map: dict):
        TodoService._start_task(task, file_lines_map)
        logger.info("-> Starting task: %s", task['desc'])
        code = ""
        if task.get('code'):
            code = "\n" + task['code'] + "\n"

        focus_spec = task.get("focus")
        if isinstance(focus_spec, dict):
            focus_str = focus_spec.get('pattern', '')
        else:
            focus_str = focus_spec or ''

        include = task.get("include") or {}
        raw_focus = ""
        if focus_str.startswith('file='):
            raw_focus = focus_str[len('file='):]

        logger.info("focus:" + focus_str)
        knowledge = self._gather_include_knowledge(include, svc)
        tk = self._get_token_count(knowledge)
        logger.info(f"Include knowledge total tokens: {tk}")

        prompt = (
            "knowledge:\n" + knowledge + "\n\n"
            "task A0: " + task['desc'] + "\n\n"
            "task A1: " + code + "\n\n"
            "task A2: respond with code full-file \n"
            "task A3: tag each code fence with a leading line `# file: <path>`\n"
            "task A4: No diffs, no extra explanation.\n"
        )
        t2 = self._get_token_count(prompt)
        logger.info(f"Prompt token count: {t2}")
        ai_out = svc.ask(prompt)

        if focus_str:
            self._apply_focus(focus_str, ai_out, svc)
        else:
            logger.info("No focus file pattern specified; skipping file update.")

        TodoService._complete_task(task, file_lines_map)
        logger.info(f"Completed task: {task['desc']}")