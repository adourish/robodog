# file: file_service.py
#!/usr/bin/env python3
"""File operations and path resolution service."""
import os
import logging
from typing import List, Optional
from pathlib import Path
import tempfile
import fnmatch
import shutil
logger = logging.getLogger(__name__)


class FileService:
    """Handles file operations and path resolution."""
    
    def __init__(self, roots: List[str], base_dir: str = None, backupFolder:str = None):
        logger.debug(f"Initializing FileService with roots: {roots}, base_dir: {base_dir}")
        self._roots = roots
        self._base_dir = base_dir
        self._exclude_dirs = {"node_modules", "dist", "diffoutput"}
        self._backupFolder = backupFolder
        logger.info(f"FileService initialized with backup folder: {backupFolder}")
    @property
    def base_dir(self) -> Optional[str]:
        return self._base_dir
    
    @base_dir.setter
    def base_dir(self, value: str):
        logger.debug(f"Setting base_dir to: {value}")
        self._base_dir = value
    
    def search_files(self, patterns="*", recursive=True, roots=None, exclude_dirs=None):
        logger.info(f"Searching files with patterns: {patterns}, recursive: {recursive}")
        if isinstance(patterns, str):
            patterns = patterns.split("|")
        else:
            patterns = list(patterns)
        exclude_dirs = set(exclude_dirs or self._exclude_dirs)
        matches = []
        for root in roots or []:
            if not os.path.isdir(root):
                logger.warning(f"Root directory not found: {root}")
                continue
            if recursive:
                for dirpath, dirnames, filenames in os.walk(root):
                    dirnames[:] = [d for d in dirnames if d not in exclude_dirs]
                    for fn in filenames:
                        full = os.path.join(dirpath, fn)
                        for pat in patterns:
                            if fnmatch.fnmatch(full, pat) or fnmatch.fnmatch(fn, pat):
                                matches.append(full)
                                logger.debug(f"Matched file: {full}")
                                break
            else:
                for fn in os.listdir(root):
                    full = os.path.join(root, fn)
                    if not os.path.isfile(full) or fn in exclude_dirs:
                        continue
                    for pat in patterns:
                        if fnmatch.fnmatch(full, pat) or fnmatch.fnmatch(fn, pat):
                            matches.append(full)
                            logger.debug(f"Matched file: {full}")
                            break
        logger.info(f"Search completed, found {len(matches)} matches")
        return matches


    def find_files_by_pattern(self, pattern: str, recursive: bool, svc=None) -> List[str]:
        """Find files matching the given glob pattern."""
        logger.info(f"Finding files by pattern: {pattern}, recursive: {recursive}")
        if svc:
            results = self.search_files(patterns=pattern, recursive=recursive, roots=self._roots)
            logger.debug(f"Found {len(results)} files")
            return results
        logger.warning("Svc not provided, returning empty list")
        return []
    
    def find_matching_file(self, filename: str, include_spec: dict, svc=None) -> Optional[Path]:
        """Find a file by name based on the include pattern."""
        logger.info(f"Finding matching file for: {filename}")
        files = self.find_files_by_pattern(
            include_spec['pattern'], 
            include_spec.get('recursive', False),
            svc
        )
        for f in files:
            if Path(f).name == filename:
                logger.info(f"Matching file found: {f}")
                return Path(f)
        logger.warning(f"No matching file found for: {filename}")
        return None
    
    def resolve_path(self, frag: str, svc) -> Optional[Path]:

        candidate = self.find_matching_file(frag, {'pattern':'*','recursive':True}, svc)
        """Resolve a file fragment to an absolute path."""
        logger.debug(f"Resolving path for frag: {frag}")
        if candidate:
            logger.info(f"Resolved path: {candidate}")
        return candidate
    
    def safe_read_file(self, path: Path) -> str:
        """Safely read a file, handling binary files and encoding issues."""
        logger.info(f"Safe read of: {path.absolute()}")
        try:
            # Check for binary content
            with open(path, 'rb') as bf:
                if b'\x00' in bf.read(1024):
                    logger.warning(f"Binary content detected in {path}, treating as binary")
                    raise UnicodeDecodeError("binary", b"", 0, 1, "null")
            content = path.read_text(encoding='utf-8')
            token_count = len(content.split())
            logger.info(f"Successfully read file {path}, {token_count} tokens")
            return content
        except UnicodeDecodeError:
            logger.warning(f"Binary content detected for {path}, trying with ignore")
            try:
                content = path.read_text(encoding='utf-8', errors='ignore')
                token_count = len(content.split())
                logger.info(f"Read binary file with ignore: {path}, {token_count} tokens")
                return content
            except Exception as e:
                logger.error(f"Failed to read {path} with ignore: {e}")
                return ""
        except Exception as e:
            logger.error(f"Failed to read {path}: {e}")
            return ""

    def binary_read(self, path: Path) -> bytes:
        """Safely read a file as binary."""
        logger.info(f"Binary read of: {path.absolute()}")
        try:
            content = path.read_bytes()
            logger.info(f"Successfully read binary file: {path}, {len(content)} bytes")
            return content
        except Exception as e:
            logger.error(f"Failed to read binary {path}: {e}")
            return b""

    def write_file(self, path: Path, content: str):
        """
        Atomically write `content` to `path`, creating directories as needed.
        If atomic replace fails, falls back to a simple write.
        """
        path = Path(path)
        logger.info(f"Writing file {path} (atomic, with fsync and fallback)")
        token_count = len(content.split())

        # 1) ensure parent directories exist
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            logger.debug(f"Ensured parent directories for {path}")
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
                logger.debug(f"Wrote to temp file: {tmp_name}")

            # 4) atomic replace (overwrites or creates)
            os.replace(tmp_name, str(path))
            tmp_name = None  # prevent cleanup in finally
            logger.info(f"Written (atomic): {path} ({token_count} tokens)")

        except Exception as atomic_exc:
            logger.warning(f"Atomic write failed for {path}: {atomic_exc}")
            # fallback: simple write
            try:
                if tmp_name and os.path.exists(tmp_name):
                    os.remove(tmp_name)
                    logger.debug(f"Cleaned up temp file: {tmp_name}")
                with open(path, "w", encoding="utf-8") as f:
                    f.write(content)
                    f.flush()
                    os.fsync(f.fileno())
                logger.info(f"Written (fallback): {path} ({token_count} tokens)")
            except Exception as fallback_exc:
                logger.error(f"Fallback write also failed for {path}: {fallback_exc}")

        finally:
            # Cleanup stray temp file if something went wrong
            if tmp_name and os.path.exists(tmp_name):
                try:
                    os.remove(tmp_name)
                    logger.debug(f"Cleaned up stray temp file: {tmp_name}")
                except Exception:
                    logger.warning(f"Failed to clean up stray temp file: {tmp_name}")

    def ensure_dir(self, path: Path, parents: bool = True, exist_ok: bool = True):
        """Ensure directory exists, creating parents if needed."""
        logger.debug(f"Ensuring directory: {path}, parents: {parents}, exist_ok: {exist_ok}")
        try:
            path.mkdir(parents=parents, exist_ok=exist_ok)
            logger.info(f"Directory ensured: {path}")
        except Exception as e:
            logger.error(f"Failed to ensure directory {path}: {e}")

    def delete_file(self, path: Path):
        """Delete a file if it exists."""
        logger.info(f"Deleting file: {path}")
        if path.exists():
            try:
                path.unlink()
                logger.info(f"Deleted file: {path}")
            except Exception as e:
                logger.error(f"Failed to delete {path}: {e}")
        else:
            logger.warning(f"File to delete not found: {path}")

    def append_file(self, path: Path, content: str):
        """Append content to a file, creating directories if needed."""
        logger.info(f"Appending to file: {path}")
        token_count = len(content.split())
        self.ensure_dir(path.parent)
        with path.open('a', encoding='utf-8') as f:
            f.write(content)
            logger.info(f"Appended {token_count} tokens to {path}")

    def delete_dir(self, path: Path, recursive: bool = False):
        """Delete a directory, optionally recursive."""
        logger.info(f"Deleting directory: {path}, recursive: {recursive}")
        try:
            if recursive:
                shutil.rmtree(path)
            else:
                path.rmdir()
            logger.info(f"Deleted directory: {path}")
        except Exception as e:
            logger.error(f"Failed to delete directory {path}: {e}")

    def rename(self, src: Path, dst: Path):
        """Rename or move a file/directory."""
        logger.info(f"Renaming {src} to {dst}")
        self.ensure_dir(dst.parent)
        src.rename(dst)
        logger.info(f"Renamed {src} to {dst}")

    def copy_file(self, src: Path, dst: Path):
        """Copy a file."""
        logger.info(f"Copying file {src} to {dst}")
        self.ensure_dir(dst.parent)
        shutil.copy2(src, dst)
        logger.info(f"Copied {src} to {dst}")

