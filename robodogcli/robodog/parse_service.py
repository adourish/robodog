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
        # detect "# file: <filename>" sections
        self.section_pattern = re.compile(r'^\s*#\s*file:\s*["`]?(.+?)["`]?\s*$', re.IGNORECASE | re.MULTILINE)
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
        """
        logger.debug(f"Starting parse of LLM output ({len(llm_output)} chars)")
        try:
            if self._is_section_format(llm_output):
                parsed = self._parse_section_format(llm_output)
            elif self._is_json_format(llm_output):
                parsed = self._parse_json_format(llm_output)
            elif self._is_yaml_format(llm_output):
                parsed = self._parse_yaml_format(llm_output)
            elif self._is_xml_format(llm_output):
                parsed = self._parse_xml_format(llm_output)
            elif self._is_md_fenced_format(llm_output):
                parsed = self._parse_md_fenced_format(llm_output)
            else:
                parsed = self._parse_generic_format(llm_output)
        except Exception as e:
            logger.error(f"Parsing error: {e}")
            try:
                parsed = self._parse_fallback(llm_output)
            except Exception as fe:
                logger.error(f"Fallback parsing also failed: {fe}")
                raise ParsingError(f"Could not parse LLM output: {e}")

        # enhance each parsed object
        for obj in parsed:
            self._enhance_parsed_object(obj, base_dir, file_service or self.file_service, task, svc)

        # ensure filename keys
        for obj in parsed:
            fn = obj.get('filename', '')
            obj['filename'] = fn
            obj.setdefault('originalfilename', fn)
            obj.setdefault('matchedfilename', fn)

        # mark new files
        for obj in parsed:
            matched = obj.get('matchedfilename', '')
            is_new = False
            if matched:
                try:
                    if not Path(matched).exists():
                        is_new = True
                except Exception:
                    is_new = True
            obj['new'] = is_new
            # append NEW to content directive if new
            content = obj.get('content','')
            if is_new and content.startswith("# file:"):
                header, _, rest = content.partition("\n")
                header += " NEW"
                obj['content'] = header + ("\n" + rest if rest else "")

        # write side-by-side diffs to disk using file_service if available
        if ai_out_path:
            out_root = Path(ai_out_path).parent
        elif base_dir:
            out_root = Path(base_dir)
        else:
            out_root = Path.cwd()
        diffdir = out_root / 'diffoutput'
        fs = file_service or self.file_service
        if fs:
            fs.ensure_dir(diffdir)
        else:
            logger.warning("No file_service available, skipping diff output writes.")
            # No fallback to direct writes; rely on file_service being injected
        ts = datetime.utcnow().strftime("%Y%m%d-%H%M-%S")
        for obj in parsed:
            sbs = obj.get('diff_sbs','')
            if not sbs:
                continue
            stem = Path(obj.get('filename','file')).stem
            suf  = Path(obj.get('filename','')).suffix or ''
            name = f"diff-sbs-{stem}-{ts}{suf}.md"
            path = diffdir / name
            try:
                if fs:
                    fs.write_file(path, sbs)
                    logger.debug(f"Saved side-by-side diff: {path}")
                else:
                    logger.warning(f"Skipping diff save for {path} due to missing file_service")
            except Exception as e:
                logger.error(f"Failed to save diff {path}: {e}")

        return parsed

    def _enhance_parsed_object(
        self,
        obj: Dict[str, Union[str,int]],
        base_dir: Optional[str],
        file_service: Optional[object],
        task: Union[Dict, List],
        svc: Optional[object]
    ):
        filename = obj.get('filename','')
        new_content = obj.get('content','')
        original_content = ''
        matched = filename
        diff_md = ''
        diff_sbs = ''
        # use file_service to locate and read original
        if file_service:
            try:
                include_spec = {}
                if isinstance(task, dict) and isinstance(task.get('include'), dict):
                    include_spec = task['include']
                else:
                    include_spec = {'pattern':'*','recursive':True}
                candidate = file_service.find_matching_file(filename, include_spec, svc)
                if candidate:
                    matched = str(candidate.resolve())
                    original_content = file_service.safe_read_file(candidate)
                    # generate diffs via diff_service
                    diff_md  = self.diff_service.generate_improved_md_diff(filename, original_content, new_content, matched)
                    diff_sbs = self.diff_service.generate_side_by_side_diff(filename, original_content, new_content, matched)
            except Exception as e:
                logger.error(f"Error enhancing {filename}: {e}")
        else:
            logger.warning(f"No file_service for parsing {filename}")

        # token metrics
        new_toks = len(new_content.split())
        orig_toks= len(original_content.split())
        delta    = new_toks - orig_toks
        change   = 0.0 if orig_toks==0 else abs(delta)/orig_toks*100
        long_compare = f"Compare: '{filename}' -> {matched} (o/n/d: {orig_toks}/{new_toks}/{delta}) change={change:.1f}%"
        short_compare = f"{filename} (o/n/d/c: {orig_toks}/{new_toks}/{delta}/{change:.1f}%)"
        logger.info(long_compare)
        obj.update({
            'originalfilename': filename,
            'matchedfilename': matched,
            'diff_md': diff_md,
            'diff_sbs': diff_sbs,
            'new_tokens': new_toks,
            'original_tokens': orig_toks,
            'delta_tokens': delta,
            'change': change,
            'originalcontent': f"# file: {filename}\n{original_content}",
            'completeness': self._check_content_completeness(new_content, filename),
            'long_compare': long_compare,
            'short_compare': short_compare,
            'result': self._result_code(change)
        })
        # normalize content directive
        obj['content'] = f"# file: {filename}\n{new_content}"

    def _result_code(self, change: float) -> int:
        if change > 40.0:
            return -2
        if change > 20.0:
            return -1
        return 0

    def _check_content_completeness(self, content: str, name: str) -> int:
        if name.lower()=='todo.md':
            return 0
        lines = content.splitlines()
        if len(lines)<3:
            logger.error(f"Incomplete output for {name}: only {len(lines)} lines")
            return -3
        # no truncation phrases for now
        return 0

    # format detection and parsing below
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
            return root.tag=='files' and len(root)>0 and root[0].tag=='file'
        except:
            return False

    def _is_md_fenced_format(self, out: str) -> bool:
        return bool(self.md_fenced_pattern.search(out))

    def _parse_section_format(self, out: str) -> List[Dict[str, Union[str,int]]]:
        matches = list(self.section_pattern.finditer(out))
        sections = []
        for idx, m in enumerate(matches):
            clean = m.group(1).strip().strip('\'"`')
            fn = Path(clean).name
            start = m.end()
            end = matches[idx+1].start() if idx+1<len(matches) else len(out)
            chunk = out[start:end].strip('\n')
            sections.append({'filename':fn,'content':chunk})
        return sections

    def _parse_json_format(self, out: str) -> List[Dict[str, Union[str,int]]]:
        data = json.loads(out.strip())
        files = data.get('files',[])
        parsed=[]
        for it in files:
            fn = it.get('filename','').strip()
            ct = it.get('content','').strip()
            if self._validate_filename(fn):
                parsed.append({'filename':fn,'content':ct})
        return parsed

    def _parse_yaml_format(self, out: str) -> List[Dict[str, Union[str,int]]]:
        data = yaml.safe_load(out)
        files = data.get('files',[])
        parsed=[]
        for it in files:
            fn=it.get('filename','').strip()
            ct=it.get('content','').strip()
            if self._validate_filename(fn):
                parsed.append({'filename':fn,'content':ct})
        return parsed

    def _parse_xml_format(self, out: str) -> List[Dict[str, Union[str,int]]]:
        root = ET.fromstring(out.strip())
        parsed=[]
        for fe in root.findall('file'):
            fn_el=fe.find('filename'); ct_el=fe.find('content')
            if fn_el is None or ct_el is None: continue
            fn,ct=(fn_el.text or '').strip(),(ct_el.text or '').strip()
            if self._validate_filename(fn):
                parsed.append({'filename':fn,'content':ct})
        return parsed

    def _parse_md_fenced_format(self, out: str) -> List[Dict[str, Union[str,int]]]:
        matches = self.md_fenced_pattern.findall(out)
        parsed=[]
        for info,content in matches:
            fn = info.strip() or "unnamed"
            if not self._validate_filename(fn):
                logger.warning(f"Invalid filename: {fn}, skipping")
                continue
            parsed.append({'filename':fn,'content':content.strip()})
        return parsed

    def _parse_generic_format(self, out: str) -> List[Dict[str, Union[str,int]]]:
        lines = out.split('\n')
        parsed=[]; cur_fn=None; buf=[]
        for line in lines:
            m=self.filename_pattern.match(line)
            if m:
                if cur_fn and buf:
                    ct='\n'.join(buf).strip()
                    if self._validate_filename(cur_fn):
                        parsed.append({'filename':cur_fn,'content':ct})
                cur_fn=m.group(1).strip()
                buf=[m.group(2).strip()]
            elif cur_fn and line.strip():
                buf.append(line.strip())
        if cur_fn and buf:
            ct='\n'.join(buf).strip()
            if self._validate_filename(cur_fn):
                parsed.append({'filename':cur_fn,'content':ct})
        if not parsed:
            raise ParsingError("No valid files found in generic parsing")
        return parsed

    def _parse_fallback(self, out: str) -> List[Dict[str, Union[str,int]]]:
        logger.warning("Fallback parser - single file")
        return [{'filename':'generated.txt','content':out.strip()}]

    def _validate_filename(self, fn: str) -> bool:
        if not fn or len(fn)>255: return False
        for ch in '<>:"/\\|?*':
            if ch in fn: return False
        if '..' in fn or fn.startswith('/'): return False
        return True

# original file length: 338 lines
# updated file length: 344 lines