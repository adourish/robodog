# Project To-Dos


# tasks and todo
- [x][x] changes to tasks and todo
  - started: None | completed: 2025-09-14 13:28 | knowledge: 0 | include: 0 | prompt: 0 | cur_model: x-ai/grok-code-fast-1 | commit: success
  - include: pattern=*robodogcli*robodog*.py  recursive`
  - out:  temp\out.py
```knowledge
1. in todo.py and task manager
2. make sure the truncation param is populated when calling format_summary in complete_task
3. the update should tell me if there was an issue with the ai_out 
```


# enhance cli
- [x][-] enhance the cli with plan and include
  - started: 2025-09-13 23:02 | completed: 2025-09-13 23:04 | knowledge_tokens: 89 | include_tokens: 1894 | prompt_tokens: 2192 | cur_model: openai/o4-mini
  - include: pattern=*robodogcli*robodog*todo.py|*robodog*console.jsx|*robodoglib*router*.js  recursive`
  - out:  temp\out-enhance.py
```knowledge
1. create a /include <patter>. it should create a include.txt file with the pattern. this is now the default pattern

2. create a /plan <folder> <my plan> command. it should create a todo.md file using the default include 

2. break into multiple tasks based on grouping
3. each task needs a 'out: tmp\file.ext' 
4. each task needs an 'include: pattern=*robodogcli*robodog*.py  recursive` or appropriate matching pattern
5. use the ```knowledge block to store more details
6. ensure that each task is disabled [-][-] 
7. ensure the tasks are disabled like this [-][-] or [x][x] 
```


# plan a todo.md
- [x][-] ask: todo changes
  - started: 2025-09-14 14:21 | completed: 2025-09-14 14:21 | knowledge: 143 | include: 1920 | prompt: 2293 | cur_model: x-ai/grok-code-fast-1 | truncation: warning | truncation: error
  - include: pattern=*robodogcli*robodog*todo.py|*robodog*console.jsx|*robodoglib*router*.js  recursive`
  - out:  temp\out.md
```knowledge
1. create a project plan in todo.md file format (see a-f format instructions).
2. enhance parse_llm_output. to set matchedfilename using the self._file_service.resolve_path(frag) function. it will do a smart match
3. if there is no match, it might be a new file. create a property explaining that it might be a new file
4. we are planning mode only no code yet. ignore all other insructions

--------
todo.md format instructions
a. break into multiple tasks based on grouping
b. each task needs a out file. out: temp\out-<filename.ext>
c. each task needs an include pattern=*robodogcli*robodog*.py  recursive`
d. use the ```knowledge block to store more details
e. ensure that each task is disabled [-][-] 
f. ensure the tasks are disabled like this [-][-] or [x][x] 
g. ensure there is a markdown header with sequencing details and other info
h. clearly show that this todo.md was generated
```
