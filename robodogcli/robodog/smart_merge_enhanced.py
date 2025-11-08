# file: smart_merge_enhanced.py
#!/usr/bin/env python3
"""
Enhanced SmartMerge with validation, safety checks, and better diagnostics.
"""
import logging
from typing import Tuple, Dict, Any
from smart_merge import SmartMerge

logger = logging.getLogger(__name__)


class EnhancedSmartMerge(SmartMerge):
    """
    Enhanced SmartMerge with:
    - Higher similarity threshold (0.75 vs 0.6)
    - Validation of merged content
    - Syntax checking for Python files
    - Better diagnostics and logging
    - Safety checks for critical sections
    """
    
    def __init__(self, similarity_threshold: float = 0.75):
        """
        Initialize with higher threshold for better accuracy.
        
        Args:
            similarity_threshold: Minimum similarity (0.75 recommended vs 0.6 default)
        """
        super().__init__(similarity_threshold)
        self.min_confidence = 0.7
        self.enable_validation = True
        self.max_size_change_ratio = 3.0  # Don't allow >3x size changes
        
        logger.info(f"EnhancedSmartMerge initialized: threshold={similarity_threshold}, "
                   f"validation={'enabled' if self.enable_validation else 'disabled'}")
    
    def apply_partial_content_safe(
        self,
        original_content: str,
        partial_content: str,
        context_lines: int = 5,
        validate: bool = True
    ) -> Tuple[str, bool, str, Dict[str, Any]]:
        """
        Safe version of apply_partial_content with validation and diagnostics.
        
        Args:
            original_content: Full original file content
            partial_content: Partial content from LLM
            context_lines: Number of context lines (5 recommended vs 3 default)
            validate: Whether to validate merged content
        
        Returns:
            Tuple of (merged_content, success, message, diagnostics)
        """
        diagnostics = {
            'original_lines': len(original_content.splitlines()),
            'partial_lines': len(partial_content.splitlines()),
            'merge_strategy': None,
            'confidence': 0.0,
            'validation_passed': False,
            'warnings': [],
            'is_python': False,
            'syntax_valid': True
        }
        
        logger.info(f"Starting safe merge: original={diagnostics['original_lines']} lines, "
                   f"partial={diagnostics['partial_lines']} lines")
        
        # Pre-validation checks
        if not partial_content or not partial_content.strip():
            logger.warning("Partial content is empty")
            return original_content, False, "Partial content is empty", diagnostics
        
        # Check if this is Python code
        diagnostics['is_python'] = self._is_python_file(original_content)
        
        # Validate syntax of partial content (for Python)
        if validate and diagnostics['is_python']:
            syntax_valid, syntax_error = self._validate_python_syntax(partial_content)
            diagnostics['syntax_valid'] = syntax_valid
            
            if not syntax_valid:
                warning = f"Partial content has syntax issues: {syntax_error}"
                diagnostics['warnings'].append(warning)
                logger.warning(warning)
                # Continue anyway, but log the warning
        
        # Perform the merge using parent class
        try:
            merged, success, message = self.apply_partial_content(
                original_content,
                partial_content,
                context_lines
            )
            
            diagnostics['merge_strategy'] = 'smart_merge' if success else 'replacement'
            
            logger.info(f"Merge result: success={success}, strategy={diagnostics['merge_strategy']}")
            
        except Exception as e:
            logger.error(f"Merge failed with exception: {e}")
            return original_content, False, f"Merge exception: {e}", diagnostics
        
        # Post-validation
        if success and validate and self.enable_validation:
            logger.info("Validating merged content...")
            validation_passed, validation_msg = self._validate_merged_content(
                original_content, merged, partial_content
            )
            diagnostics['validation_passed'] = validation_passed
            
            if not validation_passed:
                warning = f"Merge validation failed: {validation_msg}"
                diagnostics['warnings'].append(warning)
                logger.warning(warning)
                
                # Return original content if validation fails
                return original_content, False, warning, diagnostics
            
            logger.info("✅ Validation passed")
        
        return merged, success, message, diagnostics
    
    def _validate_merged_content(
        self,
        original: str,
        merged: str,
        partial: str
    ) -> Tuple[bool, str]:
        """
        Validate that merged content is reasonable and safe.
        
        Checks:
        1. Not empty
        2. Size change is reasonable
        3. Critical sections preserved
        4. Syntax valid (for Python)
        """
        # Check 1: Not empty
        if not merged.strip():
            return False, "Merged content is empty"
        
        # Check 2: Size change is reasonable
        orig_lines = len(original.splitlines())
        merged_lines = len(merged.splitlines())
        
        if orig_lines > 0:
            size_ratio = merged_lines / orig_lines
            if size_ratio < (1.0 / self.max_size_change_ratio) or size_ratio > self.max_size_change_ratio:
                return False, f"Merged size changed drastically: {size_ratio:.2f}x (limit: {self.max_size_change_ratio}x)"
        
        # Check 3: Critical sections preserved
        if self._has_critical_section(original):
            if not self._critical_sections_preserved(original, merged):
                return False, "Critical sections were removed or modified"
        
        # Check 4: Syntax validation for Python
        if self._is_python_file(original):
            syntax_valid, error = self._validate_python_syntax(merged)
            if not syntax_valid:
                return False, f"Merged content has syntax error: {error}"
        
        return True, "All validation checks passed"
    
    def _is_python_file(self, content: str) -> bool:
        """Check if content appears to be Python code."""
        if not content:
            return False
        
        lines = content.strip().splitlines()
        if not lines:
            return False
        
        # Check for Python indicators in first 10 lines
        indicators = ['import ', 'from ', 'def ', 'class ', 'if __name__', '#!/usr/bin/env python']
        first_lines = '\n'.join(lines[:10])
        
        return any(ind in first_lines for ind in indicators)
    
    def _validate_python_syntax(self, content: str) -> Tuple[bool, str]:
        """
        Validate Python syntax by attempting to compile.
        
        Returns:
            Tuple of (is_valid, error_message)
        """
        try:
            compile(content, '<string>', 'exec')
            return True, ""
        except SyntaxError as e:
            return False, f"Line {e.lineno}: {e.msg}"
        except Exception as e:
            return False, str(e)
    
    def _critical_sections_preserved(self, original: str, merged: str) -> bool:
        """
        Check that critical sections marked with special comments are preserved.
        
        Critical markers:
        - CRITICAL IMPORTS
        - DO NOT REMOVE
        - DO NOT MODIFY
        - REQUIRED FOR
        """
        critical_markers = [
            'CRITICAL IMPORTS',
            'DO NOT REMOVE',
            'DO NOT MODIFY',
            'REQUIRED FOR'
        ]
        
        original_upper = original.upper()
        merged_upper = merged.upper()
        
        for marker in critical_markers:
            if marker in original_upper:
                if marker not in merged_upper:
                    logger.warning(f"Critical marker '{marker}' was removed during merge")
                    return False
        
        return True
    
    def get_diagnostics_summary(self, diagnostics: Dict[str, Any]) -> str:
        """Create a human-readable summary of diagnostics."""
        lines = [
            f"Merge Diagnostics:",
            f"  Original: {diagnostics['original_lines']} lines",
            f"  Partial: {diagnostics['partial_lines']} lines",
            f"  Strategy: {diagnostics['merge_strategy']}",
            f"  Confidence: {diagnostics['confidence']:.2%}",
            f"  Validation: {'✅ Passed' if diagnostics['validation_passed'] else '❌ Failed'}",
        ]
        
        if diagnostics['is_python']:
            lines.append(f"  Python syntax: {'✅ Valid' if diagnostics['syntax_valid'] else '❌ Invalid'}")
        
        if diagnostics['warnings']:
            lines.append(f"  Warnings:")
            for warning in diagnostics['warnings']:
                lines.append(f"    - {warning}")
        
        return '\n'.join(lines)


# Convenience function for backward compatibility
def create_enhanced_smart_merge(similarity_threshold: float = 0.75) -> EnhancedSmartMerge:
    """
    Create an EnhancedSmartMerge instance with recommended settings.
    
    Args:
        similarity_threshold: Minimum similarity (default 0.75, recommended over 0.6)
    
    Returns:
        EnhancedSmartMerge instance
    """
    return EnhancedSmartMerge(similarity_threshold=similarity_threshold)
