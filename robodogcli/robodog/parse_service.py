# file: C:\Projects\robodog\robodogcli\robodog\parse_service.py
# filename: robodog/parse_service.py
# original file length: 370 lines
# updated file length: 342 lines
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
        self.section_pattern = re.compile(r'^#\s*file:\s*(.+)$', re.MULTILINE | re.IGNORECASE)
        self.md_fenced_pattern = re.compile(r'```([^\^\n]*)\n(.*?)\n```', re.DOTALL)
        self.filename_pattern = re.compile(r'^([^:]+):\s*(.*)$', re.MULTILINE)

    def parse_llm_output(
        self,
        llm_output: str,
        base_dir: Optional[str] = None,
        file_service: Optional[object] = None,
        ai_out_path: str = ''
    ) -> List[Dict[str, Union[str, int]]]:
        """
        Parse LLM output into objects with enhanced metadata for better readability and tracking:
            'filename', 'originalfilename', 'matchedfilename',
            'content', 'originalcontent', 'diff_md' (improved markdown extension for easier reading),
            'new_tokens', 'original_tokens', 'delta_tokens'
        Also writes each improved diff as a compact markdown file to an out/ folder.
        """
        logger.info(f"Starting enhanced parse of LLM output ({len(llm_output)} chars) with base_dir: {base_dir} and ai_out_path: {ai_out_path}")
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

        # Enhance metadata for better tracking
        for obj in parsed_objects:
            self._enhance_parsed_object(obj, base_dir, file_service)

        # Write enhanced compact markdown diff files to out/ folder based on ai_out_path or base_dir
        if ai_out_path:
            out_root = Path(ai_out_path).parent
        elif base_dir:
            out_root = Path(base_dir)
        else:
            out_root = Path.cwd()
        out_dir = out_root / 'diffoutput'
        try:
            out_dir.mkdir(parents=True, exist_ok=True)
        except Exception as e:
            logger.warning(f"Could not create out directory {out_dir}: {e}")
        ts = datetime.utcnow().strftime("%Y%m%d-%H%M-%S")
        for obj in parsed_objects:
            md_diff = obj.get('diff_md', '')
            if md_diff:
                orig_fn = obj.get('filename', 'file')
                stem = Path(orig_fn).stem
                suffix = Path(orig_fn).suffix or ''
                diff_name = f"diff-{stem}-{ts}{suffix}.md"
                diff_path = out_dir / diff_name
                try:
                    with open(diff_path, 'w', encoding='utf-8') as f:
                        f.write(md_diff)
                    logger.info(f"Wrote enhanced markdown diff to {diff_path}")
                except Exception as e:
                    logger.error(f"Failed to write enhanced markdown diff file {diff_path}: {e}")

        return parsed_objects

    def _enhance_parsed_object(
        self,
        obj: Dict[str, Union[str, int]],
        base_dir: Optional[str],
        file_service: Optional[object]
    ):
        """
        Enhance the parsed object with tracking metadata and improved diffs:
          - 'filename', 'originalfilename', 'matchedfilename'
          - 'diff_md' (enhanced with markdown/HTML for colors and emojis)
          - 'new_tokens', 'original_tokens', 'delta_tokens'
        """
        filename = obj.get('filename', '')
        new_content = obj.get('content', '')
        matched = None
        original = ''
        diff_md = ''

        # Resolve via file_service for accurate matching
        if file_service:
            try:
                candidate = file_service.resolve_path(filename)
                if candidate and candidate.exists():
                    matched = str(candidate.resolve())
                    original = candidate.read_text(encoding='utf-8', errors='ignore')
                    diff_md = self._generate_improved_md_diff(filename, original, new_content, matched)
            except Exception as e:
                logger.debug(f"resolve_path failed for {filename}: {e}")

        # Fallback to base_dir lookup
        if matched is None and base_dir:
            try:
                candidate = Path(base_dir) / filename
                if candidate.exists():
                    matched = str(candidate.resolve())
                    original = candidate.read_text(encoding='utf-8', errors='ignore')
                    diff_md = self._generate_improved_md_diff(filename, original, new_content, matched)
            except Exception as e:
                logger.debug(f"Base_dir lookup failed for {filename}: {e}")

        orig_lines = original.count('\n') + (1 if original else 0)
        new_lines = new_content.count('\n') + (1 if new_content else 0)
        new_tokens = len(new_content.split())
        original_tokens = len(original.split()) if original else 0
        delta_tokens = new_tokens - original_tokens

        # Enhanced metadata for tracking
        length_comment = (
            f"# original file length: {orig_lines} lines\n"
            f"# updated file length: {new_lines} lines\n"
        )
        filename_meta = (
            f"# file: {matched or filename}\n"
            f"# filename: {filename}\n"
            f"# originalfilename: {filename}\n"
            f"# matchedfilename: {matched}\n"
        )
        # Prepend metadata to content for consistency
        obj['content'] = filename_meta + length_comment + new_content
        obj['originalcontent'] = original
        obj['diff_md'] = diff_md
        obj['new_tokens'] = new_tokens
        obj['original_tokens'] = original_tokens
        obj['delta_tokens'] = delta_tokens
        obj['_tokens'] = new_tokens  # Legacy

    def _generate_improved_md_diff(self, filename: str, original: str, updated: str, matched: str) -> str:
        """
        Generate improved markdown diff with emojis, line numbers, and icons:
        - 🗂️ for file headers (---/+++)
        - 🧩 for hunk headers (@@)
        - [ lineNo⚫/➕/⚪ ] for removed/added/unchanged lines
        """
        orig_lines = original.splitlines()
        updt_lines = updated.splitlines()

        unified = list(difflib.unified_diff(
            orig_lines, updt_lines,
            fromfile=f'🔵 Original: {filename}',
            tofile=f'🔴 Updated: {filename} (matched: {matched})',
            lineterm='', n=7
        ))

        md_lines = []
        md_lines.append(f"# 📊 Enhanced Diff for {filename}")
        md_lines.append(f"**File Path:** {matched or filename}")
        md_lines.append(f"**Change Timestamp:** {datetime.utcnow().isoformat()}")
        md_lines.append("")
        md_lines.append("## 🔍 Unified Diff (With Emojis & Line Numbers)")
        md_lines.append("```diff")
        for idx, line in enumerate(unified, start=1):
            if line.startswith('---') or line.startswith('+++'):
                md_lines.append(f"🗂️ **{line}**")
            elif line.startswith('@@'):
                md_lines.append(f"🧩 **{line}**")
            else:
                prefix_char = line[0] if line else ' '
                emoji = '⚪'
                if prefix_char == '-':
                    emoji = '⚫'
                elif prefix_char == '+':
                    emoji = '➕'
                content = line[1:] if prefix_char in ('-','+',' ') else line
                md_lines.append(f"[{idx:4}{emoji}] {content}")
        md_lines.append("```")
        return "\n".join(md_lines) + "\n"


    def _generate_improved_md_diffb(self, filename: str, original: str, updated: str, matched: str) -> str:
        """
        Generate improved markdown diff with better readability:
        - Use HTML <font> tags for colors (as markdown doesn't support native colors)
        - Add emoji for unchanged rows (○ for unchanged, ⚫ for - and +)
        - Use plain text instead of problem ASCII codes for better visibility
        - Enhanced side-by-side using markdown table
        """
        orig_lines = original.splitlines()
        updt_lines = updated.splitlines()

        unified = list(difflib.unified_diff(
            orig_lines, updt_lines,
            fromfile=f'🔵 Original: {filename}',
            tofile=f'🔴 Updated: {filename} (matched: {matched})',
            lineterm='', n=7
        ))

        md_lines = []
        md_lines.append(f"# 📊 Enhanced Diff for {filename}")
        md_lines.append(f"**File Path:** {matched or filename}")
        md_lines.append(f"**Change Timestamp:** {datetime.utcnow().isoformat()}")
        md_lines.append("")
        md_lines.append("## 🔍 Unified Diff (Improved Readability)")
        md_lines.append("```diff")
        for line in unified:
            if line.startswith('---') or line.startswith('+++'):
                md_lines.append(f"**{line}**")
            elif line.startswith('-'):
                md_lines.append(f"<font color='red'>⚫ {line[1:]}</font>")
            elif line.startswith('+'):
                md_lines.append(f"<font color='green'>➕ {line[1:]}</font>")
            elif line.startswith(' '):
                md_lines.append(f"○ {line[1:]}")
            else:
                md_lines.append(line)
        md_lines.append("```")
        md_lines.append("")
        md_lines.append("## 📋 Markdown Side-by-Side Diff")
        md_lines.append("| Change Type | Original Content | Updated Content |")
        md_lines.append("|-------------|------------------|-----------------|")
        md_lines.extend(self._parse_unified_to_table_enhanced(unified))
        md_lines.append("")
        md_lines.append("Legend: ⚫ Removed, ➕ Added, ○ Unchanged")
        return "\n".join(md_lines) + "\n"

    def _parse_unified_to_table_enhanced(self, unified: List[str]) -> List[str]:
        rows = []
        for line in unified:
            if line.startswith('-'):
                orig = line[1:]
                rows.append(f"| <font color='red'>⚫ Modified</font> | `{orig}` | (removed) |")
            elif line.startswith('+'):
                up = line[1:]
                rows.append(f"| <font color='green'>➕ Modified</font> | (new) | `{up}` |")
            elif line.startswith(' '):
                unch = line[1:]
                rows.append(f"| ○ Unchanged | `{unch}` | `{unch}` |")
        return rows

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
            return root.tag == 'files' and any(child.tag == 'file' for child in root)
        except:
            return False

    def _is_md_fenced_format(self, output: str) -> bool:
        return bool(self.md_fenced_pattern.search(output))

    def _parse_section_format(self, output: str) -> List[Dict[str, Union[str, int]]]:
        matches = list(self.section_pattern.finditer(output))
        objs = []
        for idx, m in enumerate(matches):
            fn = m.group(1).strip()
            start = m.end()
            end = matches[idx+1].start() if idx+1 < len(matches) else len(output)
            content = output[start:end].strip()
            objs.append({'filename': fn, 'content': content})
        return objs

    def _parse_json_format(self, output: str) -> List[Dict[str, Union[str, int]]]:
        data = json.loads(output)
        files = data.get('files', [])
        if not isinstance(files, list):
            raise ParsingError("JSON 'files' must be list")
        parsed = []
        for it in files:
            fn = it.get('filename','').strip()
            ct = it.get('content','').strip()
            if fn:
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
            if fn:
                parsed.append({'filename': fn, 'content': ct})
        return parsed

    def _parse_xml_format(self, output: str) -> List[Dict[str, Union[str, int]]]:
        root = ET.fromstring(output)
        if root.tag != 'files':
            raise ParsingError("Root must be 'files'")
        parsed = []
        for fe in root.findall('file'):
            fn_el = fe.find('filename')
            ct_el = fe.find('content')
            if fn_el is not None and ct_el is not None:
                fn = (fn_el.text or '').strip()
                ct = (ct_el.text or '').strip()
                if fn:
                    parsed.append({'filename': fn, 'content': ct})
        return parsed

    def _parse_md_fenced_format(self, output: str) -> List[Dict[str, Union[str, int]]]:
        matches = self.md_fenced_pattern.findall(output)
        parsed = []
        for info, content in matches:
            fn = info.strip() or "unnamed"
            parsed.append({'filename': fn, 'content': content.strip()})
        return parsed

    def _parse_generic_format(self, output: str) -> List[Dict[str, Union[str, int]]]:
        lines = output.splitlines()
        parsed = []
        cur_fn = None
        buf = []
        for line in lines:
            m = self.filename_pattern.match(line)
            if m:
                if cur_fn and buf:
                    parsed.append({'filename': cur_fn, 'content': '\n'.join(buf).strip()})
                cur_fn = m.group(1).strip()
                buf = [m.group(2).strip()]
            elif cur_fn:
                buf.append(line.strip())
        if cur_fn and buf:
            parsed.append({'filename': cur_fn, 'content': '\n'.join(buf).strip()})
        if not parsed:
            raise ParsingError("No valid files in generic parse")
        return parsed

    def _parse_fallback(self, output: str) -> List[Dict[str, Union[str, int]]]:
        logger.warning("Using fallback parser")
        return [{'filename': 'generated.txt', 'content': output.strip()}]
# original file length: 401 lines
# updated file length: 424 lines