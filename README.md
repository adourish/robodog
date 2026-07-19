# 🤖 Robodog

Robodog Terminal is an **agentic coding terminal** for your shell — a tool-use loop
that reads and edits files, runs commands, runs tests, and self-corrects, driven by
a large language model. It's built to run leading models on **self-hosted / air-gapped LLM gateways**, and works just as well with OpenAI-compatible
models or a fully offline mock for development.

> This repository is a monorepo. Terminal mode (`apps/cli/robodog/robodog_terminal`)
> is the active, flagship client — everything else is archived.

## Preview

```text
┌──────────────────────────── 🤖 robodog ─────────────────────────────┐
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

# run the test suite (deterministic, keyless)
python robodog_terminal/run_tests.py

# opt-in LIVE performance test: fires N real subagents concurrently and
# reports the fan-out speedup (needs a live backend; skips cleanly without one)
ROBODOG_PERF=1 python robodog_terminal/run_tests.py
python robodog_terminal/perf_fanout.py 12        # or run it directly
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
and whitespace-tolerant edits · **parallel subagents** (fan out several in one
turn — they run concurrently) plus background subagents ·
per-prompt **checkpoints** with `/rewind` · JSONL **sessions** (`/resume`,
`--continue`) · **plan mode** · **skills & custom commands** (`.robodog/`) ·
`CLAUDE.md`/`ROBODOG.md` instruction hierarchy · a rich + prompt_toolkit **TUI**
(emoji/color status line, clickable file & `file:line` links, multiline paste,
mid-turn Ctrl+B backgrounding) · **headless `-p`** (text/json) · `/doctor`.

## Configuration

### Keys

Simplest path: environment variables. `ROBODOG_LLM_URL`/`ROBODOG_LLM_KEY` for
any OpenAI-compatible endpoint (OpenRouter, OpenAI, LiteLLM, …), or
`GATEWAY_ENDPOINT`/`GATEWAY_ENGINE`/`GATEWAY_ACCESS_KEY`/`GATEWAY_SECRET_KEY`
for a self-hosted runPixel-style gateway. Env vars always win.

Optional: a **KeePass** database, so keys never touch env vars or disk in
plaintext. Robodog looks up credentials by entry title (`OpenAI`,
`OpenRouter`, `Gateway`) via a `keepass_loader.py` module (bring your own —
a thin `pykeepass` wrapper exposing `KeePassLoader(db_path, keyfile).get_credentials(title=...)`
is all it needs; keyfile-only auth means no master-password prompt). Point
Robodog at it with:

| Env var | Purpose |
|---|---|
| `ROBODOG_KEEPASS_DIR` | directory containing `keepass_loader.py`, `automation-keys.kdbx`, `automation-keys.keyfile` |
| `ROBODOG_KEEPASS_DB` / `ROBODOG_KEEPASS_KEYFILE` | exact file paths, if your layout differs |

Persist these without touching your system environment by dropping them in
`~/.robodog/config.env` (`KEY=VALUE` per line, loaded automatically on
startup; existing env vars still win). Falls back to
`~/.robodog/automation-keys.kdbx` if nothing is set.

Run `/doctor` any time to see which entries/vars were actually found — values
are never printed.

<details>
<summary>Creating a KeePass DB from scratch</summary>

```python
import os
from pykeepass import create_database

keyfile = "keys/automation-keys.keyfile"
open(keyfile, "wb").write(os.urandom(32))     # random keyfile, no master password
kp = create_database("keys/automation-keys.kdbx", password=None, keyfile=keyfile)
kp.add_entry(kp.root_group, "OpenRouter", "robodog", "<your-api-key>",
             url="https://openrouter.ai/api/v1")
kp.save()
```

To rotate a token later, open the same entry (in KeePassXC, or a short
`pykeepass` script) and overwrite the password field — Robodog picks up the
new value on next unlock.
</details>

### Adding a new model

A model is just an ID string forwarded to the provider — there is no list to
edit. Three levels, by what you actually mean:

**1. A different model on the current provider — no code.** The default provider
is OpenRouter, so any catalog ID works right away. OpenRouter uses *dotted*
version ids (`-4.8`, **not** `-4-8`; the terminal auto-corrects that common
slip and inline `# comments`):

