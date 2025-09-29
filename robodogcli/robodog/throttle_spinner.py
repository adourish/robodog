# robodog/throttle_spinner.py
import sys
import time

class ThrottledSpinner:
    """
    A simple spinner that only redraws every `interval` seconds
    to reduce stdout churn.
    """
    def __init__(self, interval: float = 0.1):
        self.interval = interval
        self.last_time = 0.0
        self.chars = ['|', '/', '-', '\\']
        self.idx = 0
        self.running = False

    def start(self):    
        """Initialize spinner state and print first frame."""
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
        """Remove spinner character and reset."""
        if self.running:
            sys.stdout.write('\b')
            sys.stdout.flush()
            self.running = False