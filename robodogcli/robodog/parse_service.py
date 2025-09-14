# filename:         robodog/parse_service.py
# originalfilename: robodog/parse_service.py
# matchedfilename:  C:\Projects\robodog\robodogcli\robodog\parse_service.py
# original file length: 295 lines
# updated file length:  309 lines
# filename:         c:\projects\robodog\robodogcli\robodog\parse_service.py
# originalfilename: c:\projects\robodog\robodogcli\robodog\parse_service.py
# matchedfilename:  C:\Projects\robodog\robodogcli\robodog\parse_service.py
# original file length: 292 lines
# updated file length:  450 lines
#!/usr/bin/env python3
"""Parse various LLM output formats into file objects with enhanced metadata."""
import re
import json
import yaml
import xml.etree.ElementTree as ET
from typing import List, Dict, Tuple, Optional, Union
import logging
import difflib
from pathlib import Path

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
            'content', 'originalcontent', 'diff', 'tokens'
        Parse LLM output into objects with metadata:
            'filename', 'originalfilename', 'matchedfilename',
            'content', 'originalcontent', 'diff', 'new_tokens', 'original_tokens', 'delta_tokens'
        """
        logger.info(f"Starting parse of LLM output ({len(llm_output)} chars) with base_dir: {base_dir}")
        try:
            if self._is_section_format(llm_output):
                logger.debug("Detected section format")
                parsed_objects = self._parse_section_format(llm_output)
            elif self._is_json_format(llm_output):
                logger.debug("Detected JSON format")
                parsed_objects = self._parse_json_format(llm_output)
            elif self._is_yaml_format(llm_output):
                logger.debug("Detected YAML format")
                parsed_objects = self._parse_yaml_format(llm_output)
            elif self._is_xml_format(llm_output):
                logger.debug("Detected XML format")
                parsed_objects = self._parse_xml_format(llm_output)
            elif self._is_md_fenced_format(llm_output):
                logger.debug("Detected Markdown fenced format")
                parsed_objects = self._parse_md_fenced_format(llm_output)
            else:
                logger.info("No specific format detected, trying generic parsing")
                parsed_objects = self._parse_generic_format(llm_output)
        except Exception as e:
            logger.error(f"Parsing error: {e}")
            try:
                parsed_objects = self._parse_fallback(llm_output)
            except Exception as fallback_e:
                logger.error(f"Fallback parsing also failed: {fallback_e}")
                raise ParsingError(f"Could not parse LLM output: {e}")

        for obj in parsed_objects:
            self._enhance_parsed_object(obj, base_dir, file_service)

        return parsed_objects

    def _enhance_parsed_object(
        self,
        obj: Dict[str, Union[str, int]],
        base_dir: Optional[str],
        file_service: Optional[object]
    ):
        """
        Enhance the parsed object with:
          - originalfilename
          - matchedfilename (via file_service.resolve_path validation)
          - originalcontent
          - diff (comparing new content with content from matchedfilename)
        """
        filename    = obj.get('filename', '')
        new_content = obj.get('content', '')
        matched     = None
        original    = ''
        diff_text   = ''

        # Resolve the filename using file_service.resolve_path to validate and find real location
        if file_service:
            try:
                candidate = file_service.resolve_path(filename)
                if candidate and candidate.exists():
                    matched = str(candidate.resolve())  # Set matchedfilename to the resolved full path
                    original = candidate.read_text(encoding='utf-8', errors='ignore')  # Read content from matchedfilename for comparison
                    # Compare new content with original content from matchedfilename
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

        # Fallback to base_dir lookup if resolve_path didn't find it
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

        # Compute line-counts for metadata
        orig_lines = original.count('\n') + (1 if original else 0)
        new_lines  = new_content.count('\n') + (1 if new_content else 0)

        # Compute word counts and delta word counts
        new_word_count = len(new_content.split())
        original_word_count = len(original.split()) if original else 0
        delta_word_count = new_word_count - original_word_count

        # Build metadata comments including filename resolution
        length_comment = (
            f"# original file length: {orig_lines} lines\n"
            f"# updated file length:  {new_lines} lines\n"
        )
        filename_meta = (
            f"# filename:         {filename}\n"  # Includes filename
            f"# originalfilename: {filename}\n"  # Includes originalfilename
            f"# matchedfilename:  {matched}\n"   # Includes matched filename (resolved real location)
        )

        # Overwrite object's content with metadata, length comments, and new content
        obj['content']          = filename_meta + length_comment + new_content
        obj['originalfilename'] = filename  # Includes originalfilename
        obj['matchedfilename']  = matched   # Includes matchedfilename (real validated location)
        obj['originalcontent']  = original  # Content for comparison
        obj['diff']             = diff_text # Diff from comparison
        obj['new_tokens']       = new_word_count
        obj['original_tokens']  = original_word_count
        obj['delta_tokens']     = delta_word_count
        obj['_tokens']          = new_word_count  # Legacy 'tokens' for compatibility

    def _is_section_format(self, output: str) -> bool:
        return bool(self.section_pattern.search(output))

    def _is_json_format(self, output: str) -> bool:
        stripped = output.strip()
        if not stripped.startswith('{') and not stripped.startswith('['):
            return False
        try:
            parsed = json.loads(stripped)
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
        stripped = output.strip()
        if not stripped.startswith('<'):
            return False
        try:
            root = ET.fromstring(stripped)
            return root.tag == 'files' and len(root) > 0 and root[0].tag == 'file'
        except:
            return False

    def _is_md_fenced_format(self, output: str) -> bool:
        return bool(self.md_fenced_pattern.search(output))

    def _parse_section_format(self, output: str) -> List[Dict[str, Union[str, int]]]:
        matches = list(self.section_pattern.finditer(output))
        parsed_objects = []
        for i, match in enumerate(matches):
            filename = match.group(1).strip()
            start = match.end()
            end = matches[i+1].start() if i+1 < len(matches) else len(output)
            content = output[start:end].strip()
            parsed_objects.append({'filename': filename, 'content': content})
        logger.info(f"Parsed {len(parsed_objects)} from section format")
        return parsed_objects

    def _parse_json_format(self, output: str) -> List[Dict[str, Union[str, int]]]:
        data = json.loads(output.strip())
        files = data.get('files', [])
        if not isinstance(files, list):
            raise ParsingError("JSON 'files' must be list")
        parsed = []
        for item in files:
            fn = item.get('filename','').strip()
            ct = item.get('content','').strip()
            if self._validate_filename(fn):
                parsed.append({'filename': fn, 'content': ct})
        logger.info(f"Parsed {len(parsed)} from JSON")
        return parsed

    def _parse_yaml_format(self, output: str) -> List[Dict[str, Union[str, int]]]:
        data = yaml.safe_load(output)
        files = data.get('files', [])
        if not isinstance(files, list):
            raise ParsingError("YAML 'files' must be list")
        parsed = []
        for item in files:
            fn = item.get('filename','').strip()
            ct = item.get('content','').strip()
            if self._validate_filename(fn):
                parsed.append({'filename': fn, 'content': ct})
        logger.info(f"Parsed {len(parsed)} from YAML")
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
        logger.info(f"Parsed {len(parsed)} from XML")
        return parsed

    def _parse_md_fenced_format(self, output: str) -> List[Dict[str, Union[str, int]]]:
        matches = self.md_fenced_pattern.findall(output)
        parsed = []
        for info, content in matches:
            fn = info.strip() or "unnamed"
            if self._validate_filename(fn):
                parsed.append({'filename': fn, 'content': content.strip()})
        logger.info(f"Parsed {len(parsed)} from Markdown fences")
        return parsed

    def _parse_generic_format(self, output: str) -> List[Dict[str, Union[str, int]]]:
        lines = output.splitlines()
        parsed = []
        current_fn = None
        buf = []
        for line in lines:
            m = self.filename_pattern.match(line)
            if m:
                if current_fn and buf and self._validate_filename(current_fn):
                    parsed.append({'filename': current_fn, 'content': '\n'.join(buf).strip()})
                current_fn = m.group(1).strip()
                buf = [m.group(2).strip()]
            elif current_fn and line.strip():
                buf.append(line.strip())
        if current_fn and buf and self._validate_filename(current_fn):
            parsed.append({'filename': current_fn, 'content': '\n'.join(buf).strip()})
        if not parsed:
            raise ParsingError("No valid files in generic parse")
        logger.info(f"Parsed {len(parsed)} from generic format")
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

