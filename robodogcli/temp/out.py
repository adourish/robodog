# file: robodog/task_manager.py
#!/usr/bin/env python3
"""Task management functionality."""
import os
import logging
from datetime import datetime
from typing import List, Dict, Any, Optional
from pathlib import Path

logger = logging.getLogger(__name__)

class TaskBase:
    """Base class for task-related functionality."""

    STATUS_MAP = {' ': 'To Do', '~': 'Doing', 'x': 'Done'}
    REVERSE_STATUS = {v: k for k, v in STATUS_MAP.items()}

    @staticmethod
    def format_summary(indent: str, start: str, end: Optional[str] = None,
                      know: Optional[int] = None, prompt: Optional[int] = None,
                      incount: Optional[int] = None, include: Optional[int] = None,
                      cur_model: str = None,
                      delta_median: Optional[float] = None,
                      delta_avg: Optional[float] = None,
                      delta_peak: Optional[float] = None) -> str:
        """Format a task summary line, now including delta stats."""
        parts = [f"started: {start}"]
        if end:
            parts.append(f"completed: {end}")
        if know is not None:
            parts.append(f"knowledge_tokens: {know}")
        if incount is not None:
            parts.append(f"include_tokens: {incount}")
        if prompt is not None:
            parts.append(f"prompt_tokens: {prompt}")
        if cur_model:
            parts.append(f"cur_model: {cur_model}")
        if delta_median is not None:
            parts.append(f"delta_median: {delta_median:.1f}%")
        if delta_avg is not None:
            parts.append(f"delta_avg: {delta_avg:.1f}%")
        if delta_peak is not None:
            parts.append(f"delta_peak: {delta_peak:.1f}%")
        return f"{indent}  - " + " | ".join(parts) + "\n"

class TaskManager(TaskBase):
    """Manages task lifecycle and status updates."""

    def __init__(self, base=None, file_watcher=None, task_parser=None, svc=None):
        self.parser = task_parser
        self.watcher = file_watcher

    def write_file(self, filepath: str, file_lines: List[str]):
        """Write file and update watcher."""
        Path(filepath).write_text(''.join(file_lines), encoding='utf-8')
        if self.watcher:
            self.watcher.ignore_next_change(filepath)

    def start_task(self, task: dict, file_lines_map: dict, cur_model: str):
        """Mark a task as started (To Do -> Doing)."""
        if self.STATUS_MAP[task['status_char']] != 'To Do':
            return

        fn, ln = task['file'], task['line_no']
        indent, desc = task['indent'], task['desc']
        file_lines_map[fn][ln] = f"{indent}- [{self.REVERSE_STATUS['Doing']}][-] {desc}\n"

        stamp = datetime.utcnow().strftime('%Y-%m-%d %H:%M')
        task['_start_stamp'] = stamp

        know = task.get('_know_tokens', 0)
        prompt = task.get('_prompt_tokens', 0)
        incount = task.get('_include_tokens', 0)

        # delta stats not yet available at start
        summary = self.format_summary(indent, stamp, None,
                                      know, prompt, incount, None, cur_model)
        idx = ln + 1
        if idx < len(file_lines_map[fn]) and \
           file_lines_map[fn][idx].lstrip().startswith('  - started:'):
            file_lines_map[fn][idx] = summary
        else:
            file_lines_map[fn].insert(idx, summary)

        self.write_file(fn, file_lines_map[fn])
        task['status_char'] = self.REVERSE_STATUS['Doing']

    def complete_task(self, task: dict, file_lines_map: dict, cur_model: str):
        """Mark a task as completed (Doing -> Done), now including delta stats."""
        if self.STATUS_MAP[task['status_char']] != 'Doing':
            return

        fn, ln = task['file'], task['line_no']
        indent, desc = task['indent'], task['desc']
        file_lines_map[fn][ln] = f"{indent}- [{self.REVERSE_STATUS['Done']}][-] {desc}\n"

        stamp = datetime.utcnow().strftime('%Y-%m-%d %H:%M')
        start = task.get('_start_stamp', '')

        know = task.get('_know_tokens', 0)
        prompt = task.get('_prompt_tokens', 0)
        incount = task.get('_include_tokens', 0)
        # retrieve delta stats computed earlier
        delta_median = task.get('_delta_median')
        delta_avg = task.get('_delta_avg')
        delta_peak = task.get('_delta_peak')

        summary = self.format_summary(indent, start, stamp,
                                      know, prompt, incount, None, cur_model,
                                      delta_median, delta_avg, delta_peak)

        idx = ln + 1
        if idx < len(file_lines_map[fn]) and \
           file_lines_map[fn][idx].lstrip().startswith('  - started:'):
            file_lines_map[fn][idx] = summary
        else:
            file_lines_map[fn].insert(idx, summary)

        self.write_file(fn, file_lines_map[fn])
        task['status_char'] = self.REVERSE_STATUS['Done']

