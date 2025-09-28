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
import traceback  # Added for stack traces
logger = logging.getLogger(__name__)
import re


class FileService:
    """Handles file operations and path resolution."""
    
    def __init__(self, roots: List[str], base_dir: str = None, backupFolder:str = None, app=None):
        logger.debug(f"Initializing FileService with roots: {roots}, base_dir: {base_dir}", extra={'log_color': 'HIGHLIGHT'})
        self._roots = roots
        self._base_dir = base_dir
        self._exclude_dirs = {"node_modules", "dist", "diffoutput"}
        self._backupFolder = backupFolder
        self._app = app
        logger.info(f"FileService initialized with {len(roots)} roots and exclude_dirs: {self._exclude_dirs}", extra={'log_color': 'HIGHLIGHT'})
    
    @property
    def base_dir(self) -> Optional[str]:
        return self._base_dir
    
    @base_dir.setter
    def base_dir(self, value: str):
        logger.debug(f"Setting base_dir to: {value}", extra={'log_color': 'HIGHLIGHT'})
        self._base_dir = value
        logger.info(f"Base directory updated to: {value}", extra={'log_color': 'HIGHLIGHT'})
    

 
  

    def _get_comment_style_for_extension(self, filename: str) -> str:
        """
        Determine the correct single‐line comment prefix for a given filename.
        Examples:
        .py   → "# "
        .js   → "// "
        .java → "/* "
        .xml  → "<!-- "
        .sql  → "-- "
        .md   → "<!-- "
        Falls back to "# " if the extension is unknown.
        """
           # Map extensions to their single‐line comment prefixes
        _COMMENT_PREFIXES = {
            # Hash‐style
            '.py':   '# ',
            '.rb':   '# ',
            '.sh':   '# ',
            '.bash': '# ',
            '.zsh':  '# ',
            '.yml':  '# ',
            '.yaml': '# ',
            '.txt':  '# ',   # plain text, just use hash
            # Double‐dash (SQL)
            '.sql':  '-- ',
            # C‐style and derivatives
            '.c':    '// ',
            '.h':    '// ',
            '.cpp':  '// ',
            '.cc':   '// ',
            '.cxx':  '// ',
            '.hpp':  '// ',
            '.cs':   '// ',
            '.go':   '// ',
            '.kt':   '// ',
            '.swift':'// ',
            '.rs':   '// ',
            # Java/Objective‐C block (you’ll only get the prefix here)
            '.java': '// ',
            '.php':  '// ',
            # JS/TS/JSX/TSX
            '.js':   '// ',
            '.ts':   '// ',
            '.jsx':  '// ',
            '.tsx':  '// ',
            # CSS/SCSS
            '.css':  '// ',
            '.scss': '// ',
            # HTML‐style (also Markdown & XML & JSON)
            '.html': '// ',
            '.htm':  '// ',
            '.xml':  '<!-- ',
            '.json': '<!-- ',
            '.md':   '# ',
        }
        ext = Path(filename).suffix.lower()
        prefix = _COMMENT_PREFIXES.get(ext)
        if prefix:
            return prefix
        logger.warning(
            "Unknown extension '%s' for %s, defaulting to '# '",
            ext, filename,
            extra={'log_color': 'DELTA'}
        )
        return "# "

    def _fix_comment_directive(self, content: str, filename: str) -> str:
        """
        Check existing content for a comment directive and fix if incorrect or missing.
        Scans for the first line matching the directive pattern and prepends the correct one if needed.
        Logs the fix applied. Enhanced to handle multi-line comments like XML (<!-- -->) and ensure closing tags.
        For XML/JSON, ensure the directive starts with <!-- and ends with --> if it's a single-line directive.
        Updated: For XML/JSON files (extensions .xml, .json), do not prepend directives if content starts with < or ?, to avoid comments before root element.
        If a leading directive exists before root, remove it. Support similar for other markup files.
        """
        logger.debug(f"Checking comment directive for {filename}", extra={'log_color': 'HIGHLIGHT'})
        ext = Path(filename).suffix.lower()
        is_xml_or_json = ext in ('.xml', '.json')
        lines = content.splitlines()
        directive_pattern = re.compile(r'^(#|//|/\*|< !--)\s*file:\s*(?P<fname>[^ \n]+)')
        existing_directive = None
        for i, line in enumerate(lines):
            match = directive_pattern.match(line.strip())
            if match:
                existing_directive = (match.group(1), match.group('fname'), i)
                break

        correct_style = self._get_comment_style_for_extension(filename)
        correct_prefix = f"{correct_style}file: {Path(filename).name}"

        # For XML/JSON: If content starts with < or ?, remove leading directive to avoid comments before root
        if is_xml_or_json:
            # Enhanced: Skip all leading lines that are comments or directives until non-comment content (e.g., root element)
            new_lines = []
            for i, line in enumerate(lines):
                stripped = line.strip()
                # Skip empty lines or lines that are comments/directives at the start
                if not stripped or stripped.startswith(('#', '//', '/*', '<!--')):
                    logger.debug(f"Skipping leading comment/directive line for {filename}: {stripped[:50]}...", extra={'log_color': 'HIGHLIGHT'})
                    continue
                # Found the start of actual content (e.g., <?xml or <tag>)
                if stripped.startswith(('<', '?xml')):
                    logger.info(f"Found XML/JSON root at line {i+1} for {filename}, starting content from here", extra={'log_color': 'HIGHLIGHT'})
                    new_lines = lines[i:]  # Keep from this line onward
                    break
                else:
                    # If non-comment but not XML root, treat as normal and proceed with original logic
                    new_lines = lines
                    break
            lines = new_lines if new_lines else lines
            content = '\n'.join(lines)

            # After trimming leading comments, do not prepend any directive for XML/JSON
            logger.info(f"No directive prepended for {filename} (XML/JSON root detected or leading comments skipped)", extra={'log_color': 'HIGHLIGHT'})
            return content  # Return as-is, no fix needed for directive addition

        # For non-XML/JSON or after handling above: Standard logic
        if not existing_directive:
            logger.info(f"No directive found in {filename}, adding: {correct_prefix}", extra={'log_color': 'HIGHLIGHT'})
            lines.insert(0, correct_prefix)
            return '\n'.join(lines)
        elif existing_directive[0] != correct_style.strip():
            logger.info(f"Incorrect directive in {filename}: '{existing_directive[0]}' -> '{correct_style}file: {filename}'", extra={'log_color': 'HIGHLIGHT'})
            # Replace the existing line
            i = existing_directive[2]
            lines[i] = f"{correct_prefix} --> " if correct_style == "<!-- " else correct_prefix  # Ensure XML closing if applicable
            return '\n'.join(lines)
        else:
            logger.debug(f"Correct directive already present in {filename}", extra={'log_color': 'HIGHLIGHT'})
            return content

    def search_files(self, patterns="*", recursive=True, roots=None, exclude_dirs=None):
        logger.info(f"Searching files with patterns: {patterns}, recursive: {recursive}", extra={'log_color': 'HIGHLIGHT'})
        if isinstance(patterns, str):
            patterns = patterns.split("|")
        else:
            patterns = list(patterns)
        exclude_dirs = set(exclude_dirs or self._exclude_dirs)
        matches = []
        roots_to_search = roots or self._roots
        logger.debug(f"Searching in {len(roots_to_search)} roots with {len(patterns)} patterns, excluding {exclude_dirs}", extra={'log_color': 'HIGHLIGHT'})
        for root in roots_to_search:
            if not os.path.isdir(root):
                logger.warning(f"Root directory not found: {root}", extra={'log_color': 'DELTA'})
                continue
            if recursive:
                for dirpath, dirnames, filenames in os.walk(root):
                    # Filter out excluded directories
                    dirnames[:] = [d for d in dirnames if d not in exclude_dirs]
                    logger.debug(f"Scanning directory: {dirpath}, filtered dirnames: {dirnames}", extra={'log_color': 'HIGHLIGHT'})
                    for fn in filenames:
                        full = os.path.join(dirpath, fn)
                        for pat in patterns:
                            if fnmatch.fnmatch(full, pat) or fnmatch.fnmatch(fn, pat):
                                matches.append(full)
                                logger.debug(f"Matched file: {full} with pattern: {pat}", extra={'log_color': 'PERCENT'})
                                break
            else:
                for fn in os.listdir(root):
                    full = os.path.join(root, fn)
                    if not os.path.isfile(full) or fn in exclude_dirs:
                        continue
                    for pat in patterns:
                        if fnmatch.fnmatch(full, pat) or fnmatch.fnmatch(fn, pat):
                            matches.append(full)
                            logger.debug(f"Matched file (non-recursive): {full} with pattern: {pat}", extra={'log_color': 'PERCENT'})
                            break
        logger.info(f"Search completed: {len(matches)} files matched", extra={'log_color': 'PERCENT'})
        return matches


    def find_files_by_pattern(self, pattern: str, recursive: bool, svc=None) -> List[str]:
        """Find files matching the given glob pattern."""
        logger.debug(f"find_files_by_pattern called with pattern: {pattern}, recursive: {recursive}", extra={'log_color': 'HIGHLIGHT'})
        found = self.search_files(patterns=pattern, recursive=recursive, roots=self._roots)
        logger.info(f"Found {len(found)} files matching pattern '{pattern}'", extra={'log_color': 'HIGHLIGHT'})
        return found
    
    def find_matching_file(self, filename: str, include_spec: dict, svc=None) -> Optional[Path]:
        """Find a file by name based on the include pattern."""
        logger.debug(f"find_matching_file called for {filename} with spec: {include_spec}", extra={'log_color': 'HIGHLIGHT'})
        files = self.find_files_by_pattern(
            include_spec['pattern'], 
            include_spec.get('recursive', False),
            svc
        )
        for f in files:
            if Path(f).name == filename:
                logger.info(f"Matching file found: {f}", extra={'log_color': 'HIGHLIGHT'})
                return Path(f)
        logger.debug("No matching file found", extra={'log_color': 'DELTA'})
        return None
    
    def resolve_path(self, frag: str, svc) -> Optional[Path]:
        logger.debug(f"Resolving path for frag: {frag}", extra={'log_color': 'HIGHLIGHT'})
        candidate = self.find_matching_file(frag, {'pattern':'*','recursive':True}, svc)
        logger.info(f"Resolved path for {frag}: {candidate}", extra={'log_color': 'HIGHLIGHT'})
        return candidate
    
    def safe_read_file(self, path: Path) -> str:
        """Safely read a file, handling binary files and encoding issues. Enhanced to fix comment directives after reading."""
        logger.debug(f"Safe read of: {path.absolute()}", extra={'log_color': 'HIGHLIGHT'})
        if not path.exists():
            logger.warning(f"File not found: {path.absolute()}", extra={'log_color': 'DELTA'})
            return ""
        try:
            # Check for binary content
            with open(path, 'rb') as bf:
                sample = bf.read(1024)
                if b'\x00' in sample:
                    logger.warning(f"Binary content detected for {path}, treating as binary", extra={'log_color': 'DELTA'})
                    raise UnicodeDecodeError("binary", b"", 0, 1, "null")
            content = path.read_text(encoding='utf-8')
            # Enhanced: Apply directive fix after reading to ensure consistency
            content = self._fix_comment_directive(content, path.name)
            logger.debug(f"Applied post-read directive fix for {path.name}")
            token_count = len(content.split())
            logger.info(f"Successfully read file: {path}, {token_count} tokens", extra={'log_color': 'HIGHLIGHT'})
            return content
        except UnicodeDecodeError as ude:
            logger.warning(f"Binary content detected for {path}, trying with ignore: {ude}", extra={'log_color': 'DELTA'})
            try:
                content = path.read_text(encoding='utf-8', errors='ignore')
                # Enhanced: Still try to fix directive if possible, even on ignored content
                if len(content) > 0:
                    content = self._fix_comment_directive(content, path.name)
                    logger.debug(f"Applied post-read directive fix on ignored content for {path.name}")
                token_count = len(content.split())
                logger.info(f"Read with ignore: {path}, {token_count} tokens", extra={'log_color': 'HIGHLIGHT'})
                return content
            except Exception as e:
                logger.error(f"Failed to read {path} with ignore: {e}", extra={'log_color': 'DELTA'})
                logger.error(traceback.format_exc(), extra={'log_color': 'DELTA'})  # Added stack trace
                return ""
        except Exception as e:
            logger.error(f"Failed to read {path}: {e}", extra={'log_color': 'DELTA'})
            logger.error(traceback.format_exc(), extra={'log_color': 'DELTA'})  # Added stack trace
            return ""

    def binary_read(self, path: Path) -> bytes:
        """Safely read a file as binary."""
        logger.debug(f"Binary read of: {path.absolute()}", extra={'log_color': 'HIGHLIGHT'})
        if not path.exists():
            logger.warning(f"Binary file not found: {path.absolute()}", extra={'log_color': 'DELTA'})
            return b""
        try:
            content = path.read_bytes()
            logger.info(f"Successfully read binary file: {path}, {len(content)} bytes", extra={'log_color': 'HIGHLIGHT'})
            return content
        except Exception as e:
            logger.error(f"Failed to read binary {path}: {e}", extra={'log_color': 'DELTA'})
            logger.error(traceback.format_exc(), extra={'log_color': 'DELTA'})  # Added stack trace
            return b""

    def write_file(self, path: Path, content: str):
        """
        Atomically write `content` to `path`, creating directories as needed.
        If atomic replace fails, falls back to a simple write.
        Applies cleanup mechanism to ensure correct comment directive based on file type. Enhanced to always apply fix before writing.
        """
        path = Path(path)
        logger.debug(f"Writing file {path} (atomic, with fsync, fallback, and directive cleanup)", extra={'log_color': 'HIGHLIGHT'})
        token_count = len(content.split())

        # Enhanced: Apply directive cleanup before writing, ensuring correct style
        content = self._fix_comment_directive(content, path.name)
        logger.debug(f"Applied pre-write directive fix for {path.name}")

        # 1) ensure parent directories exist
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            logger.debug(f"Ensured parent directories for {path}", extra={'log_color': 'HIGHLIGHT'})
        except Exception as e:
            logger.error(f"Failed to create parent dirs for {path}: {e}", extra={'log_color': 'DELTA'})
            logger.error(traceback.format_exc(), extra={'log_color': 'DELTA'})  # Added stack trace
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
            logger.debug(f"Created temp file: {tmp_name}", extra={'log_color': 'HIGHLIGHT'})

            # 3) write, flush, fsync
            with os.fdopen(fd, "w", encoding="utf-8") as tmp_file:
                tmp_file.write(content)
                tmp_file.flush()
                os.fsync(tmp_file.fileno())
                logger.debug(f"Wrote and synced temp file for {path}", extra={'log_color': 'HIGHLIGHT'})

            # 4) atomic replace (overwrites or creates)
            os.replace(tmp_name, str(path))
            tmp_name = None  # prevent cleanup in finally
            logger.info(f"Written (atomic): {path} ({token_count} tokens)", extra={'log_color': 'HIGHLIGHT'})

        except Exception as atomic_exc:
            logger.warning(f"Atomic write failed for {path}: {atomic_exc}", extra={'log_color': 'DELTA'})
            logger.error(traceback.format_exc(), extra={'log_color': 'DELTA'})  # Added stack trace
            # fallback: simple write
            try:
                if tmp_name and os.path.exists(tmp_name):
                    os.remove(tmp_name)
                    logger.debug(f"Cleaned up temp file {tmp_name}", extra={'log_color': 'HIGHLIGHT'})
                with open(path, "w", encoding="utf-8") as f:
                    f.write(content)
                    f.flush()
                    os.fsync(f.fileno())
                logger.info(f"Written (fallback): {path} ({token_count} tokens)", extra={'log_color': 'HIGHLIGHT'})
            except Exception as fallback_exc:
                logger.error(f"Fallback write also failed for {path}: {fallback_exc}", extra={'log_color': 'DELTA'})
                logger.error(traceback.format_exc(), extra={'log_color': 'DELTA'})  # Added stack trace

        finally:
            # Cleanup stray temp file if something went wrong
            if tmp_name and os.path.exists(tmp_name):
                try:
                    os.remove(tmp_name)
                    logger.debug(f"Cleaned up stray temp file {tmp_name}", extra={'log_color': 'HIGHLIGHT'})
                except Exception:
                    logger.warning(f"Failed to clean up temp file {tmp_name}", extra={'log_color': 'DELTA'})
                    logger.error(traceback.format_exc(), extra={'log_color': 'DELTA'})  # Added stack trace

    def ensure_dir(self, path: Path, parents: bool = True, exist_ok: bool = True):
        """Ensure directory exists, creating parents if needed."""
        logger.debug(f"Ensuring directory: {path}", extra={'log_color': 'HIGHLIGHT'})
        try:
            path.mkdir(parents=parents, exist_ok=exist_ok)
            logger.info(f"Ensured directory: {path}", extra={'log_color': 'HIGHLIGHT'})
        except Exception as e:
            logger.error(f"Failed to ensure directory {path}: {e}", extra={'log_color': 'DELTA'})
            logger.error(traceback.format_exc(), extra={'log_color': 'DELTA'})  # Added stack trace

    def delete_file(self, path: Path):
        """Delete a file if it exists."""
        logger.debug(f"Deleting file: {path}", extra={'log_color': 'HIGHLIGHT'})
        if path.exists():
            try:
                path.unlink()
                logger.info(f"Deleted file: {path}", extra={'log_color': 'DELTA'})
            except Exception as e:
                logger.error(f"Failed to delete file {path}: {e}", extra={'log_color': 'DELTA'})
                logger.error(traceback.format_exc(), extra={'log_color': 'DELTA'})  # Added stack trace
        else:
            logger.warning(f"File not found for deletion: {path}", extra={'log_color': 'DELTA'})

    def append_file(self, path: Path, content: str):
        """Append content to a file, creating directories if needed."""
        logger.debug(f"Appending to file: {path}", extra={'log_color': 'HIGHLIGHT'})
        try:
            self.ensure_dir(path.parent)
            # Enhanced: Apply directive fix to appended content as well
            content = self._fix_comment_directive(content, path.name)
            with path.open('a', encoding='utf-8') as f:
                f.write(content)
            token_count = len(content.split())
            logger.info(f"Appended to file: {path}, {token_count} tokens", extra={'log_color': 'HIGHLIGHT'})
        except Exception as e:
            logger.error(f"Failed to append to file {path}: {e}", extra={'log_color': 'DELTA'})
            logger.error(traceback.format_exc(), extra={'log_color': 'DELTA'})  # Added stack trace

    def delete_dir(self, path: Path, recursive: bool = False):
        """Delete a directory, optionally recursive."""
        logger.debug(f"Deleting directory: {path}, recursive: {recursive}", extra={'log_color': 'HIGHLIGHT'})
        try:
            if recursive:
                shutil.rmtree(path)
            else:
                path.rmdir()
            logger.info(f"Deleted directory: {path} (recursive: {recursive})", extra={'log_color': 'DELTA'})
        except Exception as e:
            logger.error(f"Failed to delete directory {path}: {e}", extra={'log_color': 'DELTA'})
            logger.error(traceback.format_exc(), extra={'log_color': 'DELTA'})  # Added stack trace

    def rename(self, src: Path, dst: Path):
        """Rename or move a file/directory."""
        logger.debug(f"Renaming: {src} -> {dst}", extra={'log_color': 'HIGHLIGHT'})
        try:
            self.ensure_dir(dst.parent)
            src.rename(dst)
            logger.info(f"Renamed: {src} -> {dst}", extra={'log_color': 'HIGHLIGHT'})
        except Exception as e:
            logger.error(f"Failed to rename {src} to {dst}: {e}", extra={'log_color': 'DELTA'})
            logger.error(traceback.format_exc(), extra={'log_color': 'DELTA'})  # Added stack trace

    def copy_file(self, src: Path, dst: Path):
        """Copy a file."""
        logger.debug(f"Copying file: {src} -> {dst}", extra={'log_color': 'HIGHLIGHT'})
        try:
            self.ensure_dir(dst.parent)
            shutil.copy2(src, dst)
            logger.info(f"Copied file: {src} -> {dst}", extra={'log_color': 'HIGHLIGHT'})
        except Exception as e:
            logger.error(f"Failed to copy file {src} to {dst}: {e}", extra={'log_color': 'DELTA'})
            logger.error(traceback.format_exc(), extra={'log_color': 'DELTA'})  # Added stack trace

# Original file length: 360 lines
# Updated file length: 378 lines