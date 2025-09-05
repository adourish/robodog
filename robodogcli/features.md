# file: features-v2.md

# Project Features

This document enumerates the key modules in RobodogCLI and describes, in enough detail, each feature and its implementation so that you can re-create the application from scratch.

---

## 1. CLI Front-End (cli.py)

### REPL & Command Parsing
- Prompts: `[<model>]»` or `>` indicates current model and streaming mode.
- `interact()`  
  • Reads user lines  
  • If line starts with `/`, calls `parse_cmd()` and dispatches; otherwise sends text as user message to the LLM  
  • Catches errors and logs stack traces  

- `parse_cmd(line)`  
  • Splits on whitespace  
  • Returns `cmd` (without leading `/`) and `args` list  

### Built-in “/” Commands
- `/help`  
  Lists all supported commands and descriptions (uses `print_help()`).

- `/models`  
  Calls `svc.list_models()` to enumerate configured models.

- `/model <name>`  
  Calls `svc.set_model(name)`, logs new model.

- `/key <provider> <key>` and `/getkey <provider>`  
  Set or get an API key for a provider.

- `/folders <dir1> [dir2 …]`  
  Invokes `svc.call_mcp("SET_ROOTS", {"roots": args})`.

- `/include <spec> [prompt]`  
  Parses an include spec (`pattern=…`, `file=…`, `recursive`) plus optional prompt, calls `svc.include(spec)` then `svc.ask(prompt+knowledge)`.

- `/curl <url…>`  
  Delegates to `svc.curl(args)`.

- `/play <instructions>`  
  Delegates to `svc.play(instructions)`.

- `/mcp <OP> [JSON]`  
  Sends a raw MCP operation: `svc.call_mcp(OP, payload)`.

- `/import <glob>` / `/export <filename>`  
  Wraps `svc.import_files()` and `svc.export_snapshot()`.

- Session management:  
  `/clear`, `/stash <name>`, `/pop <name>`, `/list` stashes.

- Parameter tuning:  
  `/temperature`, `/top_p`, `/max_tokens`, `/frequency_penalty`, `/presence_penalty`.

- Streaming toggle: `/stream` or `/rest`.

- `/todo`  
  Triggers `svc.todo.run_next_task(svc)` to process the next outstanding task.

### Startup (`main`)
- Parses CLI flags: `--config`, `--folders`, `--host`, `--port`, `--token`, `--model`, `--log-file`, `--log-level`, `--backupFolder`.
- Configures colorized console logging and file logging.
- Instantiates:
  - `RobodogService(args.config)`
  - `TodoService(args.folders)`
  - Sets `svc.backup_folder`
- Launches MCP server thread via `run_robodogmcp(...)`.
- Optionally sets startup model.
- Calls `interact(svc)`; on exit, shuts down the MCP server.

---

## 2. Service Layer (service.py)

### Configuration & Initialization
- **`__init__(config_path, api_key=None)`**  
  • Calls `_load_config()` to read `config.yaml`  
  • Sets default `_roots` to cwd (overwritten by `cli`)  
  • Calls `_init_llm(api_key)`  

- **`_load_config(path)`**  
  Reads YAML:  
  - `configs.providers`: list of `{provider, baseUrl, apiKey}`  
  - `configs.models`: list of `{provider, model, stream, ...}`  
  - `mcpServer`: `{baseUrl, apiKey}`  
  Sets default model, streaming flag, and numeric params.

- **`_init_llm(api_key)`**  
  Resolves API key (explicit / env / config), instantiates `OpenAI(api_key=…)` client.

### Core Chat & LLM
- **`ask(prompt)`**  
  • Builds chat completion request with current model and parameters.  
  • If `stream=True`, iterates chunks, prints rotating “cylon” spinner, updates terminal title.  
  • If `stream=False`, waits for full response.  
  • Returns assembled text.

- **`list_models()` / `set_model(name)`**  
  Lists available models or switches, re-inits LLM client.

- **`set_key(provider, key)` / `get_key(provider)`**  
  Manage API keys for multiple providers.

### Stashes / Snapshots
- **`stash(name)` / `pop(name)` / `list_stashes()`**  
  In-memory stash of chat+knowledge.

- **`clear()`**  
  Reset chat and knowledge (stubbed for extension).

- **`import_files(glob)`**  
  Reads all files matching the glob, concatenates content into one knowledge string, returns count.

- **`export_snapshot(filename)`**  
  Writes chat history and current knowledge into a text file.

### Numeric Parameters
- **`set_param(key,value)`**  
  E.g. `temperature`, `top_p`, `max_tokens`, `frequency_penalty`, `presence_penalty`.

### MCP Client
- **`call_mcp(op, payload, timeout)`**  
  Posts to MCP server as plain text: `"OP {...}\n"`, returns JSON result.

### Include / Knowledge Gathering
- **`parse_include(text)`**  
  Splits on spaces, recognizes:  
  - `all`  
  - `file=...`  
  - `pattern=...`  
  - `dir=...` + optional `pattern=` and `recursive`  
  Returns `{type, file, dir, pattern, recursive}`.

- **`include(spec_text)`**  
  Calls `parse_include()`, constructs one or more “search” specs, chooses `roots` from `svc.todo._roots` or its own `_roots`, calls `search_files()`, reads each matching file concurrently, logs token counts via `tiktoken`, and returns big knowledge blob.

- **`search_files(patterns, recursive, roots, exclude_dirs)`**  
  Walks given roots, filters filenames by glob patterns and excludes directories like `node_modules`.

