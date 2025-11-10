# Quick Start: Advanced Analysis & Cascade Mode

## 🚀 Getting Started

### 1. Start RoboDog CLI

```bash
cd c:\Projects\robodog\robodogcli
python robodog\cli.py --folders c:\projects\robodog\robodogcli --port 2500 --token testtoken --model openai/o4-mini
```

### 2. Scan Your Codebase (Required First!)

```bash
[openai/o4-mini]» /map scan
```

**Output:**
```
Scanning codebase in 1 roots
Mapped 29 files
```

**⚠️ Important:** You MUST run `/map scan` before using `/analyze` commands!

## 📊 Advanced Analysis Commands

### Build Call Graph

Shows all function relationships in your codebase.

```bash
[openai/o4-mini]» /analyze callgraph
```

**Output:**
```
🔍 Building call graph...
✅ Functions: 245
   Total calls: 1,234
```

### Impact Analysis

Find what breaks if you change a function.

```bash
[openai/o4-mini]» /analyze impact TodoManager
```

**Output:**
```
🔍 Analyzing impact of 'TodoManager'...
📊 Impact analysis for TodoManager:
   Direct callers: 5
   Total impacted: 15
   Direct callers:
     - TodoService
     - cli
     - app
     - service
     - main
```

### Dependency Analysis

Show what a file imports (internal/external).

```bash
[openai/o4-mini]» /analyze deps robodog/cli.py
```

**Output:**
```
🔍 Analyzing dependencies for robodog/cli.py...
📦 Dependencies:
   Total imports: 25
   Internal: 12
   External: 13
   External packages:
     - argparse
     - json
     - logging
     - os
     - sys
     ...
```

### Codebase Statistics

Get overview of your codebase.

```bash
[openai/o4-mini]» /analyze stats
```

**Output:**
```
📊 Calculating codebase statistics...
🔍 Building call graph first...
   Total functions: 245
   Total calls: 1,234
   Avg calls/function: 5.0
   Total files: 29
   Most called functions:
     ask: 45 calls
     call_mcp: 38 calls
     read_file: 32 calls
     write_file: 28 calls
     parse_cmd: 25 calls
```

**Note:** If call graph isn't built yet, it will automatically build it first.

## 🌊 Cascade Mode

Run tasks with parallel execution (2-3x faster!).

```bash
[openai/o4-mini]» /cascade run create a hello world function
```

**Output:**
```
🌊 Running cascade for: create a hello world function
✅ Cascade completed:
   Steps: 5
   Successful: 5
   Failed: 0
   Duration: 12.3s
```

### Example Tasks for Cascade

```bash
# Implement a feature
/cascade run implement user authentication

# Refactor code
/cascade run refactor the file service module

# Add tests
/cascade run add unit tests for TodoManager

# Fix bugs
/cascade run fix error handling in cascade_mode.py
```

## 🎯 Common Workflows

### Workflow 1: Understand Impact Before Refactoring

```bash
# 1. Scan codebase
/map scan

# 2. Find the function
/map find TodoManager

# 3. Check impact
/analyze impact TodoManager

# 4. Check dependencies
/analyze deps robodog/todo_manager.py

# 5. Refactor with cascade
/cascade run refactor TodoManager to use async/await
```

### Workflow 2: Analyze New Codebase

```bash
# 1. Scan
/map scan

# 2. Get overview
/analyze stats

# 3. Find most complex functions
/analyze callgraph

# 4. Check specific module
/analyze deps robodog/service.py
```

### Workflow 3: Debug Issues

```bash
# 1. Find the function
/map find execute_subtask

# 2. Check who calls it
/analyze impact execute_subtask

# 3. Check dependencies
/analyze deps robodog/agent_loop.py

# 4. Fix with cascade
/cascade run add error handling to execute_subtask
```

## 🐛 Troubleshooting

### "Code map not scanned" Error

**Problem:**
```
⚠️  Code map not scanned. Run '/map scan' first.
```

**Solution:**
```bash
/map scan
```

**Note:** The command is `/map scan`, NOT `/analyze scan`!

### Empty Statistics (0 functions)

**Problem:**
```
Total functions: 0
Total calls: 0
```

**Solution:**
The code map needs to be scanned first:
```bash
/map scan
/analyze stats
```

### Function Not Found

**Problem:**
```
No definition found for 'MyFunction'
```

**Solutions:**
1. Check spelling (case-sensitive)
2. Rescan if you added new code:
   ```bash
   /map scan
   /analyze impact MyFunction
   ```

## 📱 React App Usage

All commands work the same in the React app!

1. Open http://localhost:3000
2. Hard refresh (Ctrl+Shift+R) to get latest build
3. Use same commands:

```
> /map scan
> /analyze callgraph
> /analyze impact TodoManager
> /cascade run implement feature X
```

## 💡 Pro Tips

### Tip 1: Always Scan First

Before using any `/analyze` commands, run `/map scan`:
```bash
/map scan
```

### Tip 2: Use Impact Analysis Before Big Changes

```bash
# Before refactoring
/analyze impact MyFunction

# Shows what will break
# Plan accordingly
```

### Tip 3: Check Dependencies for External Packages

```bash
/analyze deps myfile.py

# Shows all external packages used
# Helps with requirements.txt
```

### Tip 4: Use Cascade for Multi-Step Tasks

```bash
# Instead of manual steps
/cascade run implement login feature with JWT

# Cascade will:
# 1. Analyze requirements
# 2. Create files in parallel
# 3. Add tests
# 4. Self-correct errors
```

### Tip 5: Combine with Code Map

```bash
# Find relevant files
/map context authentication

# Check impact
/analyze impact AuthService

# Implement with cascade
/cascade run add OAuth support to authentication
```

## 🎯 Quick Reference

| Command | Purpose | Example |
|---------|---------|---------|
| `/map scan` | **Required first!** Scan codebase | `/map scan` |
| `/analyze callgraph` | Build call graph | `/analyze callgraph` |
| `/analyze impact <fn>` | Find what breaks | `/analyze impact TodoManager` |
| `/analyze deps <file>` | Show dependencies | `/analyze deps cli.py` |
| `/analyze stats` | Codebase overview | `/analyze stats` |
| `/cascade run <task>` | Parallel execution | `/cascade run add tests` |

## 🚀 Next Steps

1. **Try it now:**
   ```bash
   /map scan
   /analyze stats
   ```

2. **Explore your codebase:**
   ```bash
   /analyze callgraph
   /analyze impact <your_function>
   ```

3. **Use cascade mode:**
   ```bash
   /cascade run <your_task>
   ```

4. **Read full docs:**
   - `WINDSURF_FEATURES_IMPLEMENTED.md` - Complete feature guide
   - `WINDSURF_FEATURE_COMPARISON.md` - Comparison with Windsurf

---

**Happy coding with RoboDog! 🐕**
