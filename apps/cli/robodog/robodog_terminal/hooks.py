# file: robodog_terminal/hooks.py
"""
Hooks + permission rules, mirroring a modern agentic terminal's settings.json.

Settings are merged from four locations — project first, then user; within
each scope `.robodog` wins over `.claude` (same precedence as skills.py), so
an existing Claude Code project's settings work unchanged:

    <cwd>/.robodog/settings.json
    <cwd>/.claude/settings.json
    ~/.robodog/settings.json
    ~/.claude/settings.json

Shape (all keys optional):

    {
      "permissions": {
        "allow": ["bash(git *)", "read_file(*)"],
        "deny":  ["bash(rm -rf *)", "write_file(*.env)"]
      },
      "hooks": {
        "PreToolUse":  [{"matcher": "bash|run_script",
                         "command": "python lint_gate.py", "timeout": 30}],
        "PostToolUse": [{"matcher": "write_file|edit_file",
                         "command": "npx prettier --write ."}],
        "Stop":        [{"command": "notify-send 'robodog turn done'"}]
      }
    }

PERMISSION RULES — "tool" or "tool(glob)". The glob is fnmatch-style and is
tested against the call's primary argument (command for bash/run_script,
path for file tools, prompt for agent). Semantics:
  deny match   -> the call is refused (BLOCKED, deny always wins)
  allow match  -> the call is pre-approved: the dangerous-command confirm
                  prompt is skipped for it
  no match     -> default behavior (danger guard still applies)

HOOKS — each entry's `matcher` is a regex fullmatched against the tool name
(absent/empty = every tool). `command` runs through the shell with a JSON
payload on stdin: {"event", "tool_name", "tool_input", "tool_result"?, "cwd"}.
  PreToolUse   exit 2 blocks the tool call; stderr is returned to the model.
               Other exit codes proceed (nonzero logs a warning).
  PostToolUse  runs after the tool; never blocks.
  Stop         runs when an agent turn finishes; never blocks.
Hook failures and timeouts (default 30s) never crash the loop.
"""
from __future__ import annotations

import fnmatch
import json
import logging
import os
import re
import subprocess
from pathlib import Path
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

DEFAULT_HOOK_TIMEOUT = 30
_RULE_RE = re.compile(r"^\s*([\w-]+)\s*(?:\((.*)\))?\s*$")
HOOK_EVENTS = ("PreToolUse", "PostToolUse", "Stop")


def primary_arg(args: Dict[str, str]) -> str:
    """The argument a permission glob is tested against."""
    return str(args.get("command") or args.get("path")
               or args.get("prompt") or args.get("pattern") or "")


def _parse_rule(rule: str) -> Optional[Tuple[str, str]]:
    """'bash(git *)' -> ('bash', 'git *'); 'read_file' -> ('read_file', '*')."""
    m = _RULE_RE.match(str(rule or ""))
    if not m or not m.group(1):
        return None
    pattern = m.group(2)
    return m.group(1), (pattern if pattern not in (None, "") else "*")


