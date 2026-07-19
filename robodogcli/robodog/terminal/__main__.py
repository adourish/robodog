# file: terminal/__main__.py
"""Entry point for `python -m robodog.terminal`."""
from __future__ import annotations

try:
    from .app import main
except ImportError:  # running the folder directly
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    from terminal.app import main

if __name__ == "__main__":
    raise SystemExit(main())
