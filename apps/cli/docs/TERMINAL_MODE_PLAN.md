# Robodog Terminal Mode — Build Plan

A agentic interactive terminal for robodog: welcome box + bottom status line,
slash commands, a real agentic **tool-use loop**, and the ability to **edit files** and
**run shell commands**.

## Decisions (locked)

- **Fresh tool-use loop** — model emits `tool_calls` → we execute → feed results back → repeat.
  We do NOT extend the todo-oriented `agent_loop.py` (that stays for `/todo`).
- **Auto-approve (YOLO)** — edits and shell commands run without prompting. Keep a
  `--ask` flag / config toggle so a permission gate can be turned on later.
- **Configurable provider** — thin `LLMClient` interface, two backends
  (OpenAI-compatible + Anthropic-native), chosen by config.

## Provider: FDA ELSA endpoint (RESOLVED — it's SEMOSS, not OpenAI/Anthropic)

Confirmed from `C:\projects\fda-serio\temp\ELSA API Guide.pdf` (FDA, updated 2025-09-30)
and the existing `fda-serio` tooling. ELSA exposes **Anthropic Claude Sonnet** but through
a **custom SEMOSS "Monolith" `runPixel` API — NOT** an OpenAI- or Anthropic-native shape:

- **Endpoint:** `POST https://<host>/Monolith/api/engine/runPixel`
  - Dev: `https://elsa-dev.preprod.fda.gov/...`  · Prod: `https://elsa.fda.gov/...`
- **Auth:** HTTP **Basic** — Username = access key, Password = secret key
  (KeePass entry `SEMOSS-Elsa-Dev`; keys never printed/committed).
- **Content-Type:** `application/x-www-form-urlencoded`
- **Body:** a single URL-encoded `expression` field wrapping a pixel call:
  `LLM(engine="<engine_id>", command="<encode>PROMPT</encode>", context="<system prompt>", useHistory=<bool>, paramValues=[{"max_completion_tokens":N,"temperature":T}])`
  (plus `tz=America/New_York`).
- **Engine IDs:** Dev `7bd59c7b-92d6-4bc9-91eb-4d17f74b5b3f` (Sonnet 4.0); Pre-Prod / Prod differ.
- **Response:** JSON — the model text is at `pixelReturn[0].output.response`; token counts
  at `output.numberOfTokensIn{Prompt,Response}`; session id at `insightID` / `output.roomId`.

### The consequence for the agentic loop
**ELSA has NO native tool-use.** There is no `tools=[…]` param and no `tool_calls` in the
response — it's raw prompt-in / text-out. So the loop **cannot** rely on provider-native
function-calling. Instead use **prompted (text-based) tool calling**, which Claude Sonnet
does very well:

1. Put the tool catalog + output contract in the `context` (system prompt): the model must
   emit tool calls as structured blocks (XML tags, e.g. `<tool name="bash"><arg .../></tool>`
   — robust with Claude, and `parse_service.py` already does tag/block extraction).
2. Parse tool-call blocks out of `pixelReturn[0].output.response`.
3. Execute locally (read/write/edit/bash…), then feed results back as the next `command`.
4. Thread history via `useHistory=true` (server-side `roomId` session) **or** by
   re-sending the running transcript in `command`. Prefer explicit transcript threading for
   determinism; treat `useHistory` as an optimization to validate.

Notes / gotchas already known from `fda-serio`:
- Structured output needs a **schema-instructing `context` + a high `max_completion_tokens`
  (e.g. 8192)** — a low 2000 cap produced empty/prose responses.
- Some flows are **async with 302 redirects + sticky-session cookies** (submit in one
  session, poll/fetch in another). The synchronous `runPixel` above is fine for interactive
  turns; be aware the poller path exists.
