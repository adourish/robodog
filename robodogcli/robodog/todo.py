# file: robodog/cli/todo.py
#!/usr/bin/env python3
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
FOC_RE  = re.compile(
    r'^\s*-\s*(?P<key>focus):\s*'
    r'(?:file=)?(?P<pattern>"[^"]+"|`[^`]+`|\S+)'
    r'(?:\s+(?P<rec>recursive))?'
)

STATUS_MAP     = {' ': 'To Do', '~': 'Doing', 'x': 'Done'}
REVERSE_STATUS = {v: k for k, v in STATUS_MAP.items()}

if sys.platform.startswith("win"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except AttributeError:
        import io
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
        sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')


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

                if j < len(lines) and lines[j].lstrip().startswith('```'):
                    k = j + 1
                    code_lines = []
                    while k < len(lines) and not lines[k].lstrip().startswith('```'):
                        code_lines.append(lines[k])
                        k += 1
                    task['knowledge'] = ''.join(code_lines).rstrip('\n')
                    j = k + 1

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
        line_idx = ln + 1
        summary = TodoService._format_summary(indent, stamp, None, know, prompt, total)
        if line_idx < len(file_lines_map[fn]) and file_lines_map[fn][line_idx].lstrip().startswith('- started:'):
            file_lines_map[fn][line_idx] = summary
        else:
            file_lines_map[fn].insert(line_idx, summary)
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
        line_idx = ln + 1
        summary = TodoService._format_summary(indent, start, stamp, know, prompt, total)
        if line_idx < len(file_lines_map[fn]) and file_lines_map[fn][line_idx].lstrip().startswith('- started:'):
            file_lines_map[fn][line_idx] = summary
        else:
            file_lines_map[fn].insert(line_idx, summary)
        TodoService._write_file(fn, file_lines_map[fn])
        task['status_char'] = new_char

    def run_next_task(self, svc):
        self._svc = svc
        self._load_all()
        for t in self._tasks:
            logger.debug(f"Task: {t['desc']}  Status: {STATUS_MAP[t['status_char']]}")

        todo = [t for t in self._tasks if STATUS_MAP[t['status_char']] == 'To Do']
        if not todo:
            logger.info("No To Do tasks found.")
            return
        task = todo[0]
        logger.info(f"Task: {task['desc']}  Status: {STATUS_MAP[task['status_char']]}")

        self._process_one(task, svc, self._file_lines)
        logger.info("Completed one To Do task")

    def _get_token_count(self, text: str) -> int:
        try:
            return len(text.split())
        except:
            return 0

    def _gather_include_knowledge(self, include: dict, svc) -> str:
        raw = include.get('pattern', '').strip('"').strip('`')
        if raw.startswith('pattern='):
            raw = raw[len('pattern='):]
        spec = f"pattern={raw}" + (" recursive" if include.get('recursive') else "")
        logger.info("Gather include knowledge: " + spec)
        return svc.include(spec) or ""

    def _resolve_path(self, raw_focus: str) -> str | None:
        """
        Try to turn raw_focus into exactly one existing file path.
        Returns absolute path or None if nothing found.
        Raises ValueError if more than one bare‐filename match found.
        """
        p = Path(raw_focus)

        # 1) Absolute path
        if p.is_absolute():
            return str(p) if p.exists() else None

        # 2) Relative path with at least one directory component
        if len(p.parts) > 1:
            for root in self._roots:
                candidate = Path(root) / p
                if candidate.exists():
                    return str(candidate)
            return None

        # 3) Bare filename: search all roots
        matches = []
        for root in self._roots:
            for f in Path(root).rglob(p.name):
                if f.is_file() and f.name == p.name:
                    matches.append(f)

        if not matches:
            return None

        if len(matches) > 1:
            # Option A: pick the shallowest and warn
            matches.sort(key=lambda f: len(f.parts))
            chosen = matches[0]
            logger.warning(
                "Ambiguous focus '%s' matched multiple files: %s. "
                "Defaulting to %s",
                raw_focus,
                [str(m) for m in matches],
                chosen,
            )
            return str(chosen)

            # Option B: instead of warning, raise an error
            # raise ValueError(f"Ambiguous focus '{raw_focus}', found: {matches}")

        return str(matches[0])


    def _resolve_pathb(self, path: str) -> Optional[str]:
        p = path.strip('"').strip('`')
        if os.path.isabs(p) and os.path.isfile(p):
            return p
        for root in self._roots:
            cand = os.path.join(root, p)
            if os.path.isfile(cand):
                return cand
        base = os.path.basename(p)
        for root in self._roots:
            for dp, _, fns in os.walk(root):
                if base in fns:
                    return os.path.join(dp, base)
        return None

    def _apply_focus(self, raw_focus: str, ai_out: str, svc):
        """
        Ensure the target file exists (creating dirs as needed),
        back it up, then write ai_out via the service.
        """
        resolved = self._resolve_path(raw_focus)
        if not resolved:
            # If it did not exist at all, create it under the first root
            resolved = os.path.join(self._roots[0], raw_focus)

        # Ensure parent dir
        parent = os.path.dirname(resolved)
        os.makedirs(parent, exist_ok=True)

        # Ensure file exists
        if not os.path.exists(resolved):
            Path(resolved).write_text("", encoding="utf-8")
            logger.info("Created new focus file: %s", resolved)

        # Backup if service has backup_folder
        backup_folder = getattr(svc, "backup_folder", None)
        if backup_folder:
            os.makedirs(backup_folder, exist_ok=True)
            timestamp = datetime.utcnow().strftime("%Y%m%d-%H%M%S")
            dest = os.path.join(
                backup_folder,
                f"{Path(resolved).name}-{timestamp}"
            )
            shutil.copy(resolved, dest)
            logger.info("Backup created: %s", dest)

        # Push new content
        svc.call_mcp("UPDATE_FILE", {"path": resolved, "content": ai_out})
        logger.info("Updated focus file: %s", resolved)

        # Update watch‐ignore
        try:
            m_after = os.path.getmtime(resolved)
            self._watch_ignore[resolved] = m_after
        except OSError:
            pass
        
    def _apply_focusc(self, raw_focus: str, ai_out: str, svc):
        # 1) resolve into an absolute path
        real = (
            self._resolve_path(raw_focus)
            or (raw_focus if os.path.isabs(raw_focus) else os.path.join(self._roots[0], raw_focus))
        )
        real = os.path.abspath(raw_focus)
        dirpath = os.path.dirname(real)

        # 2) ensure the directory exists on the MCP side
        try:
            svc.call_mcp("CREATE_DIR", {"path": dirpath, "mode": 0o755})
            logger.info(f"Ensured focus directory via MCP: {dirpath}")
        except Exception as e:
            # if it already existed, MCP may error—ignore that
            logger.debug(f"CREATE_DIR on {dirpath} failed or already exists: {e}")

        # 3) optionally back up the old content locally
        backup_folder = getattr(svc, "backup_folder", None)
        if backup_folder:
            # attempt to READ_FILE via MCP; if it doesn't exist, skip backup
            try:
                resp = svc.call_mcp("READ_FILE", {"path": real})
                old = resp.get("content", "")
                if old:
                    ts = datetime.utcnow().strftime("%Y%m%d-%H%M%S")
                    Path(backup_folder).mkdir(parents=True, exist_ok=True)
                    bkname = f"{Path(real).name}-{ts}.bak"
                    bkpath = os.path.join(backup_folder, bkname)
                    with open(bkpath, "w", encoding="utf-8") as f:
                        f.write(old)
                    logger.info(f"Backed up old focus file to: {bkpath}")
            except Exception:
                logger.debug(f"No existing file at {real} to back up.")

        # 4) push the new content
        svc.call_mcp("UPDATE_FILE", {"path": real, "content": ai_out})
        logger.info(f"Updated focus file via MCP: {real}")

        # 5) ignore our own write in the watch loop
        try:
            m_after = os.path.getmtime(real)
            self._watch_ignore[real] = m_after
        except OSError:
            pass

    def _apply_focusb(self, raw_focus: str, ai_out: str, svc):
        real = self._resolve_path(raw_focus) or (
            raw_focus if os.path.isabs(raw_focus) else os.path.join(self._roots[0], raw_focus)
        )
        if not os.path.exists(real):
            os.makedirs(os.path.dirname(real), exist_ok=True)
            Path(real).write_text('', encoding='utf-8')
            logger.info(f"Created new focus file: {real}")

        backup = getattr(svc, 'backup_folder', None)
        if backup and os.path.exists(real):
            os.makedirs(backup, exist_ok=True)
            ts = datetime.utcnow().strftime('%Y%m%d-%H%M%S')
            dest = os.path.join(backup, f"{Path(real).name}-{ts}")
            shutil.copy(real, dest)
            logger.info(f"Backup created: {dest}")

        svc.call_mcp("UPDATE_FILE", {"path": real, "content": ai_out})
        logger.info(f"Updated focus file: {real}")
        try:
            m_after = os.path.getmtime(real)
            self._watch_ignore[real] = m_after
        except OSError:
            pass

    def _extract_focus(self, focus_spec) -> Optional[str]:
            """
            Turn the parsed focus‐spec (dict or raw string) into a clean path,
            stripping any `file=` or `pattern=` prefixes and backticks/quotes.
            """
            if not focus_spec:
                return None

            # focus_spec is usually a dict with keys 'pattern' or 'file'
            if isinstance(focus_spec, dict):
                raw = focus_spec.get("file") or focus_spec.get("pattern") or ""
            else:
                raw = str(focus_spec)

            # strip quotes or backticks
            raw = raw.strip('"').strip("`")

            # strip any leading prefix
            for prefix in ("file=", "pattern="):
                if raw.startswith(prefix):
                    raw = raw[len(prefix):]

            return raw or None

    def _process_one(self, task: dict, svc, file_lines_map: dict):
        include = task.get("include") or {}
        knowledge = self._gather_include_knowledge(include, svc)
        know_tokens = self._get_token_count(knowledge)

        _knowledge = ("\n" + task['knowledge'] + "\n") if task.get('knowledge') else ""
        prompt = (
            "knowledge:\n" + knowledge + "\n\n:end knowledge:\n\n"
            "ask: " + task['desc'] + "\n\n"
            "ask and knowledge: " + _knowledge + "\n\n"
            "task A2: Respond with full code full-file \n"
            "task A3: Tag each code file with a leading line `# file: <path>`\n"
            "task A4: No diffs.\n"
            "task A5: No extra explanation.\n"
            "task A6: No code fences.\n"
            "task A7: Ensure all tasks and sub tasks are completed.\n"
        )
        prompt_tokens = self._get_token_count(prompt)
        total_tokens = know_tokens + prompt_tokens

        task['_know_tokens'] = know_tokens
        task['_prompt_tokens'] = prompt_tokens
        task['_token_count'] = total_tokens

        TodoService._start_task(task, file_lines_map)
        logger.info("-> Starting task: %s", task['desc'])
        logger.info(f"Include knowledge tokens: {know_tokens}, Prompt tokens: {prompt_tokens}")
        focus_spec = task.get("focus")
        raw_focus = self._extract_focus(focus_spec)
        logger.info("Raw focus: %s", raw_focus)
        ai_out = svc.ask(prompt)

        if raw_focus:
            self._apply_focus(raw_focus, ai_out, svc)
        else:
            logger.info("No focus file specified; skipping update.")

        TodoService._complete_task(task, file_lines_map)
        logger.info(f"Completed task: {task['desc']}")

# end of file