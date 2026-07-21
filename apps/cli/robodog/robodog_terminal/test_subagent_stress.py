# file: robodog_terminal/test_subagent_stress.py
"""
Subagent STRESS tests — dimensions the functional suite doesn't cover:
  1. Massive foreground fan-out (many agent calls in ONE turn) all complete, in order
  2. Concurrency PROOF: wall-clock << serial (each child sleeps)
  3. Failure isolation: some subagents raise, the rest still finish, parent answers
  4. Background storm: dozens spawned fast, all reach a terminal state, no deadlock
  5. Thread-safe id allocation under concurrent spawns (no dupes / lost tasks)
  6. Cancellation under load: cancel mid-fan-out returns promptly, never hangs
Network-free (EchoClient + a stateless callable script), so it's deterministic.
Run: python robodog_terminal/test_subagent_stress.py
"""
from __future__ import annotations

import logging
import sys
import tempfile
import threading
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from robodog_terminal.agents import register_agent_tool          # noqa: E402
from robodog_terminal.background import BackgroundManager         # noqa: E402
from robodog_terminal.llm_client import EchoClient                # noqa: E402
from robodog_terminal.loop import AgentLoop                       # noqa: E402
from robodog_terminal.tools import default_registry               # noqa: E402

# Silence the intentional worker-failure tracebacks these tests provoke.
logging.getLogger("robodog_terminal.background").setLevel(logging.CRITICAL)

CHILD_SLEEP = 0.3
ok = True


def check(cond, msg):
    global ok
    print(f"  [{'PASS' if cond else 'FAIL'}] {msg}")
    ok = ok and cond


def _fanout_script(n, fail_ids=()):
    """Stateless, thread-safe EchoClient script driving parent + children."""
    def script(prompt, ctx=""):
        if "TOOL RESULT [agent]" in prompt:        # parent's 2nd turn: children done
            return "All subagents returned. PARENT_ALL_DONE."
        if "STRESSCHILD" in prompt:                # a child invocation
            unit = prompt.split("STRESSCHILD unit ")[1].split()[0].strip()
            if unit.isdigit() and int(unit) in fail_ids:
                raise RuntimeError(f"boom-{unit}")   # child handler explodes
            time.sleep(CHILD_SLEEP)
            return f"STRESSCHILD_DONE:{unit}"
        return "".join(                            # parent's 1st turn: fan out n calls
            f'<tool name="agent"><param name="prompt">STRESSCHILD unit {i}</param>'
            f'<param name="type">general</param></tool>'
            for i in range(n))
    return script


def _parent(n, fail_ids=(), cancel_event=None):
    client = EchoClient(script=_fanout_script(n, fail_ids))
    reg = default_registry(cwd=tempfile.mkdtemp())
    register_agent_tool(reg, client)
    return AgentLoop(client, reg, max_iterations=6, cancel_event=cancel_event)


