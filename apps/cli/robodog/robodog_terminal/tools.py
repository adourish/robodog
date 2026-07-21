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
import re
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


def find_by_basename(root: Path, name: str, limit: int = 5,
                     max_scan: int = 40_000) -> List[str]:
    """Find files named exactly `name` (case-insensitive) anywhere under `root`,
    skipping EXCLUDE_DIRS. Used to turn a read_file 'not found' into a 'did you
    mean …' when the model has the right filename but the wrong directory.
    Uses os.walk with in-place dir pruning so node_modules/.git etc. are never
    descended into; bounded by `max_scan` files so a huge tree can't stall it."""
    name_l = name.lower()
    hits, scanned = [], 0
    try:
        for dirpath, dirnames, filenames in os.walk(str(root)):
            dirnames[:] = [d for d in dirnames
                           if d not in EXCLUDE_DIRS and not d.endswith(".egg-info")]
            scanned += len(filenames)
            for fn in filenames:
                if fn.lower() == name_l:
                    hits.append(os.path.join(dirpath, fn))
                    if len(hits) >= limit:
                        return hits
            if scanned > max_scan:
                break
    except (OSError, RuntimeError):
        pass
    return hits


def read_not_found_hint(root: Path, requested: Path) -> str:
    """A 'did you mean …' for a read_file miss: same basename elsewhere in the
    tree. Returns a hint (leading space) or "" when there's no better path."""
    matches = find_by_basename(root, requested.name)
    # Don't suggest the exact path we already failed to open.
    matches = [m for m in matches if Path(m) != requested]
    if not matches:
        return ""
    if len(matches) == 1:
        return f" Did you mean: {matches[0]}"
    return " Did you mean one of: " + " | ".join(matches)


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


# Outward-facing state changes — POSTing to close a Jira ticket, deleting a
# remote resource, etc. These are HARD TO REVERSE and must never run unattended
# without the user's ok. Detected in BOTH bash and run_script content. Bias is
# toward over-detecting: a false confirm prompt is cheap; a silent ticket-close
# (which actually happened) is not.
_NET_WRITE_PATTERNS = [
    (r"\brequests\.(post|put|delete|patch)\s*\(", "HTTP {m} (requests)"),
    (r"\bhttpx\.(post|put|delete|patch)\s*\(", "HTTP {m} (httpx)"),
    (r"\b(?:session|client|http|api)\.(post|put|delete|patch)\s*\(", "HTTP {m}"),
    # the skill run() dict + urllib Request(method=…): `"method": "POST"`
    (r"""["']method["']\s*[:=]\s*["'](post|put|delete|patch)["']""", "API {m} call"),
    (r"""\bmethod\s*=\s*["'](post|put|delete|patch)["']""", "API {m} call"),
    (r"\bcurl\b[^\n]*?-X\s*(post|put|delete|patch)\b", "curl -X {m}"),
    (r"\bInvoke-(?:RestMethod|WebRequest)\b[^\n]*?-Method\s+(post|put|delete|patch)\b",
     "Invoke-RestMethod -Method {m}"),
    # high-risk endpoints/verbs regardless of how the call is spelled
    (r"/rest/api/[^\s'\"]*/transitions", "Jira issue transition (status change)"),
    (r"\.transition\s*\(|\bdoTransition\b", "issue transition"),
    (r"/issue/[A-Z][A-Z0-9]+-\d+\b[^\n]*\bDELETE\b", "delete a Jira issue"),
]


def classify_network_mutation(content: str) -> Optional[str]:
    """Return a short reason if `content` looks like it makes an outward-facing,
    hard-to-reverse change to an external service (a network write: POST/PUT/
    DELETE/PATCH, a ticket transition, etc.), else None. Read-only calls (GET)
    are never flagged."""
    import re
    for pat, label in _NET_WRITE_PATTERNS:
        m = re.search(pat, content or "", re.IGNORECASE)
        if m:
            verb = next((g.upper() for g in (m.groups() or ())
                         if g and g.lower() in ("post", "put", "delete", "patch")), "")
            return label.replace("{m}", verb or "write")
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
    if os.name != "nt":
        return command
    # No &&/|| chain: still translate Unix pipe filters (| head/tail/wc).
    if "&&" not in command and "||" not in command:
        return translate_unix_pipe_filters(command)
    ands = _split_top_level(command, "&&")
    ors = _split_top_level(command, "||")
    if len(ands) > 1 and len(ors) == 1:
        parts, cond = ands, "if ($?)"
    elif len(ors) > 1 and len(ands) == 1:
        parts, cond = ors, "if (-not $?)"
    else:
        return command   # mixed / operator only inside quotes — leave it
    if any(not p.strip() for p in parts):
        return command   # empty segment -> malformed, don't touch
    # Translate pipe filters WITHIN each chain segment so the parens they add
    # stay local (translating the whole string first would let the paren cross
    # the `&&` split boundary and unbalance the `if ($?) { }` block).
    chain = [translate_unix_pipe_filters(p.strip()) for p in parts]
    out = chain[-1]
    for seg in reversed(chain[:-1]):
        out = f"{seg}; {cond} {{ {out} }}"
    return out


