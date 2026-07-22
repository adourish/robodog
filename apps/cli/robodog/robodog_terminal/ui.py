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
import threading
from pathlib import Path
from typing import Dict, List, Optional

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
    from prompt_toolkit.completion import WordCompleter, Completer, Completion
    from prompt_toolkit.history import FileHistory
    from prompt_toolkit.patch_stdout import patch_stdout
    from prompt_toolkit.key_binding import KeyBindings, merge_key_bindings
    from prompt_toolkit.styles import Style as _PTStyle
    _HAVE_PT = True

    class _SafeFileHistory(FileHistory):
        """FileHistory that never crashes the REPL. A line pasted from a
        Windows console can carry lone UTF-16 surrogates; FileHistory encodes
        entries to UTF-8, and `surrogates not allowed` was propagating out of
        the Enter key binding and killing the prompt. Strip surrogates before
        storing, and swallow any residual write error — losing a history entry
        must never take down input."""
        def store_string(self, string: str) -> None:
            clean = "".join(c for c in string
                            if not 0xD800 <= ord(c) <= 0xDFFF)
            try:
                super().store_string(clean)
            except Exception:  # pragma: no cover - defensive
                pass

    class _RobodogCompleter(Completer):
        """Completes slash commands AND @-file mentions. When the word under the
        cursor starts with '@', complete file/dir paths under cwd; otherwise fall
        back to the slash-command word list."""

        def __init__(self, commands, cwd):
            self._words = (WordCompleter(sorted(commands), sentence=True,
                                         match_middle=False) if commands else None)
            self._cwd = Path(cwd)

        def get_completions(self, document, complete_event):
            text = document.text_before_cursor
            at = text.rfind("@")
            if (at != -1 and (at == 0 or text[at - 1].isspace())
                    and " " not in text[at + 1:]):
                yield from self._paths(text[at + 1:])
                return
            if self._words is not None:
                yield from self._words.get_completions(document, complete_event)

        def _paths(self, frag):
            frag = frag.replace("\\", "/")
            if "/" in frag:
                sub, _, prefix = frag.rpartition("/")
                base = self._cwd / sub
            else:
                base, prefix = self._cwd, frag
            try:
                entries = sorted(base.iterdir(),
                                 key=lambda p: (p.is_file(), p.name.lower()))
            except OSError:
                return
            pl = prefix.lower()
            for child in entries:
                name = child.name
                if name.startswith(".") and not prefix.startswith("."):
                    continue
                if name.lower().startswith(pl):
                    yield Completion(name + ("/" if child.is_dir() else ""),
                                     start_position=-len(prefix))
except Exception:  # pragma: no cover
    _HAVE_PT = False


def _input_key_bindings(on_cycle_permission=None):
    """
    Enter submits (single-line feel); a line ending in backslash continues to
    a new line (a modern agentic terminal's `\\`+Enter); Alt/Option+Enter always inserts a
    newline. Pasted multi-line text is delivered via bracketed paste (not key
    events), so it lands in the buffer whole without triggering submit.

    `on_cycle_permission`, if given, is bound to Shift+Tab (Claude Code's
    permission-mode cycle: default -> acceptEdits -> plan -> bypassPermissions).
    `event.app.invalidate()` is what makes the bottom toolbar redraw
    immediately instead of waiting for the next keystroke/tick — the same
    "prompt refreshes right now" effect asked for elsewhere in the toolbar.
    """
    kb = KeyBindings()

    @kb.add("enter")
    def _(event):
        buf = event.current_buffer
        # Strip lone UTF-16 surrogates a Windows-console paste can carry, before
        # anything encodes them (history save, or the submitted line). Belt to
        # _SafeFileHistory's braces.
        if any(0xD800 <= ord(c) <= 0xDFFF for c in buf.text):
            clean = "".join(c for c in buf.text
                            if not 0xD800 <= ord(c) <= 0xDFFF)
            buf.text = clean
            buf.cursor_position = min(buf.cursor_position, len(clean))
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

    if on_cycle_permission is not None:
        @kb.add("s-tab")  # Shift+Tab -> cycle permission mode (Claude-Code-style)
        def _(event):
            on_cycle_permission()
            event.app.invalidate()

    return kb


