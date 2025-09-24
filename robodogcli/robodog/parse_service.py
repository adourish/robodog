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
        # Pattern to match comment directives with optional NEW/DELETE/COPY/UPDATE flags
        self.section_pattern = re.compile(
            r'^\s*(?P<comment>(#|//|/\*))\s*file:\s*'
            r'(["`]?(?P<filename>[^"`\s]+(?:/[^"`\s]+)*)["`]?)?'  # quoted or unquoted filename/path
            r'\s*(?P<flag>NEW|DELETE|COPY|UPDATE)?\s*$', 
            re.IGNORECASE | re.MULTILINE
        )
        # fenced code blocks
        self.md_fenced_pattern = re.compile(r'```([^\n]*)\n(.*?)\n```', re.DOTALL)
        # generic "filename: content" lines
        self.filename_pattern = re.compile(r'^([^:]+):\s*(.*)$', re.MULTILINE)
        self.side_width = 60
        self._base_dir = base_dir
        self._backupFolder = backupFolder
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
        Parse LLM output into objects with enhanced metadata.
        Ensures each returned dict has 'filename', 'originalfilename', and 'matchedfilename'.
        """
        logger.debug("Starting parse of LLM output")
        try:
            fmt = self._detect_format(llm_output)
            parsed = self._parse_by_format(llm_output, fmt)
        except Exception as e:
            logger.error(f"Parsing error: {e}")
            try:
                parsed = self._parse_fallback(llm_output)
            except Exception as fe:
                raise ParsingError(f"Could not parse LLM output: {e}")
        fs = file_service or self.file_service
        # Enhance and apply flags
        for obj in parsed:
            self._enhance_parsed_object(obj, base_dir, fs, task, svc)
        # Ensure key fields
        for obj in parsed:
            fn = obj.get('filename', '')
            obj.setdefault('originalfilename', fn)
            obj.setdefault('matchedfilename', fn)
        # Apply flags (NEW/DELETE/COPY/UPDATE)
        for obj in parsed:
            flags = self._determine_flags(obj, obj['matchedfilename'])
            obj.update(flags)
            self._apply_flag_to_content(obj)
        # Generate side-by-side diffs if applicable
        self._write_side_by_side_diffs(parsed, ai_out_path or self._base_dir or str(Path.cwd()), fs)

        # Log for each file: action, filename, original/updated/delta/percentage
        for obj in parsed:
            filename = obj.get('filename', '')
            originalfilename = obj.get('originalfilename', filename)
            matchedfilename = obj.get('matchedfilename', filename)
            relative_path = obj.get('relative_path', filename)
            original_tokens = obj.get('original_tokens', 0)
            new_tokens = obj.get('new_tokens', 0)
            abs_delta = obj.get('abs_delta_tokens', 0)
            percent_delta = obj.get('percent_delta', 0.0)
            action = 'NEW' if obj.get('new') else 'UPDATE' if obj.get('update') else 'DELETE' if obj.get('delete') else 'COPY' if obj.get('copy') else 'UPDATE'
            # Enhanced: Use DELTA color for parsing logs via extra dict (colorlog supports it if configured)
            logger.info(f"Parse {action} {relative_path}: (O/U/D/P {original_tokens}/{new_tokens}/{abs_delta}/{percent_delta:.1f}%)", extra={'log_color': 'DELTA'})
            logger.debug(f"  - originalfilename: {originalfilename}")
            logger.debug(f"  - matchedfilename: {matchedfilename}")

        logger.debug("Completed parse_llm_output")
        return parsed

    # --- helper methods below (unchanged) ---
    def parse_llm_output_commit(
        self,
        llm_output: str,
        base_dir: Optional[str] = None,
        file_service: Optional[object] = None,
        ai_out_path: Union[str, Path] = '',
        task: Union[Dict, List] = None,
        svc: Optional[object] = None,
    ) -> List[Dict[str, Union[str, int, bool]]]:
        """
        Same as parse_llm_output, but afterwards re‐reads the first line of each
        file‐directive and forces the new/update/delete/copy flags to exactly
        what the directive in the AI output says.
        """
        # first, parse normally (this will fill content, matchedfilename, etc)
        parsed = self.parse_llm_output(
            llm_output,
            base_dir=base_dir,
            file_service=file_service,
            ai_out_path=str(ai_out_path),
            task=task,
            svc=svc,
        )
        import re
        for obj in parsed:
            # look at the very first line of the content
            first = obj.get('content', '').splitlines()[0]
            m = re.search(r'\b(NEW|DELETE|COPY|UPDATE)\s*$', first, re.IGNORECASE)
            # reset all four to False
            obj['new'] = obj['update'] = obj['delete'] = obj['copy'] = False
            if m:
                flag = m.group(1).upper()
                if flag == 'NEW':
                    obj['new'] = True
                elif flag == 'UPDATE':
                    obj['update'] = True
                elif flag == 'DELETE':
                    obj['delete'] = True
                elif flag == 'COPY':
                    obj['copy'] = True
        return parsed
    def _detect_format(self, out: str) -> str:
        if self._is_section_format(out):
            return 'section'
        if self._is_json_format(out):
            return 'json'
        if self._is_yaml_format(out):
            return 'yaml'
        if self._is_xml_format(out):
            return 'xml'
        if self._is_md_fenced_format(out):
            return 'md_fenced'
        return 'generic'

    def _parse_by_format(self, out: str, fmt: str):
        if fmt == 'section':
            return self._parse_section_format(out)
        if fmt == 'json':
            return self._parse_json_format(out)
        if fmt == 'yaml':
            return self._parse_yaml_format(out)
        if fmt == 'xml':
            return self._parse_xml_format(out)
        if fmt == 'md_fenced':
            return self._parse_md_fenced_format(out)
        return self._parse_generic_format(out)

    def _is_section_format(self, out: str) -> bool:
        return bool(self.section_pattern.search(out))

    def _is_json_format(self, out: str) -> bool:
        s = out.strip()
        if not (s.startswith('{') or s.startswith('[')): return False
        try:
            data = json.loads(s)
            return isinstance(data, dict) and 'files' in data
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
            return root.tag == 'files'
        except:
            return False

    def _is_md_fenced_format(self, out: str) -> bool:
        return bool(self.md_fenced_pattern.search(out))

    def _parse_section_format(self, out: str):  
        matches = list(self.section_pattern.finditer(out))
        sections = []
        for idx, m in enumerate(matches):
            comment, raw_fn, flag = self._extract_filename_and_flag(m.group(0))
            if not raw_fn:
                continue
            fn = Path(raw_fn).name
            start = m.end()
            end = matches[idx+1].start() if idx+1 < len(matches) else len(out)
            content = out[start:end].strip('\n')
            sections.append({
                'filename': fn,
                'relative_path': raw_fn,
                'content': content,
                'flag': flag,
                'comment_style': comment
            })
        return sections

    def _parse_json_format(self, out: str):
        data = json.loads(out)
        return [{'filename': f.get('filename',''), 'content': f.get('content','')} for f in data.get('files',[])]

    def _parse_yaml_format(self, out: str):
        data = yaml.safe_load(out)
        return [{'filename': f.get('filename',''), 'content': f.get('content','')} for f in data.get('files',[])]

    def _parse_xml_format(self, out: str):
        root = ET.fromstring(out)
        parsed = []
        for fe in root.findall('file'):
            fn = fe.findtext('filename','').strip()
            ct = fe.findtext('content','').strip()
            parsed.append({'filename': fn, 'content': ct})
        return parsed

    def _parse_md_fenced_format(self, out: str):
        matches = self.md_fenced_pattern.findall(out)
        return [{'filename': info.strip(), 'content': content.strip()} for info, content in matches]

    def _parse_generic_format(self, out: str):
        lines = out.split('\n')
        parsed = []
        cur = None
        buf = []
        for line in lines:
            m = self.filename_pattern.match(line)
            if m:
                if cur:
                    parsed.append({'filename': cur, 'content': '\n'.join(buf)})
                cur = m.group(1).strip()
                buf = [m.group(2).strip()]
            elif cur:
                buf.append(line)
        if cur:
            parsed.append({'filename': cur, 'content': '\n'.join(buf)})
        return parsed

    def _parse_fallback(self, out: str):
        return [{'filename': 'generated.txt', 'content': out.strip()}]

    def _extract_filename_and_flag(self, header: str):
        """
        Extract the comment prefix, the raw filename/path, and the flag (NEW|DELETE|COPY|UPDATE)
        from a directive line like:
            "# file: src/foo.txt DELETE"
            "// file: bar.js NEW"
        """
        # 1) grab the comment‐prefix (#, // or /*)
        cm = re.match(r'^\s*(?P<comment>(#|//|/\*))', header)
        comment = cm.group('comment') if cm else '#'

        # 2) strip off that prefix
        rest = header[cm.end():].strip() if cm else header.strip()

        # 3) remove an initial "file:" (case‐insensitive)
        rest = re.sub(r'(?i)^file:\s*', '', rest).strip()

        # 4) split into tokens and look at the last token for a flag
        parts = rest.split()
        flag = ''
        if parts and parts[-1].upper() in ('NEW', 'DELETE', 'COPY', 'UPDATE'):
            flag = parts[-1].upper()
            filename = ' '.join(parts[:-1])
        else:
            filename = rest

        # 5) strip any wrapping quotes or backticks
        filename = filename.strip('"').strip("'").strip('`')

        return comment, filename, flag
    
    def _extract_filename_and_flagb(self, header: str):
        comment_m = re.match(r'^\s*(?P<comment>(#|//|/\*))', header)
        comment = comment_m.group('comment') if comment_m else '#'
        rest = header[comment_m.end():].strip() if comment_m else header
        if rest.lower().startswith('file:'):
            rest = rest[5:].strip()
        parts = rest.rsplit(' ',1)
        if len(parts)==2 and parts[1].upper() in ('NEW','DELETE','COPY','UPDATE'):
            return comment, parts[0].strip(), parts[1].strip().upper()
        return comment, rest, ''

    def _enhance_parsed_object(self, obj, base_dir, fs, task, svc):
        filename = obj.get('filename','')
        content = obj.get('content','')
        flag = obj.get('flag','').upper()
        obj['comment_style'] = obj.get('comment_style','#')
        obj['relative_path'] = obj.get('relative_path', filename)
        # default original and matched to filename
        obj['originalfilename'] = filename
        obj['matchedfilename'] = filename
        # attempt to read original if UPDATE or DELETE
        if fs and flag not in ('NEW','COPY'):
            candidate = fs.find_matching_file(filename, {'pattern':'*','recursive':True}, svc)
            if candidate:
                obj['originalfilename'] = filename
                obj['matchedfilename'] = str(candidate.resolve())
        # diffs only for UPDATE/DELETE
        orig = fs.safe_read_file(Path(obj['matchedfilename'])) if fs and flag!='NEW' else ''
        upd = content if flag!='DELETE' else ''
        obj['diff_md'] = self.diff_service.generate_improved_md_diff(filename, orig, upd, obj['matchedfilename']) if flag!='NEW' else ''
        obj['diff_sbs'] = self.diff_service.generate_side_by_side_diff(filename, orig, upd, obj['matchedfilename']) if flag!='NEW' else ''
        # Add original content and token counts for logging in todo.py
        obj['original_content'] = orig
        obj['original_tokens'] = len(orig.split()) if orig else 0
        obj['new_tokens'] = len(upd.split()) if upd else 0
        obj['abs_delta_tokens'] = obj['new_tokens'] - obj['original_tokens']
        obj['percent_delta'] = ((obj['new_tokens'] - obj['original_tokens']) / obj['original_tokens'] * 100) if obj['original_tokens'] > 0 else 100.0 if obj['new_tokens'] > 0 else 0.0
        obj['short_compare'] = f"O:{obj['original_tokens']} N:{obj['new_tokens']} D:{obj['abs_delta_tokens']}"

    def _determine_flags(self, obj, matched):
        flag = obj.get('flag','').upper()
        logger.debug("flag:" + flag)
        exists = Path(matched).exists() if matched else False
        return {
            'new': flag=='NEW',
            'update': flag=='UPDATE',
            'delete': flag=='DELETE',
            'copy': flag=='COPY'
        }

    def _determine_flagsc(self, obj, matched):
        """
        Determine new/update/delete/copy based on the actual LLM directive line,
        or, if none of those keywords is present, fall back to using
        filesystem existence to choose between new vs. update.
        """
        # look at the very first line of the content (the "// file: ..." or "# file: ..." line)
        first_line = obj.get('content', '').splitlines()[0] if obj.get('content') else ''
        # try to find one of the four keywords
        m = re.search(r'\b(NEW|UPDATE|DELETE|COPY)\b', first_line, re.IGNORECASE)
        flag = m.group(1).upper() if m else ''

        # if matched is a path, test whether it already exists on disk
        exists = False
        if matched:
            try:
                exists = Path(matched).exists()
            except Exception:
                exists = False

        return {
            # explicit NEW or no keyword + file did not exist
            'new':      (flag == 'NEW') or (flag == '' and not exists),
            # explicit UPDATE or no keyword + file did exist
            'update':   (flag == 'UPDATE') or (flag == '' and exists),
            'delete':   (flag == 'DELETE'),
            'copy':     (flag == 'COPY'),
        }
    
    def _apply_flag_to_content(self, obj):
        c = obj.get('comment_style','#')
        fname = obj.get('filename','')
        parts = [f"{c} file: {fname}"]
        if obj['new'] and not obj['copy']:
            parts[0] += " NEW"
        if obj['delete']:
            parts[0] += " DELETE"
        if obj['copy']:
            parts[0] += " COPY"
        body = obj.get('content','')
        obj['content'] = parts[0] + (f"\n{body}" if not obj['delete'] else "")

    def _write_side_by_side_diffs(self, parsed, out_path, fs):
        if not fs: return
        diffdir = Path(out_path or self._base_dir or '.').parent / 'diffoutput'
        fs.ensure_dir(diffdir)
        ts = datetime.utcnow().strftime("%Y%m%d-%H%M%S")
        for obj in parsed:
            sbs = obj.get('diff_sbs','')
            if not sbs: continue
            stem = Path(obj['filename']).stem
            suf = Path(obj['filename']).suffix or '.md'
            name = f"diff-sbs-{stem}-{ts}{suf}"
            try:
                fs.write_file(diffdir / name, sbs)
            except Exception:
                pass
    def parse_llm_outputd(
        self,
        llm_output: str,
        base_dir: Optional[str] = None,
        file_service: Optional[object] = None,
        ai_out_path: str = '',
        task: Union[Dict, List] = None,
        svc: Optional[object] = None,
    ) -> List[Dict[str, Union[str, int, bool]]]:
        """
        Parse LLM output into objects with enhanced metadata.
        Ensures each returned dict has 'filename', 'originalfilename', and 'matchedfilename'.
        """
        logger.debug("Starting parse of LLM output")
        try:
            fmt = self._detect_format(llm_output)
            parsed = self._parse_by_format(llm_output, fmt)
        except Exception as e:
            logger.error(f"Parsing error: {e}")
            try:
                parsed = self._parse_fallback(llm_output)
            except Exception as fe:
                raise ParsingError(f"Could not parse LLM output: {e}")
        fs = file_service or self.file_service
        # Enhance and apply flags
        for obj in parsed:
            self._enhance_parsed_object(obj, base_dir, fs, task, svc)
        # Ensure key fields
        for obj in parsed:
            fn = obj.get('filename', '')
            obj.setdefault('originalfilename', fn)
            obj.setdefault('matchedfilename', fn)
        # Apply flags (NEW/DELETE/COPY/UPDATE)
        for obj in parsed:
            flags = self._determine_flags(obj, obj['matchedfilename'])
            obj.update(flags)
            self._apply_flag_to_content(obj)
        # Generate side-by-side diffs if applicable
        self._write_side_by_side_diffs(parsed, ai_out_path or self._base_dir or str(Path.cwd()), fs)
        logger.debug("Completed parse_llm_output")
        return parsed

    # --- helper methods below (unchanged) ---
    def _detect_formatb(self, out: str) -> str:
        if self._is_section_format(out):
            return 'section'
        if self._is_json_format(out):
            return 'json'
        if self._is_yaml_format(out):
            return 'yaml'
        if self._is_xml_format(out):
            return 'xml'
        if self._is_md_fenced_format(out):
            return 'md_fenced'
        return 'generic'

    def _parse_by_formatb(self, out: str, fmt: str):
        if fmt == 'section':
            return self._parse_section_format(out)
        if fmt == 'json':
            return self._parse_json_format(out)
        if fmt == 'yaml':
            return self._parse_yaml_format(out)
        if fmt == 'xml':
            return self._parse_xml_format(out)
        if fmt == 'md_fenced':
            return self._parse_md_fenced_format(out)
        return self._parse_generic_format(out)

    def _is_section_formatb(self, out: str) -> bool:
        return bool(self.section_pattern.search(out))

    def _is_json_formatb(self, out: str) -> bool:
        s = out.strip()
        if not (s.startswith('{') or s.startswith('[')): return False
        try:
            data = json.loads(s)
            return isinstance(data, dict) and 'files' in data
        except:
            return False

    def _is_yaml_formatb(self, out: str) -> bool:
        try:
            data = yaml.safe_load(out)
            return isinstance(data, dict) and 'files' in data
        except:
            return False

    def _is_xml_formatb(self, out: str) -> bool:
        s = out.strip()
        if not s.startswith('<'): return False
        try:
            root = ET.fromstring(s)
            return root.tag == 'files'
        except:
            return False

    def _is_md_fenced_formatb(self, out: str) -> bool:
        return bool(self.md_fenced_pattern.search(out))

    def _parse_section_formatb(self, out: str):
        matches = list(self.section_pattern.finditer(out))
        sections = []
        for idx, m in enumerate(matches):
            comment, raw_fn, flag = self._extract_filename_and_flag(m.group(0))
            if not raw_fn:
                continue
            fn = Path(raw_fn).name
            start = m.end()
            end = matches[idx+1].start() if idx+1 < len(matches) else len(out)
            content = out[start:end].strip('\n')
            sections.append({
                'filename': fn,
                'relative_path': raw_fn,
                'content': content,
                'flag': flag,
                'comment_style': comment
            })
        return sections

    def _parse_json_formatb(self, out: str):
        data = json.loads(out)
        return [{'filename': f.get('filename',''), 'content': f.get('content','')} for f in data.get('files',[])]

    def _parse_yaml_formatb(self, out: str):
        data = yaml.safe_load(out)
        return [{'filename': f.get('filename',''), 'content': f.get('content','')} for f in data.get('files',[])]

    def _parse_xml_formatb(self, out: str):
        root = ET.fromstring(out)
        parsed = []
        for fe in root.findall('file'):
            fn = fe.findtext('filename','').strip()
            ct = fe.findtext('content','').strip()
            parsed.append({'filename': fn, 'content': ct})
        return parsed

    def _parse_md_fenced_formatb(self, out: str):
        matches = self.md_fenced_pattern.findall(out)
        return [{'filename': info.strip(), 'content': content.strip()} for info, content in matches]

    def _parse_generic_formatb(self, out: str):
        lines = out.split('\n')
        parsed = []
        cur = None
        buf = []
        for line in lines:
            m = self.filename_pattern.match(line)
            if m:
                if cur:
                    parsed.append({'filename': cur, 'content': '\n'.join(buf)})
                cur = m.group(1).strip()
                buf = [m.group(2).strip()]
            elif cur:
                buf.append(line)
        if cur:
            parsed.append({'filename': cur, 'content': '\n'.join(buf)})
        return parsed

    def _parse_fallbackb(self, out: str):
        return [{'filename': 'generated.txt', 'content': out.strip()}]

    def _extract_filename_and_flagb(self, header: str):
        comment_m = re.match(r'^\s*(?P<comment>(#|//|/\*))', header)
        comment = comment_m.group('comment') if comment_m else '#'
        rest = header[comment_m.end():].strip() if comment_m else header
        if rest.lower().startswith('file:'):
            rest = rest[5:].strip()
        parts = rest.rsplit(' ',1)
        if len(parts)==2 and parts[1].upper() in ('NEW','DELETE','COPY','UPDATE'):
            return comment, parts[0].strip(), parts[1].strip().upper()
        return comment, rest, ''

    def _enhance_parsed_objectb(self, obj, base_dir, fs, task, svc):
        filename = obj.get('filename','')
        content = obj.get('content','')
        flag = obj.get('flag','').upper()
        obj['comment_style'] = obj.get('comment_style','#')
        obj['relative_path'] = obj.get('relative_path', filename)
        # default original and matched to filename
        obj['originalfilename'] = filename
        obj['matchedfilename'] = filename
        # attempt to read original if UPDATE or DELETE
        if fs and flag not in ('NEW','COPY'):
            candidate = fs.find_matching_file(filename, {'pattern':'*','recursive':True}, svc)
            if candidate:
                obj['originalfilename'] = filename
                obj['matchedfilename'] = str(candidate.resolve())
        # diffs only for UPDATE/DELETE
        orig = fs.safe_read_file(Path(obj['matchedfilename'])) if fs and flag!='NEW' else ''
        upd = content if flag!='DELETE' else ''
        obj['diff_md'] = self.diff_service.generate_improved_md_diff(filename, orig, upd, obj['matchedfilename']) if flag!='NEW' else ''
        obj['diff_sbs'] = self.diff_service.generate_side_by_side_diff(filename, orig, upd, obj['matchedfilename']) if flag!='NEW' else ''
        # Add original content and token counts for logging in todo.py
        obj['original_content'] = orig
        obj['original_tokens'] = len(orig.split()) if orig else 0
        obj['new_tokens'] = len(upd.split()) if upd else 0
        obj['abs_delta_tokens'] = obj['new_tokens'] - obj['original_tokens']
        obj['percent_delta'] = ((obj['new_tokens'] - obj['original_tokens']) / obj['original_tokens'] * 100) if obj['original_tokens'] > 0 else 100.0 if obj['new_tokens'] > 0 else 0.0
        obj['short_compare'] = f"(O/N/D/P {obj['original_tokens']}/{obj['new_tokens']}/{obj['abs_delta_tokens']}/{obj['percent_delta']})"

    def _determine_flagsb(self, obj, matched):
        flag = obj.get('flag','').upper()
        exists = Path(matched).exists() if matched else False
        return {
            'new': flag=='NEW' or (not exists and flag==''),
            'update': flag=='UPDATE' or (exists and flag==''),
            'delete': flag=='DELETE',
            'copy': flag=='COPY'
        }

    def _apply_flag_to_contentb(self, obj):
        c = obj.get('comment_style','#')
        fname = obj.get('filename','')
        parts = [f"{c} file: {fname}"]
        if obj['new'] and not obj['copy']:
            parts[0] += " NEW"
        if obj['delete']:
            parts[0] += " DELETE"
        if obj['copy']:
            parts[0] += " COPY"
        body = obj.get('content','')
        obj['content'] = parts[0] + (f"\n{body}" if not obj['delete'] else "")


# original file length: 566 lines
# updated file length: 586 lines