Here’s one way to layer “multi-agent” support into your existing `/todo` runner in three steps:

1) Add an `agent:` field to each task in todo.md  
   ­– Simply treat it like your other sub-entries:
     ```md
     - [ ] Generate SDK client
       - agent: agent1
       - include: pattern=api/**/*.py recursive
       - focus: file=src/sdk/client.py
     ```
   ­– You can define as many agents (agent1, agent2, …) as you like.  

2) Wire up a map of `RobodogService` instances in your CLI startup  
   ­– After you create your “main” service:
     ```python
     svc = RobodogService("config.yaml")
     # build one per agent
     agents = {
       "agent1": RobodogService("config.agent1.yaml"),
       "agent2": RobodogService("config.agent2.yaml"),
     }
     todo = TodoService(roots)
     todo.agents = agents      # stash the map on your TodoService
     svc.todo = todo
     ```
   ­– In `_process_one()`, pick the right service for each task by its `agent` field:
     ```python
     # inside TodoService._process_one(...)
     name    = task.get("agent")                # e.g. "agent1"
     agent_s = self.agents.get(name, svc)       # fallback → default svc
     ai_out  = agent_s.ask(prompt)
     agent_s.call_mcp("UPDATE_FILE", {
       "path": str(target),
       "content": ai_out
     })
     ```

3) (Optional) Fire off tasks in parallel  
   ­– Instead of grabbing only the first `[ ]` task, you can collect all “To Do” tasks and push them into a thread‐pool. Each worker picks its service as above:
   ```python
   from concurrent.futures import ThreadPoolExecutor, as_completed

   def run_all_tasks(self):
       self._load_all()
       todo = [t for t in self._tasks if STATUS_MAP[t["status_char"]] == "To Do"]
       if not todo:
           logger.info("No To Do tasks.")
           return

       with ThreadPoolExecutor(max_workers=len(todo)) as pool:
           futures = []
           for t in todo:
               svc_for_t = self.agents.get(t.get("agent"), self._svc)
               futures.append(pool.submit(self._process_one, t, svc_for_t, self._file_lines))
           for f in as_completed(futures):
               try:
                   f.result()
               except Exception as e:
                   logger.error("Task failed: %s", e)

       logger.info("All To Do tasks completed.")
   ```
   ­– You can expose that as a new `/todo all` command or a CLI flag.

With these three changes you’ll have per-task agent selection, a service-instance map, and—if you choose—a fully concurrent runner.