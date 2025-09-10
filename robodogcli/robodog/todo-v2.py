Here are the enhanced todo.py changes to support multiple in/out files with better prompting:

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
import yaml

logger = logging.getLogger(__name__)

TASK_RE = re.compile(r'^(\s*)-\s*\[(?P<status>[ x~])\]\s*(?P<desc>.+)$')
SUB_RE = re.compile(
    r'^\s*-\s*(?P<key>include|out|in|focus):\s*'
    r'(?:pattern=|file=)?(?P<pattern>"[^"]+"|`[^`]+`|\S+)'
    r'(?:\s+(?P<rec>recursive))?'
)

STATUS_MAP = {' ': 'To Do', '~': 'Doing', 'x': 'Done'}
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

    def __init__(self, roots: List[str], parser):
        self._roots = roots
        self._file_lines = {}
        self._tasks = []
        self._mtimes = {}
        self._watch_ignore = {}
        self._svc = None
        self._parser = parser
        self._base_dir = self._parse_base_dir()

        self._load_all()
        for fn in self._find_files():
            try:
                self._mtimes[fn] = os.path.getmtime(fn)
            except:
                pass

        threading.Thread(target=self._watch_loop, daemon=True).start()

    # ... [Keep all existing helper methods unchanged until _load_all] ...

    def _load_all(self):
        """Parse each todo.md into tasks with multiple in/out entries and knowledge blocks."""
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
                desc = m.group('desc').strip()
                task = {
                    'file': fn,
                    'line_no': i,
                    'indent': indent,
                    'status_char': status,
                    'desc': desc,
                    'include': [],
                    'in': [],
                    'out': [],
                    'knowledge': '',
                    '_start_stamp': None,
                    '_know_tokens': 0,
                    '_in_tokens': 0,
                    '_token_count': 0,
                }

                j = i + 1
                while j < len(lines) and lines[j].startswith(indent + '  '):
                    sub = SUB_RE.match(lines[j])
                    if sub:
                        key = sub.group('key')
                        pat = sub.group('pattern').strip('"').strip('`')
                        rec = bool(sub.group('rec'))
                        if key in ['include', 'in', 'out']:
                            task[key].append({'pattern': pat, 'recursive': rec})
                        elif key == 'focus':  # Alias for out
                            task['out'].append({'pattern': pat, 'recursive': rec})
                    j += 1

                if j < len(lines) and lines[j].lstrip().startswith('```knowledge'):
                    fence = []
                    j += 1
                    while j < len(lines) and not lines[j].startswith('```'):
                        fence.append(lines[j])
                        j += 1
                    task['knowledge'] = ''.join(fence)
                    j += 1  # Skip closing ```

                self._tasks.append(task)
                i = j

    def _resolve_paths(self, patterns: List[str]) -> List[Path]:
        """Resolve multiple patterns to absolute paths"""
        resolved = []
        for pattern in patterns:
            try:
                resolved.append(self._resolve_path(pattern))
            except Exception as e:
                logger.error(f"Path resolution failed for {pattern}: {e}")
        return resolved

    def _process_one(self, task: dict, svc, file_lines_map: dict):
        _basedir = os.path.dirname(task['file'])
        logger.info("Task todo file: %s", _basedir)
        self._base_dir = _basedir

        # Process include knowledge
        include = "\n".join([self._gather_include_knowledge(inc, svc) 
                           for inc in task['include']])
        task['_know_tokens'] = self._get_token_count(include)

        # Process input files
        in_patterns = [item['pattern'] for item in task['in']]
        in_content = []
        for path in self._resolve_paths(in_patterns):
            if path and path.is_file():
                in_content.append(f"# file: {path}\n{path.read_text(encoding='utf-8')}")
        in_content = "\n\n".join(in_content)

        # Build enhanced prompt
        prompt_instructions = """\
When making changes, ALWAYS include COMPLETE FILE CONTENTS using this format:

# file: relative/path/to/file.ext
Full file content here...

# file: another/file.txt
Full content here...

Include ALL lines of each file you modify, even unchanged ones.
"""
        parts = []
        if in_content:
            parts.append(f"Input files:\n{in_content}")
        if include:
            parts.append(f"Included knowledge:\n{include}")
        if task['knowledge']:
            parts.append(f"Task knowledge:\n{task['knowledge']}")
        parts.append(f"Task: {task['desc']}\n{prompt_instructions}")
        
        full_prompt = "\n\n".join(parts)
        ai_out = svc.ask(full_prompt)

        # Process parsed files
        parsed_objects = self._parser.parse_llm_output(ai_out)
        for obj in parsed_objects:
            filename = obj.get('filename', 'unknown')
            content = obj.get('content', '')
            
            target = self._resolve_path(filename)
            if not target:
                logger.error(f"Failed to resolve path for {filename}")
                continue
                
            # Create backup
            bf = getattr(svc, 'backup_folder', None)
            if bf and target.exists():
                backup = Path(bf)
                backup.mkdir(parents=True, exist_ok=True)
                ts = datetime.utcnow().strftime("%Y%m%d-%H%M%S")
                dest = backup / f"{target.name}-{ts}"
                shutil.copy2(target, dest)
                logger.info("Backup created: %s", dest)

            # Update file
            svc.call_mcp("UPDATE_FILE", {
                "path": str(target),
                "content": content
            })
            try:
                self._watch_ignore[str(target)] = os.path.getmtime(str(target))
            except:
                pass
            logger.info("Updated file: %s", target)

        TodoService._complete_task(task, file_lines_map, svc.get_cur_model())

__all_classes__ = ["Change", "ChangesList", "TodoService"]
```

Key improvements:
1. Multiple `in`/`out` support via lists
2. Enhanced prompt with clear formatting instructions
3. Processing multiple files from parsed_objects
4. Better path resolution handling
5. Maintained existing Markdown parsing while adding new features

The existing ParseService can handle the # file: format already. When the AI responds with file contents using the specified format, it will automatically create/update multiple files.

Example todo.md usage:
```markdown
- [ ] Update API endpoints
  - in: pattern=src/api/*.ts
  - out: pattern=src/api/
  - in: file=src/types.ts
  - out: file=test/api.spec.ts
```