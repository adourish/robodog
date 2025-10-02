# file: todo.py
#!/usr/bin/env python3
"""Todo task management and execution service."""
import os
import re
import time
import threading
import logging
import traceback
import shutil
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Dict, Callable
import statistics  # Added for calculating median, avg, peak
from textwrap import shorten

import tiktoken
from pydantic import BaseModel, RootModel
import yaml   # ensure PyYAML is installed
from typing import Any, Tuple
try:
    from .parse_service import ParseService
except ImportError:
    from parse_service import ParseService

logger = logging.getLogger(__name__)

# Updated TASK_RE to robustly capture flags without including them in desc group
# Now ensures desc starts after all captured flags, avoiding leakage of trailing flags/metadata into desc
# Also uses non-greedy matching and anchors to prevent trailing content leakage
TASK_RE = re.compile(
    r'^(\s*)-\s*'                  # indent + "- "
    r'(?:\s*\[(?P<plan>[ x~-])\])?'   # optional [plan_flag]
    r'\s*\[(?P<status>[ x~])\]'     # execution [status] - required
    r'(?:\s*\[(?P<write>[ x~-])\])?' # optional [write_flag]
    r'(?:\s*\|\s*(?P<metadata>.*?))?' # optional metadata after |
    r'\s*(?P<desc>.*?)(?=\s*\[|$)'  # desc: capture up to next [ or end, non-greedy
    # Enhanced: Use (?=\s*\[|$) to stop before any trailing [, ensuring no flags leak into desc
)

SUB_RE = re.compile(
    r'^\s*-\s*(?P<key>include|out|in|focus|plan):\s*'
    r'(?:pattern=|file=)?(?P<pattern>"[^"]+"|`[^`]+`|\S+)'
    r'(?:\s+(?P<rec>recursive))?'
)

