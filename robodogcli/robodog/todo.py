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
TASK_RE = re.compile(
    r'^(\s*)-\s*'                  # indent + "- "
    r'\[(?P<status>[ x~])\]'       # first [status]
    r'(?:\s*\[(?P<write>[ x~-])\])?'  # optional [write_flag], whitespace allowed
    r'\s*(?P<desc>.+)$'            # space + desc (including potential metadata)
)
SUB_RE = re.compile(
    r'^\s*-\s*(?P<key>include|out|in|focus):\s*'
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

    def __init__(self, roots: List[str], svc=None, prompt_builder=None, task_manager=None, task_parser=None, file_watcher=None, file_service=None, exclude_dirs={"node_modules", "dist"}):
        logger.debug(f"Initializing TodoService with roots: {roots}")
        logger.debug(f"Svc provided: {svc is not None}, Prompt builder: {prompt_builder is not None}")
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
        
        logger.debug(f"Base directory parsed: {self._base_dir}")

        self._load_all()
        for fn in self._find_files():
            try:
                self._mtimes[fn] = os.path.getmtime(fn)
                logger.debug(f"Initial mtime for {fn}: {self._mtimes[fn]}")
            except Exception as e:
                logger.warning(f"Could not get mtime for {fn}: {e}")
                pass

        threading.Thread(target=self._watch_loop, daemon=True).start()
        logger.debug("TodoService initialized successfully")

    def _parse_task_metadata(self, full_desc: str) -> Dict:
        """
        Parse the task description for metadata like started, completed, knowledge_tokens, etc.
        Returns a dict with parsed values and the clean description.
        """
        metadata = {
            'desc': full_desc.strip(),
            '_start_stamp': None,
            '_complete_stamp': None,
            'knowledge_tokens': 0,
            'include_tokens': 0,
            'prompt_tokens': 0,
        }
        # Split by | to separate desc from metadata
        parts = [p.strip() for p in full_desc.split('|') if p.strip()]
        if len(parts) > 1:
            metadata['desc'] = parts[0]  # Clean desc is the first part
            # Parse metadata parts
            for part in parts[1:]:
                if ':' in part:
                    key, val = [s.strip() for s in part.split(':', 1)]
                    try:
                        if key == 'started':
                            metadata['_start_stamp'] = val if val.lower() != 'none' else None
                        elif key == 'completed':
                            metadata['_complete_stamp'] = val if val.lower() != 'none' else None
                        elif key == 'knowledge':
                            metadata['knowledge_tokens'] = int(val) if val.isdigit() else 0
                        elif key == 'include':
                            metadata['include_tokens'] = int(val) if val.isdigit() else 0
                        elif key == 'prompt':
                            metadata['prompt_tokens'] = int(val) if val.isdigit() else 0
                    except ValueError:
                        logger.debug(f"Failed to parse metadata part: {part}")
        return metadata

    def _parse_base_dir(self) -> Optional[str]:
        logger.debug("_parse_base_dir called")
        for fn in self._find_files():
            logger.debug(f"Parsing front-matter from {fn}")
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
                        logger.debug(f"Found base dir: {base}")
                        return os.path.normpath(base)
        logger.debug("No base dir found")
        return None

    def _find_files(self) -> List[str]:
        logger.debug("_find_files called")
        out = []
        for r in self._roots:
            for dp, _, fns in os.walk(r):
                if self.FILENAME in fns:
                    out.append(os.path.join(dp, self.FILENAME))
        logger.debug(f"Found files: {out}")
        return out

    def _load_all(self):
        """
        Parse each todo.md into tasks, capturing optional second‐bracket
        write‐flag and any adjacent ```knowledge``` block.
        Also parse metadata from the task line (e.g., | started: ... | knowledge: 0).
        """
        logger.debug("_load_all called: Reloading all tasks from files")
        self._file_lines.clear()
        self._tasks.clear()
        for fn in self._find_files():
            logger.debug(f"Parsing tasks from {fn}")
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
                    'desc': desc,
                    'include': None,
                    'in': None,
                    'out': None,
                    'knowledge': '',
                    'knowledge_tokens': 0,
                    'include_tokens': 0,
                    'prompt_tokens': 0,
                    '_start_stamp': None,
                    '_know_tokens': 0,
                    '_in_tokens': 0,
                    '_prompt_tokens': 0,
                    '_include_tokens': 0,
                    '_complete_stamp': None,
                }
                task.update(metadata)  # Add parsed metadata (tokens, stamps)

                # scan sub‐entries (include, in, focus)
                j = i + 1
                while j < len(lines) and lines[j].startswith(indent + '  '):
                    sub = SUB_RE.match(lines[j])
                    if sub:
                        key = sub.group('key')
                        pat = sub.group('pattern').strip('"').strip('`')
                        rec = bool(sub.group('rec'))
                        if key == 'focus':
                            task['out'] = {'pattern': pat, 'recursive': rec}
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
                    j += 1  # skip closing ``` line

                self._tasks.append(task)
                task_count += 1
                i = j
            logger.debug(f"Loaded {task_count} tasks from {fn}")

    def _watch_loop(self):
        """
        Watch all todo.md files under self._roots.
        On external change, re‐parse tasks, re‐emit any manually Done tasks
        with write_flag=' ' and then run the next To Do.
        """
        logger.debug("_watch_loop started")
        while True:
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
                        tb = traceback.format_exc()
                        logger.error(f"watch loop error: {e}\n{tb}")

                # 3) update our stored mtime
                self._mtimes[fn] = mtime

            time.sleep(1)

    def _process_manual_done(self, done_tasks: list, todoFilename: str = ""):
        """
        Iterate all manually-completed tasks, normalize their output paths
        by combining with the folder of todoFilename, and skip any
        that don’t exist on disk.
        """
        logger.info(f"_process_manual_done called with {len(done_tasks)} tasks, todoFilename={todoFilename}")

        # derive the folder containing the todo.md that was edited
        base_folder = None
        if todoFilename:
            try:
                base_folder = Path(todoFilename).parent
                logger.info("Process manual base folder:" + str(base_folder))    
            except Exception:
                logger.warning(f"Could not determine parent folder of {todoFilename}")
                base_folder = None

        for task in done_tasks:
            # only act on tasks that were manually marked Done (status_char='x') with write_flag=' '
            if STATUS_MAP.get(task.get('status_char')) != 'Done' or task.get('write_flag') != ' ':
                continue

            logger.info(f"Manual commit of task: {task['desc']}")

            # ensure token counts exist
            task['knowledge_tokens'] = task.get('knowledge_tokens', task.get('_know_tokens', 0))
            task['include_tokens']   = task.get('include_tokens', task.get('_include_tokens', 0))
            task['prompt_tokens']    = task.get('prompt_tokens', task.get('_prompt_tokens', 0))

            # ensure a start stamp
            if task.get('_start_stamp') is None:
                task['_start_stamp'] = datetime.now().isoformat()

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
                except Exception:
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
            ai_out = self._file_service.safe_read_file(out_path)
            logger.info(f"Read existing out: {out_path} ({len(ai_out.split())} tokens)")

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
            except Exception as e:
                logger.error(f"Parsing existing AI output failed: {e}")
                parsed_files = []

            # write out parsed files, collect compare info
            committed, compare = 0, []
            success = False
            if parsed_files:
                committed, compare = self._write_parsed_files(parsed_files, task, True, base_folder)
                success = (committed > 0 or bool(compare))
            else:
                logger.info("No parsed files to commit.")

            if success:
                logger.info("Commit completed")

            # finally mark the task done in todo.md
            ct = self.complete_task(task, self._file_lines, cur_model, 0, compare, True)
            if ct is None:
                ct = datetime.now().isoformat()
            task['_complete_stamp'] = ct

    def start_task(self, task: dict, file_lines_map: dict, cur_model: str):
        logger.debug(f"Starting task: {task['desc']}")
        # Ensure tokens are populated before calling task_manager
        task['knowledge_tokens'] = task.get('knowledge_tokens', task.get('_know_tokens', 0))
        task['include_tokens'] = task.get('include_tokens', task.get('_include_tokens', 0))
        task['prompt_tokens'] = task.get('prompt_tokens', task.get('_prompt_tokens', 0))
        st = self._task_manager.start_task(task, file_lines_map, cur_model)
        # Preserve or set stamp if task_manager returns None
        if st is None:
            st = datetime.now().isoformat()
        task['_start_stamp'] = st  # Ensure start stamp is set on task
        return st
        
    def complete_task(self, task: dict, file_lines_map: dict, cur_model: str, truncation: float, compare: Optional[List[str]] = None, commit: bool = False):
        logger.info(f"Completing task: {task['desc']}")
        # Ensure tokens are populated before calling task_manager
        task['knowledge_tokens'] = task.get('knowledge_tokens', task.get('_know_tokens', 0))
        task['include_tokens'] = task.get('include_tokens', task.get('_include_tokens', 0))
        task['prompt_tokens'] = task.get('prompt_tokens', task.get('_prompt_tokens', 0))
        ct = self._task_manager.complete_task(task, file_lines_map, cur_model, 0, compare, commit)
        # Preserve or set stamp if task_manager returns None
        if ct is None:
            ct = datetime.now().isoformat()
        task['_complete_stamp'] = ct  # Ensure complete stamp is set on task
        return ct
            
    def run_next_task(self, svc, todoFilename: str = ""):
        logger.debug("run_next_task called")
        self._svc = svc
        self._load_all()
        todo = [t for t in self._tasks
                if STATUS_MAP[t['status_char']] == 'To Do']
        if not todo:
            logger.info("No To Do tasks found.")
            return
        self._process_one(todo[0], svc, self._file_lines, todoFilename=todoFilename)
        logger.info("Completed one To Do task")

    def _gather_include_knowledge(self, task: dict, svc) -> str:
        logger.debug("Gathering include knowledge")
        inc = task.get('include') or {}
        spec = inc.get('pattern','')
        if not spec:
            return ""
        rec = " recursive" if inc.get('recursive') else ""
        full_spec = f"pattern={spec}{rec}"
        try:
            know = svc.include(full_spec) or ""
            logger.debug(f"Gathered {len(know.split())} tokens from include")
            return know
        except Exception as e:
            logger.error(f"Include failed for spec='{full_spec}': {e}")
            return ""

    # --- modified write-and-report method ---
    def _write_parsed_files(self, parsed_files: List[dict], task: dict = None, commit_file: bool= False, base_folder: str = "") -> tuple[int, List[str]]:
        """
        Write parsed files and compare tokens using parse_service object properties, return results and compare list
        For NEW files, resolve path relative to todo.md folder (base_dir) and create full path.
        For DELETE files, delete the matched file if it exists; prioritize DELETE over NEW even if both flags are set.
        matchedfilename remains relative for reporting.
        Enhanced logging for UPDATEs: full compare details with percentage deltas (median, avg, peak line/token changes).
        """
        logger.info("_write_parsed_files called commit file: " + str(base_folder))
        result = 0
        compare: List[str] = []
        basedir = Path(task['file']).parent if task else Path.cwd()
        self._file_service.base_dir = str(basedir)  # Set base_dir for relative path resolution
        update_deltas = []  # Collect deltas for UPDATE logging
        update_abs_deltas = []  # Collect absolute deltas for UPDATE logging

        for parsed in parsed_files:
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
            logger.info(f"{action} {filename}: (original={orig_tokens}, updated={new_tokens}, delta={abs_delta}, percentage={token_delta:.1f}%)")

            # Enhanced logging including originalfilename and matchedfilename
            logger.debug(f"  - originalfilename: {originalfilename}")
            logger.debug(f"  - matchedfilename: {matchedfilename}")

            # Prioritize DELETE: delete if flagged, regardless of other flags
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

            if commit_file:
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
                    new_path = self._file_service.resolve_path(relative_path, self._svc)
                    self._file_service.write_file(new_path, content)
                    logger.info(f"Created NEW file at: {new_path} (relative: {relative_path}, matched: {matchedfilename})")
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
                        logger.info(f"UPDATE details for {filename}: Tokens original={orig_tokens}, new={new_tokens}, delta_tokens={abs_delta}, delta_percent={token_delta:.1f}%")
                        result += 1
                    else:
                        logger.warning(f"Path for UPDATE not found: {new_path}")
                else:
                    logger.warning(f"Unknown action for {filename}: new={is_new}, update={is_update}, delete={is_delete}, copy={is_copy}")

            short_compare = parsed.get('short_compare', '')
            if is_delete:
                compare.append(f"{short_compare} (DELETE) -> {matchedfilename}")
            elif is_copy:
                compare.append(f"{short_compare} (COPY) -> {matchedfilename}")
            elif is_new:
                compare.append(f"{short_compare} (NEW) -> {matchedfilename}")
            elif is_update:
                compare.append(f"{short_compare} (UPDATE, delta_tokens={abs_delta}, delta_percent={token_delta:.1f}%) -> {matchedfilename}")
            else:
                compare.append(short_compare)

        # Aggregate UPDATE logging: full compare details with stats (median, avg, peak delta)
        if update_deltas and commit_file:
            if len(update_deltas) > 0:
                delta_median = statistics.median(update_deltas)
                delta_avg = statistics.mean(update_deltas)
                delta_peak = max(update_deltas)
                abs_delta_median = statistics.median(update_abs_deltas)
                abs_delta_avg = statistics.mean(update_abs_deltas)
                abs_delta_peak = max(update_abs_deltas)
                # Log in task_manager format
                logger.info(f"Task UPDATE stats: median_delta_percent={delta_median:.1f}%, avg_delta_percent={delta_avg:.1f}%, peak_delta_percent={delta_peak:.1f}%, median_delta_tokens={abs_delta_median}, avg_delta_tokens={abs_delta_avg}, peak_delta_tokens={abs_delta_peak}")

        return result, compare

    def _test_write_parsed_files(self, parsed_files: List[dict], task: dict = None, commit_file: bool = False, base_folder: str = "") -> tuple[int, List[str]]:
        """
        Write parsed files and compare tokens using parse_service object properties, return results and compare list
        For NEW files, resolve path relative to todo.md folder (base_dir) and create full path.
        For DELETE files, delete the matched file if it exists; prioritize DELETE over NEW even if both flags are set.
        matchedfilename remains relative for reporting.
        Enhanced logging for UPDATEs: full compare details with percentage deltas (median, avg, peak line/token changes).
        """
        logger.debug("_test_write_parsed_files called")
        result = 0
        compare: List[str] = []
        basedir = Path(task['file']).parent if task else Path.cwd()
        self._file_service.base_dir = str(basedir)  # Set base_dir for relative path resolution
        update_deltas = []  # Collect deltas for UPDATE logging
        update_abs_deltas = []  # Collect absolute deltas for UPDATE logging

        for parsed in parsed_files:
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
            logger.info(f"{action} {filename}: (original={orig_tokens}, updated={new_tokens}, delta={abs_delta}, percentage={token_delta:.1f}%)")

            # Enhanced logging including originalfilename and matchedfilename
            logger.debug(f"  - originalfilename: {originalfilename}")
            logger.debug(f"  - matchedfilename: {matchedfilename}")

            # Prioritize DELETE: delete if flagged, regardless of other flags
            if is_delete:
                delete_path = Path(matchedfilename) if matchedfilename else None
                if commit_file and delete_path and delete_path.exists():
                    # self._file_service.delete_file(delete_path)
                    logger.info(f"Test DELETE of file: {delete_path} (matched: {matchedfilename})")
                    result += 1
                elif not delete_path:
                    logger.warning(f"No matched path for DELETE: {filename}")
                else:
                    logger.info(f"DELETE file not found: {delete_path}")
                compare.append(f"{parsed.get('short_compare', '')} (DELETE) -> {matchedfilename}")
                continue  # No further action for deletes

            if commit_file:
                if is_copy:
                    # For COPY: resolve source and destination, copy file
                    src_path = Path(matchedfilename)  # Assume matched is source
                    dst_path = self._file_service.resolve_path(relative_path, self._svc)  # Destination relative
                    if src_path.exists():
                        # self._file_service.copy_file(src_path, dst_path)
                        logger.info(f"Test COPY file: {src_path} -> {dst_path} (relative: {relative_path})")
                        result += 1
                    else:
                        logger.warning(f"Source for COPY not found: {src_path}")
                elif is_new:
                    # For NEW, resolve relative to base_dir
                    new_path = self._file_service.resolve_path(relative_path, self._svc)
                    # self._file_service.write_file(new_path, content)
                    logger.info(f"Test NEW file at: {new_path} (relative: {relative_path}, matched: {matchedfilename})")
                    result += 1
                elif is_update:
                    # For UPDATE, use matched path
                    new_path = Path(matchedfilename)
                    if new_path.exists():
                        # self._file_service.write_file(new_path, content)
                        logger.info(f"Test UPDATE file: {new_path} (matched: {matchedfilename})")
                        # Enhanced UPDATE logging: calculate and log deltas
                        update_deltas.append(token_delta)
                        update_abs_deltas.append(abs_delta)
                        logger.info(f"UPDATE details for {filename}: Tokens original={orig_tokens}, new={new_tokens}, delta_tokens={abs_delta}, delta_percent={token_delta:.1f}%")
                        result += 1
                    else:
                        logger.warning(f"Path for UPDATE not found: {new_path}")
                else:
                    logger.warning(f"Unknown action for {filename}: new={is_new}, update={is_update}, delete={is_delete}, copy={is_copy}")

            short_compare = parsed.get('short_compare', '')
            if is_delete:
                compare.append(f"{short_compare} (DELETE) -> {matchedfilename}")
            elif is_copy:
                compare.append(f"{short_compare} (COPY) -> {matchedfilename}")
            elif is_new:
                compare.append(f"{short_compare} (NEW) -> {matchedfilename}")
            elif is_update:
                compare.append(f"{short_compare} (UPDATE, delta_tokens={abs_delta}, delta_percent={token_delta:.1f}%) -> {matchedfilename}")
            else:
                compare.append(short_compare)

        # Aggregate UPDATE logging: full compare details with stats (median, avg, peak delta)
        if update_deltas and commit_file:
            if len(update_deltas) > 0:
                delta_median = statistics.median(update_deltas)
                delta_avg = statistics.mean(update_deltas)
                delta_peak = max(update_deltas)
                abs_delta_median = statistics.median(update_abs_deltas)
                abs_delta_avg = statistics.mean(update_abs_deltas)
                abs_delta_peak = max(update_abs_deltas)
                # Log in task_manager format
                logger.info(f"Task UPDATE stats: median_delta_percent={delta_median:.1f}%, avg_delta_percent={delta_avg:.1f}%, peak_delta_percent={delta_peak:.1f}%, median_delta_tokens={abs_delta_median}, avg_delta_tokens={abs_delta_avg}, peak_delta_tokens={abs_delta_peak}")

        return result, compare

    def _backup_and_write_output(self, svc, out_path: Path, content: str):
        if not out_path:
            return
        self._file_service.write_file(out_path, content)
        logger.info(f"Backed up and wrote output to: {out_path}")
        
    def _write_full_ai_output(self, svc, task, ai_out, trunc_code, base_folder: str="" ):
        out_path = self._get_ai_out_path(task, base_folder=base_folder)
        logger.info(f"Write AI out: {out_path} ({len(ai_out.split())} tokens)")
        if out_path:
            self._backup_and_write_output(svc, out_path, ai_out)
    
    def _get_ai_out_path(self, task, base_folder: str = ""):
        out_pat = task.get('out', {}).get('pattern','')
        if not out_pat:
            logger.debug(f"No AI out path: {out_pat}")
            return
        
        logger.debug(f"Resoling AI out path: {out_pat}")
        out_path = self._file_service.resolve_path(out_pat, self._svc)
        logger.debug(f"Resolved AI out path: {out_path}")
        return out_path

    def _process_one(self, task: dict, svc, file_lines_map: dict, todoFilename: str = ""):
        logger.debug(f"_process_one called with task, todoFilename={todoFilename!r}")

        # derive the folder containing the todo.md that was edited
        base_folder = None
        if todoFilename:
            try:
                base_folder = Path(todoFilename).parent
                logger.info("Process base folder:" + str(base_folder))  
            except Exception:
                logger.warning(f"Could not determine parent folder of {todoFilename}")
                base_folder = None

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
        out_path = self._get_ai_out_path(task, base_folder=base_folder)
        prompt = self._prompt_builder.build_task_prompt(task, self._base_dir, str(out_path), knowledge_text, include_text)
        task['_prompt_tokens'] = len(prompt.split())
        task['prompt_tokens'] = task['_prompt_tokens']
        logger.info(f"Prompt tokens: {task['_prompt_tokens']}")
        cur_model = svc.get_cur_model()
        task['cur_model'] = cur_model  # Set cur_model for logging
        st = self.start_task(task, file_lines_map, cur_model)
        task['_start_stamp'] = st  # Ensure start stamp is set

        try:
            ai_out = svc.ask(prompt)
        except Exception as e:
            logger.error(f"LLM call failed: {e}")
            ai_out = ""

        # Added check for ai_out issues
        if not ai_out:
            logger.warning("No AI output generated for task. Running one more time.")
            ai_out = svc.ask(prompt)
            if not ai_out:
                logger.error("No AI output generated for task. Failed.")
            else:
                logger.info(f"AI output length: {len(ai_out)} characters")
        else:
            logger.info(f"AI output length: {len(ai_out)} characters")

        # Write AI output immediately
        self._write_full_ai_output(svc, task, ai_out, 0, base_folder=base_folder)

        # parse and report before writing
        try:
            parsed_files = self.parser.parse_llm_output(ai_out, base_dir=str(basedir), file_service=self._file_service, ai_out_path=out_path, task=task, svc=self._svc) if ai_out else []
        except Exception as e:
            logger.error(f"Parsing AI output failed: {e}")
            parsed_files = []

        commited, compare = 0, []
        success = False
        if parsed_files:
            commited, compare = self._write_parsed_files(parsed_files, task, True, base_folder=base_folder)
            if commited > 0 or len(compare) > 0:
                success = True
        else:
            logger.info("No parsed files to commit.")
        truncation = 0.0  # Assuming no truncation
        ct = self.complete_task(task, file_lines_map, cur_model, truncation, compare, False)
        task['_complete_stamp'] = ct  # Ensure complete stamp is set
        logger.info(f"Task processed: {task['desc']}")

    def _resolve_path(self, frag: str) -> Optional[Path]:
        logger.debug(f"Resolving path: {frag}")
        srf = self._file_service.resolve_path(frag, self._svc)
        return srf

    # ----------------------------------------------------------------
    # 1) drop-in search_files()
    # ----------------------------------------------------------------
    def search_files(self, pattern: str, recursive: bool = False) -> List[str]:
        """
        Find files matching `pattern` under cwd (or self.root_dir if you have one).
        """
        base = getattr(self, 'root_dir', Path.cwd())
        base = Path(base)
        if recursive:
            matches = base.rglob(pattern)
        else:
            matches = base.glob(pattern)
        return [str(p) for p in matches if p.is_file()]

    # ----------------------------------------------------------------
    # 2) drop-in _get_ai_out_path()
    # ----------------------------------------------------------------
    def _get_ai_out_pathb(self, task: Dict[str,Any]) -> Optional[str]:
        """
        task['out'] may be:
          - a string → return it  
          - a dict { pattern:str, recursive:bool } → glob it  
          - missing or empty → return None
        """
        raw = task.get('out')
        if not raw:
            return None

        
        logger.info("raw out candidate:" +raw[0])
        candidate = self._file_service.find_matching_file(raw[0], {'pattern':'*','recursive':True}, self._svc)
        logger.info("out candidate:" +candidate)
        # if they already gave us a literal string path
        
        return candidate

    def _get_ai_out_pathc(self, task, base_folder=None):
        """
        Compute an output Path from task['out'], which may be a string
        or a single‐element list/tuple.  If it's not absolute and
        base_folder is known, we resolve it against base_folder.
        """
        raw = task.get('out')
        if raw is None:
            raise ValueError(f"Task missing 'out': {task!r}")

        # normalize (string or [string])
        if isinstance(raw, (list, tuple)):
            if not raw:
                raise ValueError(f"Empty 'out' list in task {task!r}")
            candidate = raw[0]
        else:
            candidate = raw

        # log safely
        logger.info(f"raw out candidate: {candidate!r}")

        # build path
        out_path = Path(candidate)
        if base_folder and not out_path.is_absolute():
            out_path = base_folder / out_path

        logger.info(f"resolved AI out path: {out_path}")
        return out_path
    # ----------------------------------------------------------------
    # optional: if you also need to extract filenames/flags from LLM headers
    # ----------------------------------------------------------------
    def _extract_filename_and_flag(self, header: str) -> Tuple[Optional[str], Optional[str]]:
        """
        parse a markdown code-fence info string like:
          ```python filename=foo.py flag=XYZ
        """
        import re
        m = re.search(r'```[^\s]*\s+filename=(\S+)(?:\s+flag=(\S+))?', header)
        if not m:
            return None, None
        filename = m.group(1)
        flag     = m.group(2)
        return filename, flag

# original file length: 1042 lines
# updated file length: 1374 lines