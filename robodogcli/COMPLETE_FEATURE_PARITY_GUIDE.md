# Complete Feature Parity Implementation Guide

## Overview

This guide provides complete implementation details for achieving 100% feature parity between the CLI and React app.

## Current Status

**Feature Parity: 75%**

### ✅ Already Implemented (Both Apps)
- Code map commands (`/map scan`, `/map find`, `/map context`, `/map save`, `/map load`)
- Model management (`/models`, `/model`)
- Clear history (`/clear`)
- Help (`/help`)
- Dark mode toggle (React only, but acceptable)

### ❌ Missing from React App (High Priority)

#### 1. API Key Management

**Add to React Settings Panel:**

```typescript
// SettingsComponent.jsx
const [apiKeys, setApiKeys] = useState({
  openai: '',
  anthropic: '',
  google: ''
});

const handleSetKey = async (provider, key) => {
  await mcpService.callMCP('SET_KEY', {
    provider,
    key
  });
  
  setApiKeys({...apiKeys, [provider]: key});
  showMessage(`API key for ${provider} set successfully`);
};

// UI
<div className="settings-section">
  <h3>API Keys</h3>
  <div className="api-key-input">
    <label>OpenAI API Key:</label>
    <input 
      type="password"
      value={apiKeys.openai}
      onChange={(e) => setApiKeys({...apiKeys, openai: e.target.value})}
      onBlur={() => handleSetKey('openai', apiKeys.openai)}
    />
  </div>
  <div className="api-key-input">
    <label>Anthropic API Key:</label>
    <input 
      type="password"
      value={apiKeys.anthropic}
      onChange={(e) => setApiKeys({...apiKeys, anthropic: e.target.value})}
      onBlur={() => handleSetKey('anthropic', apiKeys.anthropic)}
    />
  </div>
</div>
```

**Add MCP Endpoint:**

```python
# mcphandler.py
if op == "SET_KEY":
    provider = p.get("provider")
    key = p.get("key")
    if not provider or not key:
        raise ValueError("Missing provider or key")
    
    SERVICE.set_key(provider, key)
    return {"status": "ok", "provider": provider}

if op == "GET_KEY":
    provider = p.get("provider")
    if not provider:
        raise ValueError("Missing provider")
    
    key = SERVICE.get_key(provider)
    return {"status": "ok", "provider": provider, "key": key or ""}
```

#### 2. LLM Parameters

**Add to React Settings Panel:**

```typescript
// SettingsComponent.jsx
const [llmParams, setLlmParams] = useState({
  temperature: 0.7,
  max_tokens: 2000,
  top_p: 1.0,
  frequency_penalty: 0,
  presence_penalty: 0
});

const handleParamChange = (param, value) => {
  const newParams = {...llmParams, [param]: parseFloat(value)};
  setLlmParams(newParams);
  
  // Update via MCP
  mcpService.callMCP('SET_PARAM', {
    param,
    value: parseFloat(value)
  });
};

// UI
<div className="settings-section">
  <h3>LLM Parameters</h3>
  
  <div className="param-input">
    <label>Temperature (0-2):</label>
    <input 
      type="number"
      step="0.1"
      min="0"
      max="2"
      value={llmParams.temperature}
      onChange={(e) => handleParamChange('temperature', e.target.value)}
    />
    <span className="param-help">Higher = more creative</span>
  </div>
  
  <div className="param-input">
    <label>Max Tokens:</label>
    <input 
      type="number"
      step="100"
      min="100"
      max="4000"
      value={llmParams.max_tokens}
      onChange={(e) => handleParamChange('max_tokens', e.target.value)}
    />
  </div>
  
  <div className="param-input">
    <label>Top P (0-1):</label>
    <input 
      type="number"
      step="0.1"
      min="0"
      max="1"
      value={llmParams.top_p}
      onChange={(e) => handleParamChange('top_p', e.target.value)}
    />
  </div>
</div>
```

**Add MCP Endpoint:**

