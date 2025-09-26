# file: - Refine service.py
In include() and search_files(), ensure they support targeted updates without full re-parsing chains across multiple files.

## Actionable Next Steps
1. In todo.py, refactor _load_all() to return tasks with a persistent index (e.g., via metadata), advancing it after each successful task to prevent re-processing.
2. Modify run_next_task() in todo.py to select and process only the next indexed task, updating the todo.md to mark progress without full reload.
3. Add validation in _watch_loop() of todo.py to check if external changes affect only the active task, avoiding unnecessary full parses.
4. Update cli.py's /todo handler to call a single-task mode, ensuring one iteration completes before next, breaking any loop on multi-task files.
5. Test by adding multiple tasks to todo.md, running /todo repeatedly, and verifying sequential advancement without infinite re-entries.