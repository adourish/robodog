# file: todo.py
#!/usr/bin/env python3
"""Todo task management and execution service."""
import os
import re
import time
import threading
import logging
import shutil
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Dict

import tiktoken
from pydantic import BaseModel, RootModel
import yaml   # ensure PyYAML is installed

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
                                         
                        self._process_manual_done(done_tasks)

                        # b) then run the next To Do task, if any remain
                        next_todos = [
                            t for t in self._tasks
                            if STATUS_MAP.get(t.get('status_char') or ' ') == 'To Do'
                        ]
                        if next_todos:
                            logger.info("New To Do tasks found, running next")
                            self.run_next_task(self._svc)

                    except Exception as e:
                        logger.error(f"watch loop error: {e}")

                # 3) update our stored mtime
                self._mtimes[fn] = mtime

            time.sleep(1)

    def _process_manual_done(self, done_tasks: list):
        """
        When a task is manually marked Done:
        - Use the same processing logic as _process_one for consistency
        - Ensure token values are populated from parsed metadata or defaults
        - After successful commit, update status to [x][x]
        - Do not re-write the output file during commit
        """
        logger.debug(f"_process_manual_done called with {len(done_tasks)} tasks")
        for task in done_tasks:
            if STATUS_MAP[task['status_char']] == 'Done' and task.get('write_flag') == ' ':
                logger.info(f"Manual commit of task: {task['desc']}")
                # Tokens should already be populated from _load_all parsing
                # But ensure they are set (fallback to 0 if not)
                task['knowledge_tokens'] = task.get('knowledge_tokens', task.get('_know_tokens', 0))
                task['include_tokens'] = task.get('include_tokens', task.get('_include_tokens', 0))
                task['prompt_tokens'] = task.get('prompt_tokens', task.get('_prompt_tokens', 0))
                # Ensure start stamp is set before task_manager call
                if task.get('_start_stamp') is None:
                    task['_start_stamp'] = datetime.now().isoformat()
                # Read the existing ai_out from out_path (do not regenerate or re-write)
                out_path = self._get_ai_out_path(task)
                if not out_path or not out_path.exists():
                    logger.warning(f"Output path not found for manual commit: {out_path}")
                    continue
                ai_out = self._file_service.safe_read_file(out_path)
                logger.info(f"Read existing out: {out_path} ({len(ai_out.split())} tokens)")
                # Parse the existing ai_out
                cur_model = self._svc.get_cur_model()
                st = self.start_task(task, self._file_lines, cur_model)
                # Preserve or set stamp if task_manager returns None
                if st is None:
                    st = task['_start_stamp']
                task['_start_stamp'] = st

                try:
                    basedir = Path(task['file']).parent
                    self._file_service.base_dir = str(basedir)
                    parsed_files = self.parser.parse_llm_output(ai_out, base_dir=str(basedir), file_service=self._file_service, ai_out_path=out_path, task=task, svc=self._svc) if ai_out else []
                except Exception as e:
                    logger.error(f"Parsing existing AI output failed: {e}")
                    parsed_files = []

                commited, compare = 0, []
                success = False
                if parsed_files:
                    commited, compare = self._write_parsed_files(parsed_files, task, True)
                    if commited > 0 or len(compare) > 0:
                        success = True
                else:
                    logger.info("No parsed files to commit.")

                # After successful commit, update status to [x][x]
                if success:
                    file_lines = self._file_lines[task['file']]
                    line_no = task['line_no']
                    indent = task['indent']
                    # Reconstruct full line with metadata
                    clean_desc = task['desc']
                    metadata_parts = []
                    if task.get('_start_stamp'):
                        metadata_parts.append(f"started: {task['_start_stamp']}")
                    if task.get('_complete_stamp'):
                        metadata_parts.append(f"completed: {task['_complete_stamp']}")
                    if task.get('knowledge_tokens', 0) > 0:
                        metadata_parts.append(f"knowledge: {task['knowledge_tokens']}")
                    if task.get('include_tokens', 0) > 0:
                        metadata_parts.append(f"include: {task['include_tokens']}")
                    if task.get('prompt_tokens', 0) > 0:
                        metadata_parts.append(f"prompt: {task['prompt_tokens']}")
                    full_desc = clean_desc
                    if metadata_parts:
                        full_desc += ' | ' + ' | '.join(metadata_parts)
                    # Update the line to [x][x] full_desc
                    new_line = f"{indent}- [x][x] {full_desc}\n"
                    file_lines[line_no] = new_line
                    # Write back to file
                    self._file_service.write_file(Path(task['file']), ''.join(file_lines))
                    logger.info(f"Updated task status to [x][x] for successful commit: {task['desc']}")
                    # Ignore our own write in watcher
                    self._watch_ignore[task['file']] = os.path.getmtime(task['file'])

                ct = self.complete_task(task, self._file_lines, cur_model, 0, compare)
                # Preserve or set stamp if task_manager returns None
                if ct is None:
                    ct = datetime.now().isoformat()
                task['_complete_stamp'] = ct
            else:
                logger.debug("No tasks to commit.")

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
        
    def complete_task(self, task: dict, file_lines_map: dict, cur_model: str, truncation: float, compare: Optional[List[str]] = None):
        logger.debug(f"Completing task: {task['desc']}")
        # Ensure tokens are populated before calling task_manager
        task['knowledge_tokens'] = task.get('knowledge_tokens', task.get('_know_tokens', 0))
        task['include_tokens'] = task.get('include_tokens', task.get('_include_tokens', 0))
        task['prompt_tokens'] = task.get('prompt_tokens', task.get('_prompt_tokens', 0))
        ct = self._task_manager.complete_task(task, file_lines_map, cur_model, truncation, compare)
        # Preserve or set stamp if task_manager returns None
        if ct is None:
            ct = datetime.now().isoformat()
        task['_complete_stamp'] = ct  # Ensure complete stamp is set on task
        return ct
            
    def run_next_task(self, svc):
        logger.debug("run_next_task called")
        self._svc = svc
        self._load_all()
        todo = [t for t in self._tasks
                if STATUS_MAP[t['status_char']] == 'To Do']
        if not todo:
            logger.info("No To Do tasks found.")
            return
        self._process_one(todo[0], svc, self._file_lines)
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
    def _write_parsed_files(self, parsed_files: List[dict], task: dict = None, commit_file: bool= False) -> tuple[int, List[str]]:
        """
        Write parsed files and compare tokens using parse_service object properties, return results and compare list
        For NEW files, resolve path relative to todo.md folder (base_dir) and create full path.
        For DELETE files, delete the matched file if it exists; prioritize DELETE over NEW even if both flags are set.
        matchedfilename remains relative for reporting.
        """
        logger.debug("_write_parsed_files called")
        result = 0
        compare: List[str] = []
        basedir = Path(task['file']).parent if task else Path.cwd()
        self._file_service.base_dir = str(basedir)  # Set base_dir for relative path resolution
        for parsed in parsed_files:
            content = parsed['content']
            # completeness check
            filename = parsed.get('filename', '')
            matchedfilename = parsed.get('matchedfilename', '')  # Relative path for NEW files
            relative_path = parsed.get('relative_path', filename)
            is_new = parsed.get('new', False)
            is_delete = parsed.get('delete', False)
            is_copy = parsed.get('copy', False)
            is_update = parsed.get('update', False)
            new_path = None

            # Prioritize DELETE: delete if flagged, regardless of other flags
            if is_delete:
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
                    dst_path = self._file_service.resolve_path(relative_path)  # Destination relative
                    if src_path.exists():
                        self._file_service.copy_file(src_path, dst_path)
                        logger.info(f"Copied file: {src_path} -> {dst_path} (relative: {relative_path})")
                        result += 1
                    else:
                        logger.warning(f"Source for COPY not found: {src_path}")
                elif is_new:
                    # For NEW, resolve relative to base_dir
                    new_path = self._file_service.resolve_path(relative_path)
                    self._file_service.write_file(new_path, content)
                    logger.info(f"Created NEW file at: {new_path} (relative: {relative_path}, matched: {matchedfilename})")
                    result += 1
                elif is_update:
                    # For UPDATE, use matched path
                    new_path = Path(matchedfilename)
                    if new_path.exists():
                        self._file_service.write_file(new_path, content)
                        logger.info(f"Updated file: {new_path} (matched: {matchedfilename})")
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
                compare.append(f"{short_compare} (UPDATE) -> {matchedfilename}")
            else:
                compare.append(short_compare)

        return result, compare

    def _backup_and_write_output(self, svc, out_path: Path, content: str):
        
        if not out_path:
            return
        self._file_service.write_file(out_path, content)
        
    def _write_full_ai_output(self, svc, task, ai_out, trunc_code):
        out_path = self._get_ai_out_path(task)
        logger.info(f"Write AI out: {out_path} ({len(ai_out.split())} tokens)")
        if out_path:
            self._backup_and_write_output(svc, out_path, ai_out)
    
    def _get_ai_out_path(self, task):
        out_pat = task.get('out', {}).get('pattern','')
        if not out_pat:
            return
        out_path = srf = self._file_service.resolve_path(out_pat)
        return out_path
    
    def _process_one(self, task: dict, svc, file_lines_map: dict):
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
        out_path = self._get_ai_out_path(task)
        prompt = self._prompt_builder.build_task_prompt(task, self._base_dir, str(out_path), knowledge_text, include_text)
        task['_prompt_tokens'] = len(prompt.split())
        task['prompt_tokens'] = task['_prompt_tokens']
        logger.info(f"Prompt tokens: {task['_prompt_tokens']}")
        cur_model = svc.get_cur_model()
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
        self._write_full_ai_output(svc, task, ai_out, 0)

        # parse and report before writing
        try:
            parsed_files = self.parser.parse_llm_output(ai_out, base_dir=str(basedir), file_service=self._file_service, ai_out_path=out_path, task=task, svc=self._svc) if ai_out else []
        except Exception as e:
            logger.error(f"Parsing AI output failed: {e}")
            parsed_files = []

        trunc_code = 0
        compare: List[str] = []
        success = bool(parsed_files and (len(parsed_files) > 0))
        write_flag = task.get('write_flag')
        auto_commit = write_flag is None or write_flag != ' '

        # Update task line to [x][ ] (committed or pending)
        file_lines = file_lines_map[task['file']]
        line_no = task['line_no']
        indent = task['indent']
        # Reconstruct full line with metadata
        clean_desc = task['desc']
        metadata_parts = []
        if task.get('_start_stamp'):
            metadata_parts.append(f"started: {task['_start_stamp']}")
        if task.get('knowledge_tokens', 0) > 0:
            metadata_parts.append(f"knowledge: {task['knowledge_tokens']}")
        if task.get('include_tokens', 0) > 0:
            metadata_parts.append(f"include: {task['include_tokens']}")
        if task.get('prompt_tokens', 0) > 0:
            metadata_parts.append(f"prompt: {task['prompt_tokens']}")
        full_desc = clean_desc
        if metadata_parts:
            full_desc += ' | ' + ' | '.join(metadata_parts)
        # Mark as [x][ ] initially
        commit_line = f"{indent}- [x][ ] {full_desc}\n"
        file_lines[line_no] = commit_line
        self._file_service.write_file(Path(task['file']), ''.join(file_lines))
        logger.info(f"Updated task status to [x][ ] : {task['desc']}")
        self._watch_ignore[task['file']] = os.path.getmtime(task['file'])

        # If auto-commit and success, update to [x][x] and call complete_task
        if auto_commit and success:
            ct = datetime.now().isoformat()
            task['_complete_stamp'] = ct
            metadata_parts.append(f"completed: {ct}")
            full_desc = clean_desc
            if metadata_parts:
                full_desc += ' | ' + ' | '.join(metadata_parts)
            done_line = f"{indent}- [x][x] {full_desc}\n"
            file_lines[line_no] = done_line
            self._file_service.write_file(Path(task['file']), ''.join(file_lines))
            logger.info(f"Auto-committed and updated to [x][x]: {task['desc']}")
            self._watch_ignore[task['file']] = os.path.getmtime(task['file'])
            self.complete_task(task, file_lines_map, cur_model, trunc_code, compare)
        elif not auto_commit:
            logger.info(f"Manual commit pending for task (write_flag=' '): {task['desc']}")

    def _resolve_path(self, frag: str) -> Optional[Path]:
        logger.debug(f"Resolving path: {frag}")
        srf = self._file_service.resolve_path(frag)
        return srf

# original file length: 1042 lines
# updated file length: 1308 lines