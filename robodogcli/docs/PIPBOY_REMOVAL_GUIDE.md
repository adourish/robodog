# Pip-Boy Removal Guide

## Overview

This guide provides step-by-step instructions to remove the Pip-Boy UI feature from RoboDog CLI and ensure all functionality is preserved.

## Why Remove Pip-Boy?

1. **Complexity** - Adds significant code complexity
2. **Maintenance burden** - Hard to maintain alongside React app
3. **Redundancy** - React app provides better visual UI
4. **Simplification** - Standard CLI is cleaner and more reliable

## What to Remove

### 1. Command Line Argument

**File:** `cli.py` (around line 451)

**Remove:**
```python
parser.add_argument('--pipboy', action='store_true',
                    help='enable refreshing terminal UI (ANSI-based)')
```

### 2. Pip-Boy Initialization

**File:** `cli.py` (around line 528-900)

**Remove entire section:**
```python
# Initialize Simple UI if requested
pipboy_ui = None
if args.pipboy:
    try:
        pipboy_ui = SimpleUIWrapper(svc)
        
        # Set up command callback
        def handle_command(line):
            # ... hundreds of lines of pipboy command handling
            
        pipboy_ui.set_command_callback(handle_command)
        pipboy_ui.start()
        
    except Exception as e:
        logging.error(f"Failed to start Pip-Boy UI: {e}")
        pipboy_ui = None
```

### 3. Function Signature

**File:** `cli.py` (around line 180)

**Change:**
```python
# FROM:
def interact(svc: RobodogService, app_instance: RobodogApp, pipboy_ui=None):

# TO:
def interact(svc: RobodogService, app_instance: RobodogApp):
```

### 4. Conditional Outputs

**File:** `cli.py` (multiple locations)

**Pattern to find and fix:**
```python
# FIND:
if pipboy_ui:
    pipboy_ui.set_output(output)
else:
    print(output)

# REPLACE WITH:
print(output)
```

**Another pattern:**
```python
# FIND:
if pipboy_ui:
    pipboy_ui.log_status(message, "INFO")

# REMOVE (or replace with logging.info if needed)
```

### 5. Function Call

**File:** `cli.py` (around line 900)

**Change:**
```python
# FROM:
interact(svc, app_instance, pipboy_ui)

# TO:
interact(svc, app_instance)
```

## Automated Removal Script

Create a Python script to automate the removal:

```python
#!/usr/bin/env python3
"""
Script to remove Pip-Boy references from cli.py
"""

import re

def remove_pipboy_from_cli():
    with open('robodog/cli.py', 'r', encoding='utf-8') as f:
        content = f.read()
    
    # Remove --pipboy argument
    content = re.sub(
        r"parser\.add_argument\('--pipboy'.*?\n.*?help=.*?\)",
        "",
        content,
        flags=re.DOTALL
    )
    
    # Remove pipboy_ui parameter from interact function
    content = content.replace(
        "def interact(svc: RobodogService, app_instance: RobodogApp, pipboy_ui=None):",
        "def interact(svc: RobodogService, app_instance: RobodogApp):"
    )
    
    # Remove pipboy_ui initialization section
    # This is complex - manual review recommended
    
    # Remove pipboy_ui conditionals (simple cases)
    content = re.sub(
        r"if pipboy_ui:\s+pipboy_ui\.set_output\((.*?)\)\s+else:\s+print\(\1\)",
        r"print(\1)",
        content
    )
    
    # Remove pipboy_ui log_status calls
    content = re.sub(
        r"if pipboy_ui:\s+pipboy_ui\.log_status\(.*?\)",
        "",
        content
    )
    
    # Update interact() call
    content = content.replace(
        "interact(svc, app_instance, pipboy_ui)",
        "interact(svc, app_instance)"
    )
    
    # Write back
    with open('robodog/cli.py', 'w', encoding='utf-8') as f:
        f.write(content)
    
    print("✅ Pip-Boy references removed from cli.py")

if __name__ == "__main__":
    remove_pipboy_from_cli()
```

## Manual Cleanup Steps

Due to the complexity of cli.py, manual review is recommended:

### Step 1: Backup
```bash
cp robodog/cli.py robodog/cli.py.backup
```

### Step 2: Remove --pipboy Argument

Search for:
```python
parser.add_argument('--pipboy'
```

Delete the entire argument definition.

### Step 3: Remove Pip-Boy Initialization

Search for:
```python
pipboy_ui = None
if args.pipboy:
```

Delete from this line until the end of the `if args.pipboy:` block (around 400 lines).

### Step 4: Clean Up interact() Function

Search for:
```python
def interact(svc: RobodogService, app_instance: RobodogApp, pipboy_ui=None):
```

Remove `, pipboy_ui=None` parameter.

Then search for all `if pipboy_ui:` blocks and:
- Keep the `else:` block content
- Delete the `if pipboy_ui:` and `else:` lines

### Step 5: Update interact() Call

Search for:
```python
interact(svc, app_instance, pipboy_ui)
```

Change to:
```python
interact(svc, app_instance)
```

### Step 6: Remove Unused Imports

If SimpleUIWrapper is no longer used, remove:
```python
from simple_ui import SimpleUIWrapper
```

### Step 7: Test

```bash
python robodog/cli.py --help
# Should not show --pipboy option

python robodog/cli.py
# Should work normally without errors
```

## What to Keep

### Keep SimpleUI

The `simple_ui.py` file provides a lightweight alternative and should be kept:
- It's cleaner than Pip-Boy
- Can be used optionally
- Doesn't require complex integration

### Keep Standard CLI

The standard CLI (without Pip-Boy) is the main interface:
- Simple print() statements
- Standard logging
- Works everywhere

## Alternative: Use React App

For users who want a visual UI, recommend the React app:

```bash
# Start server
python robodog\cli.py --port 2500 --token testtoken

# Open browser
http://localhost:3000
```

## Testing After Removal

### Test 1: Basic Commands
```bash
python robodog\cli.py
/help
/models
/model openai/gpt-4
```

### Test 2: File Operations
```bash
/map scan
/map find TodoManager
```

### Test 3: Agent Loop
```bash
python robodog\cli.py --agent-loop
/todo
```

### Test 4: MCP Server
```bash
python robodog\cli.py --port 2500
# Should start without errors
```

## Expected Results

### Before Removal
```bash
$ python robodog\cli.py --help
...
--pipboy              enable refreshing terminal UI (ANSI-based)
...

$ python robodog\cli.py --pipboy
# Starts with Pip-Boy UI
```

### After Removal
```bash
$ python robodog\cli.py --help
...
# No --pipboy option
...

$ python robodog\cli.py
# Starts with standard CLI
robodog CLI — type /help to list commands.
[openai/gpt-4]»
```

## Rollback Plan

If issues occur:

```bash
# Restore backup
cp robodog/cli.py.backup robodog/cli.py

# Or use git
git checkout robodog/cli.py
```

## Summary

**Removing:**
- `--pipboy` command line flag
- All `pipboy_ui` variable references
- Pip-Boy initialization code (~400 lines)
- Conditional `if pipboy_ui:` blocks

**Keeping:**
- Standard CLI with print() statements
- All functionality (just different output method)
- SimpleUI as optional alternative
- React app as primary visual UI

**Benefits:**
- Simpler codebase (-400 lines)
- Easier maintenance
- More reliable
- Better focus on React app

**Next Steps:**
1. Backup cli.py
2. Remove Pip-Boy code
3. Test thoroughly
4. Update documentation

---

*Estimated Time: 30-60 minutes*
*Risk Level: Medium (large file, many changes)*
*Recommendation: Manual review + testing*
