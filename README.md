# 🐕 Robodog

Robodog Terminal is an **agentic coding terminal** for your shell — a tool-use loop
that reads and edits files, runs commands, runs tests, and self-corrects, driven by
a large language model. It's built to run leading models on **self-hosted / air-gapped LLM gateways**, and works just as well with OpenAI-compatible
models or a fully offline mock for development.

> This repository is a monorepo. Terminal mode (`apps/cli/robodog/robodog_terminal`)
> is the active, flagship client — everything else is archived.

## Preview

```text
┌──────────────────────────── 🐕 robodog ─────────────────────────────┐
│                                                                     │
│  Robodog Terminal   agentic coding in your shell                    │
│                                                                     │
│  model: gpt-4o                                                      │
│  cwd:   C:\projects\robodog                                         │
│                                                                     │
│  /help commands   ! run shell   /rewind undo edits   /exit quit     │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘
🫧 64% | 🔋 15.6k | 🦾 gpt-4o | 📁 apps/cli
› create fib.py that prints fib(10), run it, and report the result
  ⚙ write_file fib.py
  ⚙ bash python fib.py
    ↳ $ python fib.py  (exit 0)  ·  55
The script printed 55. Created fib.py and ran it.
[3 steps · 5.7k tok · 4.2s]
```

## Setup

Requires **Python 3.9+**.

```bash
git clone https://github.com/adourish/robodog.git
cd robodog/apps/cli/robodog
pip install rich prompt_toolkit requests        # core deps

# optional, for live models:
#   OpenAI/OpenRouter  -> set an API key (see Configuration)
#   enterprise the gateway           -> keys load from the KeePass automation DB
```

Or install it as a package (first-class commands):

```bash
pip install -e "robodog/apps/cli/robodog[terminal]"
robodog-terminal --echo         # then: robodog-terminal --backend openai --model gpt-4o
```

## Quickstart

```bash
cd apps/cli/robodog

# offline demo — no keys needed (scripted, just to see the UI)
python robodog_terminal/app.py --echo

# live with an OpenAI-compatible model
python robodog_terminal/app.py --backend openai --model gpt-4o

# air-gapped gateway (SEMOSS-style runPixel; keys from KeePass)
python robodog_terminal/app.py --backend gateway

# one-shot, non-interactive (great for scripts/CI)
python robodog_terminal/app.py --backend openai -p "fix the bug in x.py and run the tests"

# run the test suite (18 suites)
python robodog_terminal/run_tests.py
```

Inside the terminal, just type a task (`create hello.py and run it`). Useful commands:

| | |
|---|---|
| `/help` | list all commands |
| `/plan` | read-only: propose a plan, then approve to implement |
| `/bg <task>` · `/tasks` · `/tail` · `/kill` | background subagents |
| `/rewind` | undo file changes from a previous prompt |
| `/model <name>` · `/doctor` · `/context` · `/compact` | switch model · diagnostics · context |
| `! <cmd>` | run a shell command directly (shared with the agent) |
| `@path/to/file` | inline a file into your message |

Handy flags: `--guard confirm` (ask before destructive commands),
`--permission-mode plan`, `--editor vscode` (clickable `file:line` jumps),
`--verbose`.

## What it does

Prompted tool-use loop (intent nudge + circuit breaker) · tools:
`read_file / write_file / edit_file / multi_edit / bash / run_script / run_tests
/ glob / grep / list_dir` with read-before-edit, post-edit syntax verification,
and whitespace-tolerant edits · foreground **and background subagents** ·
per-prompt **checkpoints** with `/rewind` · JSONL **sessions** (`/resume`,
`--continue`) · **plan mode** · **skills & custom commands** (`.robodog/`) ·
`CLAUDE.md`/`ROBODOG.md` instruction hierarchy · a rich + prompt_toolkit **TUI**
(emoji/color status line, clickable file & `file:line` links, multiline paste,
mid-turn Ctrl+B backgrounding) · **headless `-p`** (text/json) · `/doctor`.

## Configuration

Keys load automatically from the KeePass automation DB (`OpenAI`, `OpenRouter`) or from environment variables
(`GATEWAY_ENDPOINT`/`GATEWAY_ENGINE`/`GATEWAY_ACCESS_KEY`/`GATEWAY_SECRET_KEY`,
`ROBODOG_LLM_URL`/`ROBODOG_LLM_KEY`). Run `/doctor` to see which entries/vars
were found (values are never printed). Project instructions are read from
`CLAUDE.md` / `ROBODOG.md` / `.robodog.md` walking from the repo root to your
working directory, plus `~/.robodog/CLAUDE.md` or `~/.robodog/ROBODOG.md` for
global instructions.

## Repository layout

```
robodog/
└── apps/cli/robodog/robodog_terminal/   Robodog Terminal — the active project
```

Full design, gap analysis, and roadmap: **`apps/cli/docs/TERMINAL_MODE_PLAN.md`**.

---

*Robodog is an independent project. It integrates various LLM providers, but is not affiliated with or endorsed
by Anthropic or any provider.*
