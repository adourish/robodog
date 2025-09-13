
# file: robodog/parse_service.py
#!/usr/bin/env python3
import re
import json
import yaml
import xml.etree.ElementTree as ET
from typing import List, Dict, Tuple, Optional
from pathlib import Path
import logging

logger = logging.getLogger(__name__)

class ParsingError(Exception):
    """Custom exception for parsing errors."""
    pass

class ParseService:
    def __init__(self):
        # Regex patterns for different formats
        self.section_pattern = re.compile(r'^#\s*file:\s*(.+)$', re.MULTILINE | re.IGNORECASE)
        self.md_fenced_pattern = re.compile(r'```([^\n]*)\n(.*?)\n```', re.DOTALL)
        self.filename_pattern = re.compile(r'^([^:]+):\s*(.*)$', re.MULTILINE)

    def parse_llm_output(self, llm_output: str) -> List[Dict[str, str]]:
        """
        Parse LLM output into a list of objects, each with 'filename' and 'content'.
        
        Supports multiple formats with error handling.
        
        Returns:
            List of dicts: [{'filename': str, 'content': str, 'tokens': int}]
            
        Raises:
            ParsingError: If no valid content could be parsed
        """
        logger.info(f"Starting parse of LLM output ({len(llm_output)} chars)")

        try:
            # Try formats in order of most common/reliable
            if self._is_section_format(llm_output):
                logger.debug("Detected section format")
                return self._parse_section_format(llm_output)
            elif self._is_json_format(llm_output):
                logger.debug("Detected JSON format")
                return self._parse_json_format(llm_output)
            elif self._is_yaml_format(llm_output):
                logger.debug("Detected YAML format")
                return self._parse_yaml_format(llm_output)
            elif self._is_xml_format(llm_output):
                logger.debug("Detected XML format")
                return self._parse_xml_format(llm_output)
            elif self._is_md_fenced_format(llm_output):
                logger.debug("Detected Markdown fenced format")
                return self._parse_md_fenced_format(llm_output)
            else:
                logger.info("No specific format detected, trying generic parsing")
                return self._parse_generic_format(llm_output)
        except Exception as e:
            logger.error(f"Parsing error: {e}")
            # Fallback to best-effort parsing
            try:
                return self._parse_fallback(llm_output)
            except Exception as fallback_e:
                logger.error(f"Fallback parsing also failed: {fallback_e}")
                raise ParsingError(f"Could not parse LLM output: {e}")

    def _is_section_format(self, output: str) -> bool:
        """Check if output follows # file: <filename> format."""
        return bool(self.section_pattern.search(output))

    def _is_json_format(self, output: str) -> bool:
        """Check if output is valid JSON with expected structure."""
        stripped = output.strip()
        if not stripped.startswith('{') and not stripped.startswith('['):
            return False
        try:
            parsed = json.loads(stripped)
            return isinstance(parsed, dict) and 'files' in parsed
        except (json.JSONDecodeError, TypeError):
            return False

    def _is_yaml_format(self, output: str) -> bool:
        """Check if output is valid YAML with expected structure."""
        try:
            parsed = yaml.safe_load(output)
            return isinstance(parsed, dict) and 'files' in parsed
        except (yaml.YAMLError, TypeError):
            return False

    def _is_xml_format(self, output: str) -> bool:
        """Check if output is valid XML with files structure."""
        stripped = output.strip()
        if not stripped.startswith('<'):
            return False
        try:
            root = ET.fromstring(stripped)
            return root.tag == 'files' and len(root) > 0 and root[0].tag == 'file'
        except ET.ParseError:
            return False

    def _is_md_fenced_format(self, output: str) -> bool:
        """Check if output contains Markdown fenced code blocks."""
        return bool(self.md_fenced_pattern.search(output))

    def _parse_section_format(self, output: str) -> List[Dict[str, str]]:
        """Parse # file: <filename> format."""
        matches = list(self.section_pattern.finditer(output))
        parsed_objects = []
        
        for i, match in enumerate(matches):
            filename = match.group(1).strip()
            if not filename:
                logger.warning(f"Empty filename at match {i}, skipping")
                continue
                
            start_pos = match.end()
            end_pos = matches[i + 1].start() if i + 1 < len(matches) else len(output)
            
            content = output[start_pos:end_pos].strip()
            
            # Validate content
            if not self._validate_filename(filename):
                logger.warning(f"Invalid filename: {filename}, skipping")
                continue
                
            parsed_objects.append({
                'filename': filename,
                'content': content,
                'tokens': len(content.split())
            })
        
        logger.info(f"Parsed {len(parsed_objects)} files from section format")
        return parsed_objects

    def _parse_json_format(self, output: str) -> List[Dict[str, str]]:
        """Parse JSON format: {"files": [...]}"""
        parsed = json.loads(output.strip())
        files = parsed.get('files', [])
        
        if not isinstance(files, list):
            raise ParsingError("JSON 'files' field must be an array")
        
        parsed_objects = []
        for item in files:
            filename = item.get('filename', '').strip()
            content = item.get('content', '').strip()
            
            if not self._validate_filename(filename):
                logger.warning(f"Invalid filename: {filename}, skipping")
                continue
                
            parsed_objects.append({
                'filename': filename,
                'content': content,
                'tokens': len(content.split())
            })
        
        logger.info(f"Parsed {len(parsed_objects)} files from JSON format")
        return parsed_objects

    def _parse_yaml_format(self, output: str) -> List[Dict[str, str]]:
        """Parse YAML format: files:\n  - filename: ...\n    content: ..."""
        parsed = yaml.safe_load(output)
        files = parsed.get('files', [])
        
        if not isinstance(files, list):
            raise ParsingError("YAML 'files' field must be a list")
        
        parsed_objects = []
        for item in files:
            filename = item.get('filename', '').strip()
            content = item.get('content', '').strip()
            
            if not self._validate_filename(filename):
                logger.warning(f"Invalid filename: {filename}, skipping")
                continue
                
            parsed_objects.append({
                'filename': filename,
                'content': content,
                'tokens': len(content.split())
            })
        
        logger.info(f"Parsed {len(parsed_objects)} files from YAML format")
        return parsed_objects

    def _parse_xml_format(self, output: str) -> List[Dict[str, str]]:
        """Parse XML format: <files><file>...</file></files>"""
        root = ET.fromstring(output.strip())
        
        if root.tag != 'files':
            raise ParsingError("Root element must be 'files'")
        
        parsed_objects = []
        for file_elem in root.findall('file'):
            filename_elem = file_elem.find('filename')
            content_elem = file_elem.find('content')
            
            if filename_elem is None or content_elem is None:
                continue
                
            filename = filename_elem.text.strip() if filename_elem.text else ''
            content = content_elem.text.strip() if content_elem.text else ''
            
            if not self._validate_filename(filename):
                logger.warning(f"Invalid filename: {filename}, skipping")
                continue
                
            parsed_objects.append({
                'filename': filename,
                'content': content,
                'tokens': len(content.split())
            })
        
        logger.info(f"Parsed {len(parsed_objects)} files from XML format")
        return parsed_objects

    def _parse_md_fenced_format(self, output: str) -> List[Dict[str, str]]:
        """Parse Markdown fenced code blocks."""
        matches = self.md_fenced_pattern.findall(output)
        parsed_objects = []
        
        for info, content in matches:
            filename = info.strip() if info else "unnamed"
            
            if not self._validate_filename(filename):
                logger.warning(f"Invalid filename: {filename}, skipping")
                continue
                
            parsed_objects.append({
                'filename': filename,
                'content': content.strip(),
                'tokens': len(content.split())
            })
        
        logger.info(f"Parsed {len(parsed_objects)} files from Markdown fenced format")
        return parsed_objects

    def _parse_generic_format(self, output: str) -> List[Dict[str, str]]:
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
                            'content': content,
                            'tokens': len(content.split())
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
                    'content': content,
                    'tokens': len(content.split())
                })
        
        if not parsed_objects:
            raise ParsingError("No valid files found in generic parsing")
        
        logger.info(f"Parsed {len(parsed_objects)} files from generic format")
        return parsed_objects

    def _parse_fallback(self, output: str) -> List[Dict[str, str]]:
        """Ultimate fallback: treat entire output as single file."""
        logger.warning("Using fallback parser - treating output as single file")
        return [{
            'filename': 'generated.txt',
            'content': output.strip(),
            'tokens': len(output.split())
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

    def write_parsed_files(self, parsed_objects: List[Dict[str, str]], base_dir: str = '.'):
        """
        Write parsed files to disk.
        
        Args:
            parsed_objects: List of file objects from parse_llm_output
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
                filepath.write_text(obj['content'], encoding='utf-8')
                success_count += 1
                logger.info(f"Written file: {filepath} ({obj['tokens']} tokens)")
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

# original file length: 256 lines
# updated file length: 256 lines
