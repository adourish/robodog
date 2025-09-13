# file: robodog/file_service.py
#!/usr/bin/env python3
"""File operations and path resolution service."""
import os
import logging
from typing import List, Optional
from pathlib import Path

logger = logging.getLogger(__name__)


class FileService:
    """Handles file operations and path resolution."""
    
    def __init__(self, roots: List[str], base_dir: str = None):
        logger.debug(f"FileService initialized with roots: {roots}, base_dir: {base_dir}")
        self._roots = roots
        self._base_dir = base_dir
    
    @property
    def base_dir(self) -> Optional[str]:
        logger.debug(f"base_dir getter called: {self._base_dir}")
        return self._base_dir
    
    @base_dir.setter
    def base_dir(self, value: str):
        logger.debug(f"base_dir setter called with value: {value}")
        self._base_dir = value
    
    def find_files_by_pattern(self, pattern: str, recursive: bool, svc=None) -> List[str]:
        """Find files matching the given glob pattern."""
        logger.debug(f"find_files_by_pattern called with pattern: {pattern}, recursive: {recursive}, svc: {svc is not None}")
        if svc:
            result = svc.search_files(patterns=pattern, recursive=recursive, roots=self._roots)
            logger.debug(f"Files found via svc: {len(result)} matches")
            return result
        logger.debug("No svc provided, returning empty list")
        return []
    
    def find_matching_file(self, filename: str, include_spec: dict, svc=None) -> Optional[Path]:
        """Find a file by name based on the include pattern."""
        logger.debug(f"find_matching_file called with filename: {filename}, include_spec: {include_spec}, svc: {svc is not None}")
        files = self.find_files_by_pattern(
            include_spec['pattern'], 
            include_spec.get('recursive', False),
            svc
        )
        for f in files:
            if Path(f).name == filename:
                logger.debug(f"Matching file found: {f}")
                return Path(f)
        logger.debug("No matching file found")
        return None
    
    def resolve_path(self, frag: str) -> Optional[Path]:
        """Resolve a file fragment to an absolute path."""
        logger.debug(f"resolve_path called with frag: {frag}")
        if not frag:
            logger.debug("Fragment is empty, returning None")
            return None
        
        f = frag.strip('"').strip('`')
        logger.debug(f"Resolved frag: {f}")
        
        # Simple filename in base_dir
        if self._base_dir and not any(sep in f for sep in (os.sep,'/','\\')):
            candidate = Path(self._base_dir) / f
            logger.debug(f"Simple filename candidate: {candidate}")
            return candidate.resolve()
        
        # Path with separators in base_dir
        if self._base_dir and any(sep in f for sep in ('/','\\')):
            candidate = Path(self._base_dir) / Path(f)
            logger.debug(f"Path with separators candidate: {candidate}")
            candidate.parent.mkdir(parents=True, exist_ok=True)
            return candidate.resolve()
        
        # Search in roots
        search_roots = ([self._base_dir] if self._base_dir else []) + self._roots
        logger.debug(f"Searching in roots: {search_roots}")
        for root in search_roots:
            cand = Path(root) / f
            if cand.is_file():
                logger.debug(f"File found in roots: {cand}")
                return cand.resolve()
        
        # Create in first root
        p = Path(f)
        base = Path(self._roots[0]) / p.parent
        logger.debug(f"Creating in first root parent: {base}")
        base.mkdir(parents=True, exist_ok=True)
        resolved = (base / p.name).resolve()
        logger.debug(f"Resolved path: {resolved}")
        return resolved
    
    def safe_read_file(self, path: Path) -> str:
        """Safely read a file, handling binary files and encoding issues."""
        logger.debug(f"Safe read of: {path.absolute()}")
        try:
            # Check for binary content
            with open(path, 'rb') as bf:
                if b'\x00' in bf.read(1024):
                    logger.debug(f"Detected binary content in {path}, raising UnicodeDecodeError")
                    raise UnicodeDecodeError("binary", b"", 0, 1, "null")
            content = path.read_text(encoding='utf-8')
            logger.debug(f"Successfully read {len(content)} chars from {path}")
            return content
        except UnicodeDecodeError:
            try:
                content = path.read_text(encoding='utf-8', errors='ignore')
                logger.warning(f"Read {path} with errors='ignore', {len(content)} chars")
                return content
            except Exception as e:
                logger.error(f"Failed to read {path}: {e}")
                return ""
        except Exception as e:
            logger.error(f"Failed to read {path}: {e}")
            return ""

    def write_file(self, path: Path, content: str):
        """Write content to the given path, creating directories as needed."""
        logger.debug(f"write_file called with path: {path}, content length: {len(content)}")
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding='utf-8')
            logger.info(f"Written file via FileService: {path} ({len(content.split())} tokens)")
        except Exception as e:
            logger.error(f"FileService.write_file failed for {path}: {e}")

