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

## Config file (`.robodog/settings.json`)

Scaffold one with `/config init` (writes to `<cwd>/.robodog/settings.json`; add
`--global` for `~/.robodog/settings.json`, `--force` to overwrite). `/config`
with no argument shows the effective config and which files were actually
loaded.

### Where robodog looks, and which one wins

Four locations are merged, **in this exact order**:

```
1. <cwd>/.robodog/settings.json   (highest priority)
2. <cwd>/.claude/settings.json
3. ~/.robodog/settings.json
4. ~/.claude/settings.json        (lowest priority)
```

`.claude/settings.json` is read too so an existing Claude Code project's
settings work unchanged. Missing files are just skipped — you only need the
one(s) you actually want.

**How "winning" works depends on the field type:**
- `permissions.allow` / `permissions.deny` — **concatenated**, not overridden.
  Every rule from every file that exists applies; there's no way for a user-level
  file to "cancel" a project-level rule (deny always wins over allow regardless
  of which file either came from — see below).
- `hooks.*` — also **concatenated**; project hooks run before user hooks.
- `defaults.*` — **scalar, first file wins**. If both `<cwd>/.robodog/settings.json`
  and `~/.robodog/settings.json` set `"guard"`, the project one is used and the
  user one is silently ignored for that key (not merged, not an error).

### Every line, what it does

```jsonc
{
  "defaults": {
    "permissionMode": "yolo",   // "yolo" | "plan" — startup permission mode.
                                // A CLI --permission-mode flag always overrides
                                // this. Anything other than exactly "plan" is
                                // silently treated as "yolo" — a typo here is
                                // harmless (falls back to the default), not an error.
    "guard": "warn",            // "warn" | "confirm" — destructive-command handling.
                                // A CLI --guard flag always overrides this.
                                // ⚠ NOT VALIDATED: any value other than the exact
                                // string "confirm" behaves like "warn" (no
                                // confirmation is EVER asked). A typo like
                                // "confirmm" silently disables the safety prompt
                                // instead of erroring — this is the one field in
                                // this file where a mistake fails UNSAFE, not safe.
    "netWrites": "confirm",     // "confirm" | "deny" | "allow" — outward-facing
                                // network writes (POST/PUT/DELETE to a remote API,
                                // e.g. closing a Jira ticket, `git push`).
                                // A CLI --net-writes flag or $ROBODOG_NET_WRITES
                                // always overrides this. Unlike "guard" above,
                                // an unrecognized value here fails SAFE — anything
                                // that isn't exactly "allow" or "deny" is treated
                                // as "confirm" (asks before proceeding).
    "verifyEdits": true         // Scaffolded by `/config init` but NOT YET READ —
                                // only the --no-verify-edits CLI flag controls
                                // post-edit syntax verification today. Known gap;
                                // this key is currently a no-op placeholder.
  },
  "permissions": {
    "allow": ["bash(git *)", "read_file(*)"],   // "tool" or "tool(glob)".
    "deny":  ["bash(rm -rf *)", "write_file(*.env)"]
                                // The glob is fnmatch-style, matched against the
                                // call's primary argument (command for bash/
                                // run_script, path for file tools, prompt for the
                                // agent tool). A `command` value is split on
                                // top-level && / || / ; / | FIRST (quote-aware) —
                                // deny fires if ANY segment matches; allow only
                                // fires if EVERY segment matches an allow rule.
                                // So `allow: ["bash(git *)"]` does NOT bless
                                // `git status && rm -rf ~` as a whole.
  },
  "hooks": {
    "PreToolUse":  [{"matcher": "bash|run_script",     // regex, fullmatched
                                                        // against the tool name.
                                                        // Empty/absent = every tool.
                     "command": "python lint_gate.py", // runs via the shell, cwd
                                                        // = the project root. Gets
                                                        // a JSON payload on stdin:
                                                        // {event, tool_name,
                                                        //  tool_input, cwd}.
                     "timeout": 30}],                  // seconds; default 30 if
                                                        // omitted.
    "PostToolUse": [{"matcher": "write_file|edit_file",
                     "command": "npx prettier --write ."}],  // same payload +
                                                              // tool_result.
    "Stop":        [{"command": "notify-send 'robodog turn done'"}]
                     // no matcher (Stop fires once per finished turn, not per tool)
  }
}
```

