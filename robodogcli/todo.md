

# todo  promots
- [x][x][-] logging in todo
  - started: 2025-09-22T12:43:38.062604 | completed: 2025-09-22 16:44 | knowledge: 93 | include: 45708 | prompt: 46268 | cur_model: x-ai/grok-4-fast:free | compare: UPDATE C:\projects\robodog\robodogcli\robodog\todo.py O:3938 N:3935 D:-3 
  - include: pattern=*robodogcli*robodog*service.py|*robodogcli*robodog*todo.py|*robodogcli*robodog*builder.py|*robodogcli*robodog*cli.py|*robodogcli*robodog*mcphandler.py    recursive`
  - out: out.py recursive
```knowledge
1. todo currently supports 2 steps [x][x] 
step 1: run LLM task
step 2: commit LLM response

2. enhance to support three steps [x][x][x]
step 1: plan LLM task. create/read/update the plan.md  [x][-][-]
step 2: run LLM task  [x][x][-]
step 3: commit LLM response  [x][x][x]

ensure that the fist [x] will work on planning with the plan.md file
ensure that the second [x] will work on the task using the plan.md, knowledge, task desc, and include
ensure that the third [x] will work on the commit sending the out file into the destination
```