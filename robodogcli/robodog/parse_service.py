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

logger = logging.getLogger(__name__)


class ParsingError(Exception):
    """Custom exception for parsing errors."""
    pass


class ParseService:
    """Service for parsing various LLM output formats into file objects."""
    
    def __init__(
        self,
        base_dir: str = None,
        backupFolder: str = None,
        diff_service: DiffService = None,
        file_service: Optional[object] = None
    ):
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
        Ensures every returned dict exposes `filename`, `originalfilename`, and `matchedfilename`.
        `originalfilename` preserves the directive-provided path, while `matchedfilename`
        points to the resolved on-disk target. Enhanced to handle unified diff format.
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
        parsed = self._normalize_core_fields(parsed)
        fs = file_service or self.file_service
        normalized_base_dir = base_dir or self._base_dir
        if not normalized_base_dir and fs and getattr(fs, 'base_dir', None):
            normalized_base_dir = fs.base_dir
        normalized_base_dir = normalized_base_dir or None
        # Enhance and apply flags
        for obj in parsed:
            self._enhance_parsed_object(obj, normalized_base_dir, fs, task, svc)
        parsed = self._normalize_core_fields(parsed)
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
            is_diff = obj.get('is_diff', False)
            action = (
                'NEW' if obj.get('new') else
                'UPDATE' if obj.get('update') else
                'DELETE' if obj.get('delete') else
                'COPY' if obj.get('copy') else
                'UPDATE'
            )
            if is_diff:
                action += " (diff)"
            logger.info(
                f"Parse {action} {relative_path}: (O/U/D/P {original_tokens}/{new_tokens}/{abs_delta}/{percent_delta:.1f}%)",
                extra={'log_color': 'DELTA'}
            )
            logger.debug(f"  - originalfilename: {originalfilename}")
            resolved_original = obj.get('original_resolved_path', '')
            if resolved_original:
                logger.debug(f"  - original_resolved_path: {resolved_original}")
            logger.debug(f"  - matchedfilename: {matchedfilename}")

        logger.debug("Completed parse_llm_output")
        return parsed

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
        Enhanced commit parsing that properly handles unified diffs.
        1. Parse normally into objects.
        2. For each UPDATE object whose content is a unified diff:
           a. Read the original file from disk.
           b. Apply the unified diff to it.
           c. Replace obj['content'] with the patched content (preserving the directive line).
           d. Recompute token counts.
        Finally, respect the directive’s NEW/UPDATE/DELETE/COPY flag.
        """
        logger.debug("Starting parse_llm_output_commit with enhanced diff handling")
        # Step 1: normal parse
        parsed = self.parse_llm_output(
            llm_output,
            base_dir=base_dir,
            file_service=file_service,
            ai_out_path=str(ai_out_path),
            task=task,
            svc=svc,
        )

        fs = file_service or self.file_service
        # Step 2: apply diffs in‐place
        for obj in parsed:
            try:
                flag = obj.get('flag', '').upper()
                # only UPDATEs get a diff applied
                if flag == 'UPDATE':
                    content = obj.get('content', '')
                    # strip off the first directive line
                    _, _, body = content.partition('\n')
                    # check for real unified diff
                    if self.diff_service.is_unified_diff(body):
                        matched = obj.get('matchedfilename')
                        if fs and matched:
                            orig_path = Path(matched)
                            if orig_path.exists():
                                original = fs.safe_read_file(orig_path)
                                try:
                                    patched = self.diff_service.apply_unified_diff(body, original)
                                    # preserve directive line
                                    first_line = content.split('\n', 1)[0]
                                    final = first_line + '\n' + patched
                                    obj['content'] = final
                                    obj['is_diff_applied'] = True
                                    # recompute token stats
                                    orig_tok = len(original.split())
                                    new_tok = len(patched.split())
                                    obj['original_tokens'] = orig_tok
                                    obj['new_tokens'] = new_tok
                                    obj['abs_delta_tokens'] = new_tok - orig_tok
                                    obj['percent_delta'] = (
                                        (new_tok - orig_tok) / orig_tok * 100
                                        if orig_tok > 0 else
                                        100.0 if new_tok > 0 else 0.0
                                    )
                                    logger.info(
                                        f"Applied unified diff in commit for {obj['filename']}: "
                                        f"{orig_tok}→{new_tok} tokens",
                                        extra={'log_color': 'HIGHLIGHT'}
                                    )
                                except Exception as e:
                                    logger.error(
                                        f"Failed to apply unified diff for {obj['filename']}: {e}",
                                        extra={'log_color': 'DELTA'}
                                    )
                                    obj['diff_apply_error'] = str(e)
                            else:
                                logger.warning(
                                    f"Original file not found for diff apply: {matched}",
                                    extra={'log_color': 'DELTA'}
                                )
                        else:
                            logger.warning(
                                f"No file_service or matchedfilename for diff apply: {obj['filename']}",
                                extra={'log_color': 'DELTA'}
                            )
            except Exception:
                logger.exception(
                    f"Error in parse_llm_output_commit handling diff for {obj.get('filename')}"
                )
        return parsed
    
    def _detect_format(self, out: str) -> str:
        if self._is_section_format(out):
            return 'section'
        if self._is_unified_diff_format(out):
            return 'unified_diff'
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
        if fmt == 'unified_diff':
            return self._parse_unified_diff_format(out)
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

    def _is_unified_diff_format(self, out: str) -> bool:
        """Check if output contains unified diff format with file directives."""
        if not self.diff_service.is_unified_diff(out):
            return False
        # Also check if it has our file directives
        return bool(self.section_pattern.search(out))

    def _is_json_format(self, out: str) -> bool:
        s = out.strip()
        if not (s.startswith('{') or s.startswith('[')):
            return False
        try:
            data = json.loads(s)
            return isinstance(data, dict) and 'files' in data
        except Exception:
            return False

    def _is_yaml_format(self, out: str) -> bool:
        try:
            data = yaml.safe_load(out)
            return isinstance(data, dict) and 'files' in data
        except Exception:
            return False

    def _is_xml_format(self, out: str) -> bool:
        s = out.strip()
        if not s.startswith('<'):
            return False
        try:
            root = ET.fromstring(s)
            return root.tag == 'files'
        except Exception:
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
            end = matches[idx + 1].start() if idx + 1 < len(matches) else len(out)
            content = out[start:end].strip('\n')
            
            # Check if content is a unified diff
            is_diff = self.diff_service.is_unified_diff(content)
            
            sections.append({
                'filename': fn,
                'relative_path': raw_fn,
                'content': content,
                'flag': flag,
                'comment_style': comment,
                'is_diff': is_diff
            })
        return sections

    def _parse_unified_diff_format(self, out: str):
        """Parse output that contains unified diffs with file directives."""
        return self._parse_section_format(out)  # Reuse section parsing

    def _parse_json_format(self, out: str):
        data = json.loads(out)
        return [{'filename': f.get('filename', ''), 'content': f.get('content', '')} for f in data.get('files', [])]

    def _parse_yaml_format(self, out: str):
        data = yaml.safe_load(out)
        return [{'filename': f.get('filename', ''), 'content': f.get('content', '')} for f in data.get('files', [])]

    def _parse_xml_format(self, out: str):
        root = ET.fromstring(out)
        parsed = []
        for fe in root.findall('file'):
            fn = fe.findtext('filename', '').strip()
            ct = fe.findtext('content', '').strip()
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

    def _normalize_core_fields(self, items: List[Dict[str, Union[str, int, bool]]]) -> List[Dict[str, Union[str, int, bool]]]:
        """
        Guarantee that every parsed object exposes filename metadata expected by downstream consumers.
        """
        normalized: List[Dict[str, Union[str, int, bool]]] = []
        for obj in items or []:
            if not isinstance(obj, dict):
                continue
            filename = obj.get('filename') or obj.get('relative_path') or obj.get('path') or 'generated.txt'
            if isinstance(filename, Path):
                filename = str(filename)
            filename = str(filename).strip() or 'generated.txt'
            obj['filename'] = filename

            rel = obj.get('relative_path')
            if isinstance(rel, Path):
                rel = str(rel)
            if rel is None or str(rel).strip() == '':
                rel = filename
            obj['relative_path'] = str(rel)

            originalfilename = obj.get('originalfilename')
            if isinstance(originalfilename, Path):
                originalfilename = str(originalfilename)
            if not originalfilename:
                originalfilename = obj['relative_path']
            obj['originalfilename'] = str(originalfilename)

            matchedfilename = obj.get('matchedfilename')
            if isinstance(matchedfilename, Path):
                matchedfilename = str(matchedfilename)
            if not matchedfilename:
                matchedfilename = obj['originalfilename']
            obj['matchedfilename'] = str(matchedfilename)

            normalized.append(obj)
        return normalized

    def _extract_filename_and_flag(self, header: str):
        """
        Extract the comment prefix, the raw filename/path, and the flag (NEW|DELETE|COPY|UPDATE)
        from a directive line like:
            "# file: src/foo.txt DELETE"
            "// file: bar.js NEW"
        """
        cm = re.match(r'^\s*(?P<comment>(#|//|/\*))', header)
        comment = cm.group('comment') if cm else '#'

        rest = header[cm.end():].strip() if cm else header.strip()
        rest = re.sub(r'(?i)^file:\s*', '', rest).strip()

        parts = rest.split()
        flag = ''
        if parts and parts[-1].upper() in ('NEW', 'DELETE', 'COPY', 'UPDATE'):
            flag = parts[-1].upper()
            filename = ' '.join(parts[:-1])
        else:
            filename = rest

        filename = filename.strip('"').strip("'").strip('`')
        return comment, filename, flag

    def _enhance_parsed_object(self, obj, base_dir, fs, task, svc):
        filename = (obj.get('filename') or '').strip()
        content = obj.get('content') or ''
        flag = (obj.get('flag') or '').upper()
        is_diff = obj.get('is_diff', False)
        obj['comment_style'] = obj.get('comment_style', '#')

        relative_raw = obj.get('relative_path')
        if isinstance(relative_raw, Path):
            relative_str = str(relative_raw)
        elif relative_raw is None or str(relative_raw).strip() == '':
            relative_str = filename
        else:
            relative_str = str(relative_raw).strip()
        if not relative_str:
            relative_str = filename or 'generated.txt'
        obj['relative_path'] = relative_str

        provided_original = obj.get('originalfilename')
        if isinstance(provided_original, Path):
            provided_original = str(provided_original)
        if not provided_original:
            provided_original = relative_str or filename
        provided_original = str(provided_original)

        rel_path = Path(relative_str) if relative_str else Path(filename or 'generated.txt')

        roots = self._collect_candidate_roots(base_dir, fs)
        existing_path = self._resolve_existing_path(rel_path, roots)
        resolved_from_service = self._attempt_service_resolution(fs, rel_path, svc) if fs else None
        if existing_path is None and resolved_from_service and resolved_from_service.exists():
            existing_path = resolved_from_service

        original_resolved_path = ''
        if existing_path:
            try:
                original_resolved_path = str(existing_path.resolve())
            except Exception:
                original_resolved_path = str(existing_path)
        obj['original_resolved_path'] = original_resolved_path
        obj['originalfilename'] = provided_original

        matched_path = existing_path or resolved_from_service
        if matched_path is None:
            matched_path = self._build_default_target(rel_path, roots)

        matched_path = Path(matched_path)
        try:
            matched_resolved = matched_path.resolve()
        except Exception:
            matched_resolved = matched_path

        obj['matchedfilename'] = str(matched_resolved)
        obj['matched_exists'] = matched_resolved.exists()
        obj['original_exists'] = bool(existing_path)

        orig = ''
        if fs and flag not in ('NEW', 'COPY'):
            read_candidate = matched_resolved if matched_resolved.exists() else matched_path
            if read_candidate.exists():
                orig = fs.safe_read_file(read_candidate)

        # Handle unified diff content
        if is_diff and self.diff_service.is_unified_diff(content) and orig:
            try:
                # Apply the diff to get the final content
                upd = self.diff_service.apply_unified_diff(content, orig)
                obj['content'] = upd  # Replace diff with final content for downstream processing
                logger.info(f"Applied unified diff for {filename}", extra={'log_color': 'HIGHLIGHT'})
            except Exception as e:
                logger.warning(f"Failed to apply unified diff for {filename}: {e}", extra={'log_color': 'DELTA'})
                upd = content  # Fall back to original content
        else:
            upd = content if flag != 'DELETE' else ''

        display_name = filename or relative_str or 'generated.txt'
        obj['diff_md'] = self.diff_service.generate_improved_md_diff(display_name, orig, upd, obj['matchedfilename']) if flag != 'NEW' else ''
        obj['diff_sbs'] = self.diff_service.generate_side_by_side_diff(display_name, orig, upd, obj['matchedfilename']) if flag != 'NEW' else ''
        obj['original_content'] = orig
        obj['original_tokens'] = len(orig.split()) if orig else 0
        obj['new_tokens'] = len(upd.split()) if upd else 0
        obj['abs_delta_tokens'] = obj['new_tokens'] - obj['original_tokens']
        obj['percent_delta'] = (
            ((obj['new_tokens'] - obj['original_tokens']) / obj['original_tokens']) * 100
            if obj['original_tokens'] > 0 else
            100.0 if obj['new_tokens'] > 0 else 0.0
        )
        obj['short_compare'] = f"O:{obj['original_tokens']} N:{obj['new_tokens']} D:{obj['abs_delta_tokens']}"
        logger.debug(
            "Enhanced file entry %s -> original=%s, matched=%s, exists=%s, is_diff=%s",
            display_name,
            obj['originalfilename'],
            obj['matchedfilename'],
            obj.get('matched_exists', False),
            is_diff
        )

    def _attempt_service_resolution(self, fs, rel_path: Path, svc) -> Optional[Path]:
        if not fs:
            return None
        candidates: List[Path] = []
        if hasattr(fs, 'resolve_path') and svc is not None:
            try:
                resolved = fs.resolve_path(str(rel_path), svc)
                if resolved:
                    candidates.append(resolved if isinstance(resolved, Path) else Path(resolved))
            except Exception as exc:
                logger.debug(f"resolve_path lookup failed for {rel_path}: {exc}")
        if hasattr(fs, 'find_matching_file'):
            try:
                include_spec = {'pattern': str(rel_path), 'recursive': True}
                matched = fs.find_matching_file(rel_path.name, include_spec, svc)
                if matched:
                    candidates.append(matched if isinstance(matched, Path) else Path(matched))
            except Exception as exc:
                logger.debug(f"find_matching_file lookup failed for {rel_path}: {exc}")
        for candidate in candidates:
            if candidate.exists():
                try:
                    return candidate.resolve()
                except Exception:
                    return candidate
        if candidates:
            try:
                return candidates[0].resolve()
            except Exception:
                return candidates[0]
        return None

    def _collect_candidate_roots(self, base_dir: Optional[Union[str, Path]], fs) -> List[Path]:
        candidates: List[Path] = []
        for value in (base_dir, self._base_dir, getattr(fs, 'base_dir', None)):
            if value:
                try:
                    candidates.append(Path(value))
                except TypeError:
                    continue
        if fs and getattr(fs, '_roots', None):
            for root in fs._roots:
                if root:
                    try:
                        candidates.append(Path(root))
                    except TypeError:
                        continue
        candidates.append(Path.cwd())
        unique: List[Path] = []
        seen: set[str] = set()
        for cand in candidates:
            try:
                key = str(cand.resolve())
            except Exception:
                key = str(cand)
            if key in seen:
                continue
            seen.add(key)
            unique.append(cand)
        return unique

    def _resolve_existing_path(self, rel_path: Path, roots: List[Path]) -> Optional[Path]:
        if rel_path.is_absolute():
            return rel_path if rel_path.exists() else None
        for root in roots:
            candidate = root / rel_path
            if candidate.exists():
                try:
                    return candidate.resolve()
                except Exception:
                    return candidate
        return None

    def _build_default_target(self, rel_path: Path, roots: List[Path]) -> Path:
        base = roots[0] if roots else Path.cwd()
        if rel_path.is_absolute():
            return rel_path
        candidate = base / rel_path
        try:
            return candidate.resolve()
        except Exception:
            return candidate

    def _determine_flags(self, obj, matched):
        flag = (obj.get('flag') or '').upper()
        exists = Path(matched).exists() if matched else False
        return {
            'new': flag == 'NEW',
            'update': flag == 'UPDATE' or (flag == '' and exists),
            'delete': flag == 'DELETE',
            'copy': flag == 'COPY'
        }

    def _apply_flag_to_content(self, obj):
        c = obj.get('comment_style', '#')
        fname = obj.get('filename', '')
        parts = [f"{c} file: {fname}"]
        if obj['new'] and not obj['copy']:
            parts[0] += " NEW"
        if obj['delete']:
            parts[0] += " DELETE"
        if obj['copy']:
            parts[0] += " COPY"
        body = obj.get('content', '')
        obj['content'] = parts[0] + (f"\n{body}" if not obj['delete'] else "")

    def _write_side_by_side_diffs(self, parsed, out_path, fs):
        if not fs:
            return
        diffdir = Path(out_path or self._base_dir or '.').parent / 'diffoutput'
        fs.ensure_dir(diffdir)
        ts = datetime.utcnow().strftime("%Y%m%d-%H%M%S")
        for obj in parsed:
            sbs = obj.get('diff_sbs', '')
            if not sbs:
                continue
            stem = Path(obj['filename']).stem
            suf = Path(obj['filename']).suffix or '.md'
            name = f"diff-sbs-{stem}-{ts}{suf}"
            try:
                fs.write_file(diffdir / name, sbs)
            except Exception:
                pass