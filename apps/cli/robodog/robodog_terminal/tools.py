# file: robodog_terminal/tools.py
"""
Tool registry + executors for terminal mode.

These are the agentic core tools: read_file, write_file, edit_file,
bash, glob, grep, list_dir. Each tool has:
  - a JSON-ish spec (name, description, params) used to render the system-prompt
    tool catalog the model reads, and
  - a Python executor that returns a string result fed back into the loop.

YOLO permissions: mutating tools (write/edit/bash) run without prompting. A gate
can be added later in permissions.py.
"""
from __future__ import annotations

import fnmatch
import json
import os
import shutil
import signal
import subprocess
import sys
import tempfile
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Dict, List, Optional, Tuple

MAX_OUTPUT = 30_000  # clamp tool output fed back to the model


# ========================================================================
# Post-edit verification: after a mutating file op, syntax-check by extension
# so the agent learns immediately when it wrote something broken and can fix it.
# Returns an error string (to append to the tool result) or None when clean/NA.
# ========================================================================
def verify_syntax(path: Path) -> Optional[str]:
    suffix = path.suffix.lower()
    try:
        if suffix == ".py":
            src = path.read_text(encoding="utf-8", errors="replace")
            try:
                compile(src, str(path), "exec")
            except SyntaxError as exc:
                return f"Python syntax error at line {exc.lineno}: {exc.msg}"
        elif suffix == ".json":
            try:
                json.loads(path.read_text(encoding="utf-8", errors="replace"))
            except json.JSONDecodeError as exc:
                return f"JSON parse error at line {exc.lineno}, col {exc.colno}: {exc.msg}"
        elif suffix in (".yaml", ".yml"):
            try:
                import yaml  # PyYAML is a robodog dependency
            except ImportError:
                return None
            try:
                yaml.safe_load(path.read_text(encoding="utf-8", errors="replace"))
            except yaml.YAMLError as exc:
                return f"YAML parse error: {str(exc).splitlines()[0]}"
        elif suffix == ".toml":
            try:
                import tomllib  # py3.11+
            except ImportError:
                return None
            try:
                tomllib.loads(path.read_text(encoding="utf-8", errors="replace"))
            except Exception as exc:
                return f"TOML parse error: {exc}"
        elif suffix in (".js", ".mjs", ".cjs", ".ts", ".jsx", ".tsx"):
            node = shutil.which("node")
            if not node or suffix in (".ts", ".tsx"):
                return None  # no node, or TS needs a real compiler — skip
            proc = subprocess.run([node, "--check", str(path)],
                                  capture_output=True, text=True, timeout=15)
            if proc.returncode != 0:
                msg = (proc.stderr or proc.stdout).strip().splitlines()
                return "JS syntax error: " + (msg[0] if msg else "check failed")
    except Exception:
        return None  # verification must never break the edit
    return None


def _fuzzy_find(original: str, old: str) -> Optional[Tuple[int, int]]:
    """
    Whitespace-tolerant fallback for edit_file: match `old` against `original`
    ignoring only TRAILING whitespace per line and surrounding blank lines
    (indentation is preserved). Returns (start, end) char span of the UNIQUE
    match in `original`, or None if zero/ambiguous.
    """
    target = [ln.rstrip() for ln in old.strip("\n").split("\n")]
    if not target or not any(target):
        return None
    src_lines = original.split("\n")
    # precompute char offset of each source line start
    offsets, pos = [], 0
    for ln in src_lines:
        offsets.append(pos)
        pos += len(ln) + 1  # +1 for the '\n'
    norm = [ln.rstrip() for ln in src_lines]
    n = len(target)
    matches = []
    for i in range(0, len(src_lines) - n + 1):
        if norm[i:i + n] == target:
            start = offsets[i]
            end = offsets[i + n - 1] + len(src_lines[i + n - 1])
            matches.append((start, end))
    return matches[0] if len(matches) == 1 else None


def edit_not_found_hint(original: str, old: str) -> str:
    """
    Explain WHY an edit_file old_string didn't match, so the model can self-
    correct instead of re-submitting the same broken edit. Returns a short hint
    string (leading space, no trailing newline), or "" if nothing useful found.

    Detects, in priority order: the text is present but with different line
    endings; present but with different leading/trailing whitespace; a non-unique
    whitespace-normalized match; or shows the closest actual line in the file
    with its line number so the model can copy the real content.
    """
    if not old.strip():
        return " old_string is empty — nothing to find."
    # 1. Line-ending mismatch: model sent CRLF the file doesn't have, or vice-versa.
    if old not in original:
        if old.replace("\r\n", "\n") in original.replace("\r\n", "\n") and (
                "\r\n" in old) != ("\r\n" in original):
            return (" the text IS present but line endings differ (CRLF vs LF). "
                    "Copy old_string exactly from read_file output.")
        # 2. Present ignoring surrounding whitespace on the whole block?
        if old.strip() and old.strip() in original:
            return (" the text is present but your old_string has extra leading/"
                    "trailing whitespace — trim it to match the file exactly.")
    # 3. Whitespace-normalized block appears but wasn't a UNIQUE fuzzy match.
    norm_src = "\n".join(l.rstrip() for l in original.split("\n"))
    norm_old = "\n".join(l.rstrip() for l in old.strip("\n").split("\n"))
    occ = norm_src.count(norm_old) if norm_old else 0
    if occ > 1:
        return (f" the text appears {occ}× (ignoring trailing whitespace); add "
                "more surrounding context so old_string is unique.")
    # 4. Point at the closest actual line so the model sees the real content.
    import difflib
    anchor = next((l for l in old.strip("\n").split("\n") if l.strip()), "")
    if anchor:
        src_lines = original.split("\n")
        best_i, best_r = -1, 0.0
        a = anchor.strip()
        for i, l in enumerate(src_lines):
            r = difflib.SequenceMatcher(None, a, l.strip()).ratio()
            if r > best_r:
                best_i, best_r = i, r
        if best_i >= 0 and best_r >= 0.5:
            actual = src_lines[best_i].strip()
            return (f" closest line in the file is line {best_i + 1}: "
                    f"{actual!r} — your old_string began {a!r}. "
                    "Re-read the file and copy the exact current text.")
    return " re-read the file with read_file and copy the exact current text."

