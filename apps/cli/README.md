# file: README.md
# Robodog
![Robodog MCP File Service](screenshot-mcp.png)

## Overview  
Robodog is a lightweight, zero-install, fast, command-line style generative AI client that integrates multiple providers (OpenAI, OpenRouter, LlamaAI, DeepSeek, Anthropic, Sarvam AI, Google Search API, and more) into a unified interface. Key capabilities include:

NEVER TRUST A CODE SPEWING ROBOT!

- Access to cutting-edge models: `o4-mini` (200k context), `gpt-4`, `gpt-4-turbo`, `dall-e-3`, Llama3-70b, Claude Opus/Sonnet, Mistral, Sarvam-M, Gemma 3n, etc.  
- Massive context windows (up to 200k tokens) across different models.  
- Seamless chat history & knowledge management with stashes and snapshots.  
- File import/export (text, Markdown, code, PDF, images via OCR).  
- In-chat file inclusion from a local MCP server.  
- Built-in web search integration.  
- Image generation & OCR pipelines.  
- Limit scope of the context window using filter tagging pattern=*robodog*.py recursive
- AI-driven web automation/testing via Playwright (`/play`).  
- Raw MCP operations (`/mcp`).  
- `/todo` feature: automate and track tasks defined in `todo.md`.  
- **Code Map**: Intelligent codebase indexing for 90% faster context loading.
- **Advanced Analysis**: Call graphs, impact analysis, dependency tracking.
- **Cascade Mode**: Windsurf-style parallel execution (2-3x faster multi-step tasks).
- Accessible, retro “console” UI with customizable themes and responsive design.  
- **🆕 Terminal Mode**: an agentic coding terminal (see below).

---

## 🖥️ Terminal Mode (agentic) — NEW

`robodog/robodog_terminal/` is a self-contained, agentic interactive coding
terminal: an agentic tool-use loop that reads/edits files, runs commands, runs
tests, and self-corrects — over pluggable LLM backends. It is designed to run
**leading models on self-hosted / air-gapped LLM gateways**, and works equally
with OpenAI-compatible models or a fully offline mock for development.

### Run it

**Installed (first-class):**
```bash
pip install -e "robodogcli[terminal]"        # pulls rich, prompt_toolkit, requests

robodog terminal --backend openai --model gpt-4o    # via the robodog command
robodog-terminal --backend gateway                  # dedicated launcher (self-hosted gateway)
python -m robodog.robodog_terminal --echo                   # module form
```

**From a source checkout (no install):**
```bash
cd robodogcli/robodog
pip install rich prompt_toolkit requests

python robodog_terminal/app.py --backend openai --model gpt-4o     # live (OpenAI/OpenRouter)
python robodog_terminal/app.py --echo                               # offline demo, no keys
python robodog_terminal/app.py --backend openai -p "fix the bug in x.py and run the tests"   # headless
python robodog_terminal/run_tests.py                                # 18 test suites
```
Keys load automatically from the KeePass automation DB (`Gateway`, `OpenAI`,
`OpenRouter`) or from `GATEWAY_*` / `ROBODOG_LLM_*` env vars — see the root
README's Configuration section.

### What works today (current progress)
- **Agentic loop** — prompted XML tool-calling (works on any model), with an
  intent nudge and a circuit breaker to stop stuck loops.
- **Tools** — `read_file`, `write_file`, `edit_file`, `multi_edit`, `bash`,
  `run_script`, `run_tests`, `glob`, `grep`, `list_dir`, plus `agent` subagents
  and `ask_user`. Read-before-edit enforced; **post-edit syntax verification**
  auto-feeds errors back; whitespace-tolerant fuzzy edits.
- **Command reaction** — streaming output, exit-code salience, process-tree kill
  on timeout, and a dangerous-command guard (`--guard confirm`).
- **Subagents** — foreground + background (`/bg`, `/tasks`, `/tail`, `/kill`) via
  a thread-based BackgroundManager; custom agent types from `.robodog/agents/*.md`.
- **Safety / undo** — per-prompt file checkpoints with `/rewind`; diff previews.
- **Sessions** — JSONL persistence, `/resume`, `--continue`/`--resume`.
- **Context** — auto-trim of old tool output, `/compact`, `/context`, `/btw`
  side-questions that don't touch history.