- FDA recommends `ai-server-sdk` (PyPI) for batch/agentic invocation — evaluate vs. a thin
  direct client. A direct `requests` client (per the guide's Python sample) is simplest and
  has zero extra deps.

**Model-name note:** the guide lists "Claude Sonnet 4.0" (not 4.6) as the Dev/Prod engine —
what matters is the **engine ID**, not the label. Whatever they call it, you target it by
engine GUID.

---

## Reuse map (what already exists)

| Need | Existing component | Status |
|---|---|---|
| Read/write/backup files | `file_service.py` | reuse |
| Extract file blocks from text | `parse_service.py` | reuse (fallback path) |
| Side-by-side diffs | `diff_service.py` | reuse for edit preview |
| Glob / grep / symbol search | `code_map.py`, `advanced_analysis.py` | wrap as tools |
| Todo tracking | `todo_manager.py` | wrap as `todo_write` tool |
| LLM access (OpenAI-compat) | `service.ask()` / `service.client` | extend → `chat_with_tools()` |
| Slash-command REPL | `cli.py` | borrow dispatch, new UI |
| **Run shell commands** | — none — | **NEW: bash tool** |
| **Tool-use loop** | — none — | **NEW** |
| **TUI (box + status line)** | `simple_ui.py` (partial) | **NEW: prompt_toolkit + rich** |
| **Permission gate** | — none — | NEW (deferred; YOLO default) |

---

## Architecture — new `robodog/terminal/` package

```
terminal/
  __init__.py
  app.py          # entry: welcome box, main loop wiring, status line
  loop.py         # agentic conversation loop (messages[], tool dispatch, iterate)
  llm_client.py   # provider abstraction: OpenAICompatClient | AnthropicClient
  tools.py        # tool schemas + executors (read/write/edit/bash/glob/grep/todo)
  permissions.py  # gate (YOLO default now; ask-mode later)
  ui.py           # prompt_toolkit input + rich rendering (banner, diffs, spinner, status)
  commands.py     # slash commands (/help /clear /model /init /status /cost + robodog's)
```

### Core loop (`loop.py`) — prompted tool-calling (no native tool API)
```
system  = TOOL_CATALOG + OUTPUT_CONTRACT      # goes in ELSA `context`
history = [user_msg]
while iteration < MAX_ITER:
    prompt = render_transcript(history)        # or useHistory=true server session
    text   = llm.complete(prompt, context=system, max_tokens=8192)   # ELSA runPixel
    calls  = parse_tool_calls(text)            # extract <tool …> blocks from text
    if calls:
        for c in calls:
            result = tools.execute(c.name, c.args)     # YOLO: no prompt
            history.append(assistant(text)); history.append(tool_result(c.name, result))
        continue
    else:
        render(text); break                    # final answer (no tool blocks)
```
`parse_tool_calls` reuses `parse_service.py`'s tag/block extraction. Tool-call format is an
XML-tag convention (Claude-friendly), specified in `OUTPUT_CONTRACT`.

### Tools (`tools.py`) — schemas + executors
- `read_file(path, offset?, limit?)` → `file_service.read_file`
- `write_file(path, content)` → `file_service.write_file` (+ backup)
- `edit_file(path, old_string, new_string, replace_all?)` → read, string-replace, write; show diff via `diff_service`
- **`bash(command, cwd?, timeout?)`** → `subprocess.run` on PowerShell/bash, capture stdout+stderr+exit code (NEW)
- `glob(pattern)` / `grep(pattern, path?, glob?)` → `code_map` / filesystem
- `list_dir(path)`
- `todo_write(todos)` → `todo_manager`

### LLM client (`llm_client.py`)
- `class LLMClient(ABC): def complete(prompt, context="", max_tokens=8192, temperature=0.3) -> Completion`
  (`Completion` = text + token counts). Tool-calling is done in the loop via prompting, not here.
- **`ElsaClient`** (primary) — `POST /Monolith/api/engine/runPixel`, Basic auth, builds the
  `expression=LLM(engine=…, command="<encode>…</encode>", context=…, paramValues=[…])` body,
  URL-encodes it, parses `pixelReturn[0].output.response`. Keys from KeePass `SEMOSS-Elsa-Dev`;
  host/engine from config/env (never hard-coded). Optional `useHistory`/`roomId` session support.
- **`EchoClient`** (dev/offline) — scripted/mock backend so the loop, tools, and UI are testable
  **off the FDA network** without creds. Default when no ELSA config present.
- `OpenAICompatClient` — retained (reuses `service.client`) for robodog's existing OpenRouter models.
- Selected by a `protocol: elsa|openai|echo` field on the model/provider config.

### UI (`ui.py`)
- **Welcome box** (rich `Panel`): logo, model, cwd, tips — like a modern agentic terminal's banner.
- **Bottom status line** (prompt_toolkit `bottom_toolbar`): `model · cwd · tokens used · context %`.
- Streaming assistant text, tool-call lines, colored diffs, spinner during LLM calls.
- `/`-prefix command autocomplete.

---

## Phased next steps

**Phase 0 — DONE (this session):** endpoint shape confirmed (ELSA/SEMOSS runPixel, no native
tool API). No live-network spike needed to start — we build against the `LLMClient` abstraction
with `EchoClient` so everything is testable offline; `ElsaClient` gets validated on the FDA box.

**Phase 1 — Loop + tools (core):** `llm_client.py` (EchoClient + ElsaClient), `tools.py`
(incl. bash), `parse_tool_calls`, `loop.py`. Headless first (plain print), no fancy UI.
Prove with EchoClient: "create a file, run it, read output, fix it." Then swap in ElsaClient.

**Phase 2 — TUI:** `ui.py` — welcome box, bottom status line, streaming, diffs, spinner.
Add `prompt_toolkit` + `rich` to `requirements.txt`.

**Phase 3 — Slash commands:** `/help /clear /model /init /status /cost` + reuse
robodog's `/map /analyze /todo /include`.

**Phase 4 — Polish:** cancel (Esc/Ctrl-C mid-loop), token/cost tracking, `CLAUDE.md`
loading as system context, session persistence, optional permission gate (flip off YOLO).

## Dependencies to add
`prompt_toolkit`, `rich`, and (only if the FDA endpoint is Anthropic-native) `anthropic`.

## Entry point
`robodog terminal` (or `python -m robodog.terminal.app`) / `--mode terminal`.

---

# Gap Analysis & Prioritized Feature Map (2026-07-18)

Audit of Phase-1 build vs. leading agentic tools. Priorities:
**P0** = blocks live use on the FDA box · **P1** = core Claude-Code parity / robustness ·
**P2** = productivity parity · **P3** = nice-to-have / later.

## ✅ Already built (Phase 1, verified offline)
| Feature | Where |
|---|---|
| Agentic loop (prompted tool-calling) | `loop.py` |
| Tools: read/write/edit/bash/glob/grep/list_dir | `tools.py` |
| Tool-call XML parser | `toolcall.py` |
| ELSA wire client (runPixel, Basic auth) | `llm_client.py` |
| Offline mock backend + E2E selftest (6/6) | `EchoClient`, `selftest.py` |
| Welcome box, status line, tool-call trace | `ui.py` |
| Slash cmds: /help /model /status /clear /cwd /tools /exit | `app.py` |
| Tool-output truncation (30k clamp) | `tools.py` |
| Max-iterations loop guard | `loop.py` |

## P0 — blocks live use (do first)
| # | Feature | Gap today | Effort |
|---|---|---|---|
| 1 | **Live ELSA validation** | ElsaClient never hit the real endpoint; unit-tested wire format only | S (on FDA box) |
| 2 | **Retry w/ backoff + visible "Retrying attempt n/N" line** | Zero retry logic; one 5xx/timeout kills the turn (an agentic coding terminal shows `API error · Retrying… attempt 1/10`) | S |
| 3 | **KeePass key loading (SEMOSS-Elsa-Dev)** | Backend needs 4 env vars set by hand; fda-serio already has the KeePass pattern | S |
| 4 | **302/sticky-cookie session handling** | `requests.Session` follows redirects but we don't pin cookies across submit/poll like the fda-serio probe does | M |
| 5 | **Empty-response guard** | Known ELSA failure mode (low token cap → empty/prose); detect empty text and retry once with adjusted params | S |

## P1 — core parity & robustness
| # | Feature | Gap today | Effort |
|---|---|---|---|
| 6 | **Cancellation (Ctrl-C mid-loop)** | Ctrl-C during an LLM call/tool run kills the whole app, not the turn | S |
| 7 | **Spinner / "thinking…" indicator** | Silent dead air during each ELSA call (~12 s per the guide!) | S |
| 8 | **Markdown rendering of answers** | Plain `Text` — no headings/code blocks; rich has `Markdown` built in | S |
| 9 | **Diff preview on edit/write** | Edits are invisible; `diff_service.py` already renders side-by-side | M |
| 10 | **Backup before write** | Our `write_file`/`edit_file` clobber directly; `file_service` already has `backupFolder` machinery | S |
| 11 | **CLAUDE.md / ROBODOG.md loading** | No project-instructions injection into system context | S |
| 12 | **Context-window management (/compact + auto-trim)** | Transcript grows unboundedly; ELSA re-sends the full transcript every iteration | M |
| 13 | **Robust tool-block parsing edge cases** | Nested/code-fenced `<tool>` text in prose could false-positive; escape rules untested against real Sonnet output | M |

## P2 — productivity parity
| # | Feature | Gap today | Effort |
|---|---|---|---|
| 14 | **Sticky bottom status bar + autocomplete** | Status line is printed, not pinned; needs `prompt_toolkit` (not installed) | M |
| 15 | **@-file mentions** (`@src/foo.py` inlines the file) | Not parsed | S |
| 16 | **/init** — generate project CLAUDE.md via the agent | Missing | S |
| 17 | **Session persistence + /resume** | History lost on exit | M |
| 18 | **TodoWrite-style progress tool** | Agent can't surface a visible plan/checklist; `todo_manager` exists to wrap | M |
| 19 | **Real /model switching (dev/preprod/prod engine IDs)** | `/model` only changes the label | S |
| 20 | **Config file (yaml) for terminal mode** | Env-vars only; robodog convention is `config.yaml` | S |
| 21 | **Wire into main cli.py** (`robodog terminal` subcommand) | Standalone entry only | S |
| 22 | **/cost & token budget display per turn** | Total tokens only; no per-turn or budget warning | S |
| 23 | **Bash background tasks / long-running commands** | 120 s timeout then dead; no `run_in_background` | M |

## P3 — later / nice-to-have
| # | Feature | Notes |
|---|---|---|
| 24 | Permission gate (ask-per-action) | Deliberately deferred (YOLO chosen); keep `--ask` flag stub |
| 25 | Subagents / parallel tasks | One loop at a time is fine for v1 |
| 26 | Web fetch/search tools | FDA network likely blocks egress anyway |
| 27 | Code-map-powered context (`/map` integration) | Optimization once basics are solid |
| 28 | `useHistory`/roomId server-side sessions | Token optimization; validate determinism first |
| 29 | /export transcript, /doctor, keyboard shortcuts | Polish |

## Recommended build order
1. **P0 pack** (items 2,3,5 offline-buildable now; 1,4 need the FDA box)
2. **P1 UX pack** (6,7,8 — one small PR, transforms feel)
3. **P1 safety pack** (9,10,11)
4. **P1 context pack** (12,13)
5. P2 in listed order.

---

# Feature Designs (2026-07-18): UI · Resizing · Background Agents · Subagents · Running Scripts

Detailed designs for the five feature areas. `prompt_toolkit` 3.0.52 is now installed
alongside `rich` — both UI plans below assume it.

## 1. UI (an agentic coding terminal look-and-feel)

**Goal:** persistent input line at the bottom with a sticky status bar, scrolling
transcript above it, spinner during LLM calls, markdown answers, colored diffs,
slash-command autocomplete, input history.

**Design — inline renderer, NOT a full-screen TUI.** an agentic coding terminal renders inline:
output scrolls in the normal terminal buffer; only the input area + status bar are
"live". We get the same with `prompt_toolkit.PromptSession`:

- `PromptSession(bottom_toolbar=…, completer=…, history=…)` in `ui.py`:
  - `bottom_toolbar` (callable) = **the sticky status line**: `model · cwd · tokens · ctx% · [N bg tasks]`.
    Re-evaluated every redraw → live and resize-safe for free.
  - `completer` = slash-command completer (`/help`, `/model`, …, plus `@`-path completion later).
  - `history=FileHistory(~/.robodog/terminal_history)` = persistent ↑/↓ input history.
  - `prompt_toolkit.patch_stdout()` wraps the session so **background threads can print
    without corrupting the input line** (this is the enabler for background agents/tasks).
- While the agent turn runs there is no active prompt, so `rich` owns the screen:
  - `console.status("✳ Thinking… (esc to cancel)")` spinner during each ELSA call.
  - `rich.markdown.Markdown` for final answers; `Panel` for the welcome box (have).
  - Diffs: unified diff colored green/red via rich `Syntax`/manual styling (reuse `diff_service`).
- Keep the no-prompt_toolkit fallback path in `ui.py` (plain input + printed status) —
  it already works and covers weird consoles.

**Files:** `ui.py` (rewrite around PromptSession), `app.py` (use `session.prompt()`).
**Effort:** M. **Deps:** prompt_toolkit (installed).

## 2. Resizing

**Goal:** everything reflows when the terminal is resized (Windows Terminal, VS Code
panes, SSH) — no truncated boxes or stale-width wraps.

**Design — never cache a width:**
- `rich.Console()` re-queries terminal size **at each print** — panels/markdown/diffs
  reflow automatically as long as we (a) create one Console and let it size itself,
  (b) never pass fixed `width=`, (c) use `expand=True`/ratio layouts in Panels & Tables.
- `prompt_toolkit` redraws the input line + bottom toolbar on its own resize handling
  (Windows console events / SIGWINCH on POSIX) — sticky bar reflow is free.
- Rules to enforce in `ui.py`:
  - Welcome panel: `expand=False` but content lines short enough for 60 cols; below
    60 cols drop the panel and print plain lines (`console.width < 60` check at call time).
  - Tool-call/status lines: truncate previews to `console.width - fixed_prefix` at
    render time (compute per call, not at init).
  - Diff view: side-by-side only when `console.width >= 120`, else unified.
- Spinner (`console.status`) and `Live` displays: rich handles resize mid-spin.
- Test: run under `mode con: cols=50` and a wide window; assert no hard-coded widths
  (`grep -n "width=" terminal/` stays empty except computed values).

**Files:** `ui.py` only. **Effort:** S (mostly discipline + a few call-time checks).

## 3. Background agents

**Goal:** kick off a long agent task, keep typing; get notified when it finishes —
a modern agentic terminal's background tasks (`/tasks`, notifications between turns).

**Design — `terminal/background.py`:**
```python
@dataclass
class BgTask:
    id: str                # "bg1", "bg2", …
    kind: str              # "agent" | "bash"
    title: str
    status: str            # running | done | failed | killed
    buffer: list[str]      # thread-safe appended output lines
    result: str | None
    thread: threading.Thread
    started: float; ended: float | None

class BackgroundManager:
    def spawn_agent(self, prompt, make_loop) -> BgTask   # runs AgentLoop.run in daemon thread
    def spawn_bash(self, command, cwd) -> BgTask          # Popen + reader thread
    def list(self) -> list[BgTask]
    def output(self, id, tail=50) -> str
    def kill(self, id)                                    # sets cancel_event / kills proc tree
    def drain_notifications(self) -> list[str]            # completed-since-last-drain
```
- **Threading model:** each bg task = one daemon thread. Each background *agent* gets
  its **own AgentLoop + own ToolRegistry + own transcript** (no shared history with the
  foreground conversation). Tool events go to its buffer, not the screen.
- **ELSA politeness:** a global `threading.Semaphore(2)` in `llm_client.py` caps
  concurrent ELSA calls across foreground + all background agents (internal gateway,
  unknown rate limits — stay conservative).
- **Cancellation:** `AgentLoop` gets a `cancel_event: threading.Event` checked between
  iterations and between tool calls; `kill()` sets it (bash: terminate process tree via
  `taskkill /T /F` on Windows).
- **Notifications:** with `patch_stdout()` active, the manager prints
  `✔ bg1 done: <title>` the moment a task finishes, even while the user is typing;
  fallback path drains before each prompt.
- **UX:**
  - `/bg <prompt>` → spawn background agent, returns `bg1`.
  - `/tasks` → table of tasks (id, kind, status, runtime, title).
  - `/tail bg1` → last N buffer lines; `/kill bg1`.
  - Status bar shows `⚙2` when tasks are running.

**Files:** new `background.py`; `loop.py` (+cancel_event), `app.py` (commands), `ui.py`
(notifications + status). **Effort:** M–L. **Order:** after UI (needs patch_stdout).

## 4. Agents (subagents the model can spawn)

**Goal:** the main agent delegates scoped work to sub-agents with their own context —
a modern agentic terminal's Agent tool (Explore/Plan/general).

**Design — `terminal/agents.py`, exposed as a tool:**
```
<tool name="agent">
  <param name="prompt">Find every caller of parse_llm_output and summarize</param>
  <param name="type">explore</param>        (optional: explore | general)
  <param name="background">true</param>     (optional; default false = wait)
</tool>
```
- **Agent types** (dict of definitions, later loadable from `.robodog/agents/*.md`):
  - `explore`: read-only registry (read_file/glob/grep/list_dir only), tighter
    max_iterations (10), system context says "return findings as your final message".
  - `general`: full registry, max_iterations 25.
- **Execution:**
  - Foreground (default): runs synchronously inside the parent's tool call; the child's
    **final text becomes the tool result** — child transcript is discarded (that's the
    whole point: context isolation; parent pays only for the summary).
  - `background=true`: delegates to `BackgroundManager.spawn_agent`, immediately returns
    `"started bg3"`; parent can later call `<tool name="task_output"><param name="id">bg3…`.
- **Safety rails:** `depth` counter passed into child registries — subagents cannot
  spawn subagents (depth 1 max, mirrors an agentic coding terminal). Parent's iteration budget is
  independent of the child's. Same global ELSA semaphore applies.
- **UI:** child tool activity rendered indented + dimmed under the parent's
  `⚙ agent explore…` line (or hidden behind `--verbose`).

**Files:** new `agents.py`; register in `tools.py` (`agent`, `task_output`); reuse
`background.py`. **Effort:** M (small once background.py exists — a subagent is just
AgentLoop-in-a-tool). **Order:** after background agents.

## 5. Running scripts

**Goal:** first-class script/command execution three ways — the agent's `bash` tool
(have, basic), the user's direct `!` passthrough, and long-running/background commands.

**Design:**
- **`!` prefix (user passthrough), in `app.py`:** `! pytest -q` runs immediately in the
  shell — no LLM round-trip — output **streams live** to the terminal AND is appended to
  the conversation history as a `tool` turn, so the next agent message can see it
  (exactly a modern agentic terminal's `!` behavior). Empty output/exit code recorded too.
- **Streaming bash (upgrade `_bash` in `tools.py`):** switch `subprocess.run` →
  `Popen` + reader thread; echo each line dimmed as it arrives (callback into UI),
  while accumulating for the clamped tool result. A 30-min hard cap replaces silent
  死-air; spinner shows elapsed seconds.
- **Timeout & kill correctness (Windows):** `taskkill /T /F /PID` to kill the process
  *tree* (plain `.terminate()` orphans children under PowerShell); POSIX `os.killpg`.
- **Background commands:** `<param name="background">true</param>` on the bash tool →
  `BackgroundManager.spawn_bash`, returns task id immediately (for dev servers,
  watchers, long builds). Agent polls with `task_output`; user with `/tail`.
- **Script affordances:**
  - `run_script` convenience tool: write content to a temp `.ps1`/`.py`/`.sh` in the
    scratch dir and execute it — avoids quoting hell for multi-line scripts through
    PowerShell `-Command`.
  - cwd, env passthrough, `timeout` param (have), exit-code always in the result (have).
- **Safety note (YOLO):** stays prompt-free by decision; the `--ask` stub would gate
  `bash`/`run_script` first if ever enabled.

**Files:** `tools.py` (streaming, background, run_script), `app.py` (`!` prefix),
`background.py` (spawn_bash). **Effort:** M.

---

# Deep-Dive Addendum (2026-07-18): official agentic-tooling docs audit

Two doc-research passes over docs.claude.com (interactive UX + agentic internals)
were diffed against this plan. Most of the enormous surface (vim mode, themes,
voice, fullscreen renderer, hooks, MCP, plugins, remote control) is P3/N-A for a
single-user FDA-machine clone. These are the items we genuinely missed or
underweighted, filtered for impact:

## Missed — now added
| Priority | Feature | Why it matters for us | Disposition |
|---|---|---|---|
| **P1** | **File checkpointing + /rewind** | an agentic coding terminal snapshots files before every edit and keeps 100 checkpoints with a restore menu (code / conversation / both). This is the *stronger* form of our "backup before write" item — and under YOLO permissions it's the only undo we'd have. | Upgrade safety pack (task #4): snapshot to `~/.robodog/checkpoints/<session>/` before each mutating tool; `/rewind` lists prompts, restores files. |
| **P1** | **Read-before-edit/write enforcement** | Real an agentic coding terminal refuses to Edit/Write a file the model hasn't Read this session — prevents blind clobbering. Cheap: track a `read_paths` set in ToolRegistry. | Add to safety pack (task #4). |
| **P1** | **Ignore-aware glob/grep** | Docs: Glob/Grep respect .gitignore. Ours recurse into `.git`, `node_modules`, `__pycache__`, `dist` — noise + token waste. | Add default exclude list (+ .gitignore parse later) to `tools.py`. |
| **P1** | **Auto-compact strategy detail** | Docs: compaction *clears older tool outputs first*, then summarizes; CLAUDE.md is re-injected from disk afterward. Adopt exactly this — dropping old tool-result turns is cheap and LLM-free before any summarization. | Fold into context pack (task #5). |
| **P2** | **Headless print mode (`-p`)** | `robodog terminal -p "prompt" --output-format json` — one-shot agentic runs for scripting/CI. FDA team already builds batch lambdas; this is the natural integration point. | New task. |
| **P2** | **AskUserQuestion tool** | Lets the model ask a multiple-choice question mid-task instead of guessing. Small tool, big steering value in an interactive terminal. | Add to tools backlog. |
| **P2** | **Plan mode (read-only cycle)** | Shift+Tab-style mode where the registry exposes only read tools and the model proposes before touching anything. We already have the explore-registry filter — a top-level mode is ~30 lines. | Add to P2 list. |
| **P2** | **Custom commands/agents from files** | `.robodog/commands/*.md` → user slash commands (prompt templates, `$ARGUMENTS`); `.robodog/agents/*.md` → custom subagent types (frontmatter: name/description/tools/maxTurns) matching the documented format. | Add to P2 list; agents.py already keyed by a dict — file loading slots in. |
| **P2** | **Esc interrupt semantics** | Esc = interrupt current turn (distinct from Ctrl-C clear/exit); double-Esc = rewind menu. Fold into UX pack cancellation design. | Task #3 note. |

## Free wins discovered (prompt_toolkit gives these for ~0 effort)
- **Ctrl+R reverse history search** — built into PromptSession + FileHistory.
- **Vim editing mode** — `vi_mode=True` flag if wanted (`/config` toggle later).
- **Ctrl+A/E/K/U/W readline editing** — default Emacs bindings, free.

## Confirmed-right calls (docs validated our design)
- `!` shell mode: output goes into context and the model responds — matches our plan.
- Subagent result contract: parent sees only the final text summary — matches Phase A build.
- Explore agent type: read-only, skips project instructions — matches.
- Bash: 2-min default / 10-min max timeout, ~30KB output clamp — ours matches (30k clamp).
- Retry line format "API error · Retrying in Ns · attempt n/N" — implemented verbatim.

## Explicitly deprioritized (P3/N-A) after review
Hooks system, MCP client integration, plugins, themes/custom statusline scripts,
voice, image paste (ELSA is text-only), fullscreen alternate-screen renderer,
`/btw` side-questions, session branching/fork, output styles, web tools (FDA
egress), remote control, marketplaces. Revisit only on demand.

## Dependency-ordered build sequence for these five
(revised 2026-07-18: user confirmed subagents are a must-have → pulled forward.
Key insight: FOREGROUND subagents are just AgentLoop-in-a-tool and need NO
BackgroundManager — only background subagents do.)

1. **Subagents Phase A** (foreground `agent` tool: explore/general types, depth cap 1,
   child transcript discarded, final text = tool result) — no dependencies, build now.
2. **UI upgrade + resizing** (PromptSession + patch_stdout + spinner + markdown).
3. **Running scripts** (`!` passthrough + streaming bash + tree-kill) — independent.
4. **Background manager** (bash first, then agents) — needs patch_stdout from step 2.
5. **Subagents Phase B** (`background=true` + `task_output`) — thin layer over 4.