# original file length: 142 lines
# updated file length: 214 lines

# file: plan.md NEW
# Plan for Adding Logging to FileService

## Task Summary
The task is to add logging to the `file_service.py` module. This involves enhancing the existing logger with more detailed log statements in key methods to track file operations, errors, and performance metrics like token counts where applicable.

## Outline of Changes
1. **Import and Logger Setup**: The file already has `import logging` and `logger = logging.getLogger(__name__)`. No change needed here.
2. **Method Enhancements**:
   - `__init__`: Log initialization details.
   - `search_files`: Log search patterns, recursion, and number of matches.
   - `find_files_by_pattern` and `find_matching_file`: Log patterns and results.
   - `resolve_path`: Log resolution attempts.
   - `safe_read_file`: Log read attempts, binary detection, token counts, and errors.
   - `binary_read`: Log binary reads and byte counts.
   - `write_file`: Log write attempts, atomic operations, token counts, and fallbacks.
   - `ensure_dir`: Log directory creation.
   - `delete_file`: Log deletions and existence checks.
   - `append_file`: Log appends and token counts.
   - `delete_dir`: Log directory deletions.
   - `rename`: Log renames.
   - `copy_file`: Log copies.
3. **Logging Levels**: Use INFO for key actions, DEBUG for details, WARNING for issues, ERROR for failures.

## Implementation Details
- Added logger calls at entry/exit points and after key operations.
- Ensured logs include paths, token counts, and results for traceability.
- Maintained existing functionality; logging is additive.

## Next Steps
1. Test the updated `file_service.py` with various operations to verify logs.
2. Integrate with the TodoService to ensure logging captures task-related file actions.
3. If needed, adjust log levels or add more granularity based on runtime behavior.
4. Mark this task as complete in todo.md after verification.