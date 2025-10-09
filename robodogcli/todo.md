# file: todo.md


# todo  protask 1
- [x][~][-] knowledge: 79 | knowledge: 79 | include: 152610 | prompt: 153473
  - started: 2025-10-09T19:56:42.496600 | completed: 2025-10-09 23:57 | knowledge: 79 | include: 18054 | cur_model: openai/o4-mini
  - include: pattern=*robodogcli*robodog*.py  recursive`
  - out: temp\out.py recursiv 
  - plan: temp\plan.md
```knowledge
1. fix commit of the diff. it should apply the unified diff to the original file version. find the line and apply only the the unified diff lines.
2. if i set build_task_prompt diff = True then it is creating a diff prompt 
3. when commiting the files, it is replacing the file with the diff output. this is not correct
4. we need to apply the diff output and only change the lines defined in the unified diff.


``` 



# todo  task 2
- [~][x][-]  | knowledge: 21 | include: 47466
  - started: 2025-10-04T16:29:57.823456 | completed: 2025-10-04 20:30 | knowledge: 21 | include: 13089 | prompt: 0 | cur_model: openai/o4-mini
  - include: pattern=*robodogcli*robodog*service.py|*robodogcli*robodog*todo.py|*robodogcli*robodog*cli.py|*robodogcli*robodog*app.py|*robodogcli*robodog*todo_util.py 
  - out: temp\out.py recursiv 
  - plan: temp\plan.md
```knowledge
1. fix issues with task desc. it is appeding "| knowledge: 15 | include: 13095 | knowledge: 15 | include: 13237"
``` 