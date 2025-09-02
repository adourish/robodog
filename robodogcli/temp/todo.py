# file: robodog/cli/todo.py
#!/usr/bin/env python3
# Classes in this module:
#   - Change: Pydantic model describing a single file change
#   - ChangesList: Pydantic root model wrapping a list of Change
#   - TodoService: Service that discovers todo.md files, parses tasks, watches for changes, and drives task execution

import os
import re
import time
import threading
import logging
import shutil
import sys
from datetime import datetime
from pathlib import Path
from typing import List, Optional

import tiktoken
from pydantic import BaseModel, RootModel

logger = logging.getLogger(__name__)

# regexes for parsing markdown tasks
TASK_RE = re.compile(r'^(\s*)-\s*\[(?P<status>[ x~])\]\s*(?P<desc>.+)$')
SUB_RE  = re.compile(
    r'^\s*-\s*(?P<key>include|focus):\s*'
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
        self._roots        = roots
        self._file_lines   = {}
        self._tasks        = []
        self._mtimes       = {}
        self._watch_ignore = {}
        self._svc          = None

        self._load_all()
        for fn in self._find_files():
            try:
                self._mtimes[fn] = os.path.getmtime(fn)
            except Exception:
                pass

        threading.Thread(target=self._watch_loop, daemon=True).start()

    def _find_files(self) -> List[str]:
        out = []
        for r in self._roots:
            for dp, _, fns in os.walk(r):
                if self.FILENAME in fns:
                    out.append(os.path.join(dp, self.FILENAME))
        return out

    def _load_all(self):
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
                    'focus': None,
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
                        task[key] = {'pattern': pat, 'recursive': rec}
                    j += 1
                self._tasks.append(task)
                i = j

    def _watch_loop(self):
        while True:
            for fn in self._find_files():
                try:
                    mtime = os.path.getmtime(fn)
                except Exception:
                    continue
                last   = self._mtimes.get(fn)
                ignore = self._watch_ignore.get(fn)
                if ignore and abs(mtime - ignore) < 0.001:
                    self._watch_ignore.pop(fn, None)
                elif last and mtime > last:
                    logger.info(f"Detected external change in {fn}, running /todo")
                    try:
                        if self._svc:
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
                        know: Optional[int]=None, prompt: Optional[int]=None, total: Optional[int]=None) -> str:
        parts = [f"started: {start}"]
        if end:
            parts.append(f"completed: {end}")
        if know is not None:
            parts.append(f"know_tokens: {know}")
        if prompt is not None:
            parts.append(f"prompt_tokens: {prompt}")
        if total is not None:
            parts.append(f"total_tokens: {total}")
        return f"{indent}  - " + " | ".join(parts) + "\n"

    @staticmethod
    def _start_task(task: dict, file_lines_map: dict):
        if STATUS_MAP[task['status_char']] != 'To Do':
            return
        fn, ln = task['file'], task['line_no']
        indent, desc = task['indent'], task['desc']
        new_char = REVERSE_STATUS['Doing']
        file_lines_map[fn][ln] = f"{indent}- [{new_char}] {desc}\n"
        stamp = datetime.utcnow().strftime('%Y-%m-%d %H:%M')
        task['_start_stamp'] = stamp
        know = task.get('_know_tokens', 0)
        prompt = task.get('_prompt_tokens', 0)
        total = task.get('_token_count', 0)
        summary = TodoService._format_summary(indent, stamp, None, know, prompt, total)
        idx = ln + 1
        if idx < len(file_lines_map[fn]) and file_lines_map[fn][idx].lstrip().startswith('- started:'):
            file_lines_map[fn][idx] = summary
        else:
            file_lines_map[fn].insert(idx, summary)
        TodoService._write_file(fn, file_lines_map[fn])
        task['status_char'] = new_char

    @staticmethod
    def _complete_task(task: dict, file_lines_map: dict):
        if STATUS_MAP[task['status_char']] != 'Doing':
            return
        fn, ln = task['file'], task['line_no']
        indent, desc = task['indent'], task['desc']
        new_char = REVERSE_STATUS['Done']
        file_lines_map[fn][ln] = f"{indent}- [{new_char}] {desc}\n"
        stamp = datetime.utcnow().strftime('%Y-%m-%d %H:%M')
        start = task.get('_start_stamp', '')
        know = task.get('_know_tokens', 0)
        prompt = task.get('_prompt_tokens', 0)
        total = task.get('_token_count', 0)
        summary = TodoService._format_summary(indent, start, stamp, know, prompt, total)
        idx = ln + 1
        if idx < len(file_lines_map[fn]) and file_lines_map[fn][idx].lstrip().startswith('- started:'):
            file_lines_map[fn][idx] = summary
        else:
            file_lines_map[fn].insert(idx, summary)
        TodoService._write_file(fn, file_lines_map[fn])
        task['status_char'] = new_char

    def run_next_task(self, svc):
        self._svc = svc
        self._load_all()
        todo = [t for t in self._tasks if STATUS_MAP[t['status_char']] == 'To Do']
        if not todo:
            logger.info("No To Do tasks found.")
            return
        task = todo[0]
        self._process_one(task, svc, self._file_lines)
        logger.info("Completed one To Do task")

    def _get_token_count(self, text: str) -> int:
        try:
            return len(text.split())
        except:
            return 0

    def _gather_include_knowledge(self, include: dict, svc) -> str:
        raw = include.get('pattern', '').strip('"').strip('`')
        spec = f"pattern={raw}" + (" recursive" if include.get('recursive') else "")
        return svc.include(spec) or ""

    def _resolve_path(self, raw_focus: str) -> Optional[Path]:
        """
        Try to locate the exact focus file:
        1) if absolute and exists → that path
        2) if relative-with-dirs under any root → that path
        3) if bare filename matches any file under include list → use full match
        4) if multi-match → choose shallowest
        """
        p = Path(raw_focus)
        # 1) absolute
        if p.is_absolute() and p.exists():
            return p
        # 2) relative-with-dirs
        if len(p.parts) > 1:
            for root in self._roots:
                cand = root if os.path.isabs(root) else os.path.abspath(root)
                fp = Path(cand) / p
                if fp.exists():
                    return fp
        # 3) bare name → search all included files
        include = self._tasks[0].get('include') or {}
        pat = include.get('pattern')
        rec = include.get('recursive', False)
        matches = []
        for root in self._roots:
            for f in Path(root).rglob(p.name) if rec else Path(root).glob(p.name):
                if f.is_file() and f.name == p.name:
                    matches.append(f)
        if not matches:
            # fallback to search under roots
            for root in self._roots:
                for f in Path(root).rglob(p.name):
                    if f.is_file():
                        matches.append(f)
        if not matches:
            return None
        # shallowest
        matches.sort(key=lambda x: len(x.parts))
        chosen = matches[0]
        if len(matches) > 1:
            logger.info(
                "Ambiguous focus '%s' matched multiple files: %s. Defaulting to %s",
                raw_focus, [str(x) for x in matches], chosen
            )
        return chosen

    def _apply_focus(self, raw_focus: str, ai_out: str, svc):
        """
        Enhanced _apply_focus:
        - loops through all include-pattern files to locate focus
        - uses full absolute path if focus appears among included files
        - creates target file/dirs if needed
        - backs up existing file
        - writes new content via MCP UPDATE_FILE
        """
        # resolve full path
        target = self._resolve_path(raw_focus)
        if not target:
            # default under first root
            target = Path(self._roots[0]) / raw_focus
        target = target.resolve()
        # ensure parent dir
        target.parent.mkdir(parents=True, exist_ok=True)
        # backup existing
        backup_folder = getattr(svc, 'backup_folder', None)
        if backup_folder:
            backup_folder = Path(backup_folder)
            backup_folder.mkdir(parents=True, exist_ok=True)
            if target.exists():
                ts = datetime.utcnow().strftime("%Y%m%d-%H%M%S")
                dest = backup_folder / f"{target.name}-{ts}"
                shutil.copy2(target, dest)
                logger.info("Backup created: %s", dest)
        # write via MCP
        svc.call_mcp("UPDATE_FILE", {"path": str(target), "content": ai_out})
        logger.info("Updated focus file: %s", target)
        # ignore own write
        try:
            self._watch_ignore[str(target)] = os.path.getmtime(str(target))
        except OSError:
            pass

    def _extract_focus(self, focus_spec) -> Optional[str]:
        if not focus_spec:
            return None
        if isinstance(focus_spec, dict):
            raw = focus_spec.get("file") or focus_spec.get("pattern") or ""
        else:
            raw = str(focus_spec)
        raw = raw.strip('"').strip("`")
        for pre in ("file=", "pattern="):
            if raw.startswith(pre):
                raw = raw[len(pre):]
        return raw or None

    def _process_one(self, task: dict, svc, file_lines_map: dict):
        include = task.get("include") or {}
        know = self._gather_include_knowledge(include, svc)
        kt = self._get_token_count(know)
        _kc = ("\n" + task.get('knowledge', '') + "\n") if task.get('knowledge') else ""
        prompt = (
            "knowledge:\n" + know + "\n\n:end knowledge:\n\n"
            "ask: " + task['desc'] + "\n\n"
            "ask and knowledge: " + _kc + "\n\n"
            "task A2: Respond with full code full-file \n"
            "task A3: Tag each code file with a leading line `# file: <path>`\n"
            "task A4: No diffs.\n"
            "task A5: No extra explanation.\n"
            "task A6: No code fences.\n"
            "task A7: Ensure all tasks and sub tasks are completed.\n"
        )
        pt = self._get_token_count(prompt)
        total = kt + pt
        task['_know_tokens'] = kt
        task['_prompt_tokens'] = pt
        task['_token_count'] = total

        TodoService._start_task(task, file_lines_map)
        logger.info("-> Starting task: %s", task['desc'])
        raw_focus = self._extract_focus(task.get("focus"))
        ai_out = svc.ask(prompt)
        if raw_focus:
            self._apply_focus(raw_focus, ai_out, svc)
        else:
            logger.info("No focus file specified; skipping update.")
        TodoService._complete_task(task, file_lines_map)
        logger.info("Completed task: %s", task['desc'])

__all_classes__ = ["Change", "ChangesList", "TodoService"]