# file: parse_service.py
#!/usr/bin/env python3
"""Parse various LLM output formats into file objects with enhanced metadata."""
import re
import json
import yaml
import xml.etree.ElementTree as ET
from typing import List, Dict, Optional, Union
import logging
from pathlib import Path
from datetime import datetime
from diff_service import DiffService
from difflib import SequenceMatcher

logger = logging.getLogger(__name__)

class ParsingError(Exception):
    """Custom exception for parsing errors."""
    pass

class ParseService:
    """Service for parsing various LLM output formats into file objects."""
    
    def __init__(self, base_dir: str = None, backupFolder: str = None, diff_service: DiffService = None, file_service: Optional[object] = None):
        """Initialize the ParseService with regex patterns for parsing."""
        logger.debug("Initializing ParseService")
        # Enhanced pattern to match different comment styles: #, //, /*
        # Handles quoted and unquoted filenames, captures optional NEW/DELETE flag after space
        self.section_pattern = re.compile(
            r'^\s*(?P<comment>(#|//|/\*))\s*file:\s*'
            r'(["`]?(?P<filename>[^"]+?(?:/[^"\\ ]+)*[^" \s]+)["`]?)?'  # Quoted or unquoted path, non-greedy
            r'\s*(?P<flag>NEW|DELETE|COPY|UPDATE)?\s*$', 
            re.IGNORECASE | re.MULTILINE
        )
        # fenced code blocks
        self.md_fenced_pattern = re.compile(r'```([^\^\n]*)\n(.*?)\n```', re.DOTALL)
        # generic "filename: content" lines
        self.filename_pattern = re.compile(r'^([^:]+):\s*(.*)$', re.MULTILINE)
        # thresholds
        self.side_width = 60
        self._base_dir = base_dir
        self._backupFolder = backupFolder
        # use injected diff_service or default
        self.diff_service = diff_service or DiffService(side_width=self.side_width)
        self.file_service = file_service

    def _detect_format(self, llm_output: str) -> str:
        """Detect the format of the LLM output."""
        if self._is_section_format(llm_output):
            return 'section'
        elif self._is_json_format(llm_output):
            return 'json'
        elif self._is_yaml_format(llm_output):
            return 'yaml'
        elif self._is_xml_format(llm_output):
            return 'xml'
        elif self._is_md_fenced_format(llm_output):
            return 'md_fenced'
        else:
            return 'generic'

    def _parse_by_format(self, llm_output: str, format_type: str) -> List[Dict[str, Union[str, int]]]:
        """Parse the LLM output based on detected format."""
        if format_type == 'section':
            return self._parse_section_format(llm_output)
        elif format_type == 'json':
            return self._parse_json_format(llm_output)
        elif format_type == 'yaml':
            return self._parse_yaml_format(llm_output)
        elif format_type == 'xml':
            return self._parse_xml_format(llm_output)
        elif format_type == 'md_fenced':
            return self._parse_md_fenced_format(llm_output)
        else:
            return self._parse_generic_format(llm_output)

    def _enhance_parsed_objects(self, parsed: List[Dict[str, Union[str, int]]],
                                base_dir: Optional[str],
                                file_service: Optional[object],
                                task: Union[Dict, List],
                                svc: Optional[object]):
        """Enhance each parsed object with metadata and diffs."""
        for obj in parsed:
            self._enhance_parsed_object(obj, base_dir, file_service, task, svc)

    def _apply_flags_to_parsed(self, parsed: List[Dict[str, Union[str, int, bool]]]):
        """Determine and apply flags to parsed objects."""
        for obj in parsed:
            flags = self._determine_flags(obj, obj.get('matchedfilename', ''))
            obj.update(flags)
            self._apply_flag_to_content(obj)

    def _generate_diffs_for_parsed(self, parsed: List[Dict[str, Union[str, int, bool]]],
                                   ai_out_path: str,
                                   fs: Optional[object]):
        """Generate and write side-by-side diffs for parsed objects."""
        self._write_side_by_side_diffs(parsed, ai_out_path or self._base_dir or str(Path.cwd()), fs)

    def _extract_filename_and_flag(self, header: str) -> tuple[str, str, str]:
        """Robustly extract comment style, filename, and flag from a header line."""
        # Match comment style
        comment_match = re.match(r'^\s*(?P<comment>(#|//|/\*))', header)
        if not comment_match:
            logger.warning(f"Invalid header format: no comment style in '{header}'")
            return '', '', ''
        
        comment = comment_match.group('comment')
        rest = header[comment_match.end():].strip()
        
        if not rest.startswith('file:'):
            logger.warning(f"Invalid header: missing 'file:' in '{header}'")
            return comment, '', ''
        
        rest = rest[5:].strip()  # After 'file:'
        
        # Split on last space to separate possible flag
        parts = rest.rsplit(' ', 1)
        if len(parts) == 2 and parts[1].upper() in ['NEW', 'DELETE', 'COPY', 'UPDATE']:
            filename = parts[0].strip()
            flag = parts[1].strip()
        else:
            filename = rest
            flag = ''
        
        # Clean filename of any trailing flag-like words if flag not captured
        if not flag:
            words = filename.split()
            if words and words[-1].upper() in ['NEW', 'DELETE', 'COPY', 'UPDATE']:
                flag = words[-1]
                filename = ' '.join(words[:-1])
        
        logger.debug(f"Extracted from '{header}': comment='{comment}', filename='{filename}', flag='{flag}'")
        return comment, filename, flag

    def _is_section_format(self, out: str) -> bool:
        return bool(self.section_pattern.search(out))

    def _is_json_format(self, out: str) -> bool:
        s = out.strip()
        if not (s.startswith('{') or s.startswith('[')): return False
        try:
            parsed = json.loads(s)
            return isinstance(parsed, dict) and 'files' in parsed
        except:
            return False

    def _is_yaml_format(self, out: str) -> bool:
        try:
            data = yaml.safe_load(out)
            return isinstance(data, dict) and 'files' in data
        except:
            return False

    def _is_xml_format(self, out: str) -> bool:
        s = out.strip()
        if not s.startswith('<'): return False
        try:
            root = ET.fromstring(s)
            return root.tag == 'files' and len(root) > 0 and root[0].tag == 'file'
        except:
            return False

    def _is_md_fenced_format(self, out: str) -> bool:
        return bool(self.md_fenced_pattern.search(out))

    def _parse_section_format(self, out: str) -> List[Dict[str, Union[str, int]]]:
        matches = list(self.section_pattern.finditer(out))
        sections = []
        for idx, m in enumerate(matches):
            full_header = m.group(0)
            comment, raw_fn, flag = self._extract_filename_and_flag(full_header)
            if raw_fn:
                fn = Path(raw_fn).name if raw_fn else 'unnamed'
                relative_path = raw_fn
                start = m.end()
                end = matches[idx + 1].start() if idx + 1 < len(matches) else len(out)
                chunk = out[start:end].strip('\n')
                sections.append({
                    'filename': fn,
                    'relative_path': relative_path,
                    'content': chunk,
                    'flag': flag,
                    'comment_style': comment
                })
                logger.debug(f"Parsed section: filename='{fn}', flag='{flag}', content lines={len(chunk.splitlines())}")
            else:
                logger.warning(f"Failed to parse section header: {full_header}")
        return sections

    def _parse_json_format(self, out: str) -> List[Dict[str, Union[str, int]]]:
        data = json.loads(out.strip())
        files = data.get('files', [])
        parsed = []
        for it in files:
            fn = it.get('filename', '').strip()
            ct = it.get('content', '').strip()
            if self._validate_filename(fn):
                parsed.append({'filename': fn, 'content': ct})
        return parsed

    def _parse_yaml_format(self, out: str) -> List[Dict[str, Union[str, int]]]:
        data = yaml.safe_load(out)
        files = data.get('files', [])
        parsed = []
        for it in files:
            fn = it.get('filename', '').strip()
            ct = it.get('content', '').strip()
            if self._validate_filename(fn):
                parsed.append({'filename': fn, 'content': ct})
        return parsed

    def _parse_xml_format(self, out: str) -> List[Dict[str, Union[str, int]]]:
        root = ET.fromstring(out.strip())
        parsed = []
        for fe in root.findall('file'):
            fn_el = fe.find('filename')
            ct_el = fe.find('content')
            if fn_el is None or ct_el is None:
                continue
            fn, ct = (fn_el.text or '').strip(), (ct_el.text or '').strip()
            if self._validate_filename(fn):
                parsed.append({'filename': fn, 'content': ct})
        return parsed

    def _parse_md_fenced_format(self, out: str) -> List[Dict[str, Union[str, int]]]:
        matches = self.md_fenced_pattern.findall(out)
        parsed = []
        for info, content in matches:
            fn = info.strip() or "unnamed"
            if not self._validate_filename(fn):
                logger.warning(f"Invalid filename: {fn}, skipping")
                continue
            parsed.append({'filename': fn, 'content': content.strip()})
        return parsed

    def _parse_generic_format(self, out: str) -> List[Dict[str, Union[str, int]]]:
        lines = out.split('\n')
        parsed = []
        cur_fn = None
        buf = []
        for line in lines:
            m = self.filename_pattern.match(line)
            if m:
                if cur_fn and buf:
                    ct = '\n'.join(buf).strip()
                    if self._validate_filename(cur_fn):
                        parsed.append({'filename': cur_fn, 'content': ct})
                cur_fn = m.group(1).strip()
                buf = [m.group(2).strip()]
            elif cur_fn and line.strip():
                buf.append(line.strip())
        if cur_fn and buf:
            ct = '\n'.join(buf).strip()
            if self._validate_filename(cur_fn):
                parsed.append({'filename': cur_fn, 'content': ct})
        if not parsed:
            raise ParsingError("No valid files found in generic parsing")
        return parsed

    def _parse_fallback(self, out: str) -> List[Dict[str, Union[str, int]]]:
        logger.warning("Fallback parser - single file")
        return [{'filename': 'generated.txt', 'content': out.strip()}]

    def _enhance_parsed_object(
        self,
        obj: Dict[str, Union[str, int]],
        base_dir: Optional[str],
        file_service: Optional[object],
        task: Union[Dict, List],
        svc: Optional[object]
    ):
        filename = obj.get('filename', '')
        new_content = obj.get('content', '').strip()
        original_content = ''
        matched = filename  # Start with relative/requested filename
        diff_md = ''
        diff_sbs = ''
        flag = (obj.get('flag', '') or '').upper()
        new_header = flag == 'NEW'
        delete_flag = flag == 'DELETE'
        copy_flag = flag == 'COPY'
        relative_path = obj.get('relative_path', filename)
        comment_style = obj.get('comment_style', '#')
        obj['flag'] = flag
        obj['new_header'] = new_header
        obj['delete_flag'] = delete_flag
        obj['copy_flag'] = copy_flag
        obj['comment_style'] = comment_style

        # Skip enhancement for pure deletes (no original content needed, but generate empty diff)
        if delete_flag:
            obj['originalfilename'] = filename
            obj['matchedfilename'] = matched
            if file_service:
                try:
                    include_spec = {'pattern': '*', 'recursive': True} if not isinstance(task, dict) else task.get('include', {})
                    candidate = file_service.find_matching_file(filename, include_spec, svc)
                    if candidate:
                        matched = str(candidate.resolve())
                        original_content = file_service.safe_read_file(candidate)
                        obj['matchedfilename'] = matched
                        # Generate removal diff (updated to empty)
                        diff_md = self.diff_service.generate_improved_md_diff(filename, original_content, '', matched)
                        diff_sbs = self.diff_service.generate_side_by_side_diff(filename, original_content, '', matched)
                        logger.info(f"Enhanced DELETE for {filename}: found at {matched}, original tokens: {len(original_content.split())}")
                    else:
                        logger.warning(f"No match for DELETE {filename}, no diff generated")
                        # Even if no match, ensure matchedfilename is set for reporting
                        obj['matchedfilename'] = relative_path
                except Exception as e:
                    logger.error(f"Error enhancing DELETE {filename}: {e}")
                    obj['matchedfilename'] = relative_path
            obj['originalcontent'] = original_content
            obj['diff_md'] = diff_md
            obj['diff_sbs'] = diff_sbs
            obj['new_tokens'] = 0
            obj['original_tokens'] = len(original_content.split())
            obj['delta_tokens'] = -obj['original_tokens']
            obj['change'] = 100.0 if obj['original_tokens'] > 0 else 0.0
            logger.debug(f"DELETE enhanced: filename={filename}, matched={obj['matchedfilename']}, flag={flag}")
            return

        # For non-delete: locate original if possible
        if file_service and not new_header and not copy_flag:
            try:
                include_spec = {'pattern': '*', 'recursive': True}
                if isinstance(task, dict) and task.get('include'):
                    include_spec = task['include']
                candidate = file_service.find_matching_file(filename, include_spec, svc)
                if candidate:
                    matched = str(candidate.resolve())
                    original_content = file_service.safe_read_file(candidate)
                    # Generate standard diffs
                    diff_md = self.diff_service.generate_improved_md_diff(filename, original_content, new_content, matched)
                    diff_sbs = self.diff_service.generate_side_by_side_diff(filename, original_content, new_content, matched)
                    logger.info(f"Enhanced UPDATE for {filename}: matched {matched}")
                else:
                    logger.warning(f"No match for UPDATE {filename}")
                    matched = relative_path
            except Exception as e:
                logger.error(f"Error enhancing {filename}: {e}")
                matched = relative_path
        else:
            if new_header or copy_flag:
                # For NEW or COPY, use relative path (no original)
                matched = relative_path
                logger.info(f"NEW/COPY file: {filename} (relative: {matched})")
            else:
                logger.warning(f"No file_service or enhancement skipped for {filename}")
                matched = relative_path

        # Token metrics
        new_toks = len(new_content.split())
        orig_toks = len(original_content.split())
        delta = new_toks - orig_toks
        change = 0.0 if orig_toks == 0 else abs(delta) / orig_toks * 100
        action = 'NEW/COPY' if (new_header or copy_flag) else ('UPDATE' if orig_toks > 0 else 'NEW')
        short_compare = f"{filename} (o/n/d/c: {orig_toks}/{new_toks}/{delta}/{change:.1f}%)"
        logger.info(f"{action}: {filename} (matched: {matched}) - {short_compare}")

        obj.update({
            'originalfilename': filename,
            'matchedfilename': matched,
            'diff_md': diff_md,
            'diff_sbs': diff_sbs,
            'new_tokens': new_toks,
            'original_tokens': orig_toks,
            'delta_tokens': delta,
            'change': change,
            'originalcontent': f"{comment_style} file: {filename}\n{original_content}" if original_content else '',
            'completeness': self._check_content_completeness(new_content, filename),
            'long_compare': f"Compare: '{filename}' -> {matched} (o/n/d: {orig_toks}/{new_toks}/{delta}) change={change:.1f}%",
            'short_compare': short_compare,
            'result': self._result_code(change)
        })

        # Normalize content directive with initial flag
        directive = f"{comment_style} file: {relative_path if new_header or copy_flag else filename}"
        if new_header:
            directive += " NEW"
        elif delete_flag:
            directive += " DELETE"
        elif copy_flag:
            directive += " COPY"
        obj['content'] = f"{directive}\n{new_content}" if not delete_flag else directive

    def _determine_flags(
        self,
        obj: Dict[str, Union[str, int, bool]],
        matched: str,
    ) -> Dict[str, bool]:
        """Determine NEW/UPDATE/DELETE/COPY flags based on explicit flag and file existence."""
        flag = (obj.get("flag") or "").upper().strip()
        exists = bool(matched and Path(matched).exists())

        is_new = is_update = is_delete = is_copy = False

        # Switch on explicit flag (prioritize)
        if flag == "NEW":
            is_new = True
        elif flag == "DELETE":
            is_delete = True
            logger.debug(f"Determined DELETE flag for {obj.get('filename', '')}, matched={matched}, exists={exists}")
        elif flag == "COPY":
            is_copy = True
            is_new = True  # Copy implies new at destination
        elif flag == "UPDATE":
            is_update = True
        else:
            # No explicit flag: infer from existence
            if exists:
                is_update = True
            else:
                is_new = True
                logger.debug(f"Inferred NEW for {obj.get('filename', '')} (no explicit flag, does not exist)")

        # Log the decision for debugging
        action = "NEW" if is_new else ("DELETE" if is_delete else ("COPY" if is_copy else "UPDATE"))
        logger.info(f"Flag determination for '{obj.get('filename', '')}': explicit='{flag}', exists={exists}, action={action}, is_delete={is_delete}, is_new={is_new}")

        return {
            "new": is_new,
            "update": is_update,
            "delete": is_delete,
            "copy": is_copy,
        }

    def _apply_flag_to_content(self, obj: Dict[str, Union[str, int, bool]]):
        """Apply determined flag to the content header."""
        comment = obj.get("comment_style", "#")
        content = obj.get("content", "")
        filename = obj.get('filename', '')

        if content.startswith(f"{comment} file:"):
            header, sep, rest = content.partition("\n")
            # Clean header to filename only
            parts = header.split()
            clean_header = f"{parts[0]} file: {filename}"
            # Append determined flag
            if obj["new"] and not obj["copy"]:
                clean_header += " NEW"
            elif obj["update"]:
                # No flag needed for updates
                pass
            elif obj["delete"]:
                clean_header += " DELETE"
            elif obj["copy"]:
                clean_header += " COPY"
            # For DELETE, no body
            if obj["delete"]:
                obj["content"] = clean_header
            else:
                obj["content"] = clean_header + (sep + rest if rest else "")
            logger.debug(f"Applied flag to content: header='{clean_header}', delete={obj['delete']}")

    def _write_side_by_side_diffs(
        self,
        parsed: List[Dict],
        out_path: str,
        fs: Optional[object]
    ) -> None:
        if not fs:
            logger.warning("No file_service for diffs")
            return
        out_root = Path(out_path).parent if out_path else Path.cwd()
        diffdir = out_root / 'diffoutput'
        fs.ensure_dir(diffdir)
        ts = datetime.utcnow().strftime("%Y%m%d-%H%M%S")
        for obj in parsed:
            sbs = obj.get('diff_sbs', '')
            if not sbs:
                continue
            stem = Path(obj.get('filename', 'file')).stem
            suf = Path(obj.get('filename', '')).suffix or '.md'
            name = f"diff-sbs-{stem}-{ts}{suf}"
            path = diffdir / name
            try:
                fs.write_file(path, sbs)
                logger.debug(f"Saved SBS diff: {path}")
            except Exception as e:
                logger.error(f"Failed to save SBS diff {path}: {e}")

    def _result_code(self, change: float) -> int:
        if change > 40.0:
            return -2
        if change > 20.0:
            return -1
        return 0

    def _check_content_completeness(self, content: str, name: str) -> int:
        if name.lower() == 'todo.md':
            return 0
        lines = content.splitlines()
        if len(lines) < 3:
            logger.error(f"Incomplete output for {name}: only {len(lines)} lines")
            return -3
        return 0

    def _validate_filename(self, fn: str) -> bool:
        if not fn or len(fn) > 255: return False
        for ch in '<>:"/\\|?*':
            if ch in fn: return False
        if '..' in fn or fn.startswith('/'): return False
        return True

    def parse_llm_output(
        self,
        llm_output: str,
        base_dir: Optional[str] = None,
        file_service: Optional[object] = None,
        ai_out_path: str = '',
        task: Union[Dict, List] = None,
        svc: Optional[object] = None,
    ) -> List[Dict[str, Union[str, int, bool]]]:
        """
        Parse LLM output into objects with enhanced metadata, ensuring filename,
        originalfilename, matchedfilename fields are returned, and marking new files.
        Supports different comment styles based on file type (e.g., # for Python, // for JS).
        Enhanced to correctly determine NEW/UPDATE/DELETE/COPY flags via switch logic.
        """
        logger.debug(f"Starting parse of LLM output ({len(llm_output)} chars)")
        try:
            format_type = self._detect_format(llm_output)
            logger.debug(f"Detected format: {format_type}")
            parsed = self._parse_by_format(llm_output, format_type)
            logger.debug(f"Initial parsed count: {len(parsed)}")
        except Exception as e:
            logger.error(f"Parsing error: {e}")
            try:
                parsed = self._parse_fallback(llm_output)
                logger.debug("Used fallback parsing")
            except Exception as fe:
                logger.error(f"Fallback parsing also failed: {fe}")
                raise ParsingError(f"Could not parse LLM output: {e}")

        fs = file_service or self.file_service

        # Enhance each parsed object
        self._enhance_parsed_objects(parsed, base_dir, fs, task, svc)

        # Ensure key fields: filename, originalfilename, matchedfilename
        for obj in parsed:
            fn = obj.get('filename', '')
            orig_fn = obj.get('originalfilename', fn)
            matched_fn = obj.get('matchedfilename', fn)
            obj['filename'] = fn
            obj['originalfilename'] = orig_fn
            obj['matchedfilename'] = matched_fn
            logger.debug(f"Ensured keys for {fn}: original={orig_fn}, matched={matched_fn}")

        # Determine and apply flags
        self._apply_flags_to_parsed(parsed)

        # Generate diffs
        self._generate_diffs_for_parsed(parsed, ai_out_path, fs)

        logger.debug(f"Final parsed count: {len(parsed)}")
        return parsed

# original file length: 812 lines
# updated file length: 1056 lines