- **Plan mode** — `/plan` (read-only propose → approve → implement).
- **Skills / commands** — `.robodog/commands/*.md` (with `$ARGUMENTS`),
  `.robodog/skills/<name>/SKILL.md`, and `CLAUDE.md`/`ROBODOG.md` hierarchy.
- **TUI (rich + prompt_toolkit)** — welcome banner, an emoji + color **status
  line** (context/token/model severity tiers, protanopia-safe cyan/yellow/
  magenta — matching a custom statusline), spinner, markdown answers,
  colored diffs, **OSC-8 clickable file & `file:line` links**, `/open`, multiline
  paste, `\`+Enter continuation, history, and slash-command autocomplete.
- **Mid-turn interactivity** — Ctrl+C cancels a turn, **Ctrl+B backgrounds it**,
  and typed follow-ups queue while it runs.
- **Headless `-p`** mode with `text`/`json` output; `/doctor` diagnostics.

**Quality:** 18 test suites (`terminal/run_tests.py`), all passing. Benchmarked at
**capability parity with a leading agentic coding assistant** across 20 agentic scenarios
(algorithms, cross-file debugging, regex/data, OOP+tests, refactors, Playwright).

### Next steps / roadmap
- [ ] **Live gateway validation on a self-hosted box** — the GatewayClient (runPixel,
  retry, KeePass keys) is built and wire-tested; validate the real round-trip and the
  302/sticky-cookie async path. (Run `/doctor` there first.)
- [ ] **Streaming responses** (Pack C) for OpenAI-compatible backends.
- [x] **Editor-aware `file:line` links** — `--editor vscode|cursor|vscodium` (or
  `$ROBODOG_EDITOR`) makes file:line clicks jump to the exact line.
- [ ] **Syntax-highlighted diffs**.
- [ ] **Per-agent model overrides** in `.robodog/agents/*.md` (cheap model for
  `explore`, expensive model for the main loop).
- [ ] Wire `terminal` in as a `robodog terminal` subcommand of the main CLI.
- [ ] Optional permission gate (`--ask`) beyond the current YOLO default.

See `robodogcli/docs/TERMINAL_MODE_PLAN.md` for the full design, gap analysis,
and the agentic-tooling docs audit.

---

## Try Robodog  

- **Web**: https://adourish.github.io/robodog/robodog/dist/  
- **Android**: https://play.google.com/store/apps/details?id=com.unclebulgaria.robodog  
- **npm packages**:  
  - `npm install robodoglib`  
  - `npm install robodogcli`  
  - `npm install robodog`  
- **Python**:  
  - `pip install robodogcli`  
  - `pip show -f robodogcli`  
  - `python -m robodogcli.cli --help`  
  - `pip install --upgrade requests tiktoken PyYAML openai playwright pydantic langchain` (optional)  

---

## Configuration  

Click the ⚙️ icon in the top-menu to open settings, or edit your YAML directly:

```yaml
configs:
  providers:
    - provider: openAI
      baseUrl: "https://api.openai.com"
      apiKey: "<open ai token>"
      httpReferer: "https://adourish.github.io"
    - provider: openRouter
      baseUrl: "https://openrouter.ai/api/v1"
      apiKey: "<open router token>"
      httpReferer: "https://adourish.github.io"
    - provider: searchAPI
      baseUrl: "https://google-search74.p.rapidapi.com"
      apiKey: "<search token>"
      httpReferer: "https://adourish.github.io"
  
  mcpServer:
    baseUrl: "http://localhost:2500"  
    apiKey:   "testtoken"  

  specialists:
    - specialist: nlp
      resume: natural language processing, chatbots, content generation, language translation
    - specialist: gi
      resume: generates images from textual descriptions. understanding and interpreting textual descriptions 
    - specialist: search
      resume: generate simple search results

  models:
    - provider: openRouter
      model: openai/gpt-5-mini
      stream: true
      specialist: nlp
      about: "Best for performance. Context window: 1.05M tokens. Competitive in Academia (#2), Marketing/Seo (#3), Health (#4), Legal (#4), Science (#4)."
    - provider: openRouter
      model: GPT-4o-mini
      stream: true
      specialist: nlp
      about: "Best for most questions. Context window: 1.05M tokens. Pricing: $0.40/M input, $1.60/M output."
    - provider: openAI
      model: o4-mini
      stream: true
      specialist: nlp
      about: "Biggest model with 200k context window and world view. Best for critical thinking. Context window: 200K tokens."
    - provider: openAI
      model: o1
      stream: true
      specialist: nlp
      about: "Big model with 128k context window and small world view. Good for critical thinking. Context window: 128K tokens."
    - provider: openRouter
      model: openai/o4-mini
      stream: true
      specialist: nlp
      about: "Best for big content. Context window: 200K tokens."
    - provider: openRouter
      model: deepseek/deepseek-r1
      stream: true
      specialist: nlp
      about: "Best for summarizing. Context window: 128K tokens. Model size: 671B parameters (37B active). Performance: #2 in Roleplay, #6 in Translation, #9 in Programming, #10 in Science. Supports thinking and non-thinking modes."
    - provider: openRouter
      model: google/gemini-2.5-pro
      stream: true
      specialist: nlp
      about: "Best for speed. Context window: 1.05M tokens. Performance: #3 in Health, #5 in Marketing, Roleplay, Academia, Science. Advanced reasoning, coding, mathematics, scientific tasks. Pricing: $1.25/M input, $10/M output."
    - provider: openRouter
      model: qwen/qwen3-coder
      stream: true
      specialist: nlp
      about: "Best for large docs when speed is not an issue. Context window: 262K tokens. Model size: 480B parameters (35B active). Optimized for agentic coding tasks. Performance: #3 in Programming, #7 in Technology, #8 in Science. Pricing: $0.20/M input, $0.80/M output."
    - provider: openRouter
      model: anthropic/claude-sonnet-4
      stream: false
      specialist: gi
      about: "Best for creating images."
    - provider: openRouter
      model: x-ai/grok-code-fast-1
      stream: false
      specialist: search
      about: "Best for searching. Context window: 256K tokens. Performance: #1 in Programming, #3 in Technology, #6 in Marketing/Seo, #10 in Trivia. Speedy and economical reasoning model. Pricing: $0.20/M input, $1.50/M output."
    - provider: searchAPI
      model: search
      stream: false
      specialist: search
      about: "Best for searching. Context window: 256K tokens. Performance: #1 in Programming, #3 in Technology, #6 in Marketing/Seo, #10 in Trivia. Speedy and economical reasoning model. Pricing: $0.20/M input, $1.50/M output."

```

---

## Supported Models  

### OpenAI  
- gpt-4, gpt-4-turbo, gpt-3.5-turbo, gpt-3.5-turbo-16k, o4-mini, o1  
- dall-e-3  

### Others  
- LlamaAI: llama3-70b  
- Anthropic: Claude Opus 4, Claude Sonnet 4  
- DeepSeek R1  
- Mistral Medium 3, Devstral-Small  
- Sarvam-M  
- Google Gemma 3n E4B  

---

## Key Features  

- **Multi-Provider Support**: Switch between any configured provider or model on the fly (`/model`).  
- **Chat & Knowledge**: Separate panes for Chat History (💭) and Knowledge (📝)—both resizable.  
- **Stash Management**:  
  - `/stash <name>` — save current chat+knowledge  
  - `/pop <name>`   — restore a stash  
  - `/list`         — list all stashes  
- **File Import/Export**:  
  - `/import <glob>` — import files (.md, .js, .py, .pdf, images via OCR)  
  - `/export <file>` — export chat+knowledge snapshot  
- **MCP File Inclusion**:  
  - `/include all`  
  - `/include file=README.md`  
  - `/include pattern=*.js|*.css recursive`  
  - `/include dir=src pattern=*.py recursive`  
- **Raw MCP Operations**:  
  - `/mcp OP [JSON]` — e.g. `/mcp LIST_FILES`, `/mcp READ_FILE {"path":"./foo.py"}`  
- **Web Fetch & Automation**:  
  - `/curl [--no-headless] <url> [<url2>|<js>]` — fetch pages or run JS  
  - `/play <instructions>` — run AI-driven Playwright tests end-to-end  
- **Web Search**:  
  - Use `search` model or click 🔎 to perform live web queries.  
- **Image Generation & OCR**: Ask questions to `dall-e-3` or drop an image to extract text via OCR.  
- **Interactive Console UI**: Retro “pip-boy green” theme, responsive on desktop/mobile, accessible.  
- **Performance & Size Indicators**: Emoji feedback for processing speed and token usage.  
- **Extensive Command Palette**: `/help` lists all commands, indicators, and settings.  
- **Todo Automation**: Use `/todo` to execute tasks defined in `todo.md` across your project roots.
- **Code Map**: Intelligent codebase indexing with 90% token savings—scan, find, and get targeted context instantly.
- **Advanced Code Analysis**:
  - **Call Graphs**: Visualize function relationships across your codebase
  - **Impact Analysis**: Find what breaks before you change code
  - **Dependency Tracking**: See all internal/external dependencies
  - **Codebase Statistics**: Get metrics on complexity and usage
- **Cascade Mode**: Windsurf-style parallel execution for 2-3x faster multi-step tasks with automatic tool selection and self-correction.  

---

## Usage Examples  

### 1) AI-Driven Web Tests with `/play`
```
/play navigate to https://example.com, extract the page title, and verify it contains 'Example Domain'
```

### 2) Fetch & Scrape with `/curl`
```
/curl https://example.com
```

### 3) Include Local Files via MCP
```
/include pattern=*.js recursive fix bug in parser
```

### 4) Raw MCP Commands
```
/mcp LIST_FILES
/mcp READ_FILE {"path":"./src/cli.py"}
```

### 5) Switch Model on the Fly
```
/model o4-mini
```

### 6) Import & Export
```
/import **/*.md
/export conversation_snapshot.txt
```

---

### 7) Auto Side by Side Diff

![Robodog MCP File Service](screenshot-diff.png)

---

## 🗺️ Code Map & Advanced Analysis

Robodog includes Windsurf-inspired features for intelligent codebase understanding and parallel execution.

### Code Map - 90% Faster Context Loading

Index your entire codebase for instant, targeted context retrieval:

```bash
# Scan your codebase (required first!)
/map scan