```bash
robodog-terminal --model deepseek/deepseek-chat         # at launch
/model anthropic/claude-opus-4.8                        # live, mid-session
echo 'ROBODOG_MODEL=anthropic/claude-opus-4.8' >> ~/.robodog/config.env  # persist default
```

**2. A different provider — env vars, still no code.** Point the
OpenAI-compatible client at any base URL + key (Groq, Together, Fireworks,
Azure, or a local Ollama at `http://localhost:11434/v1`):

```bash
# ~/.robodog/config.env
ROBODOG_LLM_URL=https://api.groq.com/openai/v1
ROBODOG_LLM_KEY=<key>            # or store it in the KeePass automation DB
# then:  robodog-terminal --model llama-3.1-8b-instant
```

**3. A named `--backend` shortcut or a non-OpenAI provider — small code change.**
For a first-class flag (`--backend groq`), add the name to the `--backend`
`choices` list and a `make_openai_compat(...)` branch in `build_backend()`
(`app.py`). For a provider that isn't OpenAI-compatible at all, add an
`LLMClient` subclass in `robodog_terminal/llm_client.py` — see
`OpenAICompatClient`/`GatewayClient` as templates.

### Project instructions

Read from `CLAUDE.md` / `ROBODOG.md` / `.robodog.md` walking from the repo
root to your working directory, plus `~/.robodog/CLAUDE.md` or
`~/.robodog/ROBODOG.md` for global instructions.

## Repository layout

```
robodog/
└── apps/cli/robodog/robodog_terminal/   Robodog Terminal — the active project
```

Full design, gap analysis, and roadmap: **`apps/cli/docs/TERMINAL_MODE_PLAN.md`**.

## Changelog

Published to PyPI as [`robodog-terminal`](https://pypi.org/project/robodog-terminal/)
(`pip install -U robodog-terminal`).

### 0.2.2

- **Add:** OpenAI-compatible backends now surface a hint on HTTP 400s caused
  by the common `provider/model` id mismatch (an OpenRouter-style id sent to
  OpenAI directly, or a bare model id sent to OpenRouter).
- **Add:** subagent fan-out stress tests (concurrency, failure isolation,
  background storm, cancel-under-load) and a live perf benchmark
  (`perf_fanout.py`).
- **Fix:** dropped stale legal/branding exposure — the docs no longer name
  any specific model vendor's product, and a proper `LICENSE` (MIT) now
  ships with the package.

### 0.2.1

- **Fix:** clipboard pastes containing lone UTF-16 surrogates (e.g. a split
  emoji on Windows) no longer crash with `'utf-8' codec can't encode…
  surrogates not allowed`. Input is sanitized at the boundary, so every
  downstream encode (HTTP body, session JSONL) is safe.
- **Fix:** running `app.py` directly no longer hit a `NameError` on first input
  (missing import on the direct-run fallback path).
- **Add:** `Ctrl+U` clears the whole input (all lines).
- **Add:** `/model` normalizes ids — strips inline `# comments` and corrects the
  common dashed OpenRouter/Anthropic slip (`claude-opus-4-8` → `claude-opus-4.8`).
- **Tests:** multi-provider model coverage (OpenRouter/OpenAI/Groq/Together/
  Ollama ids, temperature/max_tokens passthrough) and surrogate-safe wire
  payloads for every backend. 18/18 suites green.

### 0.2.0

- First public release: agentic tool-use loop, file edit/run tools, parallel &
  background subagents, plan mode, sessions/checkpoints, rich + prompt_toolkit
  TUI, headless `-p`, gateway / OpenAI-compatible / offline backends.

---

*Robodog is an independent project. It integrates various LLM providers, but is not affiliated with or endorsed
by Anthropic or any provider.*
