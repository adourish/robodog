# robodog/throttle_spinner.py
import sys
import time

class ThrottledSpinner:
    """
    A simple spinner that only redraws every `interval` seconds
    to reduce stdout churn, plus a text‐based progress bar.
    """
    def __init__(self, interval: float = 0.1, bar_width: int = 30):
        self.interval = interval
        self.last_time = 0.0
        self.chars = ['|', '/', '-', '\\']
        self.idx = 0
        self.running = False
        self.bar_width = bar_width

    def start(self):
        """Print the first spinner frame."""
        if not self.running:
            self.running = True
            self.last_time = time.time()
            sys.stdout.write(self.chars[self.idx])
            sys.stdout.flush()

    def spin(self, force: bool = False):
        """
        Advance the spinner if enough time has passed
        (or if force=True).
        """
        if not self.running:
            return

        now = time.time()
        if force or (now - self.last_time) >= self.interval:
            # backspace over previous char
            sys.stdout.write('\b' + self.chars[self.idx])
            sys.stdout.flush()
            self.idx = (self.idx + 1) % len(self.chars)
            self.last_time = now

    def stop(self):
        """Erase spinner and move to a fresh line."""
        if self.running:
            sys.stdout.write('\b')  # remove spinner char
            sys.stdout.write('\n')  # newline after progress bar
            sys.stdout.flush()
            self.running = False

    def print_bar(self, count: int, total: int):
        """
        Draw a [=====   ] XX% progress bar on the same line.
        If total is zero or None, just prints a chunk counter.
        """
        if total:
            frac = min(max(count / total, 0.0), 1.0)
            filled = int(self.bar_width * frac)
            empty = self.bar_width - filled
            pct = int(frac * 100)
            bar = '=' * filled + ' ' * empty
            sys.stdout.write(f'\rProgress: [{bar}] {pct:3d}%')
        else:
            sys.stdout.write(f'\rChunks processed: {count}')
        sys.stdout.flush()