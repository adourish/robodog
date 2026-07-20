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

This walkthrough assumes **nothing is installed yet**. Read it top to bottom
— every step is here in order, and you never need to jump ahead. Budget
about 5 minutes (15 if you choose the encrypted KeePass option in step 6).

### Step 1 — Check you have Python 3.9+

```bash
python --version         # try python3 --version if that isn't found
```

No Python? Install it from [python.org/downloads](https://www.python.org/downloads/)
(on Windows, tick **"Add Python to PATH"** in the installer — it saves you
step 3), then reopen your terminal and check again.

### Step 2 — Install Robodog

```bash
pip install -U robodog-terminal
```

Watch the output for a line like `WARNING: The script robodog-terminal.exe
is installed in '...' which is not on PATH`. If you see it, note that
directory — step 3 needs it.

### Step 3 — Make the `robodog-terminal` command work

```bash
robodog-terminal --version
```

If that prints a version, skip to step 4. If you get **`command not
found`** (or `not recognized` on Windows), pip's scripts directory isn't on
your `PATH`. Either work around it or fix it properly:

**Work around it (nothing to configure)** — this always works:

```bash
python -m robodog_terminal --version
```

Use `python -m robodog_terminal` in place of `robodog-terminal` for the rest
of this guide.

**Or fix PATH permanently — Windows:**

```powershell
python -m pip show -f robodog-terminal    # note the Location: line + Scripts entries
setx PATH "$($env:PATH);<the-scripts-dir-from-above>"
```

⚠️ **Then close your terminal and open a brand-new one.** `setx` only writes
the registry — already-open terminals keep their old `PATH` forever. This is
the single most common reason people think the fix "didn't work".

**Or fix PATH permanently — macOS/Linux** (usually `~/.local/bin`):

```bash
echo 'export PATH="$HOME/.local/bin:$PATH"' >> ~/.bashrc
source ~/.bashrc
```

> Note the **dash**: the Python *package* is `robodog_terminal` (underscore),
> but the installed *command* is `robodog-terminal` (dash). `robodogt` is a
> short alias for the same command.

### Step 4 — Smoke test with no API key

```bash
robodog-terminal --echo
```

This runs a scripted offline demo — no key, no network, no cost. You should
see the 🤖 banner and a `›` prompt. Type `/exit` to quit. If this works, your
install is sound and everything left is credentials.

### Step 5 — Get an API key

Robodog defaults to **OpenRouter**, which proxies most major models behind
one key. Create one at [openrouter.ai/keys](https://openrouter.ai/keys) and
copy it — it looks like `sk-or-v1-...`. (Prefer OpenAI, Groq, a local Ollama,
or a self-hosted gateway? Get set up here first, then see
[Configuration](#configuration) to switch providers.)

### Step 6 — Store the key

Pick **one** of these. Don't do both — plain env vars always win over
KeePass, so a stale `ROBODOG_LLM_KEY` will silently shadow your vault.

|  | Option A — config file | Option B — KeePass |
|---|---|---|
| Setup time | ~1 min | ~10 min |
| Key stored as | plaintext on disk | encrypted vault |
| Good for | trying it out, personal machines | shared/work machines, key rotation, teams already on KeePass |

---

#### Option A — plaintext config file

Robodog reads `~/.robodog/config.env` at startup (it's user-local and
gitignored — never committed):

```bash
mkdir -p ~/.robodog
echo "ROBODOG_LLM_KEY=sk-or-v1-your-key-here" >> ~/.robodog/config.env
```

On Windows PowerShell:

```powershell
New-Item -ItemType Directory -Force "$env:USERPROFILE\.robodog" | Out-Null
Add-Content "$env:USERPROFILE\.robodog\config.env" "ROBODOG_LLM_KEY=sk-or-v1-your-key-here"
```

Now skip to **step 7**.

---

#### Option B — encrypted KeePass vault

Robodog can pull keys from a KeePass database at startup, unlocked by a
**keyfile** so there's no password prompt. Three pieces have to line up: the
database, a loader module, and two config lines pointing at them.

**6B.1 — Install the KeePass library:**

```bash
pip install pykeepass
```

**6B.2 — Create the vault.** Robodog builds it for you — start it and run:

```
/keepass init sk-or-v1-your-key-here
```

That creates the database, a random keyfile (so there's no master-password
prompt), the loader module, and an `OpenRouter` entry holding your key — all
in `~/.robodog/`, which is where Robodog looks by default.

⚠️ **Back up `~/.robodog/automation-keys.keyfile`.** Without it the vault
cannot be opened — there is no master password to fall back on. `/keepass
init` will never overwrite an existing vault for exactly this reason.

Other `/keepass` subcommands:

| Command | Does |
|---|---|
| `/keepass` | show vault status + which provider entries were found |
| `/keepass init [key]` | create the vault, keyfile, and loader |
| `/keepass set <Title> <key>` | add or rotate one provider's key |

The entry **title must be exactly `OpenRouter`** — that's what Robodog looks
up — and the key goes in the *password* field. Titles for other providers:

| Entry title | Used by | URL field |
|---|---|---|
| `OpenRouter` | default / `--backend openrouter` | `https://openrouter.ai/api/v1` |
| `OpenAI` | `--backend openai` | `https://api.openai.com/v1` |
| `Gateway` | `--backend gateway` (username = access key, password = secret key) | — |

⚠️ Back up `automation-keys.keyfile` somewhere safe. Without it the vault
**cannot** be opened — there's no master password to fall back on.

**6B.3 — The loader module.** `/keepass init` already wrote this for you —
skip ahead unless you're wiring up an existing vault by hand. Robodog
imports the file by name and calls exactly this interface
(`~/.robodog/keepass_loader.py`):

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

**6B.4 — Point Robodog at the vault.** If you used the exact paths above
(`~/.robodog/automation-keys.kdbx`), that's the built-in default and **you
can skip this** — go to step 7.

Only if your vault lives elsewhere (e.g. you already keep API keys in an
existing KeePass database), add these to `~/.robodog/config.env`:

```bash
ROBODOG_KEEPASS_DB=G:\My Drive\Keys\automation-keys.kdbx
ROBODOG_KEEPASS_DIR=G:\My Drive\Keys
```

- `ROBODOG_KEEPASS_DB` — full path to the `.kdbx`
- `ROBODOG_KEEPASS_DIR` — folder containing `keepass_loader.py`
- `ROBODOG_KEEPASS_KEYFILE` — only if the keyfile *isn't* next to the
  database with the same name and a `.keyfile` extension

Values are read literally: no quotes, and **don't escape backslashes** —
Windows paths and spaces work as-is.

> **Reusing an existing vault?** You need only two things: an entry titled
> exactly `OpenRouter`, and a `keepass_loader.py` (from 6B.3) in the folder
> `ROBODOG_KEEPASS_DIR` points at. No need to create a second database.

### Step 7 — Verify your setup

```bash
robodog-terminal
```

At the `›` prompt, run:

```
/doctor
```

`/doctor` reports which keys and vars it found — **never their values** — and
flags mistakes like a mismatched backend/model pairing. On the KeePass path
you'll also see a `keepass` line reporting `unlocked` plus the entry titles
it matched.

Common failures and what they mean:

| `/doctor` says | Fix |
|---|---|
| no key found | `config.env` is missing, misspelled, or in the wrong folder — it must be `~/.robodog/config.env` |
| keepass not unlocked | wrong `ROBODOG_KEEPASS_DB` path, or the keyfile isn't beside the `.kdbx` |
| keepass unlocked, no entry | your entry title isn't exactly `OpenRouter` |
| 401 / key rejected at runtime | key is wrong or revoked — regenerate at [openrouter.ai/keys](https://openrouter.ai/keys) |

### Step 8 — Run your first real task

```bash
robodog-terminal
```

Type a task at the `›` prompt:

```
create fib.py that prints fib(10), run it, and report the result
```

Robodog writes the file, runs it, and reports back. `/rewind` undoes the file
changes, `/help` lists every command. You're set — see
[More examples](#more-examples) for other providers and flags.

---

<details>
<summary><b>Prefer to run from source instead of PyPI?</b></summary>

```bash
git clone https://github.com/adourish/robodog.git
cd robodog/apps/cli/robodog
pip install rich prompt_toolkit requests        # core deps
python robodog_terminal/app.py --echo
```

Credential setup (steps 5–7) is identical. Substitute
`python robodog_terminal/app.py` wherever this guide says
`robodog-terminal`.

</details>

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
| `/keepass [init\|set]` | create or inspect the encrypted key vault |
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

### KeePass reference

Setup steps are in [step 6, Option B](#option-b--encrypted-keepass-vault).
This is the reference for what Robodog looks for once it's configured.

Default layout — all three in `~/.robodog/`, overridable by env var:

```
~/.robodog/
├── keepass_loader.py           # loader module (ROBODOG_KEEPASS_DIR)
├── automation-keys.kdbx        # the database  (ROBODOG_KEEPASS_DB)
└── automation-keys.keyfile     # keyfile auth  (ROBODOG_KEEPASS_KEYFILE)
```

Entries are matched by **exact title**; the API key goes in the *password*
field:

| Entry title | Used by | URL field (optional override) |
|---|---|---|
| `OpenRouter` | `--backend openrouter` / auto | `https://openrouter.ai/api/v1` |
| `OpenAI` | `--backend openai` | `https://api.openai.com/v1` |
| `Gateway` | `--backend gateway` (username = access key, password = secret key) | — |

Resolution order per backend: `ROBODOG_LLM_KEY` env var → `config.env` →
KeePass entry. **Env wins**, so remove `ROBODOG_LLM_KEY` from `config.env`
if you want the vault to be used.

To rotate a token, overwrite the entry's password field (KeePassXC or a
short `pykeepass` script) — Robodog picks up the new value on next start,
with no config change.

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

### 0.2.4

- **Add:** `/keepass` — create and inspect the encrypted key vault from
  inside the terminal. `/keepass init [key]` writes the database, a random
  keyfile, and the loader module in one step (replacing the hand-run script
  the README used to ask for); `/keepass set <Title> <key>` adds or rotates
  a provider key; bare `/keepass` reports status. It refuses to overwrite an
  existing vault — the keyfile is the only way in, so clobbering it would
  destroy every credential stored there.
- **Fix:** tool results are summarized instead of dumped. `read_file` now
  reports `read 46 lines` rather than echoing the file's first line into the
  trace, `bash` reports `(exit 0) · N lines`, and `grep`/`list_dir`/`glob`
  report counts. Multi-line output can no longer flow into the transcript as
  a blob.
- **Fix:** failed tool calls render in red. They previously inherited the
  trace's `dim` style — including `ERROR:`/`BLOCKED:` results and failed
  commands — so failures were the *least* visible lines on screen.

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
