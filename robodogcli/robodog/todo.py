# file: robodog/cli/todo.py
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

from parse_service import ParseService  # Added import for ParseService

logger = logging.getLogger(__name__)

# Updated TASK_RE to capture optional second-bracket 'write' flag
TASK_RE = re.compile(
    r'^(\s*)-\s*'                  # indent + "- "
    r'\[(?P<status>[ x~])\]'       # first [status]
    r'(?:\[(?P<write>[ x~-])\])?'  # optional [write_flag]
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

    def __init__(self, roots: List[str]):
        self._roots        = roots
        self._file_lines   = {}
        self._tasks        = []
        self._mtimes       = {}
        self._watch_ignore = {}
        self._svc          = None
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
        # ... unchanged ...
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
        # ... unchanged ...
        out = []
        for r in self._roots:
            for dp, _, fns in os.walk(r):
                if self.FILENAME in fns:
                    out.append(os.path.join(dp, self.FILENAME))
        return out

    def _load_all(self):
        """
        Parse each todo.md into tasks, capturing optional second-bracket
        write-flag and any adjacent ```knowledge``` block.
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
                write_flag = m.group('write')  # may be None, ' ', '-', or 'x'
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

                # scan sub-entries (include, in, focus)
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
                except:
                    continue
                ignore = self._watch_ignore.get(fn)
                if ignore and abs(mtime - ignore) < 0.001:
                    self._watch_ignore.pop(fn, None)
                elif self._mtimes.get(fn) and mtime > self._mtimes[fn]:
                    logger.info(f"Detected external change in {fn}, processing manual tasks")
                    if self._svc:
                        try:
                            self._process_manual_done(self._svc)
                        except Exception as e:
                            logger.error(f"watch loop error: {e}")
                self._mtimes[fn] = mtime
            time.sleep(1)

    def _process_manual_done(self, svc):
        """
        When a task is manually marked Done:
        - with write_flag '-', re-emit existing output to trigger downstream watches
        - with any other write_flag, treat as a full re-run: reset to To Do, reprocess, and mark Done
        """
        self._load_all()
        for task in self._tasks:
            key = (task['file'], task['line_no'])
            # Completed with write_flag '-', re-emit existing out-file
            if STATUS_MAP[task['status_char']] == 'Done' and task.get('write_flag') == ' ' and key not in self._processed:
                out_pat = task.get('out', {}).get('pattern','')
                if out_pat:
                    out_path = self._resolve_path(out_pat)
                    logger.info(f"Manual commit of task: {task['desc']}")
                    if out_path and out_path.exists():
                        logger.info(f"Manual read of out: {out_path}")
                        content = self._safe_read_file(out_path)
                        # 1. update the status to [x][~]
                        #    toggle write_flag to '~' (Doing) then to 'x' (Done)
                        lines = self._file_lines[task['file']]
                        ln = task['line_no']
                        indent = task['indent']
                        desc = task['desc']
                        # mark Doing
                        lines[ln] = f"{indent}- [{REVERSE_STATUS['Doing']}] {desc}\n"
                        # update summary line timestamp
                        TodoService._write_file(task['file'], lines)
                        logger.debug(f"Updated task line {ln} to Doing")
                        # then mark Done
                        lines[ln] = f"{indent}- [{REVERSE_STATUS['Done']}] {desc}\n"
                        TodoService._write_file(task['file'], lines)
                        logger.debug(f"Updated task line {ln} to Done")
                        # 2. parse the output file using parse_service
                        parsed = self.parser.parse_llm_output(content)
                        for obj in parsed:
                            fname = obj['filename']
                            fcontent = obj['content']
                            # 3. do a search through the search pattern files and update matches
                            matches = svc.search_files(patterns=fname, recursive=True, roots=self._roots)
                            for path in matches:
                                logger.info(f"Updating matched file {path} with parsed content")
                                try:
                                    svc.call_mcp("UPDATE_FILE", {"path": path, "content": fcontent})
                                    self._watch_ignore[str(path)] = Path(path).stat().st_mtime
                                except Exception as e:
                                    logger.error(f"Failed to update {path}: {e}")
                self._processed.add(key)

            # Completed without '-', treat as manual trigger: re-run the AI process
            elif STATUS_MAP[task['status_char']] == 'Done' and task.get('write_flag') != '-' and key not in self._processed:
                logger.info(f"Manual re-trigger of task: {task['desc']}")
                # Reset to To Do so that _process_one will start/complete it
                task['status_char'] = REVERSE_STATUS['To Do']
                # Clear any previous stamps/counters
                task['_start_stamp'] = None
                task['_know_tokens'] = 0
                task['_in_tokens'] = 0
                task['_prompt_tokens'] = 0
                task['_include_tokens'] = 0
                # Run full AI processing
                self._process_one(task, svc, self._file_lines)
                self._processed.add(key)

    @staticmethod
    def _write_file(fn: str, file_lines: List[str]):
        Path(fn).write_text(''.join(file_lines), encoding='utf-8')

    @staticmethod
    def _format_summary(indent: str, start: str, end: Optional[str]=None,
                        know: Optional[int]=None, prompt: Optional[int]=None,
                        incount: Optional[int]=None, include: Optional[int]=None,
                        cur_model: str=None) -> str:
        parts = [f"started: {start}"]
        if end:
            parts.append(f"completed: {end}")
        if know is not None:
            parts.append(f"knowledge_tokens: {know}")
        if include is not None:
            parts.append(f"include_tokens: {include}")
        if incount is not None:
            parts.append(f"in_tokens: {incount}")
        if prompt is not None:
            parts.append(f"prompt_tokens: {prompt}")
        if cur_model:
            parts.append(f"cur_model: {cur_model}")
        return f"{indent}  - " + " | ".join(parts) + "\n"

    @staticmethod
    def _start_task(task: dict, file_lines_map: dict, cur_model: str):
        # ... unchanged ...
        if STATUS_MAP[task['status_char']] != 'To Do':
            return
        fn, ln = task['file'], task['line_no']
        indent, desc = task['indent'], task['desc']
        file_lines_map[fn][ln] = f"{indent}- [{REVERSE_STATUS['Doing']}] {desc}\n"
        stamp = datetime.utcnow().strftime('%Y-%m-%d %H:%M')
        task['_start_stamp'] = stamp
        know, prompt, incount, include = (task.get(k, 0) for k in
                                          ('_know_tokens','_prompt_tokens','_in_tokens','_include_tokens'))
        summary = TodoService._format_summary(indent, stamp, None,
                                              know, prompt, incount, include, cur_model)
        idx = ln + 1
        if idx < len(file_lines_map[fn]) and \
           file_lines_map[fn][idx].lstrip().startswith('- started:'):
            file_lines_map[fn][idx] = summary
        else:
            file_lines_map[fn].insert(idx, summary)
        TodoService._write_file(fn, file_lines_map[fn])
        task['status_char'] = REVERSE_STATUS['Doing']

    @staticmethod
    def _complete_task(task: dict, file_lines_map: dict, cur_model: str):
        # ... unchanged ...
        if STATUS_MAP[task['status_char']] != 'Doing':
            return
        fn, ln = task['file'], task['line_no']
        indent, desc = task['indent'], task['desc']
        file_lines_map[fn][ln] = f"{indent}- [{REVERSE_STATUS['Done']}] {desc}\n"
        stamp = datetime.utcnow().strftime('%Y-%m-%d %H:%M')
        start = task.get('_start_stamp','')
        know, prompt, incount, include = (task.get(k, 0) for k in
                                          ('_know_tokens','_prompt_tokens','_in_tokens','_include_tokens'))
        summary = TodoService._format_summary(indent, start, stamp,
                                              know, prompt, incount, include, cur_model)
        idx = ln + 1
        if idx < len(file_lines_map[fn]) and \
           file_lines_map[fn][idx].lstrip().startswith('- started:'):
            file_lines_map[fn][idx] = summary
        else:
            file_lines_map[fn].insert(idx, summary)
        TodoService._write_file(fn, file_lines_map[fn])
        task['status_char'] = REVERSE_STATUS['Done']

    def run_next_task(self, svc):
        # ... unchanged ...
        self._svc = svc
        self._load_all()
        todo = [t for t in self._tasks
                if STATUS_MAP[t['status_char']] == 'To Do']
        if not todo:
            logger.info("No To Do tasks found.")
            return
        self._process_one(todo[0], svc, self._file_lines)
        logger.info("Completed one To Do task")

    # ... rest of file unchanged ...

__all_classes__ = ["Change","ChangesList","TodoService"]