# Project To-Dos

# fix logging
- [x] ask: fix logging. change logging so that it gets log level through command line. change logger so that it takes log level from the command line param
  - include: pattern=*robodog*.md|*robodog*.py  recursive`
  - focus: file=c:\projects\robodog\robodogcli\robodog\cli3.py
```code
my knowledge
```

# add features to mchhandler.py
- [x] ask: add mcp features
  - include: pattern=*robodog*.md|*robodog*.py  recursive`
  - focus:   file=c:\projects\robodog\robodogcli\temp\service.log
```code
1. add more features to mcphandlers. 
2. make sure all of the features from service.py and todo.py are add to mcp. 
3. do not change or remove any existing features. only add missing features
```

# fix logger
- [x] change app prints in service logger
  - include: pattern=*robodog*.md|*robodog*.py  recursive`
  - focus:   file=c:\projects\robodog\robodogcli\robodog\service-out.py
```code
1. change all prints to logger.info
```



# todo fix counts
- [x] change _process_one
  - include: pattern=*robodog*.md|*robodog*.py  recursive`
  - focus: file=c:\projects\robodog\robodogcli\temp\todo.log
```code
1. Add concurrency to _process_one. 



```

# todo fix counts
- [x] change svc ask
  - include: pattern=*robodog*.md|*robodog*.py|*todo.md   recursive`
  - focus: file=c:\projects\robodog\robodogcli\temp\service.log
```code
1. change def ask(self, prompt: str) -> str:
2. change print(delta, end="", flush=True)
3. i dont need to see all the text stream to stdout. 
4. only show the latest line and some spinning emojis. use animals that are thinking

```

# todo readme
- [x] readme
  - include: pattern=*robodog*.md|*robodog*.py|*todo.md   recursive`
  - focus: file=c:\projects\robodog\robodogcli\temp\service.log
```code
1. do not remove any content
2. add a new readme section for the /todo feature with examples of the todo.md files and how you can have as many as possible
3. give lots of exampkes of file formats


```


# todo readme
- [x] readme
  - started: 2025-08-31 13:47 | completed: 2025-08-31 13:48 | tokens: 0
  - include: pattern=*robodog*.md|*robodog*.py|*todo.md   recursive`
  - focus: file=c:\projects\robodog\robodogcli\temp\todo.log
```code
1. do not remove any content
2. update _start_task and def _complete_task(task: dict, file_lines_map: dict):
3. for the started and completed log. change it to be one line that is either insert or update. never append. add the started time and then give me one line summary of started, ended, how many tokens were used. 

```


# todo status
- [x] readme
  - started: 2025-08-31 14:02 | completed: 2025-08-31 14:02 | know_tokens: 45172 | prompt_tokens: 45282 | total_tokens: 90454
  - include: pattern=*robodog*.md|*robodog*.py|*todo.md   recursive`
  - focus: file=c:\projects\robodog\robodogcli\temp\todo.log
```code
1. do not remove any content
2. update _start_task and def _complete_task(task: dict, file_lines_map: dict):
3. create a function to get the summary content. reuse it in both places.
4. when starting, include the tokens found. it should log the total prompt tokens and knowledge tokens.
5. only change the status information. do not change any other logic
```