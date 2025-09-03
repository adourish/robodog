# file: README.md
# Robodog Code
![Robodog MCP File Service](screenshot-mcp.png)

## Overview  
Robodog Code is a lightweight, zero-install, fast, command-line style generative AI client that integrates multiple providers (OpenAI, OpenRouter, LlamaAI, DeepSeek, Anthropic, Sarvam AI, Google Search API, and more) into a unified interface. Key capabilities include:

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
- Accessible, retro “console” UI with customizable themes and responsive design.  

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
      apiKey: "<YOUR_OPENAI_KEY>"
    - provider: openRouter
      baseUrl: "https://openrouter.ai/api/v1"
      apiKey: "<YOUR_ROUTER_KEY>"
    - provider: searchAPI
      baseUrl: "https://google-search74.p.rapidapi.com"
      apiKey: "<YOUR_RAPIDAPI_KEY>"

  specialists:
    - specialist: nlp
      resume: natural language processing, content generation
    - specialist: gi
      resume: image generation from text
    - specialist: search
      resume: web search integration

  mcpServer:
    baseUrl: "http://localhost:2500"
    apiKey: "testtoken"

  models:
    - provider: openAI
      model: gpt-4
      stream: true
      specialist: nlp
      about: best for reasoning
    - provider: openAI
      model: o4-mini
      stream: true
      specialist: nlp
      about: 200k token context, advanced reasoning
    - provider: openAI
      model: dall-e-3
      stream: false
      specialist: gi
      about: image creation
    - provider: searchAPI
      model: search
      stream: false
      specialist: search
      about: web search results
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

## /todo Feature  

Robodog’s `/todo` command scans one or more `todo.md` files in your configured project roots, detects tasks marked `[ ]`, transitions them to `[~]` (Doing) when started, and `[x]` (Done) when completed. Each task may include:

- `include:` pattern or file specification to gather relevant knowledge
- `focus:` file path where the AI will write or update content
- Optional code fences below the task as initial context

You can have multiple `todo.md` files anywhere under your roots. `/todo` processes the earliest outstanding task, runs the AI with gathered knowledge, updates the focus file, stamps start/completion times, and advances to the next.

![Robodog MCP File Service](screenshot-todo.png)

### 1. Front-Matter Base Directory
- **`base:` directive**  
  At the top of any `todo.md`, you can define a YAML front-matter block:
  
  ```yaml
  ---
  base: c:\projects\robodog
  ---
  ```
  
  `todo.py` will scan for the first `base:` entry and use it as the primary root for resolving file fragments.

### 2. Task Parsing
- Detects tasks matching:
  
    - `[ ]` To Do  
    - `[~]` Doing  
    - `[x]` Done

- Supports indented subtasks with keys:
  
    - `include:`  — pull in knowledge by pattern  
    - `in:`       — read input from files  
    - `out:`      — write output to files  
    - `focus:`    — alias for `out:`  
    - `recursive` — flag for recursive pattern matching

### 3. Path Resolution
When you specify a fragment (e.g. `mcphandler.py` or `robodogcli\robodog\mcphandler.py`), `todo.py` logs and applies one of four resolution “branches”:

1. **Bare filename under `base:`**  
   If `base` is set and the fragment contains no path separators, it’s treated as `base/<filename>`.

2. **Relative path under `base:`**  
   If the fragment includes separators and `base` is set, it becomes `base/<fragment>`, creating parent directories as needed.

3. **Search existing**  
   Looks for an existing file by trying `base` (if any), then each configured root in turn. Returns the first match.

4. **Create under first root**  
   If not found, it creates the path under the first root in your roots list, ensuring parent directories exist.

### Example `todo.md` File Formats

```markdown
# file: project1/todo.md
- [ ] Revise API client
  - include: pattern=api/*.js recursive
  - in: api/client.js
  - out: api/client-v2.js
```knowledge
// existing stub
```


```markdown
- [ ] Add unit tests
  - include: file=tests/template.spec.js
  - out: tests/api.client.spec.js
  - in: tests/api.client.spec.js
```

```markdown
# file: project2/docs/todo.md
- [ ] Update README
  - focus: file=README.md
- [ ] Generate changelog
  - include: pattern=CHANGELOG*.md
  - out: CHANGELOG.md
```knowledge

```

```markdown
# todo readme
- [x] readme
  - include: pattern=*robodog*.md|*robodog*.py|*todo.md   recursive`
  - out: c:\projects\robodog\robodogcli\temp\service-v2.py
  - in: c:\projects\robodog\robodogcli\temp\service.py
```knowledge
1. do not remove any content
2. add a new readme section for the /todo feature with examples of the todo.md files and how you can have as many as possible
3. give lots of exampkes of file formats
```


```markdown
# watch
- [ ] change app prints in service logger.INFO
  - include: pattern=*robodog*.md|*robodog*.py  recursive`
  - out:   c:\projects\robodog\robodogcli\robodog\service.py
  - out: c:\projects\robodog\robodogcli\robodog\service.py
```knowledge
do not remove any features.
give me full drop in code file
```


```markdown
# fix logging
- [ ] ask: fix logging. change logging so that it gets log level through command line. change logger so that it takes log level from the command line param
  - include: pattern=*robodog*.md|*robodog*.py  recursive`
  - in: c:\projects\robodog\robodogcli\robodog\cli.py
  - out: c:\projects\robodog\robodogcli\robodog\cli-v3.py
```knowledge
my knowledge
```

You can chain as many tasks and files as needed. Each can reside in different directories, and Robodog will locate all `todo.md` files automatically.

## Configuration & Command Reference  

See command palette in-app (`/help`) or the reference below:

```
/help             — show help  
/models           — list configured models  
/model <name>     — switch model  
/key <prov> <key> — set API key  
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
/stream           — enable streaming mode  
/rest             — disable streaming mode  
/folders <dirs>   — set MCP roots  
/include …        — include files via MCP  
/curl …           — fetch pages / run JS  
/play …           — AI-driven Playwright tests  
/mcp …            — invoke raw MCP operation  
/todo             — run next To Do task  
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
python -m playwright install
```

---

Enjoy Robodog AI—the future of fast, contextual, and extensible AI interaction!