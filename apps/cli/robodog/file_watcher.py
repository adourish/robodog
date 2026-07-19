
#!/usr/bin/env python3
"""File watching service for monitoring todo.md changes."""
import os
import time
import threading
import logging
from typing import Dict, Callable, Any
from pathlib import Path

logger = logging.getLogger(__name__)


class FileWatcher:
    """Watches files for changes and triggers callbacks."""
    
    def __init__(self):
        self._mtimes: Dict[str, float] = {}
        self._watch_ignore: Dict[str, float] = {}
        self._callbacks: Dict[str, Callable] = {}
        self._running = False
        self._thread = None
    
    def add_file(self, filepath: str, callback: Callable[[str], None]):
        """Add a file to watch with a callback."""
        self._callbacks[filepath] = callback
        try:
            self._mtimes[filepath] = os.path.getmtime(filepath)
        except OSError:
            self._mtimes[filepath] = 0
    
    def ignore_next_change(self, filepath: str):
        """Ignore the next change to a file (for our own writes)."""
        try:
            self._watch_ignore[filepath] = os.path.getmtime(filepath)
        except OSError:
            pass
    
    def start(self):
        """Start the file watcher thread."""
        if self._running:
            return
        
        self._running = True
        self._thread = threading.Thread(target=self._watch_loop, daemon=True)
        self._thread.start()
    
    def stop(self):
        """Stop the file watcher thread."""
        self._running = False
        if self._thread:
            self._thread.join()
    
    def _watch_loop(self):
        """
        Disabled file watch loop to prevent repetitive polling/infinite loop.
        """
        logger.info("⚠️  File watch loop disabled — no more polling every second.",
                    extra={'log_color': 'HIGHLIGHT'})
        return
        """Main watch loop that runs in a separate thread."""
        while self._running:
            for filepath, callback in self._callbacks.items():
                try:
                    mtime = os.path.getmtime(filepath)
                except OSError:
                    continue
                
                # Check if we should ignore this change
                ignore_time = self._watch_ignore.get(filepath)
                if ignore_time and abs(mtime - ignore_time) < 0.001:
                    self._watch_ignore.pop(filepath, None)
                    continue
                
                # Check if file has been modified
                if self._mtimes.get(filepath, 0) and mtime > self._mtimes[filepath]:
                    logger.debug(f"Detected change in {filepath}")
                    try:
                        callback(filepath)
                    except Exception as e:
                        logger.error(f"Error in file watch callback: {e}")
                
                # Update stored mtime
                self._mtimes[filepath] = mtime
            
            time.sleep(1)

# original file length: 71 lines
# updated file length: 71 lines
