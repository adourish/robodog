# Analysis of Alternatives — LLM Agentic Coding Clients
**Document type:** Analysis of Alternatives (AOA)
**CMMI Practice:** Decision Analysis and Resolution (DAR)
**Version:** 1.0
**Date:** 2026-07-23
**Status:** Draft
**Author:** FDA ORA/SI

---

## 1. Executive Summary

This Analysis of Alternatives evaluates ten LLM-backed agentic coding clients for use on the FDA
GFE laptop and REI development laptop, operating under FDA data-handling constraints (air-gapped or
gateway-only LLM access, full-tunnel VPN, Windows environment). The primary driver is identifying
which client best supports agentic software development workflows against self-hosted or approved
LLM gateways — specifically the FDA ELSA gateway (Claude Sonnet 4.6).

**Recommended alternative:** **Robodog Terminal** for gateway-bound and Windows-first workflows;
**Claude Code** as a strong complement for broader ecosystem integration and MCP tooling.

---

## 2. Problem Statement

FDA software development teams need an AI coding assistant that:
1. Works against **self-hosted / air-gapped LLM gateways** (ELSA, not public Anthropic endpoints)
2. Runs natively on **Windows** without requiring Docker or WSL
3. Operates under **FDA data-handling rules** (no data leaving the FDA network)
4. Supports **agentic workflows** (file read/edit, command execution, self-correction loops)
5. Can be **embedded or automated** for CI/headless use cases

---

## 3. Evaluation Criteria

Criteria are weighted by importance to FDA operational context.

| # | Criterion | Weight | Rationale |
|---|-----------|--------|-----------|
| C1 | Self-hosted / gateway LLM support | High | ELSA is the only approved endpoint |
| C2 | Windows-native operation | High | FDA GFE laptops are Windows |
| C3 | No external data transmission | High | FDA data policy compliance |
| C4 | Agentic tool-use loop quality | High | Core workflow requirement |
| C5 | Safety and permission controls | High | Code execution risk management |
| C6 | Open source / auditable | Medium | Security review capability |
| C7 | Embeddable / automatable | Medium | CI and headless use cases |
| C8 | MCP client support | Medium | Ecosystem integration |
| C9 | Active maintenance | Medium | Long-term viability |
| C10 | Windows command translation | Medium | Windows shell compatibility |

---

## 4. Alternatives Considered

| Alternative | Type | License | Primary Interface |
|-------------|------|---------|------------------|
| **Robodog Terminal** | CLI | MIT | Terminal / CLI |
| **Claude Code** | CLI + IDE + web | Proprietary | CLI + VS Code + Desktop |
| **Cline** | VS Code ext | Apache-2.0 | VS Code extension |
| **Roo Code** | VS Code ext | Apache-2.0 | VS Code extension |
| **Aider** | CLI | Apache-2.0 | Terminal / CLI |
| **goose** | CLI | Apache-2.0 | CLI (Rust binary) |
| **OpenHands** | CLI / SDK / web | MIT | CLI + web |
| **Continue.dev** | VS Code ext + CLI | Apache-2.0 | VS Code extension |
| **Gemini CLI** | CLI | Apache-2.0 | Terminal / CLI |
| **Qwen Code** | CLI | Apache-2.0 | Terminal / CLI |

---

## 5. Detailed Evaluation

### C1 — Self-hosted / gateway LLM support

All tools support OpenAI-compatible endpoints via `OPENAI_BASE_URL` or equivalent. ELSA exposes
both `/model/openai` (OpenAI-compatible) and `/model/anthropic` (Anthropic-compatible) surfaces.

| Tool | Gateway Support | Notes |
|------|----------------|-------|
| **Robodog** | ✅✅ | `--backend gateway` mode; built and tested against ELSA Sonnet 4.6; `GATEWAY_*` env vars |
| **Claude Code** | ✅ | `ANTHROPIC_BASE_URL` + `ANTHROPIC_AUTH_TOKEN`; currently used against ELSA `/model/anthropic` |
| Cline | ✅ | Custom OpenAI-compatible endpoint in settings |
| Roo Code | ✅ | Same as Cline |
| Aider | ✅ | `--openai-api-base` flag |
| goose | ✅ | Provider config |
| OpenHands | ✅ | LLM config |
| Continue.dev | ✅ | Model provider config |
| Gemini CLI | 🟡 | Designed for Google AI; third-party gateway support is partial |
| Qwen Code | 🟡 | Designed for DashScope/Alibaba Cloud; OpenAI-compat possible but not primary |

### C2 — Windows-native operation

| Tool | Windows | Notes |
|------|---------|-------|
| **Robodog** | ✅✅ | Built for Windows; auto-translates Unix shell commands; UTF-8 end-to-end; no Docker required |
| **Claude Code** | ✅ | Official Windows support; Git Bash required for status line |
| Cline | ✅ | Runs inside VS Code on Windows |
| Roo Code | ✅ | Same |
| Aider | ✅ | Python, runs on Windows |
| goose | 🟡 | Rust binary; Windows binary available but less tested |
| OpenHands | 🟡 | Docker-based; Docker Desktop on Windows has overhead |
| Continue.dev | ✅ | VS Code on Windows |
| Gemini CLI | ✅ | Node.js; Windows supported |
| Qwen Code | ✅ | Node.js; Windows supported |

