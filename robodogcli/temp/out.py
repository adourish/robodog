# file: robodog/task_manager.py
# Written on 2025-09-13 18:41:40 UTC

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
                      delta_peak: Optional[float] = None,
                      commited: float = 0) -> str:
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
        if commited <= -1:
            parts.append(f"commit: warning")
        if commited <= -1:
            parts.append(f"commit: error")
        if commited >= 1:
            parts.append(f"commit: success")
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
           file_lines_map[fn][idx].lstrip().startswith('- started:'):
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
           file_lines_map[fn][idx].lstrip().startswith('- started:'):
            file_lines_map[fn][idx] = summary
        else:
            file_lines_map[fn].insert(idx, summary)

        self.write_file(fn, file_lines_map[fn])
        task['status_char'] = self.REVERSE_STATUS['Done']

    def start_commit_task(self, task: dict, file_lines_map: dict, cur_model: str):
        """Mark a task as started (To Do -> Doing)."""
        if self.STATUS_MAP[task['status_char']] != 'To Do':
            return

        fn, ln = task['file'], task['line_no']
        indent, desc = task['indent'], task['desc']
        file_lines_map[fn][ln] = f"{indent}- [{self.REVERSE_STATUS['Doing']}][~] {desc}\n"

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
           file_lines_map[fn][idx].lstrip().startswith('- started:'):
            file_lines_map[fn][idx] = summary
        else:
            file_lines_map[fn].insert(idx, summary)

        self.write_file(fn, file_lines_map[fn])
        task['status_char'] = self.REVERSE_STATUS['Doing']

    def complete_commit_task(self, task: dict, file_lines_map: dict, cur_model: str, commited: float):
        """Mark a task as completed (Doing -> Done), now including delta stats."""
        if self.STATUS_MAP[task['status_char']] != 'Doing':
            return

        fn, ln = task['file'], task['line_no']
        indent, desc = task['indent'], task['desc']
        # Set first_status based on success
        first_status = 'x' if commited >= 1 else '~'
        # Set second_status based on success
        second_status = 'x' if commited >= 1 else '~'
        file_lines_map[fn][ln] = f"{indent}- [{first_status}][{second_status}] {desc}\n"

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
                                      delta_median, delta_avg, delta_peak, commited)

        idx = ln + 1
        if idx < len(file_lines_map[fn]) and \
           file_lines_map[fn][idx].lstrip().startswith('- started:'):
            file_lines_map[fn][idx] = summary
        else:
            file_lines_map[fn].insert(idx, summary)

        self.write_file(fn, file_lines_map[fn])
        task['status_char'] = self.REVERSE_STATUS['Done']

# original file length: 94 lines
# updated file length: 96 lines