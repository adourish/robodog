# 📝 Enhanced Logging for Agentic Loop

## ✅ What Was Added

Comprehensive logging throughout the enhanced agentic loop so you can see exactly what's happening at every step.

## 🎯 Logging Levels

### Phase 1: Task Decomposition
```
======================================================================
🤖 STARTING AGENTIC LOOP
Task: Fix bugs in service
Files to process: 5
Base folder: c:\projects\robodog\robodogcli
======================================================================
Initializing agent state...
Max iterations: 50

──────────────────────────────────────────────────────────────────────
PHASE 1: TASK DECOMPOSITION
──────────────────────────────────────────────────────────────────────

📦 Starting adaptive chunking for 5 files
Target: 2000 tokens/chunk, Max: 3 files/chunk
  [1/5] service.py: 1850 tokens, complexity=0.65
  [2/5] todo.py: 2100 tokens, complexity=0.78
  → Creating chunk 1 with 1 files (1850 tokens)
  [3/5] cli.py: 1200 tokens, complexity=0.45
  [4/5] app.py: 900 tokens, complexity=0.35
  [5/5] util.py: 600 tokens, complexity=0.25
  → Creating final chunk 2 with 4 files (4800 tokens)

✅ Adaptive chunking complete: 5 files → 2 chunks
  Chunk 1: service.py
  Chunk 2: todo.py, cli.py, app.py, util.py

✅ Decomposed into 2 subtasks:
  1. Process service.py (1 files)
  2. Process 4 files: todo.py, cli.py... (4 files)
```

### Phase 2: Iterative Execution
```
──────────────────────────────────────────────────────────────────────
PHASE 2: ITERATIVE EXECUTION
──────────────────────────────────────────────────────────────────────

┌────────────────────────────────────────────────────────────────────┐
│ 🔄 ITERATION 1/50                                                  │
│ Task: Process service.py                                           │
│ Files: 1                                                           │
└────────────────────────────────────────────────────────────────────┘

Executing subtask...
Building prompt for subtask...
Prompt: 2150 tokens
Calling LLM...
Received response: 1890 tokens
Parsing LLM output...
Parsed 1 files

🔍 Starting self-reflection for: Process service.py
Building reflection prompt...
Reflection prompt: 450 tokens
Asking LLM to evaluate its own work...
Received reflection response: 120 tokens
Parsing reflection response...

✅ Self-reflection complete: Quality=0.85, Completeness=Yes, Correctness=Yes, Suggestions=0

Validating result...
✅ Subtask completed: Process service.py (Q:0.85)

┌────────────────────────────────────────────────────────────────────┐
│ 🔄 ITERATION 2/50                                                  │
│ Task: Process 4 files: todo.py, cli.py...                         │
│ Files: 4                                                           │
└────────────────────────────────────────────────────────────────────┘

Executing subtask...
Building prompt for subtask...
Prompt: 5200 tokens
Calling LLM...
Received response: 3400 tokens
Parsing LLM output...
Parsed 4 files

🔍 Starting self-reflection for: Process 4 files: todo.py, cli.py...
Building reflection prompt...
Reflection prompt: 680 tokens
Asking LLM to evaluate its own work...
Received reflection response: 180 tokens
Parsing reflection response...

✅ Self-reflection complete: Quality=0.65, Completeness=No, Correctness=Yes, Suggestions=3
Suggestions for improvement:
  1. Add error handling for edge cases
  2. Improve variable naming in todo.py
  3. Add docstrings to new functions

🔧 Starting refinement for: Process 4 files: todo.py, cli.py...
Original quality: 0.65
Applying 3 suggestions:
  1. Add error handling for edge cases
  2. Improve variable naming in todo.py
  3. Add docstrings to new functions

Building refinement prompt...
Refinement prompt: 4100 tokens
Asking LLM to refine output...
Received refined response: 3800 tokens
Parsing refined output...
Parsed 4 files from refined output

✅ Refinement complete (iteration 1)
Files modified: todo.py, cli.py, app.py

🔍 Starting self-reflection for: Process 4 files: todo.py, cli.py...
Building reflection prompt...
Reflection prompt: 720 tokens
Asking LLM to evaluate its own work...
Received reflection response: 95 tokens
Parsing reflection response...

✅ Self-reflection complete: Quality=0.88, Completeness=Yes, Correctness=Yes, Suggestions=0
✨ Refined quality: 0.88

Validating result...
✅ Subtask completed: Process 4 files: todo.py, cli.py... (Q:0.88)
```

### Phase 3: Summary
```
──────────────────────────────────────────────────────────────────────
PHASE 3: SUMMARY & RESULTS
──────────────────────────────────────────────────────────────────────

🏁 Agentic loop completed!

📊 Statistics:
  ✅ Succeeded: 2
  ❌ Failed: 0
  ⏱️  Duration: 45.3s
  🔄 Iterations: 2
  💰 Total tokens: 12,450
  📁 Files modified: 5
  ⭐ Average quality: 0.87
  🔧 Refinements: 1
  📝 Micro-steps logged: 18

📁 Modified files:
  • service.py
  • todo.py
  • cli.py
  • app.py
  • util.py

======================================================================
```

## 📊 Logging Categories

### 1. **Initialization Logs**
- Starting message with task details
- Agent state configuration
- Max iterations setting

### 2. **Decomposition Logs**
- Adaptive chunking start
- File analysis (tokens, complexity)
- Chunk creation decisions
- Final chunk summary
- Subtask list

