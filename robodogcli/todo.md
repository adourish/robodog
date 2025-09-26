

# todo  promots
- [x][x][x] [-] [-] [-] [-] status
  - started: 2025-09-26T14:41:23.676187 | completed: 2025-09-26 18:41 | knowledge: 100 | include: 65477 | prompt: 0 | cur_model: x-ai/grok-4-fast:free | compare: UPDATE C:\projects\robodog\robodogcli\robodog\file_service.py O:1517 N:1712 D:195 , UPDATE C:\projects\robodog\robodogcli\robodog\parse_service.py O:2399 N:2512 D:113 
  - include: pattern=*robodogcli*robodog*service.py|*robodogcli*robodog*todo.py|*robodogcli*robodog*builder.py|*robodogcli*robodog*cli.py|*robodogcli*robodog*mcphandler.py|*robodogcli*robodog*todo_util.py    recursive`
  - out: temp\out.py recursive
  - plan: temp\plan.md
```knowledge
1. in the file_service add some cleanup mechanism to fix any files being written that have the wrong type of comment block
2. if javascript, typescript, java, xml, json, list as many types as possible.
3. if we see the wrong kind of comment in these files, add the correct comment at the start of the file. e.g., # file: in an XML is not correct
4. do the same for reading the file. 
5. when the file and replacing the comment block. if it is type <!-- . ensure the end of line has the ending comment block -->
```