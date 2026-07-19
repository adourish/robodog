# file: robodog_terminal/perf_fanout.py
"""
LIVE subagent fan-out PERFORMANCE test.

Fires N real subagents concurrently through the exact production path
(the `agent` tool -> child AgentLoop -> live LLM calls), invoked the same way
loop.py's ThreadPoolExecutor drives a fan-out. Measures the concurrency speedup
vs. the serial-equivalent time and checks answer correctness.

Uses the real backend wiring (build_backend): gateway / OpenRouter / OpenAI —
whatever your env/KeePass provides. If no live backend is configured it resolves
to the echo mock and the test SKIPS (exit 0), so it's safe in keyless CI.

Run:
  python robodog_terminal/perf_fanout.py            # N=8
  python robodog_terminal/perf_fanout.py 12         # N=12
  ROBODOG_PERF_N=10 python robodog_terminal/perf_fanout.py

Thresholds (override via env):
  ROBODOG_PERF_MIN_SPEEDUP (default 2.5)   concurrency speedup vs serial-sum
  ROBODOG_PERF_MIN_CORRECT (default N-1)   correct answers required
"""
from __future__ import annotations

import concurrent.futures as cf
import os
import sys
import time
from argparse import Namespace
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from robodog_terminal.agents import register_agent_tool           # noqa: E402
from robodog_terminal.tools import default_registry               # noqa: E402

try:
    from robodog_terminal.app import build_backend, _load_local_config
except ImportError:  # direct-run fallback
    from app import build_backend, _load_local_config  # type: ignore


def main() -> int:
    # Pull ~/.robodog/config.env into the environment exactly like the CLI does.
    try:
        _load_local_config()
    except Exception:
        pass

    N = int(sys.argv[1]) if len(sys.argv) > 1 else int(os.environ.get("ROBODOG_PERF_N", "8"))
    min_speedup = float(os.environ.get("ROBODOG_PERF_MIN_SPEEDUP", "2.5"))
    min_correct = int(os.environ.get("ROBODOG_PERF_MIN_CORRECT", str(N - 1)))

    retries = []
    args = Namespace(echo=False, backend="auto", model=None)
    client, label = build_backend(args, on_retry=lambda a, m, d, r: retries.append(r))

    if label.startswith("echo"):
        print(f"[SKIP] perf_fanout: no live backend configured ({label}). "
              f"Set ROBODOG_LLM_KEY / GATEWAY_* or a KeePass entry to run this.")
        return 0

    reg = default_registry(cwd=".")
    register_agent_tool(reg, client)

    # Self-contained tasks (no tools needed) -> each child is a couple LLM calls.
    tasks = [{"prompt": f"Reply with ONLY the integer that is {i}*7. No words, no tools.",
              "type": "general"} for i in range(1, N + 1)]
    expect = [str(i * 7) for i in range(1, N + 1)]

    def one(a):
        t0 = time.time()
        out = reg.execute("agent", a)
        return time.time() - t0, out

    print(f"perf_fanout: firing {N} live subagents concurrently on [{label}] "
          f"(max_workers={N})...\n")
    t0 = time.time()
    with cf.ThreadPoolExecutor(max_workers=N) as ex:
        results = list(ex.map(one, tasks))
    wall = time.time() - t0

    serial_sum = sum(dt for dt, _ in results)
    speedup = serial_sum / wall if wall else 0.0
    throughput = N / wall if wall else 0.0
    hits = sum(1 for i, (_, out) in enumerate(results) if expect[i] in out)

    for i, (dt, out) in enumerate(results):
        tail = out.strip().splitlines()[-1].strip()[:32] if out.strip() else ""
        print(f"  agent {i+1:>2}: {dt:4.1f}s  expect {expect[i]:>3}  "
              f"{'OK ' if expect[i] in out else 'MISS'}  ({tail!r})")

    print(f"\n  wall-clock (all {N} concurrent): {wall:.1f}s")
    print(f"  serial-equivalent (sum)        : {serial_sum:.1f}s")
    print(f"  concurrency speedup            : {speedup:.1f}x   (min {min_speedup}x)")
    print(f"  throughput                     : {throughput:.1f} agents/s")
    print(f"  correct answers                : {hits}/{N}   (min {min_correct})")
    print(f"  retries triggered              : {len(retries)}")

    passed = hits >= min_correct and speedup >= min_speedup
    print("\nperf_fanout:", "PASS" if passed else "FAIL")
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
