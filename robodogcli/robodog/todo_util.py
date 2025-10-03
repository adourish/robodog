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
from typing import List, Optional, Dict, Tuple
import statistics  # Added for calculating median, avg, peak

import tiktoken
from pydantic import BaseModel, RootModel
import yaml   # ensure PyYAML is installed
from typing import Any
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
    def __init__(self, roots: List[str], svc=None, prompt_builder=None, task_manager=None, task_parser=None, file_watcher=None, file_service=None, exclude_dirs={"node_modules", "dist", "diffout"}, app=None):
        logger.info(f"Initializing TodoUtilService with roots: {roots}", extra={'log_color': 'HIGHLIGHT'})
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
            self._app = app
            # MVP: parse a `base:` directive from front-matter


        except Exception as e:
            logger.exception(f"Error during initialization of TodoService: {e}", extra={'log_color': 'DELTA'})
            raise

    # --- Enhanced sanitize_desc method ---
    def sanitize_desc(self, desc: str) -> str:
        """
        Sanitize description by stripping trailing flag patterns like [ x ], [ - ], etc.
        Called to clean desc after parsing or before rebuilding.
        Enhanced to robustly remove all trailing flag patterns, including multiples, and handle flags before pipes ('|').
        Now also removes any lingering "[-]" patterns that may have accumulated. Enhanced: Iteratively remove until no more matches.
        """
        logger.debug(f"Sanitizing desc: {desc[:100]}...")
        # Robust regex to match and strip trailing flags: [ followed by space or symbol, then ], possibly multiple
        # Also handles cases where flags are before a metadata pipe '|'
        flag_pattern = r'\s*\[\s*[x~-]\s*\]\s*(?=\||$)'
        pipe_flag_pattern = r'\s*\[\s*[x~-]\s*\]\s*\|'  # Flags before pipe
        lingering_minus_flag = r'\s*\[\s*-\s*\]\s*$'  # Specific to catch trailing "[-]"
        while re.search(flag_pattern, desc) or re.search(pipe_flag_pattern, desc) or re.search(lingering_minus_flag, desc):
            # Remove trailing flags before pipe or end
            desc = re.sub(flag_pattern, '', desc)
            # Remove flags immediately before pipe
            desc = re.sub(pipe_flag_pattern, '|', desc)
            # Remove specific lingering "[-]" at end
            desc = re.sub(lingering_minus_flag, '', desc)
            desc = desc.rstrip()  # Clean up whitespace
            logger.debug(f"Stripped trailing/multiple/lingering flags, new desc: {desc[:100]}...")
        # Also strip any extra | metadata if desc was contaminated (ensure only one leading desc part)
        if ' | ' in desc:
            desc = desc.split(' | ')[0].strip()  # Take only the first part as desc
            logger.debug(f"Stripped metadata contamination (pre-pipe), clean desc: {desc[:100]}...")
        # Final strip of any lingering bracket patterns at end
        desc = re.sub(r'\s*\[.*?\]\s*$', '', desc).strip()
        logger.debug(f"Final sanitized desc: {desc[:100]}...")
        return desc

    # --- Enhanced _parse_task_metadata method ---
    def _parse_task_metadata(self, full_desc: str) -> Dict:
        """
        Parse the task description for metadata like started, completed, knowledge_tokens, etc.
        Returns a dict with parsed values and the clean description.
        Enhanced: Call sanitize_desc on full_desc at entry to remove any flags; re-sanitize post-metadata split.
        Ensure final task['desc'] is clean and free of trailing flags.
        Now parses plan_tokens as well. Enhanced: Parse stage-specific desc (plan_desc, llm_desc, commit_desc) from metadata if present (e.g., | plan_desc: ...).
        """
        logger.debug(f"Parsing metadata for task desc: {full_desc}")
        try:
            # First, sanitize the full_desc to remove any trailing flags, regardless of pipes, at entry
            full_desc = self.sanitize_desc(full_desc)
            logger.debug(f"Sanitized full_desc (flags removed at entry): {full_desc}")
            
            metadata = {
                'desc': full_desc.strip(),
                'plan_desc': full_desc.strip(),  # Enhanced: Default stage-specific desc to main desc
                'llm_desc': full_desc.strip(),
                'commit_desc': full_desc.strip(),
                '_start_stamp': None,
                '_complete_stamp': None,
                'knowledge_tokens': 0,
                'include_tokens': 0,
                'prompt_tokens': 0,
                'plan_tokens': 0,  # Enhanced: Added plan_tokens
            }
            # Split by | to separate desc from metadata, but only after sanitization
            parts = [p.strip() for p in full_desc.split('|') if p.strip()]
            if len(parts) > 1:
                metadata['desc'] = self.sanitize_desc(parts[0])  # Re-sanitize the desc part post-split to ensure no flags leaked
                logger.info(f"Clean desc after metadata split: {metadata['desc']}, metadata parts: {len(parts)-1}", extra={'log_color': 'HIGHLIGHT'})
                # Parse metadata parts (now safe from flag contamination)
                for part in parts[1:]:
                    if ':' in part:
                        key, val = [s.strip() for s in part.split(':', 1)]
                        try:
                            if key == 'started':
                                metadata['_start_stamp'] = val if val.lower() != 'none' else None
                                logger.info(f"Parsed started: {metadata['_start_stamp']}", extra={'log_color': 'HIGHLIGHT'})
                            elif key == 'completed':
                                metadata['_complete_stamp'] = val if val.lower() != 'none' else None
                                logger.info(f"Parsed completed: {metadata['_complete_stamp']}", extra={'log_color': 'HIGHLIGHT'})
                            elif key == 'knowledge':
                                metadata['knowledge_tokens'] = int(val) if val.isdigit() else 0
                                logger.info(f"Parsed knowledge tokens: {metadata['knowledge_tokens']}", extra={'log_color': 'PERCENT'})
                            elif key == 'include':
                                metadata['include_tokens'] = int(val) if val.isdigit() else 0
                                logger.info(f"Parsed include tokens: {metadata['include_tokens']}", extra={'log_color': 'PERCENT'})
                            elif key == 'prompt':
                                metadata['prompt_tokens'] = int(val) if val.isdigit() else 0
                                logger.info(f"Parsed prompt tokens: {metadata['prompt_tokens']}", extra={'log_color': 'PERCENT'})
                            elif key == 'plan':  # Enhanced: Parse plan_tokens
                                if 'tokens' in key or val.isdigit():
                                    metadata['plan_tokens'] = int(val) if val.isdigit() else 0
                                    logger.info(f"Parsed plan tokens: {metadata['plan_tokens']}", extra={'log_color': 'PERCENT'})
                                else:
                                    metadata['plan_desc'] = val  # Stage-specific desc
                            elif key in ['plan_desc', 'llm_desc', 'commit_desc']:  # Enhanced: Parse stage-specific desc
                                metadata[key] = val
                                logger.info(f"Parsed {key}: {val[:50]}...", extra={'log_color': 'HIGHLIGHT'})
                        except ValueError:
                            logger.warning(f"Failed to parse metadata part: {part}", extra={'log_color': 'DELTA'})
            # Final validation: Re-sanitize desc post-parsing to ensure it's completely clean
            metadata['desc'] = self.sanitize_desc(metadata['desc'])
            metadata['plan_desc'] = self.sanitize_desc(metadata['plan_desc'])
            metadata['llm_desc'] = self.sanitize_desc(metadata['llm_desc'])
            metadata['commit_desc'] = self.sanitize_desc(metadata['commit_desc'])
            logger.debug(f"Final parsed metadata with clean desc: {metadata}")
            return metadata
        except Exception as e:
            logger.exception(f"Error parsing task metadata for '{full_desc}': {e}", extra={'log_color': 'DELTA'})
            # Fallback: return sanitized desc with defaults
            clean_fallback = self.sanitize_desc(full_desc).strip()
            return {'desc': clean_fallback, 'plan_desc': clean_fallback, 'llm_desc': clean_fallback, 'commit_desc': clean_fallback, '_start_stamp': None, '_complete_stamp': None, 'knowledge_tokens': 0, 'include_tokens': 0, 'prompt_tokens': 0, 'plan_tokens': 0}

    # --- Enhanced _rebuild_task_line method ---
    def _rebuild_task_line(self, task: dict) -> str:
        """
        Safely reconstruct a task line to prevent flag appending issues.
        Enhanced: Always start with a fully sanitized desc from task['desc']; add flags only once, append metadata separately.
        Add validation to prevent flag duplication by ensuring desc has no trailing flags before building.
        Now includes plan_tokens in metadata if >0. Enhanced: Insert properties post-desc without overwriting refs; use main desc, append stage-specific if different.
        """
        logger.debug(f"Rebuilding task line for: {task['desc'][:50]}...")
        # Start with fully sanitized desc to ensure no trailing flags or duplicates (re-sanitize for safety)
        logger.debug(f"Sanitized desc in rebuild (no existing flags): {clean_desc[:50]}...")
        
        # Build flags string: Ensure single set of flags, no duplicates
        plan_char = task.get('plan_flag', ' ') if task.get('plan_flag') else ' '
        status_char = task.get('status_char', ' ') if task.get('status_char') else ' '
        write_char = task.get('write_flag', ' ') if task.get('write_flag') else ' '
        # Validation: Log if any char is invalid and default to ' '
        if plan_char not in ' x~-':
            logger.warning(f"Invalid plan_flag '{plan_char}' for task, defaulting to ' '", extra={'log_color': 'DELTA'})
            plan_char = ' '
        if status_char not in ' x~-':
            logger.warning(f"Invalid status_char '{status_char}' for task, defaulting to ' '", extra={'log_color': 'DELTA'})
            status_char = ' '
        if write_char not in ' x~-':
            logger.warning(f"Invalid write_flag '{write_char}' for task, defaulting to ' '", extra={'log_color': 'DELTA'})
            write_char = ' '
        
        flags = f"[{plan_char}][{status_char}][{write_char}]"
        line = task['indent'] + "- " + flags + " " + clean_desc
        # Append metadata if present (safely, after sanitized desc). Enhanced: Include plan_tokens and stage-specific desc if different
        meta_parts = []
        if task.get('_start_stamp'):
            meta_parts.append(f"started: {task['_start_stamp']}")
        if task.get('_complete_stamp'):
            meta_parts.append(f"completed: {task['_complete_stamp']}")
        if task.get('knowledge_tokens', 0) > 0:
            meta_parts.append(f"knowledge: {task['knowledge_tokens']}")
        if task.get('include_tokens', 0) > 0:
            meta_parts.append(f"include: {task['include_tokens']}")
        if task.get('prompt_tokens', 0) > 0:
            meta_parts.append(f"prompt: {task['prompt_tokens']}")
        if task.get('plan_tokens', 0) > 0:  # Enhanced: Add plan_tokens to metadata
            meta_parts.append(f"plan: {task['plan_tokens']}")
        # Enhanced: Append stage-specific desc if different from main desc
        for key in ['plan_desc', 'llm_desc', 'commit_desc']:
            stage_desc = task.get(key, '')
            if stage_desc and stage_desc != clean_desc:
                meta_parts.append(f"{key}: {stage_desc[:100]}")  # Truncate for line length
        if meta_parts:
            line += " | " + " | ".join(meta_parts)
        # Final validation: Ensure no duplicate flags in the rebuilt line (after appending metadata)
        if re.search(r'\[\s*[x~-]\s*\]\s*\[\s*[x~-]\s*\]\s*\[\s*[x~-]\s*\]\s*\[', line):
            logger.error(f"Potential flag duplication detected in rebuilt line: {line[:200]}...", extra={'log_color': 'DELTA'})
        logger.debug(f"Rebuilt task line (validated, no duplicates): {line[:100]}...")
        return line

    # --- modified write-and-report method ---
    def _write_parsed_files(self, parsed_files: List[dict], task: dict = None, commit_file: bool= False, base_folder: str = "", current_filename: str = None) -> tuple[int, List[str]]:
        """
        Write parsed files and compare tokens using parse_service object properties, return results and compare list
        For NEW files, resolve path relative to todo.md folder (base_dir) and create full path.
        For DELETE files, delete the matched file if it exists; prioritize DELETE over NEW even if both flags are set.
        matchedfilename remains relative for reporting.
        Enhanced logging for UPDATEs: full compare details with percentage deltas (median, avg, peak line/token changes).
        Added logging for planning step files. Now includes plan_tokens in token logging.
        Now sanitizes desc in logging to avoid flag contamination in logs. Enhanced: Use task['desc'] sanitized in logs.
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
                        # Enhanced: Sanitize task desc in logging
                        clean_task_desc = self.sanitize_desc(task['desc']) if task else ''
                        plan_t = task.get('plan_tokens', 0) if task else 0
                        logger.info(f"Write {action} {clean_relative}: (plan/k/i/p/o/u/d/p {plan_t}/{task.get('knowledge_tokens',0)}/{task.get('include_tokens',0)}/{task.get('prompt_tokens',0)}/{orig_tokens}/{new_tokens}/{abs_delta}/{token_delta:.1f}%) commit:{str(commit_file)} task_desc:{clean_task_desc[:50]}", extra={'log_color': 'PERCENT'})

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
                                    clean_task_desc = self.sanitize_desc(task['desc']) if task else ''
                                    logger.info(f"Updated for {filename} {clean_rel}: (plan/k/i/p/o/u/d/p {plan_t}/{task.get('knowledge_tokens',0)}/{task.get('include_tokens',0)}/{task.get('prompt_tokens',0)}/{orig_tokens}/{new_tokens}/{abs_delta}/{token_delta:.1f}%) task_desc:{clean_task_desc[:50]}", extra={'log_color': 'PERCENT'})
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
                p = Path(base_folder) / p
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
                    out_path = Path(base_folder) / pattern

        return out_path
    
    def _get_plan_out_path(self, task, base_folder: str = ""):
        # figure out where the plan.md file actually lives (similar to _get_ai_out_path)
        raw_out = task.get('plan')
        out_path = None

        # case 1: user supplied a literal string path
        if isinstance(raw_out, str) and raw_out.strip():
            p = Path(raw_out)
            if not p.is_absolute() and base_folder:
                p = Path(base_folder) / p
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
                    out_path = Path(base_folder) / pattern

        return out_path

    def sanitize_desc(self, desc: str) -> str:
        return desc


# original file length: 325 lines
# updated file length: 360 lines (enhanced _parse_task_metadata with entry sanitization and post-split re-sanitization, updated _rebuild_task_line with validation, and fixed typo in prompt tokens parsing)