
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
    r'\s*(?P<desc>.+)$'            # space + desc
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
        logger.info(f"Initializing TodoService with roots: {roots}")
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
        
        logger.info(f"Base directory parsed: {self._base_dir}")

        self._load_all()
        for fn in self._find_files():
            try:
                self._mtimes[fn] = os.path.getmtime(fn)
                logger.debug(f"Initial mtime for {fn}: {self._mtimes[fn]}")
            except Exception as e:
                logger.warning(f"Could not get mtime for {fn}: {e}")
                pass

        threading.Thread(target=self._watch_loop, daemon=True).start()
        logger.info("TodoService initialized successfully")

    def _parse_base_dir(self) -> Optional[str]:
        logger.debug("_parse_base_dir called")
        for fn in self._find_files():
            logger.debug(f"Parsing front-matter from {fn}")
            text = Path(fn).read_text(encoding='utf-8')
            lines = text.splitlines()
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

    def _find_files_by_pattern(self, pattern: str, recursive: bool) -> List[str]:
        """Find files matching the given glob pattern."""
        logger.debug(f"_find_files_by_pattern called with pattern: {pattern}, recursive: {recursive}")
        if self._svc:
            return self._svc.search_files(patterns=pattern, recursive=recursive, roots=self._roots)
        logger.warning("Svc not available for file search")
        return []

    def _find_matching_file(self, filename: str, include_spec: dict) -> Optional[Path]:
        """Find a file by name based on the include pattern."""
        logger.debug(f"_find_matching_file called for {filename}")
        files = self._find_files_by_pattern(include_spec['pattern'], include_spec.get('recursive', False))
        for f in files:
            if Path(f).name == filename:
                logger.debug(f"Matching file found: {f}")
                return Path(f)
        logger.debug("No matching file found")
        return None

    def _load_all(self):
        """
        Parse each todo.md into tasks, capturing optional second‐bracket
        write‐flag and any adjacent ```knowledge``` block.
        """
        logger.debug("_load_all called: Reloading all tasks from files")
        self._file_lines.clear()
        self._tasks.clear()
        for fn in self._find_files():
            logger.debug(f"Parsing tasks from {fn}")
            lines = Path(fn).read_text(encoding='utf-8').splitlines(keepends=True)
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
                desc       = m.group('desc').strip()
                task       = {
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
                    '_start_stamp': None,
                    '_know_tokens': 0,
                    '_in_tokens': 0,
                    '_prompt_tokens': 0,
                    '_include_tokens': 0,
                }

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
                    logger.debug(f"Detected external change in {fn}, reloading tasks")
                    if not self._svc:
                        logger.warning("Svc not available, skipping change processing")
                        # nothing to do if service not hooked up
                        continue

                    try:
                        # re‐parse all todo.md files into self._tasks
                        self._load_all()
                        todo = [t for t in self._tasks if STATUS_MAP[t['status_char']] == 'Done']
                                         
                        self._process_manual_done(todo)

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

    def _process_manual_done(self, todo: list):
        """
        When a task is manually marked Done:
        - Use the same processing logic as _process_one for consistency
        """
        logger.debug(f"_process_manual_done called with {len(todo)} tasks")
        for task in todo:
            if STATUS_MAP[task['status_char']] == 'Done' and task.get('write_flag') == ' ':
                logger.info(f"Manual commit of task: {task['desc']}")
                out_path = self._get_ai_out_path(task)
                ai_out = self._file_service.safe_read_file(out_path)
                logger.info(f"Read out: {out_path} ({len(ai_out.split())} tokens)")
                cur_model = self._svc.get_cur_model()
                self._task_manager.start_commit_task(task, self._file_lines, cur_model)

                try:
                    basedir = Path(task['file']).parent
                    parsed_files = self.parser.parse_llm_output(ai_out, base_dir=str(basedir), file_service=self._file_service, ai_out_path=out_path) if ai_out else []
                except Exception as e:
                    logger.error(f"Parsing AI output failed: {e}")
                    parsed_files = []

                commited, compare = 0, []
                if parsed_files:
                    commited, compare = self._write_parsed_files(parsed_files, task, True)
                else:
                    logger.info("No parsed files to report.")

                self._task_manager.complete_commit_task(task, self._file_lines, cur_model, commited, compare)
            else:
                logger.debug("No tasks to commit.")

    def start_task(self, task: dict, file_lines_map: dict, cur_model: str):
        logger.debug(f"Starting task: {task['desc']}")
        st = self._task_manager.start_task(task, file_lines_map, cur_model)
        return st
        
    def complete_task(self, task: dict, file_lines_map: dict, cur_model: str, truncation: float, compare: Optional[List[str]] = None):
        logger.debug(f"Completing task: {task['desc']}")
        ct = self._task_manager.complete_task(task, file_lines_map, cur_model, truncation, compare)
        return ct
            
    def run_next_task(self, svc):
        logger.info("run_next_task called")
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
        """
        logger.debug("_write_parsed_files called")
        result = 0
        compare: List[str] = []
        for parsed in parsed_files:
            orig_name = Path(parsed['filename']).name
            content = parsed['content']
            # completeness check
           
            new_tokens = parsed.get('new_tokens', 0)
            original_tokens = parsed.get('original_tokens', 0)
            delta_tokens = parsed.get('delta_tokens', 0)
            matchedfilename = parsed.get('matchedfilename', '')
            new_path = matchedfilename
            
            if new_path:
                if commit_file == True:
                    self._file_service.write_file(new_path, content)

            new_tokens = len(content.split())
            short_compare = parsed.get('short_compare', '')
            long_compare = parsed.get('long_compare', '')
            result = parsed.get('result', '')
            compare.append(f"{short_compare}")

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
        out_path = self._resolve_path(out_pat)
        return out_path
    


    def _process_one(self, task: dict, svc, file_lines_map: dict):
        logger.info(f"Processing task: {task['desc']}")
        basedir = Path(task['file']).parent
        self._base_dir = str(basedir)
        logger.debug(f"Base dir: {self._base_dir}")
        include_text = self._gather_include_knowledge(task, svc)
        task['_include_tokens'] = len(include_text.split())
        logger.info(f"Include tokens: {task['_include_tokens']}")
        knowledge_text = task.get('knowledge') or ""
        task['_know_tokens'] = len(knowledge_text.split())
        logger.info(f"Knowledge tokens: {task['_know_tokens']}")
        out_path = self._get_ai_out_path(task)
        prompt = self._prompt_builder.build_task_prompt(task, self._base_dir, str(out_path), knowledge_text, include_text)
        task['_prompt_tokens'] = len(prompt.split())
        logger.info(f"Prompt tokens: {task['_prompt_tokens']}")
        cur_model = svc.get_cur_model()
        self.start_task(task, file_lines_map, cur_model)

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

        # parse and report before writing
        try:
            parsed_files = self.parser.parse_llm_output(ai_out, base_dir=str(basedir), file_service=self._file_service, ai_out_path=out_path) if ai_out else []
        except Exception as e:
            logger.error(f"Parsing AI output failed: {e}")
            parsed_files = []

        trunc_code = 0
        compare: List[str] = []
        if parsed_files:
            _trunc_code, compare = self._write_parsed_files(parsed_files, task, False)
            trunc_code = _trunc_code
            self._write_full_ai_output(svc, task, ai_out, trunc_code)
        else:
            logger.info("No parsed files to report.")

        self.complete_task(task, file_lines_map, cur_model, trunc_code, compare)

    def _resolve_path(self, frag: str) -> Optional[Path]:
        logger.debug(f"Resolving path: {frag}")
        srf = self._file_service.resolve_path(frag)
        return srf

    def safe_read_file(self, path: Path) -> str:
        logger.debug(f"Safe reading file: {path}")
        srf = self._file_service.safe_read_file(path)
        return srf
        
# original file length: 497 lines
# updated file length: 503 lines