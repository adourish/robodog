#!/usr/bin/env python3
"""Task management functionality."""
import os
import logging
import sys
from datetime import datetime
from typing import List, Dict, Any, Optional, Callable
from pathlib import Path
import re
logger = logging.getLogger(__name__)


# New three-bracket TASK_RE
TASK_RE = re.compile(
    r'^(\s*)-\s*'                         # indent + "- "
    r'\[(?P<plan>[ x~\-])\]\s*'           # [plan_status]
    r'\[(?P<llm>[ x~\-])\]\s*'            # [llm_status]
    r'\[(?P<commit>[ x~\-])\]\s*'         # [commit_status]
    r'(?P<desc>.+)$'                      # the rest is your desc
)

# SUB_RE unchanged
SUB_RE = re.compile(
    r'^\s*-\s*(?P<key>include|out|in|focus|plan):\s*'
    r'(?:pattern=|file=)?(?P<pattern>"[^"]+"|`[^`]+`|\S+)'
    r'(?:\s+(?P<rec>recursive))?'
)


class TaskBase:
    """Base class for task-related functionality."""

    STATUS_MAP = {
        ' ': 'To Do',
        '~': 'Doing',
        'x': 'Done',
        '-': 'Ignore',
    }
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

    def __init__(self, base=None, file_watcher=None, task_parser=None, svc=None, file_service=None):
        self.parser = task_parser
        self.watcher = file_watcher
        self._svc = svc
        self._ui_callback: Optional[Callable] = None  # New: UI update callback
        self._file_watcher = file_watcher
        self._file_service = file_service
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
    
        
    def write_file(self, filepath: str, file_lines: List[str]):
        """Write file and update watcher."""
        Path(filepath).write_text(''.join(file_lines), encoding='utf-8')
        if self.watcher:
            self.watcher.ignore_next_change(filepath)

    def start_task(
        self,
        task: dict,
        file_lines_map: dict,
        cur_model: str,
        step: float = 1,
        progress_extra: Optional[Dict[str, object]] = None
    ):
        """
        Mark the task as started (To Do -> Doing for the given step)
        and update the todo.md line.
        """
        logger.info(f"Starting task: {task['desc']} (model: {cur_model}, step: {step})")
        # … (your existing logic up to rebuilding the line) …
        task['llm'] = self.REVERSE_STATUS['Doing']
        # rebuild the task line with new flags
        rebuilt_line = self._rebuild_task_line(task)
        fn = task['file']
        ln = task['line_no']
        lines = file_lines_map.get(fn, [])
        if 0 <= ln < len(lines):
            # replace the line in memory
            lines[ln] = rebuilt_line + '\n'
            file_lines_map[fn] = lines

            # ← NEW: tell watcher to skip the next change on this file
            self._file_watcher.ignore_next_change(fn)

            # write the updated todo.md
            self._file_service.write_file(Path(fn), "".join(lines))
            logger.info(f"Flag updated in {fn} at line {ln}")

    def complete_task(
        self,
        task: dict,
        file_lines_map: dict,
        cur_model: str,
        truncation: float = 0,
        compare: Optional[List[str]] = None,
        commit: bool = False,
        step: float = 1
    ):
        """
        Mark the task as completed for the given step (1=plan, 2=llm, 3=commit)
        and update the todo.md line.
        """
        logger.info(f"Completing task: {task['desc']} (step: {step})")
        # … (your existing logic up to rebuilding the line) …

        # rebuild the task line with updated flags
        rebuilt_line = self._rebuild_task_line(task)
        fn = task['file']
        ln = task['line_no']
        lines = file_lines_map.get(fn, [])

        if 0 <= ln < len(lines):
            # replace the line in memory
            lines[ln] = rebuilt_line + '\n'
            file_lines_map[fn] = lines

            # ← NEW: tell watcher to skip the next change on this file
            self._file_watcher.ignore_next_change(fn)

            # write the updated todo.md
            self._file_service.write_file(Path(fn), "".join(lines))
            logger.info(f"Flag/summary updated in {fn} at line {ln}")

    def _rebuild_task_line(self, task: dict) -> str:
        """
        Reconstruct a task line using the preserved `_raw_desc`, so that after flag changes
        the original description text is never lost.
        """
        raw_desc =  task.get('desc', '')
        clean_desc = raw_desc

        plan_flag = task.get('plan', ' ') or ' '
        llm_flag = task.get('llm', ' ') or ' '
        commit_flag = task.get('commit', ' ') or ' '
        for flag in (plan_flag, llm_flag, commit_flag):
            if flag not in ' x~-':
                logger.warning(f"Invalid flag '{flag}' detected; defaulting to space", extra={'log_color': 'DELTA'})

        flags = f"[{plan_flag}][{llm_flag}][{commit_flag}]"
        line = f"{task.get('indent', '')}- {flags} {clean_desc}"

        # Metadata appending disabled - keep task line clean
        # Token counts and timestamps are tracked internally but not displayed on the main line
        # meta_parts: List[str] = []
        # if task.get('_start_stamp'):
        #     meta_parts.append(f"started: {task['_start_stamp']}")
        # if task.get('_complete_stamp'):
        #     meta_parts.append(f"completed: {task['_complete_stamp']}")
        # if task.get('knowledge_tokens', 0):
        #     meta_parts.append(f"knowledge: {task['knowledge_tokens']}")
        # if task.get('include_tokens', 0):
        #     meta_parts.append(f"include: {task['include_tokens']}")
        # if task.get('prompt_tokens', 0):
        #     meta_parts.append(f"prompt: {task['prompt_tokens']}")
        # if task.get('plan_tokens', 0):
        #     meta_parts.append(f"plan: {task['plan_tokens']}")

        # for key in ('plan_desc', 'llm_desc', 'commit_desc'):
        #     stage_value = task.get(key, '') or ''
        #     if stage_value and stage_value != clean_desc:
        #         meta_parts.append(f"{key}: {stage_value}")

        # if meta_parts:
        #     line += " | " + " | ".join(meta_parts)

        if re.search(r'\[\s*[x~-]\s*\]\s*\[\s*[x~-]\s*\]\s*\[\s*[x~-]\s*\]\s*\[', line):
            logger.error(f"Flag duplication detected in rebuilt line: {line}", extra={'log_color': 'DELTA'})
        return line
                
    def _build_progress_bar(self, state: str, width: int = 10) -> str:
        """Render a progress bar for the given state."""
        fill_map = {
            'done': width * '█',
            'progress': width // 2 * '█' + (width - width // 2) * '░',
            'pending': width * '░',
            'ignored': width * '─'
        }
        bar = fill_map.get(state, width * '░')
        state_emoji = {'done': '✅', 'progress': '⚙️', 'pending': '⏳', 'ignored': '➖'}
        return f"{bar} {state_emoji.get(state, '⏳')}"


    def get_progress_update(self,
                              task: dict,
                              stage: object,
                              phase: str,
                              extra: Optional[Dict[str, object]] = None) -> None:
        """
        Emit a multi-line progress update.  Bars and emojis driven by actual task flags.
        """
        if task is None:
            return
        extra = dict(extra or {})

        # map numeric stage → key
        stage_map    = {1: 'plan', 2: 'llm', 3: 'commit'}
        stage_key    = stage_map.get(stage, None)
        if not stage_key:
            return

        # labels & emojis
        labels       = {'plan': 'Plan',   'llm': 'Code',  'commit': 'Commit'}
        icons        = {'plan': '📝',    'llm': '💻',    'commit': '📦'}
        state_names  = {'pending': 'pending', 'progress': 'running',
                        'done': 'done',      'ignored': 'skipped'}
        phase_icons  = {'start': '🚀 Starting', 'complete': '✅ Completed'}

        # derive raw states from flags
        def to_state(f):
            return {' ': 'pending', '~': 'progress', 'x': 'done', '-': 'ignored'}.get(f, 'pending')

        states = {
            'plan':   to_state(task.get('plan')),
            'llm':    to_state(task.get('llm')),
            'commit': to_state(task.get('commit'))
        }

        # override current stage on completion so bar is fully █ and ✅
        if phase == 'complete':
            states[stage_key] = 'done'

        # build lines
        title = f"{phase_icons.get(phase)} {labels[stage_key]} for: {task['desc']}"
        lines = [title, ""]
        for key in ('plan', 'llm', 'commit'):
            bar = self._build_progress_bar(states[key])
            emoji = icons[key]
            name  = labels[key].ljust(7)
            lines.append(f"{emoji} {name}: {bar} {state_names[states[key]]}")

        include_filenames_text = task.get('include_filenames_text','')
        lines.append(f"Include files:")
        lines.append(f"{include_filenames_text}")
        # timestamps & tokens
        lines += ["",
                  f"started:   {task.get('_start_stamp','—')}",
                  f"completed: {task.get('_complete_stamp','—')}",
                  f"knowledge: {task.get('knowledge_tokens',0)}",
                  f"include:   {task.get('include_tokens',0)}",
                  f"prompt:    {task.get('prompt_tokens',0)}",
                  f"plan:      {task.get('plan_tokens',0)}",
                  f"cur_model: {task.get('cur_model', self._svc.get_cur_model() if self._svc else '—')}"]


        # any extras (like file lists or previews)
        if extra:
            lines.append("")
            for k, v in extra.items():
                lines.append(f"{k}: {v}")

        
        
        message = "\n".join(lines)
        logger.info(message, extra={'log_color':'HIGHLIGHT'})
        return message

# original file length: 187 lines
# updated file length: 187 lines