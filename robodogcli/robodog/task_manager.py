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
                      cur_model: str = None) -> str:
        """Format a task summary line."""
        parts = [f"started: {start}"]
        if end:
            parts.append(f"completed: {end}")
        if know is not None:
            parts.append(f"knowledge_tokens: {know}")
        if include is not None:
            parts.append(f"include_tokens: {include}")
        if prompt is not None:
            parts.append(f"prompt_tokens: {prompt}")
        if cur_model:
            parts.append(f"cur_model: {cur_model}")
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
        
        know, prompt, incount, include = (task.get(k, 0) for k in
                                          ('_know_tokens','_prompt_tokens','_in_tokens','_include_tokens'))
        
        summary = self.format_summary(indent, stamp, None,
                                     know, prompt, incount, include, cur_model)
        
        idx = ln + 1
        if idx < len(file_lines_map[fn]) and \
           file_lines_map[fn][idx].lstrip().startswith('  - started:'):
            file_lines_map[fn][idx] = summary
        else:
            file_lines_map[fn].insert(idx, summary)
        
        self.write_file(fn, file_lines_map[fn])
        task['status_char'] = self.REVERSE_STATUS['Doing']
    
    def complete_task(self, task: dict, file_lines_map: dict, cur_model: str):
        """Mark a task as completed (Doing -> Done)."""
        if self.STATUS_MAP[task['status_char']] != 'Doing':
            return
        
        fn, ln = task['file'], task['line_no']
        indent, desc = task['indent'], task['desc']
        file_lines_map[fn][ln] = f"{indent}- [{self.REVERSE_STATUS['Done']}][-] {desc}\n"
        
        stamp = datetime.utcnow().strftime('%Y-%m-%d %H:%M')
        start = task.get('_start_stamp','')
        
        know, prompt, incount, include = (task.get(k, 0) for k in
                                          ('_know_tokens','_prompt_tokens','_in_tokens','_include_tokens'))
        
        summary = self.format_summary(indent, start, stamp,
                                     know, prompt, incount, include, cur_model)
        
        idx = ln + 1
        if idx < len(file_lines_map[fn]) and \
           file_lines_map[fn][idx].lstrip().startswith('  - started:'):
            file_lines_map[fn][idx] = summary
        else:
            file_lines_map[fn].insert(idx, summary)
        
        self.write_file(fn, file_lines_map[fn])
        task['status_char'] = self.REVERSE_STATUS['Done']

# original file length: 77 lines
# updated file length: 77 lines