# file: todo.py
#!/usr/bin/env python3
"""Todo task management and execution service."""
import os
import re
import time
import threading
import logging
import traceback
import shutil
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Dict
import statistics  # Added for calculating median, avg, peak

import tiktoken
from pydantic import BaseModel, RootModel
import yaml   # ensure PyYAML is installed
from typing import Any, Tuple
logger = logging.getLogger(__name__)
try:
    from .parse_service import ParseService
except ImportError:
    from parse_service import ParseService
class TodoUtilService:
    def __init__(self, roots: List[str], svc=None, prompt_builder=None, task_manager=None, task_parser=None, file_watcher=None, file_service=None, exclude_dirs={"node_modules", "dist", "diffout"}):
        logger.info(f"Initializing TodoService with roots: {roots}", extra={'log_color': 'HIGHLIGHT'})
        logger.debug(f"Svc provided: {svc is not None}, Prompt builder: {prompt_builder is not None}")
        try:
            self._roots        = roots
            self._file_lines   = {}
            self._tasks        = []
            self._mtimes       = {}
            self._watch_ignore = {}
            self._svc          = svc
            self._prompt_builder = prompt_builder
            self._task_manager = task_manager
            self._task_parser = task_parser
   
            self._file_watcher = file_watcher
            self._file_service = file_service
            self._exclude_dirs = exclude_dirs
            # MVP: parse a `base:` directive from front-matter


        except Exception as e:
            logger.exception(f"Error during initialization of TodoService: {e}", extra={'log_color': 'DELTA'})
            raise

    # --- modified write-and-report method ---
    def _write_parsed_files(self, parsed_files: List[dict], task: dict = None, commit_file: bool= False, base_folder: str = "", current_filename: str = None) -> tuple[int, List[str]]:
        """
        Write parsed files and compare tokens using parse_service object properties, return results and compare list
        For NEW files, resolve path relative to todo.md folder (base_dir) and create full path.
        For DELETE files, delete the matched file if it exists; prioritize DELETE over NEW even if both flags are set.
        matchedfilename remains relative for reporting.
        Enhanced logging for UPDATEs: full compare details with percentage deltas (median, avg, peak line/token changes).
        Added logging for planning step files. Now includes plan_tokens in token logging.
        Now sanitizes desc in logging to avoid flag contamination in logs.
        """
        logger.info("_write_parsed_files base folder: " + str(base_folder), extra={'log_color': 'HIGHLIGHT'})
        try:
            result = 0
            compare: List[str] = []
            basedir = Path(task['file']).parent if task else Path.cwd()
            self._file_service.base_dir = str(basedir)  # Set base_dir for relative path resolution
            update_deltas = []  # Collect deltas for UPDATE logging
            update_abs_deltas = []  # Collect absolute deltas for UPDATE logging
            plan_files_written = 0  # New counter for plan files

            for parsed in parsed_files:
                try:
                    filename = parsed.get('filename', '')
                    if current_filename == None or filename == current_filename:
                        content = parsed['content']
                        # completeness check
                        filename = parsed.get('filename', '')
                        originalfilename = parsed.get('originalfilename', filename)
                        matchedfilename = parsed.get('matchedfilename', filename)  # Relative path for NEW files
                        relative_path = parsed.get('relative_path', filename)
                        is_new = parsed.get('new', False)
                        is_delete = parsed.get('delete', False)
                        is_copy = parsed.get('copy', False)
                        is_update = parsed.get('update', False)
                        if filename == 'plan.md':  # Special handling for plan.md
                            plan_files_written += 1
                            logger.info(f"Writing plan file: {relative_path} (new: {is_new}, update: {is_update})", extra={'log_color': 'HIGHLIGHT'})
                        if not is_new and not is_copy and not is_delete and not is_update:
                            is_update = True
                        new_path = None
                        orig_content = parsed.get('original_content', '')  # Assume parsed has original for diff calc
                        orig_tokens = len(orig_content.split()) if orig_content else 0
                        new_tokens = len(content.split()) if content else 0
                        abs_delta = new_tokens - orig_tokens  # Absolute delta token count
                        token_delta = ((new_tokens - orig_tokens) / orig_tokens * 100) if orig_tokens > 0 else 100.0 if new_tokens > 0 else 0.0

                        # Determine action
                        action = 'NEW' if is_new else 'UPDATE' if is_update else 'DELETE' if is_delete else 'COPY' if is_copy else 'UNCHANGED'

                        # Per-file logging in the specified format (sanitize relative_path if needed). Enhanced: Include plan_tokens if available
                        clean_relative = self.sanitize_desc(relative_path)
                        plan_t = task.get('plan_tokens', 0) if task else 0
                        logger.info(f"Write {action} {clean_relative}: (plan/k/i/p/o/u/d/p {plan_t}/{task.get('knowledge_tokens',0)}/{task.get('include_tokens',0)}/{task.get('prompt_tokens',0)}/{orig_tokens}/{new_tokens}/{abs_delta}/{token_delta:.1f}%) commit:{str(commit_file)}", extra={'log_color': 'PERCENT'})

                        # Enhanced logging including originalfilename and matchedfilename
                        logger.debug(f"  - originalfilename: {originalfilename}")
                        logger.debug(f"  - matchedfilename: {matchedfilename}")
                        logger.debug(f"  - relative_path: {relative_path}")
                        # Prioritize DELETE: delete if flagged, regardless of other flags
                        if commit_file:
                            if is_delete:
                                logger.info(f"Delete file: {matchedfilename}", extra={'log_color': 'DELTA'})
                                delete_path = Path(matchedfilename) if matchedfilename else None
                                if commit_file and delete_path and delete_path.exists():
                                    self._file_service.delete_file(delete_path)
                                    logger.info(f"Deleted file: {delete_path} (matched: {matchedfilename})", extra={'log_color': 'DELTA'})
                                    result += 1
                                elif not delete_path:
                                    logger.warning(f"No matched path for DELETE: {filename}", extra={'log_color': 'DELTA'})
                                else:
                                    logger.info(f"DELETE file not found: {delete_path}", extra={'log_color': 'DELTA'})
                                compare.append(f"{parsed.get('short_compare', '')} (DELETE) -> {matchedfilename}")
                                continue  # No further action for deletes


                            if is_copy:
                                # For COPY: resolve source and destination, copy file
                                src_path = Path(matchedfilename)  # Assume matched is source
                                dst_path = self._file_service.resolve_path(relative_path, self._svc)  # Destination relative
                                if src_path.exists():
                                    self._file_service.copy_file(src_path, dst_path)
                                    logger.info(f"Copied file: {src_path} -> {dst_path} (relative: {relative_path})", extra={'log_color': 'HIGHLIGHT'})
                                    result += 1
                                else:
                                    logger.warning(f"Source for COPY not found: {src_path}", extra={'log_color': 'DELTA'})
                            elif is_new:
                                # For NEW, resolve relative to base_dir
                                # create the new file under the todo.md folder + relative_path
                                new_path = basedir / relative_path
                                self._file_service.write_file(new_path, content)
                                logger.info(f"Created NEW file at: {new_path} (relative: {relative_path})", extra={'log_color': 'HIGHLIGHT'})
                                result += 1
                                
                            elif is_update:
                                # For UPDATE, use matched path
                                new_path = Path(matchedfilename)
                                if new_path.exists():
                                    self._file_service.write_file(new_path, content)
                                    logger.info(f"Updated file: {new_path} (matched: {matchedfilename})", extra={'log_color': 'HIGHLIGHT'})
                                    # Enhanced UPDATE logging: calculate and log deltas
                                    update_deltas.append(token_delta)
                                    update_abs_deltas.append(abs_delta)
                                    clean_rel = self.sanitize_desc(relative_path)
                                    plan_t = task.get('plan_tokens', 0) if task else 0
                                    logger.info(f"Updated for {filename} {clean_rel}: (plan/k/i/p/o/u/d/p {plan_t}/{task.get('knowledge_tokens',0)}/{task.get('include_tokens',0)}/{task.get('prompt_tokens',0)}/{orig_tokens}/{new_tokens}/{abs_delta}/{token_delta:.1f}%)", extra={'log_color': 'PERCENT'})
                                    result += 1
                                else:
                                    logger.warning(f"Path for UPDATE not found: {new_path}", extra={'log_color': 'DELTA'})
                                    new_path = basedir / relative_path
                                    self._file_service.write_file(new_path, content)
                                    logger.info(f"Created NEW file at: {new_path} (relative: {relative_path})", extra={'log_color': 'HIGHLIGHT'})
                                    result += 1
                            else:
                                logger.warning(f"Unknown action for {filename}: new={is_new}, update={is_update}, delete={is_delete}, copy={is_copy}", extra={'log_color': 'DELTA'})

                        short_compare = parsed.get('short_compare', '')
                        if is_delete:
                            compare.append(f"DELETE {matchedfilename} {short_compare} ")
                        elif is_copy:
                            compare.append(f"COPY {matchedfilename} {short_compare}")
                        elif is_new:
                            compare.append(f"NEW {matchedfilename} {short_compare}")
                        elif is_update:
                            compare.append(f"UPDATE {matchedfilename} {short_compare} ")
                        else:
                            compare.append(short_compare)
                except Exception as e:
                    logger.exception(f"Error processing parsed file {parsed.get('filename', 'unknown')}: {e}", extra={'log_color': 'DELTA'})
                    traceback.print_exc()
                    continue
            # Enhanced UPDATE summary logging if any updates occurred
            if update_deltas:
                median_delta = statistics.median(update_deltas)
                avg_delta = statistics.mean(update_deltas)
                peak_delta = max(update_deltas)
                logger.info(f"UPDATE summary: median {median_delta:.1f}%, avg {avg_delta:.1f}%, peak {peak_delta:.1f}% across {len(update_deltas)} files", extra={'log_color': 'HIGHLIGHT'})
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
        
    def _write_full_ai_output(self, svc, task, ai_out, trunc_code, base_folder: str="" ):
        try:
            out_path = self._get_ai_out_path(task, base_folder=base_folder)
            logger.info(f"Write AI out: {out_path} ({len(ai_out.split())} tokens)", extra={'log_color': 'HIGHLIGHT'})
            if out_path:
                self._backup_and_write_output(svc, out_path, ai_out)
        except Exception as e:
            logger.exception(f"Error writing full AI output: {e}", extra={'log_color': 'DELTA'})
            traceback.print_exc()
    

    def _get_ai_out_path(self, task, base_folder: str = ""):
        # figure out where the AI output file actually lives
        raw_out = task.get('out')
        out_path = None

        # case 1: user supplied a literal string path
        if isinstance(raw_out, str) and raw_out.strip():
            p = Path(raw_out)
            if not p.is_absolute() and base_folder:
                p = base_folder / p
            out_path = p

        # case 2: user supplied a dict { pattern, recursive }
        elif isinstance(raw_out, dict):
            pattern = raw_out.get('pattern', "")
            # first try resolving via the FileService (e.g. glob in roots)
            try:
                cand = self._file_service.resolve_path(pattern, self._svc)
            except Exception as e:
                logger.exception(f"Error resolving pattern {pattern}: {e}", extra={'log_color': 'DELTA'})
                cand = None
            if cand:
                out_path = cand
            else:
                # fallback: treat it as a literal under the same folder
                if base_folder and pattern:
                    out_path = base_folder / pattern

        return out_path
    
    def _get_plan_out_path(self, task, base_folder: str = ""):
        # figure out where the AI output file actually lives
        raw_out = task.get('plan')
        out_path = None

        # case 1: user supplied a literal string path
        if isinstance(raw_out, str) and raw_out.strip():
            p = Path(raw_out)
            if not p.is_absolute() and base_folder:
                p = base_folder / p
            out_path = p

        # case 2: user supplied a dict { pattern, recursive }
        elif isinstance(raw_out, dict):
            pattern = raw_out.get('pattern', "")
            # first try resolving via the FileService (e.g. glob in roots)
            try:
                cand = self._file_service.resolve_path(pattern, self._svc)
            except Exception as e:
                logger.exception(f"Error resolving plan pattern {pattern}: {e}", extra={'log_color': 'DELTA'})
                cand = None
            if cand:
                out_path = cand
            else:
                # fallback: treat it as a literal under the same folder
                if base_folder and pattern:
                    out_path = base_folder / pattern

        return out_path

    def sanitize_desc(self, desc: str) -> str:
            """
            Sanitize description by stripping trailing flag patterns like [ x ], [ - ], etc.
            Called to clean desc after parsing or before rebuilding.
            Enhanced to robustly remove all trailing flag patterns, including multiples, and handle flags before pipes ('|').
            """
            logger.debug(f"Sanitizing desc: {desc[:100]}...")
            # Robust regex to match and strip trailing flags: [ followed by space or symbol, then ], possibly multiple
            # Also handles cases where flags are before a metadata pipe '|'
            flag_pattern = r'\s*\[\s*[x~-]\s*\]\s*(?=\||$)'
            pipe_flag_pattern = r'\s*\[\s*[x~-]\s*\]\s*\|'  # Flags before pipe
            while re.search(flag_pattern, desc) or re.search(pipe_flag_pattern, desc):
                # Remove trailing flags before pipe or end
                desc = re.sub(flag_pattern, '', desc)
                # Remove flags immediately before pipe
                desc = re.sub(pipe_flag_pattern, '|', desc)
                desc = desc.rstrip()  # Clean up whitespace
                logger.debug(f"Stripped trailing/multiple flags, new desc: {desc[:100]}...")
            # Also strip any extra | metadata if desc was contaminated (ensure only one leading desc part)
            if ' | ' in desc:
                desc = desc.split(' | ')[0].strip()  # Take only the first part as desc
                logger.debug(f"Stripped metadata contamination (pre-pipe), clean desc: {desc[:100]}...")
            # Final strip of any lingering bracket patterns at end
            desc = re.sub(r'\s*\[.*?\]\s*$', '', desc).strip()
            logger.debug(f"Final sanitized desc: {desc[:100]}...")
            return desc
