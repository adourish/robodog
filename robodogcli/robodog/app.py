# file: app.py
#!/usr/bin/env python3
import sys
from typing import List, Union

class RobodogApp:
    """
    Simple console app: maintains an in-memory log (list of strings),
    echoing all new lines to stdout.  Provides get/set methods
    so other modules can inspect or override the log.
    """

    def __init__(self) -> None:
        self._log: List[str] = []

    def display_command(self, text: str) -> None:
        """
        Append a line to the log and print it to stdout.
        """
        self._log.append(text)
        print(text)

    def get_log(self) -> List[str]:
        """
        Return the current log buffer as a list of lines.
        """
        return list(self._log)

    def set_log(self, lines: Union[str, List[str]]) -> None:
        """
        Replace the log buffer.  Accepts either a single
        newline-separated string or a list of lines.
        """
        if isinstance(lines, str):
            self._log = lines.splitlines()
        else:
            self._log = list(lines)

    def clear_log(self) -> None:
        """
        Clear the in-memory log buffer.  Does not erase stdout history.
        """
        self._log.clear()

    def format_plan_start(self, task_desc: str) -> str:
        """Format the start of a planning message."""
        return f"🚀 Starting Plan: {task_desc}"

    def format_plan_progress(self, update: str) -> str:
        """Format a planning progress message."""
        return f"📝 Planning progress: {update}"

    def format_plan_written(self, path: str, tokens: int) -> str:
        """Format the plan written completion message."""
        return f"✅ Plan written: {path} ({tokens} tokens)"

    def format_plan_done(self, task_desc: str) -> str:
        """Format the plan done completion message."""
        return f"✅ Plan completed: {task_desc}"

    def run_command(self, cmd: str) -> None:
        """
        Dispatch command: Handle planning-related commands.
        """
        # Planning commands (e.g., called via explicit routing if needed)
        if cmd.startswith("plan:start "):
            task_desc = cmd[10:].strip()  # Extract task description
            self.display_command(self.format_plan_start(task_desc))
        elif cmd.startswith("plan:progress "):
            update = cmd[14:].strip()  # Extract progress update
            self.display_command(self.format_plan_progress(update))
        elif cmd.startswith("plan:written "):
            parts = cmd[12:].strip().split(" ", 1)
            path = parts[0]
            tokens = int(parts[1]) if len(parts) > 1 else 0
            self.display_command(self.format_plan_written(path, tokens))
        elif cmd.startswith("plan:done "):
            task_desc = cmd[9:].strip()
            self.display_command(self.format_plan_done(task_desc))
        else:
            # Default: Echo unknown commands
            self.display_command(f"Unknown command: {cmd}")

    def run(self) -> None:
        """
        Main REPL loop. (Note: This is not currently used in CLI integration; kept for standalone mode.)
        """
        self.display_command("Robodog Code Console")
        self.display_command("Type /help for a list of commands")
        while True:
            try:
                cmd = input("> ").strip()
            except (EOFError, KeyboardInterrupt):
                self.display_command("\nExiting RobodogApp. Goodbye!")
                break

            if not cmd:
                continue

            # echo
            self.display_command(f"> {cmd}")
            # dispatch
            self.run_command(cmd)

# Original file length: 100 lines
# Updated file length: 115 lines