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

    def run_command(self, cmd: str) -> None:
        """
        The same demo commands as before.
        """
 
    def run(self) -> None:
        """
        Main REPL loop.
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