def main() -> int:
    global ok

    # ---- 1 & 2: massive fan-out + concurrency proof ----------------------
    N = 12
    loop = _parent(N)
    t0 = time.time()
    res = loop.run("Fan out 12 units of work in parallel.")
    dt = time.time() - t0
    agent_results = [t for t in loop.history if t.tool_name == "agent"]
    n_done = sum(1 for t in loop.history if "STRESSCHILD_DONE" in t.content)
    serial = N * CHILD_SLEEP
    check(len(agent_results) == N, f"all {N} subagents produced a result")
    check(n_done == N, f"all {N} children ran to completion")
    check("PARENT_ALL_DONE" in res.final_text, "parent synthesized a final answer after fan-out")
    check(dt < serial * 0.7, f"CONCURRENT: {dt:.2f}s vs serial {serial:.2f}s ({serial/dt:.1f}x)")

    # ---- 2b: lifecycle events (agent_spawn/agent_done) for the progress UI --
    import threading as _th
    events = []; _elk = _th.Lock()
    client = EchoClient(script=_fanout_script(3))
    reg = default_registry(cwd=tempfile.mkdtemp())
    peak = [0]; cur = [0]
    def cap_ev(kind, data):
        with _elk:
            events.append(kind)
            if kind == "agent_spawn":
                cur[0] += 1; peak[0] = max(peak[0], cur[0])
            elif kind == "agent_done":
                cur[0] -= 1
    register_agent_tool(reg, client, on_child_event=cap_ev)
    AgentLoop(client, reg, max_iterations=5).run("fan out 3")
    check(events.count("agent_spawn") == 3 and events.count("agent_done") == 3,
          "each subagent emits one agent_spawn and one agent_done")
    check(peak[0] >= 2, f"lifecycle shows concurrent in-flight subagents (peak {peak[0]})")
    check(cur[0] == 0, "in-flight returns to 0 after all subagents finish")

    # ---- 3: failure isolation --------------------------------------------
    loopf = _parent(10, fail_ids={2, 5, 8})
    resf = loopf.run("Fan out 10; some will fail.")
    ar = [t for t in loopf.history if t.tool_name == "agent"]
    n_ok = sum(1 for t in ar if "STRESSCHILD_DONE" in t.content)
    n_err = sum(1 for t in ar if ("ERROR" in t.content or "boom" in t.content
                                  or "RuntimeError" in t.content))
    check(len(ar) == 10, "all 10 subagent result slots present")
    check(n_ok == 7, f"7 healthy children completed (got {n_ok})")
    check(n_err == 3, f"3 failing children isolated as errors (got {n_err})")
    check(resf.final_text != "", "parent still answered despite child failures")

    # ---- 4 & 5: background storm + thread-safe id allocation -------------
    mgr = BackgroundManager()
    STORM = 30

    def bg_target(task):
        time.sleep(0.15)
        if task.title.endswith("F"):
            raise ValueError("bg-boom")
        return f"ok:{task.title}"

    spawned, slock = [], threading.Lock()

    def spawner(k):
        t = mgr.spawn("agent", f"unit{k}{'F' if k % 6 == 0 else 'N'}", bg_target)
        with slock:
            spawned.append(t.id)

    threads = [threading.Thread(target=spawner, args=(k,)) for k in range(STORM)]
    t0 = time.time()
    for t in threads:
        t.start()
    spawn_dt = time.time() - t0
    for t in threads:
        t.join()
    check(len(set(spawned)) == STORM, f"all {STORM} bg ids unique, none lost")
    check(spawn_dt < 1.0, f"spawning {STORM} bg tasks didn't block ({spawn_dt:.2f}s)")

    deadline = time.time() + 15
    while time.time() < deadline and mgr.running_count() > 0:
        time.sleep(0.05)
    tasks = mgr.list()
    n_done = sum(1 for t in tasks if t.status == "done")
    n_failed = sum(1 for t in tasks if t.status == "failed")
    check(mgr.running_count() == 0, "no tasks stuck running (no deadlock)")
    check(len(tasks) == STORM, f"all {STORM} tasks tracked")
    check(n_done + n_failed == STORM, f"every task terminal ({n_done} done / {n_failed} failed)")
    check(n_failed == 5, f"the 5 designed-to-fail bg tasks failed cleanly (got {n_failed})")

    # ---- 6: cancellation under load --------------------------------------
    ev = threading.Event()
    loopc = _parent(12, cancel_event=ev)

    def canceller():
        time.sleep(0.05)
        ev.set()

    threading.Thread(target=canceller, daemon=True).start()
    t0 = time.time()
    resc = loopc.run("Fan out then get cancelled.")
    cdt = time.time() - t0
    check(cdt < 3.0, f"cancellation returned promptly, no hang ({cdt:.2f}s)")
    check("cancel" in resc.final_text.lower() or resc.iterations <= 2,
          "loop honored cancel_event under load")

    print("\nSUBAGENT STRESS:", "ALL PASS" if ok else "FAILURES")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
