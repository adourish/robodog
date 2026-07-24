# Whitepaper — ELSA Model Benchmark Plan
**Document type:** Technical Whitepaper / Test Plan
**Version:** 1.0
**Date:** 2026-07-23
**Status:** Plan — not yet executed
**Author:** FDA ORA/SI

---

## 1. Purpose

Define a repeatable, documented test plan to benchmark Claude Sonnet 4.6 accessed via the FDA
ELSA gateway (`elsa-dev.preprod.fda.gov`) using the same methodology as the OpenRouter baseline
in `WHITEPAPER-PERFORMANCE-BENCHMARKS.md`. Results will populate the ELSA column in that
document and support the AOA in `AOA-LLM-AGENTIC-CLIENTS.md`.

---

## 2. Why ELSA Benchmarks Matter

The public-cloud baseline (OpenRouter) measures the model's intrinsic performance. The ELSA
benchmark measures what FDA developers actually experience: the same model behind a VPN, a
gateway hop, and FDA network infrastructure. Key questions:

1. **What is the gateway latency overhead per call?** (VPN + ELSA processing vs. direct API)
2. **Does batching compliance carry over?** (Sonnet 4.6 batched 2/2 via OpenRouter — does ELSA
   return the same model behavior?)
3. **Does the 4.6x batching win hold on ELSA?** (The A/B test was OpenRouter only; gateway
   routing could affect model behavior)
4. **What is the TTFT (time-to-first-token) on ELSA?** (Streaming mode; measures gateway
   processing latency independently of generation speed)
5. **How does fan-out speedup compare?** (Parallel subagents multiply gateway calls; overhead
   compounds)

---

## 3. Environment Requirements

| Requirement | Value |
|-------------|-------|
| Machine | FDA GFE laptop |
| Network | FDA full-tunnel VPN connected |
| ELSA endpoint | `https://elsa-dev.preprod.fda.gov/Monolith/api/model/anthropic` |
| Model | `8405ac40-89c6-4613-848c-3d89986fbc01` (Claude Sonnet 4.6) |
| Auth | Bearer `<access-key>:<secret-key>` from KeePass `SEMOSS-Elsa-Dev` |
| Robodog version | 0.3.79+ (record exact version in results) |
| Python | 3.9+ |
| FDA internal CA | Trusted (or `NODE_TLS_REJECT_UNAUTHORIZED=0`) |

---

## 4. Setup

### 4.1 Install Robodog with tracing

```bash
pip install -U robodog-terminal
robodog-terminal --version   # record this
```

### 4.2 Configure ELSA credentials

```powershell
# Load keys from KeePass
. C:\projects\ai-sdlc-playbook\tools\keepass\Get-KeePassAttr.ps1
$access = Get-KeePassAttr "SEMOSS-Elsa-Dev" -Attr UserName
$secret = Get-KeePassAttr "SEMOSS-Elsa-Dev" -Attr Password

# Set environment for the session
$env:GATEWAY_BASE_URL  = "https://elsa-dev.preprod.fda.gov/Monolith/api/model/anthropic"
$env:GATEWAY_API_KEY   = "${access}:${secret}"
$env:GATEWAY_MODEL     = "8405ac40-89c6-4613-848c-3d89986fbc01"
$env:ROBODOG_TRACE     = "1"
$env:NODE_TLS_REJECT_UNAUTHORIZED = "0"
```

### 4.3 Verify connectivity

```bash
robodog-terminal --backend gateway --echo
robodog-terminal --backend gateway -p "reply with OK"
```

Expected: `OK` response within ~15s. If timeout, check VPN connection.

---

## 5. Test Scenarios

Identical to the OpenRouter baseline. Use the same test files for repeatability.

### 5.1 Prepare test files

```bash
mkdir -p ~/robodog-bench/single-task
mkdir -p ~/robodog-bench/fanout
mkdir -p ~/robodog-bench/batching
```

**single-task/x.py** (target file for docstring addition):
```python
def calculate_seizure_risk(entry_data, compliance_history):
    score = 0
    if entry_data.get('value', 0) > 10000:
        score += 3
    if compliance_history.get('violations', 0) > 2:
        score += 2
    return min(score, 10)
```

**fanout/file1.py, file2.py, file3.py** — three independent Python files with simple functions.

**batching/config1.json, config2.json, config3.json** — three independent JSON config files.

### 5.2 Scenario A — Single-task

**Prompt:**
```
Read single-task/x.py, add a one-line docstring to calculate_seizure_risk,
then run: python -c "import ast; ast.parse(open('single-task/x.py').read()); print('OK')"
to verify it still parses.
```

**Run:**
```bash
cd ~/robodog-bench
ROBODOG_TRACE=1 robodog-terminal --backend gateway \
  -p "Read single-task/x.py, add a one-line docstring to calculate_seizure_risk, then run: python -c \"import ast; ast.parse(open('single-task/x.py').read()); print('OK')\" to verify it still parses."
```

**Record:** wall-clock time, iteration count, total tokens, trace output (LLM/tool/parse ms)

**Repeat:** 2 trials. Reset file between trials:
```bash
git checkout single-task/x.py
```

### 5.3 Scenario B — Fan-out

**Prompt:**
```
Using 3 parallel subagents: have subagent 1 read fanout/file1.py and summarize it,
subagent 2 read fanout/file2.py and summarize it, subagent 3 read fanout/file3.py
and summarize it. Report all three summaries.
```