**Key differentiator — Windows command translation:** Robodog auto-rewrites 20+ Unix-isms (grep,
head, tail, wc, curl, dir /b, 2>/dev/null, &&/|| chains, pipe filters) so LLM-generated bash
commands work on Windows PowerShell without manual correction. No other tool in this set does
this at the same breadth.

### C3 — No external data transmission

| Tool | Data Control | Notes |
|------|-------------|-------|
| **Robodog** | ✅✅ | `CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC=1`; telemetry-off flag; all traffic to configured endpoint only |
| **Claude Code** | ✅ | `CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC` env var; used successfully against ELSA |
| Cline | 🟡 | VS Code telemetry settings apply; some usage stats to Cline servers |
| Roo Code | ✅ | Fork of Cline; removes some telemetry |
| Aider | ✅ | No telemetry; open source |
| goose | ✅ | No telemetry |
| OpenHands | ✅ | Self-hosted option |
| Continue.dev | 🟡 | Telemetry opt-out available |
| Gemini CLI | 🟡 | Google Analytics opt-out flag |
| Qwen Code | 🟡 | Alibaba Cloud telemetry by default |

### C4 — Agentic tool-use loop quality

Key dimensions: iteration efficiency, subagent support, loop detection, truncation resilience,
checkpoint/rewind.

