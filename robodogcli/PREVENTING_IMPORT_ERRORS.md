# Preventing Import Errors with SmartMerge

## The Problem

When SmartMerge or LLM makes changes to Python files, it may accidentally remove or modify critical import statements, leading to errors like:

```
NameError: name 'Dict' is not defined. Did you mean: 'dict'?
```

## Solutions Implemented

### 1. **Protective Comments**

Add protective comments around critical sections in your code:

```python
# CRITICAL IMPORTS - DO NOT REMOVE OR MODIFY - REQUIRED FOR TYPE HINTS AND FUNCTIONALITY
import os
import re
from typing import List, Optional, Dict, Callable, Any, Tuple
# ... other imports
# END CRITICAL IMPORTS
```

**Benefits:**
- Clear visual marker for humans and AI
- SmartMerge detects these markers and is more conservative
- Prevents accidental removal during partial merges

### 2. **SmartMerge Protection**

SmartMerge now includes `_has_critical_section()` method that:
- Detects protective comments (`CRITICAL IMPORTS`, `DO NOT REMOVE`, `DO NOT MODIFY`, `REQUIRED FOR`)
- Increases caution when merging files with critical sections
- Logs warnings when attempting to modify protected sections

### 3. **File Structure Best Practices**

**Always structure Python files like this:**

```python
# file: myfile.py
#!/usr/bin/env python3
"""Module docstring."""

# CRITICAL IMPORTS - DO NOT REMOVE OR MODIFY
import standard_lib
from typing import TypeHints
from third_party import Package
try:
    from .relative import Module
except ImportError:
    from relative import Module
# END CRITICAL IMPORTS

# Module-level constants
CONSTANT = "value"

# Classes and functions
class MyClass:
    pass
```

## How to Protect Your Files

### Step 1: Add Protective Comments

For any file with type hints or critical imports:

```python
# CRITICAL IMPORTS - DO NOT REMOVE OR MODIFY - REQUIRED FOR TYPE HINTS AND FUNCTIONALITY
from typing import Dict, Any, Tuple, List, Optional
# END CRITICAL IMPORTS
```

### Step 2: Use Descriptive Markers

You can use any of these markers (case-insensitive):
- `CRITICAL IMPORTS`
- `DO NOT REMOVE`
- `DO NOT MODIFY`
- `REQUIRED FOR`

Example:
```python
# DO NOT REMOVE - Required for application startup
import critical_module
```

### Step 3: Test After LLM Changes

After running any LLM task that modifies Python files:

```bash
# Quick syntax check
python -m py_compile robodog/todo.py

# Or run the application
python robodog/cli.py --help
```

## SmartMerge Configuration

SmartMerge can be configured in `todo_util.py`:

```python
# Default settings
self._smart_merge = SmartMerge(
    similarity_threshold=0.6  # 60% match required
)

# More conservative (for files with critical sections)
self._smart_merge = SmartMerge(
    similarity_threshold=0.8  # 80% match required
)
```

## What SmartMerge Does

### When Original Has Critical Sections

1. **Detects markers** in original file
2. **Checks partial content** for same markers
3. **Logs warning** if attempting to modify critical sections
4. **Requires higher confidence** for merge operations

### Logging Output

You'll see logs like:
```
INFO: Original has critical sections - requiring higher confidence for merge
WARNING: Partial content contains critical section markers - using as complete replacement with caution
```

## Recovery Steps

If imports are accidentally removed:

### Quick Fix
```python
# Add back the missing imports at the top of the file
from typing import Dict, Any, Tuple, List, Optional
```

### Full Recovery
1. Check git history: `git diff HEAD~1 robodog/todo.py`
2. Restore imports from previous version
3. Add protective comments
4. Test the file: `python -m py_compile robodog/todo.py`

## Prevention Checklist

Before running LLM tasks on Python files:

- [ ] Add protective comments around imports
- [ ] Verify file has proper structure (imports at top)
- [ ] Check SmartMerge similarity threshold
- [ ] Review LLM prompt to avoid requesting import changes
- [ ] Have git backup or version control

After LLM tasks:

- [ ] Run syntax check: `python -m py_compile <file>`
- [ ] Check for import errors
- [ ] Review diff: `git diff <file>`
- [ ] Test application startup

## Files That Need Protection

Priority files to protect:

1. **Core service files**
   - `todo.py` - Main task service
   - `service.py` - LLM service
   - `todo_util.py` - Utility functions
   - `task_manager.py` - Task management

2. **Parser files**
   - `task_parser.py` - Task parsing
   - `parse_service.py` - LLM output parsing

3. **Any file with type hints**
   - Files using `Dict`, `List`, `Tuple`, `Optional`, `Any`
   - Files with `from typing import ...`

## Example: Protected File

```python
# file: example.py
#!/usr/bin/env python3
"""Example of a properly protected file."""

# CRITICAL IMPORTS - DO NOT REMOVE OR MODIFY - REQUIRED FOR TYPE HINTS AND FUNCTIONALITY
import os
import sys
from pathlib import Path
from typing import Dict, List, Optional, Any, Tuple
from datetime import datetime
# END CRITICAL IMPORTS

# Safe to modify below this line
logger = logging.getLogger(__name__)

class ExampleService:
    def __init__(self, config: Dict[str, Any]):
        self.config = config
    
    def process(self, data: List[str]) -> Tuple[bool, str]:
        # Implementation here
        pass
```

## Troubleshooting

### Error: "NameError: name 'Dict' is not defined"

**Cause:** Missing `from typing import Dict`

**Fix:**
```python
from typing import Dict, Any, Tuple, List, Optional
```

### Error: "ImportError: cannot import name 'ParseService'"

**Cause:** Missing import statement

**Fix:**
```python
try:
    from .parse_service import ParseService
except ImportError:
    from parse_service import ParseService
```

### SmartMerge Removes Imports Anyway

**Cause:** LLM output doesn't include imports, SmartMerge treats it as partial content

**Fix:**
1. Increase similarity threshold to 0.8
2. Add more protective comments
3. Review LLM prompt to request complete files only

## Best Practices

1. **Always use protective comments** for critical code
2. **Keep imports at the top** of files
3. **Group imports logically** (stdlib, third-party, local)
4. **Test after every LLM change**
5. **Use version control** (git) for easy recovery
6. **Review diffs** before committing changes
7. **Configure SmartMerge** appropriately for your use case

## Summary

✅ **Add protective comments** around critical imports
✅ **SmartMerge detects and respects** these markers
✅ **Test files** after LLM modifications
✅ **Use version control** for safety
✅ **Configure thresholds** based on file criticality

With these protections in place, import errors should be rare and easy to recover from!
