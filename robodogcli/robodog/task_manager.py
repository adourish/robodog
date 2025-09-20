#!/usr/bin/env python3
"""Task management functionality."""
import os
import logging
import sys
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
            indent: Optional[str] = None,
            start: Optional[str] = None,
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
        """Format a task summary line with inline compare info."""
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
        # commit/truncation flags
        if truncation <= -1:
            parts.append("truncation: warning")
        if truncation <= -2:
            parts.append("truncation: error")
        if committed <= -1:
            parts.append("commit: warning")
        if committed <= -2:
            parts.append("commit: error")
        if committed >= 1:
            parts.append("commit: success")
        # inline compare info
        if compare:
            parts.append("compare: " + ", ".join(compare))
        # single-line summary
        return f"{indent}  - " + " | ".join(parts) + "\n"

class TaskManager(TaskBase):
    """Manages task lifecycle and status updates."""

    def __init__(self, base=None, file_watcher=None, task_parser=None, svc=None):
        self.parser = task_parser
        self.watcher = file_watcher

    def format_task_summary(self, task, cur_model):
        """
        Build a one‐line summary of a task dict. Never throws;
        on error, emits a stderr message and returns a minimal summary.
        """
        parts = []
        try:
            # ensure task is a dict
            if not isinstance(task, dict):
                raise ValueError(f"expected task dict, got {type(task)}")

            # Required or optional fields with null checks
            start = task.get('start')
            if start is not None:
                parts.append(f"started: {start}")
            else:
                parts.append("started: N/A")

            end = task.get('end')
            if end:
                parts.append(f"completed: {end}")

            know = task.get('know')
            if know is not None:
                parts.append(f"knowledge: {know}")

            incount = task.get('incount')
            if incount is not None:
                parts.append(f"include: {incount}")

            prompt = task.get('prompt')
            if prompt is not None:
                parts.append(f"prompt: {prompt}")

            # Token counts
            prompt_tokens   = task.get('prompt_tokens')
            include_tokens  = task.get('include_tokens')
            knowledge_tokens= task.get('knowledge_tokens')

            if prompt_tokens:
                parts.append(f"prompt_tokens: {prompt_tokens}")
            if include_tokens:
                parts.append(f"include_tokens: {include_tokens}")
            if knowledge_tokens:
                parts.append(f"knowledge_tokens: {knowledge_tokens}")

            # Current model
            if cur_model:
                parts.append(f"cur_model: {cur_model}")

            # Truncation flags (use 0 as default)
            truncation = task.get('truncation', 0) or 0
            if truncation <= -1:
                parts.append("truncation: warning")
            if truncation <= -2:
                parts.append("truncation: error")

            # Commit flags (use 0 as default)
            committed = task.get('committed', 0) or 0
            if committed <= -1:
                parts.append("commit: warning")
            if committed <= -2:
                parts.append("commit: error")
            if committed >= 1:
                parts.append("commit: success")

            # Compare list
            compare = task.get('compare')
            if compare:
                if isinstance(compare, (list, tuple)):
                    parts.append("compare: " + ", ".join(str(x) for x in compare))
                else:
                    parts.append(f"compare: {compare}")

            # Indentation
            indent = task.get('indent', '')
            if indent is None:
                indent = ''

            # Build and return single‐line summary
            return f"{indent}  - " + " | ".join(parts) + "\n"

        except Exception as e:
            # Log the error and return a safe fallback
            sys.stderr.write(f"[format_task_summary] error: {e}\n")
            # Try to pull indent if possible
            try:
                indent = task.get('indent', '') if isinstance(task, dict) else ''
            except Exception:
                indent = ''
            return f"{indent}  - Error formatting task summary.\n"
    
    def format_task_summaryb(self, task, cur_model):
        start = task['start']
        end = task['end']
        know = task['know']
        incount = task['incount']
        prompt = task['prompt']
        truncation = task['truncation']
        committed = task['committed']
        _start_stamp = task['_start_stamp']
        knowledge_tokens = task['knowledge_tokens']
        include_tokens = task['include_tokens']
        prompt_tokens = task['prompt_tokens']
        compare = task['compare']
        indent = task['indent']
        parts = [f"started: {start}"]
        if end:
            parts.append(f"completed: {end}")
        if know is not None:
            parts.append(f"knowledge: {know}")
        if incount is not None:
            parts.append(f"include: {incount}")
        if prompt is not None:
            parts.append(f"prompt: {prompt}")
        if prompt_tokens:
            parts.append(f"prompt_tokens: {prompt_tokens}")
        if include_tokens:
            parts.append(f"include_tokens: {include_tokens}")
        if knowledge_tokens:
            parts.append(f"knowledge_tokens: {knowledge_tokens}")
        if cur_model:
            parts.append(f"cur_model: {cur_model}")
        # commit/truncation flags
        if truncation <= -1:
            parts.append("truncation: warning")
        if truncation <= -2:
            parts.append("truncation: error")
        if committed <= -1:
            parts.append("commit: warning")
        if committed <= -2:
            parts.append("commit: error")
        if committed >= 1:
            parts.append("commit: success")
        # inline compare info
        
        if compare:
            parts.append("compare: " + ", ".join(compare))
        # single-line summary
        return f"{indent}  - " + " | ".join(parts) + "\n"

        
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

        summary = self.format_task_summary(task, cur_model)
        idx = ln + 1
        if idx < len(file_lines_map[fn]) and file_lines_map[fn][idx].lstrip().startswith('- started:'):
            file_lines_map[fn][idx] = summary
        else:
            file_lines_map[fn].insert(idx, summary)

        self.write_file(fn, file_lines_map[fn])

        task['status_char'] = self.REVERSE_STATUS['Doing']

    def complete_task(self, task: dict, file_lines_map: dict, cur_model: str,
                      truncation: float = 0, compare: Optional[List[str]] = None, commit: bool = False):
        """Mark a task as completed (Doing -> Done), including inline compare info."""
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



# original file length: 187 lines
# updated file length: 187 lines