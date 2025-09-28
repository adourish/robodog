# file: app.py
#!/usr/bin/env python3
import logging
from textual.app import App, ComposeResult
from textual.containers import Container, Vertical, Horizontal
from textual.widgets import Header, Footer, Input, Button, Log
from textual import on
from typing import Optional

logger = logging.getLogger('robodog.mcphandler')

class RobodogApp(App):
    """Pip-Boy–style console with scrollback log and command input."""

    CSS = r"""
    Screen {
        background: rgb(10,10,10);
    }
    #log-container {
        border: heavy green;
        height: 1fr;
        background: black;
    }
    #input-container {
        border: heavy green;
        height: 3;
    }
    Input {
        background: black;
        color: green;
        border: none;
    }
    Button {
        background: green;
        color: black;
        border: none;
    }
    """

    def compose(self) -> ComposeResult:
        # a small header at top, log in the middle, command entry at bottom
        yield Header(show_clock=True)
        yield Container(
            Log(id="log-pane", highlight=False),
            id="log-container",
        )
        yield Container(
            Horizontal(
                Input(placeholder="/models, /help …", id="cmd-input"),
                Button("SUBMIT", id="submit-btn"),
                id="input-container"

            ),
        )
        yield Footer()

    def on_mount(self) -> None:
        """When app starts, greet the user."""
        log = self.query_one("#log-pane", Log)
        log.write_line("Robodog Code Console[/]")
        log.write_line("Type /help for a list of commands[/]")

    @on(Button.Pressed, "#submit-btn")
    @on(Input.Submitted, "#cmd-input")
    def handle_command(self, event) -> None:
        """When the user presses the button or hits Enter in the input."""
        cmd_in = self.query_one("#cmd-input", Input)
        cmd = cmd_in.value.strip()
        if not cmd:
            return
        log = self.query_one("#log-pane", Log)
        # echo the command
        log.write_line(f"[yellow]> {cmd}[/]")
        # clear the input
        cmd_in.value = ""
        # dispatch
        self.run_command(cmd, log)

    def run_command(self, cmd: str, log: Log) -> None:
        """Stub out a few demo commands."""
        if cmd == "/help":
            log.write_line("Available commands:")
            log.write_line("  /models   – list models")
            log.write_line("  /echo ... – echo back text")
            log.write_line("  /clear    – clear the log")
        elif cmd == "/models":
            # you could pull this from openai or another API
            models = ["gpt-3.5-turbo", "gpt-4", "custom-robodog-v1"]
            log.write_line("Installed models:")
            for m in models:
                log.write_line(f"  • {m}")
        elif cmd.startswith("/echo "):
            payload = cmd[len("/echo "):]
            log.write_line(f"Echo: {payload}")
        elif cmd == "/clear":
            log.clear()
        else:
            log.write_line(f"[red]Unknown command:[/] {cmd}")

    # New: method to display a string in the log pane (safe to be called from App thread)
    def display_command(self, text: str, *, markup: bool = True) -> None:
        """
        Display a line of text in the app's log pane. Can be scheduled from other threads
        using call_from_thread (see display_command_threadsafe).
        """
        try:
            log = self.query_one("#log-pane", Log)
            # Write directly; the Log widget supports markup
            if markup:
                log.write_line(text)
            else:
                # escape markup by surrounding with backticks in case needed; simplest: write raw
                log.write_line(text)
        except Exception as e:
            logger.exception(f"Failed to display command in UI: {e}")

    def display_command_threadsafe(self, text: str, *, markup: bool = True) -> None:
        """
        Thread-safe helper to display text in the UI from other threads.
        Use app.call_from_thread(app.display_command, text).
        """
        try:
            # call_from_thread will schedule display_command on the app thread
            self.call_from_thread(self.display_command, text, markup=markup)
        except Exception as e:
            # If we fail to schedule, try a direct call (best-effort)
            try:
                self.display_command(text, markup=markup)
            except Exception:
                logger.exception(f"Failed to schedule display_command_threadsafe: {e}")

# Original file length: 123 lines
# Updated file length: 165 lines