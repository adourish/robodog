# file: todo_util.py
#!/usr/bin/env python3
"""Utility functions for TodoService, including metadata parsing and desc sanitization."""
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

import tiktoken
from pydantic import BaseModel, RootModel
import yaml  # ensure PyYAML is installed

logger = logging.getLogger(__name__)
try:
    from .parse_service import ParseService
except ImportError:
    from parse_service import ParseService
try:
    from .file_service import FileService
except ImportError:
    from file_service import FileService


class TodoUtilService:
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
        app=None
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
        except Exception as e:
            logger.exception(f"Error during initialization of TodoUtilService: {e}", extra={'log_color': 'DELTA'})
            raise


    def _parse_task_metadata(self, full_desc: str) -> Dict:
        """
        Parse the task description for metadata (started/completed tokens, etc.).
        Preserve the original unmodified description in `_raw_desc`.
        """
        logger.debug(f"Parsing metadata for task desc: {full_desc}")
        try:
            raw_desc = full_desc.rstrip()
            sanitized_desc = raw_desc
            metadata = {
                '_raw_desc': raw_desc,
                'desc': sanitized_desc,
                'plan_desc': sanitized_desc,
                'llm_desc': sanitized_desc,
                'commit_desc': sanitized_desc,
                '_start_stamp': None,
                '_complete_stamp': None,
                'knowledge_tokens': 0,
                'include_tokens': 0,
                'prompt_tokens': 0,
                'plan_tokens': 0,
            }

            parts = [p.strip() for p in raw_desc.split('|') if p.strip()]
            if len(parts) > 1:
                main_desc = parts[0]
                metadata['_raw_desc'] = parts[0]
                metadata['desc'] = main_desc
                metadata['plan_desc'] = main_desc
                metadata['llm_desc'] = main_desc
                metadata['commit_desc'] = main_desc

                for part in parts[1:]:
                    if ':' not in part:
                        continue
                    key, val = [s.strip() for s in part.split(':', 1)]
                    lowered_val = val.lower()
                    if key == 'started':
                        metadata['_start_stamp'] = None if lowered_val == 'none' else val
                    elif key == 'completed':
                        metadata['_complete_stamp'] = None if lowered_val == 'none' else val
                    elif key == 'knowledge' and val.isdigit():
                        metadata['knowledge_tokens'] = int(val)
                    elif key == 'include' and val.isdigit():
                        metadata['include_tokens'] = int(val)
                    elif key == 'prompt' and val.isdigit():
                        metadata['prompt_tokens'] = int(val)
                    elif key == 'plan':
                        if val.isdigit():
                            metadata['plan_tokens'] = int(val)
                        else:
                            metadata['plan_desc'] = val
                    elif key in ('plan_desc', 'llm_desc', 'commit_desc'):
                        metadata[key] = val

            metadata['desc'] = metadata['desc']
            metadata['plan_desc'] = metadata['plan_desc']
            metadata['llm_desc'] = metadata['llm_desc']
            metadata['commit_desc'] = metadata['commit_desc']
            logger.debug(f"Final parsed metadata: {metadata}")
            return metadata
        except Exception as e:
            logger.exception(f"Error parsing task metadata for '{full_desc}': {e}", extra={'log_color': 'DELTA'})
            raw_desc = full_desc.rstrip()
            clean = raw_desc.strip()
            return {
                '_raw_desc': raw_desc,
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
        result = 0
        compare: List[str] = []
        basedir = Path(task['file']).parent if task else Path.cwd()
        self._file_service.base_dir = str(basedir)
        diff_srv = getattr(self._svc.parse_service, 'diff_service', None) if self._svc else None

        for parsed in parsed_files:
            try:
                rel       = parsed.get('relative_path', parsed.get('filename', ''))
                matched   = parsed.get('matchedfilename', '')
                is_new    = parsed.get('new', False)
                is_del    = parsed.get('delete', False)
                is_copy   = parsed.get('copy', False)
                is_update = parsed.get('update', False) and not is_new

                # ensure token stats
                orig_tok = parsed.get('original_tokens', None)
                new_tok  = parsed.get('new_tokens', None)
                if orig_tok is None or new_tok is None:
                    # compute from content
                    orig_text = parsed.get('original_content', '')
                    orig_tok = len(orig_text.split()) if orig_text else 0
                    body = parsed.get('content', '').partition('\n')[2]
                    new_tok = len(body.split())
                abs_delta = new_tok - orig_tok
                if orig_tok > 0:
                    pct = abs_delta / orig_tok * 100.0
                else:
                    pct = 100.0 if new_tok > 0 else 0.0

                tag = 'NEW' if is_new else 'DELETE' if is_del else 'COPY' if is_copy else 'UPDATE'

                # perform file operations if committing
                if commit_file:
                    # deletion
                    if is_del:
                        p = Path(matched)
                        if p.exists():
                            self._file_service.delete_file(p)
                            result += 1
                        # record compare
                        compare.append(f"{tag} {rel} (O:{orig_tok} N:{new_tok} Δ:{abs_delta} Δ%:{pct:.1f}%)")
                        continue

                    # copy
                    if is_copy:
                        src = Path(matched)
                        dst = basedir / rel
                        self._file_service.copy_file(src, dst)
                        result += 1
                        compare.append(f"{tag} {rel} (O:{orig_tok} N:{new_tok} Δ:{abs_delta} Δ%:{pct:.1f}%)")
                        continue

                    # new file
                    if is_new:
                        dst = basedir / rel
                        self._file_service.write_file(dst, parsed.get('content', '').partition('\n')[2])
                        result += 1
                        compare.append(f"{tag} {rel} (O:{orig_tok} N:{new_tok} Δ:{abs_delta} Δ%:{pct:.1f}%)")
                        continue

                    # update
                    if is_update:
                        dst = Path(matched) if Path(matched).exists() else basedir / rel
                        body = parsed.get('content', '').partition('\n')[2]
                        # reapply diff if needed
                        if diff_srv and diff_srv.is_unified_diff(body):
                            orig = self._file_service.safe_read_file(Path(matched))
                            try:
                                patched = diff_srv.apply_unified_diff(body, orig)
                                body = patched
                            except Exception:
                                pass
                        self._file_service.write_file(dst, body)
                        result += 1
                        compare.append(f"{tag} {rel} (O:{orig_tok} N:{new_tok} Δ:{abs_delta} Δ%:{pct:.1f}%)")
                        continue

                # non-commit: just record comparison
                compare.append(f"{tag} {rel} (O:{orig_tok} N:{new_tok} Δ:{abs_delta} Δ%:{pct:.1f}%)")

            except Exception:
                logger.exception(f"Error in _write_parsed_files for {parsed.get('filename')}")
                continue

        logger.info("Parsed files written: %d", result, extra={'log_color': 'PERCENT'})
        return result, compare

    def _write_parsed_filesc(
        self,
        parsed_files: List[dict],
        task: dict = None,
        commit_file: bool = False,
        base_folder: str = "",
        current_filename: str = None
    ) -> Tuple[int, List[str]]:
        """
        Write out parsed files.  In commit_file=True mode, any unified diffs
        in obj['content'] are applied to the on‐disk file before writing.
        Returns (count_written, [compare_strings]).
        """
        logger.info("_write_parsed_files base_folder=%s commit_file=%s",
                    base_folder, commit_file, extra={'log_color': 'HIGHLIGHT'})
        result = 0
        compare: List[str] = []
        basedir = Path(task['file']).parent if task else Path.cwd()
        self._file_service.base_dir = str(basedir)
        diff_srv = getattr(self._svc.parse_service, 'diff_service', None) if self._svc else None

        for parsed in parsed_files:
            try:
                fn       = parsed['filename']
                rel      = parsed['relative_path']
                match    = parsed['matchedfilename']
                is_new   = parsed.get('new', False)
                is_del   = parsed.get('delete', False)
                is_copy  = parsed.get('copy', False)
                is_upd   = parsed.get('update', False) and not is_new
                content  = parsed.get('content', '')
                # strip directive
                header, _, body = content.partition('\n')

                # In commit mode, re-apply diff if detected
                if commit_file and is_upd and diff_srv and diff_srv.is_unified_diff(body):
                    original = ""
                    orig_path = Path(match) if match else None
                    if orig_path and orig_path.exists():
                        original = self._file_service.safe_read_file(orig_path)
                    try:
                        patched = diff_srv.apply_unified_diff(body, original)
                        body = patched
                        parsed['is_diff_applied'] = True
                        logger.info(f"Using patched diff for {fn}", extra={'log_color': 'HIGHLIGHT'})
                    except Exception as e:
                        logger.error(f"Diff apply failed for {fn}: {e}", extra={'log_color': 'DELTA'})
                        compare.append(f"DIFF_ERROR {fn}")
                        continue

                # perform the actual file op
                if commit_file:
                    if is_del:
                        p = Path(match)
                        if p.exists():
                            self._file_service.delete_file(p)
                            result += 1
                        compare.append(f"DELETE {rel}")
                        continue

                    if is_copy:
                        src = Path(match)
                        dst = basedir / rel
                        self._file_service.copy_file(src, dst)
                        result += 1
                        compare.append(f"COPY {rel}")
                        continue

                    if is_new:
                        dst = basedir / rel
                        self._file_service.write_file(dst, body)
                        result += 1
                        compare.append(f"NEW {rel}")
                        continue

                    if is_upd:
                        dst = Path(match)
                        if dst.exists():
                            self._file_service.write_file(dst, body)
                        else:
                            # fallback create
                            dst = basedir / rel
                            self._file_service.write_file(dst, body)
                        result += 1
                        tag = "UPDATE(diff)" if parsed.get('is_diff_applied') else "UPDATE"
                        compare.append(f"{tag} {rel}")
                        continue

                # non‐commit mode: we don’t touch disk, just collect compare
                tag = "NEW" if is_new else "DELETE" if is_del else "COPY" if is_copy else "UPDATE"
                compare.append(f"{tag} {rel}")

            except Exception:
                logger.exception(f"Error in _write_parsed_files for {parsed.get('filename')}")
                continue

        return result, compare
    
    def _write_parsed_filesb(
        self,
        parsed_files: List[dict],
        task: dict = None,
        commit_file: bool = False,
        base_folder: str = "",
        current_filename: str = None
    ) -> Tuple[int, List[str]]:
        """
        Write parsed files and compare tokens for NEW/UPDATE/DELETE/COPY.
        """
        logger.info("_write_parsed_files base folder: " + str(base_folder), extra={'log_color': 'HIGHLIGHT'})
        try:
            result = 0
            compare: List[str] = []
            basedir = Path(task['file']).parent if task else Path.cwd()
            self._file_service.base_dir = str(basedir)
            update_deltas: List[float] = []
            update_abs_deltas: List[int] = []
            plan_files_written = 0

            diff_service = None
            if self._svc and getattr(self._svc, 'parse_service', None):
                diff_service = getattr(self._svc.parse_service, 'diff_service', None)

            def _extract_unified_diff_payload(raw_body: str) -> str:
                if not raw_body:
                    return ""
                text = raw_body
                stripped = raw_body.lstrip()
                if stripped.startswith("```"):
                    first_line_end = stripped.find('\n')
                    if first_line_end != -1:
                        header = stripped[3:first_line_end].strip().lower()
                        remainder = stripped[first_line_end + 1:]
                        if not header or header.startswith("diff"):
                            remainder_lines = remainder.splitlines()
                            if remainder_lines and remainder_lines[-1].strip() == "```":
                                remainder_lines = remainder_lines[:-1]
                            text = "\n".join(remainder_lines)
                text = text.lstrip('\n')
                if text and not text.endswith('\n'):
                    text += '\n'
                return text

            for parsed in parsed_files:
                try:
                    filename = parsed.get('filename', '')
                    if current_filename is not None and filename != current_filename:
                        continue

                    content = parsed.get('content', '')
                    originalfilename = parsed.get('originalfilename', filename)
                    matchedfilename = parsed.get('matchedfilename', filename)
                    relative_path = parsed.get('relative_path', filename)
                    is_new = parsed.get('new', False)
                    is_delete = parsed.get('delete', False)
                    is_copy = parsed.get('copy', False)
                    is_update = parsed.get('update', False) or (not is_new and not is_copy and not is_delete)

                    if filename == 'plan.md':
                        plan_files_written += 1
                        logger.info(
                            f"Writing plan file: {relative_path} (new: {is_new}, update: {is_update})",
                            extra={'log_color': 'HIGHLIGHT'}
                        )

                    directive_line = ''
                    body = content
                    if content:
                        first_line, _, remainder = content.partition('\n')
                        if 'file:' in first_line:
                            directive_line = first_line
                            body = remainder

                    original_content = parsed.get('original_content')
                    if not original_content and matchedfilename:
                        original_path = Path(matchedfilename)
                        if original_path.exists():
                            original_content = self._file_service.safe_read_file(original_path)
                            parsed['original_content'] = original_content

                    diff_detected = False
                    diff_applied = False
                    diff_payload = ""

                    if diff_service and not is_new and not is_copy and not is_delete:
                        diff_payload = _extract_unified_diff_payload(body)
                        if diff_payload and diff_service.is_unified_diff(diff_payload):
                            diff_detected = True
                            if original_content:
                                try:
                                    patched_text = diff_service.apply_unified_diff(diff_payload, original_content)
                                    content = patched_text
                                    parsed['content'] = content
                                    diff_applied = True
                                    logger.info(
                                        f"Applied unified diff for {matchedfilename or filename}",
                                        extra={'log_color': 'HIGHLIGHT'}
                                    )
                                except Exception as patch_exc:
                                    logger.warning(
                                        f"Failed to apply unified diff for {matchedfilename or filename}: {patch_exc}",
                                        extra={'log_color': 'DELTA'}
                                    )
                            else:
                                logger.warning(
                                    f"Unified diff detected for {matchedfilename or filename} but no original content available.",
                                    extra={'log_color': 'DELTA'}
                                )

                    if diff_detected and not diff_applied:
                        compare.append(f"DIFF_FAILED {matchedfilename or filename}")
                        if commit_file:
                            logger.warning(
                                f"Skipping write for {matchedfilename or filename} due to diff apply failure.",
                                extra={'log_color': 'DELTA'}
                            )
                        continue

                    orig_tokens = parsed.get('original_tokens', 0)
                    if orig_tokens == 0 and original_content:
                        orig_tokens = len(original_content.split())
                        parsed['original_tokens'] = orig_tokens

                    new_tokens = len(content.split()) if content else 0
                    abs_delta = new_tokens - orig_tokens
                    if orig_tokens:
                        token_delta = ((new_tokens - orig_tokens) / orig_tokens) * 100.0
                    else:
                        token_delta = 100.0 if new_tokens else 0.0

                    parsed['content'] = content
                    parsed['new_tokens'] = new_tokens
                    parsed['abs_delta_tokens'] = abs_delta
                    parsed['percent_delta'] = token_delta
                    parsed['short_compare'] = f"O:{orig_tokens} N:{new_tokens} D:{abs_delta}"

                    action = 'NEW' if is_new else 'DELETE' if is_delete else 'COPY' if is_copy else 'UPDATE'
                    clean_relative = relative_path
                    clean_task_desc = task.get('desc', '') if task else ''
                    plan_tokens = task.get('plan_tokens', 0) if task else 0
                    knowledge_tokens = task.get('knowledge_tokens', 0) if task else 0
                    include_tokens = task.get('include_tokens', 0) if task else 0
                    prompt_tokens = task.get('prompt_tokens', 0) if task else 0
                    logger.info(
                        f"Write {action} {clean_relative}: "
                        f"(plan/k/i/p/o/u/d/p {plan_tokens}/{knowledge_tokens}/{include_tokens}/{prompt_tokens}/"
                        f"{orig_tokens}/{new_tokens}/{abs_delta}/{token_delta:.1f}%) "
                        f"commit:{commit_file} task_desc:{clean_task_desc[:50]}",
                        extra={'log_color': 'PERCENT'}
                    )
                    logger.debug(f"  - originalfilename: {originalfilename}")
                    logger.debug(f"  - matchedfilename: {matchedfilename}")
                    logger.debug(f"  - relative_path: {relative_path}")

                    if commit_file:
                        if is_delete:
                            delete_path = Path(matchedfilename) if matchedfilename else None
                            if delete_path and delete_path.exists():
                                self._file_service.delete_file(delete_path)
                                logger.info(f"Deleted file: {delete_path} (matched: {matchedfilename})", extra={'log_color': 'DELTA'})
                                result += 1
                            elif not delete_path:
                                logger.warning(f"No matched path for DELETE: {filename}", extra={'log_color': 'DELTA'})
                            else:
                                logger.info(f"DELETE file not found: {delete_path}", extra={'log_color': 'DELTA'})
                            compare.append(f"{parsed.get('short_compare', '')} (DELETE) -> {matchedfilename}")
                            continue
                        if is_copy:
                            src_path = Path(matchedfilename)
                            dst_path = self._file_service.resolve_path(relative_path, self._svc)
                            if src_path.exists():
                                self._file_service.copy_file(src_path, dst_path)
                                logger.info(f"Copied file: {src_path} -> {dst_path} (relative: {relative_path})", extra={'log_color': 'HIGHLIGHT'})
                                result += 1
                            else:
                                logger.warning(f"Source for COPY not found: {src_path}", extra={'log_color': 'DELTA'})
                        elif is_new:
                            new_path = basedir / relative_path
                            self._file_service.write_file(new_path, content)
                            logger.info(f"Created NEW file at: {new_path} (relative: {relative_path})", extra={'log_color': 'HIGHLIGHT'})
                            result += 1
                        elif is_update:
                            new_path = Path(matchedfilename)
                            if new_path.exists():
                                self._file_service.write_file(new_path, content)
                                logger.info(f"Updated file: {new_path} (matched: {matchedfilename})", extra={'log_color': 'HIGHLIGHT'})
                                update_deltas.append(token_delta)
                                update_abs_deltas.append(abs_delta)
                                logger.info(
                                    f"Updated for {filename} {clean_relative}: "
                                    f"(plan/k/i/p/o/u/d/p {plan_tokens}/{knowledge_tokens}/{include_tokens}/{prompt_tokens}/"
                                    f"{orig_tokens}/{new_tokens}/{abs_delta}/{token_delta:.1f}%) "
                                    f"task_desc:{clean_task_desc[:50]}",
                                    extra={'log_color': 'PERCENT'}
                                )
                                result += 1
                            else:
                                logger.warning(f"Path for UPDATE not found: {new_path}", extra={'log_color': 'DELTA'})
                                new_path = basedir / relative_path
                                self._file_service.write_file(new_path, content)
                                logger.info(f"Created NEW file at: {new_path} (relative: {relative_path})", extra={'log_color': 'HIGHLIGHT'})
                                result += 1
                        else:
                            logger.warning(
                                f"Unknown action for {filename}: new={is_new}, update={is_update}, delete={is_delete}, copy={is_copy}",
                                extra={'log_color': 'DELTA'}
                            )

                    if is_delete:
                        compare.append(f"DELETE {matchedfilename} {parsed.get('short_compare', '')}")
                    elif is_copy:
                        compare.append(f"COPY {matchedfilename} {parsed.get('short_compare', '')}")
                    elif is_new:
                        compare.append(f"NEW {matchedfilename} {parsed.get('short_compare', '')}")
                    elif is_update:
                        compare_label = "UPDATE (diff)" if diff_applied else "UPDATE"
                        compare.append(f"{compare_label} {matchedfilename} {parsed.get('short_compare', '')}")
                    else:
                        compare.append(parsed.get('short_compare', ''))
                except Exception as inner_exc:
                    logger.exception(
                        f"Error processing parsed file {parsed.get('filename', 'unknown')}: {inner_exc}",
                        extra={'log_color': 'DELTA'}
                    )
                    traceback.print_exc()
                    continue

            if update_deltas:
                median_delta = statistics.median(update_deltas)
                avg_delta = statistics.mean(update_deltas)
                peak_delta = max(update_deltas)
                logger.info(
                    f"UPDATE summary: median {median_delta:.1f}%, avg {avg_delta:.1f}%, peak {peak_delta:.1f}% across {len(update_deltas)} files",
                    extra={'log_color': 'HIGHLIGHT'}
                )
            logger.info(f"Plan files written: {plan_files_written}", extra={'log_color': 'PERCENT'})
        except Exception as e:
            logger.exception(f"Error in _write_parsed_files: {e}", extra={'log_color': 'DELTA'})
            traceback.print_exc()

        return result, compare

    def _write_plan(self, svc, plan_path: Path, content: str):
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
            except Exception as e:
                logger.exception(f"Error resolving pattern {pattern}: {e}", extra={'log_color': 'DELTA'})
                candidate = None
            if candidate:
                out_path = candidate
            elif base_folder and pattern:
                out_path = Path(base_folder) / pattern

        return out_path

    def _get_plan_out_path(self, raw_spec: Any, base_folder: str = "") -> Optional[Path]:
        """
        Figure out where plan.md should live.
        Accepts either:
          - a dict { 'pattern': ..., 'recursive': ...}
          - a nested dict { 'plan': { 'pattern':..., 'recursive':...} }
          - a literal string path
        """
        out_path: Optional[Path] = None

        # Direct spec dict with pattern key
        if isinstance(raw_spec, dict) and 'pattern' in raw_spec:
            pattern = raw_spec.get('pattern') or ""
            if pattern:
                try:
                    candidate = self._file_service.resolve_path(pattern, self._svc)
                except Exception:
                    candidate = None
                if candidate:
                    out_path = candidate
                else:
                    out_path = Path(base_folder) / pattern if base_folder else Path(pattern)

        # Nested spec under 'plan' key
        elif isinstance(raw_spec, dict) and 'plan' in raw_spec:
            spec = raw_spec['plan']
            if isinstance(spec, dict) and spec.get('pattern'):
                pattern = spec['pattern']
                try:
                    candidate = self._file_service.resolve_path(pattern, self._svc)
                except Exception:
                    candidate = None
                if candidate:
                    out_path = candidate
                else:
                    out_path = Path(base_folder) / pattern if base_folder else Path(pattern)

        # Literal string path
        elif isinstance(raw_spec, str) and raw_spec.strip():
            candidate = Path(raw_spec.strip())
            if not candidate.is_absolute() and base_folder:
                candidate = Path(base_folder) / candidate
            out_path = candidate

        return Path(out_path) if out_path else None

    def _get_plan_out_pathc(self, raw_spec: Any, base_folder: str = "") -> Optional[Path]:
        """
        Figure out where plan.md should live.
        Accepts either:
          - a dict { 'plan': {'pattern': ..., 'recursive': ...} }
          - a literal string path
        """
        out_path: Optional[Path] = None

        if isinstance(raw_spec, dict) and 'plan' in raw_spec:
            spec = raw_spec['plan']
            if isinstance(spec, dict):
                pattern = spec.get('pattern', '')
                try:
                    candidate = self._file_service.resolve_path(pattern, self._svc)
                except Exception:
                    candidate = None
                if candidate:
                    out_path = candidate
                elif base_folder and pattern:
                    out_path = Path(base_folder) / pattern
        elif isinstance(raw_spec, str) and raw_spec.strip():
            candidate = Path(raw_spec.strip())
            if not candidate.is_absolute() and base_folder:
                candidate = Path(base_folder) / candidate
            out_path = candidate

        return Path(out_path) if out_path else None