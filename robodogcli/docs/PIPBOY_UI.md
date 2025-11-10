# Pip-Boy Style UI for RoboDog

## Overview

The Pip-Boy UI provides a retro terminal interface inspired by Fallout's Pip-Boy, featuring a refreshing display instead of scrolling output. The interface uses a classic green monochrome aesthetic with bordered panels.

## Features

- **Refreshing Display**: Screen updates in place instead of scrolling
- **Retro Aesthetic**: Green monochrome Pip-Boy style with ASCII borders
- **Real-time Status**: Live status log showing recent activity
- **Output Panel**: Dedicated area for AI responses and command output
- **Command Input**: Bottom input area for commands and messages

## Usage

### Starting the Pip-Boy UI

Add the `--pipboy` flag when starting RoboDog:

```bash
python -m robodog.cli --folders . --token YOUR_TOKEN --pipboy
```

### UI Layout

```
╔═══════════════════════════════════════════════════════════════════════╗
║ ROBOPUP INTEGRATED MANAGEMENT SYSTEM                                  ║
║ MODEL: GPT-4              TIME: 12:34:56                              ║
╚═══════════════════════════════════════════════════════════════════════╝

┌─ STATUS LOG ──────────────────────────────────────────────────────────┐
│ [12:34:56] ROBOPUP SYSTEM INITIALIZED                                 │
│ [12:34:57] Type /help for available commands                          │
│                                                                        │
└────────────────────────────────────────────────────────────────────────┘

┌─ OUTPUT ──────────────────────────────────────────────────────────────┐
│                                                                        │
│ AI responses and command output appear here                           │
│                                                                        │
└────────────────────────────────────────────────────────────────────────┘

┌─ COMMAND INPUT ───────────────────────────────────────────────────────┐
> Enter command or message...
└────────────────────────────────────────────────────────────────────────┘
```

### Keyboard Shortcuts

- **Ctrl+C**: Quit the application
- **Ctrl+L**: Clear output panel
- **F1**: Show help

### Exit Commands

You can exit the Pip-Boy UI using any of these methods:
- Type `/quit` or `/exit` or `quit` or `exit`
- Press **Ctrl+C**
- Close the terminal window

### Supported Commands

All standard RoboDog commands work in Pip-Boy mode:

**System Commands:**
- `/help` - Show all available commands
- `/quit` or `/exit` - Exit the application
- `/clear` - Clear chat history and output

**Model & Configuration:**
- `/models` - List available models
- `/model <name>` - Switch to a different model
- `/key <provider> <key>` - Set API key for provider
- `/getkey <provider>` - Get API key for provider
- `/temperature <n>` - Set temperature
- `/top_p <n>` - Set top_p
- `/max_tokens <n>` - Set max_tokens
- `/frequency_penalty <n>` - Set frequency penalty
- `/presence_penalty <n>` - Set presence penalty
- `/stream` - Enable streaming mode
- `/rest` - Disable streaming mode

**Task Management:**
- `/status` - Show full dashboard
- `/q` - Quick status
- `/budget` - Show token budget
- `/shortcuts` - Show keyboard shortcuts

**File & Knowledge:**
- `/import <glob>` - Import files into knowledge
- `/export <file>` - Export chat+knowledge snapshot
- `/folders <dirs>` - Set MCP roots
- `/include [spec] [prompt]` - Include files via MCP

**State Management:**
- `/stash <name>` - Stash current state
- `/pop <name>` - Restore stashed state
- `/list` - List all stashes

**Advanced:**
- `/curl <url>` - Fetch web pages/scripts
- `/play <command>` - Run AI-driven Playwright tests
- `/mcp <op> [json]` - Invoke raw MCP operation

**Regular Messages:**
- Any message without a `/` prefix is sent to the AI

### Color Coding

- **Green**: Normal status messages
- **Yellow**: Warnings
- **Red**: Errors
- **Cyan**: Success messages and highlights
- **White**: Output text

## Technical Details

### Implementation

The Pip-Boy UI is built using the [Textual](https://textual.textualize.io/) framework, which provides:

- Rich terminal UI components
- Reactive updates
- Cross-platform support
- Async event handling

### Components

- **PipBoyHeader**: Displays system info and current time
- **StatusPanel**: Shows recent log messages (last 15 entries)
- **OutputPanel**: Displays AI responses and command output (last 25 lines)
- **CommandInput**: Text input for commands and messages

### Integration

The UI runs in a separate thread and communicates with the main RoboDog service through:

- Command callbacks for user input
- Status logging for system messages
- Output methods for displaying results

## Troubleshooting

### UI doesn't start

Ensure Textual is installed:
```bash
pip install textual>=0.40.0
```

### Colors not displaying correctly

On Windows, ensure your terminal supports ANSI colors:
- Windows Terminal (recommended)
- PowerShell 7+
- ConEmu

### UI is too small

Resize your terminal window to at least 80x40 characters for optimal display.

## Fallback Mode

If the Pip-Boy UI fails to start, RoboDog will automatically fall back to the traditional scrolling CLI mode.
