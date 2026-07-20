# robodog-terminal

A agentic **agentic coding terminal**: a prompted tool-use loop that
reads/edits files, runs commands, runs tests, and self-corrects — over pluggable
LLM backends. Designed to run **leading models on self-hosted gateways**
(air-gapped, where an agentic coding terminal can't reach), and works equally with
OpenAI-compatible models or a fully offline mock.

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
`PATH` — use `python -m robodog_terminal`, or see the
[step-by-step setup guide](https://github.com/adourish/robodog#get-started).

Other providers (`ROBODOG_LLM_URL`) and the enterprise gateway (`GATEWAY_*`)
are covered in the [repo README](https://github.com/adourish/robodog#configuration).

## Features
Agentic loop with an intent nudge + circuit breaker · tools (read/write/edit/
multi_edit/bash/run_script/run_tests/glob/grep/list_dir) with read-before-edit,
post-edit syntax verification and fuzzy edits · foreground + background subagents
(`/bg /tasks /tail /kill`) · per-prompt checkpoints with `/rewind` · JSONL
sessions (`/resume`, `--continue`) · plan mode · encrypted KeePass key vault
(`/keepass`) · skills & custom commands
(`.robodog/`) · `CLAUDE.md`/`ROBODOG.md` hierarchy · a rich + prompt_toolkit TUI
with an emoji/color status line, clickable file & `file:line` links, multiline
paste, and mid-turn Ctrl+B backgrounding · headless `-p` (text/json) · `/doctor`.

Benchmarked at **capability parity with a leading agentic coding assistant** across 20 agentic
scenarios. See `robodogcli/docs/TERMINAL_MODE_PLAN.md` for the full design.