### Web & Automation
- **`curl(tokens)`** – placeholder for fetch/JS execution.
- **`play(instructions)`** – placeholder for Playwright automation.

### MCP-Server File Ops
- **`read_file(path)`** / **`update_file(path,content)`** / **`create_file(path,content)`** / **`delete_file(path)`** / **`append_file(path,content)`**  
- **`create_dir(path, mode)` / `delete_dir(path,recursive)`**  
- **`rename(src,dst)` / `copy_file(src,dst)`**  
- **`checksum(path)`** – compute SHA256 of a file.

---

## 3. To-Do Task Runner (todo.py)

### Initialization
- **`__init__(roots: List[str])`**  
  • Stores `_roots`  
  • Calls `_parse_base_dir()` to scan any `todo.md` for a YAML front-matter `base:` directive  
  • Calls `_load_all()` to parse tasks  
  • Records initial mtimes of each `todo.md`  
  • Spawns background `_watch_loop()` thread.

### Task Discovery
- **`_find_files()`**  
  Recursively finds `todo.md` under each root.

- **`_parse_base_dir()`**  
  Looks for `--- … ---` blocks at top of any `todo.md`, scans inside lines for `base: <path>` and returns it.

- **`_load_all()`**  
  Reads each `todo.md` into lines, scans for task lines matching `- [ ]`, `- [~]`, `- [x]` with regex.  
  For each task:  
  - Captures bullet, status char, description  
  - Scans indented sub-lines for `include:`, `in:`, and `focus:` entries  
  - Optionally captures a subsequent fenced ```knowledge``` block (freeform context)  
  - Appends a dict to `_tasks`.

### Auto-Reload & Watch
- **`_watch_loop()`**  
  Every second, compares mtimes of all `todo.md`.  
  If a file changed externally (not by its own writes), logs and calls `run_next_task()`.

### Processing Tasks
- **`run_next_task(svc)`**  
  Reloads tasks, selects first with status “To Do”, calls `_process_one()`.

- **`_start_task(task, file_lines_map)`** / **`_complete_task(...)`**  
  Updates the markdown line from `[ ]→[~]→[x]`, inserts or updates a summary line with timestamp and token stats, writes back to disk.

- **`_process_one(task, svc, file_lines_map)`**  
  1. Gather knowledge: `include` pattern → `svc.include()`; count tokens  
  2. Read local `in:` file if specified → content + count tokens  
  3. Stamp start in `todo.md`  
  4. Build prompt:  
     - Optional raw input section  
     - Optional included knowledge  
     - Optional fenced knowledge block  
     - Final `ask: <desc>`  
  5. **NEW**: Before writing to focus file, read its old contents, compute a unified diff (`difflib.unified_diff`), and write that diff to `FOCUSNAME-YYYYMMDD-HHMMSS.diff` beside the file. Log the diff path.  
  6. Back up old focus in `backup_folder` (timestamped) if configured.  
  7. Call `svc.call_mcp("UPDATE_FILE", {...})` to overwrite focus file.  
  8. Stamp completion in `todo.md`.

---

## 4. MCP Server Handler (mcphandler.py)

### Threaded TCP + HTTP
- **`run_robodogmcp(host,port,token,folders,svc)`**  
  Configures globals (`TOKEN`, `SERVICE`, `ROOTS`), starts a `ThreadedTCPServer` on a daemon thread.

- **`MCPHandler.handle()`**  
  Reads one line from the socket:  
  - If it looks like HTTP (GET/POST/OPTIONS + `HTTP/`), routes to `_handle_http()`.  
  - Otherwise treats it as raw MCP: splits op/payload, calls `_dispatch()`, writes JSON line.

- **`_handle_http(first_line)`**  
  Parses request line and headers, supports CORS preflight (OPTIONS), enforces `Authorization: Bearer <token>`, reads JSON body, dispatches op, returns HTTP/JSON response.

### Dispatching Operations
- **File service ops**:  
  `LIST_FILES`, `GET_ALL_CONTENTS`, `READ_FILE`, `UPDATE_FILE`, `CREATE_FILE`, `DELETE_FILE`, `APPEND_FILE`, `CREATE_DIR`, `DELETE_DIR`, `RENAME`/`MOVE`, `COPY_FILE`, `SEARCH`, `CHECKSUM`.

- **Todo**:  
  `TODO` calls `SERVICE.todo.run_next_task(SERVICE)`.

- **Include/Ask**:  
  `INCLUDE` returns knowledge (and optional immediate answer).  
  `ASK` returns LLM response.

- **Model/Key**:  
  `LIST_MODELS`, `SET_MODEL`, `SET_KEY`, `GET_KEY`.

- **Stashes**:  
  `STASH`, `POP`, `LIST_STASHES`, `CLEAR`.

- **Snapshots**:  
  `IMPORT_FILES`, `EXPORT_SNAPSHOT`.

- **Params**:  
  `SET_PARAM`.

- **Web & Automation**:  
  `CURL`, `PLAY`.

- **Shutdown**:  
  `QUIT` / `EXIT`.

### Concurrency & Reuse
- **`ThreadedTCPServer`** (mixes in `ThreadingMixIn`): allows concurrent MCP clients.  
- `allow_reuse_address` enables fast restarts.

---

By following these feature descriptions and mapping each bullet to its implementation outline, you can reconstruct all four modules—**cli.py**, **service.py**, **todo.py**, and **mcphandler.py**—and reproduce the full RobodogCLI application with zero external dependencies beyond those listed in `setup.py`.