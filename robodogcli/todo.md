# Project To-Dos


# tasks and todo
- [x][~] changes to tasks and todo
  - started: None | completed: 2025-09-14 21:22 | knowledge: 0 | include: 0 | prompt: 0 | cur_model: openai/o4-mini | commit: warning
  - include: pattern=*robodogcli*robodog*.py  recursive`
  - out:  temp\out.py
```knowledge
0. enhance parse service
1 change the unified diff markdown output to make use of emojis below

```

# parse service
- [x][-] changes to parse service
  - started: 2025-09-14 21:50 | completed: 2025-09-14 21:51 | knowledge: 73 | include: 57347 | prompt: 57659 | cur_model: x-ai/grok-code-fast-1
  - include: pattern=*robodogcli*robodog*.py  recursive`
  - out:  temp\out.py
```knowledge

1. in parse service. make the numbering match the two files being diffed. it should not be a sequence. 
2. use a default of 20 diff files. delete any older files when creating the new files.
3. it should be a rolling 20.
4. later we can pass this from the command cli
🧩 @@ -196,24 +190,18 @@
[ 190⚪]         md_lines.append("## 🔍 Unified Diff (With Emojis & File Line Numbers)")
[ 191⚪]         md_lines.append("```diff")

```

# parse service
- [x][x] changes to tasks and todo
  - started: None | completed: 2025-09-14 23:18 | knowledge: 0 | include: 0 | prompt: 0 | cur_model: openai/o4-mini | commit: success
  - include: pattern=*robodogcli*robodog*.py  recursive`
  - out:  temp\out.py
```knowledge
1. add the compare information to the format_summary
2. it should show up when completing a commit task or a single task. 
e.g, compare: <filename.ext> (o/n/d tokens:193/253/36) c=18.7%, <filename2.ext> (o/n/d tokens:193/253/36) c=18.7%, 

```
# parse service
- [x][-] changes to tasks and todo
  - started: 2025-09-14 23:40 | completed: 2025-09-14 23:40 | knowledge: 6 | include: 57083 | prompt: 57328 | cur_model: x-ai/grok-code-fast-1 | compare: parse_service.py (o/n/d tokens:1176/1221/21) c=1.8%,
  - include: pattern=*robodogcli*robodog*.py  recursive`
  - out:  temp\out.py
```knowledge

2. add debugging to the parser

```

# cli to service
- [~][-] changes cli and service security
  - started: 2025-09-20 14:49 | knowledge: 50 | include: 83453 | prompt: 84051 | cur_model: openai/o4-mini
  - include: pattern=*robodogcli*robodog*.py  recursive`
  - out:  temp\out.py
```knowledge

1. fix the todo complete. 
2. the complete works for commit flow compare: mcphandler.py (o/n/d tokens:954/1067/89) c=9.3%,
3. in commit flowwe see 

```


# todo  promots
- [x][-] logging in todo
  - started: 2025-09-21T23:18:22.395173 | completed: 2025-09-22 03:18 | knowledge: 24 | include: 44810 | prompt: 45276 | cur_model: x-ai/grok-4-fast:free | compare: UPDATE C:\Projects\robodog\robodogcli\robodog\todo.py O:3299 N:3265 D:-34 
  - include: pattern=*robodogcli*robodog*service.py|*robodogcli*robodog*todo.py|*robodogcli*robodog*builder.py|*robodogcli*robodog*cli.py|*robodogcli*robodog*mcphandler.py    recursive`
  - out: out.py recursive
```knowledge
1. enhance the prompt builder and todo to support more file operations
2. DELETE_DIR
3. RENAME
4. CREATE_DIR
5. DELETE_FILE
support these operations from the mcp handler
```


# todo  promots
- [x][-] logging in todo
  - started: 2025-09-21T23:44:43.241707 | completed: 2025-09-22 03:45 | knowledge: 26 | include: 45053 | prompt: 45546 | cur_model: x-ai/grok-4-fast:free | compare: UPDATE C:\Projects\robodog\robodogcli\robodog\prompt_builder.py O:1905 N:2097 D:192 , UPDATE C:\Projects\robodog\robodogcli\robodog\parse_service.py O:2319 N:1890 D:-429 , UPDATE C:\Projects\robodog\robodogcli\robodog\todo.py O:3299 N:628 D:-2671 
  - include: pattern=*robodogcli*robodog*service.py|*robodogcli*robodog*todo.py|*robodogcli*robodog*builder.py|*robodogcli*robodog*cli.py|*robodogcli*robodog*mcphandler.py    recursive`
  - out: out.py recursive
```knowledge
1. enhance the prompt builder and todo to support more file operations
2. enhance the prompt to support COPY_FILE, DELETE_FILE, CREATE_DIR, DELETE_DIR from the mcp handler
 
```