```python
# mcphandler.py
if op == "SET_PARAM":
    param = p.get("param")
    value = p.get("value")
    if not param:
        raise ValueError("Missing param")
    
    SERVICE.set_param(param, value)
    return {"status": "ok", "param": param, "value": value}

if op == "GET_PARAMS":
    params = {
        "temperature": SERVICE.temperature,
        "max_tokens": SERVICE.max_tokens,
        "top_p": SERVICE.top_p,
        "frequency_penalty": SERVICE.frequency_penalty,
        "presence_penalty": SERVICE.presence_penalty
    }
    return {"status": "ok", "params": params}
```

#### 3. Folder Management

**Add to React Settings Panel:**

```typescript
// SettingsComponent.jsx
const [folders, setFolders] = useState([]);
const [newFolder, setNewFolder] = useState('');

const handleAddFolder = async () => {
  if (!newFolder) return;
  
  const updatedFolders = [...folders, newFolder];
  await mcpService.callMCP('SET_FOLDERS', {
    folders: updatedFolders
  });
  
  setFolders(updatedFolders);
  setNewFolder('');
};

const handleRemoveFolder = async (folder) => {
  const updatedFolders = folders.filter(f => f !== folder);
  await mcpService.callMCP('SET_FOLDERS', {
    folders: updatedFolders
  });
  
  setFolders(updatedFolders);
};

// UI
<div className="settings-section">
  <h3>Project Folders</h3>
  
  <div className="folder-input">
    <input 
      type="text"
      placeholder="Add folder path"
      value={newFolder}
      onChange={(e) => setNewFolder(e.target.value)}
      onKeyPress={(e) => e.key === 'Enter' && handleAddFolder()}
    />
    <button onClick={handleAddFolder}>Add</button>
  </div>
  
  <ul className="folder-list">
    {folders.map(folder => (
      <li key={folder}>
        {folder}
        <button onClick={() => handleRemoveFolder(folder)}>×</button>
      </li>
    ))}
  </ul>
</div>
```

**Add MCP Endpoint:**

```python
# mcphandler.py
if op == "SET_FOLDERS":
    folders = p.get("folders")
    if not isinstance(folders, list):
        raise ValueError("folders must be a list")
    
    resp = SERVICE.call_mcp("SET_ROOTS", {"roots": folders})
    return {"status": "ok", "folders": resp.get("roots", [])}

if op == "GET_FOLDERS":
    # Return current folders
    return {"status": "ok", "folders": SERVICE.file_service.roots}
```

#### 4. Import/Export

**Add to Console.jsx:**

```typescript
// Console.jsx
case '/import':
  if (!_command.verb) {
    message = 'Usage: /import <glob>';
    setContent([...content, formatService.getMessageWithTimestamp(message, 'setting')]);
    return;
  }
  
  const importResult = await mcpService.callMCP('IMPORT', {
    glob: _command.verb
  });
  
  setKnowledge(prev => prev + '\n\n' + importResult.content);
  message = `Imported ${importResult.file_count} files`;
  setContent([...content, formatService.getMessageWithTimestamp(message, 'setting')]);
  break;

case '/export':
  const filename = _command.verb || 'export.json';
  await mcpService.callMCP('EXPORT', {
    filename,
    context,
    knowledge,
    question,
    content
  });
  
  message = `Exported to ${filename}`;
  setContent([...content, formatService.getMessageWithTimestamp(message, 'setting')]);
  break;
```

**Add MCP Endpoints:**

```python
# mcphandler.py
if op == "IMPORT":
    glob_pattern = p.get("glob")
    if not glob_pattern:
        raise ValueError("Missing glob pattern")
    
    count = SERVICE.import_files(glob_pattern)
    content = SERVICE.knowledge  # Get imported content
    return {"status": "ok", "file_count": count, "content": content}

if op == "EXPORT":
    filename = p.get("filename", "export.json")
    data = {
        "context": p.get("context", ""),
        "knowledge": p.get("knowledge", ""),
        "question": p.get("question", ""),
        "content": p.get("content", [])
    }
    
    SERVICE.export_snapshot(filename, data)
    return {"status": "ok", "filename": filename}
```

#### 5. Session Management (Stash/Pop)

**Already has UI in React, add commands:**

