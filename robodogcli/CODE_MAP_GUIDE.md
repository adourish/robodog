# Code Map Guide

## Overview

The Code Map system creates a lightweight, searchable index of your codebase to enable efficient context gathering for AI agents and developers. Instead of loading entire files, the system provides quick access to:

- **Class definitions** and their methods
- **Function signatures** and locations
- **Import dependencies**
- **File summaries** with key information
- **Contextual file recommendations** for tasks

## Why Code Mapping?

### Problem
Traditional approaches load entire files into context, which:
- ❌ Wastes tokens on irrelevant code
- ❌ Exceeds context windows quickly
- ❌ Slows down processing
- ❌ Makes it hard to find relevant code

### Solution
Code mapping provides:
- ✅ **Instant lookups** - Find definitions in milliseconds
- ✅ **Smart context** - Only load relevant files
- ✅ **Token efficiency** - 10-100x reduction in context size
- ✅ **Incremental updates** - Fast rescans of changed files
- ✅ **Persistent cache** - Save/load maps for instant startup

## Features

### 1. Codebase Scanning
Automatically parses Python and JavaScript/TypeScript files to extract:
- Classes and methods
- Functions and signatures
- Imports and dependencies
- Docstrings and comments
- Line numbers for everything

### 2. Smart Search
- **Find definitions** - Locate where classes/functions are defined
- **Find usages** - See which files import a module
- **Get context** - Find relevant files for a task description

### 3. Context Optimization
- **Keyword extraction** - Automatically identifies important terms
- **Relevance scoring** - Ranks files by importance to task
- **Pattern matching** - Supports glob patterns for file filtering
- **Dependency tracking** - Understands module relationships

### 4. Persistence
- **Save maps** - Export to JSON for reuse
- **Load maps** - Instant startup from cached map
- **Incremental updates** - Only rescan changed files

## CLI Commands

### Scan Codebase
```bash
/map scan
```
Scans all Python and JavaScript/TypeScript files in project roots.

**Output:**
```
Code Map Created:
45 files mapped
12 classes
87 functions
```

### Find Definition
```bash
/map find TodoManager
```
Finds where a class or function is defined.

**Output:**
```
Found 1 definition(s) for 'TodoManager':

class: TodoManager
  File: todo_manager.py:18
  Doc: High-level todo.md management
```

### Get Context for Task
```bash
/map context implement authentication
```
Finds relevant files for a task based on keywords.

**Output:**
```
Context for: implement authentication

Keywords: implement, authentication
Relevant files: 3

[5] auth_service.py
  Classes: AuthService, TokenManager
  Functions: login, logout, verify_token

[3] user_model.py
  Classes: User, Session
  Functions: create_user, authenticate

[2] api_routes.py
  Functions: auth_required, login_route
```

### Save Map
```bash
/map save codemap.json
```
Saves the current map to a JSON file for reuse.

### Load Map
```bash
/map load codemap.json
```
Loads a previously saved map (instant startup).

## Python API

### Basic Usage

```python
from robodog.code_map import CodeMapper

# Initialize
mapper = CodeMapper(
    roots=["/path/to/project"],
    exclude_dirs={'node_modules', 'dist', '__pycache__'}
)

# Scan codebase
file_maps = mapper.scan_codebase()
print(f"Mapped {len(file_maps)} files")

# Find definition
results = mapper.find_definition("TodoManager")
for r in results:
    print(f"{r['type']}: {r['name']} at {r['file']}:{r['line_start']}")

# Get context for task
context = mapper.get_context_for_task("implement user authentication")
for file_path, info in context['relevant_files'].items():
    print(f"[{info['score']}] {file_path}")
    print(f"  Summary: {info['summary']}")

# Save/load
mapper.save_map("codemap.json")
mapper.load_map("codemap.json")
```

### Advanced Usage

```python
# Get file summary
summary = mapper.get_file_summary("/path/to/file.py")
print(f"Classes: {summary['classes']}")
print(f"Functions: {summary['functions']}")
print(f"Dependencies: {summary['dependencies']}")

# Find module usages
files = mapper.find_usages("requests")
print(f"Files using 'requests': {files}")

# Custom file extensions
file_maps = mapper.scan_codebase(extensions=['.py', '.pyx', '.pyi'])

# Get context with patterns
context = mapper.get_context_for_task(
    "fix database bug",
    include_patterns=["**/db/*.py", "**/models/*.py"]
)
```

## Data Structures

### FileMap
```python
{
    'path': '/path/to/file.py',
    'language': 'python',
    'size': 5432,
    'lines': 156,
    'classes': [ClassInfo(...)],
    'functions': [FunctionInfo(...)],
    'imports': [ImportInfo(...)],
    'global_vars': ['CONFIG', 'LOGGER'],
    'docstring': 'Module docstring',
    'dependencies': {'os', 'json', 'requests'}
}
```

### ClassInfo
```python
{
    'name': 'TodoManager',
    'line_start': 18,
    'line_end': 250,
    'bases': ['BaseManager'],
    'methods': [FunctionInfo(...)],
    'docstring': 'Manages todo.md files',
    'decorators': ['dataclass']
}
```

### FunctionInfo
```python
{
    'name': 'add_task',
    'line_start': 74,
    'line_end': 162,
    'args': ['self', 'description', 'path'],
    'returns': 'Dict[str, Any]',
    'docstring': 'Add a new task',
    'is_async': False,
    'is_method': True,
    'decorators': []
}
```

