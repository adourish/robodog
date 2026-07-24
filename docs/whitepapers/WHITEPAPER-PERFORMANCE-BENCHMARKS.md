# Whitepaper — LLM Agentic Client Performance Benchmarks
**Document type:** Technical Whitepaper / Performance Analysis
**Version:** 1.0
**Date:** 2026-07-23
**Status:** Baseline established; ELSA benchmarks pending
**Author:** FDA ORA/SI

---

## 1. Purpose

This whitepaper documents performance benchmarks for the Robodog Terminal agentic coding client
across multiple LLM backends, establishes a baseline for public cloud models (via OpenRouter), and
defines the methodology for repeating equivalent tests against the FDA ELSA gateway
(Claude Sonnet 4.6 via `elsa-dev.preprod.fda.gov`).

---

## 2. Methodology

### 2.1 Instrumentation

All measurements use Robodog's built-in opt-in tracing:

```bash
robodog-terminal --trace    # per-session
# or:
ROBODOG_TRACE=1 robodog-terminal
```

The `--trace` flag instruments four phases independently with zero overhead when off:
- **LLM phase** — time from request dispatch to first byte of response
- **Tool phase** — time for each tool call (file read, bash, glob, grep)
- **Parse phase** — time to parse the model's response into tool calls
- **Render phase** — time to render output to the terminal

The embeddable core `build_core()` was used for benchmarks — no CLI/UI overhead included in
wall-clock measurements.

### 2.2 Scenarios

Three standardized scenarios; each run twice per model per scenario (2 trials):

| Scenario | Description | What it measures |
|----------|-------------|-----------------|
| **Single-task** | Read a Python file → add a docstring → run `python -c "import ast; ast.parse(open('x.py').read())"` to verify | Baseline read+edit+verify round trip; iteration count; wall clock |
| **Fan-out** | 3 independent files; 3 parallel `type=explore` subagents in one reply | Parallel speedup = sum(subagent durations) / max(subagent duration); 3.0x = perfect |
| **Batching** | 3 independent config files; asked about in one prompt | Does the model batch all 3 reads in its first reply (as the batching system prompt instructs)? 2/2 = always; 0/2 = never |

### 2.3 Variables tracked per run

- Wall-clock time (seconds)
- Iteration count (number of LLM round trips)
- Total tokens (prompt + completion)
- Per-phase timing breakdown (LLM / tool / parse / render)
- Batching compliance (Y/N per trial)
- Fan-out speedup ratio

### 2.4 Environment

- **Client:** Robodog Terminal, version at time of test (see header)
- **Backend:** OpenRouter (public baseline) / ELSA (FDA gateway)
- **Network:** REI laptop, consumer broadband (public) / FDA GFE laptop, full-tunnel VPN (ELSA)
- **Trial count:** 2 per scenario per model (directional; not statistically rigorous)
- **Variance note:** Network and provider-side scheduling variance is real; results are
  directional snapshots, not production SLAs

---

## 3. Baseline Results — OpenRouter (Public Cloud)

**Test date:** 2026-07 (see README.md for exact run dates)
**Robodog version:** 0.3.78+

### 3.1 Cross-model comparison

| Model | Single-task wall | Avg iterations | Fan-out speedup | Batches on first try |
|-------|-----------------|----------------|-----------------|---------------------|
| **Claude Sonnet 4.6** | 14.74s | ~3-4 | 2.5x | 2/2 ✅ |
| **Claude Opus 4.8** | 9.38s | ~3-4 | 2.7x | 2/2 ✅ |
| GPT-4o mini | 35.07s | ~5-7 | 2.7x | 1/2 🟡 |
| o4-mini | 34.18s | ~5-7 | 2.2x | 2/2 ✅ |
| GPT-5 Codex | 203.25s | high | 1.1x | 0/2 ❌ |
| Gemini 2.5 Flash | 3.02s | ~2-3 | 2.1x | 0/2 ❌ |

### 3.2 Key findings

**Iteration count beats per-call speed.** GPT-4o mini and o4-mini were 5-7 iterations on the
single-task scenario vs. 3-4 for Sonnet/Opus — wall-clock suffered not because the model is
slower per call but because it needed more round trips to reach a verified result.