# Directories glob/grep never descend into (mirrors .gitignore-aware search).
EXCLUDE_DIRS = {
    ".git", "node_modules", "__pycache__", "dist", "build", ".venv", "venv",
    ".idea", ".vscode", ".pytest_cache", ".mypy_cache", "egg-info", ".tox",
}


def _is_excluded(path: Path) -> bool:
    return any(part in EXCLUDE_DIRS or part.endswith(".egg-info")
               for part in path.parts)


def _clamp(text: str, limit: int = MAX_OUTPUT) -> str:
    if len(text) <= limit:
        return text
    head = text[: limit // 2]
    tail = text[-limit // 2:]
    return f"{head}\n... [truncated {len(text) - limit} chars] ...\n{tail}"


# Commands that can destroy data or push irreversibly — flagged even in YOLO.
_DANGER_PATTERNS = [
    r"\brm\s+-[a-z]*[rf]", r"\brmdir\s+/s", r"\bdel\s+/[a-z]*[fs]",
    r"\bRemove-Item\b.*-Recurse", r"\bgit\s+push\b.*(--force|-f)\b",
    r"\bgit\s+reset\s+--hard", r"\bgit\s+clean\s+-[a-z]*f",
    # disk format only — NOT the `--format`/`-format` flag common in git/log/etc.
    r"(?<!-)\bformat\s+([a-zA-Z]:|/[a-z])", r"\bmkfs\b", r"\bdd\s+if=",
    r":\(\)\s*\{",  # fork bomb
    r"\b(shutdown|reboot)\b", r">\s*/dev/sd", r"\bchmod\s+-R\s+777",
    r"\bDrop-Item\b", r"\bTruncate\b.*Table", r"\bDROP\s+(TABLE|DATABASE)\b",
]


def classify_danger(command: str) -> Optional[str]:
    """Return a short reason if the command looks destructive, else None."""
    import re
    for pat in _DANGER_PATTERNS:
        if re.search(pat, command, re.IGNORECASE):
            return pat
    return None


def _split_top_level(command: str, op: str) -> List[str]:
    """Split on `op` (e.g. '&&') at the top level only — never inside single or
    double quotes. Returns [command] when the operator isn't present."""
    parts, buf = [], []
    i, n, L = 0, len(command), len(op)
    quote = None
    while i < n:
        ch = command[i]
        if quote:
            buf.append(ch)
            if ch == quote:
                quote = None
            i += 1
            continue
        if ch in ("'", '"'):
            quote = ch
            buf.append(ch)
            i += 1
            continue
        if command[i:i + L] == op:
            parts.append("".join(buf))
            buf = []
            i += L
            continue
        buf.append(ch)
        i += 1
    parts.append("".join(buf))
    return parts


def powershell_translate(command: str) -> str:
    """Rewrite a bash-style `A && B` / `A || B` chain into PowerShell so it runs
    instead of erroring — models trained on bash reach for `&&` constantly on
    Windows. `&&` -> nested `if ($?) { … }` (preserves the run-B-only-if-A
    conditional, unlike a bare `;`); `||` -> `if (-not $?) { … }`. Only pure
    chains are translated (mixed &&/|| is left for the hint); quotes are
    respected so `echo "a && b"` is untouched. Returns the command unchanged
    when there's nothing to do."""
    if os.name != "nt" or ("&&" not in command and "||" not in command):
        return command
    ands = _split_top_level(command, "&&")
    ors = _split_top_level(command, "||")
    if len(ands) > 1 and len(ors) == 1:
        chain = [p.strip() for p in ands]
        cond = "if ($?)"
    elif len(ors) > 1 and len(ands) == 1:
        chain = [p.strip() for p in ors]
        cond = "if (-not $?)"
    else:
        return command   # mixed / operator only inside quotes — leave it
    if any(not seg for seg in chain):
        return command   # empty segment -> malformed, don't touch
    out = chain[-1]
    for seg in reversed(chain[:-1]):
        out = f"{seg}; {cond} {{ {out} }}"
    return out


def shell_syntax_hint(command: str, combined: str) -> str:
    """A one-line fix for the shell-syntax mistakes models repeat on Windows
    PowerShell — appended to a FAILED command result so the model self-corrects
    instead of looping. `combined` is the command's stdout+stderr. Module-level
    (not a bash closure) so it's directly testable regardless of what Unix
    tools happen to be on the host PATH."""
    if os.name != "nt":
        return ""
    low = (combined or "").lower()
    if "&&" in command and ("not a valid statement separator" in low
                            or "token '&&'" in low):
        return ("\nHINT: this shell is PowerShell — `&&` and `||` are not "
                "valid. Chain with `;` (run both) or send separate commands. "
                "For 'run B only if A succeeded': `A; if ($?) { B }`.")
    if "not recognized as the name of a cmdlet" in low:
        unix = ("head", "tail", "grep", "cat", "which", "ls ", "wc",
                "uniq", "awk", "sed", "less", "touch", "sort ")
        if any(f" {u}" in f" {command}" or command.startswith(u) for u in unix):
            return ("\nHINT: that's a Unix command in PowerShell. Use "
                    "`Select-Object -First N` (head), `-Last N` (tail), "
                    "`Measure-Object -Line` (wc -l), `Select-String` (grep), "
                    "`Get-Content` (cat), `Get-ChildItem` (ls), "
                    "`Sort-Object -Unique` (sort/uniq). Or run the same query "
                    "without the pipe — many git/tools have built-in limits "
                    "(e.g. `git log -n 20`).")
    cmd_low = command.lower()
    if "if not exist" in cmd_low or "if exist" in cmd_low or "%errorlevel%" in cmd_low:
        return ("\nHINT: that's cmd.exe syntax in PowerShell. Use "
                "`if (-not (Test-Path X)) { ... }` instead of `if not exist X`, "
                "and `New-Item -ItemType Directory -Force X` to mkdir.")
    return ""


def python_import_hint(stderr: str, cwd: str) -> str:
    """A one-line fix for the #1 Python import loop we see with skill repos:
    `from pkg.sub.jira_call.main import run` fails with ModuleNotFoundError
    because the real directory is `jira-call` (a HYPHEN) — not importable by a
    dotted name. When the missing module maps to a hyphenated directory on disk,
    point the model straight at importlib. Returns a hint (leading '\\n') or "".
    """
    import re as _re
    m = _re.search(r"ModuleNotFoundError: No module named ['\"]([\w.]+)['\"]", stderr or "")
    if not m:
        return ""
    dotted = m.group(1)
    parts = dotted.split(".")
    try:
        base = Path(cwd)
    except Exception:
        return ""
    # Walk the existing prefix; at the first segment that ISN'T a real dir, check
    # whether its underscores-as-hyphens variant IS a directory (the skill dir).
    cur = base
    for seg in parts:
        nxt = cur / seg
        if nxt.is_dir():
            cur = nxt
            continue
        hy = seg.replace("_", "-")
        if hy != seg and (cur / hy).is_dir():
            target = cur / hy
            main_py = target / "main.py"
            loc = main_py if main_py.is_file() else target
            return (f"\nHINT: '{seg}' isn't importable because the directory is "
                    f"'{hy}' (a hyphen) — Python module names can't contain '-'. "
                    f"Load it with importlib instead:\n"
                    f"    import importlib.util\n"
                    f"    spec = importlib.util.spec_from_file_location("
                    f"'mod', r'{loc}')\n"
                    f"    mod = importlib.util.module_from_spec(spec); "
                    f"spec.loader.exec_module(mod)")
        break
    return ""


def python_error_hint(stderr: str) -> str:
    """A one-line fix for recurring Python runtime mistakes the model loops on
    (keyed on the traceback text only — no filesystem needed). Returns a hint
    with a leading '\\n', or "" when nothing matches."""
    err = stderr or ""
    # json.loads() on an ALREADY-parsed value. Skill run()s that return
    # body=<parsed dict> made the model loop on `json.loads(result["body"])`.
    import re as _re
    m = _re.search(
        r"the JSON object must be str, bytes or bytearray, not (\w+)", err)
    if m:
        typ = m.group(1)
        return (f"\nHINT: that value is ALREADY a parsed {typ} — drop the "
                f"json.loads() call and use it directly (index/iterate it). "
                f"json.loads() only takes a JSON *string*; call it just once on "
                f"raw text, never on a dict/list you already have.")
    return ""


@dataclass
class ToolParam:
    name: str
    description: str
    required: bool = True


@dataclass
class Tool:
    name: str
    description: str
    params: List[ToolParam]
    handler: Callable[[Dict[str, str]], str]
    mutating: bool = False

    def run(self, args: Dict[str, str]) -> str:
        missing = [p.name for p in self.params if p.required and p.name not in args]
        if missing:
            return f"ERROR: missing required param(s): {', '.join(missing)}"
        try:
            return _clamp(self.handler(args))
        except Exception as exc:  # tool errors are fed back, not fatal
            return f"ERROR: {type(exc).__name__}: {exc}"


class ToolRegistry:
    def __init__(self, cwd: Optional[str] = None):
        self.cwd = Path(cwd or os.getcwd()).resolve()
        self._tools: Dict[str, Tool] = {}
        # Safety layer (wired by app.py):
        self.read_paths: set = set()      # files Read this session (read-before-edit)
        self.checkpointer = None          # Checkpointer — snapshots before mutation
        self.on_diff: Optional[Callable[[str, str], None]] = None  # UI diff preview
        self.on_bash_line: Optional[Callable[[str], None]] = None  # UI live output, per line
        # Plan mode: when "plan", mutating tools are refused (read-only propose-first).
        self.mode: str = "yolo"  # "yolo" | "plan"
        # Background bash hook (app wires to BackgroundManager.spawn_bash).
        self.background_spawn: Optional[Callable[[str, str], str]] = None
        # Post-edit syntax verification (self-healing edits).
        self.verify_edits: bool = True
        # Dangerous-command guard: "warn" (log+proceed, YOLO) or "confirm".
        self.guard: str = "warn"
        self.on_confirm: Optional[Callable[[str, str], bool]] = None
        # Override/auto-detect the project's test command (run_tests tool).
        self.test_command: Optional[str] = None
        # Hooks + permission rules (hooks.HookEngine; wired by app.py).
        self.hooks = None

    # ---- registration ---------------------------------------------------
    def register(self, tool: Tool) -> None:
        self._tools[tool.name] = tool

    def get(self, name: str) -> Optional[Tool]:
        return self._tools.get(name)

    def execute(self, name: str, args: Dict[str, str]) -> str:
        tool = self._tools.get(name)
        if not tool:
            return f"ERROR: unknown tool '{name}'. Available: {', '.join(self._tools)}"
        if self.mode == "plan" and tool.mutating:
            return (f"ERROR: plan mode — {name} is not allowed (read-only). "
                    f"Investigate with read tools and present a plan; the user "
                    f"will approve before implementation.")
        if self.hooks is not None:
            verdict, rule = self.hooks.check_permission(name, args)
            if verdict == "deny":
                return (f"BLOCKED: permission rule '{rule}' denies this call. "
                        f"Do not retry it; choose a different approach.")
            block = self.hooks.run_pre(name, args)
            if block is not None:
                return f"BLOCKED: {block}"
        result = tool.run(args)
        if self.hooks is not None:
            self.hooks.run_post(name, args, result)
        return result

    # ---- path helper ----------------------------------------------------
    def _project_root(self) -> Optional[Path]:
        """Nearest ancestor of cwd containing a .git (the repo root), or None."""
        for base in (self.cwd, *self.cwd.parents):
            if (base / ".git").exists():
                return base
        return None

    def _resolve(self, p: str, search: bool = False) -> Path:
        """
        Resolve a path. Absolute paths pass through. Relative paths join to cwd.
        With search=True (read tools), if cwd/p doesn't exist, also try the
        repo root and cwd's ancestors — so a REPO-RELATIVE path like `apps/cli`
        still resolves even when cwd is deep inside the tree (no more doubling
        like cwd/apps/cli/…/apps/cli). Falls back to cwd-relative if nothing
        exists, so the not-found error stays sensible.
        """
        path = Path(p)
        if path.is_absolute():
            return path
        direct = self.cwd / path
        if not search or direct.exists():
            return direct
        root = self._project_root()
        bases = []
        if root is not None:
            bases.append(root)
        for anc in self.cwd.parents:
            bases.append(anc)
            if root is not None and anc == root:
                break
        for base in bases:
            cand = base / path
            if cand.exists():
                return cand
        return direct

    # ---- system-prompt catalog -----------------------------------------
    def catalog(self) -> str:
        """Render the tool catalog + output contract for the system context."""
        lines = [
            "You are Robodog, an agentic coding assistant running in a terminal.",
            "You perform actions by CALLING TOOLS — never by describing what you would do.",
            "",
            "RULES (strict):",
            "1. To act, your reply MUST contain one or more <tool> blocks, exactly like:",
            '   <tool name="write_file">',
            '     <param name="path">hello.py</param>',
            '     <param name="content">print("hi")</param>',
            "   </tool>",
            "2. NEVER say 'I will create/run/edit ...' without emitting the tool block",
            "   that does it in the SAME reply. Words without tool blocks do nothing.",
            "3. Do NOT wrap tool blocks in markdown code fences. Emit them as plain text.",
            "4. After each tool call you receive a TOOL RESULT, then you continue.",
            "5. Only when the task is FULLY done: reply with your answer and NO <tool>",
            "   blocks. That ends the turn.",
            "6. Only use the tools listed below.",
            "",
            "AVAILABLE TOOLS:",
        ]
        if self.mode == "plan":
            lines.insert(1, "PLAN MODE IS ACTIVE: you may only READ (mutating tools "
                            "are blocked). Investigate, then present a clear "
                            "step-by-step plan as your final message for approval.")
        for t in self._tools.values():
            ps = ", ".join(
                f"{p.name}{'' if p.required else '?'}" for p in t.params
            )
            lines.append(f"- {t.name}({ps}): {t.description}")
            for p in t.params:
                req = "required" if p.required else "optional"
                lines.append(f"    · {p.name} ({req}): {p.description}")
        return "\n".join(lines)


# ========================================================================
# Default tool implementations
# ========================================================================
def default_registry(cwd: Optional[str] = None) -> ToolRegistry:
    reg = ToolRegistry(cwd=cwd)

    # --- helpers for the safety layer -----------------------------------
    def _diff_and_checkpoint(path: Path, old_text: Optional[str], new_text: str):
        """Snapshot before mutation and surface a diff preview to the UI."""
        if reg.checkpointer is not None:
            if old_text is None:
                reg.checkpointer.record_new(path)
            else:
                reg.checkpointer.snapshot(path)
        if reg.on_diff is not None:
            import difflib

            def _nl_terminated(text):
                # A file whose last line has no trailing newline yields a diff
                # line with no '\n'; "".join then GLUES it to the next +/- line
                # (`examples.+**See**`). difflib emits no `\ No newline` marker,
                # so terminate the last line ourselves — this is display-only.
                lines = text.splitlines(keepends=True)
                if lines and not lines[-1].endswith(("\n", "\r")):
                    lines[-1] += "\n"
                return lines

            old_lines = _nl_terminated(old_text or "")
            new_lines = _nl_terminated(new_text)
            diff = "".join(difflib.unified_diff(
                old_lines, new_lines,
                fromfile=f"a/{path.name}", tofile=f"b/{path.name}", n=2))
            if diff:
                reg.on_diff(str(path), diff)

    # --- read_file -------------------------------------------------------
    def _read_file(args):
        path = reg._resolve(args["path"], search=True)
        if not path.exists():
            return f"ERROR: file not found: {path}"
        reg.read_paths.add(str(path))
        text = path.read_text(encoding="utf-8", errors="replace")
        lines = text.splitlines()
        offset = int(args.get("offset", 0) or 0)
        limit = args.get("limit")
        if limit is not None and str(limit).strip():
            lines = lines[offset: offset + int(limit)]
        elif offset:
            lines = lines[offset:]
        numbered = "\n".join(f"{i + offset + 1}\t{ln}" for i, ln in enumerate(lines))
        return numbered or "(empty file)"

    reg.register(Tool(
        name="read_file",
        description="Read a text file. Returns line-numbered content.",
        params=[
            ToolParam("path", "File path (absolute or relative to cwd)."),
            ToolParam("offset", "0-based start line.", required=False),
            ToolParam("limit", "Max lines to read.", required=False),
        ],
        handler=_read_file,
    ))

    def _finalize_write(path: Path, old_text: Optional[str], new_text: str,
                        summary: str) -> str:
        """Checkpoint + diff + write + mark-read + post-edit verify."""
        path.parent.mkdir(parents=True, exist_ok=True)
        _diff_and_checkpoint(path, old_text, new_text)
        path.write_text(new_text, encoding="utf-8")
        reg.read_paths.add(str(path))
        if reg.verify_edits:
            err = verify_syntax(path)
            if err:
                summary += (f"\n\n⚠ VERIFY FAILED: {err}\n"
                            f"The file was saved but does not parse. Fix it now.")
        return summary

    # --- write_file ------------------------------------------------------
    def _write_file(args):
        path = reg._resolve(args["path"])
        content = args.get("content", "")
        existed = path.exists()
        if existed and str(path) not in reg.read_paths:
            return (f"ERROR: refusing to overwrite {path} — read it first with "
                    f"read_file so you know what you are replacing.")
        old_text = path.read_text(encoding="utf-8", errors="replace") if existed else None
        verb = "Overwrote" if existed else "Created"
        return _finalize_write(
            path, old_text, content,
            f"{verb} {path} ({len(content)} bytes, {len(content.splitlines())} lines).")

    reg.register(Tool(
        name="write_file",
        description="Create or overwrite a file with the given content.",
        params=[
            ToolParam("path", "File path to write."),
            ToolParam("content", "Full file content."),
        ],
        handler=_write_file,
        mutating=True,
    ))

    # --- edit_file (string replace) -------------------------------------
    def _edit_file(args):
        path = reg._resolve(args["path"])
        if not path.exists():
            return (f"ERROR: file not found: {path} — it doesn't exist yet, so "
                    "there's nothing to edit. Use write_file to CREATE it.")
        if str(path) not in reg.read_paths:
            return (f"ERROR: refusing to edit {path} — read it first with "
                    f"read_file so old_string matches the real content.")
        original = path.read_text(encoding="utf-8")
        old = args["old_string"]
        new = args.get("new_string", "")
        replace_all = str(args.get("replace_all", "")).lower() in ("1", "true", "yes")
        count = original.count(old)
        note = ""
        if count == 0:
            # Whitespace-tolerant fallback (indentation preserved).
            span = _fuzzy_find(original, old)
            if span is None:
                return (f"ERROR: old_string not found in {path}."
                        + edit_not_found_hint(original, old))
            s, e = span
            updated = original[:s] + new + original[e:]
            note = " (matched with whitespace-normalization)"
            return _finalize_write(path, original, updated,
                                   f"Edited {path} (1 replacement){note}.")
        if count > 1 and not replace_all:
            return (f"ERROR: old_string is not unique in {path} ({count} matches). "
                    f"Add more context or set replace_all=true.")
        updated = original.replace(old, new) if replace_all else original.replace(old, new, 1)
        n = count if replace_all else 1
        return _finalize_write(
            path, original, updated,
            f"Edited {path} ({n} replacement{'s' if n != 1 else ''}).")

    reg.register(Tool(
        name="edit_file",
        description="Replace an exact substring in a file. old_string must be unique unless replace_all=true.",
        params=[
            ToolParam("path", "File path to edit."),
            ToolParam("old_string", "Exact text to find."),
            ToolParam("new_string", "Replacement text.", required=False),
            ToolParam("replace_all", "true to replace every occurrence.", required=False),
        ],
        handler=_edit_file,
        mutating=True,
    ))

    # --- multi_edit (atomic multi-replace on one file) -------------------
    def _multi_edit(args):
        path = reg._resolve(args["path"])
        if not path.exists():
            return f"ERROR: file not found: {path}"
        if str(path) not in reg.read_paths:
            return (f"ERROR: refusing to edit {path} — read it first with read_file.")
        raw = args["edits"]
        # edits format: one 'old_string>>>new_string' pair per line, pairs
        # separated by a line containing only '==='.
        blocks = [b for b in raw.split("\n===\n") if b.strip()]
        pairs = []
        for b in blocks:
            if ">>>" not in b:
                return (f"ERROR: bad edit block (missing '>>>'): {b[:60]}. "
                        f"Format: old text>>>new text, blocks split by a line '==='.")
            old, new = b.split(">>>", 1)
            pairs.append((old.strip("\n"), new.strip("\n")))
        if not pairs:
            return "ERROR: no edits provided."
        original = path.read_text(encoding="utf-8")
        updated = original
        applied = 0
        for i, (old, new) in enumerate(pairs, 1):
            c = updated.count(old)
            if c == 1:
                updated = updated.replace(old, new, 1)
                applied += 1
            else:
                span = _fuzzy_find(updated, old) if c == 0 else None
                if span:
                    s, e = span
                    updated = updated[:s] + new + updated[e:]
                    applied += 1
                else:
                    reason = "not found" if c == 0 else f"not unique ({c} matches)"
                    hint = edit_not_found_hint(updated, old) if c == 0 else (
                        " add more surrounding context so it's unique.")
                    return (f"ERROR: edit #{i} {reason} — NO changes applied "
                            f"(atomic). old text starts: {old[:50]!r}.{hint}")
        return _finalize_write(path, original, updated,
                               f"Applied {applied} edits to {path} atomically.")

    reg.register(Tool(
        name="multi_edit",
        description=("Apply several find/replace edits to ONE file atomically "
                     "(all succeed or none are applied). Provide edits as "
                     "'old text>>>new text' pairs, each pair separated by a line "
                     "containing only '==='. Each old text must be unique."),
        params=[
            ToolParam("path", "File path to edit."),
            ToolParam("edits", "old>>>new pairs separated by '===' lines."),
        ],
        handler=_multi_edit,
        mutating=True,
    ))

    # --- streaming subprocess machinery (shared by bash and run_script) --
    def _kill_tree(proc: subprocess.Popen) -> None:
        """Kill a process and its entire tree (Windows: taskkill; POSIX: killpg)."""
        try:
            if os.name == "nt":
                subprocess.run(
                    ["taskkill", "/F", "/T", "/PID", str(proc.pid)],
                    capture_output=True,
                )
            else:
                os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
        except Exception:
            pass
        try:
            proc.wait(timeout=5)
        except Exception:
            pass

    def _run_streaming(cmd_list: List[str], cwd, timeout: int
                       ) -> Tuple[Optional[int], List[str], List[str], bool]:
        """Run cmd_list, streaming each output line to reg.on_bash_line as it
        arrives. Returns (returncode, stdout_lines, stderr_lines, timed_out).
        On timeout the whole process TREE is killed."""
        popen_kwargs = {}
        if os.name != "nt":
            popen_kwargs["start_new_session"] = True
        proc = subprocess.Popen(
            cmd_list, cwd=str(cwd),
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            text=True, errors="replace", **popen_kwargs,
        )
        out_lines: List[str] = []
        err_lines: List[str] = []

        def _reader(stream, sink: List[str]) -> None:
            try:
                for line in stream:
                    line = line.rstrip("\r\n")
                    sink.append(line)
                    cb = reg.on_bash_line
                    if cb is not None:
                        try:
                            cb(line)
                        except Exception:
                            pass  # a UI error must never kill the reader
            finally:
                try:
                    stream.close()
                except Exception:
                    pass

        t_out = threading.Thread(target=_reader, args=(proc.stdout, out_lines), daemon=True)
        t_err = threading.Thread(target=_reader, args=(proc.stderr, err_lines), daemon=True)
        t_out.start()
        t_err.start()
        timed_out = False
        try:
            proc.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            timed_out = True
            _kill_tree(proc)
        t_out.join(timeout=5)
        t_err.join(timeout=5)
        return proc.returncode, out_lines, err_lines, timed_out

    def _format_run_result(shown_cmd: str, returncode: Optional[int],
                           out_lines: List[str], err_lines: List[str],
                           timed_out: bool, timeout: int,
                           command: str = "") -> str:
        out = "\n".join(out_lines)
        err = "\n".join(err_lines)
        if timed_out:
            parts = [f"ERROR: command timed out after {timeout}s "
                     f"(process tree killed): {shown_cmd}"]
        elif returncode == 0:
            parts = [f"$ {shown_cmd}", "(exit 0)"]
        else:
            # Make failure salient so the agent reacts rather than moving on.
            parts = [f"$ {shown_cmd}",
                     f"⚠ COMMAND FAILED (exit {returncode}) — read the error and fix it."]
        # On truncation, prefer keeping the END of output (errors/tracebacks live there).
        if out.strip():
            parts.append("--- stdout ---\n" + _tail_clamp(out.rstrip()))
        if err.strip():
            parts.append("--- stderr ---\n" + _tail_clamp(err.rstrip()))
        # Shell-syntax hint keys on the ERROR TEXT, not the return code —
        # PowerShell often exits 0 even when a cmdlet in a pipe wasn't found.
        hint = shell_syntax_hint(command or shown_cmd, out + "\n" + err)
        if hint:
            parts.append(hint.lstrip("\n"))
        # Python self-heal hints (failed runs only): hyphenated-skill-dir import
        # loop (fdaskills.jira.jira_call -> jira-call) and json.loads on an
        # already-parsed value — both observed looping 3x on ELSA.
        if returncode not in (0, None):
            for h in (python_import_hint(err, str(reg.cwd)),
                      python_error_hint(err)):
                if h:
                    parts.append(h.lstrip("\n"))
        return "\n".join(parts)

    def _tail_clamp(text: str, limit: int = 12_000) -> str:
        if len(text) <= limit:
            return text
        head = text[: limit // 4]
        tail = text[-3 * limit // 4:]  # keep 3x more of the tail (where errors are)
        return f"{head}\n... [truncated {len(text) - limit} chars] ...\n{tail}"

    # --- bash / run command ---------------------------------------------
    def _bash(args):
        command = args["command"]
        background = str(args.get("background", "")).strip().lower()
        cwd = args.get("cwd")
        cwd_path = reg._resolve(cwd) if cwd else reg.cwd
        if background not in ("", "0", "false", "no", "none"):
            if reg.background_spawn is not None:
                return reg.background_spawn(command, str(cwd_path))
            return ("ERROR: background execution is not available yet — "
                    "run in foreground or split the work.")
        # Dangerous-command guard. An `allow` permission rule pre-approves the
        # exact call, skipping the confirm prompt (deny rules were already
        # enforced in execute() before the handler ran).
        danger = classify_danger(command)
        preapproved = (reg.hooks is not None and
                       reg.hooks.check_permission("bash", {"command": command})[0] == "allow")
        if danger and not preapproved:
            if reg.guard == "confirm" and reg.on_confirm is not None:
                if not reg.on_confirm(command, danger):
                    return f"BLOCKED: user declined the potentially destructive command: {command}"
            elif reg.on_bash_line is not None:
                reg.on_bash_line(f"⚠ running potentially destructive command: {command}")
        timeout = int(args.get("timeout", 120) or 120)
        # Use PowerShell on Windows, sh elsewhere, matching the host shell.
        if os.name == "nt":
            # Auto-fix the bash `&&`/`||` chains models reach for so they run
            # instead of erroring (and the model hallucinating success).
            run_cmd = powershell_translate(command)
            shell_cmd = ["powershell", "-NoProfile", "-NonInteractive", "-Command", run_cmd]
        else:
            shell_cmd = ["/bin/sh", "-c", command]
        rc, out_lines, err_lines, timed_out = _run_streaming(shell_cmd, cwd_path, timeout)
        return _format_run_result(command, rc, out_lines, err_lines, timed_out,
                                  timeout, command=command)

    reg.register(Tool(
        name="bash",
        description="Run a shell command (PowerShell on Windows, sh elsewhere). Returns exit code + output.",
        params=[
            ToolParam("command", "The command line to execute."),
            ToolParam("cwd", "Working directory.", required=False),
            ToolParam("timeout", "Timeout in seconds (default 120).", required=False),
            ToolParam("background", "true to run in background (not available yet).", required=False),
        ],
        handler=_bash,
        mutating=True,
    ))

    # --- run_script ------------------------------------------------------
    _SCRIPT_EXT = {"python": ".py", "powershell": ".ps1", "bash": ".sh"}

    def _run_script(args):
        content = args["content"]
        interpreter = str(args.get("interpreter") or "python").strip().lower()
        timeout = int(args.get("timeout", 120) or 120)
        ext = _SCRIPT_EXT.get(interpreter)
        if ext is None:
            return (f"ERROR: unknown interpreter '{interpreter}'. "
                    f"Use one of: python, powershell, bash.")
        fd, tmp_path = tempfile.mkstemp(
            suffix=ext, prefix="robodog_script_", dir=tempfile.gettempdir())
        try:
            with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as fh:
                fh.write(content)
            if interpreter == "powershell":
                cmd = ["powershell", "-NoProfile", "-NonInteractive",
                       "-ExecutionPolicy", "Bypass", "-File", tmp_path]
            elif interpreter == "bash":
                cmd = ["bash", tmp_path]
            else:
                cmd = [sys.executable, tmp_path]
            shown = f"run_script({interpreter})"
            rc, out_lines, err_lines, timed_out = _run_streaming(cmd, reg.cwd, timeout)
            return _format_run_result(shown, rc, out_lines, err_lines, timed_out, timeout)
        finally:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass

    reg.register(Tool(
        name="run_script",
        description=("Run a multi-line script without shell quoting issues: the "
                     "script text is written to a temp file and executed with the "
                     "chosen interpreter (python, powershell, or bash)."),
        params=[
            ToolParam("content", "The full script text to execute."),
            ToolParam("interpreter", "python | powershell | bash (default python).", required=False),
            ToolParam("timeout", "Timeout in seconds (default 120).", required=False),
        ],
        handler=_run_script,
        mutating=True,
    ))

    # --- run_tests -------------------------------------------------------
    def _detect_test_command() -> Optional[str]:
        if reg.test_command:
            return reg.test_command
        root = reg.cwd
        looks_pytest = ((root / "pytest.ini").exists()
                        or (root / "pyproject.toml").exists()
                        or (root / "setup.py").exists()
                        or any(root.glob("test_*.py"))
                        or (root / "tests").is_dir())
        if looks_pytest:
            import importlib.util
            # Invoke via the running interpreter so PATH gaps don't matter; only
            # if pytest is actually importable, else fall back to unittest.
            if importlib.util.find_spec("pytest") is not None:
                return f'"{sys.executable}" -m pytest -q'
            return f'"{sys.executable}" -m unittest discover -s "{root}"'
        pkg = root / "package.json"
        if pkg.exists():
            try:
                data = json.loads(pkg.read_text(encoding="utf-8"))
                if "test" in (data.get("scripts") or {}):
                    return "npm test"
            except Exception:
                pass
        return None

    def _summarize_tests(rc, out_lines, err_lines) -> str:
        blob = "\n".join(out_lines + err_lines)
        import re
        # pytest: "3 passed, 1 failed in 0.2s"; jest: "Tests: 1 failed, 5 passed"
        m = re.search(r"(\d+)\s+failed", blob)
        p = re.search(r"(\d+)\s+passed", blob)
        head = "PASS" if rc == 0 else "FAIL"
        counts = []
        if p:
            counts.append(f"{p.group(1)} passed")
        if m:
            counts.append(f"{m.group(1)} failed")
        return f"[{head}] " + (", ".join(counts) if counts else f"exit {rc}")

    def _run_tests(args):
        cmd = args.get("command") or _detect_test_command()
        if not cmd:
            return ("ERROR: no test command detected. Pass command= "
                    "(e.g. 'pytest -q') or configure one.")
        timeout = int(args.get("timeout", 600) or 600)
        if os.name == "nt":
            shell_cmd = ["powershell", "-NoProfile", "-NonInteractive", "-Command", cmd]
        else:
            shell_cmd = ["/bin/sh", "-c", cmd]
        rc, out_lines, err_lines, timed_out = _run_streaming(shell_cmd, reg.cwd, timeout)
        if timed_out:
            return f"ERROR: tests timed out after {timeout}s: {cmd}"
        summary = _summarize_tests(rc, out_lines, err_lines)
        detail = _format_run_result(cmd, rc, out_lines, err_lines, False, timeout)
        return f"{summary}\n{detail}"

    reg.register(Tool(
        name="run_tests",
        description=("Run the project's test suite and get a pass/fail summary. "
                     "Auto-detects pytest / npm test, or pass command= explicitly. "
                     "Use after making changes to verify they work."),
        params=[
            ToolParam("command", "Test command (auto-detected if omitted).", required=False),
            ToolParam("timeout", "Timeout in seconds (default 600).", required=False),
        ],
        handler=_run_tests,
        mutating=True,
    ))

    # --- glob ------------------------------------------------------------
    def _glob(args):
        pattern = args["pattern"]
        root = reg._resolve(args.get("path", ".") or ".", search=True)
        matches = sorted(str(p.relative_to(reg.cwd)) if str(p).startswith(str(reg.cwd)) else str(p)
                         for p in root.rglob("*")
                         if p.is_file() and not _is_excluded(p.relative_to(root))
                         and fnmatch.fnmatch(p.name, pattern))
        if not matches:
            return f"No files matching '{pattern}' under {root}."
        return "\n".join(matches[:500])

    reg.register(Tool(
        name="glob",
        description="Find files by name pattern (e.g. *.py) recursively.",
        params=[
            ToolParam("pattern", "Filename glob, e.g. *.py"),
            ToolParam("path", "Root dir to search (default cwd).", required=False),
        ],
        handler=_glob,
    ))

    # --- grep ------------------------------------------------------------
    def _grep(args):
        import re as _re
        pattern = args["pattern"]
        root = reg._resolve(args.get("path", ".") or ".", search=True)
        file_glob = args.get("glob", "*")
        try:
            rx = _re.compile(pattern)
        except _re.error as exc:
            return f"ERROR: bad regex: {exc}"
        results = []
        targets = [root] if root.is_file() else [
            p for p in root.rglob("*")
            if p.is_file() and not _is_excluded(p.relative_to(root))
            and fnmatch.fnmatch(p.name, file_glob)
        ]
        for fp in targets:
            try:
                for i, line in enumerate(fp.read_text(encoding="utf-8", errors="ignore").splitlines(), 1):
                    if rx.search(line):
                        rel = fp.relative_to(reg.cwd) if str(fp).startswith(str(reg.cwd)) else fp
                        results.append(f"{rel}:{i}: {line.strip()[:200]}")
                        if len(results) >= 300:
                            break
            except Exception:
                continue
            if len(results) >= 300:
                break
        return "\n".join(results) if results else f"No matches for /{pattern}/."

    reg.register(Tool(
        name="grep",
        description="Search file contents by regex. Returns file:line: match.",
        params=[
            ToolParam("pattern", "Regular expression."),
            ToolParam("path", "File or dir to search (default cwd).", required=False),
            ToolParam("glob", "Filename filter, e.g. *.py", required=False),
        ],
        handler=_grep,
    ))

    # --- list_dir --------------------------------------------------------
    def _list_dir(args):
        path = reg._resolve(args.get("path", ".") or ".", search=True)
        if not path.exists():
            return f"ERROR: not found: {path}"
        entries = []
        for p in sorted(path.iterdir()):
            entries.append(f"{'d' if p.is_dir() else '-'} {p.name}")
        return "\n".join(entries) or "(empty dir)"

    reg.register(Tool(
        name="list_dir",
        description="List entries in a directory.",
        params=[ToolParam("path", "Directory (default cwd).", required=False)],
        handler=_list_dir,
    ))

    return reg