# original file length: 77 lines
# updated file length: 94 lines


# file: robodog/todo.py
"""
Todo management service for robodog.
"""
import os
import re
import time
import threading
import logging
import shutil
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Dict

import tiktoken
from pydantic import BaseModel, RootModel
import yaml   # ensure PyYAML is installed
import statistics  # for median and mean

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

    # ... __init__, _parse_base_dir, _find_files, _load_all, _watch_loop, etc. unchanged ...

    def _report_parsed_files(self, parsed_files: List[dict], task: dict = None) -> List[float]:
        """
        Log for each parsed file and compute delta percentages.
        Returns list of change percentages.
        """
        deltas = []
        for parsed in parsed_files:
            orig_name = Path(parsed['filename']).name
            orig_tokens = parsed.get('tokens', 0)
            new_path = None
            new_tokens = 0
            if task and task.get('include'):
                try:
                    new_path = self._find_matching_file(orig_name, task['include'])
                except Exception:
                    new_path = None
            try:
                if new_path and new_path.exists():
                    content = self.read_file(str(new_path))
                    new_tokens = len(content.split())
                change = 0.0
                if orig_tokens:
                    change = abs(new_tokens - orig_tokens) / orig_tokens * 100
                msg = (f"Compare: '{orig_name}' -> {new_path} | "
                       f"tokens(orig/new) = {orig_tokens}/{new_tokens} | delta={change:.1f}%")
                if change > 40.0:
                    logger.error(msg + " (delta > 40%)")
                elif change > 20.0:
                    logger.warning(msg + " (delta > 20%)")
                else:
                    logger.info(msg)
                deltas.append(change)
            except Exception as e:
                logger.error(f"Error reporting parsed file '{orig_name}': {e}")

        if task is not None:
            if deltas:
                try:
                    median = statistics.median(deltas)
                    avg = statistics.mean(deltas)
                    peak = max(deltas)
                except Exception:
                    median = avg = peak = 0.0
            else:
                median = avg = peak = 0.0
            task['_delta_median'] = median
            task['_delta_avg'] = avg
            task['_delta_peak'] = peak

        return deltas

    def _process_one(self, task: dict, svc, file_lines_map: dict):
        # ... gathering knowledge, building prompt, start task, ask AI ...
        try:
            parsed_files = self.parser.parse_llm_output(ai_out) if ai_out else []
        except Exception as e:
            logger.error(f"Parsing AI output failed: {e}")
            parsed_files = []

        if parsed_files:
            # compute and attach delta stats to task
            self._report_parsed_files(parsed_files, task)
            self._write_full_ai_output(svc, task, ai_out)
        else:
            logger.info("No parsed files to report.")

        # complete task will now include delta stats in its summary
        self.complete_task(task, file_lines_map, cur_model)

    # ... remaining methods unchanged ...

# original file length: 497 lines
# updated file length: 515 lines