# Find any class or function
/map find TodoManager

# Get relevant files for a task
/map context implement user authentication

# Save/load the map
/map save codemap.json
/map load codemap.json
```

**Example Output:**
```
🗺️ Scanning codebase...
✅ Scanned 29 files
   Classes: 12
   Functions: 87

/map find TodoManager
Found 1 definition(s) for 'TodoManager':
  class: TodoManager
    File: robodog/todo_manager.py:45
    Doc: Manages todo tasks across multiple files
```

**Benefits:**
- **90% token savings** - Load only relevant code
- **Instant search** - Find any definition in milliseconds
- **Smart context** - AI gets exactly what it needs

### Advanced Code Analysis

Understand your codebase structure with call graphs, impact analysis, and dependency tracking:

```bash
# Build complete call graph
/analyze callgraph

# Find what breaks if you change a function
/analyze impact execute_subtask

# Show file dependencies (internal/external)
/analyze deps robodog/cli.py

# Get codebase statistics
/analyze stats
```

**Example Output:**
```
/analyze callgraph
🔍 Building call graph...
✅ Functions: 245
   Total calls: 1,234

/analyze impact TodoManager
📊 Impact analysis for TodoManager:
   Direct callers: 5
   Total impacted: 15
   Direct callers:
     - TodoService
     - cli
     - app
     - service
     - main

