# Testing Amplenote & Todoist in Robodog UI

## Quick Start

### 1. Start the MCP Server

Open a terminal and run:

```bash
cd c:\Projects\robodog\robodogcli
python robodog\cli.py --folders c:\projects\robodog\robodogcli --port 2500 --token testtoken --config config.yaml --model openai/o4-mini --log-level INFO
```

**Keep this terminal running!** This is your MCP server.

### 2. Open the Test UI

Open in your browser:
```
file:///C:/Projects/robodog/test_integrations_ui.html
```

This provides a simple interface to test all integration features.

### 3. Test the Features

The test UI includes:

#### Amplenote Tests:
- ✅ List all notes
- ✅ Create a new note
- ✅ Add content to a note
- ✅ Add a task to a note

#### Todoist Tests:
- ✅ List all projects
- ✅ List tasks (all or by project)
- ✅ Create a new task
- ✅ Complete a task
- ✅ List all labels

## Alternative: Test in Main Robodog UI

### Option A: Use Browser Console

1. Open the main UI:
   ```
   file:///C:/Projects/robodog/robodog/dist/index.html
   ```

2. Open Developer Console (F12)

3. Run test commands:

```javascript
// Test Amplenote
fetch('http://127.0.0.1:2500', {
  method: 'POST',
  headers: {
    'Content-Type': 'application/json',
    'Authorization': 'Bearer testtoken'
  },
  body: JSON.stringify({
    operation: 'AMPLENOTE_LIST',
    payload: {}
  })
})
.then(r => r.json())
.then(data => console.log(data));

// Test Todoist
fetch('http://127.0.0.1:2500', {
  method: 'POST',
  headers: {
    'Content-Type': 'application/json',
    'Authorization': 'Bearer testtoken'
  },
  body: JSON.stringify({
    operation: 'TODOIST_PROJECTS',
    payload: {}
  })
})
.then(r => r.json())
.then(data => console.log(data));
```

### Option B: Use CLI Commands

In the Robodog CLI terminal:

```bash
# Amplenote commands
/amplenote list
/amplenote create "Test Note"
/amplenote add <note_uuid> "Test content"

# Todoist commands
/todoist projects
/todoist tasks
/todoist create "Test task" p3
/todoist complete <task_id>
```

## MCP Operations Reference

### Amplenote Operations

| Operation | Description | Payload |
|-----------|-------------|---------|
| `AMPLENOTE_AUTH` | Authenticate | `{ redirect_uri }` |
| `AMPLENOTE_LIST` | List notes | `{ since }` (optional) |
| `AMPLENOTE_CREATE` | Create note | `{ name, tags }` |
| `AMPLENOTE_ADD` | Add content | `{ note_uuid, content, content_type }` |
| `AMPLENOTE_TASK` | Add task | `{ note_uuid, task_text, due, flags }` |
| `AMPLENOTE_LINK` | Add link | `{ note_uuid, url, link_text, description }` |
| `AMPLENOTE_UPLOAD` | Upload media | `{ note_uuid, file_path }` |

### Todoist Operations

| Operation | Description | Payload |
|-----------|-------------|---------|
| `TODOIST_AUTH` | Authenticate | `{ redirect_uri }` |
| `TODOIST_PROJECTS` | List projects | `{}` |
| `TODOIST_TASKS` | List tasks | `{ project_id, label, filter }` |
| `TODOIST_CREATE` | Create task | `{ content, description, project_id, due_string, priority, labels }` |
| `TODOIST_COMPLETE` | Complete task | `{ task_id }` |
| `TODOIST_PROJECT` | Create project | `{ name, color, is_favorite }` |
| `TODOIST_LABELS` | List labels | `{}` |
| `TODOIST_COMMENT` | Add comment | `{ task_id, content }` |

## Example Workflows

### Workflow 1: Create and Populate Amplenote

