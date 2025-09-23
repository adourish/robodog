# file: plan.md NEW
# Plan to Fix Appending Flags in Task Descriptions

## Task Summary
The task is to diagnose and resolve the issue where task descriptions in `todo.md` accumulate extra checkbox flags (e.g., `[x][x][x] [-] [-] [-] [-]`) with each run or update. This appending corrupts the task description, making it unreadable and breaking parsing logic in `TodoService`. The goal is to ensure task descriptions remain clean, with flags managed only in their designated brackets (plan, status, write).

**Key Problem**: Flags are being appended to the end of the `desc` field during task rebuilding or metadata parsing, likely due to incomplete cleaning in `_parse_task_metadata` or `_rebuild_task_line` in `todo.py`.

## Analysis
- **Root Cause Identification**:
  - In `todo.py`, the `_parse_task_metadata` method splits on `|` and cleans trailing `[ - ]`, but it may not handle multiple or varied flag patterns (e.g., `[x]`, `[-]`, or combinations).
  - The `_rebuild_task_line` reconstructs lines but assumes a clean `desc`; if `desc` already has appended flags from prior runs, they persist and new ones are added.
  - During task updates (e.g., in `complete_task`), metadata like timestamps and tokens is appended via `|`, but flag contamination in `desc` isn't fully stripped.
  - Regex in `TASK_RE` captures flags but doesn't prevent description pollution during reloading.

- **Reproduction**:
  - Run a task multiple times: Observe `desc` growing with flags like `[ - ]` at the end.
  - Check logs: Look for patterns in `_load_all` or `_process_one` where `desc` is modified without full sanitization.

- **Impact**:
  - Breaks task readability and parsing (e.g., `TASK_RE` may fail on malformed lines).
  - Increases token count unnecessarily in prompts.
  - Affects planning/execution steps if descriptions become too long.

## Proposed Changes
Update `todo.py` to prevent flag appending:

1. **Enhance Cleaning in `_parse_task_metadata`**:
   - Use a robust regex to strip all trailing flag patterns (e.g., `\s*\[ [x~-] \]\s*$`) repeatedly until no more matches.
   - Ensure `desc` is always trimmed after splitting on `|`.

2. **Improve `_rebuild_task_line`**:
   - Validate `desc` before reconstruction: Strip any embedded flags.
   - Only append metadata if clean; log warnings for contaminated `desc`.

3. **Add Validation in `_load_all`**:
   - After parsing each task, run a post-clean on `desc` to remove any detected flags.
   - Introduce a `sanitize_desc` helper method.

4. **Logging and Error Handling**:
   - Add debug logs in `_parse_task_metadata` and `_rebuild_task_line` to trace `desc` changes.
   - If contamination detected, log an error and auto-clean.

5. **No New Files Needed**:
   - All changes are in-place updates to `todo.py`.
   - Test with existing `todo.md` samples.

**File Changes**:
- **todo.py**: Update parsing and rebuilding logic (approx. 50-100 lines modified in `_parse_task_metadata`, `_rebuild_task_line`, and `_load_all`).

## Next Steps
1. **Immediate (Planning/Testing)**:
   - Reproduce the issue: Create a test `todo.md` with a task, run `/todo` multiple times, inspect appended flags.
   - Review code: Focus on `todo.py` lines 300-500 (metadata parsing and line rebuilding).

2. **Implementation**:
   - Update `_parse_task_metadata`: Add loop to strip multiple trailing flags.
   - Update `_rebuild_task_line`: Integrate sanitization.
   - Add unit tests for cleaning (new method in `todo.py`).

3. **Verification**:
   - Run full task cycle 3-5 times: Confirm no appending.
   - Check token counts: Ensure `prompt_tokens` doesn't inflate.
   - Update this `plan.md` with results.

4. **Deployment**:
   - Commit changes to `todo.py`.
   - Monitor next `/todo` runs for issues.

**Estimated Effort**: 2-4 hours (analysis + implementation + testing).
**Risks**: Minimal; changes are defensive cleaning. Backup `todo.md` before testing.

**Original file length**: 0 lines (new file)  
**Updated file length**: 45 lines

# original file length: 0 lines
# updated file length: 45 lines