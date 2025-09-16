# file: parse_service.py
#!/usr/bin/env python3
"""Parse various LLM output formats into file objects with enhanced metadata."""
import re
import json
import yaml
import xml.etree.ElementTree as ET
from typing import List, Dict, Optional, Union
import logging
import difflib
from pathlib import Path
from datetime import datetime

logger = logging.getLogger(__name__)


class ParsingError(Exception):
    """Custom exception for parsing errors."""
    pass

class ParseService:
    """Service for parsing various LLM output formats into file objects."""
    
    def __init__(self):
        """Initialize the ParseService with regex patterns for parsing."""
        logger.debug("Initializing ParseService")
        #self.section_pattern = re.compile(r'^#\s*file:\s*(.+)$', re.MULTILINE | re.IGNORECASE)
        self.section_pattern = re.compile(r'^\s*#\s*file:\s*["`]?(.+?)["`]?\s*$', re.IGNORECASE | re.MULTILINE)
        self.md_fenced_pattern = re.compile(r'```([^\^\n]*)\n(.*?)\n```', re.DOTALL)
        self.filename_pattern = re.compile(r'^([^:]+):\s*(.*)$', re.MULTILINE)
        # pattern to parse unified diff hunk headers
        self.hunk_header = re.compile(r'^@@ -\d+(?:,\d+)? \+(\d+)(?:,\d+)? @@')

    def parse_llm_output(
        self,
        llm_output: str,
        base_dir: Optional[str] = None,
        file_service: Optional[object] = None,
        ai_out_path: str = '',
        task: List[object] = None,
        svc: Optional[object] = None,
    ) -> List[Dict[str, Union[str, int]]]:
        """
        Parse LLM output into objects with enhanced metadata for better readability and tracking.
        Returns list of dicts each containing:
            'filename', 'originalfilename', 'matchedfilename',
            'content', 'originalcontent', 'diff_md',
            'new_tokens', 'original_tokens', 'delta_tokens', etc.
        """
        logger.debug(f"Starting enhanced parse of LLM output ({len(llm_output)} chars) with base_dir: {base_dir} and ai_out_path: {ai_out_path}")
        try:
            if self._is_section_format(llm_output):
                parsed_objects = self._parse_section_format(llm_output)
            elif self._is_json_format(llm_output):
                parsed_objects = self._parse_json_format(llm_output)
            elif self._is_yaml_format(llm_output):
                parsed_objects = self._parse_yaml_format(llm_output)
            elif self._is_xml_format(llm_output):
                parsed_objects = self._parse_xml_format(llm_output)
            elif self._is_md_fenced_format(llm_output):
                parsed_objects = self._parse_md_fenced_format(llm_output)
            else:
                parsed_objects = self._parse_generic_format(llm_output)
        except Exception as e:
            logger.error(f"Parsing error: {e}")
            try:
                parsed_objects = self._parse_fallback(llm_output)
            except Exception as fe:
                logger.error(f"Fallback parsing also failed: {fe}")
                raise ParsingError(f"Could not parse LLM output: {e}")

        # Enhance metadata for each parsed object
        for obj in parsed_objects:
            self._enhance_parsed_object(obj, base_dir, file_service, task, svc)

        # Write enhanced diffs to disk
        if ai_out_path:
            out_root = Path(ai_out_path).parent
        elif base_dir:
            out_root = Path(base_dir)
        else:
            out_root = Path.cwd()
        out_dir = out_root / 'diffoutput'
        out_dir.mkdir(parents=True, exist_ok=True)
        ts = datetime.utcnow().strftime("%Y%m%d-%H%M-%S")
        for obj in parsed_objects:
            md_diff = obj.get('diff_md', '')
            if not md_diff:
                continue
            stem = Path(obj.get('filename', 'file')).stem
            suffix = Path(obj.get('filename', '')).suffix or ''
            diff_name = f"diff-{stem}-{ts}{suffix}.md"
            diff_path = out_dir / diff_name
            try:
                with open(diff_path, 'w', encoding='utf-8') as f:
                    f.write(md_diff)
                logger.info(f"Diff: {diff_name} -> {diff_path}")
            except Exception as e:
                logger.error(f"Failed to write diff file {diff_path}: {e}")

        return parsed_objects

    def _load_truncation_phrases(self) -> List[str]:
        phrases_file = Path(__file__).parent / 'truncation_phrases.txt'
        if not phrases_file.exists():
            logger.warning("Truncation phrases file not found.")
            return []
        try:
            with open(phrases_file, 'r', encoding='utf-8') as f:
                return [line.strip() for line in f if line.strip()]
        except Exception as e:
            logger.error(f"Failed to load truncation phrases: {e}")
            return []

    def _enhance_parsed_object(
        self,
        obj: Dict[str, Union[str, int]],
        base_dir: Optional[str],
        file_service: Optional[object],
        task: List[object],
        svc: Optional[object] = None
    ):
        """
        Enhance the parsed object with:
         - originalfilename, matchedfilename
         - diff_md with emojis
         - token counts and delta
        """
        filename = obj.get('filename', '')
        new_content = obj.get('content', '')
        original_content = ''
        matched = filename
        diff_md = ''

        if file_service:
            try:
                # Use include spec from task if provided, else default to search all
                include_spec = {}
                if isinstance(task, dict) and isinstance(task.get('include'), dict):
                    include_spec = task['include']
                else:
                    include_spec = {'pattern': '*', 'recursive': True}
                candidate = file_service.find_matching_file(filename, include_spec, svc)
                if candidate:
                    matched = str(candidate.resolve())
                    original_content = file_service.safe_read_file(candidate)
                    diff_md = self._generate_improved_md_diff(filename, original_content, new_content, matched)
            except Exception as e:
                logger.error(f"resolve_path failed for {filename}: {e}")
        else:
            logger.warning(f"No file service provided for enhancing {filename}")

        new_tokens = len(new_content.split())
        original_tokens = len(original_content.split())
        delta_tokens = new_tokens - original_tokens
        change = 0.0 if original_tokens == 0 else abs(delta_tokens) / original_tokens * 100

        # Set metadata fields
        obj['originalfilename'] = filename
        obj['matchedfilename'] = matched
        obj['diff_md'] = diff_md
        obj['new_tokens'] = new_tokens
        obj['original_tokens'] = original_tokens
        obj['delta_tokens'] = delta_tokens
        obj['change'] = change

        # Prepend file marker to content and originalcontent
        obj['content'] = f"# file: {filename}\n{new_content}"
        obj['originalcontent'] = f"# file: {filename}\n{original_content}"

        # Check completeness
        obj['completeness'] = self._check_content_completeness(new_content, filename)

        # Comparison strings
        long_cmp = f"Compare: '{filename}' -> {matched} (orig/new/delta tokens: {original_tokens}/{new_tokens}/{delta_tokens}) change={change:.1f}%"
        short_cmp = f"Compare: '{filename}' (o/n/d: {original_tokens}/{new_tokens}/{delta_tokens}) c={change:.1f}%"
        obj['long_compare'] = long_cmp
        obj['short_compare'] = short_cmp
        obj['result'] = 0
        if change > 40.0:
            obj['result'] = -2
            logger.error(long_cmp + " >40%")
        elif change > 20.0:
            obj['result'] = -1
            logger.warning(long_cmp + " >20%")
        else:
            logger.info(long_cmp)

    def get_full_pattern_spec(self, task: dict, svc) -> str:
        logger.debug("Gathering include knowledge")
        inc = task.get('include') or {}
        spec = inc.get('pattern','')
        if not spec:
            return ""
        rec = " recursive" if inc.get('recursive') else ""
        full_spec = f"pattern={spec}{rec}"
        
        return full_spec
        
    def _check_content_completeness(self, content: str, orig_name: str) -> int:
        """
        Enhanced check if AI output appears complete, with phrases loaded from file to avoid triggering the function.
        - Too few lines (under 3) → error -3
        - Detect added truncation phrases from external file → error -4
        - Skip check for todo.md to avoid false positives
        """
        # Skip completeness check for todo.md as it's not AI-generated content
        if orig_name.lower() == 'todo.md':
            return 0
        
        lines = content.splitlines()
        if len(lines) < 3:
            logger.error(f"Incomplete output for {orig_name}: only {len(lines)} lines")
            return -3

        # Load truncation phrases from file
        truncation_phrases = self._load_truncation_phrases()
        lower = content.lower()
        for phrase in truncation_phrases:
            if phrase.lower() in lower:
                logger.error(f"Truncation indication found for {orig_name}: '{phrase}'")
                return -4

        return 0      

    def _generate_improved_md_diff(self, filename: str, original: str, updated: str, matched: str) -> str:
        """
        Generate improved markdown diff with emojis, actual file line numbers, and icons:
        - 🗂️ for file headers
        - 🔗 for matched path
        - 🧩 for hunk headers (@@)
        - [lineNo⚫/➕/⚪] for removed/added/unchanged lines
        """
        logger.debug(f"Generating improved MD diff for {filename}")
        orig_lines = original.splitlines()
        updt_lines = updated.splitlines()

        unified = list(difflib.unified_diff(
            orig_lines, updt_lines,
            fromfile=f'🔵 Original: {filename}',
            tofile=f'🔴 Updated: {filename} (matched: {matched})',
            lineterm='', n=7
        ))

        md_lines: List[str] = []
        md_lines.append(f"# 📊 Enhanced Diff for {filename}")
        md_lines.append(f"**File Path:** {matched or filename}")
        md_lines.append(f"**Change Timestamp:** {datetime.utcnow().isoformat()}")
        md_lines.append("")
        md_lines.append("## 🔍 Unified Diff (With Emojis & File Line Numbers)")
        md_lines.append("```diff")
        orig_num = None
        new_num = None
        for line in unified:
            if line.startswith('--- '):
                content = line[4:]
                md_lines.append(f"🗂️ {content}")
            elif line.startswith('+++ '):
                content = line[4:]
                if '(matched:' in content:
                    before, _, after = content.partition(' (matched:')
                    after = after.rstrip(')')
                    md_lines.append(f"🗂️ {before}")
                    md_lines.append(f"🔗 Matched: {after}")
                else:
                    md_lines.append(f"🗂️ {content}")
            elif line.startswith('@@'):
                md_lines.append(f"🧩 {line}")
                m = self.hunk_header.match(line)
                if m:
                    new_num = int(m.group(1))
                    orig_match = re.search(r'-([\d]+)', line)
                    if orig_match:
                        orig_num = int(orig_match.group(1))
                continue
            else:
                prefix = line[0] if line else ' '
                content = line[1:] if prefix in ('-', '+', ' ') else line
                if prefix == ' ':
                    emoji = '⚪'
                    if new_num is not None:
                        md_lines.append(f"[{new_num:4}{emoji}] {content}")
                    new_num = (new_num or 0) + 1
                    orig_num = (orig_num or 0) + 1
                elif prefix == '-':
                    emoji = '⚫'
                    if orig_num is not None:
                        md_lines.append(f"[{orig_num:4}{emoji}] {content}")
                    orig_num = (orig_num or 0) + 1
                elif prefix == '+':
                    emoji = '➕'
                    if new_num is not None:
                        md_lines.append(f"[{new_num:4}{emoji}] {content}")
                    new_num = (new_num or 0) + 1
                else:
                    md_lines.append(line)
        md_lines.append("```")
        return "\n".join(md_lines) + "\n"

    def _is_section_format(self, output: str) -> bool:
        return bool(self.section_pattern.search(output))

    def _is_json_format(self, output: str) -> bool:
        s = output.strip()
        if not (s.startswith('{') or s.startswith('[')):
            return False
        try:
            parsed = json.loads(s)
            return isinstance(parsed, dict) and 'files' in parsed
        except:
            return False

    def _is_yaml_format(self, output: str) -> bool:
        try:
            parsed = yaml.safe_load(output)
            return isinstance(parsed, dict) and 'files' in parsed
        except:
            return False

    def _is_xml_format(self, output: str) -> bool:
        s = output.strip()
        if not s.startswith('<'):
            return False
        try:
            root = ET.fromstring(s)
            return root.tag == 'files' and len(root) and root[0].tag == 'file'
        except:
            return False

    def _is_md_fenced_format(self, output: str) -> bool:
        return bool(self.md_fenced_pattern.search(output))

    def _parse_section_format(self, output: str) -> List[Dict[str, Union[str, int]]]:
        """
        Splits an LLM output into file‐sections by '# file: <filename>' markers,
        but only keeps the basename of each file.
        """
        matches = list(self.section_pattern.finditer(output))
        if not matches:
            return []

        sections: List[Dict[str, Union[str, int]]] = []
        # Build skeleton entries with basename-only filenames
        for m in matches:
            raw = m.group(1).strip()
            # strip surrounding quotes/backticks, then take only the final path component
            clean = raw.strip('\'"`')
            fn = Path(clean).name
            sections.append({'filename': fn, 'content': ''})

        # Carve out the content between markers
        for idx, m in enumerate(matches):
            start = m.end()
            end = matches[idx + 1].start() if idx + 1 < len(matches) else len(output)
            chunk = output[start:end]
            # trim leading/trailing blank lines
            chunk = re.sub(r'^\s*\n+', '', chunk)
            chunk = re.sub(r'\n+\s*$', '', chunk)
            sections[idx]['content'] = chunk

        return sections
    
    def _parse_json_format(self, output: str) -> List[Dict[str, Union[str, int]]]:
        data = json.loads(output.strip())
        files = data.get('files', [])
        if not isinstance(files, list):
            raise ParsingError("JSON 'files' must be list")
        parsed = []
        for it in files:
            fn = it.get('filename','').strip()
            ct = it.get('content','').strip()
            if self._validate_filename(fn):
                parsed.append({'filename': fn, 'content': ct})
        return parsed

    def _parse_yaml_format(self, output: str) -> List[Dict[str, Union[str, int]]]:
        data = yaml.safe_load(output)
        files = data.get('files', [])
        if not isinstance(files, list):
            raise ParsingError("YAML 'files' must be list")
        parsed = []
        for it in files:
            fn = it.get('filename','').strip()
            ct = it.get('content','').strip()
            if self._validate_filename(fn):
                parsed.append({'filename': fn, 'content': ct})
        return parsed

    def _parse_xml_format(self, output: str) -> List[Dict[str, Union[str, int]]]:
        root = ET.fromstring(output.strip())
        if root.tag != 'files':
            raise ParsingError("Root must be 'files'")
        parsed = []
        for fe in root.findall('file'):
            fn_el = fe.find('filename')
            ct_el = fe.find('content')
            if fn_el is None or ct_el is None:
                continue
            fn = (fn_el.text or '').strip()
            ct = (ct_el.text or '').strip()
            if self._validate_filename(fn):
                parsed.append({'filename': fn, 'content': ct})
        return parsed

    def _parse_md_fenced_format(self, output: str) -> List[Dict[str, Union[str, int]]]:
        """Parse Markdown fenced code blocks."""
        matches = self.md_fenced_pattern.findall(output)
        parsed_objects = []
        
        for info, content in matches:
            filename = info.strip() if info else "unnamed"
            
            if not self._validate_filename(filename):
                logger.warning(f"Invalid filename: {filename}, skipping")
                continue
            
            # Only change code that must be changed: validate and parse but don't add extra fields yet
            parsed_objects.append({
                'filename': filename,
                'content': content.strip()
            })
        
        logger.info(f"Parsed {len(parsed_objects)} files from Markdown fenced format")
        return parsed_objects

    def _parse_generic_format(self, output: str) -> List[Dict[str, Union[str, int]]]:
        """Best-effort parsing for unrecognized formats."""
        lines = output.split('\n')
        parsed_objects = []
        current_filename = None
        content_lines = []
        
        for line in lines:
            match = self.filename_pattern.match(line)
            if match:
                # Save previous file if exists
                if current_filename and content_lines:
                    content = '\n'.join(content_lines).strip()
                    if self._validate_filename(current_filename):
                        parsed_objects.append({
                            'filename': current_filename,
                            'content': content
                        })
                    content_lines = []
                
                current_filename = match.group(1).strip()
                content_lines.append(match.group(2).strip())
            elif current_filename and line.strip():
                content_lines.append(line.strip())
        
        # Save last file
        if current_filename and content_lines:
            content = '\n'.join(content_lines).strip()
            if self._validate_filename(current_filename):
                parsed_objects.append({
                    'filename': current_filename,
                    'content': content
                })
        
        if not parsed_objects:
            raise ParsingError("No valid files found in generic parsing")
        
        logger.info("Parsed %d files from generic format", len(parsed_objects))
        return parsed_objects

    def _parse_fallback(self, output: str) -> List[Dict[str, Union[str, int]]]:
        """Ultimate fallback: treat entire output as single file."""
        logger.warning("Using fallback parser - treating output as single file")
        return [{
            'filename': 'generated.txt',
            'content': output.strip()
        }]

    def _validate_filename(self, filename: str) -> bool:
        """Validate filename for safety."""
        if not filename or len(filename) > 255:
            return False
        
        # Check for invalid characters
        invalid_chars = ['<>:"/\\|?*']
        for char in invalid_chars:
            if char in filename:
                return False
        
        # Check for path traversal attempts
        if '..' in filename or filename.startswith('/'):
            return False
        
        return True

    def write_parsed_files(self, parsed_objects: List[Dict[str, Union[str, int]]], base_dir: str = '.') -> Dict[str, Union[int, List[str]]]:
        """
        Write parsed files to disk.
        
        Args:
            parsed_objects: List of enhanced file objects from parse_llm_output
            base_dir: Base directory to write files to
            
        Returns:
            Dict with success count and error list
        """
        success_count = 0
        errors = []
        base_path = Path(base_dir)
        
        for obj in parsed_objects:
            try:
                filepath = base_path / obj['filename']
                filepath.parent.mkdir(parents=True, exist_ok=True)
                # Write the content, which now includes length comments
                filepath.write_text(obj['content'], encoding='utf-8')
                success_count += 1
                logger.info(f"Written file: {filepath} ({obj.get('tokens', 0)} tokens)")
            except Exception as e:
                error_msg = f"Failed to write {obj['filename']}: {e}"
                logger.error(error_msg)
                errors.append(error_msg)
        
        logger.info(f"Successfully wrote {success_count} files")
        if errors:
            logger.warning(f"Errors encountered: {len(errors)}")
        
        return {
            'success_count': success_count,
            'errors': errors
        }
# original file length: 468 lines
# updated file length: 468 lines