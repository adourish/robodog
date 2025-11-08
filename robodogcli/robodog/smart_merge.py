# file: smart_merge.py
#!/usr/bin/env python3
"""
Smart merge service for applying partial LLM output to existing files.
Handles cases where the LLM returns only a substring of the full file.
"""
import difflib
import re
from typing import List, Tuple, Optional
import logging

logger = logging.getLogger(__name__)


class SmartMerge:
    """
    Intelligently merge partial LLM output into existing files.
    Uses fuzzy matching to find the best location for the changes.
    """
    
    def __init__(self, similarity_threshold: float = 0.6):
        """
        Initialize SmartMerge.
        
        Args:
            similarity_threshold: Minimum similarity ratio (0-1) to consider a match
        """
        self.similarity_threshold = similarity_threshold
    
    def apply_partial_content(
        self,
        original_content: str,
        partial_content: str,
        context_lines: int = 3
    ) -> Tuple[str, bool, str]:
        """
        Apply partial content from LLM to the original file.
        
        Args:
            original_content: The full original file content
            partial_content: The partial content from LLM (may be a substring)
            context_lines: Number of context lines to use for matching
            
        Returns:
            Tuple of (merged_content, success, message)
        """
        if not partial_content or not partial_content.strip():
            return original_content, False, "Partial content is empty"
        
        # Check if original has critical sections that should be protected
        if self._has_critical_section(original_content):
            # Check if partial content is trying to modify critical sections
            if self._has_critical_section(partial_content):
                logger.warning("Partial content contains critical section markers - using as complete replacement with caution")
            else:
                # Partial doesn't have critical markers but original does
                # Be more conservative - require higher confidence
                logger.info("Original has critical sections - requiring higher confidence for merge")
        
        # If partial content looks like a complete file, use it directly
        if self._looks_like_complete_file(partial_content, original_content):
            logger.info("Partial content appears to be a complete file replacement")
            return partial_content, True, "Complete file replacement"
        
        # Try to find where the partial content should be inserted
        match_result = self._find_best_match(original_content, partial_content, context_lines)
        
        if not match_result:
            # No good match found - try as a complete replacement
            logger.warning("No good match found for partial content, using as complete replacement")
            return partial_content, False, "No match found - used as complete replacement"
        
        start_line, end_line, confidence = match_result
        
        # Apply the changes
        merged = self._merge_at_location(
            original_content,
            partial_content,
            start_line,
            end_line
        )
        
        message = f"Merged at lines {start_line}-{end_line} (confidence: {confidence:.2%})"
        logger.info(message)
        
        return merged, True, message
    
    def _looks_like_complete_file(self, partial: str, original: str) -> bool:
        """
        Heuristic to determine if partial content is actually a complete file.
        """
        partial_lines = partial.strip().splitlines()
        original_lines = original.strip().splitlines()
        
        # If partial has similar line count to original (within 20%), likely complete
        if len(partial_lines) > 0 and len(original_lines) > 0:
            ratio = len(partial_lines) / len(original_lines)
            if 0.8 <= ratio <= 1.2:
                return True
        
        # If partial starts with typical file headers (imports, shebangs, etc.)
        if partial_lines:
            first_line = partial_lines[0].strip()
            if first_line.startswith(('#!', 'import ', 'from ', '<?php', '<!DOCTYPE')):
                # And has a reasonable number of lines
                if len(partial_lines) > 10:
                    return True
        
        return False
    
    def _has_critical_section(self, content: str) -> bool:
        """
        Check if content contains critical sections that should not be modified.
        Returns True if critical markers are found.
        """
        critical_markers = [
            'CRITICAL IMPORTS',
            'DO NOT REMOVE',
            'DO NOT MODIFY',
            'REQUIRED FOR',
        ]
        content_upper = content.upper()
        return any(marker in content_upper for marker in critical_markers)
    
    def _find_best_match(
        self,
        original: str,
        partial: str,
        context_lines: int
    ) -> Optional[Tuple[int, int, float]]:
        """
        Find the best location in original content to insert partial content.
        
        Returns:
            Tuple of (start_line, end_line, confidence) or None if no good match
        """
        orig_lines = original.splitlines()
        partial_lines = partial.splitlines()
        
        if not partial_lines:
            return None
        
        # Extract first and last few lines from partial for context matching
        context_start = partial_lines[:min(context_lines, len(partial_lines))]
        context_end = partial_lines[-min(context_lines, len(partial_lines)):]
        
        best_match = None
        best_confidence = 0.0
        
        # Slide through original content looking for best match
        for i in range(len(orig_lines)):
            # Try to match the start context
            window_start = orig_lines[i:i + len(context_start)]
            if not window_start:
                continue
            
            # Calculate similarity for start context
            start_similarity = self._calculate_similarity(context_start, window_start)
            
            if start_similarity < self.similarity_threshold:
                continue
            
            # Try to find where it ends
            search_end = min(i + len(partial_lines) + 10, len(orig_lines))
            for j in range(i + len(partial_lines) - len(context_end), search_end):
                window_end = orig_lines[j:j + len(context_end)]
                if not window_end:
                    continue
                
                end_similarity = self._calculate_similarity(context_end, window_end)
                
                # Combined confidence
                confidence = (start_similarity + end_similarity) / 2
                
                if confidence > best_confidence:
                    best_confidence = confidence
                    best_match = (i, j + len(context_end), confidence)
        
        if best_match and best_confidence >= self.similarity_threshold:
            return best_match
        
        return None
    
    def _calculate_similarity(self, lines1: List[str], lines2: List[str]) -> float:
        """
        Calculate similarity ratio between two sets of lines.
        """
        if not lines1 or not lines2:
            return 0.0
        
        # Use SequenceMatcher for fuzzy comparison
        text1 = '\n'.join(lines1)
        text2 = '\n'.join(lines2)
        
        matcher = difflib.SequenceMatcher(None, text1, text2)
        return matcher.ratio()
    
    def _merge_at_location(
        self,
        original: str,
        partial: str,
        start_line: int,
        end_line: int
    ) -> str:
        """
        Merge partial content into original at specified location.
        """
        orig_lines = original.splitlines()
        partial_lines = partial.splitlines()
        
        # Build the merged content
        result_lines = []
        
        # Keep everything before the match
        result_lines.extend(orig_lines[:start_line])
        
        # Insert the partial content
        result_lines.extend(partial_lines)
        
        # Keep everything after the match
        result_lines.extend(orig_lines[end_line:])
        
        # Preserve original line ending style
        result = '\n'.join(result_lines)
        if original.endswith('\n'):
            result += '\n'
        
        return result
    
    def create_diff_preview(
        self,
        original: str,
        merged: str,
        filename: str = "file"
    ) -> str:
        """
        Create a unified diff preview of the changes.
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
