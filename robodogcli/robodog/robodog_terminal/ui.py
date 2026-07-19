# file: robodog_terminal/ui.py
"""
Claude Code-style terminal UI.

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
    a new line (Claude Code's `\\`+Enter); Alt/Option+Enter always inserts a
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

    return kb


class UI:
    def __init__(self, model_name: str = "elsa/sonnet", cwd: Optional[str] = None,
                 commands: Optional[List[str]] = None, stderr: bool = False):
        self.model_name = model_name
        self.cwd = str(cwd or os.getcwd())
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
                # multi-line cut/paste is captured whole, like Claude Code.
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

    # ---- status line (emoji + color, Claude Code custom style) ----------
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
        if "sonnet" in m or "elsa" in m:
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
        tips = (
            "[bold]/help[/bold] commands   [bold]![/bold] run shell   "
            "[bold]/rewind[/bold] undo edits   [bold]/exit[/bold] quit"
        )
        if self.console and self.console.width >= 60:
            body = Text.from_markup(
                "[bold cyan]Robodog Terminal[/bold cyan]  "
                "[dim]agentic coding in your shell[/dim]\n\n"
                f"model: [green]{self.model_name}[/green]\n"
                f"cwd:   [blue]{self.cwd}[/blue]\n\n"
                f"{tips}"
            )
            # Explicit width avoids the off-by-one border misalignment rich can
            # produce when it infers width from a piped (non-TTY) console.
            self.console.print(Panel(body, title="🐕 robodog", border_style="cyan",
                                     padding=(1, 2), width=self.console.width,
                                     expand=False))
        else:  # narrow terminal or no rich: plain lines
            print("Robodog Terminal — agentic coding in your shell")
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
    def _file_uri(self, path_str: str):
        """file:// URI for a path (so the terminal can open it), or None."""
        try:
            p = Path(path_str)
            if not p.is_absolute():
                p = Path(self.cwd) / p
            return p.resolve().as_uri()
        except Exception:
            return None

    def _linked_path(self, path_str: str, style: str = "dim"):
        """A rich Text whose displayed path is a clickable file:// hyperlink."""
        from rich.text import Text as _T
        from rich.style import Style as _S
        uri = self._file_uri(path_str)
        if uri:
            return _T(path_str, style=_S.parse(style) + _S(link=uri, underline=True))
        return _T(path_str, style=style)

    def tool_call(self, name: str, args: dict):
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

    def tool_result(self, name: str, result: str):
        first = result.strip().splitlines()[0] if result.strip() else ""
        more = result.count("\n")
        suffix = f"  (+{more} lines)" if more else ""
        if self.console:
            from rich.text import Text as _T
            import re as _re
            line = _T("    ↳ ", style="dim")
            # Linkify an absolute path OR a file:line reference (grep results,
            # tracebacks) in the summary line so it opens the file on click.
            snippet = first[:100]
            m = _re.search(
                r"([A-Za-z]:\\[^\s():]+|[\w./\\-]+\.[A-Za-z]\w*)(:\d+)?", snippet)
            if m and (m.group(2) or "\\" in m.group(1) or "/" in m.group(1)):
                path, lineno = m.group(1), (m.group(2) or "")
                pre, post = snippet[:m.start()], snippet[m.end():]
                line.append(pre, style="dim")
                lp = self._linked_path(path, "dim")
                if lineno:
                    lp.append(lineno, style="dim")
                line.append_text(lp)
                line.append(post + suffix, style="dim")
            else:
                line.append(snippet + suffix, style="dim")
            self.console.print(line)
        else:
            print(f"    -> {first[:100]}{suffix}")

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
