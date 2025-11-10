# Agentic Game Loop Implementation Guide

## Overview

The Agentic Game Loop transforms the monolithic LLM step into an iterative process that handles small chunks of work at a time, making it more manageable, resilient, and efficient.

## Architecture

### Traditional Flow (Monolithic)
```
┌─────────────────────────────────────┐
│ Step 2: LLM (All at Once)          │
├─────────────────────────────────────┤
│ • Load ALL 14k+ tokens              │
│ • Build ONE massive prompt          │
│ • Get ONE large response            │
│ • Parse ALL files                   │
│ • Success or Total Failure          │
└─────────────────────────────────────┘
```

**Problems:**
- ❌ Context window overflow
- ❌ All-or-nothing execution
- ❌ No progress tracking
- ❌ Difficult to debug
- ❌ Can't recover from partial failures

### Agentic Loop (Incremental)
```
┌─────────────────────────────────────┐
│ Step 2: LLM Agent Loop              │
├─────────────────────────────────────┤
│ 1. Decompose Task                   │
│    ├─ Analyze includes              │
│    ├─ Parse plan.md                 │
│    └─ Create subtasks               │
│                                     │
│ 2. Execute Loop (max 20 iterations) │
│    ├─ Get next subtask              │
│    ├─ Load ONLY relevant files      │
│    ├─ Build focused prompt (~2k)    │
│    ├─ Execute with LLM              │
│    ├─ Validate result               │
│    ├─ Update state                  │
│    └─ Continue or retry             │
│                                     │
│ 3. Aggregate Results                │
│    ├─ Combine all changes           │
│    ├─ Report summary                │
│    └─ Mark complete                 │
└─────────────────────────────────────┘
```

**Benefits:**
- ✅ Small context windows (2-3k tokens)
- ✅ Incremental progress
- ✅ Retry failed subtasks
- ✅ Track state across iterations
- ✅ Graceful degradation
- ✅ Better debugging

## Key Components

### 1. AgentState
Tracks execution state across iterations:

```python
class AgentState:
    - subtasks: List[Dict]           # Queue of pending work
    - completed_subtasks: List[Dict] # Successfully completed
    - failed_subtasks: List[Dict]    # Failed attempts
    - current_subtask: Dict          # Currently executing
    - iteration: int                 # Current iteration (1-20)
    - total_tokens_used: int         # Token tracking
    - files_modified: List[str]      # Changed files
```

### 2. AgentLoop
Main execution engine:

```python
class AgentLoop:
    def execute(task, base_folder, include_files, knowledge, plan):
        # Returns: (success, parsed_files, state)
        
    def _decompose_task(task, files, plan):
        # Break into subtasks
        
    def _execute_subtask(subtask, task, ...):
        # Execute one subtask
        
    def _validate_result(result, subtask):
        # Check if result is valid
```

## Decomposition Strategies

### Strategy 1: File-Based
For small projects (≤5 files):
```python
subtasks = [
    {'description': 'Process service.py', 'target_files': ['service.py']},
    {'description': 'Process todo.py', 'target_files': ['todo.py']},
    ...
]
```

### Strategy 2: Group-Based
For larger projects (>5 files):
```python
subtasks = [
    {'description': 'Process robodog module (3 files)', 
     'target_files': ['service.py', 'todo.py', 'cli.py']},
    {'description': 'Process utils module (2 files)',
     'target_files': ['file_service.py', 'parse_service.py']},
]
```

### Strategy 3: Action-Based
Extract from plan.md:
```python
# From plan.md:
# 1. Fix import statements
# 2. Add error handling
# 3. Update documentation

subtasks = [
    {'description': 'Fix import statements', 'type': 'plan_action'},
    {'description': 'Add error handling', 'type': 'plan_action'},
    {'description': 'Update documentation', 'type': 'plan_action'},
]
```

## Integration with TodoService

### Option 1: Enable Globally

In `cli.py` or service initialization:

```python
from agent_loop import enable_agent_loop

# After creating TodoService
todo_service = TodoService(...)
enable_agent_loop(todo_service, enable=True)
```

### Option 2: Enable Per Task

In `todo.md`:

```markdown
- [ ][-] Fix bugs | agent_loop: true
  - include: pattern=*.py
  - out: temp/out.py
```

### Option 3: Enable via CLI Flag

```bash
python robodog/cli.py --agent-loop --folders ...
```

## Prompt Strategy

### Traditional Prompt (14k+ tokens)
```
Task: Fix all bugs
Include: [14,000 tokens of code]
Knowledge: [500 tokens]
Plan: [200 tokens]
Total: ~15k tokens
```

### Agentic Prompt (2-3k tokens per iteration)
```
Iteration 1:
Task: Fix bugs
Subtask: Process service.py only
Include: [2,000 tokens - service.py only]
Context: [300 tokens - what's been done]
Total: ~2.5k tokens

Iteration 2:
Task: Fix bugs
Subtask: Process todo.py only
Include: [2,500 tokens - todo.py only]
Context: [300 tokens - previous results]
Total: ~3k tokens
```

## State Management

### Iteration Tracking
```python
state = AgentState(task)
while state.should_continue():
    subtask = state.next_subtask()
    result = execute_subtask(subtask)
    if validate(result):
        state.mark_complete(result)
    else:
        state.mark_failed("validation error")
```

### Progress Reporting
```python
{
    'total_iterations': 5,
    'completed': 4,
    'failed': 1,
    'pending': 0,
    'duration_seconds': 45.2,
    'total_tokens': 12500,
    'files_modified': ['service.py', 'todo.py', 'cli.py']
}
```

## Validation & Retry Logic

### Validation Checks
1. **Output exists**: Parsed files present
2. **Target match**: Result files match expected targets
3. **No errors**: No parse errors in output
4. **Syntax valid**: Code is syntactically correct

