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
from typing import List, Optional, Dict
import statistics  # Added for calculating median, avg, peak

import tiktoken
from pydantic import BaseModel, RootModel
import yaml   # ensure PyYAML is installed
from typing import Any, Tuple
try:
    from .parse_service import ParseService
except ImportError:
    from parse_service import ParseService

logger = logging.getLogger(__name__)

# Updated TASK_RE to capture optional second‐bracket 'write' flag,
# allowing "[x][ ]" or "[x] [ ]" with optional whitespace between brackets
# Enhanced to support third bracket for planning step
TASK_RE = re.compile(
    r'^(\s*)-\s*'                  # indent + "- "
    r'(?:\s*\[(?P<plan>[ x~-])\])?'   # step 1: [plan_flag] for three-step process
    r'\[(?P<status>[ x~])\]'       # step 2: execution [status]
    r'(?:\s*\[(?P<write>[ x~-])\])?'  # optional [write_flag], whitespace allowed

    r'\s*(?P<desc>.+)$'            # space + desc (including potential metadata)
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

    def __init__(self, roots: List[str], svc=None, prompt_builder=None, task_manager=None, task_parser=None, file_watcher=None, file_service=None, exclude_dirs={"node_modules", "dist", "diffout"}):
        logger.info(f"Initializing TodoService with roots: {roots}", extra={'log_color': 'HIGHLIGHT'})
        logger.debug(f"Svc provided: {svc is not None}, Prompt builder: {prompt_builder is not None}")
        try:
            self._roots        = roots
            self._file_lines   = {}
            self._tasks        = []
            self._mtimes       = {}
            self._watch_ignore = {}
            self._svc          = svc
            self.parser        = ParseService()
            self._prompt_builder = prompt_builder
            self._task_manager = task_manager
            self._task_parser = task_parser
            self._file_watcher = file_watcher
            self._file_service = file_service
            self._exclude_dirs = exclude_dirs
            # MVP: parse a `base:` directive from front-matter
            self._base_dir = self._parse_base_dir()
            
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

    def sanitize_desc(self, desc: str) -> str:
        """
        Sanitize description by stripping trailing flag patterns like [ x ], [ - ], etc.
        Called to clean desc after parsing or before rebuilding.
        Enhanced to robustly remove all trailing flag patterns, including multiples, and handle flags before pipes ('|').
        """
        logger.debug(f"Sanitizing desc: {desc[:100]}...")
        # Robust regex to match and strip trailing flags: [ followed by space or symbol, then ], possibly multiple
        # Also handles cases where flags are before a metadata pipe '|'
        flag_pattern = r'\s*\[\s*[x~-]\s*\]\s*(?=\||$)'
        pipe_flag_pattern = r'\s*\[\s*[x~-]\s*\]\s*\|'  # Flags before pipe
        while re.search(flag_pattern, desc) or re.search(pipe_flag_pattern, desc):
            # Remove trailing flags before pipe or end
            desc = re.sub(flag_pattern, '', desc)
            # Remove flags immediately before pipe
            desc = re.sub(pipe_flag_pattern, '|', desc)
            desc = desc.rstrip()  # Clean up whitespace
            logger.debug(f"Stripped trailing/multiple flags, new desc: {desc[:100]}...")
        # Also strip any extra | metadata if desc was contaminated (ensure only one leading desc part)
        if ' | ' in desc:
            desc = desc.split(' | ')[0].strip()  # Take only the first part as desc
            logger.debug(f"Stripped metadata contamination (pre-pipe), clean desc: {desc[:100]}...")
        # Final strip of any lingering bracket patterns at end
        desc = re.sub(r'\s*\[.*?\]\s*$', '', desc).strip()
        logger.debug(f"Final sanitized desc: {desc[:100]}...")
        return desc

    def _parse_task_metadata(self, full_desc: str) -> Dict:
        """
        Parse the task description for metadata like started, completed, knowledge_tokens, etc.
        Returns a dict with parsed values and the clean description.
        Enhanced: Ensure desc is isolated cleanly from flags/metadata before sanitization.
        Strip any flag-like patterns from the end of desc even if followed by ' | metadata'.
        Now parses plan_tokens as well.
        """
        logger.debug(f"Parsing metadata for task desc: {full_desc}")
        try:
            # First, sanitize the full_desc to remove any trailing flags, regardless of pipes
            full_desc = self.sanitize_desc(full_desc)
            logger.debug(f"Sanitized full_desc (flags removed): {full_desc}")
            
            metadata = {
                'desc': full_desc.strip(),
                '_start_stamp': None,
                '_complete_stamp': None,
                'knowledge_tokens': 0,
                'include_tokens': 0,
                'prompt_tokens': 0,
                'plan_tokens': 0,  # Enhanced: Added plan_tokens
            }
            # Split by | to separate desc from metadata, but only after final sanitization
            parts = [p.strip() for p in full_desc.split('|') if p.strip()]
            if len(parts) > 1:
                metadata['desc'] = self.sanitize_desc(parts[0])  # Re-sanitize the desc part post-split
                logger.info(f"Clean desc after metadata split: {metadata['desc']}, metadata parts: {len(parts)-1}", extra={'log_color': 'HIGHLIGHT'})
                # Parse metadata parts (now safe from flag contamination)
                for part in parts[1:]:
                    if ':' in part:
                        key, val = [s.strip() for s in part.split(':', 1)]
                        try:
                            if key == 'started':
                                metadata['_start_stamp'] = val if val.lower() != 'none' else None
                                logger.info(f"Parsed started: {metadata['_start_stamp']}", extra={'log_color': 'HIGHLIGHT'})
                            elif key == 'completed':
                                metadata['_complete_stamp'] = val if val.lower() != 'none' else None
                                logger.info(f"Parsed completed: {metadata['_complete_stamp']}", extra={'log_color': 'HIGHLIGHT'})
                            elif key == 'knowledge':
                                metadata['knowledge_tokens'] = int(val) if val.isdigit() else 0
                                logger.info(f"Parsed knowledge tokens: {metadata['knowledge_tokens']}", extra={'log_color': 'PERCENT'})
                            elif key == 'include':
                                metadata['include_tokens'] = int(val) if val.isdigit() else 0
                                logger.info(f"Parsed include tokens: {metadata['include_tokens']}", extra={'log_color': 'PERCENT'})
                            elif key == 'prompt':
                                metadata['prompt_tokens'] = int(val) if val.isdigit() else 0
                                logger.info(f"Parsed prompt tokens: {metadata['prompt_tokens']}", extra={'log_color': 'PERCENT'})
                            elif key == 'plan':  # Enhanced: Parse plan_tokens
                                metadata['plan_tokens'] = int(val) if val.isdigit() else 0
                                logger.info(f"Parsed plan tokens: {metadata['plan_tokens']}", extra={'log_color': 'PERCENT'})
                        except ValueError:
                            logger.warning(f"Failed to parse metadata part: {part}", extra={'log_color': 'DELTA'})
            # Final validation: Ensure desc has no trailing flags post-parsing
            metadata['desc'] = self.sanitize_desc(metadata['desc'])
            logger.debug(f"Final parsed metadata: {metadata}")
            return metadata
        except Exception as e:
            logger.exception(f"Error parsing task metadata for '{full_desc}': {e}", extra={'log_color': 'DELTA'})
            # Fallback: return sanitized desc with defaults
            return {'desc': self.sanitize_desc(full_desc).strip(), '_start_stamp': None, '_complete_stamp': None, 'knowledge_tokens': 0, 'include_tokens': 0, 'prompt_tokens': 0, 'plan_tokens': 0}

    def _rebuild_task_line(self, task: dict) -> str:
        """
        Safely reconstruct a task line to prevent flag appending issues.
        Enhanced: Always start with a fully sanitized desc, add flags only once, append metadata separately.
        Add validation to prevent flag duplication by stripping any existing flags from desc before adding new ones.
        Now includes plan_tokens in metadata if >0.
        """
        logger.debug(f"Rebuilding task line for: {task['desc'][:50]}...")
        # Sanitize desc first to ensure no trailing flags or duplicates
        clean_desc = self.sanitize_desc(task['desc'])
        task['desc'] = clean_desc  # Update task with sanitized desc
        logger.debug(f"Sanitized desc in rebuild (no existing flags): {clean_desc[:50]}...")
        
        # Build flags string: Ensure single set of flags, no duplicates
        plan_char = task.get('plan_flag', ' ') if task.get('plan_flag') else ' '
        status_char = task.get('status_char', ' ') if task.get('status_char') else ' '
        write_char = task.get('write_flag', ' ') if task.get('write_flag') else ' '
        # Validation: Log if any char is invalid
        if plan_char not in ' x~-':
            logger.warning(f"Invalid plan_flag '{plan_char}' for task, defaulting to ' '", extra={'log_color': 'DELTA'})
            plan_char = ' '
        if status_char not in ' x~-':
            logger.warning(f"Invalid status_char '{status_char}' for task, defaulting to ' '", extra={'log_color': 'DELTA'})
            status_char = ' '
        if write_char not in ' x~-':
            logger.warning(f"Invalid write_flag '{write_char}' for task, defaulting to ' '", extra={'log_color': 'DELTA'})
            write_char = ' '
        
        flags = f"[{plan_char}][{status_char}][{write_char}]"
        line = task['indent'] + "- " + flags + " " + clean_desc
        # Append metadata if present (safely, after sanitized desc). Enhanced: Include plan_tokens
        meta_parts = []
        if task.get('_start_stamp'):
            meta_parts.append(f"started: {task['_start_stamp']}")
        if task.get('_complete_stamp'):
            meta_parts.append(f"completed: {task['_complete_stamp']}")
        if task.get('knowledge_tokens', 0) > 0:
            meta_parts.append(f"knowledge: {task['knowledge_tokens']}")
        if task.get('include_tokens', 0) > 0:
            meta_parts.append(f"include: {task['include_tokens']}")
        if task.get('prompt_tokens', 0) > 0:
            meta_parts.append(f"prompt: {task['prompt_tokens']}")
        if task.get('plan_tokens', 0) > 0:  # Enhanced: Add plan_tokens to metadata
            meta_parts.append(f"plan: {task['plan_tokens']}")
        if meta_parts:
            line += " | " + " | ".join(meta_parts)
        # Final validation: Ensure no duplicate flags in the rebuilt line
        if re.search(r'\[\s*[x~-]\s*\]\s*\[\s*[x~-]\s*\]\s*\[\s*[x~-]\s*\]', line):
            logger.error(f"Potential flag duplication detected in rebuilt line: {line[:200]}...", extra={'log_color': 'DELTA'})
        logger.debug(f"Rebuilt task line (validated, no duplicates): {line[:100]}...")
        return line

    def _parse_base_dir(self) -> Optional[str]:
        logger.info("_parse_base_dir called", extra={'log_color': 'HIGHLIGHT'})
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
            logger.info(f"Found {len(out)} todo files", extra={'log_color': 'HIGHLIGHT'})
            return out
        except Exception as e:
            logger.exception(f"Error finding todo files: {e}", extra={'log_color': 'DELTA'})
            return []

    def _normalize_task_flags(self):
        """
        Make sure every task always has plan_flag, status_char and write_flag set
        to one of ' ', '~', 'x', '-' (never None).
        Now with logging for normalization.
        """
        logger.info("Normalizing task flags", extra={'log_color': 'HIGHLIGHT'})
        changed = 0
        for i, t in enumerate(self._tasks):
            orig_flags = f"P:{t.get('plan_flag')} S:{t.get('status_char')} W:{t.get('write_flag')}"
            # default to ' ' when the regex group was missing
            t['plan_flag']   = t.get('plan_flag')   or ' '
            t['status_char'] = t.get('status_char') or ' '
            t['write_flag']  = t.get('write_flag')  or ' '
            if orig_flags != f"P:{t['plan_flag']} S:{t['status_char']} W:{t['write_flag']}":
                changed += 1
                logger.debug(f"Normalized task {i}: {orig_flags} -> P:{t['plan_flag']} S:{t['status_char']} W:{t['write_flag']}")
        logger.info(f"Normalized {changed} tasks out of {len(self._tasks)}", extra={'log_color': 'PERCENT'})

    def _load_all(self):
        """
        Parse each todo.md into tasks, capturing optional second‐bracket
        write‐flag, third bracket for planning, and any adjacent ```knowledge``` block.
        Also parse metadata from the task line (e.g., | started: ... | knowledge: 0).
        Added logging for task loading.
        Now includes post-parsing sanitization in _load_all. Enhanced to parse plan_tokens from metadata.
        """
        logger.info("_load_all called: Reloading all tasks from files", extra={'log_color': 'HIGHLIGHT'})
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
                    write_flag = m.group('write')  # may be None, ' ', '~', or 'x'
                    plan_flag  = m.group('plan')   # may be None, ' ', '~', or 'x'
                    full_desc  = m.group('desc')
                    # Parse metadata and clean desc
                    metadata = self._parse_task_metadata(full_desc)
                    desc     = metadata.pop('desc')
                    # Additional cleaning for trailing flags in desc to fix appending issue
                    desc = self.sanitize_desc(desc)
                    task     = {
                        'file': fn,
                        'line_no': i,
                        'indent': indent,
                        'plan_flag': plan_flag,  # New field
                        'status_char': status,
                        'write_flag': write_flag,
                        'desc': desc,
                        'include': None,
                        'in': None,
                        'out': None,
                        'plan': None,  # New for plan.md spec
                        'knowledge': '',
                        'knowledge_tokens': 0,
                        'include_tokens': 0,
                        'prompt_tokens': 0,
                        'plan_tokens': 0,  # New
                        '_start_stamp': None,
                        '_know_tokens': 0,
                        '_in_tokens': 0,
                        '_prompt_tokens': 0,
                        '_include_tokens': 0,
                        '_complete_stamp': None,
                    }
                    task.update(metadata)  # Add parsed metadata (tokens, stamps)

                    logger.info(f"Loaded task {task_count}: flags P:{plan_flag} S:{status} W:{write_flag}, desc length {len(desc)} (sanitized)", extra={'log_color': 'HIGHLIGHT'})

                    # scan sub‐entries (include, in, focus, plan)
                    j = i + 1
                    while j < len(lines) and lines[j].startswith(indent + '  '):
                        sub = SUB_RE.match(lines[j])
                        if sub:
                            key = sub.group('key')
                            pat = sub.group('pattern').strip('"').strip('`')
                            rec = bool(sub.group('rec'))
                            if key == 'focus':
                                task['out'] = {'pattern': pat, 'recursive': rec}
                            elif key == 'plan':  # New for plan.md
                                task['plan'] = {'pattern': pat, 'recursive': rec}
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
                        know_tokens = len(''.join(fence).split())
                        task['_know_tokens'] = know_tokens
                        task['knowledge_tokens'] = know_tokens  # Override if metadata had different value
                        logger.info(f"Loaded knowledge for task {task_count}: {know_tokens} tokens", extra={'log_color': 'PERCENT'})
                        j += 1  # skip closing ``` line

                    self._tasks.append(task)
                    task_count += 1
                    total_tasks += 1
                    i = j
                logger.info(f"Loaded {task_count} tasks from {fn}", extra={'log_color': 'PERCENT'})
            # Post-load sanitization for all tasks
            for i, t in enumerate(self._tasks):
                t['desc'] = self.sanitize_desc(t['desc'])
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
        """
        logger.info("_watch_loop started", extra={'log_color': 'HIGHLIGHT'})
        while True:
            try:
                for fn in self._find_files():
                    try:
                        mtime = os.path.getmtime(fn)
                    except OSError:
                        logger.warning(f"File {fn} not found, skipping", extra={'log_color': 'DELTA'})
                        # file might have been deleted
                        continue

                    # 1) ignore our own writes
                    ignore_time = self._watch_ignore.get(fn)
                    if ignore_time and abs(mtime - ignore_time) < 1e-3:
                        self._watch_ignore.pop(fn, None)
                        logger.debug(f"Skipped our own write for {fn}")

                    # 2) external change?
                    elif self._mtimes.get(fn) and mtime > self._mtimes[fn]:
                        logger.info(f"Detected external change in {fn}, reloading tasks", extra={'log_color': 'DELTA'})
                        if not self._svc:
                            logger.warning("Svc not available, skipping change processing", extra={'log_color': 'DELTA'})
                            # nothing to do if service not hooked up
                            continue

                        try:
                            # re‐parse all todo.md files into self._tasks
                            self._load_all()

                            # b) then run the next To Do task, if any remain
                            next_todos = [
                                t for t in self._tasks
                                if t.get('status_char') == ' '
                                or t.get('write_flag')  == ' '
                                or t.get('plan_flag')   == ' '
                            ]
                            if next_todos:
                                logger.info(f"New To Do tasks found ({len(next_todos)}), running next", extra={'log_color': 'HIGHLIGHT'})
                                self.run_next_task(self._svc, fn)

                        except Exception as e:
                            logger.exception(f"Watch loop error processing {fn}: {e}", extra={'log_color': 'DELTA'})
                            traceback.print_exc()

                    # 3) update our stored mtime
                    self._mtimes[fn] = mtime

            except Exception as e:
                logger.exception(f"Error in watch loop: {e}", extra={'log_color': 'DELTA'})
                traceback.print_exc()

            time.sleep(1)

    def start_task(self, task: dict, file_lines_map: dict, cur_model: str, step: float = 1):
        logger.info(f"Starting task: {task['desc']} (model: {cur_model}, step: {step})", extra={'log_color': 'HIGHLIGHT'})
        try:
            # Ensure tokens are populated before calling task_manager, including plan_tokens
            task['knowledge_tokens'] = task.get('knowledge_tokens', task.get('_know_tokens', 0))
            task['include_tokens'] = task.get('include_tokens', task.get('_include_tokens', 0))
            task['prompt_tokens'] = task.get('prompt_tokens', task.get('_prompt_tokens', 0))
            task['plan_tokens'] = task.get('plan_tokens', 0)
            st = self._task_manager.start_task(task, file_lines_map, cur_model, step)
            # Preserve or set stamp if task_manager returns None
            if st is None:
                st = datetime.now().isoformat()
            task['_start_stamp'] = st  # Ensure start stamp is set on task
            # Enhanced logging: Include plan_tokens, knowledge_tokens, include_tokens
            logger.info(f"Task started: plan_tokens={task['plan_tokens']}, knowledge_tokens={task['knowledge_tokens']}, include_tokens={task['include_tokens']}, prompt_tokens={task['prompt_tokens']}", extra={'log_color': 'PERCENT'})
            return st
        except Exception as e:
            logger.exception(f"Error starting task {task['desc']}: {e}", extra={'log_color': 'DELTA'})
            traceback.print_exc()
            st = datetime.now().isoformat()
            task['_start_stamp'] = st
            return st
            
    def complete_task(self, task: dict, file_lines_map: dict, cur_model: str, truncation: float, compare: Optional[List[str]] = None, commit: bool = False, step: float = 1):
        logger.info(f"Completing task: {task['desc']} (model: {cur_model}, commit: {commit}, step: {step})", extra={'log_color': 'HIGHLIGHT'})
        try:
            # Ensure tokens are populated before calling task_manager, including plan_tokens
            task['knowledge_tokens'] = task.get('knowledge_tokens', task.get('_know_tokens', 0))
            task['include_tokens'] = task.get('include_tokens', task.get('_include_tokens', 0))
            task['prompt_tokens'] = task.get('prompt_tokens', task.get('_prompt_tokens', 0))
            task['plan_tokens'] = task.get('plan_tokens', 0)
            # Use rebuilt line for safe update (with sanitized desc and single flags)
            rebuilt_line = self._rebuild_task_line(task)
            # Force full line rewrite by updating the file with the rebuilt line
            # This overwrites any accumulated flags from previous appends
            fn = task['file']
            line_no = task['line_no']
            lines = file_lines_map.get(fn, [])
            if 0 <= line_no < len(lines):
                lines[line_no] = rebuilt_line + '\n'  # Overwrite the entire line
                file_lines_map[fn] = lines
                # Write back to file immediately to prevent accumulation
                self._file_service.write_file(Path(fn), ''.join(lines))
                logger.info(f"Forced full line rewrite for task at line {line_no} in {fn} to prevent flag appending", extra={'log_color': 'HIGHLIGHT'})
            # Now proceed with task_manager.complete_task
            ct = self._task_manager.complete_task(task, file_lines_map, cur_model, 0, compare, commit, step)
            # Preserve or set stamp if task_manager returns None
            if ct is None:
                ct = datetime.now().isoformat()
            task['_complete_stamp'] = ct  # Ensure complete stamp is set on task
            # Enhanced logging: Include plan_tokens, knowledge_tokens, include_tokens
            logger.info(f"Task completed: plan_tokens={task['plan_tokens']}, knowledge_tokens={task['knowledge_tokens']}, include_tokens={task['include_tokens']}, prompt_tokens={task['prompt_tokens']}", extra={'log_color': 'PERCENT'})
            return ct
        except Exception as e:
            logger.exception(f"Error completing task {task['desc']}: {e}", extra={'log_color': 'DELTA'})
            traceback.print_exc()
            ct = datetime.now().isoformat()
            task['_complete_stamp'] = ct
            return ct
            
    def run_next_task(self, svc, todoFilename: str = ""):
        logger.info("run_next_task called", extra={'log_color': 'HIGHLIGHT'})
        try:
            self._svc = svc
            self._load_all()
            self._normalize_task_flags()

            # Find next task based on flags for three-step process
            # Priority: plan_flag ' ' first, then write_flag ' ' (LLM), then status ' ' with flags 'x' for commit
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
                return
            next_task = todo[0]
            step = 'plan' if next_task in plan_pending else 'llm' if next_task in llm_pending else 'commit'
            logger.info(f"Running next {step} step for task: {next_task['desc']}", extra={'log_color': 'HIGHLIGHT'})
            self._process_one(next_task, svc, self._file_lines, todoFilename=todoFilename)
            logger.info(f"Completed {step} step", extra={'log_color': 'HIGHLIGHT'})
        except Exception as e:
            logger.exception(f"Error running next task: {e}", extra={'log_color': 'DELTA'})
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
                know = svc.include(full_spec) or ""
                include_tokens = len(know.split())
                task['_include_tokens'] = include_tokens
                task['include_tokens'] = include_tokens  # Update task
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

    # New method for planning step: generate/update plan.md
    def _generate_plan(self, task: dict, svc, base_folder: Optional[Path] = None) -> str:
        """
        Step 1: Generate or update plan.md summarizing the task plan, changes, and next steps.
        Uses a specialized prompt for planning. Enhanced for token efficiency and performance.
        """
        logger.info(f"Generating plan for task: {task['desc']}", extra={'log_color': 'HIGHLIGHT'})
        try:
            # Determine plan path
            plan_spec = task.get('plan') or {'pattern': 'plan.md', 'recursive': True}
            plan_path = self._get_plan_out_path({'plan': plan_spec}, base_folder=base_folder)
            if not plan_path:
                plan_path = base_folder / 'plan.md' if base_folder else Path('plan.md')
                logger.info(f"Default plan path: {plan_path}", extra={'log_color': 'HIGHLIGHT'})

            logger.info(f"Plan plan_path:{plan_path} base_folder:{base_folder}", extra={'log_color': 'HIGHLIGHT'})
            self._write_plan(self._svc, plan_path=plan_path,  content='')

            # Build planning prompt (enhanced for performance: concise, token-aware)
            plan_prompt = self._prompt_builder.build_plan_prompt(
                task,
                basedir=str(base_folder) if base_folder else '',
                out_path=str(plan_path),
                knowledge_text=task.get('knowledge', ''),
                include_text=self._gather_include_knowledge(task, svc)
            ) 

            # Generate plan (use shorter max_tokens for efficiency if possible)
            plan_content = svc.ask(plan_prompt)
            if not plan_content:
                logger.warning("No plan content generated", extra={'log_color': 'DELTA'})
                return ""

            self._write_plan(self._svc, plan_path=plan_path, content=plan_content)      
            plan_tokens = len(plan_content.split())
            task['plan_tokens'] = plan_tokens
            logger.info(f"Plan generated and committed: {plan_path} files, {plan_tokens} tokens (efficient plan for task performance)", extra={'log_color': 'PERCENT'})
            return plan_content
        except Exception as e:
            logger.exception(f"Error generating plan: {e}", extra={'log_color': 'DELTA'})
            traceback.print_exc()
            return ""

    # --- modified write-and-report method ---
    def _write_parsed_files(self, parsed_files: List[dict], task: dict = None, commit_file: bool= False, base_folder: str = "", current_filename: str = None) -> tuple[int, List[str]]:
        """
        Write parsed files and compare tokens using parse_service object properties, return results and compare list
        For NEW files, resolve path relative to todo.md folder (base_dir) and create full path.
        For DELETE files, delete the matched file if it exists; prioritize DELETE over NEW even if both flags are set.
        matchedfilename remains relative for reporting.
        Enhanced logging for UPDATEs: full compare details with percentage deltas (median, avg, peak line/token changes).
        Added logging for planning step files. Now includes plan_tokens in token logging.
        Now sanitizes desc in logging to avoid flag contamination in logs.
        """
        logger.info("_write_parsed_files base folder: " + str(base_folder), extra={'log_color': 'HIGHLIGHT'})
        try:
            result = 0
            compare: List[str] = []
            basedir = Path(task['file']).parent if task else Path.cwd()
            self._file_service.base_dir = str(basedir)  # Set base_dir for relative path resolution
            update_deltas = []  # Collect deltas for UPDATE logging
            update_abs_deltas = []  # Collect absolute deltas for UPDATE logging
            plan_files_written = 0  # New counter for plan files

            for parsed in parsed_files:
                try:
                    filename = parsed.get('filename', '')
                    if current_filename == None or filename == current_filename:
                        content = parsed['content']
                        # completeness check
                        filename = parsed.get('filename', '')
                        originalfilename = parsed.get('originalfilename', filename)
                        matchedfilename = parsed.get('matchedfilename', filename)  # Relative path for NEW files
                        relative_path = parsed.get('relative_path', filename)
                        is_new = parsed.get('new', False)
                        is_delete = parsed.get('delete', False)
                        is_copy = parsed.get('copy', False)
                        is_update = parsed.get('update', False)
                        if filename == 'plan.md':  # Special handling for plan.md
                            plan_files_written += 1
                            logger.info(f"Writing plan file: {relative_path} (new: {is_new}, update: {is_update})", extra={'log_color': 'HIGHLIGHT'})
                        if not is_new and not is_copy and not is_delete and not is_update:
                            is_update = True
                        new_path = None
                        orig_content = parsed.get('original_content', '')  # Assume parsed has original for diff calc
                        orig_tokens = len(orig_content.split()) if orig_content else 0
                        new_tokens = len(content.split()) if content else 0
                        abs_delta = new_tokens - orig_tokens  # Absolute delta token count
                        token_delta = ((new_tokens - orig_tokens) / orig_tokens * 100) if orig_tokens > 0 else 100.0 if new_tokens > 0 else 0.0

                        # Determine action
                        action = 'NEW' if is_new else 'UPDATE' if is_update else 'DELETE' if is_delete else 'COPY' if is_copy else 'UNCHANGED'

                        # Per-file logging in the specified format (sanitize relative_path if needed). Enhanced: Include plan_tokens if available
                        clean_relative = self.sanitize_desc(relative_path)
                        plan_t = task.get('plan_tokens', 0) if task else 0
                        logger.info(f"Write {action} {clean_relative}: (plan/k/i/p/o/u/d/p {plan_t}/{task.get('knowledge_tokens',0)}/{task.get('include_tokens',0)}/{task.get('prompt_tokens',0)}/{orig_tokens}/{new_tokens}/{abs_delta}/{token_delta:.1f}%) commit:{str(commit_file)}", extra={'log_color': 'PERCENT'})

                        # Enhanced logging including originalfilename and matchedfilename
                        logger.debug(f"  - originalfilename: {originalfilename}")
                        logger.debug(f"  - matchedfilename: {matchedfilename}")
                        logger.debug(f"  - relative_path: {relative_path}")
                        # Prioritize DELETE: delete if flagged, regardless of other flags
                        if commit_file:
                            if is_delete:
                                logger.info(f"Delete file: {matchedfilename}", extra={'log_color': 'DELTA'})
                                delete_path = Path(matchedfilename) if matchedfilename else None
                                if commit_file and delete_path and delete_path.exists():
                                    self._file_service.delete_file(delete_path)
                                    logger.info(f"Deleted file: {delete_path} (matched: {matchedfilename})", extra={'log_color': 'DELTA'})
                                    result += 1
                                elif not delete_path:
                                    logger.warning(f"No matched path for DELETE: {filename}", extra={'log_color': 'DELTA'})
                                else:
                                    logger.info(f"DELETE file not found: {delete_path}", extra={'log_color': 'DELTA'})
                                compare.append(f"{parsed.get('short_compare', '')} (DELETE) -> {matchedfilename}")
                                continue  # No further action for deletes


                            if is_copy:
                                # For COPY: resolve source and destination, copy file
                                src_path = Path(matchedfilename)  # Assume matched is source
                                dst_path = self._file_service.resolve_path(relative_path, self._svc)  # Destination relative
                                if src_path.exists():
                                    self._file_service.copy_file(src_path, dst_path)
                                    logger.info(f"Copied file: {src_path} -> {dst_path} (relative: {relative_path})", extra={'log_color': 'HIGHLIGHT'})
                                    result += 1
                                else:
                                    logger.warning(f"Source for COPY not found: {src_path}", extra={'log_color': 'DELTA'})
                            elif is_new:
                                # For NEW, resolve relative to base_dir
                                # create the new file under the todo.md folder + relative_path
                                new_path = basedir / relative_path
                                self._file_service.write_file(new_path, content)
                                logger.info(f"Created NEW file at: {new_path} (relative: {relative_path})", extra={'log_color': 'HIGHLIGHT'})
                                result += 1
                                
                            elif is_update:
                                # For UPDATE, use matched path
                                new_path = Path(matchedfilename)
                                if new_path.exists():
                                    self._file_service.write_file(new_path, content)
                                    logger.info(f"Updated file: {new_path} (matched: {matchedfilename})", extra={'log_color': 'HIGHLIGHT'})
                                    # Enhanced UPDATE logging: calculate and log deltas
                                    update_deltas.append(token_delta)
                                    update_abs_deltas.append(abs_delta)
                                    clean_rel = self.sanitize_desc(relative_path)
                                    plan_t = task.get('plan_tokens', 0) if task else 0
                                    logger.info(f"Updated for {filename} {clean_rel}: (plan/k/i/p/o/u/d/p {plan_t}/{task.get('knowledge_tokens',0)}/{task.get('include_tokens',0)}/{task.get('prompt_tokens',0)}/{orig_tokens}/{new_tokens}/{abs_delta}/{token_delta:.1f}%)", extra={'log_color': 'PERCENT'})
                                    result += 1
                                else:
                                    logger.warning(f"Path for UPDATE not found: {new_path}", extra={'log_color': 'DELTA'})
                            else:
                                logger.warning(f"Unknown action for {filename}: new={is_new}, update={is_update}, delete={is_delete}, copy={is_copy}", extra={'log_color': 'DELTA'})

                        short_compare = parsed.get('short_compare', '')
                        if is_delete:
                            compare.append(f"DELETE {matchedfilename} {short_compare} ")
                        elif is_copy:
                            compare.append(f"COPY {matchedfilename} {short_compare}")
                        elif is_new:
                            compare.append(f"NEW {matchedfilename} {short_compare}")
                        elif is_update:
                            compare.append(f"UPDATE {matchedfilename} {short_compare} ")
                        else:
                            compare.append(short_compare)
                except Exception as e:
                    logger.exception(f"Error processing parsed file {parsed.get('filename', 'unknown')}: {e}", extra={'log_color': 'DELTA'})
                    traceback.print_exc()
                    continue
            # Enhanced UPDATE summary logging if any updates occurred
            if update_deltas:
                median_delta = statistics.median(update_deltas)
                avg_delta = statistics.mean(update_deltas)
                peak_delta = max(update_deltas)
                logger.info(f"UPDATE summary: median {median_delta:.1f}%, avg {avg_delta:.1f}%, peak {peak_delta:.1f}% across {len(update_deltas)} files", extra={'log_color': 'HIGHLIGHT'})
            logger.info(f"Plan files written: {plan_files_written}", extra={'log_color': 'PERCENT'})
        except Exception as e:
            logger.exception(f"Error in _write_parsed_files: {e}", extra={'log_color': 'DELTA'})
            traceback.print_exc()


        return result, compare

    def _write_plan(self, svc, plan_path: Path, content: str):
        if not plan_path:
            return
        try:
            self._file_service.write_file(plan_path, content)
            logger.info(f"Wrote plan to: {plan_path}", extra={'log_color': 'HIGHLIGHT'})
        except Exception as e:
            logger.exception(f"Failed to backup and write plan to {plan_path}: {e}", extra={'log_color': 'DELTA'})
            traceback.print_exc()

    def _backup_and_write_output(self, svc, out_path: Path, content: str):
        if not out_path:
            return
        try:
            self._file_service.write_file(out_path, content)
            logger.info(f"Backed up and wrote output to: {out_path}", extra={'log_color': 'HIGHLIGHT'})
        except Exception as e:
            logger.exception(f"Failed to backup and write output to {out_path}: {e}", extra={'log_color': 'DELTA'})
            traceback.print_exc()
        
    def _write_full_ai_output(self, svc, task, ai_out, trunc_code, base_folder: str="" ):
        try:
            out_path = self._get_ai_out_path(task, base_folder=base_folder)
            logger.info(f"Write AI out: {out_path} ({len(ai_out.split())} tokens)", extra={'log_color': 'HIGHLIGHT'})
            if out_path:
                self._backup_and_write_output(svc, out_path, ai_out)
        except Exception as e:
            logger.exception(f"Error writing full AI output: {e}", extra={'log_color': 'DELTA'})
            traceback.print_exc()
    

    def _get_ai_out_path(self, task, base_folder: str = ""):
        # figure out where the AI output file actually lives
        raw_out = task.get('out')
        out_path = None

        # case 1: user supplied a literal string path
        if isinstance(raw_out, str) and raw_out.strip():
            p = Path(raw_out)
            if not p.is_absolute() and base_folder:
                p = base_folder / p
            out_path = p

        # case 2: user supplied a dict { pattern, recursive }
        elif isinstance(raw_out, dict):
            pattern = raw_out.get('pattern', "")
            # first try resolving via the FileService (e.g. glob in roots)
            try:
                cand = self._file_service.resolve_path(pattern, self._svc)
            except Exception as e:
                logger.exception(f"Error resolving pattern {pattern}: {e}", extra={'log_color': 'DELTA'})
                cand = None
            if cand:
                out_path = cand
            else:
                # fallback: treat it as a literal under the same folder
                if base_folder and pattern:
                    out_path = base_folder / pattern

        return out_path
    
    def _get_plan_out_path(self, task, base_folder: str = ""):
        # figure out where the AI output file actually lives
        raw_out = task.get('plan')
        out_path = None

        # case 1: user supplied a literal string path
        if isinstance(raw_out, str) and raw_out.strip():
            p = Path(raw_out)
            if not p.is_absolute() and base_folder:
                p = base_folder / p
            out_path = p

        # case 2: user supplied a dict { pattern, recursive }
        elif isinstance(raw_out, dict):
            pattern = raw_out.get('pattern', "")
            # first try resolving via the FileService (e.g. glob in roots)
            try:
                cand = self._file_service.resolve_path(pattern, self._svc)
            except Exception as e:
                logger.exception(f"Error resolving plan pattern {pattern}: {e}", extra={'log_color': 'DELTA'})
                cand = None
            if cand:
                out_path = cand
            else:
                # fallback: treat it as a literal under the same folder
                if base_folder and pattern:
                    out_path = base_folder / pattern

        return out_path

    def _process_one(self, task: dict, svc, file_lines_map: dict, todoFilename: str = ""):
        logger.info(f"_process_one called with task, todoFilename={todoFilename!r}", extra={'log_color': 'HIGHLIGHT'})

        # derive the folder containing the todo.md that was edited
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
            self._file_service.base_dir = str(basedir)  # Set base_dir for relative resolutions
            logger.debug(f"Base dir: {self._base_dir}")
            include_text = self._gather_include_knowledge(task, svc)
            task['_include_tokens'] = len(include_text.split())
            task['include_tokens'] = task['_include_tokens']
            logger.info(f"Include tokens: {task['_include_tokens']}", extra={'log_color': 'PERCENT'})
            knowledge_text = task.get('knowledge') or ""
            task['_know_tokens'] = len(knowledge_text.split())
            task['knowledge_tokens'] = task['_know_tokens']
            logger.info(f"Knowledge tokens: {task['_know_tokens']}", extra={'log_color': 'PERCENT'})

            # Determine which step to run based on flags
            plan_flag = task.get('plan_flag', 'x')
            write_flag = task.get('write_flag', 'x')
            status = task.get('status_char', 'x')
            logger.warning(f'Runnig next task plan:[{plan_flag}] execution status:[{status}] commit:[{write_flag}]', extra={'log_color': 'DELTA'})
            if plan_flag == ' ':
                # Step 1: Planning
                logger.warning("Step 1: Running planning", extra={'log_color': 'HIGHLIGHT'})
                st = self.start_task(task, file_lines_map, self._svc.get_cur_model(), 1)
                plan_content = self._generate_plan(task, svc, base_folder)
                if plan_content:
                    task['plan_tokens'] = len(plan_content.split())
                    logger.info(f"Plan tokens: {task['plan_tokens']}", extra={'log_color': 'PERCENT'})
                
                ct = self.complete_task(task, file_lines_map, self._svc.get_cur_model(), 0, None, False, 1)
                task['_start_stamp'] = st
            elif status == ' ':
                # Step 2: LLM Task (after planning)
                logger.warning("Step 2: Running LLM task using plan.md", extra={'log_color': 'HIGHLIGHT'})
                out_path = self._get_ai_out_path(task, base_folder=base_folder)
                # Include plan.md in knowledge for step 2
                plan_knowledge = ""
                plan_spec = task.get('plan', {'pattern': 'plan.md', 'recursive': False})
                plan_path = self._get_plan_out_path({'plan': plan_spec}, base_folder=base_folder)
                if plan_path and plan_path.exists():
                    plan_content = self._file_service.safe_read_file(plan_path)
                    plan_knowledge = f"Plan from plan.md:\n{plan_content}\n"
                    logger.info("Included plan.md in LLM prompt", extra={'log_color': 'HIGHLIGHT'})
                prompt = self._prompt_builder.build_task_prompt(
                    task, self._base_dir, str(out_path), knowledge_text + plan_knowledge, include_text
                )
                task['_prompt_tokens'] = len(prompt.split())
                task['prompt_tokens'] = task['_prompt_tokens']
                logger.info(f"Prompt tokens: {task['_prompt_tokens']}", extra={'log_color': 'PERCENT'})
                cur_model = svc.get_cur_model()
                task['cur_model'] = cur_model
                st = self.start_task(task, file_lines_map, cur_model, 2)
                task['_start_stamp'] = st
                ai_out = svc.ask(prompt)
                if not ai_out:
                    logger.warning("No AI output generated, retrying once", extra={'log_color': 'DELTA'})
                    ai_out = svc.ask(prompt)
                self._write_full_ai_output(svc, task, ai_out, 0, base_folder=base_folder)
                # Parse but do not commit yet
                parsed_files = self.parser.parse_llm_output(ai_out, base_dir=str(basedir), file_service=self._file_service, ai_out_path=out_path, task=task, svc=svc) if ai_out else []
                committed, compare = self._write_parsed_files(parsed_files, task, False, base_folder=base_folder, current_filename=None)
                logger.info(f"LLM step: {committed} files parsed (not committed)", extra={'log_color': 'PERCENT'})
                ct = self.complete_task(task, file_lines_map, self._svc.get_cur_model(), 0, compare, True, 2)
                task['_complete_stamp'] = ct
            elif status == 'x' and write_flag == ' ' and plan_flag == 'x':
                # Step 3: Commit
                logger.warning("Step 3: Committing LLM response", extra={'log_color': 'HIGHLIGHT'})
                st = self.start_task(task, file_lines_map, self._svc.get_cur_model(), 3)
                raw_out = task.get('out')
                out_path = self._get_ai_out_path(task, base_folder=base_folder)
                if out_path and out_path.exists():
                    ai_out = self._file_service.safe_read_file(out_path)
                    parsed_files = self.parser.parse_llm_output_commit(ai_out, base_dir=str(basedir), file_service=self._file_service, ai_out_path=out_path, task=task, svc=svc)
                    committed, compare = self._write_parsed_files(parsed_files, task, True, base_folder=base_folder, current_filename=None)
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

    # ----------------------------------------------------------------
    # 1) drop-in search_files()
    # ----------------------------------------------------------------
    def search_files(self, pattern: str, recursive: bool = False) -> List[str]:
        """
        Find files matching `pattern` under cwd (or self.root_dir if you have one).
        Added logging for search results.
        """