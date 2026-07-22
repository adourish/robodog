# robodog-terminal

An **agentic coding terminal**: a prompted tool-use loop that reads/edits files,
runs commands, runs tests, and self-corrects — over pluggable LLM backends.
Designed to run **leading models on self-hosted gateways** (air-gapped, where the
usual agentic assistants can't reach), and works equally with OpenAI-compatible
models or a fully offline mock.

## Install
```bash
pip install -U robodog-terminal       # or, from a checkout: pip install -e apps/cli/robodog
```

## Run

The command is **dashed** (`robodog-terminal` or the short alias `robodogt`);
the Python package is `robodog_terminal` with an underscore
(`python -m robodog_terminal` also works).

```bash
robodog-terminal --backend openrouter --model anthropic/claude-sonnet-4.6  # live via OpenRouter (provider/model ids)
robodog-terminal --backend openai --model gpt-4o      # live via OpenAI directly (bare ids)
robodog-terminal --backend gateway                    # enterprise box (the gateway / leading models)
robodog-terminal --echo                               # offline demo, no keys
robodog-terminal --backend openai -p "fix x.py and run the tests"   # headless (-p)
python -m robodog_terminal.run_tests                  # test suites (from a checkout)
```

## Configure (first run)

Get a key at [openrouter.ai/keys](https://openrouter.ai/keys), then either
drop it in a config file:

```bash
mkdir -p ~/.robodog
echo "ROBODOG_LLM_KEY=<your OpenRouter key>" >> ~/.robodog/config.env
robodog-terminal             # then /doctor to verify what was found
```

…or keep it in an encrypted KeePass vault instead — no plaintext key on disk:

```bash
pip install "robodog-terminal[keepass]"
robodog-terminal
# then, at the prompt:
#   /keepass init <your OpenRouter key>     creates vault + keyfile + loader
#   /keepass                                status; /doctor to verify
```

`command not found` right after install? Your pip scripts dir isn't on
`PATH` — the exes live in `..\Scripts` **relative to the `Location:` shown by
`pip show -f robodog-terminal`** (e.g. `...\AppData\Roaming\Python\Python312\Scripts`
for a Windows user-level install). Use `python -m robodog_terminal` as a
zero-setup fallback, and see the
[troubleshooting guide](https://github.com/adourish/robodog#troubleshooting)
for PATH repair (do **not** use `setx` — it truncates long PATHs to 1024
chars), locked-exe upgrade failures, and more.

Other providers (`ROBODOG_LLM_URL`) and the enterprise gateway (`GATEWAY_*`)
are covered in the [repo README](https://github.com/adourish/robodog#configuration).

## Features

**Agentic loop** — tools (read/write/edit/multi_edit/bash/run_script/run_tests/
glob/grep/list_dir) with read-before-edit, byte-faithful writes + verify-after-
write, fuzzy edits, and syntax checks.

**Built for flaky gateways** — truncation-aware parsing (a cut-off tool call is
recovered), a capped reflection loop that re-teaches the format on a malformed
call, self-healing error hints (Windows paths, hyphenated skill dirs, `json.loads`
on a dict, a credit-limited 402 auto-retried smaller), jittered `Retry-After`
backoff, multi-format parsing (`<tool>`/`<invoke>`, `<think>` stripping, JSON tool
calls).

**Windows-smart** — auto-translates `&&`/`||`, `| head/tail/wc/grep`,
`curl`→`curl.exe`, `dir /b`, `2>/dev/null`; UTF-8 end-to-end (no mojibake).

**Safe by default** — one central guard on every code-executing tool; outward
network writes (Jira POST, `git push`, `gh pr create`) confirm and **block
fail-safe** when unattended. `/net-writes allow|deny|confirm`, or press `a` to
always-allow.

**Context & concurrency** — keep-goal/summarize-middle compaction, on-disk
freshness checks, **parallel subagents** (live progress + model-concurrency cap)
plus background subagents (`/bg /tasks /tail /kill`), a bounded never-overwhelming
trace (`/verbose` for the full feed).

**Ergonomics** — `@file`/`@folder` mentions with tab-completion · atomic
`/rewind` (files + transcript) · JSONL sessions (`/resume`, `--continue`) · plan
mode · encrypted KeePass vault (`/keepass`) · skills & custom commands with
keyword triggers (`.robodog/`, `.claude/`) · `CLAUDE.md`/`ROBODOG.md` hierarchy ·
rich + prompt_toolkit TUI (emoji/color status line, clickable `file:line`) ·
`/stats` (tokens + est. cost), `/copy`, `/save` · headless `-p` (text/json) ·
`/doctor`.

Benchmarked at **capability parity with a leading agentic coding assistant** across 20 agentic
scenarios. See `docs/TERMINAL_MODE_PLAN.md` for the full design and `ROADMAP.md`
for what's shipped/next.

## Embedding (using robodog as a library, not the CLI)

`robodog_terminal.core.build_core()` assembles the agentic core — `ToolRegistry`
+ `AgentLoop`, with hooks/skills/background/session wiring — with **no
dependency on the terminal UI or argparse**. This is the same function the CLI
entrypoint (`app.py::main()`) calls; it just also wires a `UI` and a REPL loop
on top. An embedder (a web backend, a chat bot, a test harness) can call it
directly:

```python
from robodog_terminal.core import build_core
from robodog_terminal.llm_client import EchoClient  # or GatewayClient/OpenAICompatClient

core = build_core(cwd=".", client=EchoClient())
result = core.loop.run("list the files here and summarize the project")
print(result.final_text)
```

Every UI touchpoint is an optional callback with a safe no-UI default (`ask_fn`
auto-picks the first option; `on_diff`/`on_bash_line`/`on_confirm`/`on_event`
no-op if you don't supply them — though a destructive command under
`guard="confirm"` still fails **closed**, not open, with no `on_confirm`
wired). Pass your own to hook into a different frontend:

```python
core = build_core(
    cwd=".", client=my_client,
    guard="confirm", on_confirm=lambda cmd, reason: my_approval_ui(cmd, reason),
    on_bash_line=lambda line: my_ui.stream(line),
    on_event=lambda kind, data: my_ui.render(kind, data),
)
```

See `core.py`'s `build_core()` docstring for the full parameter list. Three
extension points discovered from `<cwd>/.robodog/` (mirrored from `.claude/`
for existing Claude Code projects) come along for free in the returned
`Core.registry`/`Core.skills`:

- **`.robodog/settings.json`** (`hooks.py`) — permission allow/deny rules and
  `PreToolUse`/`PostToolUse`/`Stop` hooks, plus a `defaults` block
  (`permissionMode`/`guard`/`netWrites`) that seeds `build_core()`'s own
  defaults. Scaffold one with `/config init` in the CLI, or write it directly.
- **`.robodog/commands/*.md`, `.robodog/agents/*.md`, `.robodog/skills/<name>/SKILL.md`**
  (`skills.py`) — custom slash commands, custom subagent types, and
  keyword-triggered context injection.
- **`agents.py`**'s `AGENT_TYPES` — the built-in subagent roster (`explore`,
  `general`); `SkillsRegistry.agent_type_overrides()` merges file-defined ones
  in, and `build_core()` does this merge automatically.
