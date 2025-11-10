# 🧪 Testing the Enhanced Agent Loop

## ✅ Test Task Created

A new test task has been added to `todo.md`:

```markdown
# todo  task 3
- [ ][ ][ ] test enhanced agent loop
  - include: pattern=*robodogcli*robodog*agent_loop*.py|*robodogcli*robodog*cli.py|*robodogcli*robodog*dashboard.py
  - out: temp\out.py
  - plan: temp\plan.md
```

This task will test:
1. ✅ Self-reflection and quality scoring
2. ✅ Adaptive chunking based on file size
3. ✅ Iterative refinement for low-quality output
4. ✅ Comprehensive logging at each phase
5. ✅ Micro-step tracking

## 🚀 How to Run the Test

### Option 1: With Agent Loop (Enhanced)

```bash
python robodog\cli.py --agent-loop --folders . --port 2500 --token testtoken --config config.yaml --model qwen/qwen3-coder --log-level INFO --diff
```

Then in the CLI:
```
[qwen/qwen3-coder]> /todo
```

### Option 2: Without Agent Loop (Standard)

```bash
python robodog\cli.py --folders . --port 2500 --token testtoken --config config.yaml --model qwen/qwen3-coder --log-level INFO --diff
```

Then in the CLI:
```
[qwen/qwen3-coder]> /todo
```

## 📊 Expected Output with Agent Loop

### Phase 1: Task Decomposition
```
======================================================================
🤖 STARTING AGENTIC LOOP
Task: test enhanced agent loop
Files to process: 3
Base folder: c:\Projects\robodog\robodogcli
======================================================================
Initializing agent state...
Max iterations: 50

──────────────────────────────────────────────────────────────────────
PHASE 1: TASK DECOMPOSITION
──────────────────────────────────────────────────────────────────────

📦 Starting adaptive chunking for 3 files
Target: 2000 tokens/chunk, Max: 3 files/chunk
  [1/3] agent_loop.py: 2800 tokens, complexity=0.72
  → Creating chunk 1 with 1 files (2800 tokens)
  [2/3] agent_loop_enhanced.py: 1900 tokens, complexity=0.68
  [3/3] cli.py: 1500 tokens, complexity=0.55
  → Creating chunk 2 with 2 files (3400 tokens)

✅ Adaptive chunking complete: 3 files → 2 chunks
  Chunk 1: agent_loop.py
  Chunk 2: agent_loop_enhanced.py, cli.py

✅ Decomposed into 2 subtasks:
  1. Process agent_loop.py (1 files)
  2. Process 2 files: agent_loop_enhanced.py, cli.py (2 files)
```

### Phase 2: Iterative Execution
```
──────────────────────────────────────────────────────────────────────
PHASE 2: ITERATIVE EXECUTION
──────────────────────────────────────────────────────────────────────

┌────────────────────────────────────────────────────────────────────┐
│ 🔄 ITERATION 1/50                                                  │
│ Task: Process agent_loop.py                                        │
│ Files: 1                                                           │
└────────────────────────────────────────────────────────────────────┘

Executing subtask...
Building prompt for subtask...
Prompt: 3200 tokens
Calling LLM...
Received response: 2100 tokens
Parsing LLM output...
Parsed 1 files

🔍 Starting self-reflection for: Process agent_loop.py
Building reflection prompt...
Reflection prompt: 520 tokens
Asking LLM to evaluate its own work...
Received reflection response: 145 tokens
Parsing reflection response...

✅ Self-reflection complete: Quality=0.82, Completeness=Yes, Correctness=Yes, Suggestions=1
Suggestions for improvement:
  1. Add more error handling in execute method

Validating result...
✅ Subtask completed: Process agent_loop.py (Q:0.82)

┌────────────────────────────────────────────────────────────────────┐
│ 🔄 ITERATION 2/50                                                  │
│ Task: Process 2 files: agent_loop_enhanced.py, cli.py             │
│ Files: 2                                                           │
└────────────────────────────────────────────────────────────────────┘

Executing subtask...
Building prompt for subtask...
Prompt: 4100 tokens
Calling LLM...
Received response: 2800 tokens
Parsing LLM output...
Parsed 2 files

🔍 Starting self-reflection for: Process 2 files: agent_loop_enhanced.py, cli.py
Building reflection prompt...
Reflection prompt: 680 tokens
Asking LLM to evaluate its own work...
Received reflection response: 165 tokens
Parsing reflection response...

✅ Self-reflection complete: Quality=0.88, Completeness=Yes, Correctness=Yes, Suggestions=0

Validating result...
✅ Subtask completed: Process 2 files: agent_loop_enhanced.py, cli.py (Q:0.88)
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
  ⏱️  Duration: 38.7s
  🔄 Iterations: 2
  💰 Total tokens: 13,610
  📁 Files modified: 3
  ⭐ Average quality: 0.85
  🔧 Refinements: 0
  📝 Micro-steps logged: 14

📁 Modified files:
  • agent_loop.py
  • agent_loop_enhanced.py
  • cli.py

======================================================================
```

## 🔍 What to Look For

### ✅ Successful Test Indicators

1. **Phase Headers**
   - Should see 3 clear phase separators
   - Each phase should have a descriptive header

