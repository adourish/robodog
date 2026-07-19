# Robodog — monorepo

Robodog is a family of generative-AI clients. Active development is focused on
the **agentic coding terminal** (Claude Code-style) in `apps/cli`. Older
iterations are kept, read-only, under `archive/`.

## Layout

```
robodog/
├── apps/
│   └── cli/            Python CLI + robodog_terminal   ← 🟢 ACTIVE / flagship
├── integrations/       one-off automation scripts (Google, email, Todoist,
│                       Amplenote, SharePoint, MCP demos) that call CLI services
├── docs/               integration & setup guides, test-result notes
├── assets/             screenshots, slide deck, PDF, diagram, sample data
└── archive/            unmaintained iterations, kept for history (read-only)
    ├── web/            React/TypeScript web client (robodog)  — last 2025-11
    ├── lib/            shared JS services (robodoglib)         — last 2025-11
    ├── batch/          batch tool (robodogbatch)              — last 2025-07
    ├── android/        Android wrapper (robodogandroid)        — last 2024-11
    └── vscode/         VS Code extension (robodogvscode)       — last 2024-06
```

## The flagship — Terminal Mode (`apps/cli`)

A Claude Code-style agentic coding terminal: a prompted tool-use loop that
reads/edits files, runs commands, runs tests, and self-corrects — over pluggable
LLM backends. Built to run **Claude Sonnet on the FDA ELSA/SEMOSS gateway**
(air-gapped, where Claude Code can't reach), and works with OpenAI-compatible
models or a fully offline mock.

```bash
cd apps/cli/robodog
pip install rich prompt_toolkit requests

python robodog_terminal/app.py --backend openai --model gpt-4o   # live
python robodog_terminal/app.py --echo                             # offline demo
python robodog_terminal/run_tests.py                              # 18 test suites
```

Installed (first-class): `pip install -e "apps/cli[terminal]"` then
`robodog-terminal …` / `robodog terminal …` / `python -m robodog.robodog_terminal`.

Full docs, design, and roadmap: **`apps/cli/README.md`** and
**`apps/cli/docs/TERMINAL_MODE_PLAN.md`**.

## Archived iterations

Everything under `archive/` is retained for reference but no longer maintained.
The web client and its shared JS lib (`archive/web`, `archive/lib`) still build
from source if needed; the Android app and VS Code extension are historical.

---
*Legacy per-package READMEs live inside each directory.*
