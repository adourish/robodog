# Project To-Dos

# fix logging
- [x] ask: fix logging. change logging so that it gets log level through command line. change logger so that it takes log level from the command line param
  - include: pattern=*robodog*.md|*robodog*.py  recursive`
  - focus: file=c:\projects\robodog\robodogcli\robodog\cli3.py
```knowledge
my knowledge
```

# add features to mchhandler.py
- [x] ask: add mcp features
  - started: 2025-09-01 13:57 | completed: 2025-09-01 13:58 | know_tokens: 27277 | prompt_tokens: 27366 | total_tokens: 54643
  - include: pattern=*robodog*.md|*robodog*.py  recursive`
  - focus:   file=c:\projects\robodog\robodogcli\temp\service.log
```knowledge
1. add more features to mcphandlers. 
2. make sure all of the features from service.py and todo.py are add to mcp. 
3. do not change or remove any existing features. only add missing features
```

# fix logger
- [x] change app prints in service logger
  - include: pattern=*robodog*.md|*robodog*.py  recursive`
  - focus:   file=c:\projects\robodog\robodogcli\robodog\service-out.py
```knowledge
1. change all prints to logger.info
```



# todo fix counts
- [x] change _process_one
  - include: pattern=*robodog*.md|*robodog*.py  recursive`
  - focus: file=c:\projects\robodog\robodogcli\temp\todo.log
```knowledge
1. Add concurrency to _process_one. 



```

# todo fix counts
- [x] change svc ask
  - include: pattern=*robodog*.md|*robodog*.py|*todo.md   recursive`
  - focus: file=c:\projects\robodog\robodogcli\temp\service.log
```knowledge
1. change def ask(self, prompt: str) -> str:
2. change print(delta, end="", flush=True)
3. i dont need to see all the text stream to stdout. 
4. only show the latest line and some spinning emojis. use animals that are thinking

```

# todo readme
- [x] readme
  - started: 2025-09-01 13:47 | completed: 2025-09-01 13:48 | know_tokens: 48459 | prompt_tokens: 48550 | total_tokens: 97009
  - include: pattern=*robodog*.md|*robodog*.py|*todo.md   recursive`
  - focus: file=c:\projects\robodog\robodogcli\temp\service.log
```knowledge
1. do not remove any content
2. add a update readme section for the /todo feature with examples of the todo.md files and how you can have as many as possible
3. give lots of exampkes of file formats


```


# todo readme
- [x] readme
  - started: 2025-08-31 13:47 | completed: 2025-08-31 13:48 | tokens: 0
  - include: pattern=*robodog*.md|*robodog*.py|*todo.md   recursive`
  - focus: file=c:\projects\robodog\robodogcli\temp\todo.log
```knowledge
1. do not remove any content
2. update _start_task and def _complete_task(task: dict, file_lines_map: dict):
3. for the started and completed log. change it to be one line that is either insert or update. never append. add the started time and then give me one line summary of started, ended, how many tokens were used. 

```


# todo status
- [x] readme
  - started: 2025-08-31 14:02 | completed: 2025-08-31 14:02 | know_tokens: 45172 | prompt_tokens: 45282 | total_tokens: 90454
  - include: pattern=*robodog*.md|*robodog*.py|*todo.md   recursive`
  - focus: file=c:\projects\robodog\robodogcli\temp\todo.log
```knowledge
1. do not remove any content
2. update _start_task and def _complete_task(task: dict, file_lines_map: dict):
3. create a function to get the summary content. reuse it in both places.
4. when starting, include the tokens found. it should log the total prompt tokens and knowledge tokens.
5. only change the status information. do not change any other logic
```

# todo status
- [x] security
  - started: 2025-09-01 14:06 | completed: 2025-09-01 14:07 | know_tokens: 48900 | prompt_tokens: 49050 | total_tokens: 97950
  - include: pattern=*robodog*.md|*robodog*.py|*todo.md   recursive`
  - focus: file=c:\projects\robodog\robodogcli\temp\todo.log
```knowledge
1. do not remove any content
2. create a function that validates that the path is within the --folders locations
3. update search_files and and any file operations to validate the path is within the location
4. dont change any other logic


    def read_file(self, path: str):

    def update_file(self, path: str, content: str):

    def create_file(self, path: str, content: str = ""):

    def delete_file(self, path: str):

    def append_file(self, path: str, content: str):

    def create_dir(self, path: str, mode: int = 0o755):

    def delete_dir(self, path: str, recursive: bool = False):

    def rename(self, src: str, dst: str):
    

    def copy_file(self, src: str, dst: str):
        

 
```