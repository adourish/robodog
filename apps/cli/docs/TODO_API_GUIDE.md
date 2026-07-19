# Todo Management API Guide

## Overview

RoboDog now has comprehensive todo.md management capabilities exposed through:
1. **CLI Commands** - `/todo` commands in the UI
2. **MCP API** - HTTP endpoints for React client
3. **Python Library** - `TodoManager` class

## CLI Commands

### List Tasks
```
/todo
```
Shows all tasks from all todo.md files with status and location.

### Add Task
```
/todo add <description>
```
Creates a new task in the first available todo.md (or creates one if none exist).

Examples:
- `/todo add Implement user authentication`
- `/todo add Fix bug in login form`
- `/todo add Add tests for API endpoints`

### Show Statistics
```
/todo stats
```
Displays statistics about tasks:
- Total count
- Count by status (To Do, Doing, Done, Ignore)
- Count by file
- Count by priority
- Count by tag

### List Todo Files
```
/todo files
```
Shows all todo.md files found in the project roots.

### Create Todo File
```
/todo create [path]
```
Creates a new todo.md file with a template.
- If no path specified, creates in first root directory
- Creates parent directories if needed

## MCP API Endpoints

All endpoints use POST with Bearer token authentication.

### TODO_LIST
List all tasks with optional filtering.

**Request:**
```json
{
  "path": "/path/to/todo.md",  // optional
  "status": " "                 // optional: ' ', '~', 'x', '-'
}
```

**Response:**
```json
{
  "status": "ok",
  "tasks": [
    {
      "file": "/path/to/todo.md",
      "line_number": 5,
      "status": "To Do",
      "status_char": " ",
      "description": "Implement feature",
      "full_description": "Implement feature !1 #backend",
      "priority": "1",
      "tags": ["backend"],
      "raw_line": "- [ ] Implement feature !1 #backend"
    }
  ]
}
```

### TODO_ADD
Add a new task.

**Request:**
```json
{
  "description": "Task description",
  "path": "/path/to/todo.md",  // optional
  "status": " ",                // optional: ' ', '~', 'x', '-'
  "priority": "1",              // optional
  "tags": ["tag1", "tag2"]      // optional
}
```

**Response:**
```json
{
  "status": "ok",
  "task": {
    "path": "/path/to/todo.md",
    "description": "Task description",
    "status": "To Do",
    "line": "- [ ] Task description !1 #tag1 #tag2",
    "line_number": 5
  }
}
```

### TODO_UPDATE
Update task status.

**Request:**
```json
{
  "path": "/path/to/todo.md",
  "line_number": 5,
  "new_status": "x"  // ' ', '~', 'x', '-'
}
```

**Response:**
```json
{
  "status": "ok",
  "task": {
    "path": "/path/to/todo.md",
    "line_number": 5,
    "status": "Done",
    "line": "- [x] Task description"
  }
}
```

### TODO_DELETE
Delete a task.

**Request:**
```json
{
  "path": "/path/to/todo.md",
  "line_number": 5
}
```

**Response:**
```json
{
  "status": "ok",
  "deleted": {
    "path": "/path/to/todo.md",
    "line_number": 5,
    "deleted_line": "- [ ] Task description"
  }
}
```

### TODO_STATS
Get todo statistics.

**Request:**
```json
{}
```

**Response:**
```json
{
  "status": "ok",
  "statistics": {
    "total": 25,
    "todo": 10,
    "doing": 5,
    "done": 8,
    "ignore": 2,
    "by_file": {
      "/path/to/todo.md": 15,
      "/path/to/other/todo.md": 10
    },
    "by_priority": {
      "1": 5,
      "2": 3
    },
    "by_tag": {
      "backend": 8,
      "frontend": 7
    }
  }
}
```

### TODO_FILES
Find all todo.md files.

**Request:**
```json
{}
```

**Response:**
```json
{
  "status": "ok",
  "files": [
    "/path/to/todo.md",
    "/path/to/other/todo.md"
  ]
}
```

### TODO_CREATE
Create a new todo.md file.

**Request:**
```json
{
  "path": "/path/to/new/todo.md"  // optional
}
```

**Response:**
```json
{
  "status": "ok",
  "path": "/path/to/new/todo.md"
}
```

## Python Library Usage

### Initialize TodoManager

```python
from robodog.todo_manager import TodoManager

# Initialize with project roots
todo_mgr = TodoManager(roots=["/path/to/project"])
```

### List Tasks

```python
# List all tasks
tasks = todo_mgr.list_tasks()

# List tasks from specific file
tasks = todo_mgr.list_tasks(path="/path/to/todo.md")

# Filter by status
todo_tasks = todo_mgr.list_tasks(status_filter=' ')  # To Do only
doing_tasks = todo_mgr.list_tasks(status_filter='~')  # Doing only
done_tasks = todo_mgr.list_tasks(status_filter='x')   # Done only
```

### Add Task

```python
# Simple task
result = todo_mgr.add_task("Implement feature")

# Task with priority and tags
result = todo_mgr.add_task(
    description="Fix critical bug",
    priority="1",
    tags=["urgent", "backend"]
)

# Task in specific file
result = todo_mgr.add_task(
    description="Add tests",
    path="/path/to/todo.md"
)
```

### Update Task Status

```python
# Mark task as doing
result = todo_mgr.update_task_status(
    path="/path/to/todo.md",
    line_number=5,
    new_status='~'
)

# Mark task as done
result = todo_mgr.update_task_status(
    path="/path/to/todo.md",
    line_number=5,
    new_status='x'
)
```

