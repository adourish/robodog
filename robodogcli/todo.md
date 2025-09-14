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
  - started: 2025-09-14 23:34 | completed: 2025-09-14 23:34 | knowledge: 45 | include: 57076 | prompt: 57360 | cur_model: x-ai/grok-code-fast-1 | truncation: warning | truncation: error | compare: parse_service.py (o/n/d tokens:1175/650/-549) c=46.7%,
  - include: pattern=*robodogcli*robodog*.py  recursive`
  - out:  temp\out.py
```knowledge

2. make sure the compare is added to the status 
3. it should look like this. "started: 2025-09-14 23:20 | completed: 2025-09-14 23:20 | knowledge: 9 | include: 57806 | prompt: 58054 | cur_model: x-ai/grok-code-fast-1 | compare: <filename.ext> (o/n/d tokens:193/253/36) c=18.7%, <filename2.ext> (o/n/d tokens:193/253/36) c=18.7%,  
```
