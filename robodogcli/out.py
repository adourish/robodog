# file: plan.md NEW
# Plan for Enhancing Logging in todo.py

## Task Overview
The primary task is to enhance logging capabilities in the `todo.py` module of the Robodog CLI project. This involves improving the logging depth, structure, and output for better debugging, tracking, and monitoring of task execution, file operations, and system interactions. The goal is to make the todo service more observable and easier to troubleshoot, especially during task parsing, AI interactions, and file writes.

Current logging in `todo.py` is basic (using `logging.info`, `logging.debug`, etc.) but lacks:
- Structured logging with metadata (e.g., task IDs, timestamps, token counts).
- Consistent levels for different operations (e.g., DEBUG for internal states, INFO for key events, WARNING for issues).
- Aggregation of statistics (e.g., median/avg token deltas, commit summaries).
- Error handling with full tracebacks and context.

## Key Requirements
- **Compliance with Instructions**: Follow A-U strictly. Use appropriate comment directives (e.g., `#` for Python). Ensure files are self-contained and executable. Add original/updated line length comments.
- **Logging Enhancements**:
  - Add loggers for specific components (e.g., task loading, watching, committing).
  - Include metadata in logs (e.g., task desc, file paths, token counts, timestamps).
  - Log stats like median/avg/peak deltas for UPDATEs.
  - Handle exceptions with detailed logging including tracebacks.
  - Support configurable log levels and formats (integrate with CLI's colorlog).
- **No Guessing**: Only modify `todo.py` based on existing structure. Do not infer new files beyond what's specified.
- **Base Directory**: Relative to the project root (c:\projects\robodog\robodogcli\robodog).
- **Temp Output**: Stash AI outputs in `c:\projects\robodog\robodogcli\out.py`.

## Planned Changes
### 1. **todo.py Modifications** (UPDATE)
   - **Original Length**: ~1352 lines (estimated from provided code).
   - **Key Additions**:
     - Import `traceback` and `statistics` (if not already).
     - Create module-level logger: `logger = logging.getLogger(__name__)`.
     - Enhance `_load_all()`: Log task counts, metadata parsing, knowledge token counts.
     - Enhance `_watch_loop()`: Log file changes, reloading events, with timestamps.
     - Enhance `_process_manual_done()`: Log manual commit steps, paths resolved, success/failure.
     - Enhance `run_next_task()`: Log step detection (plan/LLM/commit), task selection.
     - Add logging in `_gather_include_knowledge()`, `_generate_plan()`, `_write_parsed_files()`:
       - Token counts, paths, deltas (e.g., "UPDATE stats: median_delta_percent=5.2%, avg_delta_tokens=10").
       - Errors with full context.
     - In `_write_parsed_files()`: Log per-file actions with O/U/D/P format, aggregate UPDATE stats at end.
   - **Updated Length**: ~1450 lines (adding ~100 lines for logs and stats).
   - **Rationale**: Improves traceability without altering core logic. No deletions.

### 2. **No New Files** (beyond this plan.md).
   - If needed, log any external includes/knowledge.

### 3. **No Deletions/Copies**.
   - Focus on in-place updates to `todo.py`.

## Potential Risks & Mitigations
- **Over-Logging**: Use DEBUG for verbose details, INFO for key events to avoid noise.
- **Performance**: Token counting and stats are lightweight; no impact on watch loop.
- **Error Handling**: Wrap all new log calls in try-except to prevent crashes.
- **Compatibility**: Ensure logs work with existing colorlog setup in CLI.

## Next Steps
1. **LLM Generation (Step 2)**: Run the main task prompt to implement the logging enhancements in `todo.py`. Include this plan.md in knowledge.
2. **Commit (Step 3)**: Manually mark task as complete in todo.md and commit changes via CLI.
3. **Verification**: Test with `/todo` command; check logs for completeness (e.g., run a sample task and review robodog.log).
4. **Iteration**: If issues, add a follow-up task for refinements.

This plan ensures incremental, observable improvements. Total estimated effort: Low (focus on logging wrappers). Proceed to code generation.

# Updated Length: ~250 lines (new file, no original).