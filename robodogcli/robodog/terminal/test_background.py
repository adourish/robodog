# file: terminal/test_background.py
"""
Self-test for terminal/background.py (BackgroundManager).

Exercises: generic spawn, spawn_bash streaming + exit code, failing targets,
kill() of a long-running shell command (process-tree kill), running_count,
and output() on an unknown id. Real threads and real subprocesses — no mocks.

Run:  python terminal/test_background.py        (from robodogcli/robodog/)
"""
from __future__ import annotations

import logging
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from terminal.background import BackgroundManager, BgTask  # noqa: E402

# Test 3 fails a task on purpose; keep its logged traceback out of the output.
logging.getLogger("terminal.background").addHandler(logging.NullHandler())
logging.getLogger("terminal.background").propagate = False


def main() -> int:
    ok = True

    def check(cond, msg):
        nonlocal ok
        status = "PASS" if cond else "FAIL"
        if not cond:
            ok = False
        print(f"  [{status}] {msg}")

    def wait_for(cond, timeout=10.0, interval=0.05):
        """Poll `cond()` until true or timeout. Returns final truth value."""
        deadline = time.time() + timeout
        while time.time() < deadline:
            if cond():
                return True
            time.sleep(interval)
        return cond()

    cwd = str(Path(__file__).resolve().parent.parent)

    # ---- 1. generic spawn: done + single notification -------------------
    print("=== 1. spawn() generic target ===")
    mgr = BackgroundManager()

    def target(task: BgTask) -> str:
        task.emit("working")
        return "the answer is 42"

    t1 = mgr.spawn("agent", "answer question", target)
    check(t1.id == "bg1", f"first task id is bg1 (got {t1.id})")
    t1.thread.join(5)
    check(not t1.thread.is_alive(), "worker thread finished")
    check(t1.status == "done", f"status is done (got {t1.status})")
    check(t1.result == "the answer is 42", "result carries target return value")
    check(t1.ended is not None and t1.ended >= t1.started, "ended timestamp set")
    notes = mgr.drain_notifications()
    check(len(notes) == 1, f"drain reports exactly one finish (got {len(notes)})")
    check(notes and "bg1" in notes[0] and "done" in notes[0]
          and "answer question" in notes[0],
          "notification names task id, status, and title")
    check(mgr.drain_notifications() == [], "second drain is empty")

    # ---- 2. spawn_bash: streaming output + exit code --------------------
    print("=== 2. spawn_bash echo ===")
    mgr2 = BackgroundManager()
    t2 = mgr2.spawn_bash("echo line1; echo line2", cwd=cwd)
    t2.thread.join(30)
    check(not t2.thread.is_alive(), "bash task finished")
    check(t2.status == "done", f"status is done (got {t2.status})")
    out = mgr2.output(t2.id)
    check("line1" in out, "output() contains line1")
    check("line2" in out, "output() contains line2")
    check(t2.result is not None and t2.result.startswith("(exit 0)"),
          f"result reports exit 0 (got {(t2.result or '')[:30]!r})")
    check("line2" in (t2.result or ""), "result includes tail of output")

    # ---- 3. failing target -> failed + notification ----------------------
    print("=== 3. failing target ===")
    mgr3 = BackgroundManager()

    def boom(task: BgTask) -> str:
        raise ValueError("kaboom")

    t3 = mgr3.spawn("agent", "doomed task", boom)
    t3.thread.join(5)
    check(t3.status == "failed", f"status is failed (got {t3.status})")
    check(t3.result is not None and "ValueError" in t3.result
          and "kaboom" in t3.result, "result carries error text")
    notes3 = mgr3.drain_notifications()
    check(len(notes3) == 1 and "failed" in notes3[0] and "doomed task" in notes3[0],
          "failure reported once with status and title")

    # ---- 4 + 5. kill() a long bash task; running_count while running -----
    print("=== 4/5. kill() long-running bash + running_count ===")
    mgr4 = BackgroundManager()
    if os.name == "nt":
        long_cmd = "Start-Sleep -Seconds 30"
    else:
        long_cmd = "sleep 30"
    t4 = mgr4.spawn_bash(long_cmd, cwd=cwd)
    check(wait_for(lambda: t4.proc is not None, timeout=10),
          "task got a live process handle")
    check(mgr4.running_count() == 1,
          f"running_count is 1 while task runs (got {mgr4.running_count()})")
    check(t4.status == "running", "status is running before kill")
    killed_at = time.time()
    msg = mgr4.kill(t4.id)
    check(msg.startswith("Killed"), f"kill() confirms (got {msg!r})")
    check(t4.status == "killed", f"status is killed (got {t4.status})")
    t4.thread.join(5)
    joined = time.time() - killed_at
    check(not t4.thread.is_alive(), f"worker thread joined within ~5s ({joined:.1f}s)")
    check(t4.cancel_event.is_set(), "cancel_event was set")
    check(mgr4.running_count() == 0, "running_count back to 0 after kill")
    notes4 = mgr4.drain_notifications()
    check(len(notes4) == 1 and "killed" in notes4[0],
          "kill reported exactly once (worker finish did not double-report)")
    check(mgr4.kill(t4.id).startswith(f"{t4.id} is not running"),
          "second kill reports task not running")

    # ---- 6. output() on unknown id ---------------------------------------
    print("=== 6. unknown task id ===")
    check(mgr4.output("bg99").startswith("ERROR"),
          "output() on unknown id returns error string")
    check(mgr4.kill("bg99").startswith("ERROR"),
          "kill() on unknown id returns error string")
    check(mgr4.get("bg99") is None, "get() on unknown id returns None")

    print("\nRESULT:", "ALL PASS" if ok else "FAILURES")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
