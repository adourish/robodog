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
    r'\[(?P<status>[ x~])\]'       # first [status]
    r'(?:\s*\[(?P<write>[ x~-])\])?'  # optional [write_flag], whitespace allowed
    r'(?:\s*\[(?P<plan>[ x~-])\])?'   # optional [plan_flag] for three-step process
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
        logger.debug(f"Initializing TodoService with roots: {roots}")
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
            
            logger.info(f"Base directory parsed: {self._base_dir}")

            self._load_all()
            for fn in self._find_files():
                try:
                    self._mtimes[fn] = os.path.getmtime(fn)
                    logger.debug(f"Initial mtime for {fn}: {self._mtimes[fn]}")
                except Exception as e:
                    logger.exception(f"Could not get mtime for {fn}: {e}")
                    pass
            threading.Thread(target=self._watch_loop, daemon=True).start()
            logger.info("TodoService initialized successfully")
        except Exception as e:
            logger.exception(f"Error during initialization of TodoService: {e}")
            raise

    def _parse_task_metadata(self, full_desc: str) -> Dict:
        """
        Parse the task description for metadata like started, completed, knowledge_tokens, etc.
        Returns a dict with parsed values and the clean description.
        Enhanced logging for metadata parsing.
        """
        logger.info(f"Parsing metadata for task desc: {full_desc}")
        try:
            metadata = {
                'desc': full_desc.strip(),
                '_start_stamp': None,
                '_complete_stamp': None,
                'knowledge_tokens': 0,
                'include_tokens': 0,
                'prompt_tokens': 0,
                'plan_tokens': 0,  # New for planning step
            }
            # Split by | to separate desc from metadata
            parts = [p.strip() for p in full_desc.split('|') if p.strip()]
            if len(parts) > 1:
                metadata['desc'] = parts[0]  # Clean desc is the first part
                logger.info(f"Clean desc: {metadata['desc']}, metadata parts: {len(parts)-1}")
                # Parse metadata parts
                for part in parts[1:]:
                    if ':' in part:
                        key, val = [s.strip() for s in part.split(':', 1)]
                        try:
                            if key == 'started':
                                metadata['_start_stamp'] = val if val.lower() != 'none' else None
                                logger.info(f"Parsed started: {metadata['_start_stamp']}")
                            elif key == 'completed':
                                metadata['_complete_stamp'] = val if val.lower() != 'none' else None
                                logger.info(f"Parsed completed: {metadata['_complete_stamp']}")
                            elif key == 'knowledge':
                                metadata['knowledge_tokens'] = int(val) if val.isdigit() else 0
                                logger.info(f"Parsed knowledge tokens: {metadata['knowledge_tokens']}")
                            elif key == 'include':
                                metadata['include_tokens'] = int(val) if val.isdigit() else 0
                                logger.info(f"Parsed include tokens: {metadata['include_tokens']}")
                            elif key == 'prompt':
                                metadata['prompt_tokens'] = int(val) if val.isdigit() else 0
                                logger.info(f"Parsed prompt tokens: {metadata['prompt_tokens']}")
                            elif key == 'plan':  # New for planning step
                                metadata['plan_tokens'] = int(val) if val.isdigit() else 0
                                logger.info(f"Parsed plan tokens: {metadata['plan_tokens']}")
                        except ValueError:
                            logger.warning(f"Failed to parse metadata part: {part}")
            logger.info(f"Parsed metadata: {metadata}")
            return metadata
        except Exception as e:
            logger.exception(f"Error parsing task metadata for '{full_desc}': {e}")
            return {'desc': full_desc.strip(), '_start_stamp': None, '_complete_stamp': None, 'knowledge_tokens': 0, 'include_tokens': 0, 'prompt_tokens': 0, 'plan_tokens': 0}

    def _parse_base_dir(self) -> Optional[str]:
        logger.info("_parse_base_dir called")
        try:
            for fn in self._find_files():
                logger.info(f"Parsing front-matter from {fn}")
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
                            logger.info(f"Found base dir: {base}")
                            return os.path.normpath(base)
            logger.info("No base dir found")
            return None
        except Exception as e:
            logger.exception(f"Error parsing base dir: {e}")
            return None

    def _find_files(self) -> List[str]:
        logger.debug("_find_files called")
        try:
            out = []
            for r in self._roots:
                for dp, _, fns in os.walk(r):
                    if self.FILENAME in fns:
                        out.append(os.path.join(dp, self.FILENAME))
            logger.info(f"Found files: {out}")
            return out
        except Exception as e:
            logger.exception(f"Error finding todo files: {e}")
            return []

    def _load_all(self):
        """
        Parse each todo.md into tasks, capturing optional second‐bracket
        write‐flag, third bracket for planning, and any adjacent ```knowledge``` block.
        Also parse metadata from the task line (e.g., | started: ... | knowledge: 0).
        Added logging for task loading.
        """
        logger.debug("_load_all called: Reloading all tasks from files")
        try:
            self._file_lines.clear()
            self._tasks.clear()
            total_tasks = 0
            for fn in self._find_files():
                logger.info(f"Parsing tasks from {fn}")
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
                    task     = {
                        'file': fn,
                        'line_no': i,
                        'indent': indent,
                        'status_char': status,
                        'write_flag': write_flag,
                        'plan_flag': plan_flag,  # New field
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
                        logger.info(f"Loaded knowledge for task {task_count}: {know_tokens} tokens")
                        j += 1  # skip closing ``` line

                    self._tasks.append(task)
                    task_count += 1
                    total_tasks += 1
                    i = j
                logger.info(f"Loaded {task_count} tasks from {fn}")
            logger.info(f"Total tasks loaded across all files: {total_tasks}")
        except Exception as e:
            logger.exception(f"Error in _load_all: {e}")
            traceback.print_exc()

    def _watch_loop(self):
        """
        Watch all todo.md files under self._roots.
        On external change, re‐parse tasks, re‐emit any manually Done tasks
        with write_flag=' ' and then run the next To Do.
        Added logging for watch events.
        """
        logger.debug("_watch_loop started")
        while True:
            try:
                for fn in self._find_files():
                    try:
                        mtime = os.path.getmtime(fn)
                    except OSError:
                        logger.warning(f"File {fn} not found, skipping")
                        # file might have been deleted
                        continue

                    # 1) ignore our own writes
                    ignore_time = self._watch_ignore.get(fn)
                    if ignore_time and abs(mtime - ignore_time) < 1e-3:
                        self._watch_ignore.pop(fn, None)
                        logger.debug(f"Skipped our own write for {fn}")

                    # 2) external change?
                    elif self._mtimes.get(fn) and mtime > self._mtimes[fn]:
                        logger.info(f"Detected external change in {fn}, reloading tasks")
                        if not self._svc:
                            logger.warning("Svc not available, skipping change processing")
                            # nothing to do if service not hooked up
                            continue

                        try:
                            # re‐parse all todo.md files into self._tasks
                            self._load_all()
                            done_tasks = [t for t in self._tasks if STATUS_MAP[t['status_char']] == 'Done']
                                 
                            self._process_manual_done(done_tasks, fn)

                            # b) then run the next To Do task, if any remain
                            next_todos = [
                                t for t in self._tasks
                                if STATUS_MAP.get(t.get('status_char') or ' ') == 'To Do'
                            ]
                            if next_todos:
                                logger.info("New To Do tasks found, running next")
                                self.run_next_task(self._svc, fn)

                        except Exception as e:
                            logger.exception(f"Watch loop error processing {fn}: {e}")
                            traceback.print_exc()

                    # 3) update our stored mtime
                    self._mtimes[fn] = mtime

            except Exception as e:
                logger.exception(f"Error in watch loop: {e}")
                traceback.print_exc()

            time.sleep(1)

    def _process_manual_done(self, done_tasks: list, todoFilename: str = ""):
        """
        Iterate all manually-completed tasks, normalize their output paths
        by combining with the folder of todoFilename, and skip any
        that don’t exist on disk.
        Added logging for manual processing.
        """
        logger.info(f"_process_manual_done called with {len(done_tasks)} tasks, todoFilename={todoFilename}")

        # derive the folder containing the todo.md that was edited
        base_folder = None
        if todoFilename:
            try:
                base_folder = Path(todoFilename).parent
                logger.info("Process manual base folder: " + str(base_folder))    
            except Exception as e:
                logger.exception(f"Could not determine parent folder of {todoFilename}: {e}")
                traceback.print_exc()
                base_folder = None

        for task in done_tasks:
            try:
                # only act on tasks that were manually marked Done (status_char='x') with write_flag=' '
                if STATUS_MAP.get(task.get('status_char')) != 'Done' or task.get('write_flag') != ' ':
                    logger.debug(f"Skipping task {task.get('desc', '')}: status={task.get('status_char')}, write={task.get('write_flag')}")
                    continue

                logger.info(f"Manual commit of task: {task['desc']}")

                # ensure token counts exist
                task['knowledge_tokens'] = task.get('knowledge_tokens', task.get('_know_tokens', 0))
                task['include_tokens']   = task.get('include_tokens', task.get('_include_tokens', 0))
                task['prompt_tokens']    = task.get('prompt_tokens', task.get('_prompt_tokens', 0))
                task['plan_tokens']      = task.get('plan_tokens', 0)  # New

                # ensure a start stamp
                if task.get('_start_stamp') is None:
                    task['_start_stamp'] = datetime.now().isoformat()
                    logger.debug(f"Set start stamp for manual task: {task['_start_stamp']}")

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
                        logger.exception(f"Error resolving pattern {pattern}: {e}")
                        traceback.print_exc()
                        cand = None
                    if cand:
                        out_path = cand
                    else:
                        # fallback: treat it as a literal under the same folder
                        if base_folder and pattern:
                            out_path = base_folder / pattern

                # nothing to do if we still don't have a path
                if not out_path:
                    logger.warning(f"No valid 'out' path for manual commit: {raw_out!r}")
                    continue

                # sanity check
                if not out_path.exists():
                    logger.warning(f"Output path not found on disk for manual commit: {out_path}")
                    continue

                # read the existing AI output
                try:
                    ai_out = self._file_service.safe_read_file(out_path)
                    logger.info(f"Read existing out: {out_path} ({len(ai_out.split())} tokens)")
                except Exception as e:
                    logger.exception(f"Error reading AI output from {out_path}: {e}")
                    traceback.print_exc()
                    ai_out = ""

                # re-parse it just like a normal complete
                cur_model = self._svc.get_cur_model()
                # mark as started if needed
                st = self.start_task(task, self._file_lines, cur_model)
                if st is None:
                    st = task['_start_stamp']
                task['_start_stamp'] = st

                try:
                    basedir = Path(task['file']).parent
                    self._file_service.base_dir = str(basedir)
                    parsed_files = (
                        self.parser.parse_llm_output(
                            ai_out,
                            base_dir=str(basedir),
                            file_service=self._file_service,
                            ai_out_path=out_path,
                            task=task,
                            svc=self._svc
                        )
                        if ai_out else []
                    )
                    logger.debug(f"Parsed {len(parsed_files)} files from AI output")
                except Exception as e:
                    logger.exception(f"Parsing existing AI output failed: {e}")
                    traceback.print_exc()
                    parsed_files = []

                # write out parsed files, collect compare info
                committed, compare = 0, []
                success = False
                if parsed_files:
                    try:
                        committed, compare = self._write_parsed_files(parsed_files, task, True, base_folder)
                        success = (committed > 0 or bool(compare))
                        logger.info(f"Committed {committed} files, success: {success}")
                    except Exception as e:
                        logger.exception(f"Error writing parsed files: {e}")
                        traceback.print_exc()
                else:
                    logger.info("No parsed files to commit.")

                if success:
                    logger.info("Manual commit completed successfully")

                # finally mark the task done in todo.md
                ct = self.complete_task(task, self._file_lines, cur_model, 0, compare, True)
                if ct is None:
                    ct = datetime.now().isoformat()
                task['_complete_stamp'] = ct
                logger.debug(f"Manual task completion stamp: {ct}")
            except Exception as e:
                logger.exception(f"Error processing manual done task {task['desc']}: {e}")
                traceback.print_exc()

    def start_task(self, task: dict, file_lines_map: dict, cur_model: str):
        logger.info(f"Starting task: {task['desc']} (model: {cur_model})")
        try:
            # Ensure tokens are populated before calling task_manager
            task['knowledge_tokens'] = task.get('knowledge_tokens', task.get('_know_tokens', 0))
            task['include_tokens'] = task.get('include_tokens', task.get('_include_tokens', 0))
            task['prompt_tokens'] = task.get('prompt_tokens', task.get('_prompt_tokens', 0))
            task['plan_tokens'] = task.get('plan_tokens', 0)
            st = self._task_manager.start_task(task, file_lines_map, cur_model)
            # Preserve or set stamp if task_manager returns None
            if st is None:
                st = datetime.now().isoformat()
            task['_start_stamp'] = st  # Ensure start stamp is set on task
            logger.info(f"Task start stamp: {st}")
            return st
        except Exception as e:
            logger.exception(f"Error starting task {task['desc']}: {e}")
            traceback.print_exc()
            st = datetime.now().isoformat()
            task['_start_stamp'] = st
            return st
            
    def complete_task(self, task: dict, file_lines_map: dict, cur_model: str, truncation: float, compare: Optional[List[str]] = None, commit: bool = False):
        logger.info(f"Completing task: {task['desc']} (model: {cur_model}, commit: {commit})")
        try:
            # Ensure tokens are populated before calling task_manager
            task['knowledge_tokens'] = task.get('knowledge_tokens', task.get('_know_tokens', 0))
            task['include_tokens'] = task.get('include_tokens', task.get('_include_tokens', 0))
            task['prompt_tokens'] = task.get('prompt_tokens', task.get('_prompt_tokens', 0))
            task['plan_tokens'] = task.get('plan_tokens', 0)
            ct = self._task_manager.complete_task(task, file_lines_map, cur_model, 0, compare, commit)
            # Preserve or set stamp if task_manager returns None
            if ct is None:
                ct = datetime.now().isoformat()
            task['_complete_stamp'] = ct  # Ensure complete stamp is set on task
            logger.info(f"Task complete stamp: {ct}")
            return ct
        except Exception as e:
            logger.exception(f"Error completing task {task['desc']}: {e}")
            traceback.print_exc()
            ct = datetime.now().isoformat()
            task['_complete_stamp'] = ct
            return ct
            
    def run_next_task(self, svc, todoFilename: str = ""):
        logger.info("run_next_task called")
        try:
            self._svc = svc
            self._load_all()
            todo = [t for t in self._tasks
                    if STATUS_MAP[t['status_char']] == 'To Do']
            if not todo:
                logger.info("No To Do tasks found.")
                return
            self._process_one(todo[0], svc, self._file_lines, todoFilename=todoFilename)
            logger.info("Completed one To Do task")
        except Exception as e:
            logger.exception(f"Error running next task: {e}")
            traceback.print_exc()

    def _gather_include_knowledge(self, task: dict, svc) -> str:
        logger.info("Gathering include knowledge")
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
                logger.info(f"Gathered include knowledge: {include_tokens} tokens from spec '{full_spec}'")
                return know
            except Exception as e:
                logger.exception(f"Include failed for spec='{full_spec}': {e}")
                traceback.print_exc()
                return ""
        except Exception as e:
            logger.exception("Error in _gather_include_knowledge: {e}")
            traceback.print_exc()
            return ""

    # New method for planning step: generate/update plan.md
    def _generate_plan(self, task: dict, svc, base_folder: Optional[Path] = None) -> str:
        """
        Step 1: Generate or update plan.md summarizing the task plan, changes, and next steps.
        Uses a specialized prompt for planning.
        """
        logger.info(f"Generating plan for task: {task['desc']}")
        try:
            # Determine plan path
            plan_spec = task.get('plan') or {'pattern': 'plan.md', 'recursive': False}
            plan_path = self._get_ai_out_path({'out': plan_spec}, base_folder=base_folder)
            if not plan_path:
                plan_path = base_folder / 'plan.md' if base_folder else Path('plan.md')
                logger.info(f"Default plan path: {plan_path}")

            # Build planning prompt
            plan_prompt = self._prompt_builder.build_task_prompt(
                task,
                basedir=str(base_folder) if base_folder else '',
                out_path=str(plan_path),
                knowledge_text=task.get('knowledge', ''),
                include_text=self._gather_include_knowledge(task, svc)
            ) + "\n\nFocus on planning: Summarize the task, outline changes, and list next steps in plan.md."

            # Generate plan
            plan_content = svc.ask(plan_prompt)
            if not plan_content:
                logger.warning("No plan content generated")
                return ""

            # Parse and write plan (treat as UPDATE or NEW)
            parsed_plan = self.parser.parse_llm_output(
                plan_content,
                base_dir=str(base_folder) if base_folder else '',
                file_service=self._file_service,
                ai_out_path=str(plan_path),
                task={'desc': f"Plan for {task['desc']}"},
                svc=svc
            )
            committed, _ = self._write_parsed_files(parsed_plan, task, True, base_folder)
            plan_tokens = len(plan_content.split())
            task['plan_tokens'] = plan_tokens
            logger.info(f"Plan generated and committed: {committed} files, {plan_tokens} tokens")
            return plan_content
        except Exception as e:
            logger.exception(f"Error generating plan: {e}")
            traceback.print_exc()
            return ""

    # --- modified write-and-report method ---
    def _write_parsed_files(self, parsed_files: List[dict], task: dict = None, commit_file: bool= False, base_folder: str = "") -> tuple[int, List[str]]:
        """
        Write parsed files and compare tokens using parse_service object properties, return results and compare list
        For NEW files, resolve path relative to todo.md folder (base_dir) and create full path.
        For DELETE files, delete the matched file if it exists; prioritize DELETE over NEW even if both flags are set.
        matchedfilename remains relative for reporting.
        Enhanced logging for UPDATEs: full compare details with percentage deltas (median, avg, peak line/token changes).
        Added logging for planning step files.
        """
        logger.info("_write_parsed files base folder: " + str(base_folder))
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
                        logger.info(f"Writing plan file: {filename} (new: {is_new}, update: {is_update})")
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

                    # Per-file logging in the specified format
                    logger.info(f"{action} {relative_path}: (O/U/D/P {orig_tokens}/{new_tokens}/{abs_delta}/{token_delta:.1f}%)")

                    # Enhanced logging including originalfilename and matchedfilename
                    logger.info(f"  - originalfilename: {originalfilename}")
                    logger.info(f"  - matchedfilename: {matchedfilename}")
                    logger.info(f"  - relative_path: {relative_path}")
                    # Prioritize DELETE: delete if flagged, regardless of other flags
                    if commit_file:
                        if is_delete:
                            logger.info(f"Delete file: {matchedfilename}")
                            delete_path = Path(matchedfilename) if matchedfilename else None
                            if commit_file and delete_path and delete_path.exists():
                                self._file_service.delete_file(delete_path)
                                logger.info(f"Deleted file: {delete_path} (matched: {matchedfilename})")
                                result += 1
                            elif not delete_path:
                                logger.warning(f"No matched path for DELETE: {filename}")
                            else:
                                logger.info(f"DELETE file not found: {delete_path}")
                            compare.append(f"{parsed.get('short_compare', '')} (DELETE) -> {matchedfilename}")
                            continue  # No further action for deletes


                        if is_copy:
                            # For COPY: resolve source and destination, copy file
                            src_path = Path(matchedfilename)  # Assume matched is source
                            dst_path = self._file_service.resolve_path(relative_path, self._svc)  # Destination relative
                            if src_path.exists():
                                self._file_service.copy_file(src_path, dst_path)
                                logger.info(f"Copied file: {src_path} -> {dst_path} (relative: {relative_path})")
                                result += 1
                            else:
                                logger.warning(f"Source for COPY not found: {src_path}")
                        elif is_new:
                            # For NEW, resolve relative to base_dir
                            # create the new file under the todo.md folder + relative_path
                            new_path = basedir / relative_path
                            self._file_service.write_file(new_path, content)
                            logger.info(f"Created NEW file at: {new_path} (relative: {relative_path})")
                            result += 1
                            
                        elif is_update:
                            # For UPDATE, use matched path
                            new_path = Path(matchedfilename)
                            if new_path.exists():
                                self._file_service.write_file(new_path, content)
                                logger.info(f"Updated file: {new_path} (matched: {matchedfilename})")
                                # Enhanced UPDATE logging: calculate and log deltas
                                update_deltas.append(token_delta)
                                update_abs_deltas.append(abs_delta)
                                logger.info(f"UPDATE details for {filename}: (o/n/d/p {orig_tokens}/{new_tokens}/{abs_delta}{token_delta:.1f}%)")
                                result += 1
                            else:
                                logger.warning(f"Path for UPDATE not found: {new_path}")
                        else:
                            logger.warning(f"Unknown action for {filename}: new={is_new}, update={is_update}, delete={is_delete}, copy={is_copy}")

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
                    logger.exception(f"Error processing parsed file {parsed.get('filename', 'unknown')}: {e}")
                    traceback.print_exc()
                    continue
            logger.info(f"Plan files written: {plan_files_written}")
        except Exception as e:
            logger.exception(f"Error in _write_parsed_files: {e}")
            traceback.print_exc()

        # Aggregate UPDATE logging: full compare details with stats (median, avg, peak delta)
        if update_deltas and commit_file:
            try:
                if len(update_deltas) > 0:
                    delta_median = statistics.median(update_deltas)
                    delta_avg = statistics.mean(update_deltas)
                    delta_peak = max(update_deltas)
                    abs_delta_median = statistics.median(update_abs_deltas)
                    abs_delta_avg = statistics.mean(update_abs_deltas)
                    abs_delta_peak = max(update_abs_deltas)
                    # Log in task_manager format
                    logger.info(f"Task UPDATE stats: median_delta_percent={delta_median:.1f}%, avg_delta_percent={delta_avg:.1f}%, peak_delta_percent={delta_peak:.1f}%, median_delta_tokens={abs_delta_median}, avg_delta_tokens={abs_delta_avg}, peak_delta_tokens={abs_delta_peak}")
            except Exception as e:
                logger.exception(f"Error calculating UPDATE stats: {e}")
                traceback.print_exc()

        return result, compare

    def _backup_and_write_output(self, svc, out_path: Path, content: str):
        if not out_path:
            return
        try:
            self._file_service.write_file(out_path, content)
            logger.info(f"Backed up and wrote output to: {out_path}")
        except Exception as e:
            logger.exception(f"Failed to backup and write output to {out_path}: {e}")
            traceback.print_exc()
        
    def _write_full_ai_output(self, svc, task, ai_out, trunc_code, base_folder: str="" ):
        try:
            out_path = self._get_ai_out_path(task, base_folder=base_folder)
            logger.info(f"Write AI out: {out_path} ({len(ai_out.split())} tokens)")
            if out_path:
                self._backup_and_write_output(svc, out_path, ai_out)
        except Exception as e:
            logger.exception(f"Error writing full AI output: {e}")
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
                logger.exception(f"Error resolving pattern {pattern}: {e}")
                cand = None
            if cand:
                out_path = cand
            else:
                # fallback: treat it as a literal under the same folder
                if base_folder and pattern:
                    out_path = base_folder / pattern

        return out_path


    def _process_one(self, task: dict, svc, file_lines_map: dict, todoFilename: str = ""):
        logger.info(f"_process_one called with task, todoFilename={todoFilename!r}")

        # derive the folder containing the todo.md that was edited
        base_folder = None
        if todoFilename:
            try:
                base_folder = Path(todoFilename).parent
                logger.info("Process base folder: " + str(base_folder))  
            except Exception as e:
                logger.exception(f"Could not determine parent folder of {todoFilename}: {e}")
                traceback.print_exc()
                base_folder = None

        try:
            logger.info(f"Processing task: {task['desc']}")
            basedir = Path(task['file']).parent
            self._base_dir = str(basedir)
            self._file_service.base_dir = str(basedir)  # Set base_dir for relative resolutions
            logger.debug(f"Base dir: {self._base_dir}")
            include_text = self._gather_include_knowledge(task, svc)
            task['_include_tokens'] = len(include_text.split())
            task['include_tokens'] = task['_include_tokens']
            logger.info(f"Include tokens: {task['_include_tokens']}")
            knowledge_text = task.get('knowledge') or ""
            task['_know_tokens'] = len(knowledge_text.split())
            task['knowledge_tokens'] = task['_know_tokens']
            logger.info(f"Knowledge tokens: {task['_know_tokens']}")

            # Step 1: Planning - generate/update plan.md if plan_flag is ' ' or None
            plan_flag = task.get('plan_flag')
            if plan_flag in [None, ' ']:
                plan_content = self._generate_plan(task, svc, base_folder)
                if plan_content:
                    task['plan_tokens'] = len(plan_content.split())
                    logger.info(f"Plan tokens: {task['plan_tokens']}")
                else:
                    logger.warning("Plan generation failed or skipped")
            else:
                logger.info(f"Planning skipped: plan_flag={plan_flag}")

            out_path = self._get_ai_out_path(task, base_folder=base_folder)
            prompt = self._prompt_builder.build_task_prompt(task, self._base_dir, str(out_path), knowledge_text, include_text)
            task['_prompt_tokens'] = len(prompt.split())
            task['prompt_tokens'] = task['_prompt_tokens']
            logger.info(f"Prompt tokens: {task['_prompt_tokens']}")
            cur_model = svc.get_cur_model()
            task['cur_model'] = cur_model  # Set cur_model for logging
            st = self.start_task(task, file_lines_map, cur_model)
            task['_start_stamp'] = st  # Ensure start stamp is set

            # Step 2: Run LLM task
            try:
                ai_out = svc.ask(prompt)
            except Exception as e:
                logger.exception(f"LLM call failed: {e}")
                traceback.print_exc()
                ai_out = ""

            # Added check for ai_out issues
            if not ai_out:
                logger.warning("No AI output generated for task. Running one more time.")
                try:
                    ai_out = svc.ask(prompt)
                    if not ai_out:
                        logger.error("No AI output generated for task. Failed.")
                    else:
                        logger.info(f"AI output length: {len(ai_out)} characters")
                except Exception as e:
                    logger.exception(f"Second LLM call failed: {e}")
                    traceback.print_exc()
            else:
                logger.info(f"AI output length: {len(ai_out)} characters")

            # Write AI output immediately
            self._write_full_ai_output(svc, task, ai_out, 0, base_folder=base_folder)

            # parse and report before writing
            try:
                parsed_files = self.parser.parse_llm_output(ai_out, base_dir=str(basedir), file_service=self._file_service, ai_out_path=out_path, task=task, svc=self._svc) if ai_out else []
                logger.debug(f"Parsed {len(parsed_files)} files from AI output")
            except Exception as e:
                logger.exception(f"Parsing AI output failed: {e}")
                traceback.print_exc()
                parsed_files = []

            commited, compare = 0, []
            success = False
            if parsed_files:
                try:
                    commited, compare = self._write_parsed_files(parsed_files, task, False, base_folder=base_folder)
                    if commited > 0 or len(compare) > 0:
                        success = True
                    logger.info(f"Committed {commited} files from LLM output, success: {success}")
                except Exception as e:
                    logger.exception(f"Error writing parsed files: {e}")
                    traceback.print_exc()
            else:
                logger.info("No parsed files to commit.")

            # Step 3: Commit (if write_flag is ' ')
            write_flag = task.get('write_flag')
            if write_flag == ' ':
                logger.info("Step 3: Committing changes")
                try:
                    # Re-parse and commit
                    parsed_files_commit = self.parser.parse_llm_output_commit(ai_out, base_dir=str(basedir), file_service=self._file_service, ai_out_path=out_path, task=task, svc=self._svc)
                    committed_commit, compare_commit = self._write_parsed_files(parsed_files_commit, task, True, base_folder=base_folder)
                    logger.info(f"Commit step: {committed_commit} files committed")
                except Exception as e:
                    logger.exception(f"Commit step failed: {e}")
                    traceback.print_exc()
            else:
                logger.info(f"Commit skipped: write_flag={write_flag}")

            truncation = 0.0  # Assuming no truncation
            ct = self.complete_task(task, file_lines_map, cur_model, truncation, compare, False)
            task['_complete_stamp'] = ct  # Ensure complete stamp is set
            logger.info(f"Task processed: {task['desc']}")
        except Exception as e:
            logger.exception(f"Error processing task {task['desc']}: {e}")
            traceback.print_exc()

    def _resolve_path(self, frag: str) -> Optional[Path]:
        logger.info(f"Resolving path: {frag}")
        try:
            srf = self._file_service.resolve_path(frag, self._svc)
            return srf
        except Exception as e:
            logger.exception(f"Error resolving path {frag}: {e}")
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
        logger.info(f"Searching files with pattern '{pattern}', recursive={recursive}")
        try:
            base = getattr(self, 'root_dir', Path.cwd())
            base = Path(base)
            if recursive:
                matches = base.rglob(pattern)
            else:
                matches = base.glob(pattern)
            result = [str(p) for p in matches if p.is_file()]
            logger.info(f"Search found {len(result)} matches")
            return result
        except Exception as e:
            logger.exception(f"Error searching files with pattern {pattern}: {e}")
            traceback.print_exc()
            return []



    # optional: if you also need to extract filenames/flags from LLM headers
    # ----------------------------------------------------------------
    def _extract_filename_and_flag(self, header: str) -> Tuple[Optional[str], Optional[str]]:
        """
        parse a markdown code-fence info string like:
          ```python filename=foo.py flag=XYZ
        Added logging for extraction.
        """
        logger.info(f"Extracting filename and flag from: {header}")
        try:
            import re
            m = re.search(r'```[^\s]*\s+filename=(\S+)(?:\s+flag=(\S+))?', header)
            if not m:
                logger.debug("No match found in header")
                return None, None
            filename = m.group(1)
            flag     = m.group(2)
            logger.info(f"Extracted: filename={filename}, flag={flag}")
            return filename, flag
        except Exception as e:
            logger.exception(f"Error extracting filename and flag from {header}: {e}")
            traceback.print_exc()
            return None, None

# original file length: 1042 lines
# updated file length: 1352 lines