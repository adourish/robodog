# Written on 2025-09-13 18:36:00 UTC

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
        logger.info(f"Initializing FileService with roots: {roots}, base_dir: {base_dir}")
        self._roots = roots
        self._base_dir = base_dir
    
    @property
    def base_dir(self) -> Optional[str]:
        return self._base_dir
    
    @base_dir.setter
    def base_dir(self, value: str):
        logger.debug(f"Setting base_dir to: {value}")
        self._base_dir = value
    
    def find_files_by_pattern(self, pattern: str, recursive: bool, svc=None) -> List[str]:
        """Find files matching the given glob pattern."""
        logger.debug(f"find_files_by_pattern called with pattern: {pattern}, recursive: {recursive}")
        if svc:
            return svc.search_files(patterns=pattern, recursive=recursive, roots=self._roots)
        logger.warning("Svc not provided, returning empty list")
        return []
    
    def find_matching_file(self, filename: str, include_spec: dict, svc=None) -> Optional[Path]:
        """Find a file by name based on the include pattern."""
        logger.debug(f"find_matching_file called for {filename}")
        files = self.find_files_by_pattern(
            include_spec['pattern'], 
            include_spec.get('recursive', False),
            svc
        )
        for f in files:
            if Path(f).name == filename:
                logger.debug(f"Matching file found: {f}")
                return Path(f)
        logger.debug("No matching file found")
        return None
    
    def resolve_path(self, frag: str) -> Optional[Path]:
        """Resolve a file fragment to an absolute path."""
        logger.debug(f"Resolving path for frag: {frag}")
        if not frag:
            return None
        
        f = frag.strip('"').strip('`')
        
        # Simple filename in base_dir
        if self._base_dir and not any(sep in f for sep in (os.sep,'/','\\')):
            candidate = Path(self._base_dir) / f
            logger.debug(f"Resolved to base_dir candidate: {candidate}")
            return candidate.resolve()
        
        # Path with separators in base_dir
        if self._base_dir and any(sep in f for sep in ('/','\\')):
            candidate = Path(self._base_dir) / Path(f)
            candidate.parent.mkdir(parents=True, exist_ok=True)
            logger.debug(f"Resolved to base_dir path candidate: {candidate}")
            return candidate.resolve()
        
        # Search in roots
        search_roots = ([self._base_dir] if self._base_dir else []) + self._roots
        for root in search_roots:
            cand = Path(root) / f
            if cand.is_file():
                logger.debug(f"Found in roots: {cand}")
                return cand.resolve()
        
        # Create in first root
        p = Path(f)
        base = Path(self._roots[0]) / p.parent
        base.mkdir(parents=True, exist_ok=True)
        created = (base / p.name).resolve()
        logger.debug(f"Created new path: {created}")
        return created
    
    def safe_read_file(self, path: Path) -> str:
        """Safely read a file, handling binary files and encoding issues."""
        logger.debug(f"Safe read of: {path.absolute()}")
        try:
            # Check for binary content
            with open(path, 'rb') as bf:
                if b'\x00' in bf.read(1024):
                    raise UnicodeDecodeError("binary", b"", 0, 1, "null")
            content = path.read_text(encoding='utf-8')
            logger.debug(f"Successfully read file, {len(content.split())} tokens")
            return content
        except UnicodeDecodeError:
            logger.warning(f"Binary content detected for {path}, trying with ignore")
            try:
                content = path.read_text(encoding='utf-8', errors='ignore')
                logger.debug(f"Read with ignore, {len(content.split())} tokens")
                return content
            except Exception as e:
                logger.error(f"Failed to read {path}: {e}")
                return ""
        except Exception as e:
            logger.error(f"Failed to read {path}: {e}")
            return ""

    def write_file(self, path: Path, content: str):
        """Write content to the given path, creating directories as needed."""
        logger.debug(f"Writing file: {path}")
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding='utf-8')
            logger.info(f"Written file via FileService: {path} ({len(content.split())} tokens)")
        except Exception as e:
            logger.error(f"FileService.write_file failed for {path}: {e}")

    def write_file_lines(self, filepath: str, file_lines: List[str]):
        """Write file and update watcher."""
        logger.debug(f"Writing file lines to: {filepath}")
        Path(filepath).write_text(''.join(file_lines), encoding='utf-8')

    def write_file_text (self, filepath: str, content: str):
        """Write file and update watcher."""
        logger.debug(f"Writing text to: {filepath}")
        Path(filepath).write_text(content, encoding='utf-8')
# original file length: 82 lines
# updated file length: 102 lines