**Record:** wall-clock, individual subagent durations from trace, calculated speedup ratio
`sum(subagent durations) / max(subagent duration)`

**Repeat:** 2 trials.

### 5.4 Scenario C — Batching compliance

**Prompt:**
```
I have three config files: batching/config1.json, batching/config2.json, batching/config3.json.
What is the value of the "name" field in each?
```

**Record:** Did the model read all 3 files in its first reply? (Y/N per trial)

**Repeat:** 2 trials.

### 5.5 Scenario D — TTFT measurement (ELSA-specific)

This scenario is not in the OpenRouter baseline. It isolates gateway latency.

**Method:** Use `build_core()` in streaming mode and record time-to-first-token:

```python
import time
from robodog_terminal import build_core

core = build_core(backend='gateway')

start = time.perf_counter()
first_token = None

for chunk in core.stream("reply with the word OK and nothing else"):
    if first_token is None:
        first_token = time.perf_counter() - start
        print(f"TTFT: {first_token:.3f}s")
    print(chunk, end='', flush=True)

print(f"\nTotal: {time.perf_counter() - start:.3f}s")
```

**Record:** TTFT (seconds), total response time

**Repeat:** 5 trials (more trials — TTFT variance is higher than wall-clock).

### 5.6 Scenario E — Batching A/B (ELSA-specific)

Repeat the OpenRouter A/B test on ELSA to verify the 4.6x finding holds:

**Before (no batching rule):** Monkey-patch `catalog()` to strip the batching rule, run 2
trials of the single-task scenario.

**After (with batching rule):** Normal run, 2 trials of the single-task scenario.

**Record:** avg wall-clock, avg iterations, avg tokens for before/after.

---

## 6. Results Template

Copy this table into `WHITEPAPER-PERFORMANCE-BENCHMARKS.md` after running:

```markdown
### ELSA Results

**Test date:** YYYY-MM-DD
**Robodog version:** X.X.X
**ELSA endpoint:** https://elsa-dev.preprod.fda.gov/Monolith/api/model/anthropic
**Model:** 8405ac40-89c6-4613-848c-3d89986fbc01 (Claude Sonnet 4.6)
**VPN:** FDA full-tunnel

#### Scenario A — Single-task

| Trial | Wall-clock | Iterations | Tokens | LLM phase | Tool phase |
|-------|-----------|------------|--------|-----------|------------|
| 1 | Xs | N | N | Xms | Xms |
| 2 | Xs | N | N | Xms | Xms |
| **Avg** | **Xs** | **N** | **N** | | |

**vs. OpenRouter baseline (Sonnet 4.6):** 14.74s — ELSA overhead: +Xs (+X%)

#### Scenario B — Fan-out

| Trial | Wall-clock | Agent 1 | Agent 2 | Agent 3 | Speedup |
|-------|-----------|---------|---------|---------|---------|
| 1 | Xs | Xs | Xs | Xs | Xx |
| 2 | Xs | Xs | Xs | Xs | Xx |

#### Scenario C — Batching compliance

| Trial | All 3 reads in first reply? |
|-------|-----------------------------|
| 1 | Y / N |
| 2 | Y / N |

**vs. OpenRouter baseline:** 2/2 — ELSA compliance: X/2

#### Scenario D — TTFT

| Trial | TTFT |
|-------|------|
| 1-5 | Xs |
| **Avg** | **Xs** |
| **p95** | **Xs** |

#### Scenario E — Batching A/B (ELSA)

| Condition | Avg wall-clock | Avg iterations | Avg tokens |
|-----------|---------------|----------------|------------|
| Without batching rule | Xs | N | N |
| With batching rule (0.3.78) | Xs | N | N |
| **Change** | **Xx** | | |

**vs. OpenRouter A/B:** 4.6x — ELSA A/B change: Xx
```

---

## 7. Analysis Framework

After running, answer these questions:

1. **Gateway overhead per call:** `(ELSA single-task avg) - (OpenRouter single-task avg) / avg iterations` = overhead per round trip
2. **Batching rule portability:** Does the 4.6x win replicate on ELSA? If not, is the model version the same?
3. **TTFT vs. total latency:** What fraction of total latency is gateway vs. generation?
4. **Fan-out gateway penalty:** Does parallel fan-out compound the overhead? `(ELSA fan-out overhead) vs. (N × single-call overhead)`
5. **Recommendation update:** Based on results, does the AOA recommendation change?

---

## 8. Re-run Schedule

| Trigger | Action |
|---------|--------|
| ELSA model ID changes | Re-run all scenarios; record new model ID |
| Robodog major version update | Re-run single-task and batching |
| VPN infrastructure changes | Re-run TTFT scenario |
| Quarterly review | Re-run all scenarios; update baselines |
| New model available on ELSA | Add column to cross-model table |

---

## 9. Related Documents

- `WHITEPAPER-PERFORMANCE-BENCHMARKS.md` — baseline results (OpenRouter); ELSA section to be filled
- `AOA-LLM-AGENTIC-CLIENTS.md` — decision framework; updated with ELSA benchmark findings
- `RUNBOOK-claude-code-setup.md` — ELSA credentials and configuration
- `RUNBOOK-keepass.md` — getting ELSA keys from KeePass

---

## 10. Revision History

| Version | Date | Author | Change |
|---------|------|--------|--------|
| 1.0 | 2026-07-23 | FDA ORA/SI | Initial plan |
