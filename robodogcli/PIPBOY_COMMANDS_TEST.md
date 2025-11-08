# Pip-Boy UI Commands Test Guide

## Branding Fixed
✅ Changed all "ROBOPUP" references to "ROBODOG"
- Header now shows "ROBODOG"
- Startup message: "ROBODOG SYSTEM ONLINE"
- Help text updated

## All Commands Output to UI

### Working Commands (Output to UI)

#### System Commands
- ✅ `/help` - Shows help text in OUTPUT panel
- ✅ `/quit` or `/exit` - Exits application cleanly
- ✅ `/clear` - Clears chat history and OUTPUT panel

#### Model & Configuration
- ✅ `/models` - Lists all models with current model highlighted in OUTPUT
- ✅ `/model <name>` - Switches model, updates header, shows success/error in STATUS
- ✅ `/key <provider> <key>` - Sets API key, shows success in STATUS
- ✅ `/getkey <provider>` - Shows API key in OUTPUT
- ✅ `/temperature <n>` - Sets temperature, shows success in STATUS
- ✅ `/top_p <n>` - Sets top_p, shows success in STATUS
- ✅ `/max_tokens <n>` - Sets max_tokens, shows success in STATUS
- ✅ `/frequency_penalty <n>` - Sets frequency penalty, shows success in STATUS
- ✅ `/presence_penalty <n>` - Sets presence penalty, shows success in STATUS
- ✅ `/stream` - Enables streaming, shows success in STATUS
- ✅ `/rest` - Disables streaming, shows success in STATUS

#### Task Management
- ✅ `/status` - Shows full dashboard in OUTPUT (captured from stdout)
- ✅ `/q` - Shows quick status in OUTPUT (captured from stdout)
- ✅ `/budget` - Shows token budget in OUTPUT (captured from stdout)
- ✅ `/shortcuts` - Shows keyboard shortcuts in OUTPUT (captured from stdout)
- ✅ `/todo` - Shows helpful message explaining it's not available in Pip-Boy mode

#### File & Knowledge
- ✅ `/import <glob>` - Imports files, shows count in STATUS
- ✅ `/export <file>` - Exports snapshot, shows success in STATUS
- ✅ `/folders <dirs>` - Sets MCP roots, shows list in OUTPUT
- ✅ `/include [spec] [prompt]` - Includes files and asks AI, shows response in OUTPUT

#### State Management
- ✅ `/stash <name>` - Stashes state, shows success in STATUS
- ✅ `/pop <name>` - Restores state, shows success in STATUS
- ✅ `/list` - Lists all stashes in OUTPUT

#### Advanced
- ✅ `/mcp <op> [json]` - Invokes MCP operation, shows result in OUTPUT (captured from pprint)
- ⚠️ `/curl <url>` - Shows "not yet implemented" message in OUTPUT
- ⚠️ `/play <instructions>` - Shows "not yet implemented" message in OUTPUT

#### Regular Messages
- ✅ Any text without `/` - Sent to AI, response shown in OUTPUT

### Error Handling

All commands now properly handle errors:
- Invalid arguments show WARNING in STATUS
- Missing required args show usage message
- Exceptions show full traceback in OUTPUT
- Unknown commands show helpful message in OUTPUT

### Output Locations

**STATUS Panel** (last 4 messages):
- Command execution status
- Success/warning/error messages
- Quick feedback

**OUTPUT Panel** (last 7 lines):
- Command results
- AI responses
- Help text
- Lists and data
- Error tracebacks

## Test Scenarios

### Test 1: Model Commands
```
/models
Expected: List of models with current model shown in OUTPUT

/model gpt-4
Expected: STATUS shows "Model changed: old → gpt-4", header updates

/model invalid
Expected: STATUS shows error, OUTPUT shows available models
```

### Test 2: Status Commands
```
/status
Expected: Full dashboard in OUTPUT

/q
Expected: Quick status in OUTPUT

/budget
Expected: Token budget display in OUTPUT
```

### Test 3: Configuration
```
/temperature 0.7
Expected: STATUS shows "temperature set to 0.7"

/stream
Expected: STATUS shows "Switched to streaming mode."
```

### Test 4: State Management
```
/stash test1
Expected: STATUS shows "Stashed under 'test1'."

/list
Expected: OUTPUT shows list of stashes

/pop test1
Expected: STATUS shows "Popped 'test1' into current session."
```

### Test 5: Error Handling
```
/model
Expected: STATUS warning, OUTPUT shows available models

/unknown
Expected: STATUS warning, OUTPUT shows help message

/temperature abc
Expected: STATUS error, OUTPUT shows traceback
```

### Test 6: AI Interaction
```
Hello, how are you?
Expected: STATUS shows "Asking AI: Hello, how are you?", OUTPUT shows AI response
```

## Verification Checklist

- [x] All "ROBOPUP" changed to "ROBODOG"
- [x] Header shows "ROBODOG"
- [x] All commands output to UI (STATUS or OUTPUT)
- [x] No commands print to console only
- [x] Error messages appear in UI
- [x] Success messages appear in STATUS
- [x] Command results appear in OUTPUT
- [x] Help text shows in OUTPUT
- [x] Unknown commands show helpful message
- [x] AI responses show in OUTPUT
- [x] Model changes update header immediately