class UI:
    def __init__(self, model_name: str = "gateway/sonnet", cwd: Optional[str] = None,
                 commands: Optional[List[str]] = None, stderr: bool = False,
                 editor: Optional[str] = None, theme: Optional[str] = None):
        self.model_name = model_name
        self.cwd = str(cwd or os.getcwd())
        # Editor for clickable file:line jumps (file | vscode | cursor | vscodium).
        self.editor = editor or os.environ.get("ROBODOG_EDITOR", "file")
        # Color theme: --theme / ROBODOG_THEME / settings.json default -> "default".
        self.theme = (theme or os.environ.get("ROBODOG_THEME", "default")).strip().lower()
        self._C = self._THEMES.get(self.theme, self._THEMES["default"])
        self.total_tokens = 0
        self.bg_running = 0          # background tasks (wired later)
        self.context_pct = 0         # transcript fill estimate (loop sets)
        # stderr=True: headless -p mode — decorations go to stderr so stdout
        # carries only the final result.
        self.console = Console(stderr=stderr) if _HAVE_RICH else None
        self._stderr = stderr
        self._status = None          # active rich spinner
        # Resolve the stream-line caps from the env NOW (config.env is loaded
        # before the UI is built), not at import time.
        self.STREAM_LIMIT, self.TURN_STREAM_LIMIT = UI.stream_settings()
        self._typing = False         # user is typing a mid-turn line (suppress spinner)
        self._interactive = bool(
            _HAVE_PT and sys.stdin.isatty() and sys.stdout.isatty()
        )
        self._session = None
        # Permission-mode indicator (shift+tab cycle). Wired post-construction
        # via wire_permission_registry() once the ToolRegistry exists; empty
        # until then, so the segment just doesn't render.
        self.permission_label = ""
        self._cycle_permission_cb = None
        if self._interactive:
            hist_dir = Path.home() / ".robodog"
            hist_dir.mkdir(parents=True, exist_ok=True)
            # Slash commands + @-path completion (files/dirs under cwd).
            completer = _RobodogCompleter(commands or [], self.cwd)

            def _do_cycle_permission():
                if self._cycle_permission_cb is not None:
                    self.permission_label = self._cycle_permission_cb()

            self._session = PromptSession(
                history=_SafeFileHistory(str(hist_dir / "terminal_history")),
                completer=completer,
                bottom_toolbar=self._toolbar,
                complete_while_typing=True,
                # multiline=True keeps pasted newlines in the buffer instead of
                # submitting at the first one. Bracketed paste (default in
                # prompt_toolkit) inserts pasted text via insert_text, so the
                # custom Enter binding below does NOT fire per pasted line —
                # multi-line cut/paste is captured whole, like a modern agentic terminal.
                multiline=True,
                key_bindings=_input_key_bindings(_do_cycle_permission),
                prompt_continuation=lambda width, ln, wrapped: "  " if not wrapped else "",
                # Black background for the status toolbar (the default light/
                # reversed bar looks out of place with the emoji + ANSI colors).
                style=_PTStyle.from_dict({
                    "bottom-toolbar": "bg:#000000 noreverse",
                    "bottom-toolbar.text": "bg:#000000",
                }),
            )

    def wire_permission_registry(self, registry) -> None:
        """Call once the ToolRegistry exists (app.py, right after it's built)
        to hook up shift+tab -> registry.cycle_permission_mode() and seed the
        initial status-bar label from the registry's current mode/guard."""
        self._cycle_permission_cb = registry.cycle_permission_mode
        self.permission_label = registry.permission_mode_label()

    # ---- status line (emoji + color, an agentic coding terminal custom style) ----------
    # Swappable ANSI palettes — same keys, different values, so every call site
    # (self._C[...]) is theme-agnostic. `self._C` is picked in __init__ (or via
    # set_theme()); this is a CLASS attribute of named palettes, not the active
    # one.
    _THEMES: Dict[str, Dict[str, str]] = {
        "default": {   # protanopia-safe: cyan / yellow / magenta + emoji severity
            "magenta_b": "\033[1;35m", "magenta": "\033[0;35m",
            "cyan": "\033[0;36m", "yellow": "\033[0;33m",
            "gray": "\033[0;90m", "reset": "\033[0m",
        },
        "high-contrast": {   # bold + higher-saturation; red for the top severity tier
            "magenta_b": "\033[1;31m", "magenta": "\033[0;31m",
            "cyan": "\033[1;36m", "yellow": "\033[1;33m",
            "gray": "\033[0;37m", "reset": "\033[0m",
        },
        "mono": {   # no color at all — dumb terminals, log capture, screen readers
            "magenta_b": "", "magenta": "", "cyan": "", "yellow": "", "gray": "", "reset": "",
        },
        "pip-boy": {   # Fallout Pip-Boy: monochrome green phosphor CRT. Every
            # role maps to a shade of green instead of a different hue — bold
            # bright green for the loudest tier, dim green for the least
            # important (folder), so severity still reads by INTENSITY, the
            # way a real amber/green terminal has no other way to do it.
            "magenta_b": "\033[1;92m", "magenta": "\033[0;92m",
            "cyan": "\033[0;32m", "yellow": "\033[1;32m",
            "gray": "\033[2;32m", "reset": "\033[0m",
        },
    }
    # Fenced-code-block syntax highlighting (rich Markdown's `code_theme=`,
    # a pygments style name) — matched per theme instead of rich's unconfigured
    # default, so `mono` genuinely means no color anywhere, code blocks included.
    _CODE_THEMES: Dict[str, str] = {
        "default": "monokai", "high-contrast": "fruity", "mono": "bw",
        "pip-boy": "vim",   # closest built-in pygments style to a green CRT
    }

    def set_theme(self, name: str) -> bool:
        """Switch the color theme live (e.g. the `/theme` command). Returns
        False for an unrecognized name, leaving the current theme untouched."""
        name = (name or "").strip().lower()
        if name not in self._THEMES:
            return False
        self.theme = name
        self._C = self._THEMES[name]
        return True

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

    def _permission_color(self) -> str:
        C = self._C
        lbl = self.permission_label
        if "bypass" in lbl:
            return C["magenta_b"]   # loudest warning — nothing is gated
        if "plan" in lbl:
            return C["cyan"]
        if "accept" in lbl:
            return C["yellow"]
        return C["gray"]            # "default"

    def status_line(self) -> str:
        """Plain (uncolored) status line — fallback + tests."""
        return "  ".join(t for t, _ in self._status_segments())

    def thinking_line(self, iteration: int) -> str:
        """Spinner text for a running turn, WITH the status bar folded in — the
        spinner is the only element that persists on screen mid-turn, so this is
        how model/tokens/context/branch stay visible while the agent works."""
        return (f"✳ Thinking… step {iteration} (ctrl-c cancel) · "
                + self.status_line())

    def _status_ansi(self) -> str:
        C = self._C
        sep = f" {C['gray']}|{C['reset']} "
        return sep.join(f"{color}{t}{C['reset']}"
                        for t, color in self._status_segments())

    def _permission_ansi(self) -> str:
        """The permission-mode indicator, colored — rendered on its OWN toolbar
        row (see _toolbar) rather than crammed in among the token/model/branch
        segments, so it reads like Claude Code's own status line instead of
        getting lost in a long `|`-separated row."""
        if not self.permission_label:
            return ""
        C = self._C
        return f"{self._permission_color()}{self.permission_label}{C['reset']}"

    def _toolbar(self):
        # prompt_toolkit bottom toolbar — two rows: status segments, then the
        # permission-mode indicator on its own line underneath. Returning text
        # with an embedded newline is all multi-line takes here; prompt_toolkit
        # sizes the toolbar window to fit it automatically.
        try:
            from prompt_toolkit.formatted_text import ANSI
            lines = [" " + self._status_ansi()]
            perm = self._permission_ansi()
            if perm:
                lines.append(" " + perm)
            return ANSI("\n".join(lines))
        except Exception:
            lines = [self.status_line()]
            if self.permission_label:
                lines.append(self.permission_label)
            return "\n".join(" " + ln for ln in lines)

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

    # ---- sticky mid-turn input (opt-in: ROBODOG_STICKY_INPUT=1) ----------
    def watch_turn_sticky(self, runner, on_command=None):
        """
        Claude Code-style mid-turn input: a real PromptSession anchored at the
        bottom while the agent works, with tool output scrolling ABOVE it via
        patch_stdout — so typing never gets scrambled by streamed output.

        Enter queues a follow-up (turn keeps running); Ctrl+B backgrounds;
        Ctrl+C cancels. The prompt closes on its own when the turn finishes.

        Robustness vs the earlier attempt that lost output: patch_stdout is
        held across the WHOLE watch (never opened/closed per-prompt, which left
        a window where writes went nowhere), and app.exit is guarded + retried
        so a race between a typed line and turn-completion can't hang the prompt.
        """
        from .turnrunner import TurnOutcome
        session = self._session
        if session is None:                      # non-interactive: just wait
            runner.join()
            if runner.error is not None:
                raise runner.error
            return TurnOutcome("done", runner.result, list(runner.queued))

        app = session.app
        DONE = ("__sticky_done__",)
        BG = ("__sticky_bg__",)
        kb = KeyBindings()

        @kb.add("c-b")
        def _(event):
            event.app.exit(result=BG)

        orig_kb = session.key_bindings
        session.key_bindings = merge_key_bindings([orig_kb, kb])
        self._typing = True                      # suppress the rich Live spinner
        stop = threading.Event()

        def _watcher():
            runner.join()                        # block until the turn finishes
            # Keep asking the running prompt to close until it actually does —
            # covers the gap between one prompt() returning and the next starting.
            while not stop.wait(0.03):
                if app.is_running and app.loop is not None:
                    def _safe_exit():
                        try:
                            if app.is_running:
                                app.exit(result=DONE)
                        except Exception:        # pragma: no cover - "already set" race
                            pass
                    try:
                        app.loop.call_soon_threadsafe(_safe_exit)
                    except Exception:
                        pass

        threading.Thread(target=_watcher, daemon=True).start()

        outcome = None
        try:
            with patch_stdout(raw=True):
                while True:
                    try:
                        line = session.prompt("› ")
                    except KeyboardInterrupt:
                        cancel_event = runner.loop.cancel_event
                        if cancel_event is not None:
                            cancel_event.set()
                        runner.join(timeout=10)
                        outcome = TurnOutcome("cancelled", runner.result,
                                             list(runner.queued))
                        break
                    if line is DONE:
                        break
                    if line is BG:
                        outcome = TurnOutcome("backgrounded", None,
                                             list(runner.queued))
                        break
                    if isinstance(line, str) and line.strip():
                        # A read-only slash command runs in-place (output scrolls
                        # above via patch_stdout); anything else is queued.
                        handled = False
                        if on_command is not None:
                            try:
                                handled = bool(on_command(line.strip()))
                            except Exception:
                                handled = False
                        if not handled:
                            runner.queued.append(line.strip())
                    if not runner.running():
                        break
        finally:
            stop.set()
            self._typing = False
            session.key_bindings = orig_kb

        if outcome is not None:
            return outcome
        if runner.error is not None:
            raise runner.error
        return TurnOutcome("done", runner.result, list(runner.queued))

    # ---- spinner --------------------------------------------------------
    def spinner_start(self, text: str):
        # While the user is typing a mid-turn line, a rich Live spinner would
        # repaint over their keystrokes and fragment each char onto its own
        # line. Suppress it until they submit.
        if getattr(self, "_typing", False):
            return
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

    # ---- mid-turn typing ------------------------------------------------
    # Echo a line the user types WHILE the agent is working, without the Live
    # spinner shredding it. The raw key reader (turnrunner.make_key_source)
    # calls these; they own a single clean input line.
    def mid_input_start(self):
        """First keystroke of a mid-turn line: stop the spinner, mark typing
        active (so it can't restart over the text), and print a prompt."""
        self.spinner_stop()
        self._typing = True
        if sys.stdout.isatty():
            sys.stdout.write("\n› ")
            sys.stdout.flush()

    def mid_input_echo(self, ch: str):
        if sys.stdout.isatty():
            sys.stdout.write(ch)
            sys.stdout.flush()

    def mid_input_backspace(self):
        if sys.stdout.isatty():
            sys.stdout.write("\b \b")
            sys.stdout.flush()

    def mid_input_end(self):
        """Line submitted (or input abandoned): let the spinner run again."""
        was_typing = getattr(self, "_typing", False)
        self._typing = False
        if was_typing and sys.stdout.isatty():
            sys.stdout.write("\n")
            sys.stdout.flush()

    def reset_typing(self):
        """Belt-and-braces: never leave the spinner suppressed after a turn."""
        self._typing = False

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

    def warn(self, msg: str):
        """An amber notice — attention-getting but NOT an error (used for the
        approval prompt, which reads wrong in red)."""
        if self.console:
            self.console.print(msg, style="yellow", markup=False, highlight=False)
        else:
            print(msg)

    def assistant(self, text: str):
        """Render a final answer as markdown (falls back to plain text)."""
        if self.console:
            try:
                code_theme = self._CODE_THEMES.get(self.theme, "monokai")
                self.console.print(Markdown(text, code_theme=code_theme))
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
    # trace shows a small bounded head and then reports what it held back — the
    # `↳` summary line (exit status + line count) carries the result. The MODEL
    # still receives the complete output; this caps the DISPLAY only.
    #   ROBODOG_STREAM_LINES=0      -> no live stream at all (summary only)
    #   ROBODOG_TURN_STREAM_LINES=0 -> no per-turn cap
    # NOTE: read in __init__ (see stream_settings), NOT at class-definition time,
    # so values from ~/.robodog/config.env (loaded during startup, after this
    # module is imported) actually take effect.
    STREAM_LIMIT = 8          # per-command default (overridden per-instance)
    TURN_STREAM_LIMIT = 40    # per-turn default (overridden per-instance)

    @staticmethod
    def stream_settings():
        """(per-command limit, per-turn limit) resolved from the env RIGHT NOW —
        so config.env values loaded during startup are honored."""
        try:
            per_cmd = int(os.environ.get("ROBODOG_STREAM_LINES", "8") or 8)
        except ValueError:
            per_cmd = 8
        try:
            per_turn = int(os.environ.get("ROBODOG_TURN_STREAM_LINES", "40") or 40)
        except ValueError:
            per_turn = 40
        return per_cmd, per_turn

    def reset_turn_stream(self):
        """Start-of-turn: reset the per-turn live-preview budget."""
        self._turn_stream = 0

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

        if self.STREAM_LIMIT <= 0:
            return   # summary-only mode: the `↳` line reports the result

        # Collapse runs of blank lines — PowerShell in particular emits many,
        # and a column of empty │ bars is pure noise.
        if not line.strip():
            if self._stream_blank or self._stream_shown == 0:
                return
            self._stream_blank = True
        else:
            self._stream_blank = False

        turn = getattr(self, "_turn_stream", 0)
        over_turn = self.TURN_STREAM_LIMIT > 0 and turn >= self.TURN_STREAM_LIMIT
        if not over_turn and self._stream_shown < self.STREAM_LIMIT:
            self._stream_shown += 1
            self._turn_stream = turn + 1
            self.dim(f"  │ {line}")
        elif not self._stream_capped:
            self._stream_capped = True
            note = ("  │ … (turn preview budget reached — summaries only; "
                    "full output still goes to the model)" if over_turn
                    else "  │ … output continues (shown in full to the model)")
            self.dim(note)

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
        import re as _re
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
            # result leads with "N match(es) for /…/:" — that header IS the
            # summary; don't append a redundant "(+N more)".
            if _re.match(r"\d+ match", first):
                return self._flatten(first, 120), "dim"
            more = f"  (+{n - 1} more)" if n > 1 else ""
            return self._flatten(first, 100) + more, "dim"

        if name in ("glob", "list_dir"):
            if first.lower().startswith("no files"):
                return self._flatten(first, 120), "dim"
            # glob leads with "N file(s) matching …" — use that (accurate count).
            if name == "glob" and _re.match(r"\d+ file", first):
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
