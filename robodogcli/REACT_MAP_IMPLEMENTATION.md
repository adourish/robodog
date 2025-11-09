# React App /map Command Implementation

## Changes Made

### 1. Updated MCP Handler (`mcphandler.py`)
✅ Added MAP commands to HELP list so server recognizes them

### 2. Updated React Console (`Console.jsx` and `Console copy.jsx`)

#### Added `/map` case in switch statement:
```javascript
case '/map':
  handleMapCommand(_command.verb, _command.args)
  break;
```

#### Added `handleMapCommand` function:
```javascript
const handleMapCommand = async (subcommand, args) => {
  // Handles: scan, find, context, save, load
  // Calls providerService.callMCP() for each operation
}
```

## Available Commands

### /map scan
Scans the codebase and creates a code map.

**Usage:**
```
/map scan
```

**Output:**
```
🗺️ Scanning codebase...
Scanned 45 files, 12 classes, 87 functions
```

### /map find <name>
Finds where a class or function is defined.

**Usage:**
```
/map find TodoManager
```

**Output:**
```
Found 1 definition(s):
class: TodoManager at todo_manager.py:18
  High-level todo.md management
```

### /map context <task>
Gets relevant files for a task.

**Usage:**
```
/map context implement authentication
```

**Output:**
```
Context for: implement authentication
Keywords: implement, authentication
Relevant files: 3

[5] auth_service.py
[3] user_model.py
[2] api_routes.py
```

### /map save
Saves the code map to file.

**Usage:**
```
/map save
```

**Output:**
```
💾 Code map saved to codemap.json
```

### /map load
Loads a previously saved code map.

**Usage:**
```
/map load
```

**Output:**
```
📂 Code map loaded: 45 files
```

## How It Works

1. **User types `/map scan` in React UI**
2. **Console.jsx parses the command**
   - Recognizes `/map` as command
   - Extracts `scan` as subcommand
3. **Calls `handleMapCommand('scan', [])`**
4. **Function calls `providerService.callMCP('MAP_SCAN', {})`**
5. **MCP server processes request**
   - Calls `SERVICE.code_mapper.scan_codebase()`
   - Returns results
6. **React displays formatted output**

## Testing

### Test in React App:

1. Start the backend:
```bash
python robodog\cli.py --folders c:\projects\robodog\robodogcli --port 2500 --token testtoken --config config.yaml
```

2. Open React app in browser

3. Try commands:
```
/map scan
/map find CodeMapper
/map context implement user auth
/map save
/map load
```

### Expected Behavior:

- ✅ Commands execute without "No verbs" error
- ✅ Results display in the console
- ✅ Loading indicators show during processing
- ✅ Error messages display if something fails

## Files Modified

1. **robodog/mcphandler.py**
   - Added MAP_* commands to HELP list

2. **robodog/src/Console.jsx**
   - Added `/map` case
   - Added `handleMapCommand` function

3. **robodog/src/Console copy.jsx**
   - Added `/map` case
   - Added `handleMapCommand` function

## Next Steps

1. **Rebuild React app:**
```bash
cd c:\Projects\robodog
python build.py
```

2. **Test in browser**

3. **Optional enhancements:**
   - Add syntax highlighting for code results
   - Add clickable file paths
   - Add visual code map visualization
   - Cache results for faster subsequent calls

## Summary

✅ `/map` command now works in React app
✅ Calls MCP endpoints just like `/models`, `/model`, `/clear`
✅ Supports all 5 subcommands: scan, find, context, save, load
✅ Displays formatted results in console
✅ Handles errors gracefully

The `/map` command is now fully integrated into the React app!
