# file: smart_merge_precise.py
#!/usr/bin/env python3
"""
Precise SmartMerge that only changes lines that actually differ.
Uses line-by-line comparison to minimize changes and improve reliability.
"""
import difflib
import logging
from typing import List, Tuple, Optional, Dict, Any

logger = logging.getLogger(__name__)


class PreciseSmartMerge:
    """
    Precise merge that only changes lines that actually need updating.
    
    Key improvements:
    1. Line-by-line comparison instead of block replacement
    2. Only changes lines that actually differ
    3. Preserves unchanged lines exactly
    4. Better handling of whitespace and formatting
    5. More conservative matching (higher threshold)
    """
    
    def __init__(self, similarity_threshold: float = 0.85):
        """
        Initialize with high threshold for precision.
        
        Args:
            similarity_threshold: Minimum similarity (0.85 recommended for precision)
        """
        self.similarity_threshold = similarity_threshold
        self.min_context_match = 0.9  # Context lines must match very closely
        self.max_line_diff_ratio = 0.3  # Max 30% of lines can differ
        
        logger.info(f"PreciseSmartMerge initialized: threshold={similarity_threshold}")
    
    def apply_partial_content(
        self,
        original_content: str,
        partial_content: str,
        context_lines: int = 5
    ) -> Tuple[str, bool, str]:
        """
        Apply partial content with precise line-by-line merging.
        
        Args:
            original_content: Full original file content
            partial_content: Partial content from LLM
            context_lines: Number of context lines for matching (5 recommended)
            
        Returns:
            Tuple of (merged_content, success, message)
        """
        if not partial_content or not partial_content.strip():
            return original_content, False, "Partial content is empty"
        
        orig_lines = original_content.splitlines(keepends=True)
        partial_lines = partial_content.splitlines(keepends=True)
        
        logger.info(f"Precise merge: original={len(orig_lines)} lines, partial={len(partial_lines)} lines")
        
        # Check if this looks like a complete file
        if self._is_complete_file(partial_lines, orig_lines):
            logger.info("Detected complete file replacement")
            return partial_content, True, "Complete file replacement"
        
        # Find the best matching region
        match = self._find_precise_match(orig_lines, partial_lines, context_lines)
        
        if not match:
            logger.warning("No precise match found, using as complete replacement")
            return partial_content, False, "No match found - used as complete replacement"
        
        start_idx, end_idx, confidence = match
        
        # Perform precise line-by-line merge
        merged_lines = self._merge_precise(orig_lines, partial_lines, start_idx, end_idx)
        
        # Reconstruct content
        merged_content = ''.join(merged_lines)
        
        # Calculate actual changes
        changes = self._count_changes(orig_lines[start_idx:end_idx], partial_lines)
        
        message = f"Merged at lines {start_idx+1}-{end_idx+1} (confidence: {confidence:.1%}, changed: {changes['modified']} lines)"
        logger.info(message)
        
        return merged_content, True, message
    
    def _is_complete_file(self, partial_lines: List[str], orig_lines: List[str]) -> bool:
        """Check if partial content is actually a complete file."""
        if not partial_lines or not orig_lines:
            return False
        
        # Similar line count (within 20%)
        ratio = len(partial_lines) / len(orig_lines) if len(orig_lines) > 0 else 0
        if 0.8 <= ratio <= 1.2 and len(partial_lines) > 10:
            return True
        
        # Starts with file header indicators
        first_line = partial_lines[0].strip()
        if first_line.startswith(('#!', 'import ', 'from ', '<?php', '<!DOCTYPE', '# file:')):
            if len(partial_lines) > 20:
                return True
        
        return False
    
    def _find_precise_match(
        self,
        orig_lines: List[str],
        partial_lines: List[str],
        context_lines: int
    ) -> Optional[Tuple[int, int, float]]:
        """
        Find the precise location where partial content should be merged.
        
        Uses strict context matching at start and end.
        
        Returns:
            Tuple of (start_index, end_index, confidence) or None
        """
        if len(partial_lines) < context_lines:
            context_lines = max(1, len(partial_lines) // 2)
        
        # Extract context from partial content
        context_start = partial_lines[:context_lines]
        context_end = partial_lines[-context_lines:]
        
        best_match = None
        best_confidence = 0.0
        
        # Slide through original looking for matching context
        for i in range(len(orig_lines) - len(partial_lines) + 1):
            # Check start context
            window_start = orig_lines[i:i + context_lines]
            start_sim = self._line_similarity(context_start, window_start)
            
            if start_sim < self.min_context_match:
                continue
            
            # Check end context
            end_idx = i + len(partial_lines)
            if end_idx > len(orig_lines):
                continue
            
            window_end = orig_lines[end_idx - context_lines:end_idx]
            end_sim = self._line_similarity(context_end, window_end)
            
            if end_sim < self.min_context_match:
                continue
            
            # Check middle content similarity
            middle_orig = orig_lines[i:end_idx]
            middle_sim = self._line_similarity(partial_lines, middle_orig)
            
            # Combined confidence (weighted)
            confidence = (start_sim * 0.3 + end_sim * 0.3 + middle_sim * 0.4)
            
            if confidence > best_confidence and confidence >= self.similarity_threshold:
                best_confidence = confidence
                best_match = (i, end_idx, confidence)
        
        return best_match
    
    def _line_similarity(self, lines1: List[str], lines2: List[str]) -> float:
        """
        Calculate similarity between two sets of lines.
        
        Uses line-by-line comparison with normalization.
        """
        if not lines1 or not lines2:
            return 0.0
        
        if len(lines1) != len(lines2):
            # Penalize different lengths
            len_ratio = min(len(lines1), len(lines2)) / max(len(lines1), len(lines2))
            if len_ratio < 0.8:
                return 0.0
        
        # Compare line by line
        matches = 0
        total = max(len(lines1), len(lines2))
        
        for i in range(min(len(lines1), len(lines2))):
            line1 = self._normalize_line(lines1[i])
            line2 = self._normalize_line(lines2[i])
            
            # Exact match
            if line1 == line2:
                matches += 1
            else:
                # Fuzzy match using SequenceMatcher
                matcher = difflib.SequenceMatcher(None, line1, line2)
                if matcher.ratio() >= 0.8:
                    matches += 0.5  # Partial credit
        
        return matches / total if total > 0 else 0.0
    
    def _normalize_line(self, line: str) -> str:
        """Normalize line for comparison (trim whitespace, lowercase)."""
        return line.strip().lower()
    
    def _merge_precise(
        self,
        orig_lines: List[str],
        partial_lines: List[str],
        start_idx: int,
        end_idx: int
    ) -> List[str]:
        """
        Perform precise line-by-line merge.
        
        Only replaces lines that actually differ.
        """
        result = []
        
        # Keep everything before the match
        result.extend(orig_lines[:start_idx])
        
        # Merge the matched region line by line
        orig_region = orig_lines[start_idx:end_idx]
        
        # Use difflib to find actual differences
        differ = difflib.Differ()
        diff = list(differ.compare(
            [line.rstrip('\n\r') for line in orig_region],
            [line.rstrip('\n\r') for line in partial_lines]
        ))
        
        # Reconstruct with only necessary changes
        for line in diff:
            if line.startswith('  '):  # Unchanged
                result.append(line[2:] + '\n')
            elif line.startswith('+ '):  # Added
                result.append(line[2:] + '\n')
            elif line.startswith('- '):  # Removed (skip)
                pass
            elif line.startswith('? '):  # Diff marker (skip)
                pass
        
        # Keep everything after the match
        result.extend(orig_lines[end_idx:])
        
        return result
    
    def _count_changes(self, orig_lines: List[str], new_lines: List[str]) -> Dict[str, int]:
        """Count the number of changed lines."""
        differ = difflib.Differ()
        diff = list(differ.compare(
            [line.rstrip('\n\r') for line in orig_lines],
            [line.rstrip('\n\r') for line in new_lines]
        ))
        
        added = sum(1 for line in diff if line.startswith('+ '))
        removed = sum(1 for line in diff if line.startswith('- '))
        
        return {
            'added': added,
            'removed': removed,
            'modified': added + removed
        }
    
    def create_detailed_diff(
        self,
        original: str,
        merged: str,
        filename: str = "file"
    ) -> str:
        """
        Create a detailed unified diff showing only actual changes.
        """
        orig_lines = original.splitlines(keepends=True)
        merged_lines = merged.splitlines(keepends=True)
        
        diff = difflib.unified_diff(
            orig_lines,
            merged_lines,
            fromfile=f"a/{filename}",
            tofile=f"b/{filename}",
            lineterm=''
        )
        
        return ''.join(diff)


def create_precise_merge(similarity_threshold: float = 0.85) -> PreciseSmartMerge:
    """
    Create a PreciseSmartMerge instance with recommended settings.
    
    Args:
        similarity_threshold: Minimum similarity (0.85 recommended for precision)
    
    Returns:
        PreciseSmartMerge instance
    """
    return PreciseSmartMerge(similarity_threshold=similarity_threshold)
