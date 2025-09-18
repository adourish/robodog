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
- [x][x] changes todo | started: 2025-09-17T23:24:18.813225 | knowledge: 35
  - started: 2025-09-17T23:23:00.770205 | completed: 2025-09-18 03:23 | knowledge: 35 | include: 36495 | prompt: 36815 | cur_model: openrouter/sonoma-sky-alpha | compare: prompt_builder.py (o/n/d/c: 701/857/156/22.3%)  -> C:\Projects\robodog\robodogcli\robodog\prompt_builder.py, parse_service.py (o/n/d/c: 1210/1287/77/6.4%)  -> C:\Projects\robodog\robodogcli\robodog\parse_service.py
  - include: pattern=*robodogcli*robodog*service.py|*robodogcli*robodog*todo.py|*robodogcli*robodog*builder.py|*robodogcli*robodog*cli.py|*robodogcli*robodog*mcphandler.py    recursive`
  - out:  temp\out.py
```knowledge
1. enhance the prompt_builder and parser to support other comment blocks 
2. e.g., "# file: <filename>" should be "// file: <filename> " for javascript frameworks
3. handle other file types. it is working for python


```


# todo 
- [x][-] changes todo
  - started: 2025-09-16 23:31 | completed: 2025-09-16 23:32 | knowledge: 10 | include: 25472 | prompt: 25767 | cur_model: openai/o4-mini | compare: parse_service.py (o/n/d/c: 1052/1066/14/1.3%)
  - include: pattern=*robodogcli*robodog*service.py|*robodogcli*robodog*todo.py|*robodogcli*robodog*mcphandler.py|*robodogcli*robodog*cli.py|*robodogcli*robodog*cli.py   recursive`
  - out:  temp\out.py
```knowledge


```