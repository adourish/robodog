# file: c:\projects\robodog\robodogcli\temp\features.md

# Project Features

This document describes the major modules of the Robodog CLI and summarizes the responsibilities of each function so you can recreate them if needed.

## cli.py

### print_help  
Outputs a list of available `/` commands and their descriptions to the log.

### parse_cmd  
Parses a line beginning with `/`, splits out the command name (without the leading slash) and its argument list.

### interact  
Main REPL loop.  
- Displays a prompt reflecting the current model and streaming mode  
- Reads user input, dispatches internal `/` commands or forwards messages to the LLM  
- Maintains the in‐memory chat context

### main  
Entry point when invoked as a script.  
- Parses CLI arguments (config path, folders, host/port, token, model, log settings, backupFolder)  
- Configures colored and file logging  
- Creates a RobodogService instance and TodoService watcher  
- Launches the MCP server thread  
- Sets initial model if provided  
- Calls `interact` and shuts down the MCP server on exit

## service.py

### RobodogService.__init__  
Loads YAML configuration, initializes LLM client, sets default roots, and prepares stash and param storage.

### _load_config  
Reads `config.yaml`, extracts providers, models, MCP server settings, and default LLM parameters.

### _init_llm  
Resolves the OpenAI API key (environment or config), creates the OpenAI client instance.

### model_provider  
Finds which provider supplies a given model name.

### ask  
Sends a user prompt to the LLM, streams or REST‐style reads responses, displays a spinner, and returns the full answer.

### list_models / set_model  
Lists configured model names and switches the active model (reinitializing the LLM client).

### set_key / get_key  
Updates or retrieves API keys for a named provider.

### stash / pop / list_stashes / clear  
Manages in‐memory snapshots of chat+knowledge; `clear` resets session state.

### import_files  
Reads files matching a glob into a single knowledge string, returns number of files read.

### export_snapshot  
Writes chat history and knowledge to a named snapshot file.

### set_param  
Sets numeric LLM parameters (temperature, top_p, penalties, max_tokens).

### call_mcp  
Sends a raw MCP operation to the local MCP HTTP/text‐plain endpoint, returns parsed JSON.

### parse_include / include  
Parses include specifiers (`all`, `file=…`, `pattern=…`, `dir=…`), finds matching files under roots, reads and concatenates content, logs token counts.

### search_files  
Recursively (or non‐recursive) globs directory trees, filters by pattern(s), returns matching file paths.

### curl / play  
Stubs for web fetch and Playwright automation commands.

### read_file / update_file / create_file / delete_file / append_file  
Basic file operations used by the MCP server.

### create_dir / delete_dir / rename / copy_file / checksum  
Directory and file management, including SHA256 checksum of a file.

## todo.py

### TodoService.__init__  
Accepts a list of project roots, loads all `todo.md` files, parses tasks, records modification times, and starts a background watch thread.

### _find_files  
Recursively finds all `todo.md` files under the configured roots.

### _load_all  
Reads each `todo.md`, splits into lines, applies regex to identify tasks (`- [ ]`, `- [~]`, `- [x]`), captures `include` and `focus` sub‐entries and any code fences as initial context, builds an in‐memory task list.

### _watch_loop  
Polls modification times of all `todo.md` files. When an external change is detected (excluding its own writes), automatically runs the next To Do task.

### run_next_task  
Selects the earliest `[ ]` task, gathers include knowledge, constructs a prompt including any code fence context, stamps start info, calls the LLM, applies focus output to the specified file, stamps completion info.

### _process_one  
Helper for `run_next_task`;  
- Gathers include knowledge via the Service  
- Counts tokens for knowledge and prompt  
- Marks task as “Doing” in the file with timestamp and token stats  
- Sends prompt to `svc.ask`, receives full‐file code response  
- Writes or updates the focus file (backing up previous versions) via MCP  
- Marks task as “Done” with completion timestamp

### _start_task / _complete_task  
In‐place edits of `todo.md` lines to toggle status characters (` `→`~`→`x`), insert or update summary lines with start/completion stamps and token usage.

### _resolve_path  
Resolves a raw focus specification to exactly one existing path, with handling for absolute, relative-with-dirs, and bare filenames.

### _apply_focus  
Backs up any existing focus file to a timestamped folder, then issues an MCP `UPDATE_FILE` to write new content. Updates the watch‐ignore map to avoid immediate retrigger.

## mcphandler.py

### run_robodogmcp  
Starts a threaded TCP server on the configured host/port, registers bearer‐auth token, injects the RobodogService instance, and serves forever in a daemon thread.

### MCPHandler.handle  
Reads the first line of a TCP stream, detects HTTP vs raw MCP protocol, dispatches accordingly.

### _handle_http  
Parses HTTP request lines and headers, enforces CORS and bearer auth, reads JSON payload, calls `_dispatch`, and returns JSON response.

### _dispatch  
Maps MCP operations to Service methods:  
- File service ops: `LIST_FILES`, `READ_FILE`, `UPDATE_FILE`, etc.  
- Task ops: `TODO` triggers the next To Do task  
- Include/Ask ops: `INCLUDE`, `ASK`  
- Model/key ops: `LIST_MODELS`, `SET_MODEL`, `SET_KEY`, `GET_KEY`  
- Stash ops: `STASH`, `POP`, `LIST_STASHES`, `CLEAR`  
- Snapshot ops: `IMPORT_FILES`, `EXPORT_SNAPSHOT`  
- Parameter ops: `SET_PARAM`  
- And other passthroughs: `CURL`, `PLAY`, `QUIT`/`EXIT`

### ThreadedTCPServer  
Custom mixin enabling concurrent connections and address reuse.

---

All modules are designed for zero‐install, portable operation, with comprehensive logging, token usage metrics, and automated task processing via markdown‐based `todo.md` files.