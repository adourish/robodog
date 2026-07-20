# 🤖 Robodog

Robodog Terminal is an **agentic coding terminal** for your shell — a tool-use loop
that reads and edits files, runs commands, runs tests, and self-corrects, driven by
a large language model. It's built to run leading models on **self-hosted / air-gapped LLM gateways**, and works just as well with OpenAI-compatible
models or a fully offline mock for development.

> This repository is a monorepo. Terminal mode (`apps/cli/robodog/robodog_terminal`)
> is the active, flagship client — everything else is archived.

## Preview

Six subagents fanned out in one turn — each result attributed, the answer
surfaced (not the metadata):

![6-way subagent fan-out, compact trace](docs/screenshots/2_fanout_compact.png)

![welcome banner and status line](docs/screenshots/1_welcome.png)

More screenshots in the [gallery](#screenshots) below.

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

**Or fix PATH permanently — Windows.** First find the Scripts directory:
`pip show -f` lists the exes as `..\Scripts\robodog-terminal.exe` — that's
**relative to the `Location:` line**, so a user-level install at
`...\AppData\Roaming\Python\Python312\site-packages` puts them in
`...\AppData\Roaming\Python\Python312\Scripts`:

```powershell
python -m pip show -f robodog-terminal    # Location: + "..\Scripts\..." entries
[Environment]::SetEnvironmentVariable("Path",
    [Environment]::GetEnvironmentVariable("Path", "User") + ";<the-Scripts-dir>",
    "User")
```

⚠️ **Do NOT use `setx PATH ...` for this.** `setx` silently truncates the
value to 1024 characters — on a machine with a long PATH it will *corrupt*
your user PATH while printing `SUCCESS` (see
[Troubleshooting](#troubleshooting) if that already happened). The
`[Environment]` method above has no such limit and touches only the
user-level PATH.

⚠️ **Then close your terminal and open a brand-new one.** PATH edits only
write the registry — already-open terminals (including new tabs of an open
Windows Terminal, and anything launched from VS Code) keep their old `PATH`
forever. This is the single most common reason people think the fix "didn't
work".

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
ROBODOG_KEEPASS_DB=C:\keys\automation-keys.kdbx
ROBODOG_KEEPASS_DIR=C:\keys
```

- `ROBODOG_KEEPASS_DB` — full path to the `.kdbx`
- `ROBODOG_KEEPASS_DIR` — folder containing `keepass_loader.py`
- `ROBODOG_KEEPASS_KEYFILE` — only if the keyfile *isn't* next to the
  database with the same name and a `.keyfile` extension

**Safer: keep the keyfile away from the database.** The keyfile IS the key —
anyone holding both files owns every credential inside. Storing them apart
(database in a backed-up or synced folder, keyfile on local-only disk or a
USB stick that's normally unplugged) means neither file alone is worth
anything:

```bash
ROBODOG_KEEPASS_DB=C:\keys\automation-keys.kdbx
ROBODOG_KEEPASS_DIR=C:\keys
ROBODOG_KEEPASS_KEYFILE=D:\secure\automation-keys.keyfile
```

In particular, don't let the keyfile ride along in the same cloud-sync
folder as the database — that recreates the both-files-in-one-place risk on
every synced machine.

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
| keepass not unlocked | wrong `ROBODOG_KEEPASS_DB` path, or the keyfile wasn't found — it must be beside the `.kdbx` (same name, `.keyfile` extension) or pointed at explicitly with `ROBODOG_KEEPASS_KEYFILE` (e.g. when it lives on separate media) |
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
`--continue`) · **plan mode** · **skills & custom commands** (`.robodog/` or
`.claude/` — Claude Code layouts work unchanged) ·
`CLAUDE.md`/`ROBODOG.md` instruction hierarchy · a rich + prompt_toolkit **TUI**
(emoji/color status line, clickable file & `file:line` links, multiline paste,
mid-turn Ctrl+B backgrounding) · **headless `-p`** (text/json) · `/doctor`.

## Screenshots

Every image is rendered by the real UI code (rich SVG export), not a mockup.
The default trace is compact — summaries, counts, attributed subagent
answers; `/verbose` (or `--verbose`) switches to the full per-call feed.

**Tool trace — summaries, a bounded live stream, loud failures.** `read_file`
reports a line count instead of echoing content; long command output shows a
15-line head with the rest held back (the model still gets everything);
failures render red, never dim:

![tool trace](docs/screenshots/4_tool_trace.png)

**The same fan-out with `/verbose`** — per-child `#N` tool calls and full
untruncated results:

![verbose fan-out](docs/screenshots/3_fanout_verbose.png)

**Plan mode** — the agent proposes read-only, you approve, it implements:

![plan mode](docs/screenshots/6_plan_mode.png)

**Colored diff preview** on every file edit (paths are clickable):

![diff preview](docs/screenshots/5_diff.png)

**Live task checklist** the agent maintains (`/todos`):

![todos](docs/screenshots/7_todos.png)

**Background subagents** — `/bg` detaches work, `/tasks` lists it, done
notifications land above the prompt:

![background subagents](docs/screenshots/8_background.png)

**`/doctor`** — environment diagnostics, including the model/backend pairing
check that catches a mismatch before any request is sent:

![doctor](docs/screenshots/9_doctor.png)

**Errors explain themselves** — provider mistakes come back with the fix, not
just a status code:

![error hints](docs/screenshots/10_error_hints.png)

### Use cases

**Search multiple websites in parallel** — six subagents each fetch a live
site through `run_script` and report its title, 3.6× faster than doing it
serially (this and the next scene run real network calls; regenerate with
`generate.py --live`):

![parallel web fetch](docs/screenshots/11_parallel_web.png)

**A mixed-workload agent squad in one turn** — python, powershell, and bash
scripts, live GitHub + PyPI API calls, and a Playwright CLI browser capture,
all concurrent, 4.3s wall:

![agent squad](docs/screenshots/12_squad.png)

The Playwright agent's own artifact — a real browser page capture:

![playwright capture](docs/screenshots/web_capture.png)

**Claude Code projects work unchanged** — extensions in `.claude/commands`,
`.claude/agents`, and `.claude/skills` are discovered alongside `.robodog/`
(which stays the override layer), just like `CLAUDE.md` instructions:

![.claude extensions](docs/screenshots/13_claude_dir.png)

These three scenes are also automated tests: `ROBODOG_LIVE=1 python
robodog_terminal/run_tests.py` runs the live web/API/Playwright suite, and
`.claude`/`.robodog` discovery is covered in the default suite.

## Configuration

First-time setup lives in [Get Started](#get-started) above. This section is
the reference for everything beyond the basic OpenRouter-key path.

### Keys — all the options

Every setting below is an environment variable. Robodog reads it from two
places, and a **real OS environment variable wins** over the file:

| Env var | Purpose |
|---|---|
| `ROBODOG_LLM_KEY` | API key for the OpenAI-compatible backend (OpenRouter by default) |
| `ROBODOG_LLM_URL` | override the base URL (OpenAI, Groq, LiteLLM, local Ollama, …) |
| `ROBODOG_MODEL` | default model id |
| `ROBODOG_KEEPASS_DB` / `ROBODOG_KEEPASS_DIR` / `ROBODOG_KEEPASS_KEYFILE` | KeePass vault, loader dir, keyfile (see [KeePass reference](#keepass-reference)) |
| `GATEWAY_ENDPOINT` / `GATEWAY_ENGINE` / `GATEWAY_ACCESS_KEY` / `GATEWAY_SECRET_KEY` | self-hosted runPixel-style gateway |

#### How to set them

**Option 1 — `config.env` (simplest, robodog-only).** Robodog auto-loads
`~/.robodog/config.env` at startup: one `KEY=VALUE` per line, **no quotes, no
spaces around `=`, and don't escape backslashes** — Windows paths work as-is.
No new terminal needed.

```
ROBODOG_KEEPASS_DB=C:\Keys\automation-keys.kdbx
ROBODOG_KEEPASS_DIR=C:\Keys
```

**Option 2 — real OS environment variables (available to every program).**
Set them once at the user level; they persist across reboots.

Windows PowerShell — use `[Environment]::SetEnvironmentVariable`, **not
`setx`** (`setx` truncates long values to 1024 chars and can corrupt PATH):

```powershell
[Environment]::SetEnvironmentVariable("ROBODOG_KEEPASS_DB", "C:\Keys\automation-keys.kdbx", "User")
[Environment]::SetEnvironmentVariable("ROBODOG_KEEPASS_DIR", "C:\Keys", "User")
```

macOS / Linux — append to your shell profile:

```bash
echo 'export ROBODOG_KEEPASS_DB="$HOME/keys/automation-keys.kdbx"' >> ~/.bashrc
echo 'export ROBODOG_KEEPASS_DIR="$HOME/keys"' >> ~/.bashrc
source ~/.bashrc
```

After setting OS variables, **open a brand-new terminal** — already-open
windows keep the old environment. Don't set the same variable both ways: if
it's in a real env var *and* `config.env`, the OS variable wins, so a stale
one silently shadows the file.

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

### Hooks & permissions

Drop a `settings.json` in `.robodog/` or `.claude/` (project or `~`; project
wins, `.robodog` over `.claude` — Claude Code settings work unchanged):

```json
{
  "permissions": {
    "allow": ["bash(git *)"],
    "deny":  ["bash(rm -rf *)", "write_file(*.env)"]
  },
  "hooks": {
    "PreToolUse":  [{ "matcher": "write_file|edit_file",
                      "command": "python lint_gate.py" }],
    "PostToolUse": [{ "matcher": "bash", "command": "python audit_log.py" }],
    "Stop":        [{ "command": "powershell -c '[console]::beep(880,120)'" }]
  }
}
```

**Permissions** — rules are `tool` or `tool(glob)`, matched against the
call's main argument (the command for `bash`/`run_script`, the path for file
tools). `deny` always blocks (the agent is told not to retry); `allow`
pre-approves the call past the `--guard confirm` prompt; anything unmatched
keeps the default behavior.

**Hooks** — shell commands run on agent events, with a JSON payload
(`event`, `tool_name`, `tool_input`, `tool_result`, `cwd`) on stdin.
`matcher` is a regex against the tool name (omit it to match every tool).
A `PreToolUse` hook that exits **2** blocks the tool call and its stderr is
returned to the model; other exit codes proceed. `PostToolUse` and `Stop`
(end of each agent turn) never block. Hung hooks are tree-killed at
`timeout` seconds (default 30) — a bad hook can never wedge the loop.

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

## Troubleshooting

Every entry here is a failure someone actually hit.

### `robodog-terminal` is not recognized (Windows)

pip installed fine but the command isn't found. Diagnose in one paste:

```powershell
# 1. does the exe exist? (pip show -f lists "..\Scripts\..." RELATIVE to Location:)
Test-Path "$env:APPDATA\Python\Python312\Scripts\robodog-terminal.exe"
# 2. is that dir in your stored user PATH?
[Environment]::GetEnvironmentVariable("Path", "User")
# 3. does it run by full path?
& "$env:APPDATA\Python\Python312\Scripts\robodog-terminal.exe" --version
```

If #1 is `False`, your install location differs — run
`python -m pip show -f robodog-terminal`, take the `Location:` line, and
replace `site-packages` with `Scripts`. If #2 is missing the dir, add it
with the `[Environment]::SetEnvironmentVariable` command from
[Step 3](#step-3--make-the-robodog-terminal-command-work) — **never
`setx`** — then open a brand-new terminal window. And at any point,
`python -m robodog_terminal` works with no PATH changes at all.

### `setx` printed "truncated to 1024 characters" and now PATH is broken

`setx` clobbered your user PATH with a truncated copy of the combined
system+user PATH. Repair it: list what survived with
`[Environment]::GetEnvironmentVariable("Path", "User")`, then write back the
entries that belong there (typically `...\AppData\Local\Microsoft\WindowsApps`,
your app dirs, plus the Python `Scripts` dir) using
`[Environment]::SetEnvironmentVariable("Path", "<entries>", "User")` — it has
no length limit. Your *system* PATH was not touched; a still-open terminal
from before the damage shows the original combined PATH if you need to
reconstruct the list.

### `pip install -U` fails with `WinError 32` (file in use)

A running robodog instance holds a lock on `robodog-terminal.exe`, and pip
aborts mid-uninstall. Close every robodog window (check Task Manager for
`robodog-terminal.exe` / stray `python.exe`), then:

```powershell
pip install --force-reinstall robodog-terminal
```

### `ModuleNotFoundError: No module named 'robodog_terminal'`

The aborted upgrade above leaves a half-uninstalled state: the exe exists
but the package behind it is gone (pip may also warn about an "invalid
distribution ~obodog-terminal" — that's its rename-remnant folder in
site-packages; safe to delete). The same `--force-reinstall` fixes both.

### `LLM HTTP 400: invalid model ID` (or 401/402/404)

Backend/model mismatch — e.g. an OpenRouter-style `anthropic/claude-...` id
sent to `--backend openai`, or a bare `gpt-4o` sent to OpenRouter. The error
message includes the fix, and `/doctor` flags the pairing *before* any
request is sent. 401 = key rejected (check `ROBODOG_LLM_KEY` / your KeePass
entry), 402 = out of credits, 404 = wrong `ROBODOG_LLM_URL`.

### Banner shows an old version after upgrading

The window predates the upgrade, or the upgrade silently failed (see
`WinError 32` above). `pip show robodog-terminal` tells you what's actually
installed; a fresh terminal tells you what runs.

## Repository layout

```
robodog/
└── apps/cli/robodog/robodog_terminal/   Robodog Terminal — the active project
```

Full design, gap analysis, and roadmap: **`apps/cli/docs/TERMINAL_MODE_PLAN.md`**.

## Changelog

Published to PyPI as [`robodog-terminal`](https://pypi.org/project/robodog-terminal/)
(`pip install -U robodog-terminal`).

### 0.2.6

- **Add:** attributed subagent results. A fan-out used to render N identical
  `[subagent:general finished…]  (+1 lines)` rows — metadata shown, the
  child's answer hidden. Each child now gets an id, and its result renders
  as `#3 general · 2 steps · 314 tok — <the child's actual answer>`.
- **Add:** a live fan-out summary instead of per-call child spam — while
  children work the spinner reads `✳ 6 subagents working · 23 tool calls`.
- **Add:** `/verbose` — live-toggleable full output (per-child `#N` tool
  trace + untruncated tool results); `--verbose` sets the startup default.
- **Docs:** README rebuilt around real terminal screenshots (10 scenes,
  rendered by the actual UI code; `docs/screenshots/generate.py` recreates
  them so docs can't drift).

### 0.2.5

- **Fix:** streamed command output is bounded. A long `bash` run printed every
  line it produced, so one directory listing or build log buried the whole
  conversation. The trace now shows the first 15 lines, collapses runs of
  blank lines (PowerShell emits columns of them), and reports how many lines
  it held back. The model still receives the complete output — this caps the
  display only. Tune with `ROBODOG_STREAM_LINES`.
- **Add:** the status line shows the current git branch (`🌿 main`), including
  from a subdirectory, in worktrees, and as a short SHA when detached. It
  reads `.git/HEAD` directly with an mtime-keyed cache — 26µs per redraw, and
  never spawns `git` — because the toolbar repaints on every keystroke.

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
