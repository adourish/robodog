# Robodog Terminal — Roadmap

Derived from a source-level deep dive of **Cline**, **Roo Code**, **Aider**,
**goose**, **OpenHands**, **Continue.dev**, and **Gemini CLI / Qwen Code**, plus
a survey of ~80 GitHub issues on prompted-tool-call failure modes with weaker /
gateway-served models. Written for robodog's real driver: an FDA OpenAI-compatible
gateway ("ELSA") serving a model that frequently mis-formats tool calls.

## The one-sentence finding

Robodog is **ahead** of Cline/Roo on *syntax* tolerance (lenient `<tool>`/`<invoke>`,
`<param>`/`<parameter>` + mismatched closes, entity unescape, fence unwrap, `\n`
decode, `<function_calls>` stripping — none of which they attempt). The gap is the
**conversational control loop *around* the parser**: recovery, truncation handling,
diagnostic errors, loop-breaking, context management, gateway resilience. Plus one
principle every safety incident repeated — **"an instruction is not a guardrail"** —
which validates the network-write guard we just shipped and points to more
structural (not prompt-level) safety.

Legend: ✅ done · 🟡 partial · ⬜ not started. Effort: S/M/L.

---

## Phase 1 — Reliability core (highest ROI for the ELSA model)

Every client converged here. This is what turns "mis-formatted → dead turn / infinite
loop / burned tokens" into "mis-formatted → auto-recovered."

