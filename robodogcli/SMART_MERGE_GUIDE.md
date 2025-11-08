# Smart Merge Implementation Guide

## Overview
The SmartMerge feature intelligently applies partial LLM output to existing files by finding the best location to insert changes, even when the LLM returns only a substring of the full file.

## How It Works

### 1. Detection
SmartMerge automatically detects if the LLM output is:
- **Complete file replacement**: Similar line count, starts with file headers
- **Partial content**: Substring that needs to be merged into existing file
- **Unified diff**: Already handled by existing `DiffService`

### 2. Fuzzy Matching
When partial content is detected, SmartMerge:
1. Extracts context lines from the start and end of the partial content
2. Slides through the original file looking for matching context
3. Calculates similarity scores using `difflib.SequenceMatcher`
4. Finds the best match location with confidence >= 60%

### 3. Intelligent Merging
Once a match is found:
1. Keeps all lines before the match
2. Inserts the new partial content
3. Keeps all lines after the match
4. Preserves original line ending style

## Integration Points

### In `todo_util.py`

Add SmartMerge to the file writing logic around line 420-430:

```python
# After checking for unified diff, before writing:
if self._smart_merge and not diff_srv.is_unified_diff(content_to_write):
    # Try smart merge for partial content
    orig_content = self._file_service.safe_read_file(dest_path)
    merged_content, success, message = self._smart_merge.apply_partial_content(
        orig_content,
        content_to_write,
        context_lines=3
    )
    if success:
        logger.info(f"Smart merge applied: {message}", extra={'log_color': 'HIGHLIGHT'})
        content_to_write = merged_content
    else:
        logger.warning(f"Smart merge failed: {message}, using full replacement", extra={'log_color': 'DELTA'})

self._file_service.write_file(dest_path, content_to_write)
```

### Configuration

Enable/disable smart merge in `TodoUtilService.__init__`:

```python
def __init__(self, ..., enable_smart_merge=True):
    self._smart_merge = SmartMerge(similarity_threshold=0.6) if enable_smart_merge else None
```

## Usage Examples

### Example 1: LLM Returns Middle Section

**Original file (100 lines):**
```python
def function_a():
    pass

def function_b():
    # old implementation
    return old_value

def function_c():
    pass
```

**LLM returns (partial, lines 5-7):**
```python
def function_b():
    # new implementation
    return new_value
```

**Result:** SmartMerge finds the matching context and replaces only `function_b`, keeping `function_a` and `function_c` intact.

### Example 2: LLM Returns Complete File

**LLM returns 95 lines** (similar to original 100 lines)

**Result:** SmartMerge detects this as a complete file replacement and uses it directly.

### Example 3: LLM Returns Unified Diff

**LLM returns:**
```diff
--- a/file.py
+++ b/file.py
@@ -5,3 +5,3 @@
-    return old_value
+    return new_value
```

**Result:** Existing `DiffService.apply_unified_diff()` handles this (SmartMerge is skipped).

## Configuration Options

### Similarity Threshold
```python
SmartMerge(similarity_threshold=0.6)  # 60% match required
```

- **0.5-0.6**: Lenient matching (may have false positives)
- **0.7-0.8**: Strict matching (recommended for production)
- **0.9+**: Very strict (may miss valid matches)

### Context Lines
```python
apply_partial_content(original, partial, context_lines=3)
```

- **1-2**: Fast but less accurate
- **3-5**: Balanced (recommended)
- **6+**: Slower but more accurate

## Logging

SmartMerge provides detailed logging:

```
INFO: Smart merge applied: Merged at lines 45-52 (confidence: 87%)
WARNING: Smart merge failed: No match found - used as complete replacement
DEBUG: Similarity score: 0.73 for lines 45-48
```

## Testing

Test with various scenarios:

1. **Partial middle section**
2. **Partial start of file**
3. **Partial end of file**
4. **Complete file with minor changes**
5. **Unified diff (should skip SmartMerge)**

## Fallback Behavior

If SmartMerge fails to find a good match:
1. Logs a warning
2. Falls back to complete file replacement
3. Returns `success=False` with explanation

This ensures the system never fails completely - it just uses the LLM output as-is.

## Performance

- **Fast**: O(n*m) where n=original lines, m=partial lines
- **Typical**: <100ms for files up to 1000 lines
- **Memory**: Minimal overhead (only stores line arrays)

## Future Enhancements

1. **Multi-section merging**: Handle multiple partial sections in one LLM response
2. **Conflict resolution**: Interactive mode for ambiguous matches
3. **Learning**: Adjust threshold based on success rate
4. **Preview mode**: Show diff before applying

## Troubleshooting

### Issue: SmartMerge always uses complete replacement
**Solution**: Lower `similarity_threshold` to 0.5 or increase `context_lines` to 5

### Issue: SmartMerge merges at wrong location
**Solution**: Increase `similarity_threshold` to 0.8 for stricter matching

### Issue: Performance is slow
**Solution**: Reduce `context_lines` to 2 or disable for large files (>5000 lines)

## API Reference

### SmartMerge Class

```python
class SmartMerge:
    def __init__(self, similarity_threshold: float = 0.6)
    
    def apply_partial_content(
        self,
        original_content: str,
        partial_content: str,
        context_lines: int = 3
    ) -> Tuple[str, bool, str]:
        """
        Returns: (merged_content, success, message)
        """
    
    def create_diff_preview(
        self,
        original: str,
        merged: str,
        filename: str = "file"
    ) -> str:
        """
        Returns: unified diff string
        """
```

## Example Integration

Complete example in `todo_util.py`:

```python
from smart_merge import SmartMerge

class TodoUtilService:
    def __init__(self, ..., enable_smart_merge=True):
        self._smart_merge = SmartMerge(similarity_threshold=0.7) if enable_smart_merge else None
    
    def _write_parsed_files(self, parsed_files, task, commit_file, base_folder, current_filename):
        # ... existing code ...
        
        if commit_file and is_update:
            orig_content = self._file_service.safe_read_file(dest_path)
            content_to_write = body_raw
            
            # Check if unified diff
            if diff_srv and diff_srv.is_unified_diff(content_to_write):
                content_to_write = diff_srv.apply_unified_diff(content_to_write, orig_content)
            # Try smart merge for partial content
            elif self._smart_merge:
                merged, success, msg = self._smart_merge.apply_partial_content(
                    orig_content, content_to_write, context_lines=3
                )
                if success:
                    logger.info(f"✓ Smart merge: {msg}")
                    content_to_write = merged
                    # Optional: show diff preview
                    diff_preview = self._smart_merge.create_diff_preview(
                        orig_content, merged, rel
                    )
                    logger.debug(f"Diff preview:\n{diff_preview}")
            
            self._file_service.write_file(dest_path, content_to_write)
```