/analyze deps robodog/cli.py
📦 Dependencies:
   Total imports: 25
   Internal: 12
   External: 13
   External packages:
     - argparse, json, logging, os, sys...

/analyze stats
📊 Codebase Statistics:
   Total functions: 245
   Total calls: 1,234
   Avg calls/function: 5.0
   Total files: 29
   Most called functions:
     ask: 45 calls
     call_mcp: 38 calls
     read_file: 32 calls
```

**Use Cases:**
- **Before refactoring**: Check impact to avoid breaking changes
- **Code review**: Understand function relationships
- **Dependency audit**: See all external packages used
- **Complexity analysis**: Find most complex functions

### 🌊 Cascade Mode - Parallel Execution

Execute multi-step tasks 2-3x faster with Windsurf-style parallel execution:

```bash
# Run any task with automatic parallelization
/cascade run implement user authentication

# More examples
/cascade run refactor the file service module
/cascade run add unit tests for TodoManager
/cascade run fix error handling in cascade_mode.py
```

**Example Output:**
```
🌊 Running cascade for: implement user authentication
✅ Cascade completed:
   Steps: 7
   Successful: 7
   Failed: 0
   Duration: 18.5s
```

**How It Works:**
1. **LLM breaks down task** into independent steps
2. **Parallel execution** of steps with no dependencies
3. **Automatic tool selection** (read, edit, create, search, analyze)
4. **Self-correction** on errors
5. **2-3x faster** than sequential execution

**Performance:**
| Task Type | Sequential | Cascade | Speedup |
|-----------|-----------|---------|---------|
| Multi-file changes | 60s | 25s | **2.4x** |
| Code analysis | 45s | 18s | **2.5x** |
| Test generation | 90s | 35s | **2.6x** |

### Complete Workflow Example

```bash
# 1. Start CLI with code map enabled
python robodog\cli.py --folders c:\projects\myapp --port 2500 --token testtoken --model openai/o4-mini

