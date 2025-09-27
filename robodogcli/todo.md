# file: todo.md


# todo  promots
- [x][x][x] knowledge: 60
  - started: 2025-09-27T13:57:30.393702 | completed: 2025-09-27 17:57 | knowledge: 94 | include: 69084 | prompt: 0 | cur_model: x-ai/grok-4-fast:free | compare: UPDATE C:\Projects\robodog\robodogcli\robodog\file_service.py O:2028 N:2023 D:-5 
  - include: pattern=*robodogcli*robodog*service.py|*robodogcli*robodog*todo.py|*robodogcli*robodog*builder.py|*robodogcli*robodog*cli.py|*robodogcli*robodog*mcphandler.py|*robodogcli*robodog*todo_util.py    recursive`
  - out: temp\out.py recursive
  - plan: temp\plan.md
```knowledge
1. in file_service _fix_comment_directive there are situations where we should NOT write or remove the directive
2. for xml files, we cannot have any comments before the <xml> tag at the start. handle this use case. support other files like it
3. only change the file service
4. if the file is type xml/json, do not add any additional content to the file
5. if the file is type xml/json, remove any comments in the first few lines look for # // <~-->
6. no comments in xml/json files in the first few lines
```