# file: terminal/background.py
"""
BackgroundManager: thread-based background tasks for terminal mode.

Runs long work (shell commands, agent loops) in daemon threads so the main
REPL stays responsive — Claude Code's Ctrl-B / `run_in_background` pattern.
Each task gets a small id ("bg1", "bg2", ...), a capped output buffer the
worker appends to via task.emit(), and a cancel_event / proc handle so
kill() can stop it (killing the whole process tree for shell commands).
Finished tasks are reported exactly once through drain_notifications(),
which the app polls between prompts to print one-liners like
"✔ bg1 done: run tests (42s)".

The module never prints; the app renders. Logging only.
"""
from __future__ import annotations

import logging
import os
import subprocess
import threading
import time
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional

logger = logging.getLogger(__name__)

BUFFER_MAX_LINES = 2000   # per-task output cap (oldest lines dropped)
RESULT_TAIL_LINES = 50    # lines of output folded into a bash task's result


@dataclass
class BgTask:
    id: str                       # "bg1", "bg2", ... assigned by manager
    kind: str                     # "bash" | "agent"
    title: str                    # short human label
    status: str = "running"       # "running" | "done" | "failed" | "killed"
    result: Optional[str] = None  # final result text when done/failed
    started: float = field(default_factory=time.time)
    ended: Optional[float] = None
    # -- internal ---------------------------------------------------------
    thread: Optional[threading.Thread] = field(default=None, repr=False)
    buffer: List[str] = field(default_factory=list, repr=False)
    lock: threading.Lock = field(default_factory=threading.Lock, repr=False)
    cancel_event: threading.Event = field(default_factory=threading.Event, repr=False)
    proc: Optional[subprocess.Popen] = field(default=None, repr=False)

    def emit(self, line: str) -> None:
        """Append an output line (worker-thread safe). Oldest lines drop past cap."""
        with self.lock:
            self.buffer.append(line)
            if len(self.buffer) > BUFFER_MAX_LINES:
                del self.buffer[: len(self.buffer) - BUFFER_MAX_LINES]

    def tail(self, n: int = RESULT_TAIL_LINES) -> str:
        """Last `n` buffered lines, joined."""
        with self.lock:
            return "\n".join(self.buffer[-n:]) if self.buffer else ""

    def duration(self) -> float:
        return (self.ended or time.time()) - self.started


def _kill_proc_tree(proc: subprocess.Popen) -> Optional[str]:
    """Kill `proc` and its descendants. Returns an error string or None."""
    try:
        if os.name == "nt":
            subprocess.run(
                ["taskkill", "/F", "/T", "/PID", str(proc.pid)],
                capture_output=True, timeout=10,
            )
        else:
            import signal
            # requires Popen(start_new_session=True) so pid == pgid
            os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
        return None
    except (ProcessLookupError, PermissionError, OSError,
            subprocess.SubprocessError) as exc:
        logger.warning("kill of pid %s failed: %s", proc.pid, exc)
        try:  # fall back to killing just the direct child
            proc.kill()
            return None
        except OSError:
            return f"{type(exc).__name__}: {exc}"


