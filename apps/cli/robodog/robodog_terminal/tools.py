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
import time
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


def edit_not_found_hint(original: str, old: str, new: str = "") -> str:
    """
    Explain WHY an edit_file old_string didn't match, so the model can self-
    correct instead of re-submitting the same broken edit. Returns a short hint
    string (leading space, no trailing newline), or "" if nothing useful found.

    Detects, in priority order: the edit was ALREADY applied (idempotency); the
    text is present but with different line endings; present but with different
    leading/trailing whitespace; a non-unique whitespace-normalized match; or
    shows the closest actual line in the file with its line number.
    """
    if not old.strip():
        return " old_string is empty — nothing to find."
    # 0. Already applied: old_string is gone but new_string is present. On a
    # retry this means the edit already succeeded — resubmitting loops forever.
    # Require a SUBSTANTIAL new_string (>=8 non-space chars) so a short/common
    # replacement like "x" or "0" doesn't false-positive against unrelated text.
    if (new and len(new.strip()) >= 8 and new in original and old not in original):
        return (" the new_string is ALREADY present and old_string is gone — this "
                "edit was likely applied already. Skip it and move on (re-read the "
                "file if unsure).")
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
    """A 'did you mean …' for a read_file miss. In priority order: the SAME
    basename elsewhere in the tree; else — when the parent directory exists — the
    CLOSEST-named sibling(s) (a typo/near-miss like RUNBOOK-serioplus-stack vs
    RUNBOOK-build-run-serioplus), else a sample of what the directory contains.
    Returns a hint (leading space) or "" when there's nothing useful."""
    matches = find_by_basename(root, requested.name)
    matches = [m for m in matches if Path(m) != requested]
    if matches:
        if len(matches) == 1:
            return f" Did you mean: {matches[0]}"
        return " Did you mean one of: " + " | ".join(matches)
    # Parent dir exists but the file doesn't — fuzzy-match against its siblings.
    parent = requested.parent
    try:
        if parent.is_dir():
            import difflib
            siblings = sorted(p.name for p in parent.iterdir() if p.is_file())
            if siblings:
                near = difflib.get_close_matches(requested.name, siblings, n=3, cutoff=0.5)
                if near:
                    paths = " | ".join(str(parent / n) for n in near)
                    return f" Did you mean: {paths}"
                sample = ", ".join(siblings[:10])
                more = f" (+{len(siblings) - 10} more)" if len(siblings) > 10 else ""
                return (f" {parent} exists but has no '{requested.name}'. "
                        f"It contains: {sample}{more}")
    except OSError:
        pass
    return ""


def dir_not_found_hint(requested: Path) -> str:
    """A 'did you mean …' for a list_dir miss on a directory: when the parent
    exists, fuzzy-match the name against its SUBDIRECTORIES (a model looking for
    `src/tests` when the dir is `src/test`), else list the subdirs that exist.
    Returns a hint (leading space) or "". Assumes `requested` doesn't exist."""
    parent = requested.parent
    try:
        if parent.is_dir():
            subdirs = sorted(p.name for p in parent.iterdir() if p.is_dir())
            if subdirs:
                import difflib
                near = difflib.get_close_matches(requested.name, subdirs, n=3, cutoff=0.4)
                if near:
                    return " Did you mean: " + " | ".join(str(parent / n) for n in near)
                sample = ", ".join(subdirs[:12])
                more = f" (+{len(subdirs) - 12} more)" if len(subdirs) > 12 else ""
                return (f" {parent} has no '{requested.name}' subdir. "
                        f"Its subdirs: {sample}{more}")
            return f" {parent} exists but has no subdirectories."
    except OSError:
        pass
    return ""


