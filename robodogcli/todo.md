# Project To-Dos


# todo.py
- [~][-] ask: todo changes
  - started: 2025-09-13 23:27 | knowledge: 33 | include: 55822 | prompt: 56064 | cur_model: x-ai/grok-code-fast-1
  - include: pattern=*robodogcli*robodog*.py  recursive`
  - out:  temp\out.py
```knowledge
1. in todo.py and task manager
2. make sure the truncation param is populated when calling format_summary in complete_task
3. the update should tell me if there was an issue with the ai_out 
```


# todo.py
- [x][-] ask: todo changes
  - started: 2025-09-13 23:02 | completed: 2025-09-13 23:04 | knowledge_tokens: 89 | include_tokens: 1894 | prompt_tokens: 2192 | cur_model: openai/o4-mini
  - include: pattern=*robodogcli*robodog*todo.py|*robodog*console.jsx|*robodoglib*router*.js  recursive`
  - out:  temp\out.py
```knowledge
1. create a /include <patter>. it should create a include.txt file with the pattern. this is now the default pattern

2. create a /plan <folder> <my plan> command. it should create a todo.md file using the default include 

2. break into multiple tasks based on grouping
3. each task needs a out file 
4. each task needs an include pattern=*robodogcli*robodog*.py  recursive`
5. use the ```knowledge block to store more details
6. ensure that each task is disabled [-][-] 
7. ensure the tasks are disabled like this [-][-] or [x][x] 
```


# todo.md
- [x][-] ask: todo changes
  - started: 2025-09-13 22:26 | completed: 2025-09-13 22:26 | knowledge_tokens: 80 | include_tokens: 1883 | prompt_tokens: 2172 | cur_model: x-ai/grok-code-fast-1
  - include: pattern=*robodogcli*robodog*todo.py|*robodog*console.jsx|*robodoglib*router*.js  recursive`
  - out:  temp\out.md
```knowledge
1. create a project plan in todo.md file format on how we can create a todo.md project plan from the robodog ui. 
the command should be /todo something
--------
2. break into multiple tasks based on grouping
3. each task needs a out file 
4. each task needs an include pattern=*robodogcli*robodog*.py  recursive`
5. use the ```knowledge block to store more details
6. ensure that each task is disabled [-][-] 
7. ensure the tasks are disabled like this [-][-] or [x][x] 
```
