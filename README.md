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

## Get Started

New here? Follow these five steps in order — each one unblocks the next.

**1. Install** (requires Python 3.9+):

```bash
pip install -U robodog-terminal
```

**2. Confirm the command works:**

```bash
robodog-terminal --echo          # offline demo, no keys needed yet
```

Note the **dash** — the Python *package* is `robodog_terminal` (underscore),
but the installed *command* is `robodog-terminal` (dash). `robodogt` is a
short alias for the same thing.

> **`robodog-terminal: command not found`?** Your pip scripts directory
> isn't on `PATH` yet — pip warns about this during install (`WARNING: The
> script ... is installed in ... which is not on PATH`). Two fixes:
>
> - **Right now, no setup:** `python -m robodog_terminal --echo` works
>   regardless of PATH.
> - **Permanently (Windows):**
>   ```powershell
>   python -m pip show -f robodog-terminal   # note the Location: + Scripts entries
>   setx PATH "$($env:PATH);<the-scripts-dir-from-above>"
>   ```
>   **Then close this terminal and open a brand-new one** — `setx` only
>   updates the registry; already-open terminals (and anything spawned from
>   them) keep their old PATH until you start a fresh window.
> - **Permanently (macOS/Linux)**, usually `~/.local/bin`:
>   ```bash
>   echo 'export PATH="$HOME/.local/bin:$PATH"' >> ~/.bashrc
>   ```

**3. Get an API key.** The default provider is [OpenRouter](https://openrouter.ai/keys)
— any model in its catalog works without code changes.

**4. Store the key.** Pick one:

- **Quick — plaintext file** (`~/.robodog/config.env`, created if missing,
  loaded automatically at startup):
  ```bash
  mkdir -p ~/.robodog
  echo "ROBODOG_LLM_KEY=<your OpenRouter key>" >> ~/.robodog/config.env
  ```
- **Encrypted — KeePass**, if you already keep API keys in a KeePass vault:
  see [KeePass setup](#keepass-setup-optional-step-by-step) below instead of
  the plaintext file. Skip step 4's plaintext option entirely — env vars win
  over KeePass when both are set, so don't set both.

**5. Run it:**

```bash
robodog-terminal            # defaults to OpenRouter + a Claude model
```

Type a task at the `›` prompt (e.g. `create fib.py that prints fib(10), run
it`). Run `/doctor` any time — it reports which keys/vars were found (never
their values) and flags config mistakes like a mismatched backend/model
pairing.

Prefer building from source instead of PyPI?

```bash
git clone https://github.com/adourish/robodog.git
cd robodog/apps/cli/robodog
pip install rich prompt_toolkit requests        # core deps
python robodog_terminal/app.py --echo
```

## More examples

```bash
# offline demo — no keys needed (scripted, just to see the UI)
robodog-terminal --echo

# live via OpenRouter (default provider; any catalog id works)
robodog-terminal --backend openrouter --model anthropic/claude-sonnet-4.6

# live against OpenAI directly (bare ids, no provider/ prefix)
robodog-terminal --backend openai --model gpt-4o

# air-gapped gateway (SEMOSS-style runPixel; keys from KeePass)
robodog-terminal --backend gateway

# one-shot, non-interactive (great for scripts/CI)
robodog-terminal --backend openai -p "fix the bug in x.py and run the tests"
```

From a source checkout, replace `robodog-terminal` with
`python robodog_terminal/app.py` (run inside `apps/cli/robodog`). The test
suite runs from there too:

```bash
cd apps/cli/robodog

# deterministic, keyless
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

