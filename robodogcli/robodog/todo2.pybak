#!/usr/bin/env python3
import os
import re
import json
import logging
from datetime import datetime
from pathlib import Path
from typing import List, Optional

from pydantic import BaseModel, RootModel
import difflib
import tiktoken

logger = logging.getLogger(__name__)

TASK_RE = re.compile(r'^(\s*)-\s*\[(?P<status>[ x~])\]\s*(?P<desc>.+)$')
SUB_RE  = re.compile(
    r'^\s*-\s*(?P<key>include|focus):\s*'
    r'(?:pattern=)?(?P<pattern>\S+)'
    r'(?:\s+(?P<rec>recursive))?'
)
STATUS_MAP     = {' ': 'To Do', '~': 'Doing', 'x': 'Done'}
REVERSE_STATUS = {v: k for k, v in STATUS_MAP.items()}


class Change(BaseModel):
    path: str
    start_line: int
    end_line: Optional[int]  # None means replace entire file
    new_content: str


class ChangesList(RootModel[List[Change]]):
    pass


class TodoService:
    FILENAME = 'todo.md'

    def __init__(self, roots):
        self.roots      = roots
        self.file_lines = {}
        self.tasks      = []
        self._load_all()

    def _find_files(self):
        out = []
        for r in self.roots:
            for dp, _, fns in os.walk(r):
                if self.FILENAME in fns:
                    out.append(os.path.join(dp, self.FILENAME))
        return out

    def _load_all(self):
        self.file_lines.clear()
        self.tasks.clear()
        for fn in self._find_files():
            lines = Path(fn).read_text(encoding='utf-8').splitlines(keepends=True)
            self.file_lines[fn] = lines
            i = 0
            while i < len(lines):
                m = TASK_RE.match(lines[i])
                if not m:
                    i += 1; continue
                indent = m.group(1)
                status = m.group('status')
                desc   = m.group('desc').strip()
                task = {
                    'file':        fn,
                    'line_no':     i,
                    'indent':      indent,
                    'status_char': status,
                    'desc':        desc,
                    'include':     None,
                    'focus':       None
                }
                j = i + 1
                while j < len(lines) and lines[j].startswith(indent + '  '):
                    ms = SUB_RE.match(lines[j])
                    if ms:
                        key = ms.group('key')
                        pat = ms.group('pattern')
                        rec = bool(ms.group('rec'))
                        task[key] = {'pattern': pat, 'recursive': rec}
                    j += 1
                self.tasks.append(task)
                i = j

    def get_next(self):
        for t in self.tasks:
            if STATUS_MAP[t['status_char']] == 'To Do':
                return t
        return None

    def _update_status(self, task, new_char):
        fn   = task['file']
        ln   = task['line_no']
        indent = task['indent']
        desc = task['desc']
        self.file_lines[fn][ln] = f"{indent}- [{new_char}] {desc}\n"
        task['status_char'] = new_char

    def _write_file(self, fn):
        Path(fn).write_text(''.join(self.file_lines[fn]), encoding='utf-8')

    def start(self, task):
        if STATUS_MAP[task['status_char']] != 'To Do':
            return
        self._update_status(task, REVERSE_STATUS['Doing'])
        stamp = datetime.utcnow().strftime('%Y-%m-%d %H:%M')
        indent = task['indent'] + '  '
        self.file_lines[task['file']].insert(
            task['line_no'] + 1,
            f"{indent}- started: {stamp}\n"
        )
        self._write_file(task['file'])

    def complete(self, task):
        if STATUS_MAP[task['status_char']] != 'Doing':
            return
        self._update_status(task, REVERSE_STATUS['Done'])
        stamp = datetime.utcnow().strftime('%Y-%m-%d %H:%M')
        indent = task['indent'] + '  '
        self.file_lines[task['file']].insert(
            task['line_no'] + 1,
            f"{indent}- completed: {stamp}\n"
        )
        self._write_file(task['file'])

    def _resolve_path(self, path: str) -> Optional[str]:
        if os.path.isabs(path) and os.path.isfile(path):
            return path
        for root in self.roots:
            cand = os.path.join(root, path)
            if os.path.isfile(cand):
                return cand
        base = os.path.basename(path)
        for root in self.roots:
            for dp, _, fns in os.walk(root):
                if base in fns:
                    return os.path.join(dp, base)
        return None

    def _apply_change(self, svc, change: Change):
        path = change.path
        real = self._resolve_path(path)
        if not real:
            raise FileNotFoundError(f"Cannot find file: {path}")
        if change.end_line is None:
            # full overwrite
            svc.call_mcp("UPDATE_FILE", {"path": real, "content": change.new_content})
            print(f"Replaced entire file: {real}")
        else:
            existing = Path(real).read_text(encoding='utf-8').splitlines(keepends=True)
            s = change.start_line - 1
            e = min(change.end_line, len(existing))
            new_lines = change.new_content.splitlines(keepends=True)
            updated = existing[:s] + new_lines + existing[e:]
            svc.call_mcp("UPDATE_FILE", {"path": real, "content": "".join(updated)})
            print(f"Applied change to {real}: lines {change.start_line}-{change.end_line}")
        return real

    def parse_llm_output(self, text: str) -> List[Change]:
        changes: List[Change] = []

        # --- 1) Look for any blocks starting "# file:" even if not fenced ---
        loose_blocks = re.split(r'```(?:diff)?', text)
        for block in loose_blocks:
            if block.strip().startswith('# file:'):
                lines = block.strip().splitlines()
                cur_file = lines[0].split(':',1)[1].strip()
                # collect hunks under this block
                orig_start = orig_count = new_start = new_count = None
                hunk_lines = []
                for line in lines[1:]:
                    if line.startswith('@@ '):
                        # flush previous
                        if hunk_lines and orig_start is not None:
                            new_content = ''.join(
                                l[1:] for l in hunk_lines if l.startswith('+') or l.startswith(' ')
                            )
                            end_line = orig_start - 1 + orig_count
                            changes.append(Change(
                                path=cur_file,
                                start_line=orig_start,
                                end_line=end_line,
                                new_content=new_content
                            ))
                        m = re.match(r'@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@', line)
                        if not m:
                            orig_start = None
                            continue
                        orig_start = int(m.group(1))
                        orig_count = int(m.group(2) or '1')
                        new_start  = int(m.group(3))
                        new_count  = int(m.group(4) or '1')
                        hunk_lines = []
                    elif orig_start is not None and line and line[0] in '+- ':
                        hunk_lines.append(line)
                # final flush
                if hunk_lines and orig_start is not None:
                    new_content = ''.join(
                        l[1:] for l in hunk_lines if l.startswith('+') or l.startswith(' ')
                    )
                    end_line = orig_start - 1 + orig_count
                    changes.append(Change(
                        path=cur_file,
                        start_line=orig_start,
                        end_line=end_line,
                        new_content=new_content
                    ))

        # --- 2) Fenced diff blocks ```diff ... ``` ---
        for diff_block in re.findall(r'```diff\n(.*?)```', text, re.S):
            # reuse the same parsing logic by prefixing a fake "# file:" if missing
            block = diff_block if diff_block.lstrip().startswith('# file:') else '# file: \n' + diff_block
            changes += self.parse_llm_output(block)  # recursive but will take only the new hunks

        # --- 3) Full-file code fences ```python\n# file: path\n...``` or ```\n# file: path\n...``` ---
        for code_block in re.findall(r'```(?:python)?\n(.*?)```', text, re.S):
            lines = code_block.strip().splitlines()
            if lines and lines[0].strip().startswith('# file:'):
                path = lines[0].split(':',1)[1].strip()
                content = "\n".join(lines[1:]) + "\n"
                changes.append(Change(
                    path=path,
                    start_line=1,
                    end_line=None,
                    new_content=content
                ))

        return changes

    def run_next_task(self, svc):
        self._load_all()
        task = self.get_next()
        if not task:
            print("No To Do tasks found."); return

        self.start(task)
        print(f"→ Starting task: {task['desc']}")

        # include/focus
        for key in ('focus', 'include'):
            spec = task.get(key)
            if not spec: continue
            spec_str = f"pattern={spec['pattern']}" + (" recursive" if spec['recursive'] else "")
            print(f"Including ({key}): {spec_str}")
            if key == 'include':
                ans = svc.include(spec_str, task['desc'])
                if ans:
                    svc.context += f"\nAI: {ans}"
            else:
                svc.include(spec_str)

        know = svc.knowledge

        prompt = (
            task['desc'] + "\n\n"
            "Please respond with unified-diff blocks (```diff … ```) or with full-file code fences\n"
            "tagged by a leading `# file: path` line. No extra explanation.\n"
        )

        orig_ctx = svc.context; orig_k = svc.knowledge
        svc.context = ""; svc.knowledge = know
        ai_out = svc.ask(prompt)
        svc.context = orig_ctx; svc.knowledge = orig_k
        svc.context += f"\nAI: {ai_out}"

        changes = self.parse_llm_output(ai_out)
        if not changes:
            print("Warning: no diffs or file blocks detected. Task aborted.")
            return

        changed_files = set()
        for ch in changes:
            try:
                real = self._apply_change(svc, ch)
                changed_files.add(real)
            except Exception as e:
                print(f"Error applying change {ch.dict()}: {e}")

        self.complete(task)
        print(f"✔ Completed task: {task['desc']}")

        # --- Finally, print full updated files as drop-ins ---
        for real in changed_files:
            try:
                content = svc.call_mcp("READ_FILE", {"path": real}).get("content", "")
                print(f"\n```python\n# file: {real}\n{content}```\n")
            except Exception as e:
                print(f"Could not fetch updated content of {real}: {e}")