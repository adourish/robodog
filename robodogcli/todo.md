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
  - started: 2025-09-15 16:54 | knowledge: 50 | include: 66158 | prompt: 66457 | cur_model: openai/o4-mini
  - include: pattern=*robodogcli*robodog*.py  recursive`
  - out:  temp\out.py
```knowledge

1. fix the todo complete. 
2. the complete works for commit flow compare: mcphandler.py (o/n/d tokens:954/1067/89) c=9.3%,
3. in commit flowwe see 
- started: None | completed: 2025-09-15 01:12 | knowledge: 0 | include: 0 | prompt: 0 | cur_model: openai/o4-mini | commit: success | compare: mcphandler.py (o/n/d tokens:954/1067/89) c=9.3%,


```

```

# todo 
- [x][x] changes todo
  - started: None | completed: 2025-09-16 03:28 | knowledge: 0 | include: 0 | prompt: 0 | cur_model: openai/o4-mini | commit: success | compare: 'service.py' (o/n/d/c: 1332/1350/18/1.4%) 
  - include: pattern=*robodogcli*robodog*service.py|*robodogcli*robodog*todo.py  recursive`
  - out:  temp\out.py
```knowledge

1. identify and mark unused functions with ## NOT USED!!!
2. do not refactor or change any logic. 
3. review your changes, 
```