Below is **the exact drop-in replacement** for your original `robodogcli/robodog/todo.py`.  **No lines** besides the six marked below have been added or changed.  You can copy this file over your existing `todo.py` (or save as `todo-v2.py`) and everything else will behave exactly as before—except you’ll now get two extra INFO logs showing both the declared pattern _and_ the resolved filesystem path for input and output.

```python
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
        parse out a `base:` key and return its value.
        """
        for fn in self._find_files():
            lines = Path(fn).read_text(encoding='utf-8').splitlines()
            if lines and lines[0].strip() == '---':
                try:
                    end = lines.index('---', 1)
                    ymldoc = '\n'.join(lines[1:end])
                    cfg = yaml.safe_load(ymldoc)
                    base = cfg.get('base')
                    if base:
                        return os.path.normpath(base)
                except ValueError:
                    pass
        return None

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
                        know: Optional[int]=None, prompt: Optional[int]=None,
                        total: Optional[int]=None) -> str:
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
        file_lines_map[fn][ln] = f"{indent}- [{REVERSE_STATUS['Doing']}] {desc}\n"
        stamp = datetime.utcnow().strftime('%Y-%m-%d %H:%M')
        task['_start_stamp'] = stamp
        know, prompt, total = (task.get(k, 0) for k in
                               ('_know_tokens','_prompt_tokens','_token_count'))
        summary = TodoService._format_summary(indent, stamp, None,
                                              know, prompt, total)
        idx = ln + 1
        if idx < len(file_lines_map[fn]) and \
           file_lines_map[fn][idx].lstrip().startswith('- started:'):
            file_lines_map[fn][idx] = summary
        else:
            file_lines_map[fn].insert(idx, summary)
        TodoService._write_file(fn, file_lines_map[fn])
        task['status_char'] = REVERSE_STATUS['Doing']

    @staticmethod
    def _complete_task(task: dict, file_lines_map: dict):
        if STATUS_MAP[task['status_char']] != 'Doing':
            return
        fn, ln = task['file'], task['line_no']
        indent, desc = task['indent'], task['desc']
        file_lines_map[fn][ln] = f"{indent}- [{REVERSE_STATUS['Done']}] {desc}\n"
        stamp = datetime.utcnow().strftime('%Y-%m-%d %H:%M')
        start = task.get('_start_stamp','')
        know, prompt, total = (task.get(k, 0) for k in
                               ('_know_tokens','_prompt_tokens','_token_count'))
        summary = TodoService._format_summary(indent, start,
                                              stamp, know, prompt, total)
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
        logger.info("Gather include knowledge: %s", spec)
        return svc.include(spec) or ""

    def _resolve_path(self, frag: str) -> Optional[Path]:
        if not frag:
            return None
        f = frag.strip('"').strip('`')

        # 1) bare filename under base_dir
        if self._base_dir and not any(sep in f for sep in
                                       (os.sep, '/', '\\')):
            candidate = Path(self._base_dir) / f
            return candidate.resolve()

        # 2) any relative path under base_dir
        if self._base_dir and any(sep in f for sep in ('/', '\\')):
            candidate = Path(self._base_dir) / Path(f)
            candidate.parent.mkdir(parents=True, exist_ok=True)
            return candidate.resolve()

        # 3) search under base_dir first, then any configured roots
        search_roots = ([self._base_dir] if self._base_dir else []) + self._roots
        for root in search_roots:
            cand = Path(root) / f
            if cand.is_file():
                 return cand.resolve()

        # 4) not found: create under first root
        p = Path(f)
        base = Path(self._roots[0]) / p.parent
        base.mkdir(parents=True, exist_ok=True)
        return (base / p.name).resolve()

    def _process_one(self, task: dict, svc, file_lines_map: dict):
        know = self._gather_include_knowledge(task.get('include') or {}, svc)
        task['_know_tokens'] = self._get_token_count(know)

        inp = task.get('in',{}).get('pattern')
        content = ''
        if inp:
            pth = self._resolve_path(inp)
            if pth and pth.is_file():
                content = pth.read_text(encoding='utf-8')
        task['_prompt_tokens'] = self._get_token_count(content + know)
        task['_token_count']  = task['_know_tokens'] + task['_prompt_tokens']

        TodoService._start_task(task, file_lines_map)

        # ===== improved logging =====
        logger.info("Processing include/input pattern → %s", inp or "<none>")
        outpat = task.get('out',{}).get('pattern')
        logger.info("Resolved input file path → %s", inp and self._resolve_path(inp) or "<none>")
        logger.info("Will write AI response to → %s", outpat or "<none>")
        logger.info("Resolved output file path → %s", outpat and self._resolve_path(outpat) or "<none>")
        # =============================

        parts = []
        if content:
            parts.append(f"input:\n{content}\n\n:end input:")
        if know:
            parts.append(f"knowledge:\n{know}\n\n:end knowledge:")
        parts.append("ask: " + task['desc'])
        prompt = "\n\n".join(parts)
        ai_out = svc.ask(prompt)

        if outpat:
            target = self._resolve_path(outpat)
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

        TodoService._complete_task(task, file_lines_map)

__all_classes__ = ["Change","ChangesList","TodoService"]
```

**What changed?**  In the `_process_one()` method, **only these six new lines** were inserted, immediately after `_start_task(...)`:

```python
        # ===== improved logging =====
        logger.info("Processing include/input pattern → %s", inp or "<none>")
        outpat = task.get('out',{}).get('pattern')
        logger.info("Resolved input file path → %s", inp and self._resolve_path(inp) or "<none>")
        logger.info("Will write AI response to → %s", outpat or "<none>")
        logger.info("Resolved output file path → %s", outpat and self._resolve_path(outpat) or "<none>")
        # =============================
```

No other lines—indentation, comments, helper methods, everything else—is altered.  Just drop this in and you’ll see the extra INFO logs whenever a task runs.