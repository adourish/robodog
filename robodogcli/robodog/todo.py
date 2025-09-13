# Written on 2025-09-13 18:39:11 UTC

#!/usr/bin/env python3
"""
Todo management service for robodog.
# test
"""
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

    def __init__(self, roots: List[str], svc=None, prompt_builder=None, task_manager=None, task_parser=None, file_watcher=None, file_service=None):
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
            logger.info(f"Loaded {task_count} tasks from {fn}")

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
                # Use the same code as _process_one for consistency
                #out_pat = task.get('out', {}).get('pattern','')
                out_spec = task.get('out') or {}
                out_pat   = out_spec.get('pattern', '')
                if not out_pat:
                    logger.warning("No output pattern for task")
                    return
                out_path = self._resolve_path(out_pat)
                ai_out = self._file_service.safe_read_file(out_path)
                logger.info(f"Read out: {out_path} ({len(ai_out.split())} tokens)")
                cur_model = self._svc.get_cur_model()
                self._task_manager.start_commit_task(task, self._file_lines, cur_model)

                try:
                    parsed_files = self.parser.parse_llm_output(ai_out) if ai_out else []
                except Exception as e:
                    logger.error(f"Parsing AI output failed: {e}")
                    parsed_files = []

                commited = 0;
                if parsed_files:
                    commited = self._write_parsed_files(parsed_files, task)
                else:
                    logger.info("No parsed files to report.")

                self._task_manager.complete_commit_task(task, self._file_lines, cur_model, commited)
            else:
                logger.debug("No tasks to commit.")


    def start_task(self, task: dict, file_lines_map: dict, cur_model: str):
        logger.debug(f"Starting task: {task['desc']}")
        st = self._task_manager.start_task(task, file_lines_map, cur_model)
        return st
        
    def complete_task(self, task: dict, file_lines_map: dict, cur_model: str):
        logger.debug(f"Completing task: {task['desc']}")
        ct = self._task_manager.complete_task(task, file_lines_map, cur_model)
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

    # --- new helper methods for token comparison and completeness checks ---
    def _compare_token_delta(self, orig_name: str, orig_tokens: int, new_tokens: int, new_path: Path) -> int:
        change = 0.0
        if orig_tokens:
            change = abs(new_tokens - orig_tokens) / orig_tokens * 100
        msg = f"Compare: '{orig_name}' -> {new_path} (orig/new tokens: {orig_tokens}/{new_tokens}) delta={change:.1f}%"
        if change > 40.0:
            logger.error(msg + " (delta > 40%)")
            return -2
        if change > 20.0:
            logger.warning(msg + " (delta > 20%)")
            return -1
        logger.info(msg)
        return 0
  
    
    def _check_content_completeness(self, content: str, orig_name: str) -> int:
        """
        Check if AI output appears complete.
        - Too few lines (under 3) → error -3
        - Detect added truncation phrases → error -4
        - Skip check for todo.md to avoid false positives
        """
        # Skip completeness check for todo.md as it's not AI-generated content
        if orig_name.lower() == 'todo.md':
            return 0
        
        lines = content.splitlines()
        if len(lines) < 3:
            logger.error("Incomplete output for {orig_name}: only {len_lines} lines".format(
                orig_name=orig_name, len_lines=len(lines)))
            return -3

        truncation_phrases = [
            "rest of class unchanged",
            "rest of file unchanged",
            "remaining lines omitted",
            "remaining code omitted",
            "truncated",
            "continues below",
            "see above for rest",
            "code continues",
            "rest of the code",
            "additional code omitted",
            "file truncated",
            "remaining parts unchanged",
            "see rest below",
            "code omitted for brevity",
            "file continues elsewhere",
            "other methods unchanged"
        ]
        lower = content.lower()
        for phrase in truncation_phrases:
            if phrase in lower:
                logger.error("Truncation indication found for {orig_name}: '{phrase}'".format(
                    orig_name=orig_name, phrase=phrase))
                return -4

        return 0
    
    # --- modified report method ---
    def _report_parsed_files(self, parsed_files: List[dict], task: dict = None) -> int:
        """
        Log for each parsed file: compare tokens; return error code
        """
        logger.debug("_report_parsed_files called")
        result = 0
        for parsed in parsed_files:
            orig_name = Path(parsed['filename']).name
            orig_tokens = parsed.get('tokens', 0)
            new_path = None
            new_tokens = 0
            if task and task.get('include'):
                new_path = self._find_matching_file(orig_name, task['include'])
            if new_path and new_path.exists():
                txt = self._file_service.safe_read_file(new_path)
                new_tokens = len(txt.split())
            code = self._compare_token_delta(orig_name, orig_tokens, new_tokens, new_path)
            if code < result or result == 0:
                result = code
        return result

    # --- modified write-and-report method ---
    def _write_parsed_files(self, parsed_files: List[dict], task: dict = None) -> int:
        """
        Write parsed files and compare tokens, with completeness check.
        """
        logger.debug("_write_parsed_files called")
        result = 0
        for parsed in parsed_files:
            orig_name = Path(parsed['filename']).name
            content = parsed['content']
            # completeness check
            comp = self._check_content_completeness(content, orig_name)
            if comp < 0:
                result = comp
                continue
            # determine tokens after write
            if task and task.get('include'):
                new_path = self._find_matching_file(orig_name, task['include'])
            else:
                new_path = None
            # write content
            if new_path:
                self._file_service.write_file(new_path, content)
                new_txt = self._file_service.safe_read_file(new_path)
                new_tokens = len(new_txt.split())
            else:
                new_tokens = 0
            orig_tokens = parsed.get('tokens', 0)
            code = self._compare_token_delta(orig_name, orig_tokens, new_tokens, new_path)
            # use positive code as success indicator 1
            if code >= 0:
                result = 1
            else:
                result = code
        return result

    def _backup_and_write_output(self, svc, out_path: Path, content: str):
        logger.debug(f"Backing up and writing to {out_path}")
        if not out_path:
            return
        bf = getattr(svc, 'backup_folder', None)
        if bf:
            bak = Path(bf)
            bak.mkdir(parents=True, exist_ok=True)
            if out_path.exists():
                ts = datetime.utcnow().strftime("%Y%m%d-%H%M%S")
                dest = bak / f"{out_path.name}-{ts}"
                try:
                    shutil.copy2(out_path, dest)
                except Exception:
                    pass
        try:
            svc.call_mcp("UPDATE_FILE", {"path": str(out_path), "content": content})
            self._watch_ignore[str(out_path)] = out_path.stat().st_mtime
        except Exception as e:
            logger.error(f"Failed to update {out_path}: {e}")

    def _write_full_ai_output(self, svc, task, ai_out):
        
        out_pat = task.get('out', {}).get('pattern','')
        if not out_pat:
            return
        out_path = self._resolve_path(out_pat)
        logger.info(f"Write: {out_path} ({len(ai_out.split())} tokens)")
        if out_path:
            self._backup_and_write_output(svc, out_path, ai_out)
    
    def _write_full_parsed_ai_output(self, svc, path, ai_out):
        
        logger.info(f"Write: {path} ({len(ai_out.split())} tokens)")
        if path:
            self._file_service.write_file(path, ai_out)

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
        prompt = self._prompt_builder.build_task_prompt(task, include_text, '')
        task['_prompt_tokens'] = len(prompt.split())
        logger.info(f"Prompt tokens: {task['_prompt_tokens']}")
        cur_model = svc.get_cur_model()
        self.start_task(task, file_lines_map, cur_model)

        try:
            ai_out = svc.ask(prompt)
        except Exception as e:
            logger.error(f"LLM call failed: {e}")
            ai_out = ""

        # parse and report before writing
        try:
            parsed_files = self.parser.parse_llm_output(ai_out) if ai_out else []
        except Exception as e:
            logger.error(f"Parsing AI output failed: {e}")
            parsed_files = []

        if parsed_files:
            self._report_parsed_files(parsed_files, task)
            self._write_full_ai_output(svc, task, ai_out)
        else:
            logger.info("No parsed files to report.")

        self.complete_task(task, file_lines_map, cur_model)

    def _resolve_path(self, frag: str) -> Optional[Path]:
        logger.debug(f"Resolving path: {frag}")
        srf = self._file_service.resolve_path(frag)
        return srf

    def safe_read_file(self, path: Path) -> str:
        logger.debug(f"Safe reading file: {path}")
        srf = self._file_service.safe_read_file(path)
        return srf
        
# original file length: 497 lines
# updated file length: 637 lines