First-time setup lives in [Get Started](#get-started) above. This section is
the reference for everything beyond the basic OpenRouter-key path.

### Keys — all the options

Environment variables (or `config.env` lines — same names) always win:

| Env var | Purpose |
|---|---|
| `ROBODOG_LLM_KEY` | API key for the OpenAI-compatible backend (OpenRouter by default) |
| `ROBODOG_LLM_URL` | override the base URL (OpenAI, Groq, LiteLLM, local Ollama, …) |
| `ROBODOG_MODEL` | default model id |
| `GATEWAY_ENDPOINT` / `GATEWAY_ENGINE` / `GATEWAY_ACCESS_KEY` / `GATEWAY_SECRET_KEY` | self-hosted runPixel-style gateway |

### KeePass setup (optional, step by step)

Instead of a key in a plaintext `config.env`, Robodog can pull keys from a
**KeePass** database at startup. It looks for three files in `~/.robodog/`
(or wherever `ROBODOG_KEEPASS_DIR` points; `ROBODOG_KEEPASS_DB` /
`ROBODOG_KEEPASS_KEYFILE` override the exact paths):

```
~/.robodog/
├── keepass_loader.py           # the loader module (code below)
├── automation-keys.kdbx        # the database
└── automation-keys.keyfile     # keyfile auth -> no password prompt
```

**1. Install pykeepass and create the database + keyfile:**

```bash
pip install pykeepass
```

```python
import os
from pathlib import Path
from pykeepass import create_database

d = Path.home() / ".robodog"
keyfile = d / "automation-keys.keyfile"
keyfile.write_bytes(os.urandom(32))           # random keyfile, no master password
kp = create_database(str(d / "automation-keys.kdbx"), password=None,
                     keyfile=str(keyfile))
kp.add_entry(kp.root_group, "OpenRouter", "robodog", "<your OpenRouter key>",
             url="https://openrouter.ai/api/v1")
kp.save()
```

**2. Add entries for the providers you use.** Robodog looks them up by
**exact title**; the API key goes in the *password* field:

| Entry title | Used by | URL field (optional override) |
|---|---|---|
| `OpenRouter` | `--backend openrouter` / auto | `https://openrouter.ai/api/v1` |
| `OpenAI` | `--backend openai` | `https://api.openai.com/v1` |
| `Gateway` | `--backend gateway` (username = access key, password = secret key) | — |

**3. Drop in the loader module** (`~/.robodog/keepass_loader.py`) — Robodog
imports it and calls exactly this interface:

```python
# ~/.robodog/keepass_loader.py
from pykeepass import PyKeePass

class KeePassLoader:
    def __init__(self, db_path, keyfile=None):
        self.db_path, self.keyfile, self.kp = db_path, keyfile, None

    def unlock(self, password=None):
        self.kp = PyKeePass(self.db_path, password=password, keyfile=self.keyfile)

    def get_credentials(self, title):
        e = self.kp.find_entries(title=title, first=True)
        if e is None:
            return None
        return {"title": e.title, "username": e.username,
                "password": e.password, "url": e.url}
```

**4. Verify:** start `robodog-terminal` and run `/doctor` — the `keepass`
line reports "unlocked" and which entry titles were found (values are never
printed). Remove any `ROBODOG_LLM_KEY` from `config.env` so the KeePass path
is actually exercised (env vars win when both are set).

To rotate a token later, overwrite the entry's password field (in KeePassXC
or a short `pykeepass` script) — Robodog picks up the new value on next
start.

**Already use KeePass for other credentials?** Point Robodog at your
existing vault instead of creating a second one — no new database needed.
Two requirements: the vault has an entry titled exactly `OpenRouter` (or
`OpenAI` / `Gateway`), and its folder has a `keepass_loader.py` implementing
the `KeePassLoader` interface above (many personal automation setups already
have one). Then in `~/.robodog/config.env`:

```bash
ROBODOG_KEEPASS_DB=/path/to/your/existing.kdbx
ROBODOG_KEEPASS_DIR=/path/to/the/folder/containing/keepass_loader.py
```

The keyfile is assumed to sit next to the database with the same name and a
`.keyfile` extension; set `ROBODOG_KEEPASS_KEYFILE` explicitly if yours
lives elsewhere. `pip install pykeepass` if it isn't already in your
environment.

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

### 0.2.3

- **Add:** actionable hints on the LLM errors users actually hit — 401/403
  (key rejected: points at `ROBODOG_LLM_KEY` / the KeePass entry), 402
  (credits/quota), and 404 (wrong base URL: points at `ROBODOG_LLM_URL`) —
  alongside the existing 400 model-mismatch hint.
- **Fix:** `--model` / `ROBODOG_MODEL` is normalized at startup, not just at
  `/model` — a dashed version slip (`anthropic/claude-sonnet-4-6`) no longer
  fails the first request with an opaque `invalid model ID`.
- **Add:** `/doctor` gains a `model-backend` check that flags a mismatched
  pairing (OpenRouter-style id on `--backend openai`, or a bare id on
  `--backend openrouter`) before any request is sent.

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