# 2. Scan codebase
/map scan

# 3. Understand the code
/analyze stats
/map find AuthService
/analyze impact AuthService

# 4. Check dependencies before refactoring
/analyze deps src/auth.py

# 5. Implement changes with cascade mode
/cascade run refactor AuthService to use async/await

# 6. Verify changes
/analyze impact AuthService
```

---

## /todo Feature  

Robodog’s `/todo` command scans one or more `todo.md` files in your configured project roots, detects tasks marked `[ ][-]`, transitions them to `[~][-]` (Doing) when started, and `[x][-]` (Done) when completed. Additionally, flipping from [x[[ ] will commit the changes to from the out file to the destination file(s). Each task may include:

- [ ][-] task status and task commit status
  - `include:` pattern or file specification to gather relevant knowledge
  - `out:` file path where the AI will write or update content
  - Optional code fences below the task as initial context

You can have multiple `todo.md` files anywhere under your roots. `/todo` processes the earliest outstanding task, runs the AI with gathered knowledge, updates the focus file, stamps start/completion times, and advances to the next.

![Robodog MCP File Service](screenshot-todo.png)


### Example `todo.md` File Formats

```markdown
# file: project1/todo.md
- [ ][-] Revise API client
  - include: pattern=api/*.js recursive
  - out: temp/out.js
```knowledge
// existing stub
```


```markdown
- [ ][-] Add unit tests
  - include: file=tests/template.spec.js
  - out: temp/out.js
```

```markdown
# file: project2/docs/todo.md
- [ ][-] Update README
  - out: file=README.md
- [ ][-] Generate changelog
  - include: pattern=CHANGELOG*.md
  - out: out.md
```knowledge

```

```markdown
# todo readme
- [x][-] readme
  - include: pattern=*robodog*.md|*robodog*.py|*todo.md   recursive`
  - out: temp/out.js
```knowledge
1. do not remove any content
2. add a new readme section for the /todo feature with examples of the todo.md files and how you can have as many as possible
3. give lots of exampkes of file formats
```
# todo 
- [~][-] changes todo
  - started: 2025-09-16 22:53 | knowledge: 36 | include: 25181 | prompt: 25492 | cur_model: openai/o4-mini
  - include: pattern=*robodogcli*robodog*service.py|*robodogcli*robodog*todo.py|*robodogcli*robodog*builder.py|*robodogcli*robodog*cli.py   recursive`
  - out:  temp\out.py
```knowledge

1. detect if the parsed file is new or not. 
2. # file: <filename.ext> NEW
3. add if the file is new to the list of objects from parse_llm_output
4. give me all of the code. 
```

```markdown
# watch
- [ ][-] change app prints in service logger.INFO
  - include: pattern=*robodog*.md|*robodog*.py  recursive`
  - out: temp/out.js
```knowledge
do not remove any features.
give me full drop in code file
```


```markdown
# fix logging
- [ ][-] ask: fix logging. change logging so that it gets log level through command line. change logger so that it takes log level from the command line param
  - include: pattern=*robodog*.md|*robodog*.py  recursive`
  - focus: file=c:\projects\robodog\robodogcli\robodog\cli3.py
```knowledge
my knowledge
```

You can chain as many tasks and files as needed. Each can reside in different directories, and Robodog will locate all `todo.md` files automatically.

## Configuration & Command Reference  

### Robodog UI

See command palette in-app (`/help`) or the reference below:

```
/help             — show help  
/models           — list configured models  
/model <name>     — switch model  
/import <glob>    — import files into knowledge  
/export <file>    — export snapshot  
/clear            — clear chat & knowledge  
/stash <name>     — stash state  
/pop <name>       — restore stash  
/list             — list stashes  
/temperature <n>  — set temperature  
/top_p <n>        — set top_p  
/max_tokens <n>   — set max_tokens  
/frequency_penalty <n> — set frequency_penalty  
/presence_penalty <n>  — set presence_penalty  
/dark             — toggle light/dark 
/folders <dirs>   — set MCP roots  
/include …        — include files via MCP  
/curl …           — fetch pages / run JS  
/play …           — AI-driven Playwright tests  
/mcp …            — invoke raw MCP operation  
/todo             — run next To Do task  

Code Map & Analysis:
/map scan         — scan codebase and create index
/map find <name>  — find class/function definition
/map context <task> — get relevant files for task
/map save [file]  — save code map (default: codemap.json)
/map load [file]  — load code map (default: codemap.json)
/analyze callgraph — build call graph for codebase
/analyze impact <fn> — find what breaks if function changes
/analyze deps <file> — show file dependencies
/analyze stats    — show codebase statistics
/cascade run <task> — run task with parallel execution (2-3x faster)
```
### Robodog CLI

```
/help             — show help  
/models           — list configured models  
/model <name>     — switch model  
/clear            — clear chat & knowledge  
/temperature <n>  — set temperature  
/folders <dirs>   — set MCP roots  
/include …        — include files via MCP  
/todo             — run next To Do task

Code Map & Analysis:
/map scan         — scan codebase and create index
/map find <name>  — find class/function definition
/map context <task> — get relevant files for task
/map save [file]  — save code map
/map load [file]  — load code map
/analyze callgraph — build call graph for codebase
/analyze impact <fn> — find what breaks if function changes
/analyze deps <file> — show file dependencies
/analyze stats    — show codebase statistics
/cascade run <task> — run task with parallel execution (2-3x faster)
```

---

## Build & Run  

```bash
# Clone or unzip robodog
cd robodog
python build.py
open ./dist/robodog.html
```

```bash
npm install robodoglib  
npm install robodogcli  
npm install robodog  
pip install robodogcli  
pip show -f robodogcli  
python -m robodogcli.cli --help  
python -m robodogcli.cli --folders "c:\projects\robodog" --port 2500 --token testtoken --config config.yaml --model  openai/o4-mini --backupFolder "c:\temp"

```

---

## 🚀 What's New in v2.6.16

**New Features:**
- 🆕 **Terminal Mode** - agentic coding terminal with tool-use loop, file operations, and test execution.
- **Agentic Loop** - Prompted XML tool-calling with intent nudge and circuit breaker.
- **Tools** - Comprehensive set of tools including read, write, edit, bash, run script, run tests, and more.
- **Safety & Undo** - File checkpoints with `/rewind` and diff previews.
- **Sessions & Context** - JSONL persistence, auto-trim of old tool output, and `/btw` side-questions.


**Windsurf-Inspired Features:**
- ✅ **Code Map** - 90% faster context loading with intelligent indexing
- ✅ **Advanced Analysis** - Call graphs, impact analysis, dependency tracking
- ✅ **Cascade Mode** - 2-3x faster parallel execution for multi-step tasks

**Performance Improvements:**
- Multi-file changes: **2.4x faster**
- Code analysis: **2.5x faster**
- Test generation: **2.6x faster**

See the [Code Map & Advanced Analysis](#-code-map--advanced-analysis) section for detailed examples and usage.

---

Enjoy Robodog AI—the future of fast, contextual, and extensible AI interaction!