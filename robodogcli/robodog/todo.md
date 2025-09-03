---
base: c:\projects\robodog
---
# Project To-Dos
  
# mcphandler.py
- [x] ask: enhance mcp
  - include: pattern=*robodog*.md|*robodog*.py  recursive`
  - in:  robodogcli\robodog\mcphandler.py
  - out:  robodogcli\robodog\mcphandler-v2.py
```knowledge
mcphandler.py

```


# service.py
- [x] ask: enhance service
  - include: pattern=*robodog*.md|*robodog*.py  recursive`
  - in:  robodog\robodogcli\robodog\service.py
  - out:  robodog\robodogcli\robodog\service-v2.py
```knowledge
service.py

```

# todo.py
- [x] ask: enhance todo
  - started: 2025-09-03 22:54 | completed: 2025-09-03 22:55 | know_tokens: 47323 | prompt_tokens: 48403 | total_tokens: 95726
  - include: pattern=*robodog*.md|*robodogcli*robodog*.py  recursive`
  - in:  robodogcli\robodog\todo.py
  - out:  robodogcli\robodog\todo-v2.py
```knowledge
1. log both the inpat/outpath and the actual target paths for both
2. give me a full drop in file
4. do not make any other code change
5. do not remove any comments
6. do not refactor any existing code
```


# cli.py
- [x] ask: enhance cli
  - started: 2025-09-01 20:05 | completed: 2025-09-01 20:06 | know_tokens: 24294 | prompt_tokens: 24349 | total_tokens: 48643
  - include: pattern=*robodog*.md|*robodog*.py  recursive`
  - in:  robodogcli\robodog\cli.py
  - out:  robodogcli\robodog\cli-v2.py
```knowledge
cli.py

```

# project features
- [x] ask: project features.md
  - started: 2025-09-01 22:40 | completed: 2025-09-01 22:41 | know_tokens: 25322 | prompt_tokens: 25407 | total_tokens: 50729
  - include: pattern=*robodog*.md|*robodog*.py  recursive`
  - in:  robodogcli\robodog\features.md
  - out:  robodogcli\robodog\features-v2.md
```knowledge
1. generate a features.md file. 
2. it should create a section for each python file cli.py, service.py, todo.py, and mcphandler.
3. describe what each function does so you could recreate it.

```


# project README
- [x] ask: project README.md
  - started: 2025-09-03 23:10 | completed: 2025-09-03 23:10 | know_tokens: 54226 | prompt_tokens: 55460 | total_tokens: 109686
  - include: pattern=*robodog*README*.md|*robodog*.py  recursive`
  - in:  robodog\README.md
  - out:  robodog\README-v2.md
```knowledge
1. update the README.md
2. Update the todo.md features with lots of examples. Update with the new syntax

```