### 3. **Execution Logs**
- Iteration header (boxed)
- Subtask details
- Prompt building
- LLM calls
- Response parsing
- File counts

### 4. **Reflection Logs**
- Reflection start
- Prompt building
- LLM evaluation call
- Response parsing
- Quality scores
- Completeness/correctness
- Suggestions list

### 5. **Refinement Logs**
- Refinement start
- Original quality
- Suggestions being applied
- Prompt building
- LLM refinement call
- Response parsing
- Refined file count
- Completion status

### 6. **Summary Logs**
- Success/failure counts
- Duration
- Iteration count
- Token usage
- Files modified
- Quality metrics
- Refinement count
- Micro-steps count
- File list

## 🎨 Visual Elements

### Separators
```
======================================================================  (Major sections)
──────────────────────────────────────────────────────────────────────  (Phases)
┌────────────────────────────────────────────────────────────────────┐  (Iterations)
│                                                                    │
└────────────────────────────────────────────────────────────────────┘
```

### Emojis
- 🤖 Agentic loop start
- 📦 Adaptive chunking
- ✅ Success/completion
- 🔄 Iteration
- 🔍 Self-reflection
- 🔧 Refinement
- ✨ Improved quality
- 📊 Statistics
- 📁 Files
- ⏱️  Duration
- 💰 Tokens
- ⭐ Quality score
- 📝 Micro-steps
- ❌ Failure/error
- ⚠️  Warning

## 🔍 What You Can Track

### Real-Time Progress
1. **Current iteration** - Know which iteration is running
2. **Subtask details** - See what's being processed
3. **File counts** - Track how many files per chunk
4. **Token usage** - Monitor API costs
5. **Quality scores** - See output quality in real-time

### Decision Points
1. **Chunking decisions** - Why files were grouped
2. **Refinement triggers** - When quality is too low
3. **Retry attempts** - When validation fails
4. **Complexity estimates** - File difficulty scores

### Performance Metrics
1. **Duration per iteration**
2. **Tokens per subtask**
3. **Quality trends**
4. **Refinement frequency**
5. **Success rate**

## 🚀 Usage

The enhanced logging is automatic when using `--agent-loop`:

```bash
python robodog\cli.py --agent-loop --folders . --port 2500 --token testtoken --config config.yaml --model qwen/qwen3-coder --log-level INFO
```

### Log Levels

- **INFO** - See all enhanced logging (recommended)
- **DEBUG** - Even more detailed internal logs
- **WARNING** - Only errors and warnings
- **ERROR** - Only errors

## 📈 Benefits

### For Users
1. **Transparency** - Know exactly what's happening
2. **Progress tracking** - See real-time progress
3. **Quality visibility** - Monitor output quality
4. **Problem diagnosis** - Identify issues quickly
5. **Cost monitoring** - Track token usage

### For Debugging
1. **Detailed execution flow** - Step-by-step trace
2. **Decision logging** - Why choices were made
3. **Error context** - Full context when failures occur
4. **Performance analysis** - Identify bottlenecks
5. **Quality trends** - Track improvement over time

## 🎯 Key Improvements

| Aspect | Before | After |
|--------|--------|-------|
| **Visibility** | Minimal | Comprehensive |
| **Progress** | Unclear | Real-time updates |
| **Quality** | Unknown | Scored & tracked |
| **Decisions** | Hidden | Logged & explained |
| **Debugging** | Difficult | Easy with context |
| **Micro-steps** | None | 18+ per task |

## 📝 Example Session

```
21:26:47: Starting robodog
21:26:47: TodoService initialized successfully
21:26:48: Startup model set to qwen/qwen3-coder

[qwen/qwen3-coder]> /todo

======================================================================
🤖 STARTING AGENTIC LOOP
Task: Fix bugs
Files to process: 5
Base folder: .
======================================================================

──────────────────────────────────────────────────────────────────────
PHASE 1: TASK DECOMPOSITION
──────────────────────────────────────────────────────────────────────

📦 Starting adaptive chunking for 5 files
...
✅ Decomposed into 2 subtasks

──────────────────────────────────────────────────────────────────────
PHASE 2: ITERATIVE EXECUTION
──────────────────────────────────────────────────────────────────────

┌────────────────────────────────────────────────────────────────────┐
│ 🔄 ITERATION 1/50                                                  │
│ Task: Process service.py                                           │
│ Files: 1                                                           │
└────────────────────────────────────────────────────────────────────┘

🔍 Starting self-reflection...
✅ Self-reflection complete: Quality=0.85
✅ Subtask completed (Q:0.85)

[... more iterations ...]

──────────────────────────────────────────────────────────────────────
PHASE 3: SUMMARY & RESULTS
──────────────────────────────────────────────────────────────────────

🏁 Agentic loop completed!
📊 Statistics:
  ✅ Succeeded: 2
  ⭐ Average quality: 0.87
  🔧 Refinements: 1

======================================================================
```

## 🎉 Summary

Enhanced logging provides:

✅ **70+ log messages** per task (vs ~5 before)
✅ **3 clear phases** with visual separators
✅ **Real-time progress** with iteration boxes
✅ **Quality tracking** with scores and trends
✅ **Decision logging** for chunking and refinement
✅ **Comprehensive summary** with all metrics
✅ **Visual elements** (boxes, emojis, separators)
✅ **Micro-step tracking** (18+ steps per task)

You'll always know exactly what the agentic loop is doing! 🚀