STATUS_MAP     = {' ': 'To Do', '~': 'Doing', 'x': 'Done', '-': 'Ignore'}
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

    def __init__(self, roots: List[str], svc=None, prompt_builder=None, task_manager=None, task_parser=None, file_watcher=None, file_service=None, exclude_dirs={"node_modules", "dist", "diffout"}, todo_util=None, app=None):
        logger.info(f"Initializing TodoService with roots: {roots}", extra={'log_color': 'HIGHLIGHT'})
        logger.debug(f"Svc provided: {svc is not None}, Prompt builder: {prompt_builder is not None}")
        try:
            self._roots        = roots
            self._file_lines   = {}
            self._tasks        = []
            self._mtimes       = {}
            self._watch_ignore = {}
            self._todo_util = todo_util
            self._svc          = svc
            self.parser        = ParseService()
            self._prompt_builder = prompt_builder
            self._task_manager = task_manager
            self._task_parser = task_parser
            self._file_watcher = file_watcher
            self._file_service = file_service
            self._exclude_dirs = exclude_dirs
            self._ui_callback: Optional[Callable] = None  # New: UI update callback
            # MVP: parse a `base:` directive from front-matter
            self._base_dir = self._parse_base_dir()
            self._app = app
            logger.info(f"Base directory parsed: {self._base_dir}", extra={'log_color': 'HIGHLIGHT'})

            self._load_all()
            for fn in self._find_files():
                try:
                    self._mtimes[fn] = os.path.getmtime(fn)
                    logger.debug(f"Initial mtime for {fn}: {self._mtimes[fn]}")
                except Exception as e:
                    logger.exception(f"Could not get mtime for {fn}: {e}", extra={'log_color': 'DELTA'})
                    pass
            threading.Thread(target=self._watch_loop, daemon=True).start()
            logger.info("TodoService initialized successfully", extra={'log_color': 'HIGHLIGHT'})
        except Exception as e:
            logger.exception(f"Error during initialization of TodoService: {e}", extra={'log_color': 'DELTA'})
            raise

    def set_ui_callback(self, callback: Callable):
        """Set callback for UI updates during task processing."""
        self._ui_callback = callback

    def _flag_to_state(self, flag: Optional[str]) -> str:
        """Translate flag character into a progress state."""
        mapping = {
            'x': 'done',
            '~': 'progress',
            '-': 'ignored',
            ' ': 'pending',
            None: 'pending'
        }
        return mapping.get(flag, 'pending')

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

    def _emit_progress_update(self, task: dict, stage: object, phase: str, extra: Optional[Dict[str, object]] = None) -> None:
        """Emit a multi-line progress update with contextual details."""
        if task is None:
            return
        extra = dict(extra or {})
        stage_map = {1: 'plan', 2: 'llm', 3: 'commit'}
        stage_key = stage_map.get(stage, stage if isinstance(stage, str) else 'plan')
        stage_labels = {'plan': 'Plan', 'llm': 'Code', 'commit': 'Commit'}
        stage_emojis = {'plan': '📝', 'llm': '💻', 'commit': '📦'}
        state_emojis = {'pending': '⏳', 'progress': '⚙️', 'done': '✅', 'ignored': '⏸️'}
        state_titles = {'pending': 'pending', 'progress': 'running', 'done': 'done', 'ignored': 'skipped'}
        phase_icons = {'start': '🚀 Starting', 'complete': '✅ Completed'}
        phase_icon = phase_icons.get(phase, 'ℹ️ Status')
        # Fixed-width alignment: Use max label width of 10 chars for labels, 10 for bars
        phase_title = phase_icon + f" {stage_labels.get(stage_key, stage_key.title())} step for: {task['desc'][:120]}{'…' if len(task['desc']) > 120 else ''}"

        desc = task.get('desc', '').strip()
        if self._todo_util:
            desc = self._todo_util.sanitize_desc(desc)
        else:
            desc = re.sub(r'\s*\[.*?\]\s*$', '', desc).strip()
        desc_display = shorten(desc, width=120, placeholder='…')

        stage_states = {
            'plan': self._flag_to_state(task.get('plan_flag')),
            'llm': self._flag_to_state(task.get('status_char')),
            'commit': self._flag_to_state(task.get('write_flag'))
        }

        progress_lines = []
        label_width = 10  # Fixed width for "Plan    :", "Code    :", "Commit  :" (max 10 chars)
        for key in ('plan', 'llm', 'commit'):
            emoji = stage_emojis[key]
            label = stage_labels[key].ljust(label_width)  # Pad labels to fixed width
            state = stage_states[key]
            bar = self._build_progress_bar(state)
            progress_lines.append(
                f"{emoji} {label}: {bar} {state_titles[state]}"
            )

        started_stamp = task.get('_start_stamp') or '—'
        completed_stamp = task.get('_complete_stamp') or '—'
        knowledge_tokens = task.get('knowledge_tokens', 0)
        include_tokens = task.get('include_tokens', 0)
        prompt_tokens = task.get('prompt_tokens', 0)
        plan_tokens = task.get('plan_tokens', 0)
        cur_model = task.get('cur_model') or self._svc.get_cur_model() if self._svc else '—'

        include_spec = task.get('include')
        include_spec_text = '<none>'
        if isinstance(include_spec, dict):
            bits = []
            if include_spec.get('pattern'):
                bits.append(include_spec['pattern'])
            if include_spec.get('file'):
                bits.append(include_spec['file'])
            if include_spec.get('recursive'):
                bits.append('recursive')
            include_spec_text = ' '.join(bits) if bits else '<none>'

        out_spec = task.get('out')
        out_spec_text = '<none>'
        if isinstance(out_spec, dict):
            bits = []
            if out_spec.get('pattern'):
                bits.append(out_spec['pattern'])
            if out_spec.get('file'):
                bits.append(out_spec['file'])
            if out_spec.get('recursive'):
                bits.append('recursive')
            out_spec_text = ' '.join(bits) if bits else '<none>'
        elif isinstance(out_spec, str) and out_spec.strip():
            out_spec_text = out_spec.strip()

        plan_spec = task.get('plan')
        plan_spec_text = '<none>'
        if isinstance(plan_spec, dict):
            bits = []
            if plan_spec.get('pattern'):
                bits.append(plan_spec['pattern'])
            if plan_spec.get('file'):
                bits.append(plan_spec['file'])
            if plan_spec.get('recursive'):
                bits.append('recursive')
            plan_spec_text = ' '.join(bits) if bits else '<none>'
        elif isinstance(plan_spec, str) and plan_spec.strip():
            plan_spec_text = plan_spec.strip()

        include_files = extra.get('include_files') or task.get('_include_files') or []
        plan_path = task.get('_plan_path')
        out_path = task.get('_out_path')
        files_entries = extra.get('files')
        if not files_entries and stage_key == 'llm':
            files_entries = task.get('_pending_files')
        if not files_entries and stage_key == 'commit':
            files_entries = task.get('_committed_files') if phase == 'complete' else task.get('_pending_files')

        out_text = out_spec_text if out_spec_text != '<none>' else f"{out_path}" if out_path else '<none>'
        plan_text = plan_spec_text if plan_spec_text != '<none>' else f"{plan_path}" if plan_path else '<none>'

        message_lines = [phase_title, ""]
        message_lines.extend(progress_lines)
        message_lines.append("")
        message_lines.extend([
            f"started: {started_stamp}",
            f"completed: {completed_stamp}",
            f"knowledge: {knowledge_tokens}",
            f"include: {include_tokens}",
            f"prompt: {prompt_tokens}",
            f"plan: {plan_tokens}",
            f"cur_model: {cur_model}",
            f"include: {include_spec_text}",
            f"out: {out_text}",
            f"plan: {plan_text}",
        ])

        if include_files:
            message_lines.append("")
            message_lines.append("include files:")
            for path in include_files:
                message_lines.append(f"  • {path}")

        plan_preview = extra.get('plan_preview') or (task.get('_latest_plan') if stage_key == 'plan' and phase == 'complete' else None)
        if plan_preview:
            plan_lines = plan_preview.strip().splitlines()
            if plan_lines:
                message_lines.append("")
                message_lines.append("Plan from plan.md:")
                if plan_path:
                    message_lines.append(f"  # file: {Path(plan_path).name}")
                display_plan = plan_lines[:6]
                for line in display_plan:
                    message_lines.append(f"  {line}")
                if len(plan_lines) > len(display_plan):
                    message_lines.append("  …")

        if files_entries:
            message_lines.append("")
            files_heading = "files:"
            if stage_key == 'llm' and phase == 'complete':
                files_heading = "files (preview):"
            elif stage_key == 'commit' and phase == 'complete':
                files_heading = "files (committed):"
            elif stage_key == 'commit':
                files_heading = "files (pending):"
            message_lines.append(files_heading)

            for entry in files_entries:
                message_lines.append(f"  • {entry}")

        message = "\n".join(message_lines)
        logger.info(message, extra={'log_color': 'HIGHLIGHT'})
        if self._ui_callback:
            self._ui_callback(message)
            print(message, flush=True)  # Flush after callback for immediate visibility

    def _parse_base_dir(self) -> Optional[str]:
        logger.debug("_parse_base_dir called", extra={'log_color': 'HIGHLIGHT'})
        try:
            for fn in self._find_files():
                logger.info(f"Parsing front-matter from {fn}", extra={'log_color': 'HIGHLIGHT'})
                content = self._file_service.safe_read_file(Path(fn))
                lines = content.splitlines()
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
                            logger.info(f"Found base dir: {base}", extra={'log_color': 'HIGHLIGHT'})
                            return os.path.normpath(base)
            logger.info("No base dir found", extra={'log_color': 'HIGHLIGHT'})
            return None
        except Exception as e:
            logger.exception(f"Error parsing base dir: {e}", extra={'log_color': 'DELTA'})
            return None

    def _find_files(self) -> List[str]:
        logger.debug("_find_files called")
        try:
            out = []
            for r in self._roots:
                for dp, _, fns in os.walk(r):
                    if self.FILENAME in fns:
                        out.append(os.path.join(dp, self.FILENAME))
            logger.debug(f"Found {len(out)} todo files", extra={'log_color': 'HIGHLIGHT'})
            return out
        except Exception as e:
            logger.exception(f"Error finding todo files: {e}", extra={'log_color': 'DELTA'})
            return []

    def _normalize_task_flags(self):
        """
        Make sure every task always has plan_flag, status_char and write_flag set
        to one of ' ', '~', 'x', '-' (never None).
        Now with logging for normalization. Enhanced: Detect and log if desc contains "[-]" as contamination.
        """
        logger.info("Normalizing task flags", extra={'log_color': 'HIGHLIGHT'})
        changed = 0
        contaminated = 0
        for i, t in enumerate(self._tasks):
            orig_flags = f"P:{t.get('plan_flag')} S:{t.get('status_char')} W:{t.get('write_flag')}"
            desc_has_flag = bool(re.search(r'\[\s*-\s*\]', t.get('desc', '')))
            if desc_has_flag:
                logger.warning(f"Task {i} desc contaminated with '[-]': {t['desc'][:100]}...", extra={'log_color': 'DELTA'})
                contaminated += 1
                t['desc'] = self._todo_util.sanitize_desc(t['desc'])
                logger.debug(f"Sanitized contaminated desc for task {i}: {t['desc'][:50]}...")
            t['plan_flag']   = t.get('plan_flag')   or ' '
            t['status_char'] = t.get('status_char') or ' '
            t['write_flag']  = t.get('write_flag')  or ' '
            if orig_flags != f"P:{t['plan_flag']} S:{t['status_char']} W:{t['write_flag']}":
                changed += 1
                logger.debug(f"Normalized task {i}: {orig_flags} -> P:{t['plan_flag']} S:{t['status_char']} W:{t['write_flag']}")
        logger.info(f"Normalized {changed} tasks out of {len(self._tasks)}; Contaminated: {contaminated}", extra={'log_color': 'PERCENT'})

    def _load_all(self):
        """
        Parse each todo.md into tasks, capturing optional second‐bracket
        write‐flag, third bracket for planning, and any adjacent ```knowledge``` block.
        Also parse metadata from the task line (e.g., | started: ... | knowledge: 0).
        Added logging for task loading.
        Now includes immediate sanitization of full_desc after extraction to clean trailing flags before metadata parsing.
        Enhanced to parse plan_tokens from metadata.
        """
        logger.debug("_load_all called: Reloading all tasks from files", extra={'log_color': 'HIGHLIGHT'})
        try:
            self._file_lines.clear()
            self._tasks.clear()
            total_tasks = 0
            for fn in self._find_files():
                logger.info(f"Parsing tasks from {fn}", extra={'log_color': 'HIGHLIGHT'})
                content = self._file_service.safe_read_file(Path(fn))
                lines = content.splitlines(keepends=True)
                self._file_lines[fn] = lines
                i = 0
                task_count = 0
                while i < len(lines):
                    m = TASK_RE.match(lines[i])
                    if not m:
                        i += 1
                        continue

                    indent     = m.group(1)
                    status     = m.group('status')
                    write_flag = m.group('write')
                    plan_flag  = m.group('plan')
                    metadata_str = m.group('metadata')
                    full_desc  = m.group('desc')
                    full_desc = self._todo_util.sanitize_desc(full_desc)
                    logger.debug(f"Raw full_desc after immediate sanitization: {full_desc[:100]}...")
                    
                    metadata = self._todo_util._parse_task_metadata(full_desc)
                    desc     = metadata.pop('desc')
                    task     = {
                        'file': fn,
                        'line_no': i,
                        'indent': indent,
                        'plan_flag': plan_flag,
                        'status_char': status,
                        'write_flag': write_flag,
                        'desc': desc,
                        'include': None,
                        'in': None,
                        'out': None,
                        'plan': None,
                        'knowledge': '',
                        'knowledge_tokens': 0,
                        'include_tokens': 0,
                        'prompt_tokens': 0,
                        'plan_tokens': 0,
                        '_start_stamp': None,
                        '_know_tokens': 0,
                        '_in_tokens': 0,
                        '_prompt_tokens': 0,
                        '_include_tokens': 0,
                        '_complete_stamp': None,
                    }
                    task.update(metadata)

                    logger.info(f"Loaded task {task_count}: flags P:{plan_flag} S:{status} W:{write_flag}, desc length {len(desc)} (sanitized)", extra={'log_color': 'HIGHLIGHT'})

                    j = i + 1
                    while j < len(lines) and lines[j].startswith(indent + '  '):
                        sub = SUB_RE.match(lines[j])
                        if sub:
                            key = sub.group('key')
                            pat = sub.group('pattern').strip('"').strip('`')
                            rec = bool(sub.group('rec'))
                            if key == 'focus':
                                task['out'] = {'pattern': pat, 'recursive': rec}
                            elif key == 'plan':
                                task['plan'] = {'pattern': pat, 'recursive': rec}
                            else:
                                task[key] = {'pattern': pat, 'recursive': rec}
                        j += 1

                    if j < len(lines) and lines[j].lstrip().startswith('```knowledge'):
                        fence = []
                        j += 1
                        while j < len(lines) and not lines[j].startswith('```'):
                            fence.append(lines[j])
                            j += 1
                        task['knowledge'] = ''.join(fence)
                        know_tokens = len(''.join(fence).split())
                        task['_know_tokens'] = know_tokens
                        task['knowledge_tokens'] = know_tokens
                        logger.info(f"Loaded knowledge for task {task_count}: {know_tokens} tokens", extra={'log_color': 'PERCENT'})
                        j += 1

                    self._tasks.append(task)
                    task_count += 1
                    total_tasks += 1
                    i = j
                logger.info(f"Loaded {task_count} tasks from {fn}", extra={'log_color': 'PERCENT'})
            for i, t in enumerate(self._tasks):
                t['desc'] = self._todo_util.sanitize_desc(t['desc'])
                logger.debug(f"Post-load sanitized task {i} desc: {t['desc'][:50]}...")
            logger.info(f"Total tasks loaded across all files: {total_tasks}", extra={'log_color': 'PERCENT'})
        except Exception as e:
            logger.exception(f"Error in _load_all: {e}", extra={'log_color': 'DELTA'})
            traceback.print_exc()

    def _watch_loop(self):
        """
        Watch all todo.md files under self._roots.
        On external change, re‐parse tasks, re‐emit any manually Done tasks
        with write_flag=' ' and then run the next To Do.
        Added logging for watch events.
        Enhanced: UI callback support for real-time updates.
        """
        logger.debug("_watch_loop started", extra={'log_color': 'HIGHLIGHT'})
        while True:
            try:
                for fn in self._find_files():
                    try:
                        mtime = os.path.getmtime(fn)
                    except OSError:
                        logger.warning(f"File {fn} not found, skipping", extra={'log_color': 'DELTA'})
                        continue

                    ignore_time = self._watch_ignore.get(fn)
                    if ignore_time and abs(mtime - ignore_time) < 1e-3:
                        self._watch_ignore.pop(fn, None)
                        logger.debug(f"Skipped our own write for {fn}")

                    elif self._mtimes.get(fn) and mtime > self._mtimes[fn]:
                        logger.info(f"Detected external change in {fn}, reloading tasks", extra={'log_color': 'DELTA'})
                        if self._ui_callback:
                            self._ui_callback(f"📁 File changed: {fn}")
                            
                        if not self._svc:
                            logger.warning("Svc not available, skipping change processing", extra={'log_color': 'DELTA'})
                            continue

                        try:
                            self._load_all()

                            next_todos = [
                                t for t in self._tasks
                                if t.get('status_char') == ' '
                                or t.get('write_flag')  == ' '
                                or t.get('plan_flag')   == ' '
                            ]
                            if next_todos:
                                logger.info(f"New To Do tasks found ({len(next_todos)}), running next", extra={'log_color': 'HIGHLIGHT'})
                                if self._ui_callback:
                                    self._ui_callback(f"🆕 {len(next_todos)} new tasks found")
                                self.run_next_task(self._svc, fn)

                        except Exception as e:
                            logger.exception(f"Watch loop error processing {fn}: {e}", extra={'log_color': 'DELTA'})
                            traceback.print_exc()

                    self._mtimes[fn] = mtime

            except Exception as e:
                logger.exception(f"Error in watch loop: {e}", extra={'log_color': 'DELTA'})
                traceback.print_exc()

            time.sleep(1)

    def start_task(self, task: dict, file_lines_map: dict, cur_model: str, step: float = 1, progress_extra: Optional[Dict[str, object]] = None):
        logger.info(f"Starting task: {task['desc']} (model: {cur_model}, step: {step})", extra={'log_color': 'HIGHLIGHT'})
        progress_payload: Dict[str, object] = dict(progress_extra or {})
        try:
            task['knowledge_tokens'] = task.get('knowledge_tokens', task.get('_know_tokens', 0))
            task['include_tokens'] = task.get('include_tokens', task.get('_include_tokens', 0))
            task['prompt_tokens'] = task.get('prompt_tokens', task.get('_prompt_tokens', 0))
            task['plan_tokens'] = task.get('plan_tokens', 0)
            if step == 1:
                task['plan_flag'] = '~'
                logger.info(f"Set plan_flag to ~ for task: {task['desc']}", extra={'log_color': 'HIGHLIGHT'})
            elif step == 2:
                task['status_char'] = '~'
                logger.info(f"Set status_char to ~ for task: {task['desc']}", extra={'log_color': 'HIGHLIGHT'})
            elif step == 3:
                task['write_flag'] = '~'
                logger.info(f"Set write_flag to ~ for task: {task['desc']}", extra={'log_color': 'HIGHLIGHT'})
            rebuilt_line = self._todo_util._rebuild_task_line(task)
            fn = task['file']
            line_no = task['line_no']
            lines = file_lines_map.get(fn, [])
            if 0 <= line_no < len(lines):
                lines[line_no] = rebuilt_line + '\n'
                file_lines_map[fn] = lines
                self._file_service.write_file(Path(fn), ''.join(lines))
                logger.info(f"Immediately updated flags in todo.md for task at line {line_no} in {fn}: plan={task['plan_flag']}, status={task['status_char']}, write={task['write_flag']}", extra={'log_color': 'HIGHLIGHT'})
            st = self._task_manager.start_task(task, file_lines_map, cur_model, step)
            if st is None:
                st = datetime.now().isoformat()
            task['_start_stamp'] = st
            if progress_payload:
                if step == 3 and 'files' not in progress_payload:
                    pending = task.get('_pending_files')
                    if pending:
                        progress_payload['files'] = pending
            elif step == 3 and task.get('_pending_files'):
                progress_payload['files'] = task.get('_pending_files')
            self._emit_progress_update(task, step, 'start', progress_payload)
            logger.info(f"Task started: plan_tokens={task['plan_tokens']}, knowledge_tokens={task['knowledge_tokens']}, include_tokens={task['include_tokens']}, prompt_tokens={task['prompt_tokens']}", extra={'log_color': 'PERCENT'})
            return st
        except Exception as e:
            logger.exception(f"Error starting task {task['desc']}: {e}", extra={'log_color': 'DELTA'})
            traceback.print_exc()
            st = datetime.now().isoformat()
            task['_start_stamp'] = st
            self._emit_progress_update(task, step, 'start', progress_payload)
            return st
            
    def complete_task(self, task: dict, file_lines_map: dict, cur_model: str, truncation: float, compare: Optional[List[str]] = None, commit: bool = False, step: float = 1):
        logger.info(f"Completing task: {task['desc']} (model: {cur_model}, commit: {commit}, step: {step})", extra={'log_color': 'HIGHLIGHT'})
        status_extra: Dict[str, object] = {}
        try:
            task['knowledge_tokens'] = task.get('knowledge_tokens', task.get('_know_tokens', 0))
            task['include_tokens'] = task.get('include_tokens', task.get('_include_tokens', 0))
            task['prompt_tokens'] = task.get('prompt_tokens', task.get('_prompt_tokens', 0))
            task['plan_tokens'] = task.get('plan_tokens', 0)
            if step == 1:
                task['plan_flag'] = 'x'
                logger.info(f"Set plan_flag to x for task: {task['desc']}", extra={'log_color': 'HIGHLIGHT'})
            elif step == 2:
                task['status_char'] = 'x'
                logger.info(f"Set status_char to x for task: {task['desc']}", extra={'log_color': 'HIGHLIGHT'})
            elif step == 3:
                task['write_flag'] = 'x'
                logger.info(f"Set write_flag to x for task: {task['desc']}", extra={'log_color': 'HIGHLIGHT'})
            rebuilt_line = self._todo_util._rebuild_task_line(task)
            fn = task['file']
            line_no = task['line_no']
            lines = file_lines_map.get(fn, [])
            if 0 <= line_no < len(lines):
                lines[line_no] = rebuilt_line + '\n'
                file_lines_map[fn] = lines
                self._file_service.write_file(Path(fn), ''.join(lines))
                logger.info(f"Updated flags in todo.md for task at line {line_no} in {fn}: plan={task['plan_flag']}, status={task['status_char']}, write={task['write_flag']}", extra={'log_color': 'HIGHLIGHT'})
            if compare:
                if step == 2:
                    task['_pending_files'] = compare
                elif step == 3:
                    task['_committed_files'] = compare
                status_extra['files'] = compare
            if step == 1 and task.get('_latest_plan'):
                status_extra['plan_preview'] = task.get('_latest_plan')
            ct = self._task_manager.complete_task(task, file_lines_map, cur_model, 0, compare, commit, step)
            if ct is None:
                ct = datetime.now().isoformat()
            task['_complete_stamp'] = ct
            self._emit_progress_update(task, step, 'complete', status_extra)
            logger.info(f"Task completed: plan_tokens={task['plan_tokens']}, knowledge_tokens={task['knowledge_tokens']}, include_tokens={task['include_tokens']}, prompt_tokens={task['prompt_tokens']}", extra={'log_color': 'PERCENT'})
            return ct
        except Exception as e:
            logger.exception(f"Error completing task {task['desc']}: {e}", extra={'log_color': 'DELTA'})
            traceback.print_exc()
            ct = datetime.now().isoformat()
            task['_complete_stamp'] = ct
            self._emit_progress_update(task, step, 'complete', status_extra)
            return ct
            
    def run_next_task(self, svc, todoFilename: str = ""):
        logger.info("run_next_task called", extra={'log_color': 'HIGHLIGHT'})
        try:
            self._svc = svc
            self._load_all()
            self._normalize_task_flags()

            plan_pending   = [t for t in self._tasks if t['plan_flag']   == ' ']
            llm_pending    = [t for t in self._tasks
                              if t['plan_flag']   != ' '
                             and t['status_char'] == ' ']
            commit_pending = [t for t in self._tasks
                              if t['plan_flag']   != ' '
                             and t['status_char'] != ' '
                             and t['write_flag'] == ' ']
            
            todo = plan_pending + llm_pending + commit_pending
            if not todo:
                logger.warning("No pending tasks found for any step.", extra={'log_color': 'DELTA'})
                if self._ui_callback:
                    self._ui_callback("✅ No pending tasks found")
                return
            next_task = todo[0]
            step = 1 if next_task in plan_pending else 2 if next_task in llm_pending else 3
            logger.info(f"Running next step {step} ({'plan' if step==1 else 'llm' if step==2 else 'commit'}) for task: {next_task['desc']}", extra={'log_color': 'HIGHLIGHT'})
            self._process_one(next_task, svc, self._file_lines, todoFilename=todoFilename, step=step)
            logger.info(f"Completed step {step}", extra={'log_color': 'HIGHLIGHT'})
        except Exception as e:
            logger.exception(f"Error running next task: {e}", extra={'log_color': 'DELTA'})
            if self._ui_callback:
                self._ui_callback(f"❌ Error: {e}")
            traceback.print_exc()

    def _gather_include_knowledge(self, task: dict, svc) -> str:
        logger.info("Gathering include knowledge", extra={'log_color': 'HIGHLIGHT'})
        try:
            inc = task.get('include') or {}
            spec = inc.get('pattern','')
            if not spec:
                logger.debug("No include spec found")
                return ""
            rec = " recursive" if inc.get('recursive') else ""
            full_spec = f"pattern={spec}{rec}"
            try:
                include_list = svc.include_list(full_spec) or ""
                know = svc.combine_knowledge(include_list)
                include_tokens = len(know.split())
                task['_include_tokens'] = include_tokens
                task['include_tokens'] = include_tokens
                logger.info(f"Gathered include knowledge: {include_tokens} tokens from spec '{full_spec}'", extra={'log_color': 'PERCENT'})
                return know
            except Exception as e:
                logger.exception(f"Include failed for spec='{full_spec}': {e}", extra={'log_color': 'DELTA'})
                traceback.print_exc()
                return ""
        except Exception as e:
            logger.exception(f"Error in _gather_include_knowledge: {e}", extra={'log_color': 'DELTA'})
            traceback.print_exc()
            return ""

    def _generate_plan(self, task: dict, svc, base_folder: Optional[Path] = None) -> str:
        """
        Step 1: Generate or update plan.md summarizing the task plan, changes, and next steps.
        Uses a specialized prompt for planning. Enhanced for token efficiency and performance.
        """
        logger.info(f"Generating plan for task: {task['desc']}", extra={'log_color': 'HIGHLIGHT'})
        if self._ui_callback:
            self._ui_callback(f"📋 Generating plan for: {task['desc'][:50]}...")
            
        try:
            plan_spec = task.get('plan') or {'pattern': 'plan.md', 'recursive': True}
            plan_path = self._todo_util._get_plan_out_path({'plan': plan_spec}, base_folder=base_folder)
            if not plan_path:
                plan_path = base_folder / 'plan.md' if base_folder else Path('plan.md')
                logger.info(f"Default plan path: {plan_path}", extra={'log_color': 'HIGHLIGHT'})

            if plan_path.exists():
                logger.info(f"Updating existing plan: {plan_path}", extra={'log_color': 'HIGHLIGHT'})
            else:
                logger.info(f"Creating new plan: {plan_path}", extra={'log_color': 'HIGHLIGHT'})
                self._file_service.write_file(plan_path, "# Plan for task\n\nNext steps:\n- To be generated.")

            task['_plan_path'] = str(plan_path)

            plan_prompt = self._prompt_builder.build_plan_prompt(
                task,
                basedir=str(base_folder) if base_folder else '',
                out_path=str(plan_path),
                knowledge_text=task.get('knowledge', ''),
                include_text=self._gather_include_knowledge(task, svc)
            ) 

            plan_content = svc.ask(plan_prompt)
            if not plan_content.strip():
                logger.warning("No plan content generated", extra={'log_color': 'DELTA'})
                return ""

            self._todo_util._write_plan(self._svc, plan_path=plan_path, content=plan_content)      
            plan_tokens = len(plan_content.split())
            task['plan_tokens'] = plan_tokens
            task['_latest_plan'] = plan_content
            logger.info(f"Plan generated and written: {plan_path}, {plan_tokens} tokens", extra={'log_color': 'PERCENT'})
            return plan_content
        except Exception as e:
            logger.exception(f"Error generating plan: {e}", extra={'log_color': 'DELTA'})
            traceback.print_exc()
            return ""

    def _process_one(self, task: dict, svc, file_lines_map: dict, todoFilename: str = "", step: int = 1):
        logger.info(f"_process_one called with task, todoFilename={todoFilename!r}, step={step}", extra={'log_color': 'HIGHLIGHT'})

        base_folder = None
        if todoFilename:
            try:
                base_folder = Path(todoFilename).parent
                logger.info("Process base folder: " + str(base_folder), extra={'log_color': 'HIGHLIGHT'})  
            except Exception as e:
                logger.exception(f"Could not determine parent folder of {todoFilename}: {e}", extra={'log_color': 'DELTA'})
                traceback.print_exc()
                base_folder = None

        try:
            logger.info(f"Processing task: {task['desc']}", extra={'log_color': 'HIGHLIGHT'})
            basedir = Path(task['file']).parent
            self._base_dir = str(basedir)
            self._file_service.base_dir = str(basedir)
            logger.debug(f"Base dir: {self._base_dir}")
            task['cur_model'] = svc.get_cur_model()
            include_text = self._gather_include_knowledge(task, svc)
            include_files: List[str] = []
            if include_text:
                for line in include_text.splitlines():
                    if line.startswith("# file: "):
                        include_files.append(line[8:].strip())
            task['_include_files'] = include_files
            task['_include_spec'] = task.get('include')
            task['_include_tokens'] = len(include_text.split()) if include_text else 0
            task['include_tokens'] = task.get('include_tokens', task['_include_tokens'])
            task['knowledge_tokens'] = len(task.get('knowledge', '').split())
            knowledge_text = task.get('knowledge') or ""
            task['_know_tokens'] = len(knowledge_text.split())
            task['knowledge_tokens'] = task['_know_tokens']

            plan_flag = task.get('plan_flag', 'x')
            write_flag = task.get('write_flag', 'x')
            status = task.get('status_char', 'x')
            
            if step == 1 or (plan_flag == ' '):
                logger.warning("Step 1: Running planning", extra={'log_color': 'HIGHLIGHT'})
                st = self.start_task(task, file_lines_map, self._svc.get_cur_model(), 1)
                plan_content = self._generate_plan(task, svc, base_folder)
                if plan_content:
                    task['plan_tokens'] = len(plan_content.split())
                    logger.info(f"Plan tokens: {task['plan_tokens']}", extra={'log_color': 'PERCENT'})
                ct = self.complete_task(task, file_lines_map, self._svc.get_cur_model(), 0, None, False, 1)
                task['_start_stamp'] = st
            elif step == 2 or (status == ' '):
                logger.warning("Step 2: Running LLM task using plan.md", extra={'log_color': 'HIGHLIGHT'})
                out_path = self._todo_util._get_ai_out_path(task, base_folder=base_folder)
                task['_out_path'] = str(out_path) if out_path else None
                plan_knowledge = ""
                plan_spec = task.get('plan', {'pattern': 'plan.md', 'recursive': False})
                plan_path = self._todo_util._get_plan_out_path({'plan': plan_spec}, base_folder=base_folder)
                if plan_path and plan_path.exists():
                    plan_content = self._file_service.safe_read_file(plan_path)
                    plan_knowledge = f"Plan from plan.md:\n{plan_content}\n"
                    task['_plan_path'] = str(plan_path)
                    task['_latest_plan'] = plan_content
                    logger.info("Included plan.md in LLM prompt", extra={'log_color': 'HIGHLIGHT'})
                prompt = self._prompt_builder.build_task_prompt(
                    task, self._base_dir, str(out_path), knowledge_text + plan_knowledge, include_text
                )
                task['_prompt_tokens'] = len(prompt.split())
                task['prompt_tokens'] = task['_prompt_tokens']
                logger.debug(f"Prompt tokens: {task['_prompt_tokens']}", extra={'log_color': 'PERCENT'})
                cur_model = svc.get_cur_model()
                task['cur_model'] = cur_model
                st = self.start_task(task, file_lines_map, cur_model, 2)
                task['_start_stamp'] = st
                ai_out = svc.ask(prompt)
                if not ai_out:
                    logger.warning("No AI output generated, retrying once", extra={'log_color': 'DELTA'})
                    ai_out = svc.ask(prompt)
                self._todo_util._write_full_ai_output(svc, task, ai_out, 0, base_folder=base_folder)
                parsed_files = self.parser.parse_llm_output(ai_out, base_dir=str(basedir), file_service=self._file_service, ai_out_path=out_path, task=task, svc=svc) if ai_out else []
                committed, compare = self._todo_util._write_parsed_files(parsed_files, task, False, base_folder=base_folder, current_filename=None)
                task['_pending_files'] = compare or []
                logger.info(f"LLM step: {committed} files parsed (not committed)", extra={'log_color': 'PERCENT'})
                ct = self.complete_task(task, file_lines_map, self._svc.get_cur_model(), 0, compare, True, 2)
                task['_complete_stamp'] = ct
            elif step == 3 or (status == 'x' and write_flag == ' ' and plan_flag == 'x'):
                logger.warning("Step 3: Committing LLM response", extra={'log_color': 'HIGHLIGHT'})
                commit_preview = task.get('_pending_files') or []
                progress_extra = {'files': commit_preview} if commit_preview else None
                st = self.start_task(task, file_lines_map, self._svc.get_cur_model(), 3, progress_extra=progress_extra)
                raw_out = task.get('out')
                out_path = self._todo_util._get_ai_out_path(task, base_folder=base_folder)
                if out_path and out_path.exists():
                    ai_out = self._file_service.safe_read_file(out_path)
                    parsed_files = self.parser.parse_llm_output_commit(ai_out, base_dir=str(basedir), file_service=self._file_service, ai_out_path=out_path, task=task, svc=svc)
                    committed, compare = self._todo_util._write_parsed_files(parsed_files, task, True, base_folder=base_folder, current_filename=None)
                    task['_committed_files'] = compare or []
                    logger.info(f"Commit step: {committed} files committed", extra={'log_color': 'PERCENT'})
                    truncation = 0.0
                    
                else:
                    logger.warning("No out file for commit", extra={'log_color': 'DELTA'})

                ct = self.complete_task(task, file_lines_map, svc.get_cur_model(), 0, compare, True, 3)
                task['_complete_stamp'] = ct
            else:
                logger.info(f"No step to run: status={status}, write={write_flag}, plan={plan_flag}", extra={'log_color': 'DELTA'})

            logger.info(f"Task processed: {task['desc']}", extra={'log_color': 'HIGHLIGHT'})
        except Exception as e:
            logger.exception(f"Error processing task {task['desc']}: {e}", extra={'log_color': 'DELTA'})
            traceback.print_exc()

    def _resolve_path(self, frag: str) -> Optional[Path]:
        logger.info(f"Resolving path: {frag}", extra={'log_color': 'HIGHLIGHT'})
        try:
            srf = self._file_service.resolve_path(frag, self._svc)
            return srf
        except Exception as e:
            logger.exception(f"Error resolving path {frag}: {e}", extra={'log_color': 'DELTA'})
            traceback.print_exc()
            return None