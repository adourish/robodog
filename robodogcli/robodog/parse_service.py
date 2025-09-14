# filename:         robodog/parse_service.py
# originalfilename: robodog/parse_service.py
# matchedfilename:  C:\Projects\robodog\robodogcli\robodog\parse_service.py
# original file length: 288 lines
# updated file length:  311 lines
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
        self.md_fenced_pattern = re.compile(r'```([^\n]*)\n(.*?)\n```', re.DOTALL)
        self.filename_pattern = re.compile(r'^([^:]+):\s*(.*)$', re.MULTILINE)

    def parse_llm_output(
        self,
        llm_output: str,
        base_dir: Optional[str] = None,
        file_service: Optional[object] = None
    ) -> List[Dict[str, Union[str, int]]]:
        """
        Parse LLM output into objects with metadata:
            'filename', 'originalfilename', 'matchedfilename',
            'content', 'originalcontent', 'diff',
            'new_tokens', 'original_tokens', 'delta_tokens'
        Also writes each diff to an out/ folder under base_dir (or cwd).
        """
        logger.info(f"Starting parse of LLM output ({len(llm_output)} chars) with base_dir: {base_dir}")
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

        # Enhance metadata and prepare diffs
        for obj in parsed_objects:
            self._enhance_parsed_object(obj, base_dir, file_service)

        # Write diff outputs to out/ folder
        out_root = Path(base_dir) if base_dir else Path.cwd()
        out_dir = out_root / 'out'
        try:
            out_dir.mkdir(parents=True, exist_ok=True)
        except Exception as e:
            logger.warning(f"Could not create out directory {out_dir}: {e}")
        ts = datetime.utcnow().strftime("%Y%m%d%H%M%S")
        for obj in parsed_objects:
            diff_text = obj.get('diff', '')
            if diff_text:
                orig_fn = obj.get('filename', 'file')
                stem = Path(orig_fn).stem
                suffix = Path(orig_fn).suffix or ''
                diff_name = f"diff-{stem}-{ts}{suffix}"
                diff_path = out_dir / diff_name
                try:
                    if file_service:
                        file_service.write_file(diff_path, diff_text)
                    else:
                        diff_path.write_text(diff_text, encoding='utf-8')
                    logger.info(f"Wrote diff to {diff_path}")
                except Exception as e:
                    logger.error(f"Failed to write diff file {diff_path}: {e}")

        return parsed_objects

    def _enhance_parsed_object(
        self,
        obj: Dict[str, Union[str, int]],
        base_dir: Optional[str],
        file_service: Optional[object]
    ):
        """
        Enhance the parsed object with:
          - 'originalfilename'
          - 'matchedfilename'
          - 'originalcontent'
          - 'diff'
          - 'new_tokens', 'original_tokens', 'delta_tokens'
        """
        filename    = obj.get('filename', '')
        new_content = obj.get('content', '')
        matched     = None
        original    = ''
        diff_text   = ''

        # Attempt to resolve via file_service
        if file_service:
            try:
                candidate = file_service.resolve_path(filename)
                if candidate and candidate.exists():
                    matched = str(candidate.resolve())
                    original = candidate.read_text(encoding='utf-8', errors='ignore')
                    diff_text = '\n'.join(
                        difflib.unified_diff(
                            original.splitlines(keepends=True),
                            new_content.splitlines(keepends=True),
                            fromfile=f'original/{filename}',
                            tofile=f'updated/{Path(matched).name}',
                            lineterm=''
                        )
                    )
            except Exception as e:
                logger.debug(f"resolve_path failed for {filename}: {e}")

        # Fallback to base_dir lookup
        if matched is None and base_dir:
            try:
                candidate = Path(base_dir) / filename
                if candidate.exists():
                    matched = str(candidate.resolve())
                    original = candidate.read_text(encoding='utf-8', errors='ignore')
                    diff_text = '\n'.join(
                        difflib.unified_diff(
                            original.splitlines(keepends=True),
                            new_content.splitlines(keepends=True),
                            fromfile=f'original/{filename}',
                            tofile=f'updated/{filename}',
                            lineterm=''
                        )
                    )
            except Exception as e:
                logger.debug(f"Base_dir lookup failed for {filename}: {e}")

        # Compute lines and tokens
        orig_lines = original.count('\n') + (1 if original else 0)
        new_lines  = new_content.count('\n') + (1 if new_content else 0)
        new_tokens = len(new_content.split())
        original_tokens = len(original.split()) if original else 0
        delta_tokens = new_tokens - original_tokens

        # Build metadata comments
        length_comment = (
            f"# original file length: {orig_lines} lines\n"
            f"# updated file length:  {new_lines} lines\n"
        )
        filename_meta = (
            f"# filename:         {filename}\n"
            f"# originalfilename: {filename}\n"
            f"# matchedfilename:  {matched}\n"
        )

        # Overwrite content and attach metadata
        obj['content']           = filename_meta + length_comment + new_content
        obj['originalfilename']  = filename
        obj['matchedfilename']   = matched
        obj['originalcontent']   = original
        obj['diff']              = diff_text
        obj['new_tokens']        = new_tokens
        obj['original_tokens']   = original_tokens
        obj['delta_tokens']      = delta_tokens
        obj['_tokens']           = new_tokens  # legacy

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
        matches = list(self.section_pattern.finditer(output))
        objs = []
        for idx, match in enumerate(matches):
            fn = match.group(1).strip()
            start = match.end()
            end = matches[idx+1].start() if idx+1 < len(matches) else len(output)
            content = output[start:end].strip()
            objs.append({'filename': fn, 'content': content})
        return objs

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
        parsed = []
        for info, content in matches:
            fn = info.strip() or "unnamed"
            if self._validate_filename(fn):
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
                if cur_fn and buf and self._validate_filename(cur_fn):
                    parsed.append({'filename': cur_fn, 'content': '\n'.join(buf).strip()})
                cur_fn = m.group(1).strip()
                buf = [m.group(2).strip()]
            elif cur_fn and line.strip():
                buf.append(line.strip())
        if cur_fn and buf and self._validate_filename(cur_fn):
            parsed.append({'filename': cur_fn, 'content': '\n'.join(buf).strip()})
        if not parsed:
            raise ParsingError("No valid files in generic parse")
        return parsed

    def _parse_fallback(self, output: str) -> List[Dict[str, Union[str, int]]]:
        logger.warning("Using fallback parser")
        return [{'filename': 'generated.txt', 'content': output.strip()}]

    def _validate_filename(self, filename: str) -> bool:
        if not filename or len(filename) > 255:
            return False
        for c in '<>:"/\\|?*':
            if c in filename:
                return False
        if '..' in filename or filename.startswith('/'):
            return False
        return True

# original file length: 308 lines
# updated file length: 335 lines