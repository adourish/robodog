# file: robodog_terminal/ui.py
"""
agentic terminal UI.

Interactive path: prompt_toolkit PromptSession — sticky bottom status bar
(bottom_toolbar), slash-command autocomplete, persistent input history,
Ctrl+R reverse search (free), patch_stdout so background threads can print
safely above the input line.

Non-TTY / missing-deps path: plain input() with a printed status line —
keeps piped tests and weird consoles working.

Rendering: rich (welcome panel, markdown answers, spinner, colored diffs).
Resize rule: NEVER cache a width — rich re-measures at each print and
prompt_toolkit redraws the toolbar on terminal resize by itself.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import List, Optional

# Force UTF-8 so box-drawing/emoji don't crash on Windows cp1252 consoles.
try:  # pragma: no cover - environment dependent
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass

try:
    from rich.console import Console
    from rich.markdown import Markdown
    from rich.panel import Panel
    from rich.text import Text
    _HAVE_RICH = True
except Exception:  # pragma: no cover
    _HAVE_RICH = False

try:
    from prompt_toolkit import PromptSession
    from prompt_toolkit.completion import WordCompleter
    from prompt_toolkit.history import FileHistory
    from prompt_toolkit.patch_stdout import patch_stdout
    from prompt_toolkit.key_binding import KeyBindings
    from prompt_toolkit.styles import Style as _PTStyle
    _HAVE_PT = True
except Exception:  # pragma: no cover
    _HAVE_PT = False


def _input_key_bindings():
    """
    Enter submits (single-line feel); a line ending in backslash continues to
    a new line (a modern agentic terminal's `\\`+Enter); Alt/Option+Enter always inserts a
    newline. Pasted multi-line text is delivered via bracketed paste (not key
    events), so it lands in the buffer whole without triggering submit.
    """
    kb = KeyBindings()

    @kb.add("enter")
    def _(event):
        buf = event.current_buffer
        text = buf.text
        # Backslash-continuation: strip the trailing '\' and add a newline.
        if text.rstrip("\n").endswith("\\"):
            stripped = text.rstrip("\n")
            buf.text = stripped[:-1]
            buf.cursor_position = len(buf.text)
            buf.insert_text("\n")
        else:
            buf.validate_and_handle()

    @kb.add("escape", "enter")  # Alt/Option+Enter -> hard newline
    def _(event):
        event.current_buffer.insert_text("\n")

    @kb.add("c-j")  # Ctrl+J -> newline (works in every terminal)
    def _(event):
        event.current_buffer.insert_text("\n")

    @kb.add("c-u")  # Ctrl+U -> clear the whole input (all lines)
    def _(event):
        event.current_buffer.text = ""
        event.current_buffer.cursor_position = 0

    return kb


class UI:
    def __init__(self, model_name: str = "gateway/sonnet", cwd: Optional[str] = None,
                 commands: Optional[List[str]] = None, stderr: bool = False,
                 editor: Optional[str] = None):
        self.model_name = model_name
        self.cwd = str(cwd or os.getcwd())
        # Editor for clickable file:line jumps (file | vscode | cursor | vscodium).
        self.editor = editor or os.environ.get("ROBODOG_EDITOR", "file")
        self.total_tokens = 0
        self.bg_running = 0          # background tasks (wired later)
        self.context_pct = 0         # transcript fill estimate (loop sets)
        # stderr=True: headless -p mode — decorations go to stderr so stdout
        # carries only the final result.
        self.console = Console(stderr=stderr) if _HAVE_RICH else None
        self._stderr = stderr
        self._status = None          # active rich spinner
        self._interactive = bool(
            _HAVE_PT and sys.stdin.isatty() and sys.stdout.isatty()
        )
        self._session = None
        if self._interactive:
            hist_dir = Path.home() / ".robodog"
            hist_dir.mkdir(parents=True, exist_ok=True)
            completer = None
            if commands:
                completer = WordCompleter(sorted(commands), sentence=True,
                                          match_middle=False)
            self._session = PromptSession(
                history=FileHistory(str(hist_dir / "terminal_history")),
                completer=completer,
                bottom_toolbar=self._toolbar,
                complete_while_typing=True,
                # multiline=True keeps pasted newlines in the buffer instead of
                # submitting at the first one. Bracketed paste (default in
                # prompt_toolkit) inserts pasted text via insert_text, so the
                # custom Enter binding below does NOT fire per pasted line —
                # multi-line cut/paste is captured whole, like a modern agentic terminal.
                multiline=True,
                key_bindings=_input_key_bindings(),
                prompt_continuation=lambda width, ln, wrapped: "  " if not wrapped else "",
                # Black background for the status toolbar (the default light/
                # reversed bar looks out of place with the emoji + ANSI colors).
                style=_PTStyle.from_dict({
                    "bottom-toolbar": "bg:#000000 noreverse",
                    "bottom-toolbar.text": "bg:#000000",
                }),
            )

    # ---- status line (emoji + color, an agentic coding terminal custom style) ----------
    # ANSI palette (protanopia-safe: cyan / yellow / magenta + emoji severity)
    _C = {
        "magenta_b": "\033[1;35m", "magenta": "\033[0;35m",
        "cyan": "\033[0;36m", "yellow": "\033[0;33m",
        "gray": "\033[0;90m", "reset": "\033[0m",
    }

    def _model_emoji(self) -> str:
        m = self.model_name.lower()
        if "opus" in m:
            return "👾"
        if "sonnet" in m or "gateway" in m:
            return "🤖"
        if "haiku" in m:
            return "🛸"
        if "gpt" in m or "openai" in m:
            return "🦾"
        if "echo" in m or "demo" in m:
            return "🎧"
        return "🦿"

    @staticmethod
    def _abbrev(n: int) -> str:
        if n >= 1_000_000:
            return f"{n / 1_000_000:.1f}M"
        if n >= 1_000:
            return f"{n / 1_000:.1f}k"
        return str(n)

    @staticmethod
    def _tok_emoji(n: int) -> str:
        for thresh, e in ((1_000_000, "🏭"), (500_000, "🔌"), (250_000, "🔩"),
                          (100_000, "👽"), (50_000, "🛰️"), (10_000, "🔋")):
            if n >= thresh:
                return e
        return "✨"

    # ---- git branch ------------------------------------------------------
    # The toolbar redraws on EVERY keystroke, so this must never spawn `git`.
    # Reading .git/HEAD is one open(); the result is cached and invalidated by
    # HEAD's mtime, leaving a single stat() on the hot path.
    _git_cache: dict = {}       # HEAD path -> (mtime_ns, branch)
    _git_head: dict = {}        # cwd -> resolved HEAD path (skips the walk-up)

    def _resolve_head(self) -> Optional[Path]:
        """Locate .git/HEAD for self.cwd. Only positive results are cached, so
        a `git init` mid-session is picked up instead of being stuck at None."""
        cached = self._git_head.get(self.cwd)
        if cached is not None:
            return cached
        try:
            start = Path(self.cwd).resolve()
        except Exception:
            return None

        # Find the repo root (walk up until a .git dir/file appears).
        git_path = None
        for parent in (start, *start.parents):
            cand = parent / ".git"
            if cand.exists():
                git_path = cand
                break
        if git_path is None:
            return None

        # Worktrees and submodules use a .git FILE: "gitdir: <path>".
        try:
            if git_path.is_file():
                txt = git_path.read_text(encoding="utf-8", errors="replace").strip()
                if not txt.startswith("gitdir:"):
                    return None
                git_dir = Path(txt.split(":", 1)[1].strip())
                if not git_dir.is_absolute():
                    git_dir = (git_path.parent / git_dir).resolve()
            else:
                git_dir = git_path
        except OSError:
            return None

        head = git_dir / "HEAD"
        self._git_head[self.cwd] = head
        return head

    def _git_branch(self) -> Optional[str]:
        head = self._resolve_head()
        if head is None:
            return None
        try:
            stamp = head.stat().st_mtime_ns
        except OSError:
            self._git_head.pop(self.cwd, None)   # repo moved/removed
            return None

        key = str(head)
        hit = self._git_cache.get(key)
        if hit and hit[0] == stamp:
            return hit[1]

        try:
            raw = head.read_text(encoding="utf-8", errors="replace").strip()
        except OSError:
            return None

        if raw.startswith("ref:"):
            branch = raw.split("/", 2)[-1]        # refs/heads/foo/bar -> foo/bar
        elif raw:
            branch = raw[:7]                      # detached HEAD -> short sha
        else:
            return None

        self._git_cache[key] = (stamp, branch)
        return branch

    def _status_segments(self):
        """Return [(plain_text, ansi_color), ...] for the status line."""
        C = self._C
        cwd_short = self.cwd
        home = str(Path.home())
        if cwd_short.startswith(home):
            cwd_short = "~" + cwd_short[len(home):]
        # last two path segments, like the reference statusline
        import os as _os
        parts_path = [p for p in cwd_short.replace("\\", "/").split("/") if p]
        short_cwd = "/".join(parts_path[-2:]) if len(parts_path) >= 2 else (parts_path[-1] if parts_path else cwd_short)

        segs = []
        # context remaining % with escalation (FIRST, like the reference)
        if self.context_pct:
            used = int(self.context_pct)
            rem = 100 - used
            if used >= 80:
                segs.append((f"🚨 💥 {rem}%", C["magenta_b"]))
            elif used >= 60:
                segs.append((f"⚙️ ⚠️ {rem}%", C["magenta_b"]))
            elif used >= 40:
                segs.append((f"🦑 {rem}%", C["yellow"]))
            else:
                segs.append((f"🫧 {rem}%", C["cyan"]))
        # tokens with escalating emoji
        if self.total_tokens:
            segs.append((f"{self._tok_emoji(self.total_tokens)} "
                         f"{self._abbrev(self.total_tokens)}", C["magenta"]))
        # model with emoji
        segs.append((f"{self._model_emoji()} {self.model_name}", C["cyan"]))
        # background tasks
        if self.bg_running:
            segs.append((f"🧵 {self.bg_running} bg", C["yellow"]))
        # git branch (omitted entirely outside a repo)
        branch = self._git_branch()
        if branch:
            segs.append((f"🌿 {branch}", C["yellow"]))
        # folder
        segs.append((f"📁 {short_cwd}", C["gray"]))
        return segs

    def status_line(self) -> str:
        """Plain (uncolored) status line — fallback + tests."""
        return "  ".join(t for t, _ in self._status_segments())

    def _status_ansi(self) -> str:
        C = self._C
        sep = f" {C['gray']}|{C['reset']} "
        return sep.join(f"{color}{t}{C['reset']}"
                        for t, color in self._status_segments())

    def _toolbar(self):
        # prompt_toolkit bottom toolbar — render ANSI colors + emoji.
        try:
            from prompt_toolkit.formatted_text import ANSI
            return ANSI(" " + self._status_ansi())
        except Exception:
            return " " + self.status_line()

    def print_status(self):
        if self.console:
            from rich.text import Text as _T
            self.console.print(_T.from_ansi(self._status_ansi()))
        else:
            print(self.status_line())

    # ---- banner ---------------------------------------------------------
    def welcome(self):
        try:
            from . import __version__ as _ver
        except Exception:
            _ver = "?"
        tips = (
            "[bold]/help[/bold] commands   [bold]![/bold] run shell   "
            "[bold]/rewind[/bold] undo edits   [bold]/exit[/bold] quit"
        )
        if self.console and self.console.width >= 60:
            body = Text.from_markup(
                f"[bold cyan]Robodog Terminal[/bold cyan] [dim]v{_ver}[/dim]  "
                "[dim]agentic coding in your shell[/dim]\n\n"
                f"model: [green]{self.model_name}[/green]\n"
                f"cwd:   [blue]{self.cwd}[/blue]\n\n"
                f"{tips}"
            )
            # Explicit width avoids the off-by-one border misalignment rich can
            # produce when it infers width from a piped (non-TTY) console.
            self.console.print(Panel(body, title="🤖 robodog", border_style="cyan",
                                     padding=(1, 2), width=self.console.width,
                                     expand=False))
        else:  # narrow terminal or no rich: plain lines
            print(f"Robodog Terminal v{_ver} — agentic coding in your shell")
            print(f" model: {self.model_name}")
            print(f" cwd:   {self.cwd}")
            print(" /help  !cmd  /rewind  /exit")

    # ---- prompt ---------------------------------------------------------
    def prompt(self) -> str:
        if self._session is not None:
            with patch_stdout():
                return self._session.prompt("› ").strip()
        # fallback: printed status + plain input
        self.print_status()
        if self.console:
            self.console.print("[bold magenta]›[/bold magenta] ", end="")
            return input().strip()
        return input("› ").strip()

    # ---- spinner --------------------------------------------------------
    def spinner_start(self, text: str):
        if self.console and sys.stdout.isatty() and self._status is None:
            self._status = self.console.status(f"[cyan]{text}[/cyan]",
                                               spinner="dots")
            self._status.start()

    def spinner_update(self, text: str):
        if self._status is not None:
            self._status.update(f"[cyan]{text}[/cyan]")

    def spinner_stop(self):
        if self._status is not None:
            self._status.stop()
            self._status = None

    # ---- output ---------------------------------------------------------
    def info(self, msg: str):
        # markup=False: these carry arbitrary text (paths, [btw ...], [N steps])
        # that must NOT be parsed as rich markup tags.
        if self.console:
            self.console.print(msg, markup=False, highlight=False)
        else:
            print(msg)

    def dim(self, msg: str):
        # style="dim" + markup=False so bracketed content in msg (e.g.
        # "[3 steps · 264 tok]") renders literally, not as a markup tag.
        if self.console:
            self.console.print(msg, style="dim", markup=False, highlight=False)
        else:
            print(msg)

    def assistant(self, text: str):
        """Render a final answer as markdown (falls back to plain text)."""
        if self.console:
            try:
                self.console.print(Markdown(text))
                return
            except Exception:
                pass
            self.console.print(Text(text))
        else:
            print(text)

    # ---- clickable links -----------------------------------------------
    def _abs(self, path_str: str):
        try:
            p = Path(path_str)
            if not p.is_absolute():
                p = Path(self.cwd) / p
            return p.resolve()
        except Exception:
            return None

    def _editor_uri(self, path_str: str, line: Optional[int] = None):
        """
        Build a clickable URI honoring the configured editor so clicks jump to
        the file (and line, when the editor supports it):
          file    -> file://<abs>            (opens the file, no line)
          vscode  -> vscode://file/<abs>[:line]
          cursor  -> cursor://file/<abs>[:line]
          vscodium-> vscodium://file/<abs>[:line]
        """
        p = self._abs(path_str)
        if p is None:
            return None
        editor = (self.editor or "file").lower()
        if editor in ("vscode", "code", "cursor", "vscodium"):
            scheme = {"vscode": "vscode", "code": "vscode",
                      "cursor": "cursor", "vscodium": "vscodium"}[editor]
            # vscode://file/C:/path/to/file.py:LINE  (forward slashes)
            posix = str(p).replace("\\", "/")
            if not posix.startswith("/"):
                posix = "/" + posix          # vscode wants a leading slash
            uri = f"{scheme}://file{posix}"
            return uri + (f":{line}" if line else "")
        try:
            return p.as_uri()                # plain file:// (no line support)
        except Exception:
            return None

    def _file_uri(self, path_str: str):
        """file:// (or editor) URI for a path, or None."""
        return self._editor_uri(path_str, None)

    def _linked_path(self, path_str: str, style: str = "dim",
                     line: Optional[int] = None):
        """A rich Text whose displayed path is a clickable, editor-aware link."""
        from rich.text import Text as _T
        from rich.style import Style as _S
        uri = self._editor_uri(path_str, line)
        if uri:
            return _T(path_str, style=_S.parse(style) + _S(link=uri, underline=True))
        return _T(path_str, style=style)

    # ---- streamed command output ----------------------------------------
    # Long-running commands stream line by line. Printing every line verbatim
    # buries the conversation in build logs and directory listings, so the
    # trace shows a bounded head and then reports what it held back. The MODEL
    # still receives the complete output — this caps the display only.
    STREAM_LIMIT = int(os.environ.get("ROBODOG_STREAM_LINES", "15") or 15)

    def _reset_stream(self):
        self._stream_shown = 0      # lines actually printed
        self._stream_total = 0      # lines seen (for the held-back count)
        self._stream_blank = False  # last printed line was blank
        self._stream_capped = False # "output continues" notice already shown

    def bash_line(self, line: str):
        """Print one streamed output line, bounded and blank-collapsed."""
        if not hasattr(self, "_stream_total"):
            self._reset_stream()
        self._stream_total += 1

        # Collapse runs of blank lines — PowerShell in particular emits many,
        # and a column of empty │ bars is pure noise.
        if not line.strip():
            if self._stream_blank or self._stream_shown == 0:
                return
            self._stream_blank = True
        else:
            self._stream_blank = False

        if self._stream_shown < self.STREAM_LIMIT:
            self._stream_shown += 1
            self.dim(f"  │ {line}")
        elif not self._stream_capped:
            self._stream_capped = True
            self.dim("  │ … output continues (shown in full to the model)")

    def stream_footer(self):
        """After a command finishes, report anything the display held back."""
        if getattr(self, "_stream_capped", False):
            held = self._stream_total - self._stream_shown
            if held > 0:
                self.dim(f"  │ … {held} more lines not shown")
        self._reset_stream()

    def tool_call(self, name: str, args: dict):
        self._reset_stream()          # each tool call starts a fresh window
        path = args.get("path")
        preview = args.get("command") or path or args.get("pattern") \
            or args.get("prompt") or ""
        preview = str(preview).replace("\n", " ")
        width = self.console.width if self.console else 80
        maxlen = max(20, width - len(name) - 8)
        if len(preview) > maxlen:
            preview = preview[:maxlen] + "…"
        if self.console:
            from rich.text import Text as _T
            from rich.style import Style as _S
            line = _T("  ")
            line.append(f"⚙ {name} ", style="yellow")
            # If the arg is a file path, link the (possibly truncated) display
            # text to the FULL path's file:// URI so long paths stay clickable.
            uri = self._file_uri(str(path)) if path and preview.rstrip("…") in str(path) else None
            if uri:
                line.append(preview, style=_S.parse("dim") + _S(link=uri, underline=True))
            else:
                line.append(preview, style="dim")
            self.console.print(line)
        else:
            print(f"  * {name} {preview}")

    @staticmethod
    def _flatten(s: str, limit: int = 120) -> str:
        """One clean line: tabs/newlines/control chars collapsed to spaces."""
        import re as _re
        s = _re.sub(r"[\t\r\n\x00-\x1f]+", " ", s)
        s = _re.sub(r"  +", " ", s).strip()
        return s[:limit] + "…" if len(s) > limit else s

    def _result_summary(self, name: str, result: str):
        """
        (text, style) — a compact, tool-aware summary of a tool result.

        The rule: report WHAT HAPPENED, never dump the payload. `read_file`
        returns the whole file line-numbered; echoing even its first line
        leaks content into the trace and reads like noise. Failures get a
        loud style so the eye lands on them instead of scrolling past.
        """
        text = (result or "").strip()
        if not text:
            return "(no output)", "dim"
        lines = text.splitlines()
        first = lines[0]
        n = len(lines)

        # Failures first — these must never render dim.
        if text.startswith(("ERROR:", "BLOCKED:")):
            return self._flatten(first, 160), "red"
        if "⚠ VERIFY FAILED" in text:
            return self._flatten(
                next(l for l in lines if "VERIFY FAILED" in l), 160), "red"

        if name == "read_file":
            if text == "(empty file)":
                return "empty file", "dim"
            return f"read {n} line{'' if n == 1 else 's'}", "dim"

        if name in ("bash", "run_script"):
            failed = any(l.startswith("⚠ COMMAND FAILED") for l in lines)
            body = [l for l in lines[1:]
                    if not l.startswith(("(exit", "⚠ COMMAND FAILED", "--- std"))]
            extra = f" · {len(body)} lines" if body else ""
            status = "failed" if failed else "exit 0"
            return (f"{self._flatten(first, 90)}  ({status}){extra}",
                    "red" if failed else "dim")

        if name == "grep":
            more = f"  (+{n - 1} more)" if n > 1 else ""
            return self._flatten(first, 100) + more, "dim"

        if name in ("glob", "list_dir"):
            if first.lower().startswith("no files"):
                return self._flatten(first, 120), "dim"
            return f"{n} entr{'y' if n == 1 else 'ies'}", "dim"

        if name == "agent":
            # "[subagent#3:general finished — 2 steps, 310 tokens]\n<answer>"
            # The header is metadata; the ANSWER is what the user needs to see.
            import re as _re
            m = _re.match(
                r"\[subagent#(\d+):(\w+) finished — (\d+) steps?, (\d+) tokens?\]",
                first)
            if m:
                cid, ctype, steps, toks = m.groups()
                answer = next((l for l in lines[1:] if l.strip()), "")
                label = f"#{cid} {ctype} · {steps} step{'' if steps == '1' else 's'} · {toks} tok"
                if answer:
                    return f"{label} — {self._flatten(answer, 90)}", "dim"
                return label, "dim"
            # background-start message or unexpected shape: generic fallthrough

        # write_file / edit_file / run_tests / agent: the tool already returns a
        # one-line summary — keep it, just flatten and note any overflow.
        more = f"  (+{n - 1} lines)" if n > 1 else ""
        return self._flatten(first, 100) + more, "dim"

    def tool_result(self, name: str, result: str):
        summary, style = self._result_summary(name, result)
        if self.console:
            from rich.text import Text as _T
            import re as _re
            # No base style on the Text: a global "dim" here would blend into
            # every append, rendering failures as *dim red* and burying them.
            line = _T()
            line.append("    ↳ ", style="dim")
            # Linkify an absolute path OR a file:line reference (grep results,
            # tracebacks) in the summary line so it opens the file on click.
            m = _re.search(
                r"([A-Za-z]:\\[^\s():]+|[\w./\\-]+\.[A-Za-z]\w*)(:\d+)?", summary)
            if m and (m.group(2) or "\\" in m.group(1) or "/" in m.group(1)):
                path, lineno = m.group(1), (m.group(2) or "")
                pre, post = summary[:m.start()], summary[m.end():]
                line.append(pre, style=style)
                # editor-aware: link jumps to the exact line when known
                ln_int = int(lineno[1:]) if lineno else None
                lp = self._linked_path(path, style, line=ln_int)
                if lineno:
                    lp.append(lineno, style=style)
                line.append_text(lp)
                line.append(post, style=style)
            else:
                line.append(summary, style=style)
            self.console.print(line)
        else:
            print(f"    -> {summary}")

    def diff(self, path: str, diff_text: str, max_lines: int = 40):
        """Colored unified diff preview of a file change."""
        lines = diff_text.splitlines()
        shown = lines[:max_lines]
        if self.console:
            from rich.text import Text as _T
            hdr = _T("  Δ ", style="bold")
            hdr.append_text(self._linked_path(path, "bold"))
            self.console.print(hdr)
            for ln in shown:
                if ln.startswith("+") and not ln.startswith("+++"):
                    self.console.print(f"  [green]{ln}[/green]", highlight=False)
                elif ln.startswith("-") and not ln.startswith("---"):
                    self.console.print(f"  [red]{ln}[/red]", highlight=False)
                elif ln.startswith("@@"):
                    self.console.print(f"  [cyan]{ln}[/cyan]", highlight=False)
                else:
                    self.console.print(f"  [dim]{ln}[/dim]", highlight=False)
            if len(lines) > max_lines:
                self.console.print(f"  [dim]… {len(lines) - max_lines} more diff lines[/dim]")
        else:
            print(f"  Δ {path}")
            for ln in shown:
                print(f"  {ln}")

    def error(self, msg: str):
        if self.console:
            self.console.print(f"[bold red]error:[/bold red] {msg}")
        else:
            print(f"error: {msg}")
