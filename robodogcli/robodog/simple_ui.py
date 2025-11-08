#!/usr/bin/env python3
"""
Simple Terminal UI for RoboDog CLI
Uses ANSI escape codes for a refreshing interface
"""

import os
import sys
import threading
import time
from datetime import datetime
from collections import deque


class SimpleUI:
    """Simple refreshing terminal UI using ANSI escape codes"""
    
    def __init__(self, model_name="GPT-4"):
        self.model_name = model_name
        self.status_messages = deque(maxlen=6)  # Last 6 status messages
        self.output_lines = deque(maxlen=10)  # Last 10 output lines
        self.running = False
        self.lock = threading.Lock()
        self.command_callback = None
        
        # ANSI escape codes
        self.CLEAR_SCREEN = '\033[2J'
        self.MOVE_HOME = '\033[H'
        self.CLEAR_LINE = '\033[K'
        self.GREEN = '\033[92m'
        self.CYAN = '\033[96m'
        self.YELLOW = '\033[93m'
        self.RED = '\033[91m'
        self.WHITE = '\033[97m'
        self.RESET = '\033[0m'
        self.BOLD = '\033[1m'
        
    def start(self):
        """Start the UI"""
        self.running = True
        
        # Clear screen and hide cursor
        sys.stdout.write(self.CLEAR_SCREEN + self.MOVE_HOME)
        sys.stdout.write('\033[?25l')  # Hide cursor
        sys.stdout.flush()
        
        # Start refresh thread
        self.refresh_thread = threading.Thread(target=self._refresh_loop, daemon=True)
        self.refresh_thread.start()
        
        # Start input thread
        self.input_thread = threading.Thread(target=self._input_loop, daemon=True)
        self.input_thread.start()
        
    def stop(self):
        """Stop the UI"""
        self.running = False
        sys.stdout.write('\033[?25h')  # Show cursor
        sys.stdout.write('\n')
        sys.stdout.flush()
        
    def _refresh_loop(self):
        """Refresh the display periodically"""
        while self.running:
            self._render()
            time.sleep(0.5)  # Refresh twice per second
            
    def _render(self):
        """Render the UI"""
        with self.lock:
            lines = []
            
            # Header
            now = datetime.now().strftime("%H:%M:%S")
            lines.append(f"{self.BOLD}{self.GREEN}╔══════════════════════════════════════════════════════════════════════════════╗{self.RESET}")
            lines.append(f"{self.BOLD}{self.GREEN}║ {self.CYAN}ROBODOG{self.GREEN} │ {self.YELLOW}{self.model_name:<20}{self.GREEN} │ {self.GREEN}{now}                              {self.GREEN}║{self.RESET}")
            lines.append(f"{self.BOLD}{self.GREEN}╚══════════════════════════════════════════════════════════════════════════════╝{self.RESET}")
            
            # Status panel
            lines.append(f"{self.GREEN}┌─ STATUS {('─' * 70)}┐{self.RESET}")
            for i in range(6):
                if i < len(self.status_messages):
                    timestamp, msg, level = self.status_messages[i]
                    color = self._get_color(level)
                    msg_display = msg[:66]
                    lines.append(f"{self.GREEN}│ {self.GREEN}[{timestamp}] {color}{msg_display:<66}{self.GREEN}│{self.RESET}")
                else:
                    lines.append(f"{self.GREEN}│{' ' * 78}│{self.RESET}")
            lines.append(f"{self.GREEN}└{'─' * 78}┘{self.RESET}")
            
            # Output panel
            lines.append(f"{self.GREEN}┌─ OUTPUT {('─' * 70)}┐{self.RESET}")
            for i in range(10):
                if i < len(self.output_lines):
                    line = self.output_lines[i][:76]
                    lines.append(f"{self.GREEN}│ {self.WHITE}{line:<76}{self.GREEN}│{self.RESET}")
                else:
                    lines.append(f"{self.GREEN}│{' ' * 78}│{self.RESET}")
            lines.append(f"{self.GREEN}└{'─' * 78}┘{self.RESET}")
            
            # Command input
            lines.append(f"{self.GREEN}┌─ CMD {('─' * 72)}┐{self.RESET}")
            lines.append(f"{self.GREEN}> {self.YELLOW}Type command...{' ' * 62}{self.GREEN}│{self.RESET}")
            lines.append(f"{self.GREEN}└{'─' * 78}┘{self.RESET}")
            
            # Move to home and print
            output = self.MOVE_HOME + '\n'.join(lines)
            sys.stdout.write(output)
            sys.stdout.flush()
    
    def _get_color(self, level):
        """Get color for log level"""
        colors = {
            'INFO': self.GREEN,
            'SUCCESS': self.CYAN,
            'WARNING': self.YELLOW,
            'ERROR': self.RED,
            'DEBUG': self.WHITE
        }
        return colors.get(level, self.WHITE)
    
    def _input_loop(self):
        """Handle user input"""
        while self.running:
            try:
                # Move cursor to input line
                sys.stdout.write('\033[19;3H')  # Line 19, column 3
                sys.stdout.write('\033[?25h')  # Show cursor
                sys.stdout.flush()
                
                command = input().strip()
                
                sys.stdout.write('\033[?25l')  # Hide cursor
                
                if not command:
                    continue
                    
                # Check for quit
                if command.lower() in ['/quit', '/exit', 'quit', 'exit']:
                    self.log_status("Shutting down...", "INFO")
                    self.running = False
                    break
                
                # Log command
                self.log_status(f"CMD: {command}", "INFO")
                
                # Process command
                if self.command_callback:
                    try:
                        self.command_callback(command)
                    except Exception as e:
                        self.log_status(f"Error: {str(e)}", "ERROR")
                        import traceback
                        self.set_output(traceback.format_exc())
                        
            except EOFError:
                break
            except KeyboardInterrupt:
                self.running = False
                break
    
    def log_status(self, message, level="INFO"):
        """Add a status message"""
        with self.lock:
            timestamp = datetime.now().strftime("%H:%M:%S")
            self.status_messages.append((timestamp, message, level))
    
    def set_output(self, text):
        """Set output text"""
        with self.lock:
            lines = text.split('\n')
            self.output_lines.clear()
            for line in lines[:10]:  # Only keep first 10 lines
                self.output_lines.append(line)
    
    def append_output(self, text):
        """Append to output"""
        with self.lock:
            lines = text.split('\n')
            for line in lines:
                self.output_lines.append(line)
    
    def update_model_name(self, model_name):
        """Update the model name in header"""
        with self.lock:
            self.model_name = model_name
    
    def set_command_callback(self, callback):
        """Set the command callback"""
        self.command_callback = callback
    
    def wait(self):
        """Wait for UI to close"""
        if hasattr(self, 'input_thread'):
            self.input_thread.join()
        if hasattr(self, 'refresh_thread'):
            self.refresh_thread.join()


class SimpleUIWrapper:
    """Wrapper to match the PipBoyUIWrapper interface"""
    
    def __init__(self, svc):
        self.svc = svc
        self.ui = None
        self.running = False
    
    def start(self):
        """Start the UI"""
        model_name = self.svc.cur_model if self.svc else "GPT-4"
        self.ui = SimpleUI(model_name)
        self.running = True
        self.ui.start()
        time.sleep(0.5)  # Give UI time to initialize
    
    def log_status(self, message, level="INFO"):
        """Log a status message"""
        if self.ui and self.running:
            self.ui.log_status(message, level)
    
    def set_output(self, text):
        """Set output text"""
        if self.ui and self.running:
            self.ui.set_output(text)
    
    def append_output(self, text):
        """Append to output"""
        if self.ui and self.running:
            self.ui.append_output(text)
    
    def update_model_name(self, model_name):
        """Update model name"""
        if self.ui and self.running:
            self.ui.update_model_name(model_name)
    
    def set_command_callback(self, callback):
        """Set command callback"""
        if self.ui:
            self.ui.set_command_callback(callback)
    
    def wait(self):
        """Wait for UI to close"""
        if self.ui:
            try:
                self.ui.wait()
            finally:
                self.ui.stop()
                self.running = False
