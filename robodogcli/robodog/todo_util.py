# file: todo_util.py
#!/usr/bin/env python3
"""Utility functions for TodoService, including metadata parsing and desc sanitization."""

# CRITICAL IMPORTS - DO NOT REMOVE OR MODIFY - REQUIRED FOR FUNCTIONALITY
import os
import re
import time
import threading
import logging
import traceback
import shutil
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Dict, Tuple, Any
import statistics
from smart_merge import SmartMerge
from smart_merge_precise import PreciseSmartMerge

import tiktoken
from pydantic import BaseModel, RootModel
import yaml  # ensure PyYAML is installed

logger = logging.getLogger(__name__)

# Import dashboard components for confirmation dialogs
try:
    from dashboard import CommitConfirmation
except ImportError:
    CommitConfirmation = None  # Fallback if dashboard not available
try:
    from .parse_service import ParseService
except ImportError:
    from parse_service import ParseService
try:
    from .file_service import FileService
except ImportError:
    from file_service import FileService
# END CRITICAL IMPORTS

class TodoUtilService:
    # CRITICAL METHOD - DO NOT REMOVE - REQUIRED FOR INITIALIZATION
    def __init__(
        self,
        roots: List[str],
        svc=None,
        prompt_builder=None,
        task_manager=None,
        task_parser=None,
        file_watcher=None,
        file_service=None,
        exclude_dirs={"node_modules", "dist", "diffout"},
        app=None,
        enable_smart_merge=True
    ):
        logger.info(f"Initializing TodoUtilService with roots: {roots}", extra={'log_color': 'HIGHLIGHT'})
        logger.debug(f"Svc provided: {svc is not None}, Prompt builder: {prompt_builder is not None}")
        try:
            self._roots = roots
            self._svc = svc
            self._prompt_builder = prompt_builder
            self._task_manager = task_manager
            self._task_parser = task_parser
            self._file_watcher = file_watcher
            self._file_service = file_service
            self._exclude_dirs = exclude_dirs
            self._app = app
            # Use PreciseSmartMerge for more reliable line-by-line changes
            self._smart_merge = PreciseSmartMerge(similarity_threshold=0.85) if enable_smart_merge else None
            logger.info(f"PreciseSmartMerge {'enabled' if self._smart_merge else 'disabled'} (threshold=0.85)", extra={'log_color': 'HIGHLIGHT'})
        except Exception as e:
            logger.exception(f"Error during initialization of TodoUtilService: {e}", extra={'log_color': 'DELTA'})
            raise

    def _get_plan_out_path(self, raw_spec: Any, base_folder: str = "") -> Optional[Path]:
        """
        Resolve the plan.md output path from the task's plan_spec.
        raw_spec may be {'plan': {...}} or a direct spec dict/string.
        Always returns a Path under the task's folder.
        """
        plan_spec = None
        # unpack raw_spec
        if isinstance(raw_spec, dict) and 'plan' in raw_spec:
            plan_spec = raw_spec['plan']
        else:
            plan_spec = raw_spec

        out_path: Optional[Path] = None

        # if spec is a simple string
        if isinstance(plan_spec, str) and plan_spec.strip():
            out_path = Path(plan_spec)
        # if spec is a dict with 'pattern'
        elif isinstance(plan_spec, dict):
            pattern = plan_spec.get('pattern', '').strip() or "plan.md"
            out_path = Path(pattern)

        # make it under base_folder if not absolute
        if out_path:
            if not out_path.is_absolute() and base_folder:
                out_path = Path(base_folder) / out_path
            # ensure parent exists
            out_path.parent.mkdir(parents=True, exist_ok=True)
        return out_path

    def _write_plan(self, svc, plan_path: Path, content: str) -> int:
        """
        Write the plan.md to disk, returning the token count of the content.
        """
        if not plan_path:
            return 0
        try:
            # write the file
            self._file_service.write_file(plan_path, content)
            # simple whitespace‐based token count
            tok = len(content.strip().split())
            logger.info(f"Wrote plan to: {plan_path} ({tok} tokens)", extra={'log_color': 'PERCENT'})
            return tok
        except Exception as e:
            logger.exception(f"Failed to write plan to {plan_path}: {e}", extra={'log_color': 'DELTA'})
            return 0
    
    def _prepare_diff_payload(self, raw_body: str) -> str:
        """Extract just the unified-diff body from a fenced code block, if present."""
        if not raw_body:
            return ""
        stripped = raw_body.lstrip()
        if not stripped.startswith("```"):
            text = raw_body
        else:
            lines = stripped.splitlines()
            if not lines:
                return ""
            header = lines[0].strip()
            lang = header.strip('`').strip().lower()
            if lang in ("", "diff"):
                content_lines = lines[1:]
                while content_lines and content_lines[-1].strip() == "```":
                    content_lines.pop()
                text = "\n".join(content_lines)
            else:
                text = stripped
        text = text.lstrip('\n')
        if text and not text.endswith('\n'):
            text += '\n'
        return text

    def _parse_task_metadata(self, full_desc: str) -> Dict:
        """
        Parse the task description for metadata. Splits on the first '|' only,
        treats the remainder as metadata blob, and deduplicates keys so that
        duplicate '| knowledge: ...' or '| include: ...' entries are ignored.
        """
        logger.debug(f"Parsing metadata for task desc: {full_desc}")
        try:
            raw_desc = full_desc.rstrip()
            # Separate main description and metadata blob
            if '|' in raw_desc:
                base_part, meta_part = raw_desc.split('|', 1)
            else:
                base_part, meta_part = raw_desc, ''
            base_desc = base_part.strip()

            metadata = {
                '_raw_desc': raw_desc,
                'desc': base_desc,
                'plan_desc': base_desc,
                'llm_desc': base_desc,
                'commit_desc': base_desc,
                '_start_stamp': None,
                '_complete_stamp': None,
                'knowledge_tokens': 0,
                'include_tokens': 0,
                'prompt_tokens': 0,
                'plan_tokens': 0,
            }

            seen_keys = set()
            # Parse and dedupe metadata items
            for part in [p.strip() for p in meta_part.split('|') if p.strip()]:
                if ':' not in part:
                    continue
                key, val = [s.strip() for s in part.split(':', 1)]
                key_lower = key.lower()
                if key_lower in seen_keys:
                    continue
                seen_keys.add(key_lower)
                if key_lower == 'started':
                    metadata['_start_stamp'] = None if val.lower() == 'none' else val
                elif key_lower == 'completed':
                    metadata['_complete_stamp'] = None if val.lower() == 'none' else val
                elif key_lower == 'knowledge' and val.isdigit():
                    metadata['knowledge_tokens'] = int(val)
                elif key_lower == 'include' and val.isdigit():
                    metadata['include_tokens'] = int(val)
                elif key_lower == 'prompt' and val.isdigit():
                    metadata['prompt_tokens'] = int(val)
                elif key_lower == 'plan':
                    if val.isdigit():
                        metadata['plan_tokens'] = int(val)
                    else:
                        metadata['plan_desc'] = val
                elif key_lower in ('plan_desc', 'llm_desc', 'commit_desc'):
                    metadata[key_lower] = val

            logger.debug(f"Final parsed metadata: {metadata}")
            return metadata

        except Exception as e:
            logger.exception(f"Error parsing task metadata for '{full_desc}': {e}", extra={'log_color': 'DELTA'})
            clean = full_desc.strip()
            return {
                '_raw_desc': full_desc.rstrip(),
                'desc': clean,
                'plan_desc': clean,
                'llm_desc': clean,
                'commit_desc': clean,
                '_start_stamp': None,
                '_complete_stamp': None,
                'knowledge_tokens': 0,
                'include_tokens': 0,
                'prompt_tokens': 0,
                'plan_tokens': 0,
            }

    def _ensure_parsed_entry(self, entry: Optional[dict], base_folder: str) -> dict:
        """
        Fill in filename, originalfilename, and matchedfilename for a parsed entry.
        Ensures these keys exist and are resolved paths where possible.
        """
        data: Dict[str, Any] = dict(entry or {})
        filename_candidate = data.get('filename') or data.get('relative_path') or data.get('path') or data.get('name')
        filename_str = str(filename_candidate) if filename_candidate else ''
        data['filename'] = filename_str

        relative_candidate = data.get('relative_path') or filename_str or data.get('path')
        relative = str(relative_candidate) if relative_candidate else ''
        if relative:
            data['relative_path'] = relative

        # --- Resolve matchedfilename ---
        matched = data.get('matchedfilename') or data.get('matched_filename')
        resolved_match: Optional[Path] = None
        if matched:
            try:
                resolved_match = Path(matched)
                if not resolved_match.is_absolute() and base_folder:
                    resolved_match = (Path(base_folder) / resolved_match).resolve()
                else:
                    resolved_match = resolved_match.resolve() if resolved_match.exists() else resolved_match
            except Exception:
                resolved_match = None
        if resolved_match is None and relative:
            resolved_match = self._try_resolve_path(relative, base_folder)
        if resolved_match is not None:
            matched_str = str(resolved_match)
            data['matchedfilename'] = matched_str
        elif not data.get('matchedfilename'): # If not resolved, use filename as fallback if possible
            fallback = None
            try:
                if relative:
                    if base_folder:
                        fallback = (Path(base_folder) / relative).resolve()
                    else:
                        fallback = Path(relative).resolve()
            except Exception:
                fallback = Path(base_folder) / relative if base_folder and relative else None
            if fallback is not None:
                data['matchedfilename'] = str(fallback)
            else:
                data['matchedfilename'] = data.get('matchedfilename') or filename_str

        # --- Resolve originalfilename ---
        original = data.get('originalfilename') or data.get('original_filename')
        if original:
            try:
                original_path = Path(original)
                if not original_path.is_absolute() and base_folder:
                    original_path = (Path(base_folder) / original_path).resolve()
                else:
                    original_path = original_path.resolve() if original_path.exists() else original_path
                data['originalfilename'] = str(original_path)
            except Exception:
                data['originalfilename'] = str(original)
        else:
            # If original not provided, use matchedfilename if available, else filename
            data['originalfilename'] = data.get('matchedfilename') or filename_str
        
        # --- Ensure relative_path is set if filename/path exists ---
        if filename_str and 'relative_path' not in data:
            data['relative_path'] = filename_str

        # Update the original entry if it was a dict
        if isinstance(entry, dict):
            entry.update({
                'filename': data.get('filename', ''),
                'relative_path': data.get('relative_path', ''),
                'matchedfilename': data.get('matchedfilename', ''),
                'originalfilename': data.get('originalfilename', '')
            })

        return data

    def _try_resolve_path(self, fragment: str, base_folder: str = "") -> Optional[Path]:
        if not fragment:
            return None
        try:
            # Use the file_service's resolve_path if available and appropriate
            if self._svc and hasattr(self._svc, 'file_service') and self._svc.file_service:
                resolved = self._svc.file_service.resolve_path(fragment, self._svc)
                if resolved:
                    return Path(resolved)
            elif self._file_service:
                 resolved = self._file_service.resolve_path(fragment, self._svc)
                 if resolved:
                    return Path(resolved)
        except Exception:
            pass # Continue to manual resolution
        
        try:
            frag_path = Path(fragment)
            if frag_path.is_absolute():
                return frag_path.resolve()
            if base_folder:
                return (Path(base_folder) / frag_path).resolve()
            if self._file_service and getattr(self._file_service, 'base_dir', None):
                return (Path(self._file_service.base_dir) / frag_path).resolve()
            return frag_path.resolve()
        except Exception:
            return None


    def _write_parsed_files(
        self,
        parsed_files: List[dict],
        task: dict = None,
        commit_file: bool = False,
        base_folder: str = "",
        current_filename: str = None
    ) -> Tuple[int, List[str]]:
        """
        Write out parsed files, returning (count_written, [compare_strings]).
        Each compare string now includes original_tokens, new_tokens, abs_delta, percent_delta.
        """
        logger.info("_write_parsed_files base_folder=%s commit_file=%s",
                    base_folder, commit_file, extra={'log_color': 'HIGHLIGHT'})
        
        # Confirmation dialog for commits
        if commit_file and CommitConfirmation and task:
            file_list = [p.get('filename', 'unknown') for p in parsed_files]
            if not CommitConfirmation.confirm(task, file_list):
                logger.info("Commit cancelled by user", extra={'log_color': 'DELTA'})
                return 0, []
        
        result = 0
        compare: List[str] = []
        # Use base_folder from function argument if provided, otherwise derive from task file
        effective_base_folder = base_folder if base_folder else (str(Path(task['file']).parent) if task and task.get('file') else ".")
        basedir = Path(effective_base_folder)

        # Determine diff service for applying unified diffs
        diff_srv = None
        if getattr(self, '_task_parser', None):
            diff_srv = getattr(self._task_parser, 'diff_service', None)
        if not diff_srv and self._svc and hasattr(self._svc, 'parse_service'):
            diff_srv = getattr(self._svc.parse_service, 'diff_service', None)

        for parsed in parsed_files:
            try:
                # Use the ensured keys from _ensure_parsed_entry
                rel       = parsed.get('relative_path', parsed.get('filename', '')) or parsed.get('filename')
                matched   = parsed.get('matchedfilename', '')
                original  = parsed.get('originalfilename', '')
                is_new    = parsed.get('new', False)
                is_del    = parsed.get('delete', False)
                is_copy   = parsed.get('copy', False)
                is_update = parsed.get('update', False) and not is_new

                # Ensure rel is a string, fallback to filename if empty
                rel = str(rel) if rel else parsed.get('filename')
                if not rel:
                    logger.warning(f"Skipping parsed file entry due to missing filename/relative_path: {parsed}", extra={'log_color': 'DELTA'})
                    continue

                # Original/New token counts
                orig_text_content = parsed.get('original_content', '') or ''
                orig_tok = parsed.get('original_tokens', len(orig_text_content.split()))
                
                body_raw = parsed.get('content', '')
                # If 'content' is a diff, extract the actual file content for token counting
                if diff_srv and diff_srv.is_unified_diff(body_raw):
                    # Try to apply diff to original content to get the new content for token count (for comparison purposes)
                    try:
                        temp_orig_lines = orig_text_content.splitlines()
                        applied_diff_content = diff_srv.apply_unified_diff(body_raw, orig_text_content)
                        new_tok = len(applied_diff_content.split())
                    except Exception:
                        # Fallback if diff application fails
                        new_tok = len(body_raw.split()) # Count tokens from diff body itself, which is inaccurate for content
                else:
                    # Regular file content
                    new_tok = parsed.get('new_tokens', len(body_raw.split()))

                abs_delta = new_tok - orig_tok
                pct = (abs_delta / orig_tok * 100.0) if orig_tok else (100.0 if new_tok else 0.0)

                tag = 'NEW' if is_new else 'DELETE' if is_del else 'COPY' if is_copy else 'UPDATE'

                # Determine the target path
                dest_path_str = matched or original or rel
                dest_path = basedir / dest_path_str

                if commit_file:
                    # DELETE
                    if is_del:
                        if dest_path.exists():
                            self._file_service.delete_file(dest_path)
                            result += 1
                        compare.append(f"{tag} {rel} (O:{orig_tok} N:{new_tok} Δ:{abs_delta} Δ%:{pct:.1f}%)")
                        continue

                    # COPY
                    if is_copy:
                        src_path = Path(parsed.get('source_path', '')) # Assuming 'source_path' might be provided for copy actions
                        if not src_path.is_absolute() and base_folder:
                             src_path = Path(base_folder) / src_path 
                        if src_path.exists():
                            self._file_service.copy_file(src_path, dest_path)
                            result += 1
                        compare.append(f"{tag} {rel} (O:{orig_tok} N:{new_tok} Δ:{abs_delta} Δ%:{pct:.1f}%)")
                        continue

                    # NEW
                    if is_new:
                        content_to_write = body_raw
                        self._file_service.write_file(dest_path, content_to_write)
                        result += 1
                        compare.append(f"{tag} {rel} (O:{orig_tok} N:{new_tok} Δ:{abs_delta} Δ%:{pct:.1f}%)")
                        continue

                    # UPDATE
                    if commit_file:
                        content_to_write = body_raw
                        orig_content_for_merge = self._file_service.safe_read_file(dest_path)
                        
                        # If detected as unified diff, apply it
                        if diff_srv and diff_srv.is_unified_diff(content_to_write):
                            try:
                                content_to_write = diff_srv.apply_unified_diff(content_to_write, orig_content_for_merge)
                                logger.info(f"Applied unified diff for {rel}", extra={'log_color': 'HIGHLIGHT'})
                            except Exception as e:
                                logger.warning(f"Failed to apply unified diff for {rel}: {e}", extra={'log_color': 'DELTA'})
                                # Keep original content_to_write if diff application fails
                        # Try precise smart merge for partial content (non-diff updates)
                        elif self._smart_merge and orig_content_for_merge:
                            try:
                                merged_content, success, message = self._smart_merge.apply_partial_content(
                                    orig_content_for_merge,
                                    content_to_write,
                                    context_lines=5  # More context for precise matching
                                )
                                if success:
                                    logger.info(f"✓ Smart merge for {rel}: {message}", extra={'log_color': 'HIGHLIGHT'})
                                    content_to_write = merged_content
                                else:
                                    logger.warning(f"Smart merge fallback for {rel}: {message}", extra={'log_color': 'DELTA'})
                                    # content_to_write remains as-is (full replacement)
                            except Exception as e:
                                logger.warning(f"Smart merge error for {rel}: {e}, using full replacement", extra={'log_color': 'DELTA'})
                        
                        self._file_service.write_file(dest_path, content_to_write)
                        result += 1
                        compare.append(f"{tag} {rel} (O:{orig_tok} N:{new_tok} Δ:{abs_delta} Δ%:{pct:.1f}%)")
                        continue

                # Non-committing run: just record what *would* happen
                compare.append(f"{tag} {rel} (O:{orig_tok} N:{new_tok} Δ:{abs_delta} Δ%:{pct:.1f}%)")

            except Exception as e:
                logger.exception(f"Error in _write_parsed_files for {parsed.get('filename')}: {e}", extra={'log_color': 'DELTA'})
                # Add an error entry to compare if commit is true
                if commit_file:
                    rel = parsed.get('relative_path', parsed.get('filename', ''))
                    compare.append(f"ERROR {rel} - {e}")
                continue

        logger.info("Parsed files processed: %d written successfully", result, extra={'log_color': 'PERCENT'})
        return result, compare

    def _write_planb(self, svc, plan_path: Path, content: str):
        if not plan_path:
            return
        try:
            self._file_service.write_file(plan_path, content)
            logger.info(f"Wrote plan to: {plan_path}", extra={'log_color': 'HIGHLIGHT'})
        except Exception as e:
            logger.exception(f"Failed to backup and write plan to {plan_path}: {e}", extra={'log_color': 'DELTA'})
            traceback.print_exc()

    def _backup_and_write_output(self, svc, out_path: Path, content: str):
        if not out_path:
            return
        try:
            self._file_service.write_file(out_path, content)
            logger.info(f"Backed up and wrote output to: {out_path}", extra={'log_color': 'HIGHLIGHT'})
        except Exception as e:
            logger.exception(f"Failed to backup and write output to {out_path}: {e}", extra={'log_color': 'DELTA'})
            traceback.print_exc()

    def _write_full_ai_output(self, svc, task, ai_out, trunc_code, base_folder: str = ""):
        try:
            out_path = self._get_ai_out_path(task, base_folder=base_folder)
            logger.info(f"Write AI out: {out_path} ({len(ai_out.split())} tokens)", extra={'log_color': 'HIGHLIGHT'})
            if out_path:
                self._backup_and_write_output(svc, out_path, ai_out)
        except Exception as e:
            logger.exception(f"Error writing full AI output: {e}", extra={'log_color': 'DELTA'})
            traceback.print_exc()

    def _get_ai_out_path(self, task, base_folder: str = ""):
        raw_out = task.get('out')
        out_path: Optional[Path] = None

        if isinstance(raw_out, str) and raw_out.strip():
            candidate = Path(raw_out)
            if not candidate.is_absolute() and base_folder:
                candidate = Path(base_folder) / candidate
            out_path = candidate
        elif isinstance(raw_out, dict):
            pattern = raw_out.get('pattern', "")
            try:
                candidate = self._file_service.resolve_path(pattern, self._svc)
            except Exception:
                candidate = None
            if candidate:
                out_path = Path(candidate)
            elif base_folder and pattern:
                out_path = Path(base_folder) / pattern

        # Ensure the directory exists
        if out_path:
            try:
                out_path.parent.mkdir(parents=True, exist_ok=True)
            except Exception:
                pass # Ignore if unable to create directory, file write will fail later if needed

        return out_path

    def _get_plan_out_pathe(self, raw_spec: Any, base_folder: str = "") -> Optional[Path]:
        """
        Resolve the plan.md output path from the task’s plan_spec.
        raw_spec is expected to be a dict like {'plan': {'pattern': 'plan.md', 'recursive': True}}
        """
        out_path: Optional[Path] = None
        plan_spec = None

        # unpack raw_spec
        if isinstance(raw_spec, dict) and 'plan' in raw_spec:
            plan_spec = raw_spec['plan']
        else:
            plan_spec = raw_spec

        # If spec is a simple string use it as filename
        if isinstance(plan_spec, str) and plan_spec.strip():
            candidate = Path(plan_spec)
            if not candidate.is_absolute() and base_folder:
                candidate = Path(base_folder) / candidate
            out_path = candidate

        # If spec is a dict, look for pattern and recursive
        elif isinstance(plan_spec, dict):
            pattern = plan_spec.get('pattern', '').strip()
            recursive = bool(plan_spec.get('recursive', False))
            # try to resolve existing file
            if pattern:
                try:
                    resolved = self._file_service.resolve_path(pattern, self._svc)
                except Exception:
                    resolved = None
                if resolved:
                    out_path = Path(resolved)
                else:
                    # fallback to creating under base_folder
                    if base_folder:
                        out_path = Path(base_folder) / pattern
                    else:
                        out_path = Path(pattern)

        # ensure we have a Path
        if out_path:
            # make parent dir if needed
            try:
                out_path.parent.mkdir(parents=True, exist_ok=True)
            except Exception:
                pass
        return out_path
    
    def _get_plan_out_pathd(self, raw_spec: Any, base_folder: str = "") -> Optional[Path]:
        out_path: Optional[Path] = None
        # … your existing implementation …
        return out_path

    def _get_plan_out_pathc(self, raw_spec: Any, base_folder: str = "") -> Optional[Path]:
        out_path: Optional[Path] = None
        # … your existing implementation …
        return out_path