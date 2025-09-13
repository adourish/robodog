# file: robodog/task_parser.py
#!/usr/bin/env python3
"""Task parsing functionality extracted from TodoService."""
import re
import logging
from typing import List, Dict, Any
from pathlib import Path

logger = logging.getLogger(__name__)

# Regex patterns for parsing tasks
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


class TaskParser:
    """Handles parsing of todo.md files into task objects."""
    
    def parse_base_dir(self, file_paths: List[str]) -> str:
        """Parse base directory from YAML front-matter."""
        for fn in file_paths:
            try:
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
            except Exception as e:
                logger.warning(f"Error parsing base dir from {fn}: {e}")
        
        return None
    
    def parse_tasks_from_file(self, filepath: str) -> tuple[List[str], List[Dict[Any, Any]]]:
        """Parse tasks from a single todo.md file."""
        lines = Path(filepath).read_text(encoding='utf-8').splitlines(keepends=True)
        tasks = []
        
        i = 0
        while i < len(lines):
            m = TASK_RE.match(lines[i])
            if not m:
                i += 1
                continue
            
            indent = m.group(1)
            status = m.group('status')
            write_flag = m.group('write')  # may be None, ' ', '~', or 'x'
            desc = m.group('desc').strip()
            
            task = {
                'file': filepath,
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
            
            # Scan sub-entries (include, in, focus)
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
            
            # Capture ```knowledge``` fence immediately after task
            if j < len(lines) and lines[j].lstrip().startswith('```knowledge'):
                fence = []
                j += 1
                while j < len(lines) and not lines[j].startswith('```'):
                    fence.append(lines[j])
                    j += 1
                task['knowledge'] = ''.join(fence)
                j += 1  # skip closing ``` line
            
            tasks.append(task)
            i = j
        
        return lines, tasks

# original file length: 0 lines
# updated file length: 95 lines
