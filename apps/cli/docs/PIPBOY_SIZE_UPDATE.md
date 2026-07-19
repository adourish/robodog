# Pip-Boy UI Size Update

## New Compact Dimensions

The Pip-Boy UI has been reduced to fit within approximately **21 lines** of terminal height.

### Panel Heights:
- **Header**: 3 lines (model name and time)
- **Status Log**: 6 lines (shows last 4 status messages)
- **Output Panel**: 9 lines (shows last 7 lines of output)
- **Command Input**: 3 lines
- **Total**: ~21 lines

### Width:
- **60 characters** wide

## Comparison

### Before:
- Height: ~30 lines
- Status: 10 lines (8 messages)
- Output: 14 lines (12 lines of text)

### After:
- Height: ~21 lines
- Status: 6 lines (4 messages)
- Output: 9 lines (7 lines of text)

## Perfect For:
- VSCode integrated terminal
- Small terminal windows
- Split-screen development
- Matching the height of typical log output (~22 lines)

## Layout:

```
╔══════════════════════════════════════════════════════════╗
║ ROBOPUP │ openai/o4-mi │ 12:34:56                       ║
╚══════════════════════════════════════════════════════════╝
┌─ STATUS ─────────────────────────────────────────────────┐
│ [12:34:56] ROBOPUP SYSTEM ONLINE                         │
│ [12:34:57] Model: openai/o4-mini                         │
│ [12:34:58] Type /help for commands                       │
│                                                           │
└──────────────────────────────────────────────────────────┘
┌─ OUTPUT ─────────────────────────────────────────────────┐
│                                                           │
│ AI responses and command output appear here              │
│                                                           │
│                                                           │
│                                                           │
│                                                           │
│                                                           │
└──────────────────────────────────────────────────────────┘
┌─ CMD ────────────────────────────────────────────────────┐
> Enter command...
└──────────────────────────────────────────────────────────┘
```

Total: 21 lines (fits perfectly in standard terminal output)
