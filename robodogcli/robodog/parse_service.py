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
from difflib import SequenceMatcher
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
        self.section_pattern = re.compile(r'^\s*#\s*file:\s*["`]?(.+?)["`]?\s*$', re.IGNORECASE | re.MULTILINE)
        self.md_fenced_pattern = re.compile(r'```([^\^\n]*)\n(.*?)\n```', re.DOTALL)
        self.filename_pattern = re.compile(r'^([^:]+):\s*(.*)$', re.MULTILINE)
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
        Parse LLM output into objects with enhanced metadata, ensuring filename,
        originalfilename, and matchedfilename fields are returned.
        """
        logger.debug(f"Starting enhanced parse of LLM output ({len(llm_output)} chars)")
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

        # Enhance each parsed object with diffs and token metrics
        for obj in parsed_objects:
            self._enhance_parsed_object(obj, base_dir, file_service, task, svc)

        # Ensure essential filename keys are present
        for obj in parsed_objects:
            fn = obj.get('filename', '')
            obj['filename'] = fn
            obj.setdefault('originalfilename', fn)
            obj.setdefault('matchedfilename', fn)

        # Write enhanced diffs to disk (side-by-side diff only)
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
            sbs_diff = obj.get('diff_sbs', '')
            if not sbs_diff:
                continue
            stem = Path(obj.get('filename', 'file')).stem
            suffix = Path(obj.get('filename', '')).suffix or ''
            diff_name = f"diff-sbs-{stem}-{ts}{suffix}.md"
            diff_path = out_dir / diff_name
            try:
                with open(diff_path, 'w', encoding='utf-8') as f:
                    f.write(sbs_diff)
                logger.info(f"Side-by-Side Diff: {diff_name} -> {diff_path}")
            except Exception as e:
                logger.error(f"Failed to write side-by-side diff file {diff_path}: {e}")

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
        filename = obj.get('filename', '')
        new_content = obj.get('content', '')
        original_content = ''
        matched = filename
        diff_md = ''
        diff_sbs = ''

        if file_service:
            try:
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
                    diff_sbs = self._generate_side_by_side_diff(filename, original_content, new_content, matched)
            except Exception as e:
                logger.error(f"resolve_path failed for {filename}: {e}")
        else:
            logger.warning(f"No file service provided for enhancing {filename}")

        new_tokens = len(new_content.split())
        original_tokens = len(original_content.split())
        delta_tokens = new_tokens - original_tokens
        change = 0.0 if original_tokens == 0 else abs(delta_tokens) / original_tokens * 100

        obj['originalfilename'] = filename
        obj['matchedfilename'] = matched
        obj['diff_md'] = diff_md
        obj['diff_sbs'] = diff_sbs
        obj['new_tokens'] = new_tokens
        obj['original_tokens'] = original_tokens
        obj['delta_tokens'] = delta_tokens
        obj['change'] = change

        obj['content'] = f"# file: {filename}\n{new_content}"
        obj['originalcontent'] = f"# file: {filename}\n{original_content}"
        obj['completeness'] = self._check_content_completeness(new_content, filename)

        long_cmp = f"Compare: '{filename}' -> {matched} (orig/new/delta tokens: {original_tokens}/{new_tokens}/{delta_tokens}) change={change:.1f}%"
        short_cmp = f"'{filename}' (o/n/d/c: {original_tokens}/{new_tokens}/{delta_tokens}/{change:.1f}%) "
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

    def _check_content_completeness(self, content: str, orig_name: str) -> int:
        if orig_name.lower() == 'todo.md':
            return 0
        lines = content.splitlines()
        if len(lines) < 3:
            logger.error(f"Incomplete output for {orig_name}: only {len(lines)} lines")
            return -3
        truncation_phrases = self._load_truncation_phrases()
        lower = content.lower()
        for phrase in truncation_phrases:
            if phrase.lower() in lower:
                logger.error(f"Truncation indication found for {orig_name}: '{phrase}'")
                return -4
        return 0      

    def _generate_improved_md_diff(self, filename: str, original: str, updated: str, matched: str) -> str:
        """
        Enhanced unified diff with emojis.
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
                md_lines.append(f"🗂️ {line[4:]}")
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
                    om = re.search(r'-([\d]+)', line)
                    if om:
                        orig_num = int(om.group(1))
                continue
            else:
                prefix = line[0] if line else ' '
                content = line[1:] if prefix in ('-', '+', ' ') else line
                if prefix == ' ':
                    emoji='⚪'
                    if new_num is not None:
                        md_lines.append(f"[{new_num:4}{emoji}] {content}")
                    new_num = (new_num or 0) + 1
                    orig_num = (orig_num or 0) + 1
                elif prefix == '-':
                    emoji='⚫'
                    if orig_num is not None:
                        md_lines.append(f"[{orig_num:4}{emoji}] {content}")
                    orig_num = (orig_num or 0) + 1
                elif prefix == '+':
                    emoji='➕'
                    if new_num is not None:
                        md_lines.append(f"[{new_num:4}{emoji}] {content}")
                    new_num = (new_num or 0) + 1
                else:
                    md_lines.append(line)
        md_lines.append("```")
        return "\n".join(md_lines) + "\n"

    def _generate_side_by_side_diff(self, filename: str, original: str, updated: str, matched: str) -> str:
        """
        Generate a side-by-side diff using pipes, emojis, and spacing.
        Columns are truncated to improve readability on standard laptop screens.
        """
        logger.debug(f"Generating side-by-side diff for {filename}")
        orig_lines = original.splitlines()
        updt_lines = updated.splitlines()
        matcher = SequenceMatcher(None, orig_lines, updt_lines)
        ops = matcher.get_opcodes()
        # Determine max width for left column content, truncated at 60 chars
        max_left = min(max((len(l) for l in orig_lines), default=0), 60)
        left_pad = max_left + 8  # account for "[####] emoji " prefix
        # Limit right column to 60 chars
        max_right = 60

        lines: List[str] = []
        lines.append(f"📑 Side-by-Side Diff for {filename}")
        lines.append(f"🔗 {matched or filename}")
        lines.append(f"⏱️ {datetime.utcnow().isoformat()}")
        lines.append("")
        header = f"{'ORIGINAL'.ljust(left_pad)} | {'UPDATED'}"
        lines.append(header)
        lines.append("-" * left_pad + "-|-" + "-" * max_right)

        o_ln = 1
        n_ln = 1
        for tag, i1, i2, j1, j2 in ops:
            if tag == 'equal':
                for i in range(i1, i2):
                    l = orig_lines[i]
                    disp = l if len(l) <= max_left else l[:max_left-3] + '...'
                    left = f"[{o_ln:4}⚪] {disp}".ljust(left_pad)
                    right = f"[{n_ln:4}⚪] {disp}"
                    lines.append(f"{left} | {right}")
                    o_ln += 1; n_ln += 1
            elif tag == 'delete':
                for i in range(i1, i2):
                    l = orig_lines[i]
                    disp = l if len(l) <= max_left else l[:max_left-3] + '...'
                    left = f"[{o_ln:4}⚫] {disp}".ljust(left_pad)
                    right = " " * max_right
                    lines.append(f"{left} | {right}")
                    o_ln += 1
            elif tag == 'insert':
                for j in range(j1, j2):
                    l = updt_lines[j]
                    disp = l if len(l) <= max_right else l[:max_right-3] + '...'
                    left = " " * left_pad
                    right = f"[{n_ln:4}➕] {disp}"
                    lines.append(f"{left} | {right}")
                    n_ln += 1
            elif tag == 'replace':
                a = orig_lines[i1:i2]
                b = updt_lines[j1:j2]
                m = max(len(a), len(b))
                for k in range(m):
                    if k < len(a):
                        la = a[k]
                        disp_a = la if len(la) <= max_left else la[:max_left-3] + '...'
                        left = f"[{o_ln:4}⚫] {disp_a}".ljust(left_pad)
                        o_ln += 1
                    else:
                        left = " " * left_pad
                    if k < len(b):
                        lb = b[k]
                        disp_b = lb if len(lb) <= max_right else lb[:max_right-3] + '...'
                        right = f"[{n_ln:4}➕] {disp_b}"
                        n_ln += 1
                    else:
                        right = " " * max_right
                    lines.append(f"{left} | {right}")
        return "\n".join(lines) + "\n"

    def _is_section_format(self, output: str) -> bool:
        return bool(self.section_pattern.search(output))

    def _is_json_format(self, output: str) -> bool:
        s = output.strip()
        if not (s.startswith('{') or s.startswith('[')): return False
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
        if not s.startswith('<'): return False
        try:
            root = ET.fromstring(s)
            return root.tag == 'files' and len(root) and root[0].tag == 'file'
        except:
            return False

    def _is_md_fenced_format(self, output: str) -> bool:
        return bool(self.md_fenced_pattern.search(output))

    def _parse_section_format(self, output: str) -> List[Dict[str, Union[str, int]]]:
        matches = list(self.section_pattern.finditer(output))
        if not matches: return []
        sections: List[Dict[str, Union[str, int]]] = []
        for m in matches:
            clean = m.group(1).strip().strip('\'"`')
            fn = Path(clean).name
            sections.append({'filename': fn, 'content': ''})
        for idx, m in enumerate(matches):
            start = m.end()
            end = matches[idx+1].start() if idx+1 < len(matches) else len(output)
            chunk = output[start:end]
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
        matches = self.md_fenced_pattern.findall(output)
        parsed_objects = []
        for info, content in matches:
            filename = info.strip() if info else "unnamed"
            if not self._validate_filename(filename):
                logger.warning(f"Invalid filename: {filename}, skipping")
                continue
            parsed_objects.append({'filename': filename, 'content': content.strip()})
        logger.info(f"Parsed {len(parsed_objects)} files from Markdown fenced format")
        return parsed_objects

    def _parse_generic_format(self, output: str) -> List[Dict[str, Union[str, int]]]:
        lines = output.split('\n')
        parsed_objects = []
        current_filename = None
        content_lines = []
        for line in lines:
            match = self.filename_pattern.match(line)
            if match:
                if current_filename and content_lines:
                    content = '\n'.join(content_lines).strip()
                    if self._validate_filename(current_filename):
                        parsed_objects.append({'filename': current_filename, 'content': content})
                    content_lines = []
                current_filename = match.group(1).strip()
                content_lines.append(match.group(2).strip())
            elif current_filename and line.strip():
                content_lines.append(line.strip())
        if current_filename and content_lines:
            content = '\n'.join(content_lines).strip()
            if self._validate_filename(current_filename):
                parsed_objects.append({'filename': current_filename, 'content': content})
        if not parsed_objects:
            raise ParsingError("No valid files found in generic parsing")
        logger.info("Parsed %d files from generic format", len(parsed_objects))
        return parsed_objects

    def _parse_fallback(self, output: str) -> List[Dict[str, Union[str, int]]]:
        logger.warning("Using fallback parser - treating output as single file")
        return [{'filename': 'generated.txt', 'content': output.strip()}]

    def _validate_filename(self, filename: str) -> bool:
        if not filename or len(filename) > 255:
            return False
        invalid_chars = ['<>:"/\\|?*']
        for char in invalid_chars:
            if char in filename:
                return False
        if '..' in filename or filename.startswith('/'):
            return False
        return True

# original file length: 558 lines
# updated file length: 553 lines