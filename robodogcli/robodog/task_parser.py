# file: task_parser.py
#!/usr/bin/env python3
import os
import re
import logging
from pathlib import Path
from typing import List, Tuple, Dict, Any, Optional

logger = logging.getLogger(__name__)

# New three-bracket TASK_RE
TASK_RE = re.compile(
    r'^(\s*)-\s*'                         # indent + "- "
    r'\[(?P<plan>[ x~\-])\]\s*'           # [plan_status]
    r'\[(?P<llm>[ x~\-])\]\s*'            # [llm_status]
    r'\[(?P<commit>[ x~\-])\]\s*'         # [commit_status]
    r'(?P<desc>.+)$'                      # the rest is your desc
)

# SUB_RE unchanged
SUB_RE = re.compile(
    r'^\s*-\s*(?P<key>include|out|in|focus|plan):\s*'
    r'(?:pattern=|file=)?(?P<pattern>"[^"]+"|`[^`]+`|\S+)'
    r'(?:\s+(?P<rec>recursive))?'
)

class TaskParser:
    """
    Parses lines of a todo.md into tasks.
    """

    def parse_base_dir(self, file_paths: List[str]) -> Optional[str]:
        # copy of your old parse_base_dir; unchanged
        for fn in file_paths:
            try:
                text = Path(fn).read_text(encoding='utf-8')
                lines = text.splitlines()
                if not lines or lines[0].strip() != '---':
                    continue
                try:
                    end = lines.index('---', 1)
                except ValueError:
                    continue
                for lm in lines[1:end]:
                    if lm.strip().startswith('base:'):
                        _, _, val = lm.partition(':')
                        return val.strip() or None
            except Exception:
                logger.exception("parse_base_dir error on %s", fn)
        return None

    def parse_tasks_from_file(self, filepath: str
                             ) -> Tuple[List[str], List[Dict[str,Any]]]:
        """Read the file and call parse_tasks."""
        raw = Path(filepath).read_text(encoding='utf-8')
        lines = raw.splitlines(keepends=True)
        return self.parse_tasks(filepath, lines)

    def parse_tasks(self,
                    filepath: str,
                    lines: List[str]
                   ) -> Tuple[List[str], List[Dict[str,Any]]]:
        """
        Given a filename + its lines[], return (lines, [task, …]).
        Each task is a dict with keys: file, line_no, indent, plan, llm,
        commit, desc, include, in, out, focus, plan_spec, knowledge, _raw_desc.
        """
        tasks: List[Dict[str,Any]] = []
        i = 0
        while i < len(lines):
            m = TASK_RE.match(lines[i])
            if not m:
                i += 1
                continue

            indent = m.group(1)
            plan   = m.group('plan')
            llm    = m.group('llm')
            commit = m.group('commit')
            desc   = m.group('desc').strip()
            
            # Strip metadata from description to prevent duplication
            # Metadata is everything after the first '|' character
            clean_desc = desc.split('|')[0].strip() if '|' in desc else desc

            task = {
                'file': filepath,
                'line_no': i,
                'indent': indent,
                'plan': plan,
                'llm': llm,
                'commit': commit,
                'desc': clean_desc,
                # Preserve the clean description for rebuilds
                '_raw_desc': clean_desc,
                'include': None,
                'in': None,
                'out': None,
                'focus': None,
                'plan_spec': None,
                'knowledge': '',
            }

            # scan sub-lines
            j = i + 1
            while j < len(lines) and lines[j].startswith(indent + '  '):
                subm = SUB_RE.match(lines[j])
                if subm:
                    key = subm.group('key')
                    pat = subm.group('pattern').strip('"').strip('`')
                    rec = bool(subm.group('rec'))
                    spec = {'pattern': pat, 'recursive': rec}
                    if key == 'plan':
                        task['plan_spec'] = spec
                    else:
                        task[key] = spec
                j += 1

            # optional ```knowledge``` fence
            if j < len(lines) and lines[j].lstrip().startswith('```knowledge'):
                fence = []
                j += 1
                while j < len(lines) and not lines[j].startswith('```'):
                    fence.append(lines[j])
                    j += 1
                task['knowledge'] = ''.join(fence)
                j += 1

            tasks.append(task)
            i = j

        logger.debug("Parsed %d tasks from %s", len(tasks), filepath)
        return lines, tasks

    def load_all(self,
                 file_paths: List[str],
                 file_service: Any
                ) -> Tuple[Dict[str, List[str]], List[Dict[str,Any]]]:
        """
        Reads each path via file_service.safe_read_file(), splits into lines,
        calls parse_tasks(), and accumulates file_lines + tasks.
        """
        all_file_lines: Dict[str, List[str]] = {}
        all_tasks: List[Dict[str,Any]] = []

        for fn in file_paths:
            logger.info(f"TaskParser: loading {fn}")
            content = file_service.safe_read_file(Path(fn))
            lines = content.splitlines(keepends=True)
            file_lines, tasks = self.parse_tasks(fn, lines)
            all_file_lines[fn] = file_lines
            all_tasks.extend(tasks)

        logger.info(f"TaskParser: loaded {len(all_tasks)} total tasks")
        return all_file_lines, all_tasks