```javascript
// 1. Create a note
const createResult = await mcpCall('AMPLENOTE_CREATE', {
  name: 'Project Planning',
  tags: ['work', 'planning']
});
const noteUuid = createResult.note.uuid;

// 2. Add content
await mcpCall('AMPLENOTE_ADD', {
  note_uuid: noteUuid,
  content: '## Project Overview\n\nThis is a test project.'
});

// 3. Add a task
await mcpCall('AMPLENOTE_TASK', {
  note_uuid: noteUuid,
  task_text: 'Complete project documentation'
});

// 4. Add a link
await mcpCall('AMPLENOTE_LINK', {
  note_uuid: noteUuid,
  url: 'https://github.com/project',
  link_text: 'Project Repository'
});
```

### Workflow 2: Create Todoist Project with Tasks

```javascript
// 1. Create a project
const projectResult = await mcpCall('TODOIST_PROJECT', {
  name: 'Website Redesign',
  color: 'blue',
  is_favorite: true
});
const projectId = projectResult.project.id;

// 2. Create tasks
const tasks = [
  'Design mockups',
  'Implement frontend',
  'Set up backend',
  'Deploy to production'
];

for (const content of tasks) {
  await mcpCall('TODOIST_CREATE', {
    content: content,
    project_id: projectId,
    priority: 3
  });
}

// 3. List tasks
const tasksResult = await mcpCall('TODOIST_TASKS', {
  project_id: projectId
});
console.log('Created tasks:', tasksResult.tasks);
```

## Troubleshooting

### MCP Server Not Connecting

**Problem**: "Failed to fetch" or connection errors

**Solutions**:
1. Verify MCP server is running:
   ```bash
   # Check if process is running
   netstat -ano | findstr :2500
   ```

2. Restart the MCP server:
   ```bash
   cd c:\Projects\robodog\robodogcli
   python robodog\cli.py --folders c:\projects\robodog\robodogcli --port 2500 --token testtoken --config config.yaml
   ```

3. Check firewall settings (allow localhost:2500)

### Authentication Errors

**Problem**: "Not authenticated" errors

**Solutions**:

For Amplenote:
```bash
# In CLI
/amplenote auth
```

For Todoist:
```bash
# In CLI
/todoist auth
```

### CORS Errors

**Problem**: CORS policy blocking requests

**Solution**: The MCP handler already includes CORS headers. If still having issues:
1. Use the test UI (file:// protocol)
2. Or run a local web server:
   ```bash
   cd c:\Projects\robodog
   python -m http.server 8080
   # Then open: http://localhost:8080/test_integrations_ui.html
   ```

## Testing Checklist

- [ ] MCP server starts successfully
- [ ] Test UI loads without errors
- [ ] Connection status shows "Connected"
- [ ] HELP command returns all operations
- [ ] Amplenote LIST works (or shows auth required)
- [ ] Todoist PROJECTS works (or shows auth required)
- [ ] Can create Amplenote note
- [ ] Can add content to Amplenote note
- [ ] Can create Todoist task
- [ ] Can complete Todoist task
- [ ] All operations return proper JSON responses

## Next Steps

1. **Authenticate Services**: Run `/amplenote auth` and `/todoist auth` in CLI
2. **Test Full Workflows**: Use the test UI to create notes and tasks
3. **Integrate into Main UI**: Add buttons/forms to the main Robodog UI
4. **Build Custom Features**: Use MCP operations to build your own integrations

## Resources

- **Test UI**: `file:///C:/Projects/robodog/test_integrations_ui.html`
- **Main UI**: `file:///C:/Projects/robodog/robodog/dist/index.html`
- **Documentation**:
  - `docs/AMPLENOTE_INTEGRATION.md`
  - `docs/TODOIST_INTEGRATION.md`
  - `docs/QUICK_START_AMPLENOTE.md`
  - `docs/QUICK_START_TODOIST.md`

## Support

If you encounter issues:
1. Check `robodog.log` for errors
2. Verify API keys in `config.yaml`
3. Test authentication in CLI first
4. Use browser DevTools Console for debugging