def _split_pipes_top_level(command: str) -> List[str]:
    """Split on a single top-level `|` — never inside quotes, and never on the
    `||` operator (kept intact). Returns [command] when no splittable pipe."""
    parts, buf = [], []
    i, n = 0, len(command)
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
        if ch == "|":
            if i + 1 < n and command[i + 1] == "|":   # `||` operator — keep whole
                buf.append("||")
                i += 2
                continue
            parts.append("".join(buf))
            buf = []
            i += 1
            continue
        buf.append(ch)
        i += 1
    parts.append("".join(buf))
    return parts


_PIPE_FILTER_RE = re.compile(r"^(head|tail)(?:\s+-n\s+(\d+)|\s+-(\d+))?$", re.IGNORECASE)
_PIPE_WC_RE = re.compile(r"^wc\s+-l$", re.IGNORECASE)
# `grep [flags] PATTERN` in a pipe — flags captured, PATTERN kept VERBATIM so a
# quoted pattern with spaces (grep -i "foo bar") survives intact.
_PIPE_GREP_RE = re.compile(r"^grep\s+((?:-[A-Za-z]+\s+)*)(.+)$", re.IGNORECASE)


def _translate_filter_segment(seg: str) -> Optional[str]:
    """A single pipe segment that is EXACTLY a Unix `head`/`tail`/`wc -l`/`grep`
    filter -> its PowerShell equivalent. None if the segment isn't a bare filter
    (so `head file.txt` is never touched)."""
    s = seg.strip()
    m = _PIPE_FILTER_RE.match(s)
    if m:
        n = m.group(2) or m.group(3) or "10"   # bare head/tail default to 10
        sel = "-First" if m.group(1).lower() == "head" else "-Last"
        return f"Select-Object {sel} {n}"
    if _PIPE_WC_RE.match(s):
        return "Measure-Object -Line | Select-Object -ExpandProperty Lines"
    g = _PIPE_GREP_RE.match(s)
    if g:
        flags, pattern = g.group(1) or "", g.group(2).strip()
        # A trailing file arg means it's `grep pattern file`, not a pipe filter —
        # leave it (Select-String reads the pipeline, not a file, here).
        if pattern:
            invert = "v" in flags.replace(" ", "").replace("-", "")
            return f"Select-String {'-NotMatch ' if invert else ''}{pattern}"
    return None


def translate_unix_pipe_filters(command: str) -> str:
    """Rewrite trailing/embedded `| head -N`, `| tail -N`, `| wc -l` to the
    PowerShell equivalents so `git log | head -20` actually runs on Windows
    instead of failing on the missing `head` cmdlet (models reach for these
    constantly and don't heed the hint). Quote-aware; `||` is preserved; only
    segments that are EXACTLY a bare filter are converted.

    The upstream is wrapped in parentheses — `(git log) | Select-Object -First
    20` — so the native producer runs to COMPLETION and exits 0. Without the
    parens, `Select-Object -First` stops the pipeline early, kills git, and the
    command reports a false non-zero exit even though it worked. No-op off
    Windows or when there's no bare filter to translate."""
    if os.name != "nt" or "|" not in command:
        return command
    segs = _split_pipes_top_level(command)
    if len(segs) < 2:
        return command
    # A filter must have upstream (idx > 0) to filter — a leading `head` reads
    # stdin and isn't our case. Find the first translatable filter segment.
    translated = [(_translate_filter_segment(s) if i > 0 else None)
                  for i, s in enumerate(segs)]
    first = next((i for i, t in enumerate(translated) if t is not None), None)
    if first is None:
        return command
    upstream = "|".join(segs[:first]).strip()
    tail = [translated[i] if translated[i] is not None else segs[i].strip()
            for i in range(first, len(segs))]
    return f"({upstream}) | " + " | ".join(tail)


