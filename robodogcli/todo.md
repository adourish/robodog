# file: todo.md


# todo  promots
- [x][x][x] knowledge: 60
  - started: 2025-09-27T09:48:49.608072 | completed: 2025-09-27 13:48 | knowledge: 60 | include: 67859 | prompt: 0 | cur_model: x-ai/grok-4-fast:free | compare: UPDATE C:\Projects\robodog\robodogcli\robodog\file_service.py O:1853 N:2025 D:172 
  - include: pattern=*robodogcli*robodog*service.py|*robodogcli*robodog*todo.py|*robodogcli*robodog*builder.py|*robodogcli*robodog*cli.py|*robodogcli*robodog*mcphandler.py|*robodogcli*robodog*todo_util.py    recursive`
  - out: temp\out.py recursive
  - plan: temp\plan.md
```knowledge
1. in file_service _fix_comment_directive there are situations where we should NOT write or remove the directive
2. for xml files, we cannot have any comments before the <xml> tag at the start. handle this use case. support other files like it
3. only change the file service
4. remove or do not add the directive if the file is xml/json
```