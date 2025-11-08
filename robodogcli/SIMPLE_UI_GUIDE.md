# Simple UI Guide

## What Changed

We've replaced the Textual framework with a **custom simple UI** using ANSI escape codes. This is:
- ✅ **More reliable** - Direct terminal control, no framework overhead
- ✅ **Easier to debug** - Simple code, easy to trace
- ✅ **Faster** - No complex rendering pipeline
- ✅ **Same look** - Maintains the Pip-Boy aesthetic

## How It Works

The simple UI uses:
- **ANSI escape codes** for colors and cursor positioning
- **Threading** for refresh loop and input handling
- **Deques** for efficient message storage
- **Locks** for thread-safe updates

## Usage

Start RoboDog with the `--pipboy` flag:

```bash
python robodog\cli.py --folders . --port 2500 --token testtoken --config config.yaml --model openai/o4-mini --log-level INFO --diff --pipboy
```

## UI Layout

```
╔══════════════════════════════════════════════════════════╗
║ ROBODOG │ openai/o4-mi │ 12:53:45                       ║
╚══════════════════════════════════════════════════════════╝
┌─ STATUS ─────────────────────────────────────────────────┐
│ [12:53:45] ROBODOG SYSTEM ONLINE                         │
│ [12:53:46] Model: openai/o4-mini                         │
│ [12:53:47] Type /help for commands                       │
│                                                           │
└──────────────────────────────────────────────────────────┘
┌─ OUTPUT ─────────────────────────────────────────────────┐
│                                                           │
│ Command output appears here                              │
│                                                           │
│                                                           │
│                                                           │
│                                                           │
│                                                           │
└──────────────────────────────────────────────────────────┘
┌─ CMD ────────────────────────────────────────────────────┐
> Type command...                                           │
└──────────────────────────────────────────────────────────┘
```

## Features

### Auto-Refresh
- Screen refreshes 2x per second
- Time updates in real-time
- Status and output panels update automatically

### Thread-Safe
- All updates use locks to prevent race conditions
- Multiple threads can update simultaneously

### Simple Input
- Type commands directly at the prompt
- Press Enter to execute
- Cursor automatically positioned

## Commands

All the same commands work:
- `/help` - Show help
- `/models` - List models
- `/model <name>` - Switch model
- `/status` - Show dashboard
- `/q` - Quick status
- `/quit` or `/exit` - Exit
- And all other RoboDog commands

## Exit

Type any of:
- `/quit`
- `/exit`
- `quit`
- `exit`
- Or press Ctrl+C

## Technical Details

### Files
- `simple_ui.py` - Main UI implementation
- `cli.py` - Integration with RoboDog

### Key Classes
- `SimpleUI` - Core UI with ANSI rendering
- `SimpleUIWrapper` - Wrapper matching PipBoyUIWrapper interface

### Threading
- **Refresh thread** - Updates display every 0.5s
- **Input thread** - Handles user input
- **Main thread** - Runs MCP server and command processing

### ANSI Codes Used
- `\033[2J` - Clear screen
- `\033[H` - Move cursor home
- `\033[?25l` - Hide cursor
- `\033[?25h` - Show cursor
- `\033[92m` - Green color
- `\033[96m` - Cyan color
- `\033[93m` - Yellow color
- `\033[91m` - Red color

## Advantages Over Textual

1. **No Dependencies** - Just uses built-in Python
2. **Direct Control** - We control exactly what happens
3. **Easy Debugging** - Simple code path
4. **Fast** - No framework overhead
5. **Reliable** - No complex event loops or async issues

## Testing

Try these commands to verify it works:

```
/test
/models
/help
/model gpt-4
/status
```

You should see:
- Commands appear in STATUS panel
- Output appears in OUTPUT panel
- Model name updates in header
- Time updates every second
