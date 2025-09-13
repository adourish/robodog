# file: robodog/task_manager.py
#!/usr/bin/env python3
"""Task management functionality."""
import os
import logging
from datetime import datetime
from typing import List, Dict, Any, Optional
from pathlib import Path

from .base import TaskBase
from .file_watcher import FileWatcher
from .task_parser import TaskParser

logger = logging.getLogger(__name__)


class TaskManager(TaskBase):
    """Manages task lifecycle and status updates."""
    
    def __init__(self):
        self.parser = TaskParser()
        self.watcher = FileWatcher()
    
    def write_file(self, filepath: str, file_lines: List[str]):
        """Write file and update watcher."""
        Path(filepath).write_text(''.join(file_lines), encoding='utf-8')
        self.watcher.ignore_next_change(filepath)
    
    def start_task(self, task: dict, file_lines_map: dict, cur_model: str):
        """Mark a task as started (To Do -> Doing)."""
        if self.STATUS_MAP[task['status_char']] != 'To Do':
            return
        
        fn, ln = task['file'], task['line_no']
        indent, desc = task['indent'], task['desc']
        file_lines_map[fn][ln] = f"{indent}- [{self.REVERSE_STATUS['Doing']}] {desc}\n"
        
        stamp = datetime.utcnow().strftime('%Y-%m-%d %H:%M')
        task['_start_stamp'] = stamp
        
        know, prompt, incount, include = (task.get(k, 0) for k in
                                          ('_know_tokens','_prompt_tokens','_in_tokens','_include_tokens'))
        
        summary = self.format_summary(indent, stamp, None,
                                     know, prompt, incount, include, cur_model)
        
        idx = ln + 1
        if idx < len(file_lines_map[fn]) and \
           file_lines_map[fn][idx].lstrip().startswith('- started:'):
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
        file_lines_map[fn][ln] = f"{indent}- [{self.REVERSE_STATUS['Done']}] {desc}\n"
        
        stamp = datetime.utcnow().strftime('%Y-%m-%d %H:%M')
        start = task.get('_start_stamp','')
        
        know, prompt, incount, include = (task.get(k, 0) for k in
                                          ('_know_tokens','_prompt_tokens','_in_tokens','_include_tokens'))
        
        summary = self.format_summary(indent, start, stamp,
                                     know, prompt, incount, include, cur_model)
        
        idx = ln + 1
        if idx < len(file_lines_map[fn]) and \
           file_lines_map[fn][idx].lstrip().startswith('- started:'):
            file_lines_map[fn][idx] = summary
        else:
            file_lines_map[fn].insert(idx, summary)
        
        self.write_file(fn, file_lines_map[fn])
        task['status_char'] = self.REVERSE_STATUS['Done']

# original file length: 0 lines
# updated file length: 77 lines

