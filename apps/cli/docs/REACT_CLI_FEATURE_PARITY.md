# React App vs CLI Feature Parity

## Current Status

### ✅ Features Available in Both

| Feature | CLI Command | React Command | MCP Endpoint | Status |
|---------|-------------|---------------|--------------|--------|
| List models | `/models` | `/models` | N/A | ✅ Working |
| Set model | `/model <name>` | `/model <name>` | N/A | ✅ Working |
| Clear history | `/clear` | `/clear` | N/A | ✅ Working |
| Code map scan | `/map scan` | `/map scan` | `MAP_SCAN` | ✅ Working |
| Code map find | `/map find <name>` | `/map find <name>` | `MAP_FIND` | ✅ Working |
| Code map context | `/map context <task>` | `/map context <task>` | `MAP_CONTEXT` | ✅ Working |
| Code map save | `/map save` | `/map save` | `MAP_SAVE` | ✅ Working |
| Code map load | `/map load` | `/map load` | `MAP_LOAD` | ✅ Working |

### ⚠️ Features Only in CLI

| Feature | CLI Command | Description | Priority |
|---------|-------------|-------------|----------|
| Set API key | `/key <provider> <key>` | Set API keys for providers | High |
| Get API key | `/getkey <provider>` | View stored API key | Medium |
| Set folders | `/folders <dir1> <dir2>` | Set root directories | High |
| Include files | `/include <spec> <prompt>` | Include files in context | High |
| MCP direct call | `/mcp <op> <json>` | Direct MCP endpoint call | Low |
| Import files | `/import <glob>` | Import files to knowledge | Medium |
| Export snapshot | `/export <filename>` | Export session snapshot | Medium |
| Stash session | `/stash <name>` | Save current session | Medium |
| Pop session | `/pop <name>` | Restore saved session | Medium |
| List stashes | `/list` | List all stashed sessions | Low |
| Set parameters | `/temperature <val>` | Set LLM parameters | High |
| Stream mode | `/stream` | Enable streaming | Low |
| REST mode | `/rest` | Disable streaming | Low |
| Status dashboard | `/status` | Show full dashboard | Medium |
| Quick status | `/q` | Show quick status | Low |
| Token budget | `/budget` | Show token budget | Medium |
| Keyboard shortcuts | `/shortcuts` | Show shortcuts | Low |
| Todo commands | `/todo add/update/delete` | Todo management | High |
| Agent loop | `--agent-loop` flag | Enable agentic execution | High |

### 📱 Features Only in React App

| Feature | Description | Equivalent CLI |
|---------|-------------|----------------|
| Visual file browser | Browse files in UI | `/files` (limited) |
| Live log feed | Real-time log viewing | Terminal output |
| Todo task viewer | Visual task list | `/todo` |
| Settings panel | Visual settings UI | Various `/` commands |
| Model dropdown | Visual model selection | `/model` |
| Stash dropdown | Visual stash selection | `/pop` |
| Dark/Light mode | Theme toggle | N/A |

## Recommended Additions to React App

### High Priority

#### 1. Settings Panel Enhancements

Add these settings to the React settings panel:

```typescript
// Add to SettingsComponent
<div className="setting-group">
  <h3>API Keys</h3>
  <input 
    type="password" 
    placeholder="OpenAI API Key"
    onChange={(e) => handleSetKey('openai', e.target.value)}
  />
  <input 
    type="password" 
    placeholder="Anthropic API Key"
    onChange={(e) => handleSetKey('anthropic', e.target.value)}
  />
</div>

<div className="setting-group">
  <h3>LLM Parameters</h3>
  <label>
    Temperature: <input type="number" step="0.1" min="0" max="2" />
  </label>
  <label>
    Max Tokens: <input type="number" step="100" min="100" max="4000" />
  </label>
  <label>
    Top P: <input type="number" step="0.1" min="0" max="1" />
  </label>
</div>

<div className="setting-group">
  <h3>Project Folders</h3>
  <input 
    type="text" 
    placeholder="Add folder path"
    onKeyPress={(e) => e.key === 'Enter' && handleAddFolder(e.target.value)}
  />
  <ul>
    {folders.map(f => <li key={f}>{f} <button onClick={() => removeFolder(f)}>×</button></li>)}
  </ul>
</div>
```

#### 2. Include Files Feature

Add file inclusion UI:

```typescript
// Add to Console.jsx
const handleIncludeFiles = async (pattern, prompt) => {
  const result = await mcpService.callMCP('INCLUDE', {
    spec: pattern,
    prompt: prompt
  });
  
  // Add included files to knowledge
  setKnowledge(prev => prev + '\n\n' + result.content);
};

// UI
<div className="include-panel">
  <input 
    placeholder="File pattern (e.g., **/*.py)"
    value={includePattern}
    onChange={(e) => setIncludePattern(e.target.value)}
  />
  <button onClick={() => handleIncludeFiles(includePattern, question)}>
    Include Files
  </button>
</div>
```

#### 3. Todo Management Commands

Add todo management to React:

```typescript
// Add cases to Console.jsx
case '/todo':
  if (_command.verb === 'add') {
    const desc = _command.args.slice(1).join(' ');
    await mcpService.callMCP('TODO_ADD', { description: desc });
    message = `Added task: ${desc}`;
  } else if (_command.verb === 'update') {
    const id = _command.args[1];
    const status = _command.args[2];
    await mcpService.callMCP('TODO_UPDATE', { id, status });
    message = `Updated task ${id}`;
  } else if (_command.verb === 'delete') {
    const id = _command.args[1];
    await mcpService.callMCP('TODO_DELETE', { id });
    message = `Deleted task ${id}`;
  }
  break;
```