### Delete Task

```python
result = todo_mgr.delete_task(
    path="/path/to/todo.md",
    line_number=5
)
```

### Get Statistics

```python
stats = todo_mgr.get_statistics()
print(f"Total tasks: {stats['total']}")
print(f"To Do: {stats['todo']}")
print(f"Done: {stats['done']}")
```

### Find Todo Files

```python
files = todo_mgr.find_todo_files()
for file in files:
    print(f"Found: {file}")
```

### Create Todo File

```python
# Create in default location (first root)
path = todo_mgr.create_todo_file()

# Create at specific path
path = todo_mgr.create_todo_file("/path/to/new/todo.md")
```

## Task Format

### Basic Task
```markdown
- [ ] Task description
```

### Task with Priority
```markdown
- [ ] High priority task !1
- [ ] Medium priority task !2
- [ ] Low priority task !3
```

### Task with Tags
```markdown
- [ ] Backend task #backend #api
- [ ] Frontend task #frontend #ui
```

### Task with Both
```markdown
- [ ] Critical bug fix !1 #urgent #backend
```

### Task Statuses
- `- [ ]` - To Do
- `- [~]` - Doing (in progress)
- `- [x]` - Done (completed)
- `- [-]` - Ignore (skipped/cancelled)

## React Client Integration

### Example: List Tasks

```typescript
async function listTasks() {
  const response = await fetch('http://localhost:2500', {
    method: 'POST',
    headers: {
      'Authorization': 'Bearer your-token',
      'Content-Type': 'application/json'
    },
    body: JSON.stringify({
      op: 'TODO_LIST',
      payload: {}
    })
  });
  
  const data = await response.json();
  return data.tasks;
}
```

### Example: Add Task

```typescript
async function addTask(description: string, tags: string[] = []) {
  const response = await fetch('http://localhost:2500', {
    method: 'POST',
    headers: {
      'Authorization': 'Bearer your-token',
      'Content-Type': 'application/json'
    },
    body: JSON.stringify({
      op: 'TODO_ADD',
      payload: {
        description,
        tags,
        status: ' '
      }
    })
  });
  
  const data = await response.json();
  return data.task;
}
```

### Example: Update Task Status

```typescript
async function markTaskDone(path: string, lineNumber: number) {
  const response = await fetch('http://localhost:2500', {
    method: 'POST',
    headers: {
      'Authorization': 'Bearer your-token',
      'Content-Type': 'application/json'
    },
    body: JSON.stringify({
      op: 'TODO_UPDATE',
      payload: {
        path,
        line_number: lineNumber,
        new_status: 'x'
      }
    })
  });
  
  const data = await response.json();
  return data.task;
}
```

## Error Handling

All endpoints return errors in this format:

```json
{
  "status": "error",
  "error": "Error message description"
}
```

Common errors:
- `"Missing 'description'"` - Required field not provided
- `"Invalid status: <char>"` - Status character not in [' ', '~', 'x', '-']
- `"Invalid line number: <n>"` - Line number out of range
- `"Line <n> is not a valid task"` - Line doesn't match task format
- `"Access denied"` - Path not in allowed roots

## Best Practices

1. **Always check status** - Verify `status === "ok"` before using response data
2. **Handle missing files** - TODO_LIST returns empty array if no files found
3. **Use relative paths** - Store relative paths in your app for portability
4. **Cache statistics** - Stats can be expensive, cache and refresh periodically
5. **Validate input** - Check description length and format before sending
6. **Use tags consistently** - Establish tag conventions for your project
7. **Priority levels** - Use 1-3 for high/medium/low priority

## Complete Example: Todo Management Component

```typescript
class TodoManager {
  private baseUrl: string;
  private token: string;
  
  constructor(baseUrl: string, token: string) {
    this.baseUrl = baseUrl;
    this.token = token;
  }
  
  private async request(op: string, payload: any = {}) {
    const response = await fetch(this.baseUrl, {
      method: 'POST',
      headers: {
        'Authorization': `Bearer ${this.token}`,
        'Content-Type': 'application/json'
      },
      body: JSON.stringify({ op, payload })
    });
    
    const data = await response.json();
    if (data.status !== 'ok') {
      throw new Error(data.error);
    }
    return data;
  }
  
  async listTasks(statusFilter?: string) {
    const data = await this.request('TODO_LIST', { status: statusFilter });
    return data.tasks;
  }
  
  async addTask(description: string, options: {
    priority?: string,
    tags?: string[]
  } = {}) {
    const data = await this.request('TODO_ADD', {
      description,
      ...options
    });
    return data.task;
  }
  
  async updateStatus(path: string, lineNumber: number, newStatus: string) {
    const data = await this.request('TODO_UPDATE', {
      path,
      line_number: lineNumber,
      new_status: newStatus
    });
    return data.task;
  }
  
  async deleteTask(path: string, lineNumber: number) {
    const data = await this.request('TODO_DELETE', {
      path,
      line_number: lineNumber
    });
    return data.deleted;
  }
  
  async getStatistics() {
    const data = await this.request('TODO_STATS');
    return data.statistics;
  }
}
```

## Summary

The todo management system provides:
- ✅ Full CRUD operations on tasks
- ✅ Multiple todo.md file support
- ✅ Priority and tag support
- ✅ Statistics and reporting
- ✅ CLI, API, and library interfaces
- ✅ React client ready
- ✅ Thread-safe operations
- ✅ Comprehensive error handling

All features are now available in RoboDog CLI, MCP API, and as a Python library!
