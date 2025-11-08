# Quick Start: Enable Agent Loop

The `todo.py` file has syntax errors from the integration attempt. Here's a simpler approach:

## Option 1: Enable via CLI Flag (Recommended)

Add a CLI flag to enable agent loop without modifying `todo.py`:

1. In `cli.py`, add argument:
```python
parser.add_argument('--agent-loop', action='store_true', help='Enable agentic loop for incremental execution')
```

2. After creating `TodoService`:
```python
if args.agent_loop:
    from agent_loop import enable_agent_loop
    enable_agent_loop(todo_service, enable=True)
```

## Option 2: Enable in Config

Add to `config.yaml`:
```yaml
agent_loop:
  enabled: true
  max_iterations: 20
```

## Option 3: Enable Per Task

In `todo.md`:
```markdown
- [ ][-] My task | agent_loop: true
  - include: pattern=*.py
  - out: temp/out.py
```

## Current Status

The `todo.py` file needs to be restored from git or manually fixed. The indentation got corrupted during the integration.

### To Restore:
```bash
git checkout robodog/todo.py
```

Then use Option 1 above for a clean integration.

## Summary

✅ **agent_loop.py** - Working implementation
✅ **AGENT_LOOP_GUIDE.md** - Complete documentation  
❌ **todo.py integration** - Has syntax errors, needs restoration

**Recommendation**: Restore `todo.py` from git, then use CLI flag approach for clean integration.
