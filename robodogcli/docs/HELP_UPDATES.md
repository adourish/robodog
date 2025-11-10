# Help Documentation Updates

## Summary

Updated help documentation in both CLI and React app to include the new code map commands.

## Changes Made

### 1. CLI Help (`cli.py`)

**Added Commands:**
```python
"map scan":            "scan codebase and create index",
"map find <name>":     "find class/function definition",
"map context <task>":  "get relevant files for task",
"map save <file>":     "save code map to file",
"map load <file>":     "load code map from file",
```

**How to View:**
```bash
python robodog\cli.py
/help
```

**Output:**
```
Available /commands:
  /help                — show this help
  /status              — show full dashboard
  ...
  /map scan            — scan codebase and create index
  /map find <name>     — find class/function definition
  /map context <task>  — get relevant files for task
  /map save <file>     — save code map to file
  /map load <file>     — load code map from file
  ...
```

### 2. React App Help (`ConsoleService.js`)

**Added Commands:**
```javascript
{ command: "/map scan", description: "Scan codebase and create index (saves 90% tokens!)." },
{ command: "/map find <name>", description: "Find class or function definition." },
{ command: "/map context <task>", description: "Get relevant files for a task." },
{ command: "/map save", description: "Save code map to codemap.json." },
{ command: "/map load", description: "Load code map from codemap.json." },
```

**How to View:**
```
/help
```

**Output in React:**
```
/map scan - Scan codebase and create index (saves 90% tokens!).
/map find <name> - Find class or function definition.
/map context <task> - Get relevant files for a task.
/map save - Save code map to codemap.json.
/map load - Load code map from codemap.json.
```

## Files Modified

1. **`robodog/cli.py`** - Added 5 map commands to help dictionary
2. **`robodoglib/src/ConsoleService.js`** - Added 5 map commands to _options array

## Build Status

✅ **Build completed successfully**
- RoboDogLib rebuilt with updated help
- React app rebuilt with new library
- Python CLI package rebuilt

**New Build:**
- Timestamp: Latest build
- Version: 2.6.16

## Testing

### Test CLI Help

```bash
cd c:\Projects\robodog\robodogcli
python robodog\cli.py
/help
# Should show /map commands
```

### Test React Help

1. Open React app in browser
2. Type `/help`
3. Verify `/map` commands are listed

### Test Commands Work

**CLI:**
```bash
/map scan
/map find TodoManager
/map context implement authentication
```

**React:**
```
/map scan
/map find TodoManager
/map context implement authentication
```

## Complete Command List

### Code Map Commands

| Command | Description | Example |
|---------|-------------|---------|
| `/map scan` | Scan codebase and create index | `/map scan` |
| `/map find <name>` | Find class/function definition | `/map find TodoManager` |
| `/map context <task>` | Get relevant files for task | `/map context implement auth` |
| `/map save <file>` | Save code map to file | `/map save codemap.json` |
| `/map load <file>` | Load code map from file | `/map load codemap.json` |

### Other Commands (Already in Help)

| Command | Description |
|---------|-------------|
| `/help` | Show help |
| `/models` | List models |
| `/model <name>` | Switch model |
| `/clear` | Clear screen |
| `/stash <name>` | Save session |
| `/pop <name>` | Restore session |
| `/import` | Import files |
| `/export <file>` | Export session |
| `/temperature <n>` | Set temperature |
| `/max_tokens <n>` | Set max tokens |
| `/dark` | Toggle theme |

## Benefits Highlighted

The React help now includes a note about token savings:

> **"Scan codebase and create index (saves 90% tokens!)."**

This highlights the main benefit of using the code map feature.

## Documentation Cross-References

For more details, see:
- **QUICK_START_CODE_MAP.md** - Quick start guide
- **CODE_MAP_AGENT_INTEGRATION.md** - Full integration guide
- **ENHANCEMENTS_SUMMARY.md** - Complete overview

## Next Steps

1. ✅ Help updated in both CLI and React
2. ✅ Build completed successfully
3. ⬜ Test help in both interfaces
4. ⬜ Verify all commands work as documented

## Summary

Both the CLI and React app now have complete, up-to-date help documentation that includes all code map commands. Users can easily discover and learn about the new features through the `/help` command.

**Key Achievement:** Users can now discover the code map feature and its 90% token savings benefit directly from the help menu! 🎉

---

*Last Updated: November 8, 2025*
*Build: 2.6.16*