### Retry Strategy
```python
if not validate(result):
    if subtask.retry_count < 2:
        subtask.retry_count += 1
        state.add_subtask(subtask)  # Re-queue
    else:
        state.mark_failed("Max retries exceeded")
```

## Safety Limits

- **Max iterations**: 20 (configurable)
- **Max retries per subtask**: 2
- **Token budget per subtask**: ~3k tokens
- **Timeout per subtask**: 30 seconds (recommended)

## Example Usage

### Basic Example

```python
from agent_loop import AgentLoop

# Create agent loop
agent = AgentLoop(
    svc=robodog_service,
    file_service=file_service,
    prompt_builder=prompt_builder,
    parser=parse_service
)

# Execute task
success, results, state = agent.execute(
    task={'desc': 'Fix bugs', 'include': ['*.py']},
    base_folder='/project',
    include_files=['service.py', 'todo.py'],
    knowledge_text='Fix import errors',
    plan_content='1. Fix imports\n2. Add tests'
)

# Check results
if success:
    print(f"✅ Completed {state.get_summary()['completed']} subtasks")
    print(f"Modified files: {state.files_modified}")
else:
    print(f"❌ Failed: {state.get_summary()['failed']} subtasks failed")
```

### Integration in todo.py

```python
def _process_one(self, task, svc, file_lines_map, step=1):
    # ... existing code ...
    
    elif step == 2:  # LLM step
        # Check if agent loop is enabled
        if hasattr(self, '_agent_loop') and self._agent_loop:
            # Use agentic loop
            success, parsed_files, state = self._agent_loop.execute(
                task=task,
                base_folder=base_folder,
                include_files=include_files,
                knowledge_text=knowledge_text,
                plan_content=plan_content
            )
            
            # Log summary
            summary = state.get_summary()
            logger.info(f"Agent loop: {summary['completed']} completed, "
                       f"{summary['failed']} failed, "
                       f"{summary['total_tokens']} tokens")
            
            # Continue with results
            committed, compare = self._todo_util._write_parsed_files(
                parsed_files, task, False, base_folder
            )
        else:
            # Use traditional monolithic approach
            # ... existing code ...
```

## Configuration

### In config.yaml

```yaml
agent_loop:
  enabled: true
  max_iterations: 20
  max_retries: 2
  token_budget_per_subtask: 3000
  decomposition_strategy: "auto"  # auto, file, group, action
  validation_strict: true
```

### In todo.md

```markdown
# Project settings
- agent_loop_enabled: true
- max_iterations: 15

# Task with agent loop
- [ ][-] Refactor codebase | agent_loop: true
  - include: pattern=*.py recursive
  - out: temp/out.py
```

## Monitoring & Debugging

### Log Output

```
🤖 Starting agentic loop for task: Fix bugs
📋 Decomposed into 5 subtasks
🔄 Iteration 1/20: Process service.py
✅ Subtask completed: Process service.py
🔄 Iteration 2/20: Process todo.py
⚠️ Subtask validation failed, retrying: Process todo.py
🔄 Iteration 3/20: Process todo.py (retry 1)
✅ Subtask completed: Process todo.py
...
🏁 Agentic loop completed: 4 succeeded, 1 failed, 45.2s
```

### State Inspection

```python
# During execution
print(f"Current iteration: {state.iteration}")
print(f"Pending: {len(state.subtasks)}")
print(f"Completed: {len(state.completed_subtasks)}")
print(f"Failed: {len(state.failed_subtasks)}")

# After execution
summary = state.get_summary()
for key, value in summary.items():
    print(f"{key}: {value}")
```

## Performance Comparison

### Traditional Approach
```
Task: Fix 8 files
Time: 120 seconds
Tokens: 18,000
Success rate: 60% (all or nothing)
Retries: 0
```

### Agentic Loop
```
Task: Fix 8 files
Time: 90 seconds (8 iterations × ~11s each)
Tokens: 16,000 (8 × 2k per iteration)
Success rate: 87% (7/8 subtasks succeeded)
Retries: 2 (automatic)
```

## Best Practices

1. **Start small**: Test with 2-3 files first
2. **Monitor tokens**: Track usage per subtask
3. **Set limits**: Use max_iterations to prevent runaway
4. **Validate results**: Always check output before committing
5. **Log everything**: Enable detailed logging for debugging
6. **Group wisely**: Balance between too many/too few subtasks
7. **Handle failures**: Implement proper error recovery
8. **Test incrementally**: Validate after each subtask

## Troubleshooting

### Issue: Too many iterations
**Solution**: Reduce file count or improve decomposition strategy

### Issue: Subtasks keep failing
**Solution**: Check validation logic, increase retry limit, or simplify subtasks

### Issue: Context still too large
**Solution**: Further break down subtasks, limit files per subtask to 1-2

### Issue: Results inconsistent
**Solution**: Add stricter validation, use deterministic prompts

## Future Enhancements

1. **Parallel execution**: Run independent subtasks in parallel
2. **Dependency tracking**: Detect file dependencies, order subtasks
3. **Learning**: Adjust strategy based on success rates
4. **Checkpointing**: Save state, resume from failures
5. **Cost optimization**: Minimize token usage dynamically
6. **Smart grouping**: ML-based file clustering

## Summary

The Agentic Game Loop provides:

✅ **Incremental execution** - Small chunks at a time
✅ **Better resilience** - Retry failed subtasks
✅ **Progress tracking** - Know what's done/pending
✅ **Token efficiency** - Smaller context windows
✅ **Graceful degradation** - Partial success possible
✅ **Easier debugging** - Isolated failures

Start using it today to handle large tasks more effectively!
