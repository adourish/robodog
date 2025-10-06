# file: diff_service.py
#!/usr/bin/env python3
"""Service for generating diffs used by ParseService."""
import difflib
from difflib import SequenceMatcher
import re
import textwrap
from datetime import datetime
from pathlib import Path
import logging

logger = logging.getLogger(__name__)

class DiffService:
    """Encapsulates diff-generation logic for unified and side-by-side diffs."""
    def __init__(self, side_width: int = 60):
        self.side_width = side_width
        self.hunk_header = re.compile(r'^@@ -\d+(?:,\d+)? \+(\d+)(?:,\d+)? @@')
        self._hunk_re = re.compile(r'^@@ -\d+(?:,\d+)? \+\d+(?:,\d+)? @@', re.MULTILINE)

    def generate_improved_md_diff(self, filename: str, original: str, updated: str, matched: str) -> str:
        """
        Enhanced unified diff with emojis and file line numbers, formatted as Markdown.
        """
        logger.debug(f"DiffService: generating improved MD diff for {filename}", extra={'log_color': 'HIGHLIGHT'})
        orig_lines = original.splitlines()
        updt_lines = updated.splitlines()
        unified = list(difflib.unified_diff(
            orig_lines, updt_lines,
            fromfile=f'🔵 Original: {filename}',
            tofile=f'🔴 Updated: {filename} (matched: {matched})',
            lineterm='', n=7
        ))
        md_lines = [
            f"# 📊 Enhanced Diff for {filename}",
            f"**File Path:** {matched or filename}",
            f"**Change Timestamp:** {datetime.utcnow().isoformat()}",
            "",
            "## 🔍 Unified Diff (With Emojis & File Line Numbers)",
            "```diff"
        ]
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
            else:
                prefix = line[:1]
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
                    logger.debug(f"Line deleted: {content[:50]}...", extra={'log_color': 'DELTA'})
                elif prefix == '+':
                    emoji = '🟢'
                    if new_num is not None:
                        md_lines.append(f"[{new_num:4}{emoji}] {content}")
                    new_num = (new_num or 0) + 1
                    logger.debug(f"Line added: {content[:50]}...", extra={'log_color': 'HIGHLIGHT'})
                else:
                    md_lines.append(line)
        md_lines.append("```")
        return "\n".join(md_lines) + "\n"

    def generate_side_by_side_diff(self, filename: str, original: str, updated: str, matched: str) -> str:
        """
        Side-by-side diff with emojis and wrapping.
        """
        logger.debug(f"DiffService: generating side-by-side diff for {filename}", extra={'log_color': 'HIGHLIGHT'})
        orig_lines = original.splitlines()
        updt_lines = updated.splitlines()
        matcher = SequenceMatcher(None, orig_lines, updt_lines)
        ops = matcher.get_opcodes()
        col_width = self.side_width
        left_pad = col_width + 8  # account for "[####]⚫ "

        lines = [
            f"📑 Side-by-Side Diff for {filename}",
            f"🔗 {matched or filename}",
            f"⏱️ {datetime.utcnow().isoformat()}",
            "",
            f"{'ORIGINAL'.ljust(left_pad)}   {'UPDATED'}",
            " " * left_pad + "  " + " " * (col_width + 8)
        ]

        o_ln = 1
        n_ln = 1

        def wrap(text: str, width: int):
            if len(text) <= width:
                return [text]
            return textwrap.wrap(text, width=width, break_long_words=True, break_on_hyphens=False)

        for tag, i1, i2, j1, j2 in ops:
            if tag == 'equal':
                for i in range(i1, i2):
                    l = orig_lines[i]
                    wrapped = wrap(l, col_width)
                    for idxw, segment in enumerate(wrapped):
                        if idxw == 0:
                            left = f"{o_ln:4}⚪ {segment}".ljust(left_pad)
                            right = f"             {segment}"
                        else:
                            left = f"      {segment}".ljust(left_pad)
                            right = f"         {segment}"
                        lines.append(f"{left}  {right}")
                    o_ln += 1
                    n_ln += 1
            elif tag == 'delete':
                for i in range(i1, i2):
                    wrapped = wrap(orig_lines[i], col_width)
                    for idxw, segment in enumerate(wrapped):
                        if idxw == 0:
                            left = f"{o_ln:4}⚫ {segment}".ljust(left_pad)
                        else:
                            left = f"    ⚫ {segment}".ljust(left_pad)
                        right = " " * (col_width + 8)
                        lines.append(f"{left}  {right}")
                    o_ln += 1
                    logger.debug(f"Block deleted: lines {o_ln-i2+i1} to {o_ln-1}", extra={'log_color': 'DELTA'})
            elif tag == 'insert':
                for j in range(j1, j2):
                    wrapped = wrap(updt_lines[j], col_width)
                    for idxw, segment in enumerate(wrapped):
                        left = " " * left_pad
                        if idxw == 0:
                            right = f"{n_ln:4}🟢 {segment}"
                        else:
                            right = f"      {segment}"
                        lines.append(f"{left}  {right}")
                    n_ln += 1
                    logger.debug(f"Block inserted: lines {n_ln-j2+j1} to {n_ln-1}", extra={'log_color': 'PERCENT'})
            elif tag == 'replace':
                for idxd, la in enumerate(orig_lines[i1:i2]):
                    wrapped = wrap(la, col_width)
                    for idxw, segment in enumerate(wrapped):
                        if idxw == 0:
                            left = f"{o_ln + idxd:4}⚫ {segment}".ljust(left_pad)
                        else:
                            left = f"      {segment}".ljust(left_pad)
                        right = " " * (col_width + 8)
                        lines.append(f"{left}  {right}")
                for idxi, lb in enumerate(updt_lines[j1:j2]):
                    wrapped = wrap(lb, col_width)
                    for idxw, segment in enumerate(wrapped):
                        left = " " * left_pad
                        if idxw == 0:
                            right = f"{n_ln + idxi:4}🟢 {segment}"
                        else:
                            right = f"      {segment}"
                        lines.append(f"{left}  {right}")
                o_ln += (i2 - i1)
                n_ln += (j2 - j1)
                logger.info(f"Block replaced: {i2-i1} lines removed, {j2-j1} lines added", extra={'log_color': 'HIGHLIGHT'})

        return "\n".join(lines) + "\n"

    def is_unified_diff(self, text: str) -> bool:
        """
        Quick check for unified‐diff format:
        - must contain at least one hunk header (@@ -x,y +a,b @@)
        - and file markers '--- ' and '+++ '
        """
        if not text:
            return False
        if not self._hunk_re.search(text):
            return False
        has_from = any(line.startswith('--- ') for line in text.splitlines())
        has_to   = any(line.startswith('+++ ') for line in text.splitlines())
        return has_from and has_to

    def apply_if_unified(self, diff_text: str, original_text: str) -> str:
        """
        If diff_text is a unified diff, apply it against original_text.
        Otherwise just return original_text.
        """
        if self.is_unified_diff(diff_text):
            logger.debug("Unified diff detected – applying patch")
            return self.apply_unified_diff(diff_text, original_text)
        else:
            logger.debug("Not a unified diff – skipping patch")
            return original_text
        
    def apply_unified_diff(self, diff_text: str, original_text: str) -> str:
        """
        Apply a unified diff (as produced by difflib.unified_diff) to the
        original_text and return the patched text.
        """
        import re

        orig_lines = original_text.splitlines()
        new_lines = []
        diff_lines = diff_text.splitlines()

        hunk_re = re.compile(r'^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@')

        orig_idx = 0
        i = 0

        while i < len(diff_lines):
            header = diff_lines[i]
            m = hunk_re.match(header)
            if not m:
                i += 1
                continue
            o_start = int(m.group(1)) - 1
            o_count = int(m.group(2) or '1')

            while orig_idx < o_start:
                new_lines.append(orig_lines[orig_idx])
                orig_idx += 1

            i += 1
            while i < len(diff_lines) and not diff_lines[i].startswith('@@'):
                line = diff_lines[i]
                if not line:
                    if orig_idx < len(orig_lines):
                        new_lines.append(orig_lines[orig_idx])
                        orig_idx += 1
                else:
                    tag, text = line[0], line[1:]
                    if tag == ' ':
                        new_lines.append(orig_lines[orig_idx])
                        orig_idx += 1
                    elif tag == '-':
                        orig_idx += 1
                    elif tag == '+':
                        new_lines.append(text)
                i += 1
        while orig_idx < len(orig_lines):
            new_lines.append(orig_lines[orig_idx])
            orig_idx += 1

        result = "\n".join(new_lines)
        if original_text.endswith("\n"):
            result += "\n"
        return result