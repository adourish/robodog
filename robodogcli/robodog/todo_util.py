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

    def _get_plan_out_path(self, raw_spec: Any, base_folder: str = "") -> Optional[Path]:
        """
        Resolve the plan.md output path from the task’s plan_spec.
        raw_spec may be {'plan': {...}} or a direct spec dict/string.
        Always returns a Path under the task’s folder.
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

    # Replace the existing _write_plan with this version:
    def _write_planf(self, svc, plan_path: Path, content: str) -> int:
        """
        Write the plan.md to disk, returning the token count of the content.
        """
        if not plan_path:
            return 0
        try:
            # write the file
            self._file_service.write_file(plan_path, content)
            # count tokens (simple whitespace split)
            tok = len(content.split())
            logger.info(f"Wrote plan to: {plan_path} ({tok} tokens)", extra={'log_color': 'PERCENT'})
            return tok
        except Exception as e:
            logger.exception(f"Failed to write plan to {plan_path}: {e}", extra={'log_color': 'DELTA'})
            return 0
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
                metadata.update({
                    '_raw_desc': main_desc,
                    'desc': main_desc,
                    'plan_desc': main_desc,
                    'llm_desc': main_desc,
                    'commit_desc': main_desc,
                })

                for part in parts[1:]:
                    if ':' not in part:
                        continue
                    key, val = [s.strip() for s in part.split(':', 1)]
                    lv = val.lower()
                    if key == 'started':
                        metadata['_start_stamp'] = None if lv == 'none' else val
                    elif key == 'completed':
                        metadata['_complete_stamp'] = None if lv == 'none' else val
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

            logger.debug(f"Final parsed metadata: {metadata}")
            return metadata

        except Exception as e:
            logger.exception(f"Error parsing task metadata for '{full_desc}': {e}", extra={'log_color': 'DELTA'})
            clean = full_desc.rstrip().strip()
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
        basedir = Path(task['file']).parent if task and task.get('file') else Path.cwd()
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

                # original/new token counts
                orig_tok = parsed.get('original_tokens')
                new_tok  = parsed.get('new_tokens')
                if orig_tok is None or new_tok is None:
                    orig_text = parsed.get('original_content', '') or ''
                    orig_tok = len(orig_text.split())
                    body_raw = parsed.get('content', '').partition('\n')[2]
                    new_tok = len(body_raw.split())

                abs_delta = new_tok - orig_tok
                pct = (abs_delta / orig_tok * 100.0) if orig_tok else (100.0 if new_tok else 0.0)

                tag = 'NEW' if is_new else 'DELETE' if is_del else 'COPY' if is_copy else 'UPDATE'

                if commit_file:
                    # DELETE
                    if is_del:
                        p = Path(matched or (basedir / rel))
                        if p.exists():
                            self._file_service.delete_file(p)
                            result += 1
                        compare.append(f"{tag} {rel} (O:{orig_tok} N:{new_tok} Δ:{abs_delta} Δ%:{pct:.1f}%)")
                        continue

                    # COPY
                    if is_copy:
                        src = Path(matched)
                        dst = basedir / rel
                        self._file_service.copy_file(src, dst)
                        result += 1
                        compare.append(f"{tag} {rel} (O:{orig_tok} N:{new_tok} Δ:{abs_delta} Δ%:{pct:.1f}%)")
                        continue

                    # NEW
                    if is_new:
                        dst = basedir / rel
                        body = parsed.get('content', '').partition('\n')[2]
                        self._file_service.write_file(dst, body)
                        result += 1
                        compare.append(f"{tag} {rel} (O:{orig_tok} N:{new_tok} Δ:{abs_delta} Δ%:{pct:.1f}%)")
                        continue

                    # UPDATE
                    if is_update:
                        dst = Path(matched) if Path(matched).exists() else (basedir / rel)
                        body = parsed.get('content', '').partition('\n')[2]
                        # if diff, apply it
                        if diff_srv and diff_srv.is_unified_diff(body):
                            orig = self._file_service.safe_read_file(dst)
                            try:
                                body = diff_srv.apply_unified_diff(body, orig)
                            except Exception:
                                pass
                        self._file_service.write_file(dst, body)
                        result += 1
                        compare.append(f"{tag} {rel} (O:{orig_tok} N:{new_tok} Δ:{abs_delta} Δ%:{pct:.1f}%)")
                        continue

                # non‐committing run: just record what *would* happen
                compare.append(f"{tag} {rel} (O:{orig_tok} N:{new_tok} Δ:{abs_delta} Δ%:{pct:.1f}%)")

            except Exception:
                logger.exception(f"Error in _write_parsed_files for {parsed.get('filename')}")
                continue

        logger.info("Parsed files written: %d", result, extra={'log_color': 'PERCENT'})
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
                out_path = candidate
            elif base_folder and pattern:
                out_path = Path(base_folder) / pattern

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