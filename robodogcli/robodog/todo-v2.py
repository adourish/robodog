Below is a drop‐in replacement for your existing `todo.py` (saved as e.g. `todo-v2.py`). The only change from your current implementation is that **whenever** we write a backup of a focus file, we now also log the folder in which diffs/backups are stored:

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
        self._roots = roots
        self._file_lines = {}
        self._tasks = []
        self._mtimes = {}
        self._watch_ignore = {}
        self._svc = None

        self._load_all()
        for fn in self._find_files():
            try:
                self._mtimes[fn] = os.path.getmtime(fn)
            except:
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
        file_lines_map[fn][ln] = f"{indent}- [{REVERSE_STATUS['Doing']}] {desc}\n"
        stamp = datetime.utcnow().strftime('%Y-%m-%d %H:%M')
        task['_start_stamp'] = stamp
        know   = task.get('_know_tokens', 0)
        prompt = task.get('_prompt_tokens', 0)
        total  = task.get('_token_count', 0)
        summary = TodoService._format_summary(indent, stamp, None, know, prompt, total)
        idx = ln + 1
        if idx < len(file_lines_map[fn]) and file_lines_map[fn][idx].lstrip().startswith('- started:'):
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
        start  = task.get('_start_stamp', '')
        know   = task.get('_know_tokens', 0)
        prompt = task.get('_prompt_tokens', 0)
        total  = task.get('_token_count', 0)
        summary = TodoService._format_summary(indent, start, stamp, know, prompt, total)
        idx = ln + 1
        if idx < len(file_lines_map[fn]) and file_lines_map[fn][idx].lstrip().startswith('- started:'):
            file_lines_map[fn][idx] = summary
        else:
            file_lines_map[fn].insert(idx, summary)
        TodoService._write_file(fn, file_lines_map[fn])
        task['status_char'] = REVERSE_STATUS['Done']

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
        return len(text.split())

    def _gather_include_knowledge(self, include: dict, svc) -> str:
        raw = include.get('pattern','').strip('"').strip('`')
        spec = f"pattern={raw}" + (" recursive" if include.get('recursive') else "")
        logger.info("Gather include knowledge: %s", spec)
        return svc.include(spec) or ""

    def _resolve_path(self, frag: str) -> Optional[Path]:
        if not frag:
            return None
        frag = frag.strip('"').strip('`')
        if not any(sep in frag for sep in (os.sep,'/','\\')):
            logger.warning("Bare-filename '%s' not supported; include a directory.", frag)
            return None
        # try existing files under each root
        for root in self._roots:
            candidate = Path(root) / frag
            if candidate.is_file():
                return candidate.resolve()
        # otherwise create it under the first root
        p = Path(frag)
        base = Path(self._roots[0]) / p.parent
        base.mkdir(parents=True, exist_ok=True)
        return (base / p.name).resolve()

    def _process_one(self, task: dict, svc, file_lines_map: dict):
        # 1) Gather knowledge
        include = task.get("include") or {}
        knowledge = self._gather_include_knowledge(include, svc)
        task['_know_tokens'] = self._get_token_count(knowledge)

        # 2) Read “in” file
        raw_in = task.get("in",{}).get("pattern")
        input_content = ""
        if raw_in:
            inp = self._resolve_path(raw_in)
            if inp and inp.is_file():
                input_content = inp.read_text(encoding='utf-8')
        task['_prompt_tokens'] = self._get_token_count(input_content + knowledge)
        task['_token_count']  = task['_know_tokens'] + task['_prompt_tokens']

        # --- DEBUG LOG the inputs & knowledge ---
        logger.debug("----- Todo Task Input -----\n%s", input_content or "<no input>")
        logger.debug("---- Todo Knowledge Gathered ----\n%s", knowledge or "<no knowledge>")

        # 3) Mark Doing
        TodoService._start_task(task, file_lines_map)

        # 4) Build & log prompt
        segments = []
        if input_content:
            segments.append("input:\n" + input_content + "\n\n:end input:")
        if knowledge:
            segments.append("knowledge:\n" + knowledge + "\n\n:end knowledge:")
        segments.append("ask: " + task['desc'])
        prompt = "\n\n".join(segments)
        logger.info("---- Prompt Sent to LLM ----\n%s", prompt)

        # 5) Invoke LLM & log output
        ai_out = svc.ask(prompt)
        logger.info("---- AI Output Received (%d chars) ----", len(ai_out))
        logger.debug("%s", ai_out)

        # 6) Write to focus file (with backup + diff‐folder log)
        raw_out = task.get("out",{}).get("pattern")
        if raw_out:
            target = self._resolve_path(raw_out)
            backup_folder = getattr(svc, 'backup_folder', None)
            if backup_folder:
                bf = Path(backup_folder)
                bf.mkdir(parents=True, exist_ok=True)
                # Log the diff/backup‐folder location
                logger.info("Diff/backup folder location: %s", bf.resolve())
                if target.exists():
                    ts = datetime.utcnow().strftime("%Y%m%d-%H%M%S")
                    dest = bf / f"{target.name}-{ts}"
                    shutil.copy2(target, dest)
                    logger.info("Backup created: %s", dest)
            svc.call_mcp("UPDATE_FILE", {"path": str(target), "content": ai_out})
            # prevent watch‐loop from immediately retriggering on this write
            try:
                self._watch_ignore[str(target)] = os.path.getmtime(str(target))
            except:
                pass
            logger.info("Updated focus file: %s", target)
        else:
            logger.info("No focus file specified; skipping write.")

        # 7) Mark Done
        TodoService._complete_task(task, file_lines_map)

__all_classes__ = ["Change","ChangesList","TodoService"]
```

What changed?

- Inside `_process_one`, after creating the backup directory, we now do:
  
  ```python
  logger.info("Diff/backup folder location: %s", bf.resolve())
  ```
  
  so you always see exactly where your old versions are being stored. Everything else is identical to your existing logic. 

To turn on full logging, make sure your root logger is at DEBUG or INFO:

```python
import logging
logging.getLogger().setLevel(logging.DEBUG)
```

This will show you the folder path every time a task writes a backup.