| Tool | Score | Key strengths | Key gaps |
|------|-------|--------------|----------|
| **Robodog** | ✅✅ | Read-only subagent default; atomic checkpoint/rewind; batching rule (4.6x win on Sonnet 4.6); truncation detection; loop breaker | Loop detection less sophisticated than Gemini CLI / Qwen Code |
| **Claude Code** | ✅✅ | Widest interface surface; Agent SDK; best overall feature set | Closed-source (many rows unverifiable); no embeddable core |
| Gemini CLI | ✅✅ | 3-layer loop detection incl. LLM-judged; shadow-git checkpoint; mid-stream truncation via bracket-depth | Docker-dependent for sandboxing |
| Qwen Code | ✅✅ | Most advanced loop detection; per-file snapshot; mid-stream truncation | Designed for DashScope; Windows less tested |
| Cline | ✅ | Solid; VS Code-native | VS Code dependency |
| Roo Code | ✅ | Good; forces truncated calls through (gap) | VS Code dependency |
| Aider | 🟡 | Good for git-centric workflows | No real loop detection; no checkpoint |
| OpenHands | 🟡 | Docker sandboxing; soft-timeout UX | Complex setup; not Windows-native |
| goose | 🟡 | Loop inspector is a no-op; checkpoint abandoned | Rust binary; fewer tools |
| Continue.dev | 🟡 | Good IDE integration | No loop detection (open #12702); checkpoint missing |

### C5 — Safety and permission controls

| Tool | Score | Notes |
|------|-------|-------|
| **Robodog** | ✅✅ | Deterministic 3-tier danger classification; compound-command splitting; net-write gating in headless/subagent mode; read-only subagent default |
| **Claude Code** | ✅ | ask/allow/deny; permission matching; no explicit tier system verified |
| Gemini CLI | ✅ | Real AST command parsing for permission matching |
| Qwen Code | ✅ | Same (Gemini CLI fork base) |
| Cline | 🟡 | Allow/deny; no tier classification |
| goose | ✅✅ | Regex + optional ML danger classification |

### C6 — Open source / auditable

| Tool | Auditable | Notes |
|------|-----------|-------|
| **Robodog** | ✅✅ | MIT; full source on GitHub |
| Cline, Roo Code, Aider, goose, OpenHands, Continue.dev, Gemini CLI, Qwen Code | ✅ | All Apache-2.0 |
| **Claude Code** | ❌ | Proprietary; closed-source |

### C7 — Embeddable / automatable

| Tool | Score | Notes |
|------|-------|-------|
| **Robodog** | ✅✅ | `build_core()` — Python-native embeddable core; headless `-p`; JSON output; `--trace` timing |
| Claude Code | ✅ | Claude Agent SDK (separate product); headless `-p` mode |
| OpenHands | ✅ | SDK-first design |
| Continue.dev | 🟡 | Headless `cn` mode |
| Others | ❌/🟡 | CLI-only; not designed for embedding |

### C8 — MCP client support

| Tool | MCP | Notes |
|------|-----|-------|
| **Claude Code** | ✅✅ | Full MCP client; wide server ecosystem; used with claude-mem and context7 |
| Cline, Roo Code, goose, OpenHands, Gemini CLI, Qwen Code, Continue.dev | ✅ | MCP supported |
| **Robodog** | ❌ | Not yet — ROADMAP Phase 5.1; single biggest ecosystem gap |
| Aider | ❌ | No MCP |

### C9 — Active maintenance (as of 2026-07-23)

| Tool | Activity | Notes |
|------|----------|-------|
| **Robodog** | ✅ | Active; 0.3.79 recent; FDA-motivated improvements (batching rule, ELSA testing) |
| **Claude Code** | ✅ | Anthropic-backed; very active |
| Cline | ✅ | Very active; large contributor base |
| Gemini CLI | ✅ | Google-backed |
| Qwen Code | ✅ | Alibaba-backed |
| Roo Code | ✅ | Active fork |
| Aider | ✅ | Stable; slower pace |
| OpenHands | ✅ | Active |
| Continue.dev | ✅ | Active |
| goose | 🟡 | Block AI; moderate activity |

---

## 6. Scoring Summary

| Criterion | Weight | Robodog | Claude Code | Cline | Aider | Gemini CLI |
|-----------|--------|---------|-------------|-------|-------|------------|
| C1 Gateway support | H | ✅✅ | ✅ | ✅ | ✅ | 🟡 |
| C2 Windows-native | H | ✅✅ | ✅ | ✅ | ✅ | ✅ |
| C3 No ext. data | H | ✅✅ | ✅ | 🟡 | ✅ | 🟡 |
| C4 Agentic quality | H | ✅✅ | ✅✅ | ✅ | 🟡 | ✅✅ |
| C5 Safety | H | ✅✅ | ✅ | 🟡 | ❌ | ✅ |
| C6 Open source | M | ✅✅ | ❌ | ✅ | ✅ | ✅ |
| C7 Embeddable | M | ✅✅ | ✅ | ❌ | ❌ | ❌ |
| C8 MCP | M | ❌ | ✅✅ | ✅ | ❌ | ✅ |
| C9 Maintenance | M | ✅ | ✅ | ✅ | ✅ | ✅ |
| C10 Win. translate | M | ✅✅ | 🟡 | ❌ | ❌ | ❌ |

---

## 7. Decision

### Alternative A (Recommended): Robodog Terminal (primary) + Claude Code (complementary)

**Robodog Terminal** is the recommended primary client for FDA gateway-bound agentic workflows:
- Built and tested against ELSA Sonnet 4.6
- Best Windows-native operation of any CLI client (command translation, UTF-8, no Docker)
- Strongest data-isolation posture (no telemetry, no external traffic)
- Embeddable core for CI/headless automation
- MIT license — fully auditable
- Read-only subagent default — unique safety property in this field
- 4.6x performance improvement on Sonnet 4.6 via batching rule (verified, shipped)

**Claude Code** is recommended as a complementary tool for:
- MCP ecosystem (claude-mem, context7) — Robodog does not yet have MCP
- Broader interface options (VS Code, desktop, web)
- Agent SDK for SDK-based integrations

### Gap requiring monitoring

Robodog's **MCP gap** (ROADMAP Phase 5.1) is the single largest missing feature. Until MCP lands,
Claude Code handles MCP-dependent workflows. This AOA should be re-evaluated when MCP ships.

### Alternatives not recommended for primary use

- **Cline / Roo Code** — VS Code dependency; telemetry concerns; no embeddable core
- **Aider** — git-centric; no loop detection; no checkpoint; no subagents
- **goose** — Rust binary; loop inspector is a no-op; checkpoint abandoned
- **OpenHands** — Docker-dependent; complex Windows setup
- **Gemini/Qwen Code** — Designed for Google/Alibaba; Windows less primary; ELSA compatibility unverified
- **Continue.dev** — No loop detection; checkpoint broken

---

## 8. Risk Register

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| Robodog MCP gap limits workflow | High (current) | Medium | Use Claude Code for MCP-dependent tasks; re-evaluate when MCP ships |
| ELSA model ID / endpoint changes | Medium | High | Parameterize via `ELSA_CLAUDE_MODEL` / `ELSA_CLAUDE_BASE_URL`; monitor ELSA release notes |
| Robodog single maintainer | Low-Medium | High | MIT license; fork if needed; contribute upstream |
| Claude Code closed-source security | Low | Medium | Use only against ELSA; `DISABLE_NONESSENTIAL_TRAFFIC`; review network logs |
| ELSA key rotation | Medium | Medium | Store in KeePass `SEMOSS-Elsa-Dev`; rotate on schedule |

---

## 9. References

- Robodog README.md — feature matrix, benchmark data, source-level analysis (2026-07-22)
- Robodog ROADMAP.md — MCP (Phase 5.1), sandbox (Phase 6) timeline
- `RUNBOOK-claude-code-setup.md` — Claude Code + ELSA configuration
- `RUNBOOK-claude-code-elsa.md` — ELSA endpoint details
- ELSA benchmark plan: `WHITEPAPER-ELSA-BENCHMARK-PLAN.md`

---

## 10. Revision History

| Version | Date | Author | Change |
|---------|------|--------|--------|
| 1.0 | 2026-07-23 | FDA ORA/SI | Initial draft |
