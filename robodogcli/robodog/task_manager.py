# file: C:\Projects\robodog\robodogcli\robodog\task_manager.py
# filename: robodog/task_manager.py
# originalfilename: robodog/task_manager.py
# matchedfilename: C:\Projects\robodog\robodogcli\robodog\task_manager.py
# original file length: 185 lines
# updated file length: 179 lines
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
    def format_summary(
            indent: str,
            start: str,
            end: Optional[str] = None,
            know: Optional[int] = None,
            prompt: Optional[int] = None,
            incount: Optional[int] = None,
            include: Optional[int] = None,
            cur_model: str = None,
            delta_median: Optional[float] = None,
            delta_avg: Optional[float] = None,
            delta_peak: Optional[float] = None,
            committed: float = 0,
            truncation: float = 0,
            compare: Optional[List[str]] = None
        ) -> str:
        """Format a task summary line, now including delta stats and optional compare info."""
        parts = [f"started: {start}"]
        if end:
            parts.append(f"completed: {end}")
        if know is not None:
            parts.append(f"knowledge: {know}")
        if incount is not None:
            parts.append(f"include: {incount}")
        if prompt is not None:
            parts.append(f"prompt: {prompt}")
        if cur_model:
            parts.append(f"cur_model: {cur_model}")
        if truncation <= -1:
            parts.append(f"truncation: warning")
        if truncation <= -2:
            parts.append(f"truncation: error")
        if committed <= -1:
            parts.append(f"commit: warning")
        if committed <= -2:
            parts.append(f"commit: error")
        if committed >= 1:
            parts.append(f"commit: success")
        # Build the main summary line
        line = f"{indent}  - " + " | ".join(parts) + "\n"
        # Append compare section if provided
        if compare:
            for cmp in compare:
                line += f"{indent}    - compare: {cmp}\n"
        return line

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

        # No compare at start
        summary = self.format_summary(indent, stamp, None,
                                      know, prompt, incount, None,
                                      cur_model, 0, 0, 0, 0, 0, compare=None)

        idx = ln + 1
        if idx < len(file_lines_map[fn]) and file_lines_map[fn][idx].lstrip().startswith('- started:'):
            file_lines_map[fn][idx] = summary
        else:
            file_lines_map[fn].insert(idx, summary)

        self.write_file(fn, file_lines_map[fn])
        task['status_char'] = self.REVERSE_STATUS['Doing']

    def complete_task(self, task: dict, file_lines_map: dict, cur_model: str,
                      truncation: float = 0, compare: Optional[List[str]] = None):
        """Mark a task as completed (Doing -> Done), now including truncation status and compare info."""
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

        summary = self.format_summary(indent, start, stamp,
                                      know, prompt, incount, None,
                                      cur_model, 0, 0, 0,
                                      0, truncation, compare=compare)

        idx = ln + 1
        if idx < len(file_lines_map[fn]) and file_lines_map[fn][idx].lstrip().startswith('- started:'):
            file_lines_map[fn][idx] = summary
        else:
            file_lines_map[fn].insert(idx, summary)

        self.write_file(fn, file_lines_map[fn])
        task['status_char'] = self.REVERSE_STATUS['Done']

    def start_commit_task(self, task: dict, file_lines_map: dict, cur_model: str):
        """Mark a task as started (To Do -> Doing) with commit flag."""
        if self.STATUS_MAP[task['status_char']] != 'To Do':
            return
        # same as start_task
        self.start_task(task, file_lines_map, cur_model)

    def complete_commit_task(self, task: dict, file_lines_map: dict, cur_model: str,
                              committed: float, compare: Optional[List[str]] = None):
        """Mark a commit-task as completed with commit status, delta stats, and compare info."""
        fn, ln = task['file'], task['line_no']
        indent, desc = task['indent'], task['desc']
        second_status = 'x' if committed >= 1 else '~'
        file_lines_map[fn][ln] = f"{indent}- [x][{second_status}] {desc}\n"

        stamp = datetime.utcnow().strftime('%Y-%m-%d %H:%M')
        start = task.get('_start_stamp', '')

        know = task.get('_know_tokens', 0)
        prompt = task.get('_prompt_tokens', 0)
        incount = task.get('_include_tokens', 0)
        delta_median = task.get('_delta_median')
        delta_avg = task.get('_delta_avg')
        delta_peak = task.get('_delta_peak')

        summary = self.format_summary(indent, start, stamp,
                                      know, prompt, incount, None,
                                      cur_model, delta_median, delta_avg,
                                      delta_peak, committed, 0,
                                      compare=compare)

        idx = ln + 1
        if idx < len(file_lines_map[fn]) and file_lines_map[fn][idx].lstrip().startswith('- started:'):
            file_lines_map[fn][idx] = summary
        else:
            file_lines_map[fn].insert(idx, summary)

        self.write_file(fn, file_lines_map[fn])
        task['status_char'] = self.REVERSE_STATUS['Done']

# original file length: 187 lines
# updated file length: 179 lines