# original file length: 82 lines
# updated file length: 105 lines

# file: robodog/todo.py
"""
Todo management service for robodog.
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
        logger.debug(f"TodoService initialized with roots: {roots}")
        self._roots        = roots
        self._file_lines   = {}
        self._tasks        = []
        self._mtimes       = {}
        self._watch_ignore = {}
        self._svc          = svc
        self.parser        = ParseService()
        self._processed    = set()  # track manually processed tasks
        self._prompt_builder = prompt_builder
        self._task_manager = task_manager
        self._task_parser = task_parser
        self._file_watcher = file_watcher
        self._file_service = file_service
        # MVP: parse a `base:` directive from front-matter
        self._base_dir = self._parse_base_dir()
        logger.debug(f"Parsed base_dir: {self._base_dir}")

        self._load_all()
        for fn in self._find_files():
            try:
                self._mtimes[fn] = os.path.getmtime(fn)
            except:
                pass

        threading.Thread(target=self._watch_loop, daemon=True).start()

    def _parse_base_dir(self) -> Optional[str]:
        logger.debug("_parse_base_dir called")
        for fn in self._find_files():
            logger.debug(f"Checking {fn} for front-matter")
            text = Path(fn).read_text(encoding='utf-8')
            lines = text.splitlines()
            if not lines or lines[0].strip() != '---':
                logger.debug(f"No front-matter in {fn}")
                continue
            try:
                end_idx = lines.index('---', 1)
            except ValueError:
                logger.debug(f"No closing front-matter in {fn}")
                continue
            for lm in lines[1:end_idx]:
                stripped = lm.strip()
                if stripped.startswith('base:'):
                    _, _, val = stripped.partition(':')
                    base = val.strip()
                    if base:
                        logger.debug(f"Found base: {base}")
                        return os.path.normpath(base)
        logger.debug("No base found in any front-matter")
        return None

    def _find_files(self) -> List[str]:
        logger.debug("_find_files called")
        out = []
        for r in self._roots:
            logger.debug(f"Searching in root: {r}")
            for dp, _, fns in os.walk(r):
                if self.FILENAME in fns:
                    found = os.path.join(dp, self.FILENAME)
                    logger.debug(f"Found todo.md: {found}")
                    out.append(found)
        logger.debug(f"Total todo.md files found: {len(out)}")
        return out

    def _find_files_by_pattern(self, pattern: str, recursive: bool) -> List[str]:
        """Find files matching the given glob pattern."""
        logger.debug(f"_find_files_by_pattern called with pattern: {pattern}, recursive: {recursive}")
        if self._svc:
            result = self._svc.search_files(patterns=pattern, recursive=recursive, roots=self._roots)
            logger.debug(f"Files found: {len(result)} matches")
            return result
        logger.debug("No svc provided, returning empty list")
        return []

    def _find_matching_file(self, filename: str, include_spec: dict) -> Optional[Path]:
        """Find a file by name based on the include pattern."""
        logger.debug(f"_find_matching_file called with filename: {filename}, include_spec: {include_spec}")
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
        logger.debug("_load_all called")
        self._file_lines.clear()
        self._tasks.clear()
        for fn in self._find_files():
            logger.debug(f"Loading tasks from {fn}")
            lines = Path(fn).read_text(encoding='utf-8').splitlines(keepends=True)
            self._file_lines[fn] = lines
            i = 0
            while i < len(lines):
                m = TASK_RE.match(lines[i])
                if not m:
                    i += 1
                    continue

                indent     = m.group(1)
                status     = m.group('status')
                write_flag = m.group('write')  # may be None, ' ', '~', or 'x'
                desc       = m.group('desc').strip()
                logger.debug(f"Parsed task: status={status}, write_flag={write_flag}, desc={desc}")
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
                i = j
        logger.debug(f"Total tasks loaded: {len(self._tasks)}")

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
                    logger.debug(f"File {fn} not accessible")
                    continue

                # 1) ignore our own writes
                ignore_time = self._watch_ignore.get(fn)
                if ignore_time and abs(mtime - ignore_time) < 1e-3:
                    self._watch_ignore.pop(fn, None)
                    logger.debug(f"Ignoring our own write to {fn}")

                # 2) external change?
                elif self._mtimes.get(fn) and mtime > self._mtimes[fn]:
                    logger.debug(f"Detected external change in {fn}, reloading tasks")
                    if not self._svc:
                        logger.debug("No svc, skipping watch actions")
                        continue

                    try:
                        # re‐parse all todo.md files into self._tasks
                        self._load_all()

                        # a) re‐emit any tasks that were marked Done + write_flag → To Do
                        for task in self._tasks:
                            status     = task.get('status_char') or ' '
                            write_flag = task.get('write_flag') or ' '
                            if STATUS_MAP.get(status) == 'Done' and STATUS_MAP.get(write_flag) == 'To Do':
                                desc = task.get('desc', '<no desc>')
                               
                                # call your own process routine
                                self._process_manual_done(task, self._svc, self._file_lines)

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

    def _process_manual_done(self, svc, fn=None):
        """
        When a task is manually marked Done:
        - Use the same processing logic as _process_one for consistency
        """
        logger.debug("_process_manual_done called")
        self._load_all()
        # Filter tasks based on fn if provided to fix: does not loop through the files
        filtered_tasks = [t for t in self._tasks if fn is None or t['file'] == fn]
        for task in filtered_tasks:
            key = (task['file'], task['line_no'])
            if key in self._processed:
                logger.debug(f"Task {key} already processed, skipping")
                continue
                
            if STATUS_MAP[task['status_char']] == 'Done' and task.get('write_flag') == ' ':
                logger.info(f"Manual commit of task: {task['desc']}")
                # Use the same code as _process_one for consistency
                out_pat = task.get('out', {}).get('pattern','')
                if not out_pat:
                    logger.debug("No out pattern, skipping")
                    return
                out_path = self._resolve_path(out_pat)
                ai_out = self._file_service.safe_read_file(out_path)
                logger.info(f"Read out file: {out_path} ({len(ai_out.split())} tokens)")
                cur_model = svc.get_cur_model()
                self._task_manager.start_commit_task(task, self._file_lines, cur_model)

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

                self.complete_commit_task(task, self._file_lines, cur_model)


    def write_file(self, filepath: str, file_lines: List[str]):
        """Write file and update watcher."""
        logger.debug(f"write_file called with filepath: {filepath}")
        Path(filepath).write_text(''.join(file_lines), encoding='utf-8')
        if self._file_watcher:
            self._file_watcher.ignore_next_change(filepath)

    def start_task(self, task: dict, file_lines_map: dict, cur_model: str):
        logger.debug(f"start_task called for task: {task['desc']}")
        st = self._task_manager.start_task(task, file_lines_map, cur_model)
        return st
        
    def complete_task(self, task: dict, file_lines_map: dict, cur_model: str):
        logger.debug(f"complete_task called for task: {task['desc']}")
        ct = self._task_manager.complete_task(task, file_lines_map, cur_model)
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
        logger.debug("_gather_include_knowledge called")
        inc = task.get('include') or {}
        spec = inc.get('pattern','')
        if not spec:
            logger.debug("No include pattern, returning empty")
            return ""
        rec = " recursive" if inc.get('recursive') else ""
        full_spec = f"pattern={spec}{rec}"
        try:
            know = svc.include(full_spec) or ""
            logger.debug(f"Include knowledge gathered: {len(know)} chars")
            return know
        except Exception as e:
            logger.error(f"Include failed for spec='{full_spec}': {e}")
            return ""

    def _report_parsed_files(self, parsed_files: List[dict], task: dict = None) -> int:
        """
        Log for each parsed file:
        - original filename (basename)
        - resolved new path
        - tokens(original/new)
        Detect percentage delta and:
        * if delta > 40%: log error, return -2
        * if delta > 20%: log warning, return -1
        Otherwise return 0
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
            try:
                if new_path and new_path.exists():
                    content = self.safe_read_file(new_path)
                    new_tokens = len(content.split())
                change = 0.0
                if orig_tokens:
                    change = abs(new_tokens - orig_tokens) / orig_tokens * 100
                msg = f"Compare: '{orig_name}' -> {new_path} (orig/new)({orig_tokens}/{new_tokens} tokens) delta={change:.1f}%"
                if change > 40.0:
                    logger.error(msg + " (delta > 40%)")
                    result = -2
                elif change > 20.0:
                    logger.warning(msg + " (delta > 20%)")
                    result = -1
                else:
                    logger.info(msg)
            except Exception as e:
                logger.error(f"Error reporting parsed file '{orig_name}': {e}")
        return result

    def _build_prompt(self, task: dict, include_text: str, input_text: str) -> str:
        logger.debug("_build_prompt called")
        parts = [
            "Instructions:",
            "A. Produce one or more complete, runnable code files.",
            "B. For each file, begin with exactly:  # file: <filename>  (use only filenames provided in the task; do not guess or infer).",
            "C. Immediately following that line, emit the full file content—including all imports, definitions, and boilerplate—so it can be copied into a file and run.",
            "D. If multiple files are needed, separate them with a single blank line.",
            "E. You can find the <filename.ext> in the Included files knowledge. You will need to modify these files based on the task description and task knowledge.",
            "G. Use the Task description, included knowledge, and any task-specific knowledge when generating each file.",
            "H. Verify that every file is syntactically correct, self-contained, and immediately executable.",
            "I. Add a comment with the original file length and the updated file length.",
            "J. Only change code that must be changed. Do not remove logging. Do not refactor code unless needed for the task.",
            f"Task description: {task['desc']}",
            ""
        ]
        if include_text:
            parts.append(f"Included files knowledge:\n{include_text}")
        if task.get('knowledge'):
            parts.append(f"Task knowledge:\n{task['knowledge']}")
        prompt = "\n".join(parts)
        logger.debug(f"Prompt built with length: {len(prompt)}")
        return prompt

    def _backup_and_write_output(self, svc, out_path: Path, content: str):
        logger.debug("_backup_and_write_output called")
        if not out_path:
            logger.debug("No out_path, returning")
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
                    logger.debug(f"Backup created: {dest}")
                except Exception as e:
                    logger.error(f"Backup failed: {e}")
        try:
            svc.call_mcp("UPDATE_FILE", {"path": str(out_path), "content": content})
            self._watch_ignore[str(out_path)] = out_path.stat().st_mtime
            logger.debug(f"File updated via MCP: {out_path}")
        except Exception as e:
            logger.error(f"Failed to update {out_path}: {e}")

    def _write_full_ai_output(self, svc, task, ai_out):
        logger.debug("_write_full_ai_output called")
        
        out_pat = task.get('out', {}).get('pattern','')
        if not out_pat:
            logger.debug("No out pattern")
            return
        out_path = self._resolve_path(out_pat)
        logger.info(f"Write: {out_path} ({len(ai_out.split())} tokens)")
        if out_path:
            self._backup_and_write_output(svc, out_path, ai_out)

    def _process_one(self, task: dict, svc, file_lines_map: dict):
        logger.debug(f"_process_one called for task: {task['desc']}")
        basedir = Path(task['file']).parent
        self._base_dir = str(basedir)
        logger.info(f"Base dir: {self._base_dir}")
        include_text = self._gather_include_knowledge(task, svc)
        task['_include_tokens'] = len(include_text.split())
        logger.info(f"Include tokens: {task['_include_tokens']}")
        knowledge_text = task.get('knowledge') or ""
        task['_know_tokens'] = len(knowledge_text.split())
        logger.info(f"Knowledge tokens: {task['_know_tokens']}")
        prompt = self._build_prompt(task, include_text, '')
        task['_prompt_tokens'] = len(prompt.split())
        logger.info(f"Prompt tokens: {task['_prompt_tokens']}")
        cur_model = svc.get_cur_model()
        self.start_task(task, file_lines_map, cur_model)

        try:
            ai_out = svc.ask(prompt)
            logger.debug(f"AI output length: {len(ai_out)}")
        except Exception as e:
            logger.error(f"LLM call failed: {e}")
            ai_out = ""

        # parse and report before writing
        try:
            parsed_files = self.parser.parse_llm_output(ai_out) if ai_out else []
            logger.debug(f"Parsed {len(parsed_files)} files")
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
        logger.debug(f"_resolve_path called with frag: {frag}")
        srf = self._file_service.resolve_path(frag)
        return srf

    def safe_read_file(self, path: Path) -> str:
        logger.debug(f"safe_read_file called with path: {path}")
        srf = self._file_service.safe_read_file(path)
        return srf
        
# original file length: 497 lines
# updated file length: 545 lines