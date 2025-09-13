Looking at the files and the task "todo", I can see that the task is asking me to work on the todo functionality. Based on the included files knowledge, I need to fix import issues in several files. Let me examine the patterns and fix the import statements.

# file: robodog/base.py
#!/usr/bin/env python3
"""Base classes and common utilities for robodog services."""
from typing import List, Optional, Dict, Any
from pathlib import Path
import os
import logging

logger = logging.getLogger(__name__)


class BaseService:
    """Base class for all robodog services."""
    
    def __init__(self, roots: List[str] = None):
        self._roots = roots or [os.getcwd()]
    
    @property
    def roots(self) -> List[str]:
        """Get the root directories."""
        return self._roots
    
    @roots.setter
    def roots(self, value: List[str]):
        """Set the root directories."""
        self._roots = value or [os.getcwd()]


class TaskBase:
    """Base class for task-related functionality."""
    
    STATUS_MAP = {' ': 'To Do', '~': 'Doing', 'x': 'Done'}
    REVERSE_STATUS = {v: k for k, v in STATUS_MAP.items()}
    
    @staticmethod
    def format_summary(indent: str, start: str, end: Optional[str] = None,
                      know: Optional[int] = None, prompt: Optional[int] = None,
                      incount: Optional[int] = None, include: Optional[int] = None,
                      cur_model: str = None) -> str:
        """Format a task summary line."""
        parts = [f"started: {start}"]
        if end:
            parts.append(f"completed: {end}")
        if know is not None:
            parts.append(f"knowledge_tokens: {know}")
        if include is not None:
            parts.append(f"include_tokens: {include}")
        if prompt is not None:
            parts.append(f"prompt_tokens: {prompt}")
        if cur_model:
            parts.append(f"cur_model: {cur_model}")
        return f"{indent}  - " + " | ".join(parts) + "\n"

# original file length: 45 lines
# updated file length: 45 lines

# file: robodog/todo.py
#!/usr/bin/env python3
import os
import re
import time
import threading
import logging
import shutil
from datetime import datetime
from pathlib import Path
from typing import List, Optional

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

