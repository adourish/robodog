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


    def _emit_progress_update(self, task: dict, stage: object, phase: str, extra: Optional[Dict[str, object]] = None) -> None:
        """Emit a multi-line progress update with contextual details."""
        message = self._task_manager.get_progress_update(task, stage, phase, extra)
        self._ui_callback(message)
 
    def _load_all(self):
        """
        Delegate all file-reading + task-parsing to TaskParser.
        """
        logger.debug("TodoService._load_all called", extra={'log_color': 'HIGHLIGHT'})
        try:
            # find files under roots
            files = self._find_files()
            # parser.load_all returns (file_lines_map, tasks_list)
            file_lines_map, tasks_list = self._task_parser.load_all(files, self._file_service)

            # swap in new
            self._file_lines = file_lines_map
            self._tasks      = tasks_list

            logger.info(f"Loaded {len(tasks_list)} tasks across {len(files)} files",
                        extra={'log_color': 'PERCENT'})
        except Exception as e:
            logger.exception("Error in TodoService._load_all: %s", e,
                             extra={'log_color': 'DELTA'})
            
    def _parse_base_dir(self) -> Optional[str]:
        logger.debug("_parse_base_dir called", extra={'log_color': 'HIGHLIGHT'})
        return self._svc._parse_base_dir()

    def _find_files(self) -> List[str]:
        logger.debug("_find_files called")
        try:
            out = []
            for r in self._roots:
                for dp, _, fns in os.walk(r):
                    if self._svc.get_todo_filename() in fns:
                        out.append(os.path.join(dp, self._svc.get_todo_filename()))
            logger.debug(f"Found {len(out)} todo files", extra={'log_color': 'HIGHLIGHT'})
            return out
        except Exception as e:
            logger.exception(f"Error finding todo files: {e}", extra={'log_color': 'DELTA'})
            return []

    def _watch_loop(self):
        """
        Watch all todo.md files under self._roots.
        On external change, re‐parse tasks, re‐emit any manually Done tasks
        with commit=' ' and then run the next To Do.
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
                                if t.get('llm') == ' '
                                or t.get('commit')  == ' '
                                or t.get('plan')   == ' '
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
            # Enhanced: Sanitize desc before any flag updates to ensure clean state
            task['desc'] = self._todo_util.sanitize_desc(task['desc'])
            if step == 1:
                task['plan'] = '~'
                logger.info(f"Set plan to ~ for task: {task['desc']}", extra={'log_color': 'HIGHLIGHT'})
            elif step == 2:
                task['llm'] = '~'
                logger.info(f"Set llm to ~ for task: {task['desc']}", extra={'log_color': 'HIGHLIGHT'})
            elif step == 3:
                task['commit'] = '~'
                logger.info(f"Set commit to ~ for task: {task['desc']}", extra={'log_color': 'HIGHLIGHT'})
            # Enhanced: Re-sanitize desc after flag update
            task['desc'] = self._todo_util.sanitize_desc(task['desc'])
            rebuilt_line = self._todo_util._rebuild_task_line(task)
            logger.debug(f"Rebuilt line after start: {rebuilt_line[:200]}...", extra={'log_color': 'HIGHLIGHT'})  # Log for verification
            fn = task['file']
            line_no = task['line_no']
            lines = file_lines_map.get(fn, [])
            if 0 <= line_no < len(lines):
                lines[line_no] = rebuilt_line + '\n'
                file_lines_map[fn] = lines
                self._file_service.write_file(Path(fn), ''.join(lines))
                logger.info(f"Immediately updated flags in todo.md for task at line {line_no} in {fn}: plan={task['plan']}, status={task['llm']}, write={task['commit']}", extra={'log_color': 'HIGHLIGHT'})
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
            # Enhanced: Sanitize desc before any flag updates to ensure clean state
            task['desc'] = self._todo_util.sanitize_desc(task['desc'])
            if step == 1:
                task['plan'] = 'x'
                logger.info(f"Set plan to x for task: {task['desc']}", extra={'log_color': 'HIGHLIGHT'})
            elif step == 2:
                task['llm'] = 'x'
                logger.info(f"Set llm to x for task: {task['desc']}", extra={'log_color': 'HIGHLIGHT'})
            elif step == 3:
                task['commit'] = 'x'
                logger.info(f"Set commit to x for task: {task['desc']}", extra={'log_color': 'HIGHLIGHT'})
            # Enhanced: Re-sanitize desc after flag update
            task['desc'] = self._todo_util.sanitize_desc(task['desc'])
            rebuilt_line = self._todo_util._rebuild_task_line(task)
            logger.debug(f"Rebuilt line after complete: {rebuilt_line[:200]}...", extra={'log_color': 'HIGHLIGHT'})  # Log for verification
            fn = task['file']
            line_no = task['line_no']
            lines = file_lines_map.get(fn, [])
            if 0 <= line_no < len(lines):
                lines[line_no] = rebuilt_line + '\n'
                file_lines_map[fn] = lines
                self._file_service.write_file(Path(fn), ''.join(lines))
                logger.info(f"Updated flags in todo.md for task at line {line_no} in {fn}: plan={task['plan']}, status={task['llm']}, write={task['commit']}", extra={'log_color': 'HIGHLIGHT'})
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

            plan_pending   = [t for t in self._tasks if t['plan']   == ' ']
            llm_pending    = [t for t in self._tasks
                              if t['plan']   != ' '
                             and t['llm'] == ' ']
            commit_pending = [t for t in self._tasks
                              if t['plan']   != ' '
                             and t['llm'] != ' '
                             and t['commit'] == ' ']
            
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

    def _gather_include_knowledge(self, task: dict, svc) -> Tuple[str, str]:
        """
        Returns a tuple (know, know_files):
         - know       = full '# file: …<content>' blocks
         - know_files = bullet list of filenames only
        """
        logger.info("Gathering include knowledge", extra={'log_color': 'HIGHLIGHT'})
        inc = task.get('include') or {}
        spec = inc.get('pattern','')
        if not spec:
            return "", ""
        rec = " recursive" if inc.get('recursive') else ""
        full_spec = f"pattern={spec}{rec}"
        include_list = svc.include_list(full_spec) or []
        know       = svc.combine_knowledge(include_list)
        inclide_filenames = svc.combine_knowledge_filenames(include_list)
        # record token counts if you like...
        return know, inclide_filenames

    def _generate_plan(self, task: dict, svc, base_folder: Optional[Path] = None) -> str:
        """
        Step 1: Generate or update plan.md summarizing the task plan, changes, and next steps.
        """
        logger.info(f"Generating plan for task: {task['desc']}", extra={'log_color': 'HIGHLIGHT'})
        if self._ui_callback:
            self._ui_callback(f"📋 Generating plan for: {task['desc'][:50]}…")

        # >> THIS WAS WRONG: plan_spec = task.get('plan')  # <-- this is just ' ' or '~'
        #    IT MUST BE:
        plan_spec = task.get('plan_spec') or {'pattern': 'plan.md', 'recursive': True}

        # now resolve the actual file path
        plan_path = self._todo_util._get_plan_out_path(plan_spec, base_folder=base_folder)
        if not plan_path:
            plan_path = (base_folder / 'plan.md') if base_folder else Path('plan.md')
            logger.info(f"Default plan path: {plan_path}", extra={'log_color': 'HIGHLIGHT'})

        # touch or initialize plan.md if missing
        if not plan_path.exists():
            logger.info(f"Creating new plan file: {plan_path}", extra={'log_color': 'HIGHLIGHT'})
            self._file_service.write_file(plan_path, "# Plan for task\n\nNext steps:\n- to be generated")
        else:
            logger.info(f"Updating existing plan file: {plan_path}", extra={'log_color': 'HIGHLIGHT'})

        task['_plan_path'] = str(plan_path)
        know, include_filenames =self._gather_include_knowledge(task, svc)
        # build a proper plan prompt
        plan_prompt = self._prompt_builder.build_plan_prompt(
            task,
            basedir=str(base_folder) if base_folder else '',
            out_path=str(plan_path),
            knowledge_text=task.get('knowledge',''),
            include_text=know
        )

        # generate…
        plan_content = svc.ask(plan_prompt)
        if not plan_content.strip():
            logger.warning("LLM returned an empty plan.", extra={'log_color': 'DELTA'})
            return ""

        # write out and record token count
        self._todo_util._write_plan(svc, plan_path, plan_content)
        task['plan_tokens'] = len(plan_content.split())
        task['_latest_plan'] = plan_content
        logger.info(f"Wrote plan.md with {task['plan_tokens']} tokens", extra={'log_color': 'PERCENT'})
        return plan_content
    
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
            include_text, include_filenames_text = self._gather_include_knowledge(task, svc)
            include_files: List[str] = []
            if include_text:
                for line in include_text.splitlines():
                    if line.startswith("# file: "):
                        include_files.append(line[8:].strip())
            task['_include_files'] = include_files
            task['include_filenames'] = include_files
            task['include_filenames_text'] = include_filenames_text
            task['_include_spec'] = task.get('include')
            task['_include_tokens'] = len(include_text.split()) if include_text else 0
            task['include_tokens'] = task.get('include_tokens', task['_include_tokens'])
            task['knowledge_tokens'] = len(task.get('knowledge', '').split())
            knowledge_text = task.get('knowledge') or ""
            task['_know_tokens'] = len(knowledge_text.split())
            task['knowledge_tokens'] = task['_know_tokens']

            plan = task.get('plan', 'x')
            commit = task.get('commit', 'x')
            status = task.get('llm', 'x')
            
            if step == 1 or task.get('plan') == ' ':
                st = self.start_task(task, file_lines_map, svc.get_cur_model(), 1)
                # this now correctly uses task['plan_spec']
                plan_content = self._generate_plan(task, svc, base_folder)
                if plan_content:
                    task['plan_tokens'] = len(plan_content.split())
                ct = self.complete_task(task, file_lines_map, svc.get_cur_model(), 0, None, False, 1)
                task['_start_stamp'] = st
                return
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
                    task['plan_tokens'] = len(plan_content.split())
                    task['_plan_path'] = str(plan_path)
                    task['_latest_plan'] = plan_content
                    logger.info("Included plan.md in LLM prompt", extra={'log_color': 'HIGHLIGHT'})
                # Enhanced: Use stage-specific desc for LLM (llm_desc)
                prompt_desc = task.get('llm_desc', task['desc'])
                resources = "knowledge_text: " + knowledge_text + " plan.md:" + plan_knowledge + " task desc: " + prompt_desc
                prompt = self._prompt_builder.build_task_prompt(
                    task, self._base_dir, str(out_path), resources, include_text
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
            elif step == 3 or (status == 'x' and commit == ' ' and plan == 'x'):
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
                logger.info(f"No step to run: status={status}, write={commit}, plan={plan}", extra={'log_color': 'DELTA'})

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

# Original file length: 325 lines
# Updated file length: 380 lines