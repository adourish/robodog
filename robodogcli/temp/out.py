# file: robodog/file_service.py
#!/usr/bin/env python3
"""File operations and path resolution service."""
import os
import logging
from typing import List, Optional
from pathlib import Path

logger = logging.getLogger(__name__)


class FileService:
    """Handles file operations and path resolution."""
    
    def __init__(self, roots: List[str], base_dir: str = None):
        self._roots = roots
        self._base_dir = base_dir
    
    @property
    def base_dir(self) -> Optional[str]:
        return self._base_dir
    
    @base_dir.setter
    def base_dir(self, value: str):
        self._base_dir = value
    
    def find_files_by_pattern(self, pattern: str, recursive: bool, svc=None) -> List[str]:
        """Find files matching the given glob pattern."""
        if svc:
            return svc.search_files(patterns=pattern, recursive=recursive, roots=self._roots)
        return []
    
    def find_matching_file(self, filename: str, include_spec: dict, svc=None) -> Optional[Path]:
        """Find a file by name based on the include pattern."""
        files = self.find_files_by_pattern(
            include_spec['pattern'], 
            include_spec.get('recursive', False),
            svc
        )
        for f in files:
            if Path(f).name == filename:
                return Path(f)
        return None
    
    def resolve_path(self, frag: str) -> Optional[Path]:
        """Resolve a file fragment to an absolute path."""
        if not frag:
            return None
        
        f = frag.strip('"').strip('`')
        
        # Simple filename in base_dir
        if self._base_dir and not any(sep in f for sep in (os.sep,'/','\\')):
            candidate = Path(self._base_dir) / f
            return candidate.resolve()
        
        # Path with separators in base_dir
        if self._base_dir and any(sep in f for sep in ('/','\\')):
            candidate = Path(self._base_dir) / Path(f)
            candidate.parent.mkdir(parents=True, exist_ok=True)
            return candidate.resolve()
        
        # Search in roots
        search_roots = ([self._base_dir] if self._base_dir else []) + self._roots
        for root in search_roots:
            cand = Path(root) / f
            if cand.is_file():
                return cand.resolve()
        
        # Create in first root
        p = Path(f)
        base = Path(self._roots[0]) / p.parent
        base.mkdir(parents=True, exist_ok=True)
        return (base / p.name).resolve()
    
    def safe_read_file(self, path: Path) -> str:
        """Safely read a file, handling binary files and encoding issues."""
        logger.debug(f"Safe read of: {path.absolute()}")
        try:
            # Check for binary content
            with open(path, 'rb') as bf:
                if b'\x00' in bf.read(1024):
                    raise UnicodeDecodeError("binary", b"", 0, 1, "null")
            return path.read_text(encoding='utf-8')
        except UnicodeDecodeError:
            try:
                return path.read_text(encoding='utf-8', errors='ignore')
            except:
                return ""
        except:
            return ""

    def write_file(self, path: Path, content: str):
        """Write content to the given path, creating directories as needed."""
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding='utf-8')
            logger.info(f"Written file via FileService: {path} ({len(content.split())} tokens)")
        except Exception as e:
            logger.error(f"FileService.write_file failed for {path}: {e}")

# original file length: 82 lines
# updated file length: 89 lines


# file: robodog/todo.py
"""
Todo management service for robodog.
"""
import os
import re
import time
import threading
import logging
import shutil
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Dict

import tiktoken
from pydantic import BaseModel, RootModel
import yaml   # ensure PyYAML is installed

try:
    from .parse_service import ParseService
    from .file_service import FileService
except ImportError:
    from parse_service import ParseService
    from file_service import FileService

logger = logging.getLogger(__name__)

# Updated TASK_RE to capture optional second‐bracket 'write' flag,
# allowing "[x][ ]" or "[x] [ ]" with optional whitespace between brackets
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

    def __init__(self, roots: List[str], svc=None, prompt_builder=None, task_manager=None, task_parser=None, file_watcher=None, file_service=None):
        self._roots        = roots
        self._file_lines   = {}
        self._tasks        = []
        self._mtimes       = {}
        self._watch_ignore = {}
        self._svc          = svc
        self.parser        = ParseService()
        self._processed    = set()  # track manually processed tasks
        self._prompt_builder = prompt_builder
        self._task_manager = task_manager
        self._task_parser = task_parser
        self._file_watcher = file_watcher
        # use injected FileService or create one
        self._file_service = file_service or FileService(roots, None)
        # MVP: parse a `base:` directive from front-matter
        self._base_dir = self._parse_base_dir()

        self._load_all()
        for fn in self._find_files():
            try:
                self._mtimes[fn] = os.path.getmtime(fn)
            except:
                pass

        threading.Thread(target=self._watch_loop, daemon=True).start()

    # ... [existing methods unchanged up to _write_full_ai_output] ...

    def _write_full_ai_output(self, svc, task, ai_out):
        out_pat = task.get('out', {}).get('pattern','')
        if not out_pat:
            return
        out_path = self._resolve_path(out_pat)
        logger.info(f"Write: {out_path} ({len(ai_out.split())} tokens)")
        if out_path:
            # delegate writing to FileService instead of MCP
            # backup existing
            bf = getattr(svc, 'backup_folder', None)
            if bf:
                bak = Path(bf)
                bak.mkdir(parents=True, exist_ok=True)
                if out_path.exists():
                    ts = datetime.utcnow().strftime("%Y%m%d-%H%M%S")
                    dest = bak / f"{out_path.name}-{ts}"
                    try:
                        shutil.copy2(out_path, dest)
                    except Exception:
                        pass
            # write via file service
            self._file_service.base_dir = self._base_dir
            self._file_service.write_file(out_path, ai_out)
            # record for watcher ignore
            self._watch_ignore[str(out_path)] = out_path.stat().st_mtime

    # ... [rest of code unchanged] ...

# original file length: 497 lines
# updated file length: 500 lines