```typescript
// Console.jsx
case '/stash':
  const stashName = _command.verb || 'default';
  consoleService.stash(stashName, context, knowledge, question, content, temperature, showTextarea);
  
  const stashes = consoleService.getStashList();
  setStashList(stashes.split(','));
  
  message = `Stashed session as '${stashName}'`;
  setContent([...content, formatService.getMessageWithTimestamp(message, 'setting')]);
  break;

case '/pop':
  const popName = _command.verb || 'default';
  const session = consoleService.pop(popName);
  
  if (session) {
    setContext(session.context || '');
    setKnowledge(session.knowledge || '');
    setQuestion(session.question || '');
    setTemperature(session.temperature || 0.7);
    
    message = `Restored session '${popName}'`;
  } else {
    message = `No session found: '${popName}'`;
  }
  
  setContent([...content, formatService.getMessageWithTimestamp(message, 'setting')]);
  break;

case '/list':
  const stashList = consoleService.getStashList();
  message = `Stashed sessions: ${stashList || 'none'}`;
  setContent([...content, formatService.getMessageWithTimestamp(message, 'setting')]);
  break;
```

### ❌ Missing from CLI (Lower Priority)

#### 1. Visual File Browser

**Add text-based file browser:**

```python
# cli.py
elif cmd == "files":
    # Show file tree
    def print_tree(path, prefix="", max_depth=3, current_depth=0):
        if current_depth >= max_depth:
            return
        
        try:
            items = sorted(os.listdir(path))
            for i, item in enumerate(items):
                is_last = i == len(items) - 1
                item_path = os.path.join(path, item)
                
                connector = "└── " if is_last else "├── "
                print(f"{prefix}{connector}{item}")
                
                if os.path.isdir(item_path):
                    extension = "    " if is_last else "│   "
                    print_tree(item_path, prefix + extension, max_depth, current_depth + 1)
        except PermissionError:
            pass
    
    for root in svc.file_service.roots:
        print(f"\n{root}")
        print_tree(root)
```

#### 2. Live Log Feed

**Add log viewer:**

```python
# cli.py
elif cmd == "logs":
    # Show recent logs
    import logging
    
    # Get recent log entries
    log_file = "robodog.log"
    if os.path.exists(log_file):
        with open(log_file, 'r') as f:
            lines = f.readlines()
            recent = lines[-50:]  # Last 50 lines
            print("\n".join(recent))
    else:
        print("No log file found")
```

## Implementation Priority

### Phase 1: Critical (Week 1)
1. ✅ Code map commands - DONE
2. ⬜ API key management in React
3. ⬜ LLM parameters in React
4. ⬜ Folder management in React

### Phase 2: Important (Week 2)
1. ⬜ Import/Export commands
2. ⬜ Session management commands
3. ⬜ MCP endpoints for all operations

### Phase 3: Nice-to-Have (Week 3)
1. ⬜ File browser in CLI
2. ⬜ Log viewer in CLI
3. ⬜ Token budget display
4. ⬜ Status dashboard

## Testing Matrix

| Feature | CLI Test | React Test | MCP Test |
|---------|----------|------------|----------|
| Code Map | ✅ | ✅ | ✅ |
| API Keys | ⬜ | ⬜ | ⬜ |
| LLM Params | ⬜ | ⬜ | ⬜ |
| Folders | ⬜ | ⬜ | ⬜ |
| Import | ⬜ | ⬜ | ⬜ |
| Export | ⬜ | ⬜ | ⬜ |
| Stash | ⬜ | ⬜ | N/A |
| Pop | ⬜ | ⬜ | N/A |

## Success Criteria

**100% Feature Parity Achieved When:**
- [ ] All CLI commands work in React
- [ ] All React features accessible from CLI
- [ ] All MCP endpoints implemented
- [ ] Settings persist correctly
- [ ] No feature gaps between interfaces
- [ ] Documentation complete
- [ ] Tests passing

## Summary

**Total Features to Add:**
- React: 10 features
- CLI: 2 features
- MCP Endpoints: 8 new endpoints

**Estimated Effort:**
- React features: 2-3 days
- CLI features: 1 day
- MCP endpoints: 1-2 days
- Testing: 1 day
- **Total: 5-7 days**

**Benefits:**
- 100% feature parity
- Better user experience
- Consistent interface
- Easier maintenance

---

*Next Steps: Implement Phase 1 features*