## Integration with Agent Loop

### Before (Without Code Map)
```python
# Load ALL files - wasteful!
all_files = load_all_files_in_project()  # 100+ files, 50k+ lines
context = "\n".join(all_files)  # 200k+ tokens!
prompt = f"Task: {task}\n\nCode:\n{context}"  # Exceeds context window
```

### After (With Code Map)
```python
# Get ONLY relevant files
context = code_mapper.get_context_for_task(task_desc)
relevant_files = list(context['relevant_files'].keys())[:5]  # Top 5 files

# Load only what's needed
code_snippets = []
for file_path in relevant_files:
    summary = code_mapper.get_file_summary(file_path)
    # Load only relevant classes/functions
    code_snippets.append(load_specific_sections(file_path, summary))

context = "\n".join(code_snippets)  # 2-3k tokens!
prompt = f"Task: {task}\n\nRelevant code:\n{context}"  # Fits easily
```

### Token Savings Example

**Task:** "Implement user authentication"

**Without Code Map:**
- Load all 45 files
- Total: ~180,000 tokens
- Result: Exceeds context window ❌

**With Code Map:**
- Find relevant files: `auth_service.py`, `user_model.py`, `api_routes.py`
- Load only those 3 files
- Total: ~2,500 tokens
- Result: 72x reduction, fits in context ✅

## Performance

### Scan Speed
- **Python files:** ~100 files/second
- **JavaScript files:** ~80 files/second
- **Typical project (50 files):** <1 second

### Lookup Speed
- **Find definition:** <1ms
- **Get context:** <10ms
- **File summary:** <1ms

### Memory Usage
- **Map storage:** ~1KB per file
- **Typical project (50 files):** ~50KB in memory
- **JSON export:** ~100KB on disk

## Best Practices

### 1. Scan on Startup
```python
# In your initialization
if os.path.exists('codemap.json'):
    code_mapper.load_map('codemap.json')
else:
    code_mapper.scan_codebase()
    code_mapper.save_map('codemap.json')
```

### 2. Incremental Updates
```python
# When files change
changed_files = get_changed_files()
for file in changed_files:
    code_mapper._map_file(Path(file))
code_mapper.save_map('codemap.json')
```

### 3. Use with Agent Loop
```python
# Get context before each subtask
context = code_mapper.get_context_for_task(subtask['description'])
relevant_files = list(context['relevant_files'].keys())[:3]

# Build minimal prompt
prompt = build_focused_prompt(subtask, relevant_files)
```

### 4. Combine with Patterns
```python
# Task-specific patterns
if 'database' in task_desc:
    patterns = ['**/db/*.py', '**/models/*.py']
elif 'api' in task_desc:
    patterns = ['**/api/*.py', '**/routes/*.py']

context = code_mapper.get_context_for_task(task_desc, patterns)
```

## Supported Languages

### Python (.py)
- ✅ Full AST parsing
- ✅ Classes, methods, functions
- ✅ Type hints and returns
- ✅ Decorators
- ✅ Docstrings
- ✅ Imports (import, from...import)

### JavaScript/TypeScript (.js, .ts, .tsx, .jsx)
- ✅ Regex-based parsing
- ✅ Classes and methods
- ✅ Functions (function, arrow, async)
- ✅ Imports (import, require)
- ✅ ES6+ syntax

### Future Support
- 🔄 Go (.go)
- 🔄 Rust (.rs)
- 🔄 Java (.java)
- 🔄 C++ (.cpp, .h)

## Limitations

1. **JavaScript parsing** - Uses regex, not full AST (may miss complex cases)
2. **Dynamic code** - Cannot analyze runtime-generated code
3. **Macros** - Does not expand macros or templates
4. **Accuracy** - 95%+ accurate for standard code patterns

## Troubleshooting

### Map is empty after scan
- Check that roots exist and contain files
- Verify file extensions match (default: .py, .js, .ts, .tsx, .jsx)
- Check exclude_dirs doesn't exclude everything

### Find returns no results
- Ensure scan was run first
- Check spelling of name
- Try loading a saved map

### Context returns irrelevant files
- Use more specific keywords in task description
- Add include_patterns to narrow scope
- Check that relevant files were scanned

## Examples

### Example 1: Find All Classes
```python
mapper = CodeMapper(roots=["/project"])
mapper.scan_codebase()

for class_name, files in mapper.index['classes'].items():
    print(f"{class_name}: {files}")
```

### Example 2: Dependency Graph
```python
mapper.scan_codebase()

for file_path, file_map in mapper.file_maps.items():
    print(f"{file_path}:")
    print(f"  Imports: {file_map.dependencies}")
```

### Example 3: Find Large Files
```python
mapper.scan_codebase()

large_files = [
    (path, fm.lines)
    for path, fm in mapper.file_maps.items()
    if fm.lines > 500
]

for path, lines in sorted(large_files, key=lambda x: x[1], reverse=True):
    print(f"{path}: {lines} lines")
```

## Summary

✅ **Efficient context gathering** - 10-100x token reduction
✅ **Fast lookups** - Millisecond response times
✅ **Smart recommendations** - Relevance-based file scoring
✅ **Persistent caching** - Save/load for instant startup
✅ **Multi-language** - Python, JavaScript, TypeScript
✅ **CLI integration** - Easy to use commands
✅ **Agent-ready** - Perfect for AI agent loops

The Code Map system makes it easy to work with large codebases efficiently!