STATUS_MAP     = {' ': 'To Do', '~': 'Doing', 'x': 'Done'}
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

    def __init__(self, roots: List[str], svc=None):
        self._roots        = roots
        self._file_lines   = {}
        self._tasks        = []
        self._mtimes       = {}
        self._watch_ignore = {}
        self._svc          = svc
        self.parser        = ParseService()
        self._processed    = set()  # track manually processed tasks

        # MVP: parse a `base:` directive from front-matter
        self._base_dir = self._parse_base_dir()

        self._load_all()
        for fn in self._find_files():
            try:
                self._mtimes[fn] = os.path.getmtime(fn)
            except:
                pass

        threading.Thread(target=self._watch_loop, daemon=True).start()

    def _parse_base_dir(self) -> Optional[str]:
        for fn in self._find_files():
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
                        return os.path.normpath(base)
        return None

    def _find_files(self) -> List[str]:
        out = []
        for r in self._roots:
            for dp, _, fns in os.walk(r):
                if self.FILENAME in fns:
                    out.append(os.path.join(dp, self.FILENAME))
        return out

    def _find_files_by_pattern(self, pattern: str, recursive: bool) -> List[str]:
        """Find files matching the given glob pattern."""
        if self._svc:
            return self._svc.search_files(patterns=pattern, recursive=recursive, roots=self._roots)
        return []

    def _find_matching_file(self, filename: str, include_spec: dict) -> Optional[Path]:
        """Find a file by name based on the include pattern."""
        files = self._find_files_by_pattern(include_spec['pattern'], include_spec.get('recursive', False))
        for f in files:
            if Path(f).name == filename:
                return Path(f)
        return None

    def _load_all(self):
        """
        Parse each todo.md into tasks, capturing optional second‐bracket
        write‐flag and any adjacent ```knowledge``` block.
        """
        self._file_lines.clear()
        self._tasks.clear()
        for fn in self._find_files():
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

    def _watch_loop(self):
        # monitor external edits to todo.md
        while True:
            for fn in self._find_files():
                try:
                    mtime = os.path.getmtime(fn)
                except OSError:
                    continue

                # ignore our own writes
                ignore_time = self._watch_ignore.get(fn)
                if ignore_time and abs(mtime - ignore_time) < 0.001:
                    self._watch_ignore.pop(fn, None)
                # new external change?
                elif self._mtimes.get(fn) and mtime > self._mtimes[fn]:
                    logger.debug(f"Detected external change in {fn}, reloading tasks")
                    if not self._svc:
                        continue

                    try:
                        # re-parse all todo.md into self._tasks
                        self._load_all()

                        # 1) tasks to "write": Done + write_flag == To Do
                        write_list = [
                            t for t in self._tasks
                            if STATUS_MAP.get(t['status_char']) == 'Done'
                            and STATUS_MAP.get(t.get('write_flag',' ')) == 'To Do'
                        ]
                        for task in write_list:
                            logger.info(f"Re-emitting output for task: {task['desc']}")
                            # reuse your manual-done handler to re-emit existing file
                            self._process_manual_done(self._svc)

                        # 2) tasks still To Do
                        todo_list = [
                            t for t in self._tasks
                            if STATUS_MAP.get(t['status_char']) == 'To Do'
                        ]
                        if todo_list:
                            logger.info("New To Do tasks found, running next")
                            self.run_next_task(self._svc)

                    except Exception as e:
                        logger.error(f"watch loop error: {e}")

                # update stored mtime
                self._mtimes[fn] = mtime

            time.sleep(1)


    def _watch_loopb(self):
        # monitor external edits to todo.md
        while True:
            for fn in self._find_files():
                try:
                    mtime = os.path.getmtime(fn)
                except:
                    continue
                ignore = self._watch_ignore.get(fn)
                if ignore and abs(mtime - ignore) < 0.001:
                    self._watch_ignore.pop(fn, None)
                elif self._mtimes.get(fn) and mtime > self._mtimes[fn]:
                    logger.debug(f"Detected external change in {fn}, processing manual tasks")
                    if self._svc:
                        try:
                            logger.info("Procress commit.")
                            self._process_manual_done(self._svc)
                            # Add call to run_next_task based on task knowledge checklist
                            todo_list = [t for t in self._tasks if STATUS_MAP.get(t.get('status_char')) == 'To Do']
                            if todo_list:
                                self.run_next_task(self._svc)
                        except Exception as e:
                            logger.error(f"watch loop error: {e}")
                self._mtimes[fn] = mtime
            time.sleep(1)

    def _process_manual_done(self, svc):
        """
        When a task is manually marked Done:
        - with write_flag '-', re-emit existing output to trigger downstream watches
        """
        self._load_all()
        for task in self._tasks:
            key = (task['file'], task['line_no'])
            if STATUS_MAP[task['status_char']] == 'Done' and task.get('write_flag') == ' ':
                out_pat = task.get('out', {}).get('pattern','')
                if out_pat:
                    out_path = self._resolve_path(out_pat)
                    logger.info(f"Manual commit of task: {task['desc']}")
                    if out_path and out_path.exists():
                        content = self._safe_read_file(out_path)
                        # Report on existing file
                        try:
                            parsed = [{'filename': out_path.name, 'content': content, 'tokens': len(content.split())}]
                            self._report_parsed_files(parsed, task)
                        except Exception as e:
                            logger.error(f"Reporting manual file failed: {e}")
                        self._backup_and_write_output(svc, out_path, content)
                self._processed.add(key)

    @staticmethod
    def _write_file(fn: str, file_lines: List[str]):
        Path(fn).write_text(''.join(file_lines), encoding='utf-8')

    @staticmethod
    def _format_summary(indent: str, start: str, end: Optional[str]=None,
                        know: Optional[int]=None, prompt: Optional[int]=None,
                        incount: Optional[int]=None, include: Optional[int]=None,
                        cur_model: str=None) -> str:
        parts = [f"started: {start}"]
        if end:
            parts.append(f"completed: {end}")
        if know is not None:
            parts.append(f"knowledge_tokens: {know}")
        if include is not None:
            parts.append(f"include_tokens: {include}")
        if prompt is not None:
            parts.append(f"prompt_tokens: {prompt}")
        if cur_model:
            parts.append(f"cur_model: {cur_model}")
        return f"{indent}  - " + " | ".join(parts) + "\n"

    @staticmethod
    def _start_task(task: dict, file_lines_map: dict, cur_model: str):
        if STATUS_MAP[task['status_char']] != 'To Do':
            return
        fn, ln = task['file'], task['line_no']
        indent, desc = task['indent'], task['desc']
        file_lines_map[fn][ln] = f"{indent}- [{REVERSE_STATUS['Doing']}] {desc}\n"
        stamp = datetime.utcnow().strftime('%Y-%m-%d %H:%M')
        task['_start_stamp'] = stamp
        know, prompt, incount, include = (task.get(k, 0) for k in
                                          ('_know_tokens','_prompt_tokens','_in_tokens','_include_tokens'))
        summary = TodoService._format_summary(indent, stamp, None,
                                              know, prompt, incount, include, cur_model)
        idx = ln + 1
        if idx < len(file_lines_map[fn]) and \
           file_lines_map[fn][idx].lstrip().startswith('- started:'):
            file_lines_map[fn][idx] = summary
        else:
            file_lines_map[fn].insert(idx, summary)
        TodoService._write_file(fn, file_lines_map[fn])
        task['status_char'] = REVERSE_STATUS['Doing']

    @staticmethod
    def _complete_task(task: dict, file_lines_map: dict, cur_model: str):
        if STATUS_MAP[task['status_char']] != 'Doing':
            return
        fn, ln = task['file'], task['line_no']
        indent, desc = task['indent'], task['desc']
        file_lines_map[fn][ln] = f"{indent}- [{REVERSE_STATUS['Done']}] {desc}\n"
        stamp = datetime.utcnow().strftime('%Y-%m-%d %H:%M')
        start = task.get('_start_stamp','')
        know, prompt, incount, include = (task.get(k, 0) for k in
                                          ('_know_tokens','_prompt_tokens','_in_tokens','_include_tokens'))
        summary = TodoService._format_summary(indent, start, stamp,
                                              know, prompt, incount, include, cur_model)
        idx = ln + 1
        if idx < len(file_lines_map[fn]) and \
           file_lines_map[fn][idx].lstrip().startswith('- started:'):
            file_lines_map[fn][idx] = summary
        else:
            file_lines_map[fn].insert(idx, summary)
        TodoService._write_file(fn, file_lines_map[fn])
        task['status_char'] = REVERSE_STATUS['Done']

    def run_next_task(self, svc):
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
        inc = task.get('include') or {}
        spec = inc.get('pattern','')
        if not spec:
            return ""
        rec = " recursive" if inc.get('recursive') else ""
        full_spec = f"pattern={spec}{rec}"
        try:
            know = svc.include(full_spec) or ""
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
        for parsed in parsed_files:
            orig_name = Path(parsed['filename']).name
            orig_tokens = parsed.get('tokens', 0)
            new_path = None
            new_tokens = 0
            if task and task.get('include'):
                new_path = self._find_matching_file(orig_name, task['include'])
            try:
                if new_path and new_path.exists():
                    content = self._safe_read_file(new_path)
                    new_tokens = len(content.split())
                change = 0.0
                if orig_tokens:
                    change = abs(new_tokens - orig_tokens) / orig_tokens * 100
                msg = f"Compare: '{orig_name}' -> {new_path} | tokens(orig/new) = {orig_tokens}/{new_tokens} | delta={change:.1f}%"
                if change > 40.0:
                    logger.error(msg + " (delta > 40%)")
                    return -2
                elif change > 20.0:
                    logger.warning(msg + " (delta > 20%)")
                    return -1
                else:
                    logger.info(msg)
            except Exception as e:
                logger.error(f"Error reporting parsed file '{orig_name}': {e}")
        return 0


    def _report_parsed_filesb(self, parsed_files: List[dict], task: dict = None):
        """
        Log for each parsed file:
        - original filename (basename)
        - resolved new path
        - tokens(original/new)
        """
        for parsed in parsed_files:
            orig_name = Path(parsed['filename']).name
            orig_tokens = parsed.get('tokens', 0)
            new_path = None
            if task and task.get('include'):
                new_path = self._find_matching_file(orig_name, task['include'])
            try:
                if new_path and new_path.exists():
                    content = self._safe_read_file(new_path)
                    new_tokens = len(content.split())
                else:
                    new_tokens = 0
                logger.info(
                    f"Compare: '{orig_name}' -> {new_path} | tokens(orig/new) = {orig_tokens}/{new_tokens}"
                )
            except Exception as e:
                logger.error(f"Error reporting parsed file '{orig_name}': {e}")

    def _build_prompt(self, task: dict, include_text: str, input_text: str) -> str:
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
        return "\n".join(parts)

    def _backup_and_write_output(self, svc, out_path: Path, content: str):
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

    def _process_one(self, task: dict, svc, file_lines_map: dict):
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
        TodoService._start_task(task, file_lines_map, cur_model)

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

        TodoService._complete_task(task, file_lines_map, cur_model)

    def _resolve_path(self, frag: str) -> Optional[Path]:
        if not frag:
            return None
        f = frag.strip('"').strip('`')
        if self._base_dir and not any(sep in f for sep in (os.sep,'/','\\')):
            candidate = Path(self._base_dir) / f
            return candidate.resolve()
        if self._base_dir and any(sep in f for sep in ('/','\\')):
            candidate = Path(self._base_dir) / Path(f)
            candidate.parent.mkdir(parents=True, exist_ok=True)
            return candidate.resolve()
        search_roots = ([self._base_dir] if self._base_dir else []) + self._roots
        for root in search_roots:
            cand = Path(root) / f
            if cand.is_file():
                return cand.resolve()
        p = Path(f)
        base = Path(self._roots[0]) / p.parent
        base.mkdir(parents=True, exist_ok=True)
        return (base / p.name).resolve()

    def _safe_read_file(self, path: Path) -> str:
        logger.debug(f"Safe read of out: {path.absolute()}")
        try:
            with open(path, 'rb') as bf:
                if b'\x00' in bf.read(1024):
                    raise UnicodeDecodeError("binary", b"", 0, 1, "null")
            return path.read_text(encoding='utf-8')
        except UnicodeDecodeError:
            try:
                return path.read_text(encoding='utf-8', errors='ignore')
            except:
                return ""
        except:
            return ""

