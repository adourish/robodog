# file: robodog/cli/todo.py
#!/usr/bin/env python3
import re, os, fnmatch
from typing import Optional
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
        task['status_char'] = REVERSE_STATUS['Doing']

    @staticmethod
    def _complete_task(task: dict, file_lines_map: dict):
        if STATUS_MAP[task['status_char']] != 'Doing':
            return
        fn, ln = task['file'], task['line_no']
        indent, desc = task['indent'], task['desc']
        file_lines_map[fn][ln] = f"{indent}- [{REVERSE_STATUS['Done']}] {desc}\n"
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
        try:
            return len(text.split())
        except:
            return 0

    def _gather_include_knowledge(self, include: dict, svc) -> str:
        raw = include.get('pattern', '').strip('"').strip('`')
        spec = f"pattern={raw}" + (" recursive" if include.get('recursive') else "")
        logger.info("Gather include knowledge: " + spec)
        return svc.include(spec) or ""

    def _resolve_path(self, raw_focus: str, include: dict) -> Optional[Path]:
        """
        Locate the exact focus file by running either a glob‐translated regex
        (if your focus contains *, ?, or [ ]) or a literal/regex match on the
        FULL path, scanning each include-root in turn. Bare filenames are rejected.
        If no match is found, create the file in the nearest include-root that
        best matches the focus path.
        """
        if not raw_focus or not raw_focus.strip():
            return None

        # 1) Strip whitespace and any surrounding quotes/backticks
        frag = raw_focus.strip().strip('"').strip("`")

        # 2) Reject plain filenames (no directory separator)
        if not any(sep in frag for sep in (os.sep, "/", "\\")):
            logger.warning(
                "Bare-filename focus '%s' is not supported; please include a subpath or regex.",
                raw_focus,
            )
            return None

        # 3) Compile a regex from either a glob or a regex literal
        glob_frag = frag.replace("\\", "/")
        if any(c in glob_frag for c in ("*", "?", "[", "]")):
            glob_re = fnmatch.translate(glob_frag)
            pattern = re.compile(glob_re, re.IGNORECASE)
        else:
            escaped = frag.replace("\\", r"[\\/]")
            try:
                pattern = re.compile(escaped, re.IGNORECASE)
            except re.error:
                pattern = re.compile(re.escape(escaped), re.IGNORECASE)

        # 4) Build the search-roots mapping
        if isinstance(include, dict) and include and all(isinstance(v, str) for v in include.values()):
            roots_mapping = include
        else:
            roots_mapping = {f"root_{i}": r for i, r in enumerate(self._roots)}

        # 5) Walk each root in order and return on first match
        for inc_name, root in roots_mapping.items():
            root_path = Path(root)
            if not root_path.is_dir():
                continue
            for f in root_path.rglob("*"):
                if not f.is_file():
                    continue
                full_path = str(f.resolve()).replace("\\", "/")
                if pattern.search(full_path):
                    return f.resolve()

        # 6) No existing match → try to create. But first pick the include-root
        #    that best “owns” the leading fragment of your focus path.
        normalized = frag.replace("\\", "/")
        dir_fragment = Path(normalized).parent   # e.g. Path("robodogcli/temp")
        filename     = Path(normalized).name     # e.g. "todo.py"

        # gather roots in two passes: those whose path contains the first dir of frag,
        # then the rest
        candidates = []
        if dir_fragment.parts:
            primary = dir_fragment.parts[0].lower()
            for root in roots_mapping.values():
                if primary in str(root).lower():
                    candidates.append(root)
        # append any others we didn’t already pick
        for root in roots_mapping.values():
            if root not in candidates:
                candidates.append(root)

        # now attempt creation in priority order
        for root in candidates:
            base = Path(root)
            try:
                new_dir = (base / dir_fragment).resolve()
                new_dir.mkdir(parents=True, exist_ok=True)
                new_file = new_dir / filename
                if not new_file.exists():
                    new_file.touch()
                return new_file.resolve()
            except OSError:
                # can’t write here? try the next root
                continue

        # nothing worked
        return None
    
    def _resolve_path(self, raw_focus: str, include: dict) -> Optional[Path]:
        """
        Locate (or if missing, create) the exact focus file by expecting a
        full pathname fragment (dirs + filename).  If the file doesn’t exist
        under any include‐root, create it in the first viable include‐root.
        """
        if not raw_focus or not raw_focus.strip():
            return None

        # 1) Strip whitespace and any surrounding quotes/backticks
        frag = raw_focus.strip().strip('"').strip("`")

        # 2) Reject bare filenames (no directory separator anywhere)
        if not any(sep in frag for sep in (os.sep, "/", "\\")):
            logger.warning(
                "Bare-filename focus '%s' is not supported; please include at least one subdirectory.",
                raw_focus,
            )
            return None

        # 3) Build the include‐roots mapping
        if isinstance(include, dict) and include and all(isinstance(v, str) for v in include.values()):
            roots_mapping = include
        else:
            roots_mapping = {f"root_{i}": r for i, r in enumerate(self._roots)}

        # 4) Try to find an existing file at root/frag
        for inc_name, root in roots_mapping.items():
            candidate = Path(root) / frag
            if candidate.is_file():
                return candidate.resolve()

        # 5) No existing match → create under the first viable include‐root
        p = Path(frag)
        dir_fragment = p.parent     # e.g. Path("robodogcli/temp")
        filename     = p.name       # e.g. "todo.py"

        if not dir_fragment.parts or not filename:
            # either no directory part or no filename
            return None

        for inc_name, root in roots_mapping.items():
            base = Path(root)
            try:
                new_dir = (base / dir_fragment).resolve()
                new_dir.mkdir(parents=True, exist_ok=True)
                new_file = new_dir / filename
                # create the file if it doesn’t already exist
                if not new_file.exists():
                    new_file.touch()
                return new_file.resolve()
            except OSError as e:
                logger.debug("Could not create in %s: %s", root, e)
                continue

        # if we got here, no include‐root was writable
        return None

    def _resolve_path(self, raw_focus: str, include: dict) -> Optional[Path]:
        """
        Locate the exact focus file by running either a glob‐translated regex
        (if your focus contains *, ?, or [ ]) or a literal/regex match on the
        FULL path, scanning each include-root in turn. Bare filenames are rejected.
        """
        if not raw_focus or not raw_focus.strip():
            return None

        # 1) Strip whitespace and any surrounding quotes/backticks
        frag = raw_focus.strip().strip('"').strip("`")

        # 2) Reject plain filenames (no directory separator)
        if not any(sep in frag for sep in (os.sep, "/", "\\")):
            logger.warning(
                "Bare-filename focus '%s' is not supported; please include a subpath or regex.",
                raw_focus,
            )
            return None

        # 3) Compile a regex from either a glob or a regex literal
        #    Normalize separators to "/" for glob translation
        glob_frag = frag.replace("\\", "/")
        if any(c in glob_frag for c in ("*", "?", "[", "]")):
            # treat as a glob → translate to regex
            glob_re = fnmatch.translate(glob_frag)
            # fnmatch.translate appends '\Z(?ms)'; that's okay under re.IGNORECASE
            pattern = re.compile(glob_re, re.IGNORECASE)
        else:
            # treat as a regex literal, but allow Windows/Unix separator
            escaped = frag.replace("\\", r"[\\/]")
            try:
                pattern = re.compile(escaped, re.IGNORECASE)
            except re.error:
                pattern = re.compile(re.escape(escaped), re.IGNORECASE)

        # 4) Build the search-roots mapping (same as original)
        if isinstance(include, dict) and include and all(isinstance(v, str) for v in include.values()):
            roots_mapping = include
        else:
            roots_mapping = {f"root_{i}": r for i, r in enumerate(self._roots)}

        # 5) Walk each root in order and return on first match
        for inc_name, root in roots_mapping.items():
            root_path = Path(root)
            if not root_path.is_dir():
                continue

            for f in root_path.rglob("*"):
                if not f.is_file():
                    continue
                # normalize to "/" so both glob‐regex and literal‐regex work
                full_path = str(f.resolve()).replace("\\", "/")
                if pattern.search(full_path):
                    return f.resolve()

        return None
  
    def _apply_focus(self, raw_focus: str, ai_out: str, svc, include: dict, target: str):
        
        if not target:
            target = Path(self._roots[0]) / raw_focus
        target = target.resolve()
        target.parent.mkdir(parents=True, exist_ok=True)

        backup_folder = getattr(svc, 'backup_folder', None)
        if backup_folder:
            bf = Path(backup_folder)
            bf.mkdir(parents=True, exist_ok=True)
            if target.exists():
                ts = datetime.utcnow().strftime("%Y%m%d-%H%M%S")
                dest = bf / f"{target.name}-{ts}"
                shutil.copy2(target, dest)
                logger.info("Backup created: %s", dest)

        svc.call_mcp("UPDATE_FILE", {"path": str(target), "content": ai_out})
        logger.info("Updated focus file: %s", target)

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
        knowledge = self._gather_include_knowledge(include, svc)
        kt = self._get_token_count(knowledge)
        _kc = ("\n" + task.get('knowledge', '') + "\n") if task.get('knowledge') else ""
        prompt = (
            "knowledge:\n" + knowledge + "\n\n:end knowledge:\n\n"
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
        raw_focus = self._extract_focus(task.get("focus"))
        target = self._resolve_path(raw_focus, include)
        logger.info("Focus file: %s", target)
        ai_out = svc.ask(prompt)
        if raw_focus:
            self._apply_focus(raw_focus, ai_out, svc, include, target)
        else:
            logger.info("No focus file specified; skipping update.")
        TodoService._complete_task(task, file_lines_map)

__all_classes__ = ["Change", "ChangesList", "TodoService"]