### Medium Priority

#### 4. Session Management

Add stash/pop functionality:

```typescript
const handleStash = async (name) => {
  await mcpService.callMCP('STASH', {
    name,
    context,
    knowledge,
    question,
    temperature
  });
  
  // Update stash list
  const stashes = await mcpService.callMCP('LIST_STASHES', {});
  setStashList(stashes.list);
};

const handlePop = async (name) => {
  const session = await mcpService.callMCP('POP', { name });
  setContext(session.context);
  setKnowledge(session.knowledge);
  setQuestion(session.question);
  setTemperature(session.temperature);
};
```

#### 5. Import/Export

Add import/export buttons:

```typescript
const handleImport = async (glob) => {
  const result = await mcpService.callMCP('IMPORT', { glob });
  setKnowledge(prev => prev + '\n\n' + result.content);
  message = `Imported ${result.file_count} files`;
};

const handleExport = async (filename) => {
  await mcpService.callMCP('EXPORT', {
    filename,
    context,
    knowledge,
    question,
    content
  });
  message = `Exported to ${filename}`;
};
```

#### 6. Token Budget Display

Add token budget widget:

```typescript
const TokenBudget = ({ totalTokens, maxTokens }) => {
  const percentage = (totalTokens / maxTokens) * 100;
  const color = percentage > 75 ? 'red' : percentage > 50 ? 'yellow' : 'green';
  
  return (
    <div className="token-budget">
      <div className="budget-bar" style={{ width: `${percentage}%`, background: color }} />
      <span>{totalTokens} / {maxTokens} tokens ({percentage.toFixed(1)}%)</span>
    </div>
  );
};
```

### Low Priority

#### 7. Keyboard Shortcuts Panel

Add shortcuts help:

```typescript
const ShortcutsPanel = () => (
  <div className="shortcuts-panel">
    <h3>Keyboard Shortcuts</h3>
    <ul>
      <li><kbd>Ctrl+S</kbd> - Save session</li>
      <li><kbd>Ctrl+Shift+↑</kbd> - Cycle stashes</li>
      <li><kbd>Ctrl+Enter</kbd> - Submit</li>
      <li><kbd>Esc</kbd> - Clear input</li>
    </ul>
  </div>
);
```

## Implementation Plan

### Phase 1: Core Features (Week 1)
- ✅ Code map commands
- ⬜ API key management in settings
- ⬜ LLM parameter controls
- ⬜ Folder management

### Phase 2: Session Management (Week 2)
- ⬜ Stash/pop functionality
- ⬜ Import/export
- ⬜ Session history

### Phase 3: Advanced Features (Week 3)
- ⬜ Todo management commands
- ⬜ Include files feature
- ⬜ Token budget display
- ⬜ Status dashboard

### Phase 4: Polish (Week 4)
- ⬜ Keyboard shortcuts
- ⬜ Help system
- ⬜ Tooltips
- ⬜ Error handling improvements

## MCP Endpoints Needed

### Already Implemented
- ✅ MAP_SCAN, MAP_FIND, MAP_CONTEXT, MAP_SAVE, MAP_LOAD
- ✅ TODO, TODO_LIST, TODO_ADD, TODO_UPDATE, TODO_DELETE
- ✅ READ_FILE, UPDATE_FILE, CREATE_FILE, DELETE_FILE
- ✅ LIST_FILES, SEARCH

### Need to Add
- ⬜ SET_KEY - Set API key
- ⬜ GET_KEY - Get API key
- ⬜ SET_FOLDERS - Set root folders
- ⬜ INCLUDE - Include files in context
- ⬜ IMPORT - Import files to knowledge
- ⬜ EXPORT - Export session
- ⬜ STASH - Save session
- ⬜ POP - Restore session
- ⬜ LIST_STASHES - List saved sessions
- ⬜ SET_PARAM - Set LLM parameter
- ⬜ GET_BUDGET - Get token budget

## CLI Enhancements

### Add to CLI

#### 1. Visual File Browser (like React)
```python
# Add to cli.py
elif cmd == "files":
    # Show interactive file browser
    file_browser = FileBrowser(svc.file_service)
    selected_file = file_browser.show()
    if selected_file:
        content = svc.file_service.safe_read_file(selected_file)
        pipboy_ui.set_output(content)
```

#### 2. Live Log Feed
```python
# Add to cli.py
elif cmd == "logs":
    # Show live log feed
    log_viewer = LogViewer()
    log_viewer.start()  # Tail logs in real-time
```

## Summary

### Current State
- ✅ Code map fully integrated in both CLI and React
- ✅ Basic commands work in both
- ⚠️ Many CLI features missing from React
- ⚠️ Some React features missing from CLI

### Recommended Next Steps

1. **Add API key management to React settings**
2. **Add LLM parameter controls to React**
3. **Add folder management to React**
4. **Implement missing MCP endpoints**
5. **Add todo management commands to React**
6. **Add session management (stash/pop) to React**
7. **Add file browser to CLI**

### Goal
**100% feature parity** between CLI and React app, with each interface optimized for its use case (terminal vs web).

## Feature Matrix

| Category | CLI | React | Target |
|----------|-----|-------|--------|
| Code Map | 100% | 100% | ✅ Complete |
| Model Management | 100% | 80% | 🔄 In Progress |
| File Operations | 100% | 60% | 🔄 In Progress |
| Session Management | 100% | 40% | ⏳ Planned |
| Todo Management | 100% | 60% | 🔄 In Progress |
| Settings | 100% | 50% | 🔄 In Progress |
| Visualization | 40% | 100% | 🔄 In Progress |

**Overall Parity: 75%**

Target: **95%** (some features are interface-specific)