__all_classes__ = ["Change","ChangesList","TodoService"]

# original file length: 350 lines
# updated file length: 360 lines

# file: robodog/service.py
#!/usr/bin/env python3
import os
import re
import json
import shutil
import fnmatch
import hashlib
import sys
import threading
import concurrent.futures
import asyncio
from pathlib import Path
import requests
import tiktoken
import yaml
from openai import OpenAI
from playwright.async_api import async_playwright
import logging
from typing import List, Optional
logger = logging.getLogger('robodog.service')

class RobodogService:
    FILENAME = 'todo.md'
    
    def __init__(self, config_path: str, api_key: str = None):
        # --- load YAML config and LLM setup ---
        self._load_config(config_path)
        # --- ensure we always have a _roots attribute ---
        #    If svc.todo is set later by the CLI, include() will pick up svc.todo._roots.
        #    Otherwise we default to cwd.
        self._roots = [os.getcwd()]
        self.stashes = {}
        self._init_llm(api_key)

    def _load_config(self, config_path):
        data = yaml.safe_load(open(config_path, 'r', encoding='utf-8'))
        cfg = data.get("configs", {})
        self.providers = {p["provider"]: p for p in cfg.get("providers", [])}
        self.models = cfg.get("models", [])
        self.mcp_cfg = cfg.get("mcpServer", {})
        self.cur_model = self.models[0]["model"]
        self.stream = self.models[0].get("stream", True)
        self.temperature = 1.0
        self.top_p = 1.0
        self.max_tokens = 1024
        self.frequency_penalty = 0.0
        self.presence_penalty = 0.0

    def _init_llm(self, api_key):
        provider_name = self.model_provider(self.cur_model)
        provider_cfg = self.providers.get(provider_name)

        if not provider_cfg:
            raise RuntimeError(f"No configuration found for provider: {provider_name}")

        self.api_key = (
            api_key
            or os.getenv("OPENAI_API_KEY")
            or provider_cfg.get("apiKey")
        )

        if not self.api_key:
            raise RuntimeError("Missing API key")

        base_url = provider_cfg.get("baseUrl")
        if not base_url:
            raise RuntimeError(f"Missing baseUrl for provider: {provider_name}")

        # Initialize OpenAI client with provider's base URL
        self.client = OpenAI(
            api_key=self.api_key,
            base_url=base_url  # Ensure proper v1 endpoint
        )

    def get_cur_model(self):
        return self.cur_model
    
    def model_provider(self, model_name):
        for m in self.models:
            if m["model"] == model_name:
                return m["provider"]
        return None

    # ————————————————————————————————————————————————————————————
    # CORE LLM / CHAT
    def ask(self, prompt: str) -> str:
        logger.debug(f"ask {prompt!r}")
        messages = [{"role": "user", "content": prompt}]
        resp = self.client.chat.completions.create(
            model=self.cur_model,
            messages=messages,
            temperature=self.temperature,
            top_p=self.top_p,
            frequency_penalty=self.frequency_penalty,
            presence_penalty=self.presence_penalty,
            stream=self.stream,
        )
        spinner = [
            "[•-----]",
            "[-•----]",
            "[--•---]",
            "[---•--]",
            "[----•-]",
            "[-----•]",
            "[----•-]",
            "[---•--]",
            "[--•---]",
            "[-•----]",
            "[•-----]",
            "[-•----]",
            "[--•---]",
            "[---•--]",
            "[----•-]",
            "[-----•]",
            "[----•-]",
            "[---•--]",
            "[--•---]",
            "[-•----]",
            "[•-----]",
            "[-•----]",
            "[--•---]",
            "[---•--]",
            "[----•-]",
            "[-----•]",
            "[----•-]",
            "[---•--]",
            "[--•---]",
            "[-•----]",
        ]
        idx    = 0
        answer = ""
        if self.stream:
            for chunk in resp:
                # accumulate the streamed text
                delta = getattr(chunk.choices[0].delta, "content", None)
                if delta:
                    answer += delta

                # grab the last line (or everything if no newline yet)
                last_line = answer.splitlines()[-1] if "\n" in answer else answer

                # pick our fighter‐vs‐fighter frame
                frame = spinner[idx % len(spinner)]

                # print: [fighters]  [up to 60 chars of last_line][… if truncated]
                sys.stdout.write(
                    f"\r{frame}  {last_line[:60]}{'…' if len(last_line) > 60 else ''}"
                )
                sys.stdout.flush()
                sys.stdout.write(f"\x1b]0;{last_line[:60].strip()}…\x07")
                sys.stdout.flush()
                idx += 1

            # done streaming!
            sys.stdout.write("\n")
        else:
            answer = resp.choices[0].message.content.strip()
        return answer

    # ————————————————————————————————————————————————————————————
    # MODEL / KEY MANAGEMENT
    def list_models(self):
        return [m["model"] for m in self.models]
    
    # ————————————————————————————————————————————————————————————
    # MODEL / KEY MANAGEMENT
    def list_models_about(self):
        return [m["model"] + ": " + m["about"] for m in self.models]

    def set_model(self, model_name: str):
        if model_name not in self.list_models():
            raise ValueError(f"Unknown model: {model_name}")
        self.cur_model = model_name
        self._init_llm(None)

    def set_key(self, provider: str, key: str):
        if provider not in self.providers:
            raise KeyError(f"No such provider {provider}")
        self.providers[provider]["apiKey"] = key

    def get_key(self, provider: str):
        return self.providers.get(provider, {}).get("apiKey")

    # ————————————————————————————————————————————————————————————
    # STASH / POP / LIST / CLEAR / IMPORT / EXPORT
    def stash(self, name: str):
        self.stashes[name] = str

    def pop(self, name: str):
        if name not in self.stashes:
            raise KeyError(f"No stash {name}")
        return self.stashes[name]

    def list_stashes(self):
        return list(self.stashes.keys())

    def clear(self):
        pass

    def import_files(self, glob_pattern: str) -> int:
        count = 0
        knowledge = ""
        for fn in __import__('glob').glob(glob_pattern, recursive=True):
            try:
                txt = open(fn, 'r', encoding='utf-8', errors='ignore').read()
                knowledge += f"\n\n--- {fn} ---\n{txt}"
                count += 1
            except:
                pass
        return knowledge

    def export_snapshot(self, filename: str):
        with open(filename, 'w', encoding='utf-8') as f:
            f.write("=== Chat History ===\n" + getattr(self, 'context', '') + "\n")
            f.write("=== Knowledge ===\n" + getattr(self, 'knowledge', '') + "\n")

    # ————————————————————————————————————————————————————————————
    # NUMERIC PARAMS
    def set_param(self, key: str, value):
        if not hasattr(self, key):
            raise KeyError(f"No such param {key}")
        setattr(self, key, value)

    # ————————————————————————————————————————————————————————————
    # MCP CLIENT (used by CLI to reach server)
    def call_mcp(self, op: str, payload: dict, timeout: float = 30.0) -> dict:
        url = self.mcp_cfg["baseUrl"]
        headers = {
            "Content-Type": "text/plain",
            "Authorization": f"Bearer {self.mcp_cfg['apiKey']}"
        }
        body = f"{op} {json.dumps(payload)}\n"
        r = requests.post(url, headers=headers, data=body, timeout=timeout)
        r.raise_for_status()
        return json.loads(r.text.strip().splitlines()[-1])

    # ————————————————————————————————————————————————————————————
    # /INCLUDE IMPLEMENTATION
    def parse_include(self, text: str) -> dict:
        parts = text.strip().split()
        cmd = {"type": None, "file": None, "dir": None, "pattern": "*", "recursive": False}
        if not parts:
            return cmd
        p0 = parts[0]
        if p0 == "all":
            cmd["type"] = "all"
        elif p0.startswith("file="):
            spec = p0[5:]
            if re.search(r"[*?\[]", spec):
                cmd.update(type="pattern", pattern=spec, recursive=True)
            else:
                cmd.update(type="file", file=spec)
        elif p0.startswith("dir="):
            spec = p0[4:]
            cmd.update(type="dir", dir=spec)
            for p in parts[1:]:
                if p.startswith("pattern="):
                    cmd["pattern"] = p.split("=", 1)[1]
                if p == "recursive":
                    cmd["recursive"] = True
            if re.search(r"[*?\[]", spec):
                cmd.update(type="pattern", pattern=spec, recursive=True)
        elif p0.startswith("pattern="):
            cmd.update(type="pattern", pattern=p0.split("=", 1)[1], recursive=True)
        return cmd

    def include(self, spec_text: str, prompt: str = None):
        inc = self.parse_include(spec_text)
        knowledge = ""
        searches = []
        if inc["type"] == "dir":
            searches.append({
                "root": inc["dir"],
                "pattern": inc["pattern"],
                "recursive": inc["recursive"]
            })
        else:
            pat = inc["pattern"] if inc["type"] == "pattern" else (inc["file"] or "*")
            searches.append({"pattern": pat, "recursive": True})

        matches = []
        for p in searches:
            root = p.get("root")
            # fix: pick up __roots injected from CLI's TodoService, or default to cwd
            if root:
                roots = [root]
            elif hasattr(self, 'todo') and getattr(self.todo, '_roots', None):
                roots = self.todo._roots
            else:
                roots = self._roots

            found = self.search_files(
                patterns=p.get("pattern", "*"),
                recursive=p.get("recursive", True),
                roots=roots
            )
            matches.extend(found)

        if not matches:
            return None

        included_txts = []

        def _read(path):
            content = self.read_file(path)
            return path, content

        with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
            for path, txt in pool.map(_read, matches):
                try:
                    enc = tiktoken.encoding_for_model(self.cur_model)
                except:
                    enc = tiktoken.get_encoding("gpt2")
                wc = len(txt.split())
                tc = len(enc.encode(txt))
                logger.info(f"Included: {path} ({tc} tokens)")
                included_txts.append("# file: " + path)
                included_txts.append(txt)
                combined = "\n".join(included_txts)
                knowledge += "\n" + combined + "\n"

        return knowledge

    # Default exclude directories
    DEFAULT_EXCLUDE_DIRS = {"node_modules", "dist"}

    def search_files(self, patterns="*", recursive=True, roots=None, exclude_dirs=None):
        if isinstance(patterns, str):
            patterns = patterns.split("|")
        else:
            patterns = list(patterns)
        exclude_dirs = set(exclude_dirs or self.DEFAULT_EXCLUDE_DIRS)
        matches = []
        for root in roots or []:
            if not os.path.isdir(root):
                continue
            if recursive:
                for dirpath, dirnames, filenames in os.walk(root):
                    dirnames[:] = [d for d in dirnames if d not in exclude_dirs]
                    for fn in filenames:
                        full = os.path.join(dirpath, fn)
                        for pat in patterns:
                            if fnmatch.fnmatch(full, pat) or fnmatch.fnmatch(fn, pat):
                                matches.append(full)
                                break
            else:
                for fn in os.listdir(root):
                    full = os.path.join(root, fn)
                    if not os.path.isfile(full) or fn in exclude_dirs:
                        continue
                    for pat in patterns:
                        if fnmatch.fnmatch(full, pat) or fnmatch.fnmatch(fn, pat):
                            matches.append(full)
                            break
        return matches

    def list_files(self, roots: List[str]) -> List[str]:
        """List all files in the given roots."""
        files = []
        for root in roots:
            for dirpath, dirnames, filenames in os.walk(root):
                dirnames[:] = [d for d in dirnames if d not in self.DEFAULT_EXCLUDE_DIRS]
                for fn in filenames:
                    full = os.path.join(dirpath, fn)
                    files.append(full)
        return files

    def get_all_contents(self, roots: List[str]) -> Dict[str, str]:
        """Get contents of all files in the given roots."""
        contents = {}
        files = self.list_files(roots)
        for file_path in files:
            try:
                contents[file_path] = self.read_file(file_path)
            except Exception as e:
                logger.error(f"Error reading {file_path}: {e}")
                contents[file_path] = f"ERROR: {e}"
        return contents

    # ————————————————————————————————————————————————————————————
    # /CURL IMPLEMENTATION
    def curl(self, tokens: list):
        pass

    # ————————————————————————————————————————————————————————————
    # /PLAY IMPLEMENTATION
    def play(self, instructions: str):
        pass

    # ————————————————————————————————————————————————————————————
    # MCP-SERVER FILE-OPS
    def read_file(self, path: str):
        return open(path, 'r', encoding='utf-8').read()

    def update_file(self, path: str, content: str):
        open(path, 'w', encoding='utf-8').write(content)

    def create_file(self, path: str, content: str = ""):
        os.makedirs(os.path.dirname(path), exist_ok=True)
        open(path, 'w', encoding='utf-8').write(content)

    def delete_file(self, path: str):
        os.remove(path)

    def append_file(self, path: str, content: str):
        open(path, 'a', encoding='utf-8').write(content)

    def create_dir(self, path: str, mode: int = 0o755):
        os.makedirs(path, mode, exist_ok=True)

    def delete_dir(self, path: str, recursive: bool = False):
        if recursive:
            shutil.rmtree(path)
        else:
            os.rmdir(path)

    def rename(self, src: str, dst: str):
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        os.rename(src, dst)

    def copy_file(self, src: str, dst: str):
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        shutil.copy2(src, dst)

    def _parse_base_dir(self) -> Optional[str]:
            """
            Look for a YAML front-matter block at the top of any todo.md,
            scan it line-by-line for the first line starting with `base:`
            and return its value.
            """
            for fn in self._find_files():
                text = Path(fn).read_text(encoding='utf-8')
                lines = text.splitlines()
                # Must start a YAML block
                if not lines or lines[0].strip() != '---':
                    continue

                # Find end of that block
                try:
                    end_idx = lines.index('---', 1)
                except ValueError:
                    # no closing '---'
                    continue

                # Scan only the lines inside the front-matter
                for lm in lines[1:end_idx]:
                    stripped = lm.strip()
                    if stripped.startswith('base:'):
                        # split on first colon, strip whitespace
                        _, _, val = stripped.partition(':')
                        base = val.strip()
                        if base:
                            return os.path.normpath(base)
                # if we got here, front-matter existed but no base: line → try next file

            return None


    def _find_files(self) -> List[str]:
        out = []
        for r in self._roots:
            for dp, _, fns in os.walk(r):
                if self.FILENAME in fns:
                    out.append(os.path.join(dp, self.FILENAME))
        return out

    
    def checksum(self, path: str):
        h = hashlib.sha256()
        with open(path, 'rb') as f:
            for chunk in iter(lambda: f.read(8192), b''):
                h.update(chunk)
        return h.hexdigest()

# original file length: 300 lines
# updated file length: 310 lines