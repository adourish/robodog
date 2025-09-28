# file: todo.md


# todo  promots
- [x][~][-]  | knowledge: 131 | include: 71187 | prompt: 72232
  - started: 2025-09-27T21:24:46.571349 | completed: 2025-09-28 01:25 | knowledge: 131 | include: 71187 | prompt: 0 | cur_model: x-ai/grok-4-fast:free
  - include: pattern=*robodogcli*robodog*service.py|*robodogcli*robodog*todo.py|*robodogcli*robodog*builder.py|*robodogcli*robodog*cli.py|*robodogcli*robodog*mcphandler.py|*robodogcli*robodog*todo_util.py    recursive`
  - out: temp\out.py recursive
  - plan: temp\plan.md
```knowledge
1. fix the ui errors with textual 
2. it should look like the first task in the todo. it should have the status [x][x][x]
3. it should allow you to toggle the plan, task exeuction, and commit from [ ][-][x][~] at any time [x][x][x]
4. it should like you change the desc
it should like you change the out and plan file
6. it should let you change the include
7. it should show the status
8. it should let me type commands like /models /model openai etc
9. it should let me scroll up through the output
10. THE UI SHOULD LOOK LIKE THIS
---------------------------------------

output WINDOW

                                        SCROLL BAR. UP/DOWN TO SCROLL
                                        |    
----------------------------------------
[X][X][X] DESC
--------------------------------------
/MYCOMMAND HERE


-----------------------------------------
P=TOGGLE PLAN MODEL E=EXECUTE TASK    C=COMMIT   
/PLAN OR /EXEC  /COMMIT 

```