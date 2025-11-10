# Cascade Mode Parameter Validation Fix

## ✅ Issues Fixed

**Problem 1:** Steps failing with "Missing query or code_mapper"
**Problem 2:** Steps failing with "Missing prompt"
**Root Cause:** LLM-generated plans didn't include required parameters for actions

## 🔧 Solutions Implemented

### 1. Improved Planning Prompt (Lines 117-163)

**Before:**
```python
prompt = """Break down this task into parallel executable steps.
For each step, specify:
1. step_id: unique identifier
2. action: one of [read_file, edit_file, search, analyze, map_context, create_file]
3. params: parameters for the action
4. dependencies: list of step_ids that must complete first
"""
```

**After:**
```python
prompt = """Break down this task into parallel executable steps.

Available actions and REQUIRED parameters:
1. read_file: {"path": "full/path/to/file.py"}
2. edit_file: {"path": "file.py", "changes": "description"}
3. create_file: {"path": "file.py", "content": "file content"}
4. search: {"query": "search term"}
5. analyze: {"prompt": "what to analyze"}
6. map_context: {"task": "task description"}

IMPORTANT: Each action MUST include ALL required parameters!
"""
```

**Benefits:**
- ✅ LLM knows exactly what parameters each action needs
- ✅ Clear examples showing parameter format
- ✅ Explicit warning about required parameters

### 2. Better Error Messages (Lines 315-383)

**Before:**
```python
if not query or not self.code_mapper:
    raise ValueError("Missing query or code_mapper")
```

**After:**
```python
if not query:
    raise ValueError("Missing required parameter 'query' for search action")

if not self.code_mapper:
    logger.warning("Code mapper not available, returning empty results")
    return {'results': [], 'message': 'Code mapper not initialized'}
```

**Benefits:**
- ✅ Clear error messages specify which parameter is missing
- ✅ Graceful degradation when services unavailable
- ✅ Better debugging information

### 3. Separate Parameter and Service Validation

**Updated Actions:**

#### `_action_search` (Lines 347-359)
```python
async def _action_search(self, params: Dict[str, Any]) -> Dict[str, Any]:
    """Search for code"""
    query = params.get('query')
    
    if not query:
        raise ValueError("Missing required parameter 'query' for search action")
    
    if not self.code_mapper:
        logger.warning("Code mapper not available, returning empty results")
        return {'results': [], 'message': 'Code mapper not initialized'}
    
    results = self.code_mapper.find_definition(query)
    return {'results': results}
```

#### `_action_analyze` (Lines 375-383)
```python
async def _action_analyze(self, params: Dict[str, Any]) -> str:
    """Analyze with LLM"""
    prompt = params.get('prompt')
    
    if not prompt:
        raise ValueError("Missing required parameter 'prompt' for analyze action")
    
    response = self.svc.ask(prompt)
    return response
```

#### `_action_read_file` (Lines 315-327)
```python
async def _action_read_file(self, params: Dict[str, Any]) -> str:
    """Read a file"""
    path = params.get('path')
    
    if not path:
        raise ValueError("Missing required parameter 'path' for read_file action")
    
    if not self.file_service:
        raise ValueError("File service not available")
    
    from pathlib import Path
    content = self.file_service.safe_read_file(Path(path))
    return content
```

#### `_action_map_context` (Lines 361-373)
```python
async def _action_map_context(self, params: Dict[str, Any]) -> Dict[str, Any]:
    """Get context from code map"""
    task = params.get('task')
    
    if not task:
        raise ValueError("Missing required parameter 'task' for map_context action")
    
    if not self.code_mapper:
        logger.warning("Code mapper not available, returning empty context")
        return {'context': '', 'message': 'Code mapper not initialized'}
    
    context = self.code_mapper.get_context_for_task(task)
    return context
```

#### `_action_create_file` (Lines 334-345)
```python
async def _action_create_file(self, params: Dict[str, Any]) -> str:
    """Create a new file"""
    path = params.get('path')
    content = params.get('content', '')
    
    if not path:
        raise ValueError("Missing required parameter 'path' for create_file action")
    
    with open(path, 'w', encoding='utf-8') as f:
        f.write(content)
    
    return f"Created {path}"
```

## 📊 Impact

### Before Fix
```
19:36:29: ❌ Step step_2 failed: Missing query or code_mapper
19:36:29: ❌ Step step_4 failed: Missing prompt
```

### After Fix
```
# If LLM provides proper parameters:
19:36:29: ✅ Step step_2 completed
19:36:29: ✅ Step step_4 completed

# If LLM forgets parameters:
19:36:29: ❌ Step step_2 failed: Missing required parameter 'query' for search action
19:36:29: ❌ Step step_4 failed: Missing required parameter 'prompt' for analyze action
```

## 🎯 Expected Behavior