**GPT-5 Codex outlier.** 203s wall-clock and no batching compliance. Likely a combination of
heavier reasoning overhead and OpenRouter routing. Sample size (2 trials) is insufficient to
distinguish model behavior from routing effects.

**Gemini 2.5 Flash — fast but doesn't follow batching guidance.** Fastest model tested (3.02s)
but 0/2 batching compliance. Batching is a system-prompt instruction — some models follow it,
others don't, regardless of raw speed.

**Fan-out speedup is consistently 2.1x–2.7x** across models (except GPT-5 Codex at 1.1x).
Perfect parallelism would be 3.0x for 3 subagents. The gap from ~2.5x to 3.0x reflects
subagent startup overhead and the fact that slower subagents cap the speedup.

### 3.3 Batching rule A/B test (controlled)

A controlled A/B test measured the impact of the 0.3.78 batching system-prompt rule on two models:

| Model | Before (no batching rule) | After (0.3.78) | Change |
|-------|--------------------------|----------------|--------|
| GPT-4o mini | 3.26s avg wall, 2.50 avg iterations | 3.14s avg wall, 2.25 avg iterations | Small / noisy |
| **Claude Sonnet 4.6** | **33.46s avg wall, 2.75 avg iterations, 8390 avg tokens** | **7.21s avg wall, 2.00 avg iterations, 4638 avg tokens** | **4.6x faster, 45% fewer tokens** |

**Finding:** The batching rule is a 4.6x wall-clock win on Claude Sonnet 4.6 (the ELSA model),
with no measurable benefit for GPT-4o mini (which already batches reads naturally). This is the
single largest verified performance improvement from robodog's tracing work.

**Negative result:** The same batching guidance applied to independent *write* operations showed
no measurable difference on Sonnet 4.6 (2.00 avg iterations either way). Not shipped; recorded
as a negative result.

---

## 4. ELSA Baseline — Not Yet Run

The following section is reserved for ELSA benchmark results. See Section 5 for the test plan.

| Model | Single-task wall | Avg iterations | Fan-out speedup | Batches on first try | TTFT |
|-------|-----------------|----------------|-----------------|---------------------|------|
| ELSA Sonnet 4.6 (`8405ac40…`) | — | — | — | — | — |

---

## 5. ELSA Benchmark Plan

See companion document: `WHITEPAPER-ELSA-BENCHMARK-PLAN.md`

Summary:
- Same 3 scenarios (single-task, fan-out, batching)
- Same methodology (`--trace`, `build_core()`, 2 trials minimum)
- Additional ELSA-specific metrics: TTFT (time-to-first-token), gateway latency vs. OpenRouter
- Environment: FDA GFE laptop, full-tunnel VPN, ELSA dev endpoint
- Expected finding: higher absolute latency than OpenRouter (gateway overhead + VPN) but
  same iteration count and batching compliance as Sonnet 4.6 via OpenRouter (same model)

---

## 6. Interpretation Guide

When reviewing benchmark results, apply these lenses:

### Wall-clock ≠ model intelligence
A slower wall-clock with fewer iterations (Opus 4.8: 9.38s, ~3-4 iter) can indicate a more
decisive model than a faster wall-clock with more iterations (GPT-4o mini: 35.07s, ~5-7 iter).

### Batching compliance predicts cost
Models that batch independent reads in one reply (Sonnet 4.6, Opus 4.8, o4-mini) use
significantly fewer tokens and round trips. Gemini 2.5 Flash's 0/2 compliance despite its
3.02s speed means it would be slower and more expensive at scale.

### Fan-out speedup is bounded by the slowest subagent
A 2.5x speedup with 3 subagents means the slowest subagent took ~57% of the sequential time.
To approach 3.0x, all subagents need similar completion times.

### Gateway latency is additive, not multiplicative
ELSA adds a fixed per-call overhead (VPN + gateway processing) on top of model latency.
Expected ELSA wall-clock = OpenRouter wall-clock + (N iterations × gateway overhead per call).
A model with fewer iterations suffers less gateway penalty.

---

## 7. Revision History

| Version | Date | Author | Change |
|---------|------|--------|--------|
| 1.0 | 2026-07-23 | FDA ORA/SI | Baseline from README.md; ELSA section reserved |