def shell_syntax_hint(command: str, combined: str) -> str:
    """A one-line fix for the shell-syntax mistakes models repeat on Windows
    PowerShell — appended to a FAILED command result so the model self-corrects
    instead of looping. `combined` is the command's stdout+stderr. Module-level
    (not a bash closure) so it's directly testable regardless of what Unix
    tools happen to be on the host PATH."""
    if os.name != "nt":
        return ""
    low = (combined or "").lower()
    cmd_low = command.lower()
    import re as _re
    _failed = any(s in low for s in (
        "error", "not found", "not recognized", "could not find",
        "exception", "cannot find", "is not a valid"))
    # `2>/dev/null` — PowerShell has no /dev/null; it writes stderr to a file
    # literally named C:\dev\null and dies before the pipe even runs. Key on the
    # REDIRECTION (not a bare mention) so an echo of "/dev/null" isn't flagged.
    if _re.search(r"\d?\s*>\s*/dev/null", command):
        return ("\nHINT: `/dev/null` doesn't exist on Windows — PowerShell tried "
                "to write to C:\\dev\\null and failed. Discard stderr with "
                "`2>$null`, or all output with `| Out-Null`.")
    # Unix `find PATH -name/-type ...` — not available (cmd's find.exe is a
    # different, text-search tool). This trips models constantly on Windows.
    if _failed and _re.search(
            r"(?:^|[|&;]|\s)find\s+\S.*\s-(?:name|type|iname|path|regex)\b",
            command, _re.IGNORECASE):
        return ("\nHINT: Unix `find` isn't available here. List files with "
                "`Get-ChildItem -Recurse -Filter *.py -ErrorAction "
                "SilentlyContinue` and filter with "
                "`Where-Object { $_.FullName -match 'idp' }` "
                "(use -match/-ilike, not `grep`).")
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
    if "if not exist" in cmd_low or "if exist" in cmd_low or "%errorlevel%" in cmd_low:
        return ("\nHINT: that's cmd.exe syntax in PowerShell. Use "
                "`if (-not (Test-Path X)) { ... }` instead of `if not exist X`, "
                "and `New-Item -ItemType Directory -Force X` to mkdir.")
    # `dir /b`, `dir /s /b` — cmd.exe switches; PowerShell's dir is Get-ChildItem
    # and treats `/b` as a second path argument (DirArgumentError / "path2").
    if _re.search(r"\bdir\b[^\n]*\s/[a-z]\b", command, _re.IGNORECASE):
        return ("\nHINT: `dir /b` / `dir /s` are cmd.exe switches — PowerShell's "
                "`dir` is Get-ChildItem and reads `/b` as a path. Use "
                "`Get-ChildItem -Name` (bare names, like /b), "
                "`Get-ChildItem -Recurse -Name` (recursive, like /s /b), and "
                "add `-Filter *.py` to match a pattern.")
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
    # src-layout / local package not on sys.path: Python failed to import the TOP
    # package (single-segment miss) but a directory by that name exists here — it
    # just isn't importable. (`No module named 'src'` while `src/` sits in cwd.)
    if len(parts) == 1 and (base / parts[0]).is_dir():
        pkg = parts[0]
        return (f"\nHINT: '{pkg}' exists as a directory here but isn't on Python's "
                f"path, so `import {pkg}` fails. Run from the project root with the "
                f"root on the path — PowerShell: `$env:PYTHONPATH='.'; python -m "
                f"pytest` — or `pip install -e .` if it's a package. (A missing "
                f"{pkg}/__init__.py can also cause this.)")
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
    # A well-known dev/test tool isn't installed for THIS interpreter. Seen when
    # the model flip-flops `python` vs `py` (which resolve to different installs,
    # one lacking pytest) — `<python>: No module named pytest`.
    _KNOWN_TOOLS = {"pytest", "pip", "black", "flake8", "mypy", "coverage",
                    "tox", "pylint", "isort", "poetry", "pipenv", "ruff",
                    "virtualenv", "nose", "twine", "build"}
    mt = _re.search(r"No module named ['\"]?([\w.]+)", err)
    if mt and mt.group(1).split(".")[0] in _KNOWN_TOOLS:
        top = mt.group(1).split(".")[0]
        return (f"\nHINT: '{top}' isn't installed for the Python interpreter you "
                f"ran. Install it with `python -m pip install {top}`, and use the "
                f"SAME interpreter throughout — `py` and `python` can point at "
                f"different installs (one may have {top}, the other not). "
                f"`python -m {top} …` runs it against the current interpreter.")
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
    # Does this tool run arbitrary shell/code/commands (so it could make an
    # outward-facing network write or a destructive local command)? DEFAULT
    # True — fail-safe: a newly-added tool is guarded until explicitly marked
    # safe. Pure read/local-file tools set executes=False to skip the guard.
    executes: bool = True

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
        # files Read this session -> mtime at read time (read-before-edit +
        # freshness: refuse to edit a file changed on disk since we last saw it).
        self.read_paths: dict = {}
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
        # Outward-facing network-WRITE guard (POST/PUT/DELETE to a remote API —
        # e.g. closing a Jira ticket). Independent of `guard` because the shell
        # YOLO default must NOT extend to irreversible external changes.
        #   "confirm" (default) — require approval; BLOCK if it can't be obtained
        #   "deny"              — always block network writes (read-only remote)
        #   "allow"             — permit unattended (opt-in, old behavior)
        self.net_guard: str = (os.environ.get("ROBODOG_NET_WRITES", "confirm")
                               .strip().lower() or "confirm")
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
            # (1.3) Hallucinated / misspelled tool name -> suggest the closest
            # real one (write_file vs write_files) so the model self-corrects.
            import difflib
            near = difflib.get_close_matches(name, list(self._tools), n=1, cutoff=0.6)
            hint = f" Did you mean '{near[0]}'?" if near else ""
            return (f"ERROR: unknown tool '{name}'.{hint} "
                    f"Available tools: {', '.join(sorted(self._tools))}")
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
        # Central safety checkpoint: EVERY code-executing tool passes through the
        # danger/network-write guard here, so a new tool can't be added ungated.
        if getattr(tool, "executes", True):
            blocked = self._guard_exec(name, args)
            if blocked is not None:
                return blocked
        result = tool.run(args)
        if self.hooks is not None:
            self.hooks.run_post(name, args, result)
        return result

    def _guard_exec(self, name: str, args: Dict[str, str]) -> Optional[str]:
        """Central gate for code-executing tools. Returns a BLOCKED message if
        the call must NOT run, else None. Two layers: outward-facing network
        writes (confirm by default; fail-safe BLOCK when unconfirmable — e.g.
        headless or subagent) and destructive local shell commands. A permission
        `allow` rule pre-approves and skips both. Scans every string arg so the
        code lives wherever the tool puts it (command / content / …)."""
        # A permission allow-rule is an explicit pre-approval.
        if self.hooks is not None and \
                self.hooks.check_permission(name, args)[0] == "allow":
            return None
        content = "\n".join(str(v) for v in args.values() if isinstance(v, str))
        if "command" in args:
            display = str(args["command"])
        elif "content" in args:
            snip = str(args["content"])
            display = (f"{name}:\n"
                       + (snip if len(snip) <= 800 else snip[:800] + " …(truncated)"))
        else:
            display = f"{name} {content[:200]}"
        # --- outward-facing network write (e.g. closing a Jira ticket) -------
        netmut = classify_network_mutation(content)
        if netmut:
            mode = self.net_guard or "confirm"
            if mode == "deny":
                return (f"BLOCKED: outward-facing change refused — {netmut}. "
                        f"Network writes are denied (ROBODOG_NET_WRITES=deny). "
                        f"Re-run interactively with net-writes set to confirm/allow "
                        f"if this is intended.")
            if mode != "allow":   # "confirm" (default) or anything unrecognized
                reason = f"outward-facing change to an external service — {netmut}"
                if self.on_confirm is not None:
                    if not self.on_confirm(display, reason):
                        return f"BLOCKED: user declined the outward-facing change ({netmut})."
                else:
                    return (f"BLOCKED: outward-facing change ({netmut}) needs confirmation, "
                            f"but nothing here can prompt for it (headless or subagent "
                            f"context). Run it from the interactive session, or set "
                            f"ROBODOG_NET_WRITES=allow to permit unattended writes.")
        # --- destructive local shell command (rm -rf, git reset --hard, …) ---
        danger = classify_danger(content)
        if danger:
            if self.guard == "confirm" and self.on_confirm is not None:
                if not self.on_confirm(display, danger):
                    return f"BLOCKED: user declined the potentially destructive command: {display}"
            elif self.on_bash_line is not None:
                self.on_bash_line(f"⚠ running potentially destructive command: {display}")
        return None

    # ---- read/freshness tracking ----------------------------------------
    def _mark_read(self, path: Path) -> None:
        """Record that `path` was read (or written by us) and its current mtime,
        so a later edit can tell whether the file changed underneath us."""
        try:
            mtime = path.stat().st_mtime if path.exists() else 0.0
        except OSError:
            mtime = 0.0
        self.read_paths[str(path)] = mtime

    def _stale_since_read(self, path: Path) -> bool:
        """True if `path` was read this session but has since changed on disk
        (an external edit) — so editing now would clobber content we never saw."""
        recorded = self.read_paths.get(str(path))
        if recorded is None:
            return False
        try:
            return path.stat().st_mtime > recorded + 1e-6
        except OSError:
            return False

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
            base = reg._project_root() or reg.cwd
            return f"ERROR: file not found: {path}" + read_not_found_hint(base, path)
        reg._mark_read(path)
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
        executes=False,
    ))

    def _finalize_write(path: Path, old_text: Optional[str], new_text: str,
                        summary: str) -> str:
        """Checkpoint + diff + write + mark-read + post-edit verify."""
        path.parent.mkdir(parents=True, exist_ok=True)
        _diff_and_checkpoint(path, old_text, new_text)
        path.write_text(new_text, encoding="utf-8")
        reg._mark_read(path)
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
        if existed and reg._stale_since_read(path):
            reg._mark_read(path)
            return (f"ERROR: {path} CHANGED ON DISK since you last read it — "
                    f"re-read it with read_file before overwriting (it may contain "
                    f"changes you never saw).")
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
        executes=False,
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
        if reg._stale_since_read(path):
            reg._mark_read(path)  # adopt the new state so the re-read isn't a loop
            return (f"ERROR: {path} CHANGED ON DISK since you last read it — "
                    f"something edited it outside this tool. Re-read it with "
                    f"read_file so your edit matches the current content (editing "
                    f"now could clobber changes you never saw).")
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
        executes=False,
        mutating=True,
    ))

    # --- multi_edit (atomic multi-replace on one file) -------------------
    def _multi_edit(args):
        path = reg._resolve(args["path"])
        if not path.exists():
            return f"ERROR: file not found: {path}"
        if str(path) not in reg.read_paths:
            return (f"ERROR: refusing to edit {path} — read it first with read_file.")
        if reg._stale_since_read(path):
            reg._mark_read(path)
            return (f"ERROR: {path} CHANGED ON DISK since you last read it — "
                    f"re-read it with read_file before editing (it may contain "
                    f"changes you never saw).")
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
        executes=False,
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
        # NOTE: the danger/network-write guard runs centrally in
        # ToolRegistry.execute() before this handler, so bash can't reach here
        # with an unapproved destructive/outward-facing call.
        if background not in ("", "0", "false", "no", "none"):
            if reg.background_spawn is not None:
                return reg.background_spawn(command, str(cwd_path))
            return ("ERROR: background execution is not available yet — "
                    "run in foreground or split the work.")
        timeout = int(args.get("timeout", 120) or 120)
        # Use PowerShell on Windows, sh elsewhere, matching the host shell.
        if os.name == "nt":
            # Auto-fix the bash-isms models reach for on Windows so they run
            # instead of erroring: `&&`/`||` chains -> if ($?)/if (-not $?), and
            # `| head/tail/wc` -> Select-Object/Measure-Object (handled per chain
            # segment inside powershell_translate).
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
        # NOTE: the danger/network-write guard runs centrally in
        # ToolRegistry.execute() before this handler (run_script was the escape
        # hatch a model used to POST a Jira ticket closed with no confirmation).
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
        executes=False,
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
        executes=False,
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
        executes=False,
    ))

    return reg