class HookEngine:
    """Loaded settings: permission rules + event hooks. Never raises out of
    its public methods — a bad hook or rule must not break the agent loop."""

    def __init__(self, settings: dict, cwd: str):
        self.cwd = str(cwd)
        perms = settings.get("permissions") or {}
        self.allow = [r for r in (_parse_rule(x) for x in perms.get("allow") or []) if r]
        self.deny = [r for r in (_parse_rule(x) for x in perms.get("deny") or []) if r]
        hooks = settings.get("hooks") or {}
        self.hooks: Dict[str, List[dict]] = {
            ev: [h for h in (hooks.get(ev) or []) if isinstance(h, dict) and h.get("command")]
            for ev in HOOK_EVENTS
        }
        self.sources: List[str] = settings.get("_sources", [])

    # ---- loading ---------------------------------------------------------
    @classmethod
    def load(cls, cwd: str, home: Optional[str] = None) -> "HookEngine":
        """Merge settings from the four standard locations. Project rules and
        hooks run FIRST (list-concatenation order = precedence order)."""
        home_dir = Path(home) if home else Path(os.path.expanduser("~"))
        paths = [
            Path(cwd) / ".robodog" / "settings.json",
            Path(cwd) / ".claude" / "settings.json",
            home_dir / ".robodog" / "settings.json",
            home_dir / ".claude" / "settings.json",
        ]
        merged: dict = {"permissions": {"allow": [], "deny": []},
                        "hooks": {ev: [] for ev in HOOK_EVENTS}, "_sources": []}
        seen = set()
        for p in paths:
            key = str(p.resolve()) if p.exists() else str(p)
            if key in seen:
                continue
            seen.add(key)
            if not p.is_file():
                continue
            try:
                data = json.loads(p.read_text(encoding="utf-8"))
            except Exception as exc:
                logger.warning("hooks: ignoring unparseable %s: %s", p, exc)
                continue
            perms = data.get("permissions") or {}
            merged["permissions"]["allow"] += list(perms.get("allow") or [])
            merged["permissions"]["deny"] += list(perms.get("deny") or [])
            for ev in HOOK_EVENTS:
                merged["hooks"][ev] += list((data.get("hooks") or {}).get(ev) or [])
            merged["_sources"].append(str(p))
        return cls(merged, cwd=str(cwd))

    def summary(self) -> str:
        n_rules = len(self.allow) + len(self.deny)
        n_hooks = sum(len(v) for v in self.hooks.values())
        if not (n_rules or n_hooks):
            return ""
        parts = []
        if n_rules:
            parts.append(f"{n_rules} permission rule{'s' if n_rules != 1 else ''}")
        if n_hooks:
            parts.append(f"{n_hooks} hook{'s' if n_hooks != 1 else ''}")
        return ", ".join(parts)

    # ---- permissions -----------------------------------------------------
    def check_permission(self, tool: str, args: Dict[str, str]) -> Tuple[Optional[str], str]:
        """('deny'|'allow'|None, matched_rule). Deny always wins."""
        target = primary_arg(args)
        for name, pattern in self.deny:
            if name == tool and fnmatch.fnmatchcase(target, pattern):
                return "deny", f"{name}({pattern})"
        for name, pattern in self.allow:
            if name == tool and fnmatch.fnmatchcase(target, pattern):
                return "allow", f"{name}({pattern})"
        return None, ""

    # ---- hook execution ---------------------------------------------------
    def _matching(self, event: str, tool: str) -> List[dict]:
        out = []
        for h in self.hooks.get(event, []):
            matcher = str(h.get("matcher") or "")
            if not matcher:
                out.append(h)
                continue
            try:
                if re.fullmatch(matcher, tool):
                    out.append(h)
            except re.error:
                logger.warning("hooks: bad matcher %r skipped", matcher)
        return out

    @staticmethod
    def _kill_tree(proc: subprocess.Popen) -> None:
        """Kill the whole process tree. subprocess.run's own timeout kill only
        reaches the shell on Windows — the grandchild keeps the pipes open and
        communicate() blocks until IT exits, wedging the loop for the full
        duration of a hung hook."""
        try:
            if os.name == "nt":
                subprocess.run(["taskkill", "/F", "/T", "/PID", str(proc.pid)],
                               capture_output=True)
            else:
                import signal
                os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
        except Exception:
            pass

    def _run_one(self, hook: dict, payload: dict):
        """Run one hook command. Returns (exit_code, stderr) or (None, '') on
        infrastructure failure (timeout/spawn error) — which never blocks."""
        try:
            timeout = float(hook.get("timeout") or DEFAULT_HOOK_TIMEOUT)
        except (TypeError, ValueError):
            timeout = DEFAULT_HOOK_TIMEOUT
        try:
            popen_kw = {}
            if os.name != "nt":
                popen_kw["start_new_session"] = True   # killpg needs a group
            proc = subprocess.Popen(
                str(hook["command"]), shell=True, cwd=self.cwd,
                stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                stderr=subprocess.PIPE, text=True,
                env=dict(os.environ,
                         ROBODOG_HOOK_EVENT=payload.get("event", ""),
                         ROBODOG_TOOL_NAME=payload.get("tool_name", "")),
                **popen_kw)
            try:
                _, stderr = proc.communicate(json.dumps(payload), timeout=timeout)
            except subprocess.TimeoutExpired:
                self._kill_tree(proc)
                try:
                    proc.communicate(timeout=5)
                except Exception:
                    pass
                logger.warning("hooks: %r timed out after %.0fs",
                               hook["command"], timeout)
                return None, ""
            return proc.returncode, (stderr or "").strip()
        except Exception as exc:
            logger.warning("hooks: %r failed to run: %s", hook["command"], exc)
            return None, ""

    def run_pre(self, tool: str, args: Dict[str, str]) -> Optional[str]:
        """Run PreToolUse hooks. Returns a block-reason string if any hook
        exits 2, else None (proceed)."""
        payload = {"event": "PreToolUse", "tool_name": tool,
                   "tool_input": dict(args), "cwd": self.cwd}
        for hook in self._matching("PreToolUse", tool):
            code, stderr = self._run_one(hook, payload)
            if code == 2:
                return stderr or f"blocked by PreToolUse hook: {hook['command']}"
            if code not in (0, None):
                logger.warning("hooks: PreToolUse %r exited %s (proceeding)",
                               hook["command"], code)
        return None

    def run_post(self, tool: str, args: Dict[str, str], result: str) -> None:
        payload = {"event": "PostToolUse", "tool_name": tool,
                   "tool_input": dict(args),
                   "tool_result": str(result)[:10_000], "cwd": self.cwd}
        for hook in self._matching("PostToolUse", tool):
            self._run_one(hook, payload)

    def run_stop(self) -> None:
        payload = {"event": "Stop", "cwd": self.cwd}
        for hook in self._matching("Stop", ""):
            self._run_one(hook, payload)
