Below is an updated version of `todo.py` that, for each task’s focus‐file update, computes a unified diff between the old and new content and writes that diff into the same directory as the target file (with a timestamped `.diff` name) before performing the MCP update.

```diff
--- todo.py.orig    2025-09-02 23:50:00.000000000 +0000
+++ todo.py         2025-09-03 00:10:00.000000000 +0000
@@ top of file
 import shutil
 from datetime import datetime
 from pathlib import Path
+import difflib
@@ class TodoService:
     def _process_one(self, task: dict, svc, file_lines_map: dict):
         include = task.get("include") or {}
         knowledge = self._gather_include_knowledge(include, svc)
         kt = self._get_token_count(knowledge)

         raw_in = task.get("in", {}).get("pattern") or None
         input_content = ""
         if raw_in:
             inp_path = self._resolve_path(raw_in)
             input_content = inp_path.read_text(encoding='utf-8') if inp_path else ""
         pt = self._get_token_count(input_content + knowledge)

         total = kt + pt
         task['_know_tokens'] = kt
         task['_prompt_tokens'] = pt
         task['_token_count'] = total

         TodoService._start_task(task, file_lines_map)

         prompt_parts = []
@@
         ai_out = svc.ask(prompt)
-        if target:
+        if target:
             backup_folder = getattr(svc, 'backup_folder', None)
             if backup_folder:
                 bf = Path(backup_folder)
@@
             # —————————— NEW: compute & write diff ——————————
+            try:
+                # read old content
+                old_txt = target.read_text(encoding='utf-8')
+            except Exception:
+                old_txt = ""
+
+            new_txt = ai_out
+            # produce a unified diff
+            diff_lines = difflib.unified_diff(
+                old_txt.splitlines(keepends=True),
+                new_txt.splitlines(keepends=True),
+                fromfile=str(target),
+                tofile=str(target),
+                lineterm=""
+            )
+            diff_txt = "".join(diff_lines)
+            if diff_txt:
+                # name diff file next to target, timestamped
+                ts = datetime.utcnow().strftime("%Y%m%d-%H%M%S")
+                diff_name = f"{target.name}-{ts}.diff"
+                diff_path = target.parent / diff_name
+                diff_path.write_text(diff_txt, encoding='utf-8')
+                logger.info("Diff logged to %s", diff_path)
+            # ————————————————————————————————————————————————

             svc.call_mcp("UPDATE_FILE", {"path": str(target), "content": ai_out})
             try:
                 self._watch_ignore[str(target)] = os.path.getmtime(str(target))
```

Save this patch into your `todo.py`. Every time a task’s focus file is updated, you’ll now get a `.diff` file beside it that records the changes.