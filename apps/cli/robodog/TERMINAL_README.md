# robodog-terminal

A agentic **agentic coding terminal**: a prompted tool-use loop that
reads/edits files, runs commands, runs tests, and self-corrects — over pluggable
LLM backends. Designed to run **leading models on self-hosted gateways**
(air-gapped, where an agentic coding terminal can't reach), and works equally with
OpenAI-compatible models or a fully offline mock.

## Install
```bash
pip install robodog-terminal          # or: pip install -e robodogcli/robodog
```

## Run
```bash
robodog-terminal --backend openai --model gpt-4o     # live (OpenAI/OpenRouter)
robodog-terminal --backend gateway                       # enterprise box (the gateway / leading models)
robodog-terminal --echo                               # offline demo, no keys
robodog-terminal --backend openai -p "fix x.py and run the tests"   # headless (-p)
python -m terminal.run_tests                          # 18 test suites
```

## Features
Agentic loop with an intent nudge + circuit breaker · tools (read/write/edit/
multi_edit/bash/run_script/run_tests/glob/grep/list_dir) with read-before-edit,
post-edit syntax verification and fuzzy edits · foreground + background subagents
(`/bg /tasks /tail /kill`) · per-prompt checkpoints with `/rewind` · JSONL
sessions (`/resume`, `--continue`) · plan mode · skills & custom commands
(`.robodog/`) · `CLAUDE.md`/`ROBODOG.md` hierarchy · a rich + prompt_toolkit TUI
with an emoji/color status line, clickable file & `file:line` links, multiline
paste, and mid-turn Ctrl+B backgrounding · headless `-p` (text/json) · `/doctor`.

Benchmarked at **capability parity with a leading agentic coding assistant** across 20 agentic
scenarios. See `robodogcli/docs/TERMINAL_MODE_PLAN.md` for the full design.
