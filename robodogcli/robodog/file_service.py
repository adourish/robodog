# file: file_service.py
#!/usr/bin/env python3
"""File operations and path resolution service."""
import os
import logging
from typing import List, Optional
from pathlib import Path
import tempfile
import fnmatch
logger = logging.getLogger(__name__)


class FileService:
    """Handles file operations and path resolution."""
    
    def __init__(self, roots: List[str], base_dir: str = None):
        logger.debug(f"Initializing FileService with roots: {roots}, base_dir: {base_dir}")
        self._roots = roots
        self._base_dir = base_dir
        self._exclude_dirs = {"node_modules", "dist"}
    
    @property
    def base_dir(self) -> Optional[str]:
        return self._base_dir
    
    @base_dir.setter
    def base_dir(self, value: str):
        logger.debug(f"Setting base_dir to: {value}")
        self._base_dir = value
    
    def search_files(self, patterns="*", recursive=True, roots=None, exclude_dirs=None):
        if isinstance(patterns, str):
            patterns = patterns.split("|")
        else:
            patterns = list(patterns)
        exclude_dirs = set(exclude_dirs or self._exclude_dirs)
        matches = []
        for root in roots or []:
            if not os.path.isdir(root):
                continue
            if recursive:
                for dirpath, dirnames, filenames in os.walk(root):
                    dirnames[:] = [d for d in dirnames if d not in exclude_dirs]
                    for fn in filenames:
                        full = os.path.join(dirpath, fn)
                        for pat in patterns:
                            if fnmatch.fnmatch(full, pat) or fnmatch.fnmatch(fn, pat):
                                matches.append(full)
                                break
            else:
                for fn in os.listdir(root):
                    full = os.path.join(root, fn)
                    if not os.path.isfile(full) or fn in exclude_dirs:
                        continue
                    for pat in patterns:
                        if fnmatch.fnmatch(full, pat) or fnmatch.fnmatch(fn, pat):
                            matches.append(full)
                            break
        return matches


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
            logger.info(f"Resolved to base_dir candidate: {candidate}")
            return candidate.resolve()
        
        # Path with separators in base_dir
        if self._base_dir and any(sep in f for sep in ('/','\\')):
            candidate = Path(self._base_dir) / Path(f)
            candidate.parent.mkdir(parents=True, exist_ok=True)
            logger.info(f"Resolved to base_dir path candidate: {candidate}")
            return candidate.resolve()
        
        # Search in roots
        search_roots = ([self._base_dir] if self._base_dir else []) + self._roots
        for root in search_roots:
            cand = Path(root) / f
            if cand.is_file():
                logger.info(f"Found in roots: {cand}")
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
        """
        Atomically write `content` to `path`, creating directories as needed.
        If atomic replace fails, falls back to a simple write.
        """
        path = Path(path)
        logger.info(f"Writing file {path} (atomic, with fsync and fallback)")

        # 1) ensure parent directories exist
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
        except Exception as e:
            logger.error(f"Failed to create parent dirs for {path}: {e}")
            # Proceed anyway—if mkdir failed for reasons other than exists, write may still work

        tmp_name = None
        try:
            # 2) create a real temp file in the same dir for atomic rename
            dirpath = str(path.parent) or os.getcwd()
            fd, tmp_name = tempfile.mkstemp(
                dir=dirpath,              # ← fixed!
                prefix=path.name + ".",
                suffix=".tmp"
            )

            # 3) write, flush, fsync
            with os.fdopen(fd, "w", encoding="utf-8") as tmp_file:
                tmp_file.write(content)
                tmp_file.flush()
                os.fsync(tmp_file.fileno())

            # 4) atomic replace (overwrites or creates)
            os.replace(tmp_name, str(path))
            tmp_name = None  # prevent cleanup in finally
            token_count = len(content.split())
            logger.info(f"Written (atomic): {path} ({token_count} tokens)")

        except Exception as atomic_exc:
            logger.warning(f"Atomic write failed for {path}: {atomic_exc}")
            # fallback: simple write
            try:
                if tmp_name and os.path.exists(tmp_name):
                    os.remove(tmp_name)
                with open(path, "w", encoding="utf-8") as f:
                    f.write(content)
                    f.flush()
                    os.fsync(f.fileno())
                token_count = len(content.split())
                logger.debug(f"Written (fallback): {path} ({token_count} tokens)")
            except Exception as fallback_exc:
                logger.error(f"Fallback write also failed for {path}: {fallback_exc}")

        finally:
            # Cleanup stray temp file if something went wrong
            if tmp_name and os.path.exists(tmp_name):
                try:
                    os.remove(tmp_name)
                except Exception:
                    pass
# original file length: 84 lines
# updated file length: 83 lines