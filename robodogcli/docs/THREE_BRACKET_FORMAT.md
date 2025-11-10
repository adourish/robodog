# Three-Bracket Task Format

## Overview

Tasks now use a three-bracket format: `[plan][llm][commit]` to track progress through three stages of task execution.

## Format

```markdown
- [plan][llm][commit] Task description
```

Each bracket represents a stage:
- **[plan]** - Planning stage (generate plan.md)
- **[llm]** - LLM execution stage (implement changes)
- **[commit]** - Commit stage (finalize and commit)

## Status Characters

Each bracket can have one of four status characters:
- ` ` (space) - To Do
- `~` - Doing (in progress)
- `x` - Done (completed)
- `-` - Ignore (skipped)

## Examples

### New Task (All To Do)
```markdown
- [ ][ ][ ] Implement user authentication
```

### Plan Complete, LLM In Progress
```markdown
- [x][~][ ] Add password reset functionality
```

### All Stages Complete
```markdown
- [x][x][x] Fix login bug
```

### Task with Sub-lines
```markdown
- [ ][ ][ ] Refactor database layer
  - include: src/db/*.py
  - plan: pattern="architecture.md"
```

## Creating Tasks

### CLI
```bash
/todo add Implement feature X
```
Creates:
```markdown
- [ ][ ][ ] Implement feature X
```

### Python API
```python
from robodog.todo_manager import TodoManager

todo_mgr = TodoManager(roots=["/path/to/project"])

# Basic task
task = todo_mgr.add_task("Implement feature")

# Task with specific statuses
task = todo_mgr.add_task(
    description="Continue refactoring",
    plan_status='x',  # Plan done
    llm_status='~',   # LLM in progress
    commit_status=' ' # Commit not started
)

# Task with include pattern
task = todo_mgr.add_task(
    description="Update API endpoints",
    include="src/api/*.py"
)
```

### HTTP API
```json
{
  "op": "TODO_ADD",
  "payload": {
    "description": "Implement feature",
    "plan_status": " ",
    "llm_status": " ",
    "commit_status": " ",
    "include": "src/**/*.py",
    "plan_spec": "docs/architecture.md"
  }
}
```

## Updating Task Status

### Update Specific Stage
```python
# Mark plan as done
todo_mgr.update_task_status(
    path="/path/to/todo.md",
    line_number=5,
    new_status='x',
    stage='plan'
)

# Mark LLM as in progress
todo_mgr.update_task_status(
    path="/path/to/todo.md",
    line_number=5,
    new_status='~',
    stage='llm'
)

# Mark all stages as done
todo_mgr.update_task_status(
    path="/path/to/todo.md",
    line_number=5,
    new_status='x',
    stage='all'
)
```

### HTTP API
```json
{
  "op": "TODO_UPDATE",
  "payload": {
    "path": "/path/to/todo.md",
    "line_number": 5,
    "new_status": "x",
    "stage": "plan"
  }
}
```

## Listing Tasks

Tasks returned from `list_tasks()` include all three statuses:

```python
tasks = todo_mgr.list_tasks()

for task in tasks:
    print(f"Plan: {task['plan_status']}")
    print(f"LLM: {task['llm_status']}")
    print(f"Commit: {task['commit_status']}")
    print(f"Description: {task['description']}")
```

Example output:
```
Plan: Done
LLM: Doing
Commit: To Do
Description: Implement authentication
```

## CLI Display

When listing tasks with `/todo`, the output shows:

```
Found 3 tasks:

[ ][~][ ] Implement user authentication
    Plan:To Do LLM:Doing Commit:To Do
    todo.md:5

[x][x][ ] Add password reset
    Plan:Done LLM:Done Commit:To Do
    todo.md:8

[x][x][x] Fix login bug
    Plan:Done LLM:Done Commit:Done
    todo.md:12
```

## Backward Compatibility

The system supports old single-bracket format for reading:
```markdown
- [ ] Old format task
```

This is automatically converted to:
```python
{
    "plan_status": "To Do",
    "llm_status": "To Do",
    "commit_status": "To Do"
}
```

However, **new tasks are always created in three-bracket format**.

## Task Workflow

Typical task progression:

1. **Create Task**
   ```markdown
   - [ ][ ][ ] Implement feature
   ```

2. **Start Planning**
   ```markdown
   - [~][ ][ ] Implement feature
   ```

3. **Plan Complete, Start LLM**
   ```markdown
   - [x][~][ ] Implement feature
   ```

4. **LLM Complete, Start Commit**
   ```markdown
   - [x][x][~] Implement feature
   ```

5. **All Complete**
   ```markdown
   - [x][x][x] Implement feature
   ```

## Integration with TodoService

The three-bracket format is fully compatible with the existing `TodoService` task execution system:

- `plan` status tracks plan.md generation
- `llm` status tracks LLM-based implementation
- `commit` status tracks final commit/completion

When `TodoService` processes a task:
1. Updates `plan` status when generating plan
2. Updates `llm` status when executing changes
3. Updates `commit` status when committing

## Benefits

1. **Clear Progress Tracking** - See exactly which stage each task is in
2. **Parallel Work** - Multiple tasks can be at different stages
3. **Resume Support** - Easy to see what needs to continue
4. **Reporting** - Statistics can show stage-by-stage progress
5. **Compatibility** - Works with existing TodoService workflow

## Summary

✅ Three-bracket format: `[plan][llm][commit]`
✅ Four status characters: ` `, `~`, `x`, `-`
✅ Stage-specific updates
✅ Full API support (CLI, Python, HTTP)
✅ Backward compatible reading
✅ Integrated with TodoService
✅ Clear progress visualization

All tasks now properly track plan, llm, and commit stages!