class BackgroundManager:
    """Owns the background task table. All public methods are thread-safe."""

    def __init__(self):
        self._lock = threading.Lock()          # guards table, counter, pending
        self._tasks: Dict[str, BgTask] = {}
        self._counter = 0
        self._pending: List[str] = []          # finish one-liners not yet drained

    # ---- spawning -------------------------------------------------------
    def spawn(self, kind: str, title: str,
              target: Callable[[BgTask], str]) -> BgTask:
        """
        Run `target(task) -> str` in a daemon thread. The return value becomes
        task.result with status 'done'; an exception -> 'failed' with the error
        text. `target` should check task.cancel_event periodically and may call
        task.emit(line) to stream output into the buffer.
        """
        with self._lock:
            self._counter += 1
            task = BgTask(id=f"bg{self._counter}", kind=kind, title=title)
            self._tasks[task.id] = task

        def _runner():
            try:
                result = target(task)
                self._finish(task, "done", result if result is not None else "")
            except Exception as exc:  # worker errors are captured, never raised
                logger.exception("background task %s (%s) failed", task.id, title)
                self._finish(task, "failed", f"{type(exc).__name__}: {exc}")

        task.thread = threading.Thread(
            target=_runner, name=f"bg-{task.id}", daemon=True)
        task.thread.start()
        return task

    def spawn_bash(self, command: str, cwd: str, timeout: int = 0) -> BgTask:
        """
        Run a shell command in the background (PowerShell on Windows, /bin/sh
        elsewhere), streaming each output line into the task buffer. timeout=0
        means no timeout. Result = "(exit <code>)\\n" + last 50 output lines.
        """
        def _target(task: BgTask) -> str:
            if os.name == "nt":
                shell_cmd = ["powershell", "-NoProfile", "-NonInteractive",
                             "-Command", command]
                popen_kwargs = {}
            else:
                shell_cmd = ["/bin/sh", "-c", command]
                popen_kwargs = {"start_new_session": True}  # own pgid for killpg
            proc = subprocess.Popen(
                shell_cmd, cwd=cwd,
                stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                stdin=subprocess.DEVNULL, text=True, errors="replace",
                bufsize=1, **popen_kwargs,
            )
            task.proc = proc  # so kill() can terminate the tree

            timer: Optional[threading.Timer] = None
            if timeout > 0:
                def _on_timeout():
                    task.emit(f"[timeout after {timeout}s — killing process]")
                    _kill_proc_tree(proc)
                timer = threading.Timer(timeout, _on_timeout)
                timer.daemon = True
                timer.start()
            try:
                assert proc.stdout is not None
                for line in proc.stdout:  # EOF when proc (or its killer) exits
                    task.emit(line.rstrip("\r\n"))
                code = proc.wait()
            finally:
                if timer is not None:
                    timer.cancel()
            tail = task.tail(RESULT_TAIL_LINES)
            return f"(exit {code})\n{tail}"

        title = command if len(command) <= 60 else command[:57] + "..."
        return self.spawn("bash", title, _target)

    # ---- queries --------------------------------------------------------
    def list(self) -> List[BgTask]:
        with self._lock:
            return list(self._tasks.values())

    def get(self, task_id: str) -> Optional[BgTask]:
        with self._lock:
            return self._tasks.get(task_id)

    def output(self, task_id: str, tail: int = 50) -> str:
        """Last `tail` buffered lines for a task, or an error string."""
        task = self.get(task_id)
        if task is None:
            return f"ERROR: no such background task '{task_id}'."
        text = task.tail(tail)
        return text or "(no output yet)"

    def running_count(self) -> int:
        with self._lock:
            return sum(1 for t in self._tasks.values() if t.status == "running")

    # ---- control --------------------------------------------------------
    def kill(self, task_id: str) -> str:
        """Cancel a running task, killing its process tree if it has one."""
        task = self.get(task_id)
        if task is None:
            return f"ERROR: no such background task '{task_id}'."
        if task.status != "running":
            return f"{task.id} is not running (status: {task.status})."
        task.cancel_event.set()
        err = None
        if task.proc is not None and task.proc.poll() is None:
            err = _kill_proc_tree(task.proc)
        self._finish(task, "killed", "killed by user")
        if err:
            return f"Marked {task.id} killed, but process kill failed: {err}"
        return f"Killed {task.id}: {task.title}"

    # ---- notifications --------------------------------------------------
    def drain_notifications(self) -> List[str]:
        """One-liners for tasks finished since the last drain (each once)."""
        with self._lock:
            pending, self._pending = self._pending, []
            return pending

    # ---- internal -------------------------------------------------------
    def _finish(self, task: BgTask, status: str, result: str) -> None:
        """Transition running -> terminal exactly once and queue a notification."""
        with self._lock:
            if task.status != "running":  # already finished (e.g. killed)
                return
            task.status = status
            task.result = result
            task.ended = time.time()
            symbol = {"done": "✔", "failed": "✗", "killed": "✗"}.get(status, "•")
            self._pending.append(
                f"{symbol} {task.id} {status}: {task.title} "
                f"({int(round(task.duration()))}s)")
        logger.debug("task %s finished: %s", task.id, status)
