# file: entry.py
"""
Lightweight top-level dispatcher for the `robodog` command.

Routes `robodog terminal ...` straight to Terminal Mode WITHOUT importing the
heavy server CLI (service, MCP, langchain, colorlog, …), so the agentic
terminal is a true first-class citizen with minimal dependencies. Everything
else falls through to the original server/CLI entry point unchanged.
"""
from __future__ import annotations

import sys


def main() -> int:
    argv = sys.argv[1:]
    if argv and argv[0] == "terminal":
        try:
            from robodog.terminal.app import main as terminal_main
        except ImportError:  # running from a source checkout
            from terminal.app import main as terminal_main
        return terminal_main(argv[1:])
    # default: the combined MCP file-server + Robodog CLI
    from robodog.cli import main as cli_main
    return cli_main()


if __name__ == "__main__":
    raise SystemExit(main())