### What happens when something's wrong — the exact order things fail in

Nothing here ever crashes startup or the agent loop. Failures degrade in this
order, from "whole file ignored" down to "one call proceeds instead of being
gated":

1. **A settings.json file has invalid JSON** → that ONE file is skipped
   entirely (logged as a warning), the other three still load normally.
2. **A permission rule string doesn't parse** (doesn't match `tool` or
   `tool(glob)`) → that individual rule is silently dropped; the rest of the
   list still applies.
3. **A hook's `matcher` is an invalid regex** → that hook is skipped for
   matching purposes (logged), other hooks still run.
4. **A hook command fails to spawn, or times out** (default 30s, or the
   hook's own `"timeout"`) → treated as non-fatal and logged; a broken
   `PreToolUse` hook does **not** block the call — it just doesn't run.
5. **A `PreToolUse` hook exits non-zero but not exactly `2`** → logged as a
   warning and the call proceeds. **Only exit code 2 blocks** (its stderr
   becomes the block reason shown to the model).
6. **A `defaults.*` value is malformed** (typo, wrong type) → see the
   per-field notes above; `permissionMode` and `netWrites` fail toward the
   safe default, `guard` is the one exception that fails toward *less* safety
   (an unrecognized value behaves like `"warn"`).

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

## How robodog compares

Criteria most relevant to picking an agentic coding tool. The 8 open-source columns
come from a **source-level read** of each project (see `ROADMAP.md` for citations).
**Claude Code is closed-source** — its column reflects documented/observed behavior
from actual usage, not code I could read, so treat it as less rigorously verified
than the other 9. ✅ full support · 🟡 partial · ❌ not found/not present.

| Criteria (why it matters) | **robodog** | Cline | Roo Code | Aider | goose | OpenHands | Continue | Gemini CLI | Qwen Code | Claude Code |
|---|---|---|---|---|---|---|---|---|---|---|
| **License** | **MIT** | Apache-2.0 | Apache-2.0 | Apache-2.0 | Apache-2.0 | MIT | Apache-2.0 | Apache-2.0 | Apache-2.0 | **proprietary** |
| **Primary interface** | **CLI** | VS Code ext | VS Code ext | CLI | CLI (Rust) | CLI/SDK/web | VS Code ext + CLI | CLI | CLI | CLI + IDE + desktop + web |
| **Windows command translation** — rewrites Unix-isms (`grep`, `dir`, `2>nul`, pipe filters) instead of just hoping the model writes native syntax | **✅** most extensive found | ❌ | ❌ | ❌ | ❌ (prompts native syntax) | ❌ (native Windows backend instead) | ❌ | ❌ | ❌ | 🟡 some translation/hints observed, narrower than robodog's ~20+ patterns |
| **Persistent shell session** — avoids a fresh process spawn (~0.75-1s) per command | **✅** | 🟡 VS Code terminal reuse only | 🟡 VS Code terminal reuse only | ❌ | ❌ | ✅ tmux (Linux) + native PowerShell reader (Windows) | ❌ | ❌ | ❌ (has ConPTY option) | ✅ documented persistent session |
| **Compound-command permission splitting** — an `allow`/`deny` rule matches per `&&`/`;`/`\|` segment, not the whole line | **✅** | ❌ | ✅ (matching only, not exec) | ❌ | ❌ | ❌ | ❌ | ✅ real AST parsing | ✅ | 🟡 has prefix-based permission matching; exact mechanism unverifiable |
| **Risk-tiered danger classification** — not everything destructive needs the same confirm | **✅** deterministic 3-tier — HIGH-risk (`rm -rf`, `git reset --hard`, `git push --force`, …) always confirms in *every* guard mode, not just when explicitly opted into | ❌ | ❌ (allow/deny only) | ❌ | ✅✅ regex + optional ML | 🟡 LLM classifier | ❌ | ❌ | ❌ | 🟡 ask/allow/deny prompting, not a verified explicit tier system |
| **Windows process-tree kill** (`taskkill /T /F`, not just the parent) | **✅** | ✅ | 🟡 | ❌ | 🟡 | 🟡 | ❌ | ✅ | ✅ | 🟡 unverifiable (closed-source) |
| **Long-running command UX** — hard-kill vs. a non-killing "still alive" signal | **🟡 idle-note (non-killing)** | hard timeout / detach | dual timeout | ❌ no timeout at all | timeout + cancel | ✅✅ soft-timeout, model can poll/interrupt | idle-reset timeout | idle-reset timeout | timeout + bg-promote | ✅ timeout + backgrounding (Ctrl+B) |
| **MCP client support** | **❌ not yet** | ✅ | ✅ | ❌ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| **Sandbox/container isolation** | **❌ not yet** | ❌ | ❌ | ❌ | ❌ | ✅✅ Docker | ❌ | ✅ Docker/podman/seatbelt | ✅ (same as Gemini) | 🟡 permission modes; OS-level sandboxing unverifiable |
| **Embeddable as a library** (no-UI core, usable outside the CLI) | **✅✅ `build_core()`** | ❌ | ❌ | 🟡 | ❌ (Rust binary) | ✅ SDK-first | 🟡 headless `cn` | ❌ | ❌ | ✅ Claude Agent SDK (separate product, not the CLI itself) |
| **Config file** (permission rules + hooks) | **✅** `.robodog/settings.json` | ✅ | ✅ | 🟡 | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ `settings.json` (robodog's own `hooks.py` deliberately mirrors this) |
| **Customizable color themes** | **✅✅** 4 incl. pip-boy | IDE theme | IDE theme | ❌ | ❌ | N/A | IDE theme | ✅ | ✅ (inherited) | 🟡 light/dark, not arbitrary custom palettes |
| **Loop/repetition breaker** — detects the model repeating the same (or same-failing) tool call and intervenes instead of looping forever | **✅** counter-based (consecutive-failure + identical-call-repeat thresholds); functional but less sophisticated than the content/LLM-judged detectors below | ✅ `LoopDetectionTracker` soft/hard thresholds + mistake counter (PR #9933); not uniform across all surfaces — open #12293 shows 30+ identical retries observed on one | ✅ `ToolRepetitionDetector` (canonical-hash) + configurable mistake counter, pauses for human input (fixed via #3240) | 🟡 hardcoded 3-reflection cap, not repeat-specific detection — open #2385 asks for a real one | 🟡 `RepetitionInspector` exists in code but is a no-op today — the only production call site never sets a limit | ✅ `StuckDetector` — 5 pattern types (repeat action+observation/error, monologue, alternation, context-loop), halts the turn | ❌ no mechanism at all; open, unresolved #12702 reproduces exactly this | ✅✅ 3 layered mechanisms incl. an LLM-judged semantic loop check every N turns | ✅✅ even more elaborate than its own Gemini CLI fork base, tuned against DashScope repetitive-call behavior (#5019) | 🟡 unverified (closed-source) |
| **Read-before-edit freshness check** — refuses/forces a re-read if the file changed on disk since the model last saw it, instead of silently overwriting a stale in-context copy | **✅** explicit mtime tracking per read path; edit is refused and a re-read is forced if the file changed since | 🟡 a `FileContextTracker` exists but isn't wired into the current edit path; protection is implicit (the old text must still match) | 🟡 issues #2347/#1891 closed without fixing it; advisory "recently modified" notice only, not enforced for a full overwrite | ❌ no mtime/hash tracking found; open #2864 confirms the gap | ❌ no tracking found; only re-reads fresh at write time (implicit-only) | 🟡 re-reads + exact-match protects against silent overwrite, but no explicit mtime/hash or proactive staleness warning | 🟡 gates on "has this path been read at all," not "has it changed since" — no mtime check | 🟡 hash comparison exists only in the self-correction retry path, not a general freshness ledger | ✅✅ mtime+size+inode tracking with TOCTOU-safe checks at 3 points (pre-read, post-read, pre-write) — more thorough than robodog's | 🟡 unverified (closed-source) |
| **Checkpoint/rewind — atomic file + conversation restore** — undoes file edits AND the conversation together, not just one or the other | **✅** atomic file+transcript restore (shipped 0.3.34); no shadow-git backing store yet | ✅ `restoreCheckpoint()` restores both by default (independently toggleable); against the real `.git`, not an isolated shadow repo | ✅ `checkpointRestore()` — shadow-git file revert + message rewind in one call ("Restore Files & Task") | ❌ `/undo` only reverts the git commit; chat history untouched — open #2554 asks for the combined version | ❌ attempted twice (PRs #3040/#3493), abandoned; maintainers now tell users to do it manually via `git commit` | ❌ conversation fork/navigate exists, but the workspace is shared unchanged across forks — no file snapshot tied to rewind | ❌ no native mechanism; the only "checkpoint" hit shells out to an optional external tool just for commit attribution | ✅✅ isolated shadow-git repo (its own `GIT_DIR`, never touches the user's real `.git`) + full conversation history restored together | 🟡 diverged to a custom per-file snapshot system; restores both but sequentially, not truly atomic | 🟡 unverified (closed-source) |
| **Subagent default privilege** — a delegated subagent defaults to read-only, not full write/execute, unless the caller explicitly opts in | **✅✅** defaults to `type=explore` (read-only); write/execute requires an explicit `type=general` opt-in — fixed 0.3.73 after a subagent given a read-only-sounding task raced an uncoordinated write against the parent session | 🟡 both delegation paths (`spawn_agent`, named YAML agents) inherit the parent's current mode/full unrestricted tool set by default | 🟡 delegated task gets full privileges of whichever mode the LLM picks (usually "code" = read+write+exec); no delegation-aware restriction layer exists | 🟡 "Architect" sub-coder is a fixed two-phase pipeline, not general delegation — its whole job is writing files, always full access | 🟡 subagent inherits *all* the parent's enabled extensions unless the caller filters them; sandboxed read-only delegates are a proposed, unshipped discussion (#7159) | 🟡 `permission_mode` defaults to `None` → inherits the parent's own default (`NeverConfirm`, i.e. no confirmation, full auto-execute) | 🟡 code explicitly grants all-tools-allowed by default with an inline `// todo` acknowledging the gap; no built-in restricted preset shipped | 🟡 subagents inherit all tools unless `tools:` frontmatter restricts them — same unsafe default robodog itself shipped with before 0.3.73 | 🟡 defaults to `AUTO_EDIT` (auto-approves writes, no confirm) unless the parent session itself is in `PLAN`/strict mode | 🟡 unverified (closed-source) |
| **Garbled/truncated model-response resilience** — recognizes a response cut off mid-tool-call and retries, rather than misreading it as a final answer or silently executing a corrupted call | **✅** detects `finish_reason=="length"` or an unclosed tag and re-prompts for just the tool call, capped against infinite retry | ✅ normalizes truncated finish reasons to a canonical state and raises a distinct, correctly-labeled error — doesn't auto-continue inline, though | ❌ only checks for `"tool_calls"` finish reason; on malformed/incomplete tool-call JSON it explicitly forces the call through as non-partial and executes it anyway, catching problems only via generic param validation afterward | ✅ raises a dedicated exception on `finish_reason=="length"`; malformed edit blocks are caught and trigger an automatic reflection retry, never silently applied | ❌ not detected anywhere in the provider layer; two real bugs confirm it (#7239: truncation misread as a parse error; #8167: cutoff surfaces as raw "EOF while parsing a string") | 🟡 malformed tool-call JSON is caught and corrected, and an empty response triggers a nudge — but nothing inspects `finish_reason` itself, so prose truncated by length is treated as a normal final message | ❌ JSON parse failures on tool-call arguments are silently swallowed; a truncated call proceeds with empty/partial args rather than being flagged incomplete | 🟡 detects truncation and warns the user, but doesn't auto-retry — the turn is still treated as final; a separate open issue shows some configs get no warning at all | ✅✅ detects truncation even when the provider omits `finish_reason: "length"` (via streaming JSON depth-tracking), auto-retries with an escalated token ceiling, and explicitly rejects a truncated write with chunking guidance | 🟡 unverified (closed-source) |
| **Session persistence / resume** — a conversation's full state can be saved to disk and resumed by ID/reference after the process restarts | **✅** JSONL sessions, `/resume`, `--continue` | ✅ resume-by-ID on disk, both the VS Code extension and CLI surfaces | ✅ full history reload by task ID from disk, backing the task-history sidebar | 🟡 `--restore-chat-history` genuinely reconstructs the LLM-facing conversation state, but it's one implicit file per working directory — no session-ID system for multiple named sessions | ✅ SQLite-backed session store, resume by name/ID after restart | ✅ persistent, file-store-backed event log keyed by conversation ID, with an explicit resume-after-restart API | 🟡 exists (`cn ls`/`--resume`) but confirmed broken for selecting a specific non-latest session by ID (open #12927 — always loads the newest file instead) | ✅ `/chat save\|resume\|list\|delete <tag>`, distinct from its checkpoint/revert feature | ✅✅ full session service — per-session JSONL, `--continue`/`--resume` with title search, session forking, and crash-recovery detection | 🟡 unverified (closed-source) |

**What robodog covers that most others don't:** Unix→Windows command *rewriting*
(the rest either prompt the model to use native syntax or, like Claude Code, do
narrower translation) — the only one in the table with a Python-native,
explicitly-embeddable core (`build_core()`) built for that from day one, not
retrofitted — and 4 switchable themes vs. everyone else's IDE-inherited or
none.

**robodog's real gaps** — the two rows below are the honest answer to "what's
missing": every other tool in this table (including Claude Code) has MCP;
robodog doesn't yet (`ROADMAP.md` Phase 5.1, the single biggest ecosystem
unlock available). Sandbox/container isolation is the second gap — OpenHands
(Docker) and Gemini CLI/Qwen Code (Docker/podman/seatbelt) have real
process-level isolation; robodog has permission gating but no execution
sandbox yet (`ROADMAP.md` Phase 6). Its long-running-command UX (idle-note) is
also a notch behind OpenHands' true soft-timeout-with-polling — informational
only, doesn't let the model interactively poll or send input mid-command.

**Two more honest gaps, from a fresh source-level pass (2026-07-22):**
robodog's loop-repetition breaker and read-before-edit freshness check both
work and are genuinely enforced — but Gemini CLI and Qwen Code's are more
advanced on both fronts. Gemini CLI layers three detection mechanisms
including an LLM-judged semantic loop check; Qwen Code goes further still,
purpose-tuned against real DashScope repetitive-call failures. On freshness,
Qwen Code's `priorReadEnforcement.ts` checks mtime *and* size *and* inode at
three separate points (pre-read, post-read, immediately pre-write) — robodog's
single mtime comparison is real protection but a narrower one. Where robodog
holds up well is checkpoint/rewind: its atomic file+transcript restore matches
Cline's and Roo Code's (both real, working, if not shadow-git-isolated like
Gemini CLI's) and is well ahead of Aider (file-only), goose (abandoned
attempts), OpenHands (conversation and files are decoupled), and Continue.dev
(no native mechanism at all).

**A genuine standout, from the same pass:** robodog is the only tool in this
table whose subagent delegation defaults to read-only. All 8 open-source
tools surveyed have a working delegation/subagent mechanism, and every
single one defaults to full or inherited write/execute access — several
with the gap explicitly acknowledged in their own source (Continue.dev's
executor has an inline `// todo` about it; goose has an open discussion
proposing sandboxed delegates that don't exist yet). Gemini CLI's default
is the same shape of bug robodog itself shipped with before 0.3.73 — a
subagent inherits everything unless a `tools:` field explicitly restricts
it. On truncated-response resilience robodog holds a solid, working
detect-and-retry approach, on par with Cline and Aider, and ahead of Roo
Code (which detected malformed truncated JSON but explicitly forces the
call through anyway), goose, and Continue.dev (neither handles it at
all) — though Qwen Code's is more advanced still, auto-retrying with an
escalated token ceiling rather than just re-prompting. Session
persistence is a fully solved problem across most of this table,
robodog included; Qwen Code's is the most feature-rich (forking,
crash-recovery), and Continue.dev is the one with a confirmed, currently
open bug in exactly this feature.

**On Claude Code specifically:** it's the most feature-complete tool in this
table overall (widest interface surface, MCP, an Agent SDK, a real settings
file) — but "covers everything robodog does" isn't quite accurate: robodog's
Windows command-*rewriting* is more extensive than what's been observed from
Claude Code, and Claude Code doesn't ship an embeddable no-UI core the way
`build_core()` is — the Agent SDK is a related but separate product, not the
CLI's own internals made importable. Being closed-source also means several
rows above are inherently unverifiable rather than confirmed, which is a real
asymmetry against the 8 tools whose source I could actually read.

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