### 1.1 ✅ Reflection / consecutive-mistake loop  · M · *shipped 0.3.26*
The single most-cited win (Aider `base_coder.run_one`, Cline/Roo `consecutiveMistakeCount`).
A uniform channel: parse failure, missing required param, edit-apply failure, (later) lint/test
failure all collapse into "one more turn, with this exact text as the next user message,"
capped at ~3 per user request, counter reset per user message, then **stop and ask the human**
(don't loop forever — Aider #770/#2385, Cline #5342/#735).
- Robodog: add `reflected_message` + `consecutive_mistakes` to `loop.py`'s turn driver.
- The correction text must (a) be labeled `[ERROR]`, (b) **re-embed the tool-format spec**
  (models forget it 100k tokens back — Cline re-injects at point of failure), (c) end with
  "this is an automated message, do not respond conversationally" (prevents apology loops).

### 1.2 ✅ Truncation-aware parsing  · S · *shipped 0.3.26*
The most robodog-relevant issue found (Cline #9920): at high context ELSA truncates
*mid-tool-tag*, robodog would see "no tool" and retry → permanent stall.
- Detect `finish_reason == "length"` **or** an unclosed `<tool>`/`<param>` at end of text.
- Treat as a distinct state: re-prompt for *just* the tool call, or raise `max_tokens` /
  compact — **never** classify as "no tool used." (`llm_client.py` + `toolcall.py`.)

### 1.3 ✅ Diagnostic, schema-carrying tool errors + fuzzy tool-name match  · S · *shipped 0.3.26*
Robodog already does this for shell/import/edit hints. Extend to the parser layer:
on unknown/misspelled tool name (`write_file` vs `write_files` — Roo #4530, opencode #13317)
return the valid tool list + a `difflib` "did you mean"; on missing required param, name it and
re-embed the format. Never crash the session on an unknown tool.

### 1.4 🟡 Tool-result framing  · S · *empty-result naming (0.3.26) + echo-back present; <error>/<feedback> wrappers TODO*
Cline/Roo §5. Cheap, high-leverage for a no-native-tool-API loop:
- Echo the call back: `[read_file for 'src/main.py'] Result:\n…` (substitutes for a
  `tool_use_id`, re-anchors which call the result belongs to).
- Empty result → the literal `(tool did not return anything)`, never "" (Roo PR#9325:
  empty results caused an infinite loop).
- Wrap failures in `<error>…</error>`, user denials/feedback in `<feedback>…</feedback>`,
  and **ship the recovery material in-band** (e.g. failed edit returns the closest actual lines).

### 1.5 ⬜ Loop / repetition breaker  · S
Hash the last N tool calls; on repeated identical (or identical-*failing*) calls, inject
"you are repeating yourself; the error was X; try a different approach" and hard-stop to the
user (Roo #3198, opencode #21850, claude-code #29944 — even strong models do this). Pairs with 1.1.

### 1.6 🟡 One-tool-per-message policy  · S
Robodog currently executes all parsed tool calls in a turn. Cline/Roo enforce **one**, because
call #2 can't know call #1's result (stale-state hazard). Decide: either run strictly in order
and stop on first failure (low-risk default), or adopt Cline's "execute first, tell the model the
rest were ignored, re-issue them." Enforce in `loop.py`, not just the prompt.

---

## Phase 2 — Context & correctness

### 2.1 🟡 Token accounting + threshold auto-compaction  · M · *keep-first/middle/recent compaction shipped 0.3.28; per-model token accounting still TODO*
Robodog has manual `/compact` + char-based trimming. Upgrade (goose 80%-threshold +
OpenHands condenser):
- Real token accounting vs the model's context limit (per-model override).
- Auto-compact at a configurable fraction (default ~0.8); summarize with the summary
  **schema**: goals / progress / remaining work / critical files / failing tests.
- Tier it: summarize old *tool outputs* first (cheap), full-history summary second.
- **Compact rarely, in big chunks** (cache-aware) and **keep_first K** (system + initial ask).
- After every compaction, **re-inject** the system prompt + tool schemas + durable skills
  (Roo #4530: instruction/tool-name decay after condensation). Validate the summary actually
  shrank tokens; fail loud (Roo #10781: silent condense failure = permanent stall).

### 2.2 🟡 Files-always-fresh + read-before-edit freshness  · S
Robodog enforces read-before-edit. Add the freshness half (aider #2864, Roo #2347/#1891,
claude-code #28383): store mtime/hash at read; on edit, if the file changed since, force a
re-read instead of writing from a stale mental copy. Optionally re-inject current contents of
in-context files each turn so history never carries a stale version.

### 2.3 ✅ Hard output caps entering context  · S · *universal via _clamp head+tail + [truncated N] markers*
Robodog clamps some output. Make it universal + explicit: every `read_file` / command stdout
gets head+tail truncation with a visible `[truncated N bytes]` marker *before* it enters the
transcript (Cline #4576/#4419; Roo #4186 — an oversized file wiped the whole task).

### 2.4 ✅ Multi-format tool extraction  · M · *<think> stripping (incl. leaked-no-opener) + JSON-tool fallback shipped 0.3.29*
ELSA may switch formats. Accept, in priority order: robodog XML → native `tool_calls` field →
JSON-in-content → tool calls inside `reasoning_content`/`<think>` (cline #10843/#8365,
llama.cpp #12107). **Strip `<think>…</think>` before parsing**, even when the opening tag is
missing, and scan the reasoning channel as a fallback.

### 2.5 ✅ Edit failure-message shape  · S · *closest-line + already-applied idempotency shipped 0.3.28 (atomic multi_edit = no 'other N')*
When an edit doesn't apply, return (Aider `SearchReplaceNoExactMatch`): the closest actual
lines, "the other N blocks applied — only resend the failures," and an "these REPLACE lines are
already present" idempotency note (catches double-application on retries). Robodog already has
`edit_not_found_hint`; extend it with the "other N applied / already-present" parts.

---

## Phase 3 — Gateway resilience (ELSA-specific)

### 3.1 🟡 Timeout / backoff / retry budget  · M · *Retry-After honoring + jittered backoff shipped 0.3.30; global cross-call retry budget still TODO*
Robodog auto-sets a long timeout for custom gateways. Add (cline #2941/#713, Roo #1539):
jittered exponential backoff honoring `Retry-After`; a **global** retry budget so a retry storm
can't run all night; distinguish "no first token yet" from "stream stalled mid-response."

### 3.2 🟡 Response-shape resilience  · M · *garbled-200 retry + finish_reason-independent tool detection shipped 0.3.31; SSE-sniff/non-streaming-fallback N/A (robodog is non-streaming)*
OpenAI-compatible proxies lie. Defenses (litellm #17246/#19744/#25766, vllm #31871):
- Never key tool detection off `finish_reason` alone — inspect the accumulated message.
- On empty/garbled/unterminated stream with substantial content, **parse what arrived**
  rather than discarding; retry once **non-streaming** as a fallback before erroring.
- Sniff content-type (some endpoints return SSE even for `stream:false`).

### 3.3 ⬜ Prefill continuation on truncation  · M
When `finish_reason=length` and the model supports assistant prefill (many gateways do),
re-send the partial as a trailing assistant message with `prefix=true` and continue — seamless
long file writes (Aider §6). Complements 1.2.

---

## Phase 4 — Safety hardening (continue the structural work)

The Jira incident was not unique: Replit wiped a prod DB during a code freeze then faked data
to hide it (AI Incident DB #1152); Gemini CLI deleted a user's files after a failed `mkdir`
(#4586); Gemini `git push --force`'d to remote unprompted (#5894). Every post-mortem's fix was
*structural*, never "better prompting."

### 4.1 ✅ Central danger + network-write guard (fail-safe default)
Shipped 0.3.23–0.3.25: one checkpoint in `execute()`, every tool guarded by default, network
writes confirm-or-block, `run_script`/`run_tests` covered.

### 4.2 ⬜ Verify-after-mutate  · S
The exact missing step in the Gemini deletion: after a filesystem mutation, do a cheap
existence/content check before any *dependent* destructive step. And a "task complete" tool
should require evidence (a re-read, an exit code, a test result) before robodog accepts it
(cline #8354/#9848: hallucinated completion).

### 4.3 ⬜ Persistent learned permissions  · S
Robodog *reads* `settings.json` permissions; make the confirm flow **write** them — "always
allow this" persists a rule so the same action never re-asks (Continue CLI's approve-once model).

### 4.4 ✅ Treat outward-facing git as network-class  · S · *git push / gh pr|issue|release create|merge|close guarded, shipped 0.3.31*
`git push --force`, `git push` to a remote, PR/issue creation → route through the network-write
guard, not just the local danger list (Gemini #5894). Small addition to `classify_*`.

### 4.5 ⬜ (optional) LLM risk-grader tier  · M
Between "confirm everything" and YOLO: a cheap LLM classifier tags each mutating call
LOW/MED/HIGH and only HIGH confirms (goose `PermissionJudge`, OpenHands `LLMSecurityAnalyzer`).
Falls back to the deterministic guard we already have.

---

## Phase 5 — Ecosystem & ergonomics

### 5.1 ⬜ MCP client support  · M · **biggest ecosystem unlock**
All four surveyed tools support it; goose/Continue are built on it. The official `mcp` Python
SDK gives the client side (stdio + HTTP, `list_tools`/`call_tool`). Since robodog already has a
tool table and reads `.claude` settings (where `mcpServers` conventionally live), MCP tools just
become dynamically-registered entries — weekend-scale, not a rearchitecture. Every MCP server
(GitHub, Postgres, browsers, Slack…) becomes a robodog tool for free. **Note:** MCP tools are
network-capable → they must default to `executes=True` and pass the 4.1 guard.

### 5.2 🟡 `@file` / `@folder` mentions + tab-complete  · S
Robodog has `@`-mention expansion; make sure it covers folders and has REPL tab-completion.
Table-stakes ergonomics (universal across Continue/Gemini/Qwen).

### 5.3 ⬜ `/stats` — token + cost surface  · S
Per-session tokens, context-window %, cost, cached-token savings, duration (Gemini `/stats`).
High-trust, and it's a **prerequisite for 2.1's threshold trigger** (you need window accounting).

### 5.4 🟡 Headless `-p` mode  · S
Robodog has `-p`; confirm it prints only the final answer to stdout for pipes/CI/git-hooks
(Continue `cn -p`), and that in headless mode network writes hard-block (already true via 4.1).

### 5.5 ⬜ Keyword-triggered skill injection  · S
Robodog discovers `.claude`/`.robodog` skills. Add OpenHands-style frontmatter
`triggers: [k8s, kubernetes]` so a skill loads into context **only** when the user's message
matches — conditional context injection almost for free, reduces bloat (synergy with 2.1).

### 5.6 🟡 Shadow-git checkpoint + atomic file+transcript restore  · M
Robodog has checkpoint/rewind. Upgrades (Gemini CLI): snapshot into a *shadow* git repo
(handles untracked/multi-file states, free diff/GC, isolated from the user's repo); restore
files **and** rewind the transcript together so undo is atomic across both.

---

## Phase 6 — Bigger bets (later)

- ⬜ **Repo map** (Aider `repomap.py`) · L — tree-sitter/ctags defs + a sqrt-weighted reference
  graph + `networkx.pagerank` personalized on chat/mentioned files + binary-search-to-token-budget.
  Do the ctags-based v1 before the tree-sitter version.
- ⬜ **Streaming presenter** · L — `partial` flag gating execution, cursor presenter,
  trailing-partial-tag stripper. Pairs with the planned terminal streaming mode (Cline §2).
- ⬜ **Auto-lint (fatal-only) + auto-test into the reflection loop** · M — flake8 restricted to
  fatal codes (`E9,F821,…` — never style nits, or the loop ping-pongs) + tree-sitter ERROR-node
  fallback + `█`-marked context; wire into 1.1 with checkpoint-before-fix (Aider §4).
- ⬜ **git-worktree task isolation → optional `--sandbox` container** · L — cheap git-native
  isolation first (Qwen Code), Docker later (OpenHands); couple YOLO ⇒ sandbox (Gemini CLI).

---

## Explicit non-goals

- **No embeddings / RAG codebase index.** Continue.dev built the best-in-class version
  (MiniLM + LanceDB + tree-sitter + reranker) and **deprecated it** in favor of agentic grep +
  rules files. Robodog already has glob/grep/read — agentic search won. (Continue "deprecated-codebase".)
- **No true XML depth-parsing of nested same-name tags.** Roo explicitly declined it (#4426,
  closed not-planned); the closed-tag-vocabulary + `lastIndexOf`-outer-bounds approach (below)
  covers the practical cases at far lower complexity.

---

## Cross-cutting parser upgrade (informs Phase 1)

Cline/Roo's parser is **not** an XML parser — it's a scanner over a **closed vocabulary** of the
actually-registered tool/param names; any unknown tag is inert text (so `<div>` in prose can
never be mistaken for a tool). For the one designated "content" param (file bodies that may
themselves contain `</content>`), they re-extract greedily between `indexOf("<content>")` and
**`lastIndexOf("</content>")`** anchored by the tool's close tag. Robodog's regex parser is more
lenient on malformed tags but could adopt the `lastIndexOf` outer-bounds trick for `write_file`
content to survive files that contain the close-tag string. (Cline v3.75.0 `parse-assistant-message.ts`.)

---

## Suggested build order (dependency-aware)

1. **1.2 truncation-aware** + **1.1 reflection loop** — 1.1 is the substrate that makes 1.3–1.6,
   2.5, and Phase-6 lint/test *recoverable* instead of fatal.
2. **1.4 result framing** + **1.3 diagnostic errors** + **1.5 loop breaker** — all feed the loop.
3. **3.1/3.2 gateway resilience** — ELSA reliability; independent, parallelizable.
4. **2.1 context accounting/compaction** (+ **5.3 /stats** falls out of the same work).
5. **4.2–4.4 safety** — quick structural wins on top of 4.1.
6. **5.1 MCP** — the ecosystem unlock, once the loop is solid.
7. Phase 6 as capacity allows.

*Last updated: 2026-07-20. Sources: source-level reads of Cline v3.75.0 / Roo v3.40.0 parsers,
Aider `base_coder`/`editblock_coder`/`repomap`, goose & OpenHands context/permission docs,
Gemini CLI checkpointing, and ~80 linked GitHub issues across cline/Roo/aider/continue/goose/
llama.cpp/vllm/ollama/litellm.*
