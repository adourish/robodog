# file: todo.md


# todo  promots
- [x][-][-] my task
  - started: 2025-09-26T18:59:05.576018 | completed: 2025-09-26 22:59 | knowledge: 73 | include: 67514 | prompt: 0 | cur_model: x-ai/grok-4-fast:free
  - include: pattern=*robodogcli*robodog*service.py|*robodogcli*robodog*todo.py|*robodogcli*robodog*builder.py|*robodogcli*robodog*cli.py|*robodogcli*robodog*mcphandler.py|*robodogcli*robodog*todo_util.py    recursive`
  - out: temp\out.py recursive
  - plan: temp\plan.md
```knowledge
1. when the plan, task execution, or commit starts, we need to update the task status and the todo.md file to prevent duplicate runs.
2. ensure that this is done at the beginning of execution
3. when running the plan [~][-][-]
4. when running the task execution [x][~][-]
5. when running the commit [x][x][~]
6. this has to happen as soon as the task is picked up. 
7. perform double check locking pattern 
```