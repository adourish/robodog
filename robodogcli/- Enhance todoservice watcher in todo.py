# file: - Enhance todoservice watcher in todo.py
Reload only affected tasks on file changes, but limit to advancing one task without re-scanning all files each cycle.