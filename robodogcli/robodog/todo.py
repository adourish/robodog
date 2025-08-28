# file: robodog/cli/todo.py
import os
import re
import json
import logging
from datetime import datetime
from pathlib import Path

TASK_RE = re.compile(r'^(\s*)-\s*\[(?P<status>[ x~])\]\s*(?P<desc>.+)$')
SUB_RE  = re.compile(
    r'^\s*-\s*(?P<key>include|focus):\s*(?:pattern=)?(?P<pattern>\S+)' +
    r'(?:\s+(?P<rec>recursive))?'
)

STATUS_MAP     = {' ': 'To Do', '~': 'Doing', 'x': 'Done'}
REVERSE_STATUS = {v: k for k, v in STATUS_MAP.items()}

logger = logging.getLogger(__name__)

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
                    i += 1
                    continue
                indent = m.group(1)
                status = m.group('status')
                desc   = m.group('desc').strip()
                task = {
                    'file':       fn,
                    'line_no':    i,
                    'indent':     indent,
                    'status_char': status,
                    'desc':       desc,
                    'include':    None,
                    'focus':      None
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

    def _extract_changes(self, ai_output):
        m = re.search(r'```json(.*?)```', ai_output, re.S)
        body = m.group(1).strip() if m else ai_output
        try:
            return json.loads(body)
        except json.JSONDecodeError:
            print("Warning: could not parse JSON changes from AI output.")
            return []

    def _apply_change(self, svc, change):
        logger.debug("Applying change: %r", change)
        path = change['path']

        # If relative, try to resolve under each root
        resolved = False
        if not os.path.isabs(path):
            for root in self.roots:
                candidate = os.path.join(root, path)
                if os.path.isfile(candidate):
                    path = candidate
                    resolved = True
                    logger.debug("Resolved direct: %s", path)
                    break

        # Fallback: search by basename
        if not resolved and not os.path.isfile(path):
            base = os.path.basename(path)
            for root in self.roots:
                for dp, _, fns in os.walk(root):
                    if base in fns:
                        candidate = os.path.join(dp, base)
                        path = candidate
                        resolved = True
                        logger.debug("Resolved by search: %s → %s", change['path'], path)
                        break
                if resolved:
                    break

        if not os.path.isfile(path):
            raise FileNotFoundError(f"Cannot find file to patch: {change['path']}")

        # Read, splice, and send update
        existing = Path(path).read_text(encoding='utf-8').splitlines(keepends=True)
        s, e = change['start_line'] - 1, change['end_line']
        new_lines = change['new_content'].splitlines(keepends=True)
        updated = existing[:s] + new_lines + existing[e:]
        content = ''.join(updated)

        logger.debug("Updating file %s lines %d-%d", path, change['start_line'], change['end_line'])
        svc.call_mcp("UPDATE_FILE", {"path": path, "content": content})
        print(f"Applied change to {path}: lines {change['start_line']}-{change['end_line']}")

    def run_next_task(self, svc):
        self._load_all()
        task = self.get_next()
        if not task:
            print("No To Do tasks found.")
            return

        self.start(task)
        print(f"→ Starting task: {task['desc']}")

        # bring in focus & include files
        for key in ('focus', 'include'):
            spec = task.get(key)
            if not spec:
                continue
            spec_str = f"pattern={spec['pattern']}" + (" recursive" if spec['recursive'] else "")
            print(f"Including ({key}): {spec_str}")
            if key == 'include':
                answer = svc.include(spec_str, task['desc'])
                if answer:
                    svc.context += f"\nAI: {answer}"
            else:
                svc.include(spec_str)

        # prepare JSON‐only prompt
        prompt = (
            task['desc']
            + "\n\n"
            + "Please respond ONLY with a JSON array of change objects, each with:\n"
            + "  path, start_line, end_line, new_content.\n"
            + "Do not include any other text."
        )

        # restrict context/knowledge to what was just included
        orig_context   = svc.context
        orig_knowledge = svc.knowledge

        svc.context   = ""
        svc.knowledge = orig_knowledge

        svc.context += f"\nUser: {prompt}"
        ai_out = svc.ask(prompt)

        # restore and record
        svc.context   = orig_context
        svc.knowledge = orig_knowledge
        svc.context  += f"\nAI: {ai_out}"

        changes = self._extract_changes(ai_out)
        for ch in changes:
            try:
                self._apply_change(svc, ch)
            except Exception as e:
                print(f"Error applying change {ch}: {e}")

        self.complete(task)
        print(f"✔ Completed task: {task['desc']}")