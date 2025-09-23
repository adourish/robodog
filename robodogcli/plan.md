# file: plan.md
# Plan for adding logging to file_service.py

## Task Summary
The goal is to enhance the FileService class in `file_service.py` with comprehensive logging. This will improve debugging, monitoring, and traceability of file operations such as reading, writing, searching, and path resolution. Logging will use the existing `logging` module, with levels like `debug` for detailed actions, `info` for key events, and `warning/error` for issues.

## Outline of Changes
1. **Add Logging to Existing Methods**:
   - `__init__`: Log initialization details (roots, exclude_dirs).
   - `search_files`: Log search parameters, number of matches found, and excluded directories.
   - `find_files_by_pattern`: Log pattern, recursive flag, and results count.
   - `find_matching_file`: Log search for filename, matched path if found.
   - `resolve_path`: Log fragment resolution attempt and result.
   - `safe_read_file`: Log file path, success/failure, token count (words).
   - `binary_read`: Log binary read attempt.
   - `write_file`: Log write operation (atomic/fallback), token count, path.
   - `ensure_dir`, `delete_file`, `append_file`, `delete_dir`, `rename`, `copy_file`: Log action start/end, paths involved, success/failure.

2. **Handle Errors Gracefully**: Wrap operations in try-except where needed, logging exceptions without crashing.

3. **Performance Logging**: In search methods, log time taken if applicable (optional, keep simple for now).

4. **No Breaking Changes**: Preserve existing functionality; logging is additive.

## Next Steps
- Test FileService operations (e.g., read/write/search) and verify logs appear with appropriate levels.
- Run a sample task via TodoService to ensure integration.
- If needed, adjust log levels or add more granularity based on output.
- Potential future: Add metrics (e.g., average search time) to logging.

No new files created. Updated `file_service.py` below.

---