### Good Plan (All Parameters Provided)
```json
[
  {
    "step_id": "step_1",
    "action": "map_context",
    "params": {"task": "find app.py files"},
    "dependencies": []
  },
  {
    "step_id": "step_2",
    "action": "search",
    "params": {"query": "class RobodogApp"},
    "dependencies": ["step_1"]
  },
  {
    "step_id": "step_3",
    "action": "read_file",
    "params": {"path": "robodog/app.py"},
    "dependencies": ["step_2"]
  },
  {
    "step_id": "step_4",
    "action": "analyze",
    "params": {"prompt": "Analyze the structure and main components of app.py"},
    "dependencies": ["step_3"]
  }
]
```

**Result:** All steps complete successfully ✅

### Bad Plan (Missing Parameters)
```json
[
  {
    "step_id": "step_1",
    "action": "search",
    "params": {},  // Missing 'query'
    "dependencies": []
  },
  {
    "step_id": "step_2",
    "action": "analyze",
    "params": {},  // Missing 'prompt'
    "dependencies": ["step_1"]
  }
]
```

**Result:** Clear error messages ✅
```
❌ Step step_1 failed: Missing required parameter 'query' for search action
❌ Step step_2 failed: Missing required parameter 'prompt' for analyze action
```

## 🚀 Usage

### Restart CLI to Load Fixed Code
```bash
# Stop current CLI (Ctrl+C)
# Restart with:
python robodog\cli.py --folders c:\projects\robodog\robodogcli --port 2500 --token testtoken --config config.yaml --model openai/o4-mini --agent-loop
```

### Test Cascade Command
```bash
# Simple test
/cascade run "analyze app.py structure"

# More complex test
/cascade run "find all Python files, read their imports, and summarize dependencies"
```

### Expected Output (Success)
```
19:36:16: 🌊 Starting cascade for task: analyze app.py structure...
19:36:29: 📋 Plan created: 4 steps
19:36:29: 🔄 Executing 1 steps in parallel...
19:36:29: ✅ Step step_1 completed
19:36:29: 🔄 Executing 1 steps in parallel...
19:36:29: ✅ Step step_2 completed
19:36:29: 🔄 Executing 1 steps in parallel...
19:36:29: ✅ Step step_3 completed
19:36:29: 🔄 Executing 1 steps in parallel...
19:36:29: ✅ Step step_4 completed
19:36:29: ✨ Cascade completed: 4/4 steps successful
```

### Expected Output (With Errors)
```
19:36:16: 🌊 Starting cascade for task: analyze app.py structure...
19:36:29: 📋 Plan created: 4 steps
19:36:29: 🔄 Executing 1 steps in parallel...
19:36:29: ✅ Step step_1 completed
19:36:29: 🔄 Executing 1 steps in parallel...
19:36:29: ❌ Step step_2 failed: Missing required parameter 'query' for search action
19:36:29: 🔍 Found 1 errors, attempting self-correction...
19:36:39: 💡 Correction suggestion: Add the 'query' parameter to step_2...
```

## 📝 Parameter Reference

| Action | Required Parameters | Optional Parameters | Example |
|--------|-------------------|-------------------|---------|
| **read_file** | `path` | - | `{"path": "robodog/app.py"}` |
| **edit_file** | `path`, `changes` | - | `{"path": "app.py", "changes": "add logging"}` |
| **create_file** | `path` | `content` | `{"path": "test.py", "content": "# test"}` |
| **search** | `query` | - | `{"query": "class RobodogApp"}` |
| **analyze** | `prompt` | - | `{"prompt": "Analyze structure"}` |
| **map_context** | `task` | - | `{"task": "find relevant files"}` |

## 🔍 Debugging Tips

### Check Plan Quality
The LLM's plan is logged at the start:
```
19:36:29: 📋 Plan created: 4 steps
```

If steps are failing, the plan likely has missing parameters.

### Check Error Messages
New error messages are very specific:
```
❌ Step step_2 failed: Missing required parameter 'query' for search action
```

This tells you exactly:
1. Which step failed (step_2)
2. Which parameter is missing ('query')
3. Which action it's for (search action)

### Use Self-Correction
The cascade mode will attempt to fix errors:
```
19:36:29: 🔍 Found 2 errors, attempting self-correction...
19:36:39: 💡 Correction suggestion: Add the 'query' parameter to step_2...
```

## ✅ Summary

**Fixed Issues:**
1. ✅ LLM now knows required parameters for each action
2. ✅ Clear error messages specify missing parameters
3. ✅ Graceful degradation when services unavailable
4. ✅ Better debugging information

**Files Modified:**
- `robodog/cascade_mode.py` (Lines 117-383)

**Package Rebuilt:**
- `robodogcli-2.6.16.tar.gz`
- `robodogcli-2.6.16-py3-none-any.whl`

**Status:** ✅ Fixed and Ready to Test
**Version:** 2.6.16
**Date:** November 9, 2025

---

**Restart the CLI to load the fixes!** 🎯
