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

# Updated TASK_RE to robustly capture flags without including them in desc group
# Now ensures desc starts after all captured flags, avoiding leakage of trailing flags/metadata into desc
TASK_RE = re.compile(
    r'^(\s*)-\s*'                  # indent + "- "
    r'(?:\s*\[(?P<plan>[ x~-])\])?'   # optional [plan_flag]
    r'\s*\[(?P<status>[ x~])\]'     # execution [status] - required
    r'(?:\s*\[(?P<write>[ x~-])\])?' # optional [write_flag]
    r'\s*(?P<desc>.*)$'             # desc: everything after flags, including metadata
    # Note: No $ anchor to allow desc to be flexible, but we'll sanitize it later
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

    def __init__(self, roots: List[str], svc=None, prompt_builder=None, task_manager=None, task_parser=None, file_watcher=None, file_service=None, exclude_dirs={"node_modules", "dist", "diffout"}, todo_util=None):
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
            logger.debug(f"Found {len(out)} todo files", extra={'log_color': 'HIGHLIGHT'})
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
        Now includes immediate sanitization of full_desc after extraction to clean trailing flags before metadata parsing.
        Enhanced to parse plan_tokens from metadata.
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
                    # Extract raw full_desc, then immediately sanitize to remove any trailing flags before metadata parsing
                    full_desc  = m.group('desc')
                    full_desc = self._todo_util.sanitize_desc(full_desc)  # Sanitize immediately after extraction
                    logger.debug(f"Raw full_desc after immediate sanitization: {full_desc[:100]}...")
                    
                    # Now parse metadata from the sanitized full_desc
                    metadata = self._todo_util._parse_task_metadata(full_desc)
                    desc     = metadata.pop('desc')
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
            # Post-load sanitization for all tasks (additional safety)
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
            rebuilt_line = self._todo_util._rebuild_task_line(task)
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
            plan_path = self._todo_util._get_plan_out_path({'plan': plan_spec}, base_folder=base_folder)
            if not plan_path:
                plan_path = base_folder / 'plan.md' if base_folder else Path('plan.md')
                logger.info(f"Default plan path: {plan_path}", extra={'log_color': 'HIGHLIGHT'})

            # Ensure plan.md exists for update (or create empty for NEW)
            if plan_path.exists():
                logger.info(f"Updating existing plan: {plan_path}", extra={'log_color': 'HIGHLIGHT'})
                # For UPDATE, but we'll generate new content anyway
            else:
                logger.info(f"Creating new plan: {plan_path}", extra={'log_color': 'HIGHLIGHT'})
                # Create empty file
                self._file_service.write_file(plan_path, "# Plan for task\n\nNext steps:\n- To be generated.")

            logger.info(f"Plan path resolved: {plan_path}, base folder: {base_folder}", extra={'log_color': 'HIGHLIGHT'})
            

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
            if not plan_content.strip():
                logger.warning("No plan content generated", extra={'log_color': 'DELTA'})
                return ""

            # Write the new plan content
            self._todo_util._write_plan(self._svc, plan_path=plan_path, content=plan_content)      
            plan_tokens = len(plan_content.split())
            task['plan_tokens'] = plan_tokens
            logger.info(f"Plan generated and written: {plan_path}, {plan_tokens} tokens", extra={'log_color': 'PERCENT'})
            return plan_content
        except Exception as e:
            logger.exception(f"Error generating plan: {e}", extra={'log_color': 'DELTA'})
            traceback.print_exc()
            return ""


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
            logger.warning(f'Running next task plan:[{plan_flag}] execution status:[{status}] commit:[{write_flag}]', extra={'log_color': 'DELTA'})
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
                out_path = self._todo_util._get_ai_out_path(task, base_folder=base_folder)
                # Include plan.md in knowledge for step 2
                plan_knowledge = ""
                plan_spec = task.get('plan', {'pattern': 'plan.md', 'recursive': False})
                plan_path = self._todo_util._get_plan_out_path({'plan': plan_spec}, base_folder=base_folder)
                if plan_path and plan_path.exists():
                    plan_content = self._file_service.safe_read_file(plan_path)
                    plan_knowledge = f"Plan from plan.md:\n{plan_content}\n"
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
                # Parse but do not commit yet
                parsed_files = self.parser.parse_llm_output(ai_out, base_dir=str(basedir), file_service=self._file_service, ai_out_path=out_path, task=task, svc=svc) if ai_out else []
                committed, compare = self._todo_util._write_parsed_files(parsed_files, task, False, base_folder=base_folder, current_filename=None)
                logger.info(f"LLM step: {committed} files parsed (not committed)", extra={'log_color': 'PERCENT'})
                ct = self.complete_task(task, file_lines_map, self._svc.get_cur_model(), 0, compare, True, 2)
                task['_complete_stamp'] = ct
            elif status == 'x' and write_flag == ' ' and plan_flag == 'x':
                # Step 3: Commit
                logger.warning("Step 3: Committing LLM response", extra={'log_color': 'HIGHLIGHT'})
                st = self.start_task(task, file_lines_map, self._svc.get_cur_model(), 3)
                raw_out = task.get('out')
                out_path = self._todo_util._get_ai_out_path(task, base_folder=base_folder)
                if out_path and out_path.exists():
                    ai_out = self._file_service.safe_read_file(out_path)
                    parsed_files = self.parser.parse_llm_output_commit(ai_out, base_dir=str(basedir), file_service=self._file_service, ai_out_path=out_path, task=task, svc=svc)
                    committed, compare = self._todo_util._write_parsed_files(parsed_files, task, True, base_folder=base_folder, current_filename=None)
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



# original file length: 456 lines
# updated file length: 465 lines (updated TASK_RE, _load_all to sanitize full_desc immediately, and added post-load sanitization)