2. **Adaptive Chunking**
   - Should show file analysis with token counts
   - Should show complexity scores (0.0-1.0)
   - Should explain chunking decisions

3. **Iteration Boxes**
   - Each iteration in a visual box
   - Shows iteration number, task, and file count

4. **Self-Reflection**
   - Quality score (0.0-1.0) for each subtask
   - Completeness and correctness checks
   - Suggestions list (if any)

5. **Refinement (if triggered)**
   - Only if quality < 0.7
   - Shows original quality
   - Lists suggestions being applied
   - Shows refined quality

6. **Summary Statistics**
   - Success/failure counts
   - Duration
   - Token usage
   - Quality metrics
   - File list

### ❌ Potential Issues

1. **Import Error**
   ```
   ImportError: cannot import name 'AgentLoopEnhancements'
   ```
   **Fix:** Check that `agent_loop_enhanced.py` exists in the same directory

2. **No Logging**
   ```
   Only see minimal logs
   ```
   **Fix:** Make sure `--log-level INFO` is set

3. **Agent Loop Not Running**
   ```
   No phase headers or iteration boxes
   ```
   **Fix:** Make sure `--agent-loop` flag is included

4. **AttributeError**
   ```
   AttributeError: 'AgentLoop' object has no attribute '_reflect_on_output'
   ```
   **Fix:** Check that `AgentLoop` inherits from `AgentLoopEnhancements`

## 🎯 Test Scenarios

### Scenario 1: Basic Execution
- **Goal:** Verify all phases run
- **Expected:** 3 phases, 2+ iterations, quality scores shown
- **Pass Criteria:** No errors, summary shows statistics

### Scenario 2: Adaptive Chunking
- **Goal:** Verify files are chunked intelligently
- **Expected:** Files grouped by token count, not exceeding 2000 tokens/chunk
- **Pass Criteria:** Chunking logs show token counts and decisions

### Scenario 3: Self-Reflection
- **Goal:** Verify quality scoring works
- **Expected:** Each subtask gets a quality score
- **Pass Criteria:** Quality scores between 0.0-1.0 shown

### Scenario 4: Refinement (if quality < 0.7)
- **Goal:** Verify refinement triggers
- **Expected:** Low quality triggers refinement, quality improves
- **Pass Criteria:** Refinement logs show before/after quality

### Scenario 5: Micro-Steps
- **Goal:** Verify fine-grained tracking
- **Expected:** 14+ micro-steps logged
- **Pass Criteria:** Summary shows micro-step count

## 📝 Test Checklist

Before running:
- [ ] `agent_loop.py` exists and has enhancements
- [ ] `agent_loop_enhanced.py` exists
- [ ] `todo.md` has the test task
- [ ] Model is configured in `config.yaml`

During run:
- [ ] Phase 1 header appears
- [ ] Adaptive chunking logs show
- [ ] Phase 2 header appears
- [ ] Iteration boxes appear
- [ ] Self-reflection logs show
- [ ] Quality scores displayed
- [ ] Phase 3 header appears
- [ ] Summary statistics shown

After run:
- [ ] No errors in output
- [ ] Task marked complete in `todo.md`
- [ ] Output files created in `temp/`
- [ ] Quality metrics look reasonable

## 🐛 Debugging

### Enable Debug Logging
```bash
python robodog\cli.py --agent-loop --folders . --port 2500 --token testtoken --config config.yaml --model qwen/qwen3-coder --log-level DEBUG --diff
```

### Check Agent Loop Status
In the CLI:
```
[qwen/qwen3-coder]> /status
```

### View Token Budget
In the CLI:
```
[qwen/qwen3-coder]> /budget
```

### Check Files
```bash
# Check if enhanced file exists
dir robodog\agent_loop_enhanced.py

# Check if base file exists
dir robodog\agent_loop.py

# Check todo.md
type todo.md
```

## 🎉 Success Criteria

The test is successful if you see:

✅ **All 3 phases** with clear headers
✅ **Adaptive chunking** with token counts
✅ **Iteration boxes** for each subtask
✅ **Quality scores** for each subtask
✅ **Comprehensive summary** with statistics
✅ **No errors** during execution
✅ **Task completed** in todo.md

## 📊 Performance Expectations

| Metric | Expected Range |
|--------|----------------|
| **Iterations** | 2-5 |
| **Duration** | 30-60s |
| **Quality** | 0.7-1.0 |
| **Refinements** | 0-2 |
| **Micro-steps** | 12-20 |
| **Token usage** | 10k-20k |

## 🚀 Next Steps

After successful test:

1. **Review logs** - Check that all features work
2. **Check quality** - Verify quality scores are reasonable
3. **Inspect output** - Look at generated files in `temp/`
4. **Try more tasks** - Create additional test tasks
5. **Tune settings** - Adjust chunk size, quality threshold, etc.

## 📚 Related Documentation

- `ENHANCED_AGENT_LOOP.md` - Feature documentation
- `ENHANCED_LOGGING.md` - Logging details
- `UX_IMPROVEMENTS_SUMMARY.md` - CLI improvements
- `README.md` - General usage

---

**Ready to test?** Run the command and watch the enhanced logging in action! 🚀