def _clamp(text: str, limit: int = MAX_OUTPUT) -> str:
    if len(text) <= limit:
        return text
    head = text[: limit // 2]
    tail = text[-limit // 2:]
    return f"{head}\n... [truncated {len(text) - limit} chars] ...\n{tail}"


# Commands that can destroy data or push irreversibly — flagged even in YOLO.
# (pattern, risk) — goose-style risk tiers (its security/patterns.rs tags each
# THREAT_PATTERN with a RiskLevel instead of one flat "dangerous" bucket).
# "high" = irreversible / hard-to-recover (deleted data, rewritten history,
# wiped disk); "medium" = disruptive or risky practice but recoverable/local.
# ROADMAP Phase 4.5 wanted an LLM risk-grader for this; a deterministic tier
# on the existing patterns gets most of the value ("only HIGH confirms") for
# free — see _guard_exec below.
_DANGER_SPECS = [
    (r"\brm\s+-[a-z]*[rf]", "high"),
    (r"\brmdir\s+/s", "high"),
    (r"\bdel\s+/[a-z]*[fs]", "high"),
    (r"\bRemove-Item\b.*-Recurse", "high"),
    (r"\bgit\s+push\b.*(--force|-f)\b", "high"),
    (r"\bgit\s+reset\s+--hard", "high"),
    (r"\bgit\s+clean\s+-[a-z]*f", "medium"),
    # disk format only — NOT the `--format`/`-format` flag common in git/log/etc.
    (r"(?<!-)\bformat\s+([a-zA-Z]:|/[a-z])", "high"),
    (r"\bmkfs\b", "high"),
    (r"\bdd\s+if=", "high"),
    (r":\(\)\s*\{", "high"),  # fork bomb
    (r"\b(shutdown|reboot)\b", "medium"),
    (r">\s*/dev/sd", "high"),
    (r"\bchmod\s+-R\s+777", "medium"),
    (r"\bDrop-Item\b", "medium"),
    (r"\bTruncate\b.*Table", "high"),
    (r"\bDROP\s+(TABLE|DATABASE)\b", "high"),
]
_DANGER_PATTERNS = [pat for pat, _risk in _DANGER_SPECS]
_DANGER_RISK: Dict[str, str] = dict(_DANGER_SPECS)


def classify_danger(command: str) -> Optional[str]:
    """Return a short reason (the matched pattern) if the command looks
    destructive, else None. Pair with danger_risk() for its tier."""
    import re
    for pat in _DANGER_PATTERNS:
        if re.search(pat, command, re.IGNORECASE):
            return pat
    return None


def danger_risk(reason: str) -> str:
    """'low' | 'medium' | 'high' tier for a classify_danger() reason. A reason
    this table doesn't recognize defaults to 'high' — fail toward asking."""
    return _DANGER_RISK.get(reason, "high")


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
    # Outward-facing git/GitHub — publishing to a SHARED remote is hard to undo
    # (an agent force-pushed to origin unprompted: gemini-cli#5894).
    (r"\bgit\s+push\b", "git push (publish commits to a remote)"),
    (r"\bgh\s+(?:pr|issue|release)\s+create\b", "create a GitHub PR/issue/release"),
    (r"\bgh\s+(?:pr|issue)\s+(?:close|merge|comment)\b", "modify a GitHub PR/issue"),
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


def _sub_outside_quotes(rx: "re.Pattern", repl, command: str) -> str:
    """Apply `rx.sub(repl, …)` only to the UNQUOTED spans of `command`, leaving
    text inside '…' or "…" untouched. Needed because the alias/redirect rewrites
    are regex-based and would otherwise corrupt a quoted commit message / echo /
    doc string that happens to contain `2>nul`, `curl`, etc."""
    result: List[str] = []
    unq: List[str] = []
    q = None

    def flush() -> None:
        if unq:
            result.append(rx.sub(repl, "".join(unq)))
            unq.clear()

    for ch in command:
        if q:
            result.append(ch)
            if ch == q:
                q = None
        elif ch in ("'", '"'):
            flush()
            q = ch
            result.append(ch)
        else:
            unq.append(ch)
    flush()
    return "".join(result)


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


_CURL_RE = re.compile(r"(^|[|&;{(]\s*)curl(?=\s)", re.IGNORECASE)


def _split_connectors(command: str) -> List[str]:
    """Split into [seg, conn, seg, conn, …] on top-level `&&` / `||` / `;`
    (quote-aware). A grep/head/tail COMMAND lives at the start of a connector
    segment — `cd repo && grep …` — so callers translate each segment's command
    and rejoin the connectors verbatim."""
    pieces: List[str] = []
    buf: List[str] = []
    i, n = 0, len(command)
    q = None
    while i < n:
        ch = command[i]
        if q:
            buf.append(ch)
            if ch == q:
                q = None
            i += 1
            continue
        if ch in ("'", '"'):
            q = ch
            buf.append(ch)
            i += 1
            continue
        if command[i:i + 2] in ("&&", "||"):
            pieces.append("".join(buf))
            pieces.append(command[i:i + 2])
            buf = []
            i += 2
            continue
        if ch == ";":
            pieces.append("".join(buf))
            pieces.append(";")
            buf = []
            i += 1
            continue
        buf.append(ch)
        i += 1
    pieces.append("".join(buf))
    return pieces


def split_command_segments(command: str) -> List[str]:
    """Break a compound shell command into its independent top-level commands —
    split on `&&`, `||`, `;`, and `|` (quote-aware, via `_split_connectors` +
    `_split_pipes_top_level`). Used by hooks.py's permission guard so a chained
    command (`git status && rm -rf ~`) is judged segment-by-segment instead of
    as one opaque string: an allow-rule like `bash(git *)` must not become a
    blanket bypass for whatever runs after `&&`, and a deny-rule for `rm -rf *`
    must still catch it when it isn't the first thing on the line — fnmatch's
    `*` otherwise happily matches straight through a chain operator."""
    segments: List[str] = []
    for chunk in _split_connectors(command)[0::2]:   # drop the &&/||/; tokens
        segments.extend(_split_pipes_top_level(chunk))
    return [s.strip() for s in segments if s.strip()]


def _translate_grep_command(seg: str) -> Optional[str]:
    """A `grep [flags] PATTERN [FILE/DIR…]` COMMAND -> its PowerShell equivalent.
    `grep` isn't on Windows and models reach for it constantly (incl. `cd x &&
    grep -rn …`). Non-recursive with a file -> `Select-String -Pattern P -Path F`
    (already prints file:line:text). Recursive (`-r`) -> `Get-ChildItem -Recurse
    -File DIR | Select-String -Pattern P`. `-A/-B/-C N` -> -Context, `-v` ->
    -NotMatch, `-l` -> -List; -n/-i/-H/-E/-w are Select-String defaults. Trailing
    redirects are preserved. Returns None for `grep P` with NO file (that's the
    `| grep` stdin filter, handled by _translate_filter_segment)."""
    s = seg.strip()
    if not re.match(r"^grep\b", s, re.IGNORECASE):
        return None
    toks = _tokenize_ws(s)[1:]
    recursive = invert = list_files = False
    ctx = pattern = None
    paths: List[str] = []
    redirs: List[str] = []
    i, n = 0, len(toks)
    while i < n:
        t = toks[i]
        if _REDIR_TOK_RE.match(t):
            redirs.append(t)
            if re.fullmatch(r"\d*>{1,2}|&>|<", t) and i + 1 < n:
                redirs.append(toks[i + 1])   # bare operator -> its target
                i += 2
                continue
            i += 1
            continue
        if pattern is None and t.startswith("-") and len(t) > 1:
            body = t[1:]
            if body in ("A", "B", "C") and i + 1 < n and toks[i + 1].isdigit():
                ctx = (body, toks[i + 1])   # (A=after, B=before, C=both)
                i += 2
                continue
            for c in body:
                if c in ("r", "R"):
                    recursive = True
                elif c == "v":
                    invert = True
                elif c == "l":
                    list_files = True
            i += 1
            continue
        if pattern is None:
            pattern = t
            i += 1
            continue
        paths.append(t)
        i += 1
    if pattern is None:
        return None
    ss = ["Select-String"]
    if invert:
        ss.append("-NotMatch")
    if list_files:
        ss.append("-List")
    if ctx:
        flag, num = ctx
        ss.append(f"-Context 0,{num}" if flag == "A"
                  else f"-Context {num},0" if flag == "B"
                  else f"-Context {num}")
    ss.append(f"-Pattern {pattern}")
    tail = (" " + " ".join(redirs)) if redirs else ""
    if recursive:
        target = paths[0] if paths else "."
        gci = (f"Get-ChildItem -Path {target} -Recurse -File "
               f"-ErrorAction SilentlyContinue")
        return f"{gci} | {' '.join(ss)}{tail}"
    if not paths:
        return None                      # `grep P` alone -> stdin filter, not us
    ss.append("-Path " + " ".join(paths))
    return " ".join(ss) + tail


# Standalone `head`/`tail` at command position (NOT a pipe filter) reading ONE
# file — `head -20 f`, `tail -n 5 f`, `head f`. Windows has no head/tail, so map
# to Get-Content. Multi-file (`head a b`, whose Unix output interleaves `==> a
# <==` headers) is left alone — no clean one-liner equivalent; the hint covers it.
_HEAD_TAIL_FILE_RE = re.compile(
    r"^(head|tail)(?:\s+-n\s+(\d+)|\s+-(\d+))?\s+(?!-)([^\s|]+)\s*$", re.IGNORECASE)


def _head_tail_with_file(seg: str) -> Optional[str]:
    m = _HEAD_TAIL_FILE_RE.match(seg.strip())
    if not m:
        return None
    n = m.group(2) or m.group(3) or "10"
    flag = "-TotalCount" if m.group(1).lower() == "head" else "-Tail"
    return f"Get-Content {m.group(4)} {flag} {n}"


def translate_windows_aliases(command: str) -> str:
    """On Windows, `curl` is a PowerShell ALIAS for Invoke-WebRequest, which
    chokes on real curl flags (`curl -s -o x -w y`). Point it at the real
    `curl.exe`. Also translates a standalone `grep PATTERN FILE` (code search) to
    `Select-String` — `grep` isn't a Windows command. Only command-position
    `curl`, and only grep segments that carry a FILE arg (the `| grep PATTERN`
    pipe filter is handled elsewhere)."""
    if os.name != "nt":
        return command
    out = command
    if "curl" in out.lower():
        out = _sub_outside_quotes(
            _CURL_RE, lambda m: m.group(1) + "curl.exe", out)
    # grep/head/tail with a FILE arg are a COMMAND, so they live at the start of a
    # connector segment (`cd repo && grep -rn x src/`) — process each segment's
    # command position. A grep LATER in a pipe (`cat x | grep p`) reads stdin (a
    # filter handled by translate_unix_pipe_filters), so only the FIRST pipe
    # sub-segment of each connector segment is a candidate.
    if any(k in out.lower() for k in ("grep", "head", "tail")):
        pieces = _split_connectors(out)
        for idx in range(0, len(pieces), 2):        # even indices = command segs
            seg = pieces[idx]
            psegs = _split_pipes_top_level(seg)
            first = psegs[0]
            lead = first[:len(first) - len(first.lstrip())]
            repl = _translate_grep_command(first) or _head_tail_with_file(first)
            if repl is not None:
                psegs[0] = lead + repl
                pieces[idx] = "|".join(psegs)
        out = "".join(pieces)
    return out


# `2>nul`/`>nul` (cmd) and `2>/dev/null`/`>/dev/null` (unix) both BREAK in
# PowerShell: `nul` is a reserved DOS device, so PS opens a *file* named `nul` and
# dies ("FileStream was asked to open a device that was not a file"); `/dev/null`
# becomes C:\dev\null. PowerShell's null sink is `$null`. Rewrite the redirect
# TARGET (keep the operator: 2>, >, >>, 1>). Lookahead requires a real redirect
# endpoint so a filename like `nul.txt` is never touched. `2>&1` never matches.
_NULL_REDIR_RE = re.compile(
    r"(?P<op>\d*>{1,2})\s*(?:/dev/null|nul)(?=\s|$|[|;&])", re.IGNORECASE)


def translate_null_redirects(command: str) -> str:
    if os.name != "nt":
        return command
    return _sub_outside_quotes(
        _NULL_REDIR_RE, lambda m: f"{m.group('op')}$null", command)


def _tokenize_ws(s: str) -> List[str]:
    """Whitespace-split, keeping quoted spans intact (quotes retained)."""
    toks: List[str] = []
    buf: List[str] = []
    q = None
    for ch in s.strip():
        if q:
            buf.append(ch)
            if ch == q:
                q = None
        elif ch in ("'", '"'):
            q = ch
            buf.append(ch)
        elif ch.isspace():
            if buf:
                toks.append("".join(buf))
                buf = []
        else:
            buf.append(ch)
    if buf:
        toks.append("".join(buf))
    return toks


_DIR_HEAD_RE = re.compile(r"^\s*dir\b", re.IGNORECASE)
_REDIR_TOK_RE = re.compile(r"^(?:\d*>{1,2}|&>|<)")
# `dir /b` / `dir /s /b` are cmd.exe switches; PowerShell's `dir` (Get-ChildItem)
# reads `/b` as a second path and dies ("Second path fragment must not be a
# drive"). Translate the common single-path form so it runs; bail to the hint for
# anything with an unknown switch or >1 path/glob (Get-ChildItem can't take two
# positional filespecs cleanly).
_DIR_SWITCHES = {"/b": "-Name", "/s": "-Recurse", "/a": "-Force"}


def translate_dir_switches(command: str) -> str:
    if os.name != "nt" or not _DIR_HEAD_RE.match(command):
        return command
    segs = _split_pipes_top_level(command)
    if not _DIR_HEAD_RE.match(segs[0]):
        return command
    toks = _tokenize_ws(segs[0])
    out = ["Get-ChildItem"]
    tail: List[str] = []          # redirects, appended after the switches
    paths = 0
    saw_switch = False
    for t in toks[1:]:
        if re.fullmatch(r"/[A-Za-z]", t):
            repl = _DIR_SWITCHES.get(t.lower())
            if repl is None:
                return command      # unknown cmd switch -> let the hint guide
            if repl not in out:
                out.append(repl)
            saw_switch = True
        elif _REDIR_TOK_RE.match(t):
            tail.append(t)
        else:
            paths += 1
            if paths > 1:
                return command      # >1 filespec -> GCI can't; hint instead
            out.insert(1, t)        # path right after Get-ChildItem
    if not saw_switch:
        return command              # plain `dir` already works in PowerShell
    segs[0] = " ".join(out + tail)
    return "|".join(segs)


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
    # Null-device redirect that slipped past translation, OR a non-redirect use
    # of a reserved device. `2>nul`/`2>/dev/null` are auto-rewritten to `2>$null`
    # now, so key this FALLBACK on the actual device ERROR (not the command text)
    # — otherwise it would fire spuriously on a command we already fixed. The
    # signatures: cmd's `nul` -> "device that was not a file"; unix's `/dev/null`
    # -> C:\dev\null path error.
    if ("device that was not a file" in low or "c:\\dev\\null" in low
            or "\\dev\\null" in low):
        return ("\nHINT: redirect to `$null` on Windows PowerShell — `2>$null` "
                "discards errors, `>$null` discards output. `nul`/`con`/`/dev/null` "
                "are not valid targets here (`nul` is a reserved device; "
                "`/dev/null` becomes C:\\dev\\null).")
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
    # and treats `/b` as a second path argument (DirArgumentError / "path2"). The
    # single-path form is now auto-translated, so gate the hint on an ACTUAL dir
    # error (multi-glob / unknown-switch forms that translation bailed on) — else
    # it would fire spuriously on a command we already fixed.
    if _failed and _re.search(r"\bdir\b[^\n]*\s/[a-z]\b", command, _re.IGNORECASE):
        return ("\nHINT: `dir /b` / `dir /s` are cmd.exe switches — PowerShell's "
                "`dir` is Get-ChildItem and reads `/b` as a path. Use "
                "`Get-ChildItem -Name` (bare names, like /b), "
                "`Get-ChildItem -Recurse -Name` (recursive, like /s /b), and "
                "add `-Filter *.py` to match a pattern.")
    return ""


_PS_MISSING_PATH_RE = re.compile(
    r"Cannot find path '([^']+)' because it does not exist", re.IGNORECASE)


def shell_path_not_found_hint(command: str, combined: str, cwd: str) -> str:
    """PowerShell's `Cannot find path 'X' because it does not exist` (from
    Get-Content/cat/gc/type/Remove-Item/…) is a raw dead-end. Give it the same
    did-you-mean that read_file gives — models constantly `cat`/`Get-Content` a
    file at a path they only ASSUMED (seen repeatedly on a mono-repo) — and, for a
    plain file read, nudge toward the read_file tool (which tracks the file for a
    later edit and suggests near-misses itself). Returns a hint or ""."""
    if os.name != "nt":
        return ""
    m = _PS_MISSING_PATH_RE.search(combined or "")
    if not m:
        return ""
    missing = m.group(1).strip().strip('"')
    name = os.path.basename(missing.rstrip("\\/"))
    hint = f"\nHINT: '{missing}' does not exist."
    if name:
        try:
            hits = [h for h in find_by_basename(Path(cwd), name, limit=3)
                    if os.path.normpath(h) != os.path.normpath(missing)]
        except Exception:
            hits = []
        if hits:
            hint += ((" Did you mean:\n    " + hits[0]) if len(hits) == 1
                     else " Did you mean one of:\n    " + "\n    ".join(hits))
        else:
            hint += " Check the path with list_dir or glob."
    if re.search(r"\b(get-content|gc|cat|type)\b", (command or "").lower()):
        hint += ("\n(To read a file, prefer the read_file tool — it finds "
                 "near-misses and lets you edit the file afterward.)")
    return hint


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


def npm_error_hint(combined: str) -> str:
    """Hints for the npm errors a model loops on in a non-Node repo — e.g. it
    tries `npm test` / `npm install` in a .NET or Python project that has no
    package.json. Returns a hint (leading '\\n') or ""."""
    text = combined or ""
    import re as _re
    m = _re.search(r'[Mm]issing script:?\s*["\']?([\w:.-]+)', text)
    if m:
        script = m.group(1)
        return (f"\nHINT: package.json has no '{script}' script — so this may not "
                f"be a Node project, or the script just isn't defined. Check "
                f'package.json\'s "scripts" (or that a package.json exists here at '
                f"all); add the script, or run the real command directly instead "
                f"of `npm {script}`.")
    if _re.search(r"(ENOENT|no such file)[^\n]*package\.json|Could not read package\.json"
                  r"|package\.json.*not found", text, _re.IGNORECASE):
        return ("\nHINT: there's no package.json here — this directory likely "
                "isn't a Node project. Confirm the project type before running "
                "npm (a .NET repo uses dotnet, a Python repo uses pip/pytest).")
    return ""


def pytest_error_hint(combined: str) -> str:
    """Distinguish pytest COLLECTION errors from test failures — the model burns
    many steps re-running pytest and inspecting versions when the real problem is
    an import (a missing dependency, the app package not on sys.path, or two test
    files with the same basename in a mono-repo). Observed live: `pytest tests/`
    on Shared-AI-Service showed `=== ERRORS ===` and the model looped on version
    checks before realising deps weren't installed. Returns a hint or ""."""
    text = combined or ""
    import re as _re
    # Only fire on the collection-ERROR shape, not ordinary "N failed" assertions.
    has_errors = bool(
        _re.search(r"ERROR collecting|errors? during collection"
                   r"|ImportError while importing test module"
                   r"|import file mismatch", text, _re.IGNORECASE)
        or (_re.search(r"^=+ ERRORS =+", text, _re.IGNORECASE | _re.MULTILINE)))
    if not has_errors:
        return ""
    # Duplicate test-file basenames across dirs (classic mono-repo trap).
    if _re.search(r"import file mismatch|not the same as the test file"
                  r"|unique basename", text, _re.IGNORECASE):
        return ("\nHINT: pytest COLLECTION error (not a test failure) — two test "
                "files share a basename in different folders, so the second can't "
                "be imported. Give them unique names, add an __init__.py to each "
                "test dir, or run with `--import-mode=importlib`. Deleting stale "
                "__pycache__/*.pyc also clears it.")
    # A module failed to import — missing dep or the package-under-test not on path.
    mod = _re.search(r"(?:ModuleNotFoundError|ImportError):\s*"
                     r"No module named ['\"]?([\w.]+)", text)
    if mod:
        name = mod.group(1).split(".")[0]
        # Third-party dep vs the project's own package decide the fix. A known
        # PyPI dep that's "missing" right after a `pip install` is almost always
        # the Windows interpreter-mismatch trap: the `pytest.exe` shim and
        # `python`/`pip` resolve to DIFFERENT Python versions, so the install
        # landed in the wrong one. (Observed live: pytest.exe was 3.12 while
        # `python` was 3.13 — `pip install fastapi` went to 3.13, pytest kept
        # failing on 3.12 for ~5 minutes.) A local package (src/app/…) is instead
        # a sys.path problem.
        third_party = {
            "fastapi", "pydantic", "pydantic_settings", "openai", "httpx",
            "uvicorn", "starlette", "boto3", "botocore", "requests", "numpy",
            "pandas", "markitdown", "aiohttp", "sqlalchemy", "redis", "pytest",
            "dotenv", "yaml", "jose", "passlib", "anthropic",
        }
        if name.lower() in third_party:
            return (f"\nHINT: pytest COLLECTION error (not a test failure) — `{name}` "
                    f"isn't importable. If you just `pip install`ed it, `pip`/`python` "
                    f"and `pytest` are likely DIFFERENT interpreters (on Windows the "
                    f"`pytest.exe` shim and `python` are often different versions), so "
                    f"the install went to the wrong Python. Fix by using ONE "
                    f"interpreter both ways:\n"
                    f"    python -m pip install {name}\n"
                    f"    python -m pytest        # NOT the bare `pytest` shim\n"
                    f"Run `python -c \"import sys;print(sys.executable)\"` and "
                    f"`python -m pytest --version` to confirm they match.")
        return (f"\nHINT: pytest COLLECTION error (not a test failure) — the test "
                f"module can't import `{name}`, which looks like your OWN package "
                f"rather than a dependency, so it isn't on sys.path. Run `python -m "
                f"pytest` from the project root, `pip install -e .`, add a conftest.py "
                f"at the root, or set PYTHONPATH. In a mono-repo, run pytest INSIDE "
                f"the package that owns the tests — a root `src/` may shadow a "
                f"per-service one. Re-running pytest unchanged won't fix an import.")
    return ("\nHINT: pytest reported COLLECTION errors (shown under `=== ERRORS "
            "===`), which are import/setup failures, NOT test assertions — the "
            "listed test files never ran. Read the traceback under each `ERROR "
            "collecting …` and fix the import (missing dependency, wrong sys.path, "
            "or a bad conftest) before trusting any pass/fail counts.")


def maven_error_hint(combined: str) -> str:
    """Distinguish a Maven COMPILE failure from a TEST failure — the #1 confusion
    on the SERIOPlus Java monorepo. `mvn test` that dies at `maven-compiler-plugin`
    (missing class/package) never ran a single test, but the model reads "BUILD
    FAILURE" and starts editing test logic. Observed: `mvn test -Dtest=Seizure…`
    failed because `package …common.dto.seizure does not exist` / `cannot find
    symbol class SeizureMemoDto` — the DTO was never created. Returns a hint or ""."""
    text = combined or ""
    if "BUILD FAILURE" not in text and "BUILD ERROR" not in text:
        return ""
    import re as _re
    # Compile step failed -> code doesn't build, so nothing was tested.
    if _re.search(r"COMPILATION ERROR|cannot find symbol"
                  r"|package [\w.]+ does not exist"
                  r"|maven-compiler-plugin[^\n]*compile", text, _re.IGNORECASE):
        pkg = _re.search(r"package ([\w.]+) does not exist", text)
        sym = _re.search(r"symbol:\s*(class|interface|enum|method|variable|"
                         r"constructor)\s+(\w+)", text, _re.IGNORECASE)
        detail = (f" (missing package `{pkg.group(1)}`)" if pkg
                  else f" (missing {sym.group(1).lower()} `{sym.group(2)}`)"
                  if sym else "")
        return (f"\nHINT: Maven BUILD FAILURE at the COMPILE step{detail} — the "
                f"code does not compile, so NO tests ran. This is a missing/renamed "
                f"symbol (class, method, package, or import), NOT a test-logic bug — "
                f"add or fix it, then re-run. (`mvn -o` skips the slow online "
                f"dependency check once deps are cached.)")
    # No test matched the -Dtest filter (surefire ran, found nothing).
    if _re.search(r"No tests were executed|No tests matching", text, _re.IGNORECASE):
        return ("\nHINT: `-Dtest=<Name>` matched no tests — use the SIMPLE class "
                "name (no package), check the spelling, or drop `-Dtest` to run the "
                "whole module. Add `-DfailIfNoTests=false` to tolerate no matches.")
    # Compiled fine, but assertions/errors in the tests themselves.
    if _re.search(r"There are test failures|Failures: [1-9]|Errors: [1-9]", text):
        return ("\nHINT: Maven compiled but TESTS failed — the full stack traces are "
                "in `target/surefire-reports/` (the console summary truncates them); "
                "read the `.txt` for the failing class.")
    return ""


def findstr_syntax_hint(command: str) -> str:
    """`findstr` is not grep — models reach for it as the Windows grep and use GNU
    regex it doesn't understand, so it silently matches nothing (exit 1). The most
    common: `\\|` for alternation. Observed live: `findstr /n "a\\|b\\|c" f.java`
    found nothing because findstr took `\\|` literally. Returns a hint or ""."""
    if os.name != "nt":
        return ""
    import re as _re
    if _re.search(r"\bfindstr\b", command, _re.IGNORECASE) and "\\|" in command:
        return ("\nHINT: `findstr` isn't grep — `\\|` is NOT alternation there, so it "
                "matched the literal text and found nothing. For OR-of-patterns use "
                "`findstr /r /c:\"foo\" /c:\"bar\"`, or space-separated terms in regex "
                "mode (`findstr /r \"foo bar baz\"` matches ANY), or pipe to "
                "`Select-String 'foo|bar|baz'` (.NET regex — plain `|`, no backslash).")
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
            # Show the exact format to fix it — a bare "missing content" left
            # weak models repeating the same broken call until the loop breaker
            # stopped them (write_file with a path but no content).
            skeleton = "".join(
                f'<param name="{p.name}">…</param>' for p in self.params if p.required)
            optional = [p.name for p in self.params if not p.required]
            opt = f" (optional: {', '.join(optional)})" if optional else ""
            return (f"ERROR: {self.name} is missing required param(s): "
                    f"{', '.join(missing)}. Emit ALL required params like this:\n"
                    f'<tool name="{self.name}">{skeleton}</tool>{opt}')
        try:
            return _clamp(self.handler(args))
        except Exception as exc:  # tool errors are fed back, not fatal
            return f"ERROR: {type(exc).__name__}: {exc}"


# Unified permission-mode cycle (Claude-Code-style shift+tab): each entry is
# (name, mode, guard, net_guard). Cycling maps the registry's current
# (mode, guard, net_guard) tuple to the nearest named state and advances to
# the next one — the existing --permission-mode/--guard/--net-writes flags
# and settings.json "defaults" still work unchanged, they just land on one of
# these tuples (or "custom" if a user mixed flags in a way that matches none).
_PERMISSION_STATES = [
    ("default",           "yolo", "confirm", "confirm"),
    ("acceptEdits",       "yolo", "warn",    "confirm"),
    ("plan",              "plan", "warn",    "confirm"),
    ("bypassPermissions", "yolo", "warn",    "allow"),
]
_PERMISSION_LABELS = {
    "default":           "⏸ default (shift+tab to cycle)",
    "acceptEdits":       "⏵ accept edits on (shift+tab to cycle)",
    "plan":              "⏸ plan mode on (shift+tab to cycle)",
    "bypassPermissions": "⏵⏵ bypass permissions on (shift+tab to cycle)",
}


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
        # Reasons the user chose "always allow" this session — the guard skips the
        # prompt for a repeat of the same action (Continue's approve-once model).
        self.session_allow: set = set()
        # Override/auto-detect the project's test command (run_tests tool).
        self.test_command: Optional[str] = None
        # Hooks + permission rules (hooks.HookEngine; wired by app.py).
        self.hooks = None

    # ---- registration ---------------------------------------------------
    def register(self, tool: Tool) -> None:
        self._tools[tool.name] = tool

    def get(self, name: str) -> Optional[Tool]:
        return self._tools.get(name)

    # ---- permission-mode cycle (shift+tab) -------------------------------
    def _permission_state_name(self) -> str:
        cur = (self.mode, self.guard, self.net_guard)
        for name, mode, guard, net in _PERMISSION_STATES:
            if (mode, guard, net) == cur:
                return name
        return "custom"

    def permission_mode_label(self) -> str:
        """Display text for the status bar, e.g. Claude Code's
        '⏵⏵ bypass permissions on (shift+tab to cycle)'."""
        name = self._permission_state_name()
        return _PERMISSION_LABELS.get(
            name, f"⏸ {self.guard}/{self.net_guard} (shift+tab to cycle)")

    def cycle_permission_mode(self) -> str:
        """Advance to the next permission state and return its label. An
        unrecognized ("custom") combination — e.g. hand-set via settings.json
        defaults — starts the cycle from 'default' rather than erroring."""
        names = [n for n, *_ in _PERMISSION_STATES]
        cur = self._permission_state_name()
        idx = names.index(cur) if cur in names else -1
        _, self.mode, self.guard, self.net_guard = _PERMISSION_STATES[(idx + 1) % len(_PERMISSION_STATES)]
        return self.permission_mode_label()

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
        if netmut and netmut not in self.session_allow:   # "always" skips the prompt
            mode = self.net_guard or "confirm"
            if mode == "deny":
                return (f"BLOCKED: outward-facing change refused — {netmut}. "
                        f"Network writes are denied (ROBODOG_NET_WRITES=deny). "
                        f"Re-run interactively with net-writes set to confirm/allow "
                        f"if this is intended.")
            if mode != "allow":   # "confirm" (default) or anything unrecognized
                if self.on_confirm is not None:
                    # reason == the netmut key so an "always" choice can be
                    # remembered against it in self.session_allow.
                    if not self.on_confirm(display, netmut):
                        return f"BLOCKED: user declined the outward-facing change ({netmut})."
                else:
                    return (f"BLOCKED: outward-facing change ({netmut}) needs confirmation, "
                            f"but nothing here can prompt for it (headless or subagent "
                            f"context). Run it from the interactive session, or set "
                            f"ROBODOG_NET_WRITES=allow to permit unattended writes.")
        # --- destructive local shell command (rm -rf, git reset --hard, …) ---
        # Risk-tiered (goose-style): guard="confirm" only actually prompts for
        # "high"-risk commands (irreversible/hard-to-recover). "medium"-risk
        # ones (git clean -f, chmod -R 777, shutdown/reboot, …) still surface a
        # note either way, but don't stop and wait on an answer — this is the
        # ROADMAP Phase 4.5 "only HIGH confirms" middle ground between
        # confirm-everything and full YOLO, without needing an LLM classifier.
        danger = classify_danger(content)
        if danger and danger not in self.session_allow:
            risk = danger_risk(danger)
            if self.guard == "confirm" and risk == "high":
                if self.on_confirm is not None:
                    if not self.on_confirm(display, danger):
                        return f"BLOCKED: user declined the potentially destructive command: {display}"
                else:
                    # Fail-safe, same posture as the network-write guard above:
                    # guard="confirm" means "a human must approve this" — with
                    # nothing able to ask (headless/subagent/an embedder that
                    # didn't wire on_confirm), the safe default is to refuse,
                    # not to silently run an irreversible command.
                    return (f"BLOCKED: potentially destructive command ({risk} risk) needs "
                            f"confirmation, but nothing here can prompt for it (headless or "
                            f"subagent context): {display}")
            elif self.on_bash_line is not None:
                self.on_bash_line(
                    f"⚠ running a potentially destructive command ({risk} risk): {display}")
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
        """Checkpoint + diff + write + verify-after-write + mark-read + syntax."""
        path.parent.mkdir(parents=True, exist_ok=True)
        _diff_and_checkpoint(path, old_text, new_text)
        # Write byte-faithfully (newline="" = no \n->\r\n translation) so the
        # content lands EXACTLY as the model intended — otherwise CRLF content
        # gets mangled and Windows silently rewrites line endings.
        with open(path, "w", encoding="utf-8", newline="") as _fh:
            _fh.write(new_text)
        # (4.2) Verify-after-write: read the bytes back and confirm they landed.
        # Catches a truncated/failed write (disk full, a lock, permissions) and
        # gives the model ground truth instead of assuming success.
        try:
            with open(path, "r", encoding="utf-8", newline="") as _fh:
                on_disk = _fh.read()
            if on_disk != new_text:
                summary += (f"\n\n⚠ WRITE NOT VERIFIED: the file on disk does not "
                            f"match what was written ({len(on_disk)} vs "
                            f"{len(new_text)} chars) — it may have been truncated or "
                            f"changed by another process. Re-read it before relying "
                            f"on it.")
        except OSError as exc:
            summary += f"\n\n⚠ WROTE but could not read back to verify ({exc})."
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
                        + edit_not_found_hint(original, old, new))
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
                    hint = edit_not_found_hint(updated, old, new) if c == 0 else (
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

    # OpenHands-style soft signal: silence isn't the same as a hang (installs/
    # builds/servers go quiet for long stretches while working fine). This
    # NEVER kills anything — it only surfaces one informational line so a human
    # watching the live stream (or the model reading the final result) can tell
    # "quiet but alive" from "actually stuck," instead of just staring at a
    # blank screen until the hard `timeout` eventually kills the tree.
    IDLE_NOTE_SECONDS = int(os.environ.get("ROBODOG_IDLE_NOTE_SECONDS", "20") or "20")

    def _run_streaming(cmd_list: List[str], cwd, timeout: int, env=None
                       ) -> Tuple[Optional[int], List[str], List[str], bool]:
        """Run cmd_list, streaming each output line to reg.on_bash_line as it
        arrives. Returns (returncode, stdout_lines, stderr_lines, timed_out).
        On timeout the whole process TREE is killed. Output is decoded as UTF-8
        so non-ASCII (em-dashes, accents) isn't mojibake'd (`—` -> `â€"`) by the
        Windows codepage default."""
        popen_kwargs = {}
        if os.name != "nt":
            popen_kwargs["start_new_session"] = True
        if env is not None:
            popen_kwargs["env"] = env
        proc = subprocess.Popen(
            cmd_list, cwd=str(cwd),
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            text=True, encoding="utf-8", errors="replace", **popen_kwargs,
        )
        out_lines: List[str] = []
        err_lines: List[str] = []
        last_activity = [time.monotonic()]

        def _reader(stream, sink: List[str]) -> None:
            try:
                for line in stream:
                    line = line.rstrip("\r\n")
                    sink.append(line)
                    last_activity[0] = time.monotonic()
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

        def _watch_idle() -> None:
            notified_at = 0.0
            while proc.poll() is None:
                time.sleep(1)
                idle_for = time.monotonic() - last_activity[0]
                # re-notify every IDLE_NOTE_SECONDS of continued silence, not just once,
                # so a long quiet build doesn't look abandoned after the first note.
                if idle_for >= IDLE_NOTE_SECONDS and time.monotonic() - notified_at >= IDLE_NOTE_SECONDS:
                    notified_at = time.monotonic()
                    cb = reg.on_bash_line
                    if cb is not None:
                        try:
                            cb(f"⏳ still running — no new output for {int(idle_for)}s "
                               f"(normal for installs/builds/servers; not necessarily hung)")
                        except Exception:
                            pass

        t_out = threading.Thread(target=_reader, args=(proc.stdout, out_lines), daemon=True)
        t_err = threading.Thread(target=_reader, args=(proc.stderr, err_lines), daemon=True)
        t_idle = threading.Thread(target=_watch_idle, daemon=True)
        t_out.start()
        t_err.start()
        t_idle.start()
        timed_out = False
        try:
            proc.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            timed_out = True
            _kill_tree(proc)
        t_out.join(timeout=5)
        t_err.join(timeout=5)
        t_idle.join(timeout=2)
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
        # Missing-path did-you-mean also keys on error text (Get-Content on a
        # non-existent file is a non-terminating error — may exit 0).
        ph = shell_path_not_found_hint(command or shown_cmd, out + "\n" + err,
                                       str(reg.cwd))
        if ph:
            parts.append(ph.lstrip("\n"))
        # Python self-heal hints (failed runs only): hyphenated-skill-dir import
        # loop (fdaskills.jira.jira_call -> jira-call) and json.loads on an
        # already-parsed value — both observed looping 3x on ELSA.
        if returncode not in (0, None):
            for h in (python_import_hint(err, str(reg.cwd)),
                      python_error_hint(err),
                      npm_error_hint(out + "\n" + err),
                      pytest_error_hint(out + "\n" + err),
                      maven_error_hint(out + "\n" + err),
                      findstr_syntax_hint(command or shown_cmd)):
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
            run_cmd = powershell_translate(translate_null_redirects(
                translate_dir_switches(translate_windows_aliases(command))))
            # Force UTF-8 so non-ASCII survives BOTH ways: native-command output
            # (git log) is decoded as UTF-8, and args we pass to native commands
            # (git commit -m "…") are encoded as UTF-8 — no more `—` -> `â€"`.
            run_cmd = ("[Console]::OutputEncoding=[Text.Encoding]::UTF8;"
                       "$OutputEncoding=[Text.Encoding]::UTF8;" + run_cmd)
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
        env = None
        try:
            body = content
            # UTF-8: match the utf-8 decode in _run_streaming so non-ASCII output
            # isn't mojibake'd. Python obeys PYTHONUTF8/PYTHONIOENCODING; a
            # PowerShell script gets an encoding preamble.
            if interpreter == "powershell":
                body = ("[Console]::OutputEncoding=[Text.Encoding]::UTF8;"
                        "$OutputEncoding=[Text.Encoding]::UTF8;\n" + content)
            elif interpreter == "python":
                env = {**os.environ, "PYTHONUTF8": "1", "PYTHONIOENCODING": "utf-8"}
            with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as fh:
                fh.write(body)
            if interpreter == "powershell":
                cmd = ["powershell", "-NoProfile", "-NonInteractive",
                       "-ExecutionPolicy", "Bypass", "-File", tmp_path]
            elif interpreter == "bash":
                cmd = ["bash", tmp_path]
            else:
                cmd = [sys.executable, tmp_path]
            shown = f"run_script({interpreter})"
            rc, out_lines, err_lines, timed_out = _run_streaming(cmd, reg.cwd, timeout, env=env)
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
        cwd_s = str(reg.cwd)

        def _rel(full: str) -> str:
            return str(Path(full).relative_to(reg.cwd)) if full.startswith(cwd_s) else full

        # os.walk with in-place dir pruning so node_modules/.git/etc. are never
        # descended into (rglob would walk all of them first, then filter — slow
        # right after an `npm install`). Collect a small sample of NON-matching
        # files too, to orient the model when the pattern matches nothing.
        matches: List[str] = []
        present: List[str] = []
        scanned = 0
        try:
            for dirpath, dirnames, filenames in os.walk(str(root)):
                dirnames[:] = [d for d in dirnames
                               if d not in EXCLUDE_DIRS and not d.endswith(".egg-info")]
                for fn in filenames:
                    if fnmatch.fnmatch(fn, pattern):
                        matches.append(_rel(os.path.join(dirpath, fn)))
                    elif len(present) < 40:
                        present.append(os.path.relpath(os.path.join(dirpath, fn), str(root)))
                scanned += len(filenames)
                if len(matches) >= 2000 or scanned > 60_000:
                    break
        except (OSError, RuntimeError):
            pass
        matches.sort()
        if not matches:
            # Mirror the read_file/list_dir "did you mean" philosophy: a bare "no
            # files" leads models to barrel on and read paths they only assumed
            # exist. Show what IS there so they can fix the pattern or the path.
            if not present:
                return (f"No files matching '{pattern}' under {root} "
                        f"(the directory is empty or fully excluded).")
            exts = sorted({os.path.splitext(p)[1] for p in present
                           if os.path.splitext(p)[1]})
            sample = sorted(present)[:15]
            more = "\n  …(more)" if len(present) >= 40 else ""
            return (f"No files matching '{pattern}' under {root} — but files ARE "
                    f"present there"
                    + (f" (types: {' '.join(exts[:12])})" if exts else "")
                    + ". The pattern matches the file BASENAME (e.g. '*.js', "
                    "'*.test.js'). What's actually there:\n  "
                    + "\n  ".join(sample) + more)
        # Lead with the COUNT so the model doesn't have to count lines (small
        # models miscount) — then the list (capped at 500).
        n = len(matches)
        shown = matches[:500]
        head = (f"{n} file(s) matching '{pattern}'"
                + (f" (showing first 500)" if n > 500 else "") + ":")
        return head + "\n" + "\n".join(shown)

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
        if not results:
            return f"No matches for /{pattern}/."
        capped = " (showing first 300)" if len(results) >= 300 else ""
        return f"{len(results)} match(es) for /{pattern}/{capped}:\n" + "\n".join(results)

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
            return f"ERROR: not found: {path}." + dir_not_found_hint(path)
        if not path.is_dir():
            return (f"ERROR: {path} is a file, not a directory — "
                    f"use read_file to view it.")
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
