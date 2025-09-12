# file: todo.py
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

from parse_service import ParseService  # Added import for ParseService

logger = logging.getLogger(__name__)

TASK_RE = re.compile(r'^(\s*)-\s*\[(?P<status>[ x~])\]\s*(?P<desc>.+)$')
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

    def __init__(self, roots: List[str]):
        self._roots       = roots
        self._file_lines  = {}
        self._tasks       = []
        self._mtimes      = {}
        self._watch_ignore = {}
        self._svc         = None
        self.parser       = ParseService()  # Initialize ParseService instance

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

    def _load_allb(self):
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
                indent = m.group(1)
                status = m.group('status')
                desc   = m.group('desc').strip()
                task = {
                    'file': fn,
                    'line_no': i,
                    'indent': indent,
                    'status_char': status,
                    'desc': desc,
                    'include': None,
                    'out': None,
                    'in': None,
                    'knowledge': None,
                    '_start_stamp': None,
                    '_know_tokens': 0,
                    '_prompt_tokens': 0,
                    '_token_count': 0,
                }
                j = i + 1
                while j < len(lines) and lines[j].startswith(indent + '  '):
                    ms = SUB_RE.match(lines[j])
                    if ms:
                        key = ms.group('key')
                        pat = ms.group('pattern').strip('"').strip('`')
                        rec = bool(ms.group('rec'))
                        if key == 'focus':
                            task['out'] = {'pattern': pat, 'recursive': rec}
                        else:
                            task[key] = {'pattern': pat, 'recursive': rec}
                    j += 1
                self._tasks.append(task)
                i = j

    def _load_all(self):
        """
        Parse each todo.md into tasks, capturing any adjacent ```knowledge``` block.
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

                indent = m.group(1)
                status = m.group('status')
                desc   = m.group('desc').strip()
                task   = {
                    'file': fn,
                    'line_no': i,
                    'indent': indent,
                    'status_char': status,
                    'desc': desc,
                    'include': None,
                    'in': None,
                    'out': None,
                    'knowledge': '',      # <- always present
                    '_start_stamp': None,
                    '_know_tokens': 0,
                    '_in_tokens': 0,
                    '_token_count': 0,
                }

                # scan sub‐entries (include, in, focus)
                j = i + 1
                while j < len(lines) and lines[j].startswith(indent + '  '):
                    sub = SUB_RE.match(lines[j])
                    if sub:
                        key = sub.group('key')
                        pat = sub.group('pattern').strip('"').strip('`')
                        rec = bool(sub.group('rec'))
                        task[key] = {'pattern': pat, 'recursive': rec}
                    j += 1

                # ——— NEW: capture ```knowledge``` fence immediately after task
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
        while True:
            for fn in self._find_files():
                try:
                    mtime = os.path.getmtime(fn)
                except:
                    continue
                last   = self._mtimes.get(fn)
                ignore = self._watch_ignore.get(fn)
                if ignore and abs(mtime - ignore) < 0.001:
                    self._watch_ignore.pop(fn, None)
                elif last and mtime > last:
                    logger.info(f"Detected external change in {fn}, running /todo")
                    if self._svc:
                        try:
                            self.run_next_task(self._svc)
                        except Exception as e:
                            logger.error(f"watch loop error: {e}")
                self._mtimes[fn] = mtime
            time.sleep(1)

    @staticmethod
    def _write_file(fn: str, file_lines: List[str]):
        Path(fn).write_text(''.join(file_lines), encoding='utf-8')

    @staticmethod
    def _format_summary(indent: str, start: str, end: Optional[str]=None,
                        know: Optional[int]=None, prompt: Optional[int]=None, incount: Optional[int]=None,
                        include: Optional[int]=None, cur_model: str=None) -> str:
        parts = [f"started: {start}"]
        if end:
            parts.append(f"completed: {end}")
        if know is not None:
            parts.append(f"knowledge_tokens: {know}")  # Fixed typo here
        if include is not None:
            parts.append(f"include_tokens: {include}")
        if incount is not None:
            parts.append(f"in_tokens: {incount}")  # Fixed typo here
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
                               ('_know_tokens','_prompt_tokens','_in_tokens', '_include_tokens'))  # Fixed keys here
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
                               ('_know_tokens','_prompt_tokens','_in_tokens', '_include_tokens'))  # Fixed keys here, and added start
        summary = TodoService._format_summary(indent, start, stamp,
                                              know, prompt, incount, include, cur_model)  # Fixed to include start and end
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

    def _get_token_count(self, text: str) -> int:
        return len(text.split())

    def _gather_include_knowledge(self, include: dict, svc) -> str:
        raw = include.get('pattern','').strip('"').strip('`')
        spec = f"pattern={raw}" + \
               (" recursive" if include.get('recursive') else "")
        logger.debug("Gather include knowledge: %s", spec)
        return svc.include(spec) or ""

    def _resolve_path(self, frag: str) -> Optional[Path]:
        """
        Resolve a fragment (pattern/file spec) to an absolute Path,
        logging each step to help debug why base_dir may be skipped.
        """
        logger.debug("-> _resolve_path called with frag=%r, base_dir=%r, roots=%s",
                    frag, self._base_dir, self._roots)
        if not frag:
            logger.info("   no fragment provided -> returning None")
            return None

        # strip quotes/backticks
        f = frag.strip('"').strip('`')
        logger.debug("   normalized fragment to %r", f)

        # 1) bare filename under base_dir
        if self._base_dir and not any(sep in f for sep in (os.sep, '/', '\\')):
            candidate = Path(self._base_dir) / f
            logger.debug("   branch 1: treating as bare filename under base_dir -> %s", candidate)
            return candidate.resolve()

        # 2) any relative path under base_dir
        if self._base_dir and any(sep in f for sep in ('/', '\\')):
            candidate = Path(self._base_dir) / Path(f)
            logger.debug("   branch 2: treating as relative path under base_dir -> %s", candidate)
            candidate.parent.mkdir(parents=True, exist_ok=True)
            return candidate.resolve()

        # 3) search under base_dir first, then all roots
        search_roots = ([self._base_dir] if self._base_dir else []) + self._roots
        logger.debug("   branch 3: searching for existing file under roots -> %s", search_roots)
        for root in search_roots:
            cand = Path(root) / f
            logger.debug("      checking %s", cand)
            if cand.is_file():
                logger.debug("      found existing file at %s", cand)
                return cand.resolve()

        # 4) not found: create under first configured root
        p = Path(f)
        base = Path(self._roots[0]) / p.parent
        target = base / p.name
        logger.debug("   branch 4: not found, will create under first root -> %s", target)
        base.mkdir(parents=True, exist_ok=True)
        return target.resolve()

    def _process_oneb(self, task: dict, svc, file_lines_map: dict):
        _basedir = os.path.dirname(task['file']);
        logger.info("Task todo file: %s", _basedir)
        self._base_dir =_basedir
        include = self._gather_include_knowledge(task.get('include') or {}, svc)
        knowledge = task['knowledge']
        task['_know_tokens'] = self._get_token_count(include)
        inp = task.get('in', {}).get('pattern', '')
        in_path = self._resolve_path(inp)
        logger.info(f"Input path resolved to: {in_path}")        
        out_pat = task.get('out', {}).get('pattern', '')
        out_path = self._resolve_path(out_pat)
        logger.info(f"Output path resolved to: {out_path}")

        incontent = inp
        if inp:
            pth = self._resolve_path(inp)
            if pth and pth.is_file():
                incontent = pth.read_text(encoding='utf-8')
        task['_include_tokens'] = self._get_token_count(include)
        task['_in_count']  = self._get_token_count(incontent)
        task['_knowledge_tokens'] = self._get_token_count(knowledge)
        task['_prompt_tokens'] = self._get_token_count(incontent + include + knowledge)
        logger.info("Task include count: %s", task['_include_tokens'])
        logger.info("Task in count: %s", task['_in_count'])
        logger.info("Task knowledge count: %s", task['_knowledge_tokens'])
        logger.info("Task prompt count: %s", task['_prompt_tokens'])
        _cur_model = svc.get_cur_model()
        TodoService._start_task(task, file_lines_map, _cur_model)

        prompt_sections = [
            "1. Generate output matching the following structure:",
            "2. Each file should start with: # file: <filename>",
            "3. Followed by the file content",
            "4. Separate files with blank lines",
            "",
            "Task description: " + task['desc'],
            ""
        ]

        if in_path and in_path.exists():
            prompt_sections.append(f"Input file ({in_path}):\n" + incontent)
        
        if task.get('include'):
            included = svc.include(task['include']['pattern'])
            prompt_sections.append(f"Included knowledge:\n{included}")
        
        if task['knowledge']:
            prompt_sections.append(f"Task knowledge:\n{task['knowledge']}")

        prompt = "\n".join(prompt_sections)
        logger.debug(f"Generated prompt:\n{prompt}")
        
        ai_out = svc.ask(prompt)

        if out_path:
            target = self._resolve_path(out_path)
            bf = getattr(svc, 'backup_folder', None)
            if bf:
                backup = Path(bf)
                backup.mkdir(parents=True, exist_ok=True)
                if target.exists():
                    ts = datetime.utcnow().strftime("%Y%m%d-%H%M%S")
                    dest = backup / f"{target.name}-{ts}"
                    shutil.copy2(target, dest)
                    logger.info("Backup created: %s", dest)
            svc.call_mcp("UPDATE_FILE", {"path": str(target),
                                         "content": ai_out})
            try:
                self._watch_ignore[str(target)] = \
                    os.path.getmtime(str(target))
            except:
                pass
            logger.info("Updated focus file: %s", target)
        else:
            logger.info("No focus file specified; skipping write.")

        TodoService._complete_task(task, file_lines_map, _cur_model)

    def _safe_read_file(self, path: Path) -> str:
        """
        Read a file as UTF-8, skip binary or undecodable content,
        fall back to ignoring errors if necessary.
        """
        try:
            # Quick binary check:
            with open(path, 'rb') as bf:
                if b'\x00' in bf.read(1024):
                    raise UnicodeDecodeError("binary", b"", 0, 1, "null byte")
            return path.read_text(encoding='utf-8')
        except UnicodeDecodeError:
            logger.warning(f"Skipping non-text or binary file: {path}")
            try:
                return path.read_text(encoding='utf-8', errors='ignore')
            except Exception as e:
                logger.error(f"Failed to read {path} with ignore: {e}")
                return ""
        except Exception as e:
            logger.error(f"Failed to read file {path}: {e}")
            return ""

    def _gather_include_knowledge(self, task: dict, svc) -> str:
        """
        Use svc.include to gather all 'include' knowledge,
        catch and log any errors.
        """
        inc = task.get('include') or {}
        spec = inc.get('pattern', '')
        if not spec:
            return ""
        rec = " recursive" if inc.get('recursive') else ""
        full_spec = f"pattern={spec}{rec}"
        logger.debug(f"Gathering include knowledge with spec: {full_spec}")
        try:
            know = svc.include(full_spec) or ""
            logger.info(f"Included knowledge tokens: {len(know.split())}")
            return know
        except Exception as e:
            logger.error(f"Include failed for spec='{full_spec}': {e}")
            return ""

    def _read_input(self, task: dict) -> str:
        """
        Resolve and read the 'in:' file for the task, if any.
        """
        inp = task.get('in', {}).get('pattern', '')
        if not inp:
            return ""
        # resolve path using existing resolver
        pth = self._resolve_path(inp)
        if not pth or not pth.exists():
            logger.warning(f"No input file found for pattern '{inp}'")
            return ""
        text = self._safe_read_file(pth)
        logger.info(f"Read input file {pth} ({len(text.split())} words)")
        return text

    def _build_prompt(self, task: dict, include_text: str, input_text: str) -> str:
        """
        Build the LLM prompt in a structured way.
        """
        parts = [
            "1. Generate output matching the following structure:",
            "2. Each file should start with: # file: <filename>",
            "3. Followed by the file content",
            "4. Separate files with blank lines",
            "5. You must give full drop in code files, do not remove any content from the output file",
            "",
            f"Task description: {task['desc']}",
            ""
        ]
        if input_text:
            parts.append(f"Input file:\n{input_text}")
        if include_text:
            parts.append(f"Included knowledge:\n{include_text}")
        if task.get('knowledge'):
            parts.append(f"Task knowledge:\n{task['knowledge']}")
        prompt = "\n".join(parts)
        logger.debug(f"Built prompt ({len(prompt)} chars)")
        return prompt

    def _backup_and_write_output(self, svc, out_path: Path, content: str):
        """
        Back up the old focus file (if any), then write new content via MCP.
        """
        if not out_path:
            logger.info("No focus file specified; skipping write.")
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
                    logger.info(f"Backup created: {dest}")
                except Exception as e:
                    logger.error(f"Failed to back up {out_path}: {e}")
        # now write via MCP
        try:
            svc.call_mcp("UPDATE_FILE", {"path": str(out_path), "content": content})
            # avoid triggering our own watcher
            self._watch_ignore[str(out_path)] = out_path.stat().st_mtime
            logger.info(f"Updated focus file: {out_path}")
        except Exception as e:
            logger.error(f"Failed to update focus file {out_path}: {e}")

    def _process_one(self, task: dict, svc, file_lines_map: dict):
        """
        Refactored Task processor:
          1) gather include
          2) read input
          3) build prompt
          4) call LLM
          5) parse AI output and write multiple files
          6) finalize task in todo.md
        """
        # ensure base_dir is set correctly
        basedir = Path(task['file']).parent
        logger.info(f"Processing To Do '{task['desc']}' in {basedir}")
        self._base_dir = str(basedir)

        # 1) gather include knowledge
        include_text = self._gather_include_knowledge(task, svc)
        task['_include_tokens'] = len(include_text.split())

        # 2) read input file
        input_text = self._read_input(task)
        task['_in_tokens'] = len(input_text.split())

        # 3) existing fenced knowledge
        knowledge_text = task.get('knowledge') or ""
        task['_know_tokens'] = len(knowledge_text.split())

        # 4) build prompt
        prompt = self._build_prompt(task, include_text, input_text)
        task['_prompt_tokens'] = len(prompt.split())

        # 5) mark task as Doing
        cur_model = svc.get_cur_model()
        TodoService._start_task(task, file_lines_map, cur_model)

        # 6) call LLM
        try:
            ai_out = svc.ask(prompt)
        except Exception as e:
            logger.error(f"LLM call failed: {e}")
            ai_out = ""

        # 7) parse AI output and process each file
        if ai_out:
            parsed_files = self.parser.parse_llm_output(ai_out)
            for parsed in parsed_files:
                # Find real filename by searching for matching files
                lm_filename = parsed['filename']
                file_path = self._resolve_path(lm_filename)
                if file_path:
                    logger.info(f"Matched LM filename '{lm_filename}' to real path: {file_path}")
                    self._backup_and_write_output(svc, file_path, parsed['content'])
                else:
                    # If not found, create new file at default location
                    # Assume under first root with the LM filename as relative path
                    relative_path = Path(lm_filename)
                    if self._base_dir:
                        default_path = Path(self._base_dir) / relative_path
                        default_path.parent.mkdir(parents=True, exist_ok=True)
                        logger.warning(f"No matching file found for '{lm_filename}', creating at {default_path}")
                        self._backup_and_write_output(svc, default_path, parsed['content'])
                    else:
                        logger.warning(f"No base_dir and no matching file for '{lm_filename}'")

        # 9) mark task Done
        TodoService._complete_task(task, file_lines_map, cur_model)

    def _parse_ai_output(self, ai_out: str):
        """
        Parse the AI output into an array of objects with filename and content,
        then find real filenames by searching matching files.
        
        Returns list of dicts: [{'filename': str, 'content': str, 'real_path': Path or None}]
        """
        # Use the parser to get initial objects
        parsed_files = self.parser.parse_llm_output(ai_out)
        enhanced = []
        for parsed in parsed_files:
            lm_filename = parsed['filename']
            # Find real filename by resolving the path
            real_path = self._resolve_path(lm_filename)
            enhanced.append({
                'filename': lm_filename,
                'content': parsed['content'],
                'real_path': real_path
            })
            logger.debug(f"Parsed file: {lm_filename}, resolved to: {real_path}")
        return enhanced
        
__all_classes__ = ["Change","ChangesList","TodoService"]