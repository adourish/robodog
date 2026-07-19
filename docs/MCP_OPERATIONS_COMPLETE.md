# Robodog MCP Operations - Complete Reference

## Overview

The Robodog MCP (Multi-Client Protocol) handler provides a comprehensive API for file operations, task management, and integration with Google services, Todoist, and Amplenote.

**Total Operations: 50+**

---

## Table of Contents

1. [File System Operations](#file-system-operations)
2. [TODO Operations](#todo-operations)
3. [Google API Operations](#google-api-operations)
4. [Todoist Operations](#todoist-operations)
5. [Amplenote Operations](#amplenote-operations)
6. [System Operations](#system-operations)

---

## File System Operations

### READ_FILE
Read file contents.

**Request:**
```json
{
  "operation": "READ_FILE",
  "payload": {
    "path": "/path/to/file.txt"
  }
}
```

**Response:**
```json
{
  "status": "ok",
  "content": "file contents here"
}
```

### WRITE_FILE
Write content to a file.

**Request:**
```json
{
  "operation": "WRITE_FILE",
  "payload": {
    "path": "/path/to/file.txt",
    "content": "new content"
  }
}
```

### APPEND_FILE
Append content to a file.

**Request:**
```json
{
  "operation": "APPEND_FILE",
  "payload": {
    "path": "/path/to/file.txt",
    "content": "appended content"
  }
}
```

### DELETE_FILE
Delete a file.

**Request:**
```json
{
  "operation": "DELETE_FILE",
  "payload": {
    "path": "/path/to/file.txt"
  }
}
```

### COPY_FILE
Copy a file.

**Request:**
```json
{
  "operation": "COPY_FILE",
  "payload": {
    "source": "/path/to/source.txt",
    "destination": "/path/to/dest.txt"
  }
}
```

### RENAME
Rename/move a file or directory.

**Request:**
```json
{
  "operation": "RENAME",
  "payload": {
    "old_path": "/path/to/old.txt",
    "new_path": "/path/to/new.txt"
  }
}
```

### CREATE_DIR
Create a directory.

**Request:**
```json
{
  "operation": "CREATE_DIR",
  "payload": {
    "path": "/path/to/new/directory"
  }
}
```

### DELETE_DIR
Delete a directory.

**Request:**
```json
{
  "operation": "DELETE_DIR",
  "payload": {
    "path": "/path/to/directory"
  }
}
```

### LIST_DIR
List directory contents.

**Request:**
```json
{
  "operation": "LIST_DIR",
  "payload": {
    "path": "/path/to/directory"
  }
}
```

### SEARCH
Search for files matching a pattern.

**Request:**
```json
{
  "operation": "SEARCH",
  "payload": {
    "pattern": "*.py",
    "path": "/path/to/search"
  }
}
```

### CHECKSUM
Calculate file checksum.

**Request:**
```json
{
  "operation": "CHECKSUM",
  "payload": {
    "path": "/path/to/file.txt"
  }
}
```

---

## TODO Operations

### TODO_LIST
List all TODO tasks.

**Request:**
```json
{
  "operation": "TODO_LIST",
  "payload": {}
}
```

**Response:**
```json
{
  "status": "ok",
  "tasks": [
    {
      "id": "1",
      "title": "Task 1",
      "completed": false,
      "file": "/path/to/file.py",
      "line": 42
    }
  ]
}
```

### TODO_ADD
Add a new TODO task.

**Request:**
```json
{
  "operation": "TODO_ADD",
  "payload": {
    "title": "New task",
    "file": "/path/to/file.py",
    "line": 42
  }
}
```

### TODO_COMPLETE
Mark a TODO task as complete.

**Request:**
```json
{
  "operation": "TODO_COMPLETE",
  "payload": {
    "id": "task-id"
  }
}
```

### TODO_DELETE
Delete a TODO task.

**Request:**
```json
{
  "operation": "TODO_DELETE",
  "payload": {
    "id": "task-id"
  }
}
```

---

## Google API Operations

### Authentication

#### GOOGLE_AUTH
Authenticate with Google OAuth2.

**Request:**
```json
{
  "operation": "GOOGLE_AUTH",
  "payload": {
    "code": "authorization-code"
  }
}
```

#### GOOGLE_SET_TOKEN
Set Google access token manually.

**Request:**
```json
{
  "operation": "GOOGLE_SET_TOKEN",
  "payload": {
    "token": "access-token",
    "refresh_token": "refresh-token"
  }
}
```

#### GOOGLE_STATUS
Check Google authentication status.

**Request:**
```json
{
  "operation": "GOOGLE_STATUS",
  "payload": {}
}
```

**Response:**
```json
{
  "status": "ok",
  "authenticated": true,
  "available": true
}
```

---

### Google Docs Operations

#### GDOC_CREATE
Create a new Google Doc.

**Request:**
```json
{
  "operation": "GDOC_CREATE",
  "payload": {
    "title": "My Document",
    "content": "Initial content"
  }
}
```

**Response:**
```json
{
  "status": "ok",
  "document": {
    "documentId": "abc123",
    "title": "My Document"
  }
}
```

#### GDOC_GET
Get a Google Doc.

**Request:**
```json
{
  "operation": "GDOC_GET",
  "payload": {
    "document_id": "abc123"
  }
}
```

#### GDOC_UPDATE
Update a Google Doc.

**Request:**
```json
{
  "operation": "GDOC_UPDATE",
  "payload": {
    "document_id": "abc123",
    "content": "New content",
    "insert_index": 1
  }
}
```

#### GDOC_DELETE
Delete a Google Doc.

**Request:**
```json
{
  "operation": "GDOC_DELETE",
  "payload": {
    "document_id": "abc123"
  }
}
```

#### GDOC_READ
Read text from a Google Doc.

**Request:**
```json
{
  "operation": "GDOC_READ",
  "payload": {
    "document_id": "abc123"
  }
}
```

---

### Gmail Operations

#### GMAIL_SEND
Send an email.

**Request:**
```json
{
  "operation": "GMAIL_SEND",
  "payload": {
    "to": "user@example.com",
    "subject": "Hello",
    "body": "Email body",
    "is_html": false,
    "cc": "cc@example.com",
    "bcc": "bcc@example.com"
  }
}
```

#### GMAIL_LIST
List emails.

**Request:**
```json
{
  "operation": "GMAIL_LIST",
  "payload": {
    "max_results": 10,
    "query": "is:unread"
  }
}
```

#### GMAIL_GET
Get a specific email.

**Request:**
```json
{
  "operation": "GMAIL_GET",
  "payload": {
    "message_id": "msg123"
  }
}
```

#### GMAIL_CREATE_DRAFT
Create an email draft.

**Request:**
```json
{
  "operation": "GMAIL_CREATE_DRAFT",
  "payload": {
    "to": "user@example.com",
    "subject": "Draft",
    "body": "Draft body"
  }
}
```

#### GMAIL_DELETE_DRAFT
Delete an email draft.

**Request:**
```json
{
  "operation": "GMAIL_DELETE_DRAFT",
  "payload": {
    "draft_id": "draft123"
  }
}
```

---

### Google Calendar Operations

#### GCAL_LIST
List all calendars.

**Request:**
```json
{
  "operation": "GCAL_LIST",
  "payload": {}
}
```

**Response:**
```json
{
  "status": "ok",
  "calendars": {
    "items": [
      {
        "id": "cal123",
        "summary": "My Calendar",
        "description": "Calendar description"
      }
    ]
  }
}
```

#### GCAL_CREATE
Create a new calendar.

**Request:**
```json
{
  "operation": "GCAL_CREATE",
  "payload": {
    "summary": "Work Calendar",
    "description": "My work schedule",
    "timezone": "America/New_York"
  }
}
```

#### GCAL_GET
Get calendar details.

**Request:**
```json
{
  "operation": "GCAL_GET",
  "payload": {
    "calendar_id": "cal123"
  }
}
```

#### GCAL_UPDATE
Update a calendar.

**Request:**
```json
{
  "operation": "GCAL_UPDATE",
  "payload": {
    "calendar_id": "cal123",
    "summary": "Updated Name",
    "description": "Updated description"
  }
}
```

#### GCAL_DELETE
Delete a calendar.

**Request:**
```json
{
  "operation": "GCAL_DELETE",
  "payload": {
    "calendar_id": "cal123"
  }
}
```

#### GCAL_SEARCH
Search calendars (wildcard).

**Request:**
```json
{
  "operation": "GCAL_SEARCH",
  "payload": {
    "query": "work"
  }
}
```

---

### Calendar Event Operations

#### GEVENT_LIST
List events from a calendar.

**Request:**
```json
{
  "operation": "GEVENT_LIST",
  "payload": {
    "calendar_id": "primary",
    "max_results": 10,
    "time_min": "2025-11-17T00:00:00Z",
    "time_max": "2025-11-18T00:00:00Z",
    "query": "meeting"
  }
}
```

#### GEVENT_CREATE
Create a calendar event.

**Request:**
```json
{
  "operation": "GEVENT_CREATE",
  "payload": {
    "calendar_id": "primary",
    "summary": "Team Meeting",
    "description": "Weekly sync",
    "start_time": "2025-11-17T10:00:00",
    "end_time": "2025-11-17T11:00:00",
    "location": "Conference Room A",
    "attendees": ["user1@example.com", "user2@example.com"]
  }
}
```

#### GEVENT_GET
Get event details.

**Request:**
```json
{
  "operation": "GEVENT_GET",
  "payload": {
    "calendar_id": "primary",
    "event_id": "event123"
  }
}
```

#### GEVENT_UPDATE
Update an event.

**Request:**
```json
{
  "operation": "GEVENT_UPDATE",
  "payload": {
    "calendar_id": "primary",
    "event_id": "event123",
    "summary": "Updated Meeting",
    "start_time": "2025-11-17T14:00:00",
    "end_time": "2025-11-17T15:00:00"
  }
}
```

#### GEVENT_DELETE
Delete an event.

**Request:**
```json
{
  "operation": "GEVENT_DELETE",
  "payload": {
    "calendar_id": "primary",
    "event_id": "event123"
  }
}
```

#### GEVENT_SEARCH
Search events (wildcard).

**Request:**
```json
{
  "operation": "GEVENT_SEARCH",
  "payload": {
    "calendar_id": "primary",
    "query": "meeting",
    "max_results": 25
  }
}
```

---

## Todoist Operations

### TODOIST_TASK
Get a specific Todoist task.

**Request:**
```json
{
  "operation": "TODOIST_TASK",
  "payload": {
    "task_id": "12345"
  }
}
```

### TODOIST_TASKS
List Todoist tasks.

**Request:**
```json
{
  "operation": "TODOIST_TASKS",
  "payload": {
    "project_id": "67890",
    "filter": "today"
  }
}
```

**Response:**
```json
{
  "status": "ok",
  "tasks": [
    {
      "id": "12345",
      "content": "Task title",
      "completed": false,
      "project_id": "67890"
    }
  ]
}
```

### TODOIST_CREATE
Create a Todoist task.

**Request:**
```json
{
  "operation": "TODOIST_CREATE",
  "payload": {
    "content": "New task",
    "project_id": "67890",
    "due_string": "tomorrow",
    "priority": 3
  }
}
```

### TODOIST_CLOSE
Complete a Todoist task.

**Request:**
```json
{
  "operation": "TODOIST_CLOSE",
  "payload": {
    "task_id": "12345"
  }
}
```

### TODOIST_PROJECT
Get Todoist project details.

**Request:**
```json
{
  "operation": "TODOIST_PROJECT",
  "payload": {
    "project_id": "67890"
  }
}
```

### TODOIST_PROJECTS
List all Todoist projects.

**Request:**
```json
{
  "operation": "TODOIST_PROJECTS",
  "payload": {}
}
```

### TODOIST_LABELS
List Todoist labels.

**Request:**
```json
{
  "operation": "TODOIST_LABELS",
  "payload": {}
}
```

### TODOIST_COMMENT
Add a comment to a task.

**Request:**
```json
{
  "operation": "TODOIST_COMMENT",
  "payload": {
    "task_id": "12345",
    "content": "Comment text"
  }
}
```

---

## Amplenote Operations

### AMPLENOTE_NOTES
List Amplenote notes.

**Request:**
```json
{
  "operation": "AMPLENOTE_NOTES",
  "payload": {
    "tag": "work",
    "limit": 10
  }
}
```

**Response:**
```json
{
  "status": "ok",
  "notes": [
    {
      "uuid": "note-uuid",
      "name": "Note Title",
      "tags": ["work", "project"]
    }
  ]
}
```

### AMPLENOTE_NOTE
Get a specific Amplenote note.

**Request:**
```json
{
  "operation": "AMPLENOTE_NOTE",
  "payload": {
    "note_id": "note-uuid"
  }
}
```

### AMPLENOTE_CREATE
Create an Amplenote note.

**Request:**
```json
{
  "operation": "AMPLENOTE_CREATE",
  "payload": {
    "name": "New Note",
    "content": "Note content",
    "tags": ["work", "important"]
  }
}
```

### AMPLENOTE_UPDATE
Update an Amplenote note.

**Request:**
```json
{
  "operation": "AMPLENOTE_UPDATE",
  "payload": {
    "note_id": "note-uuid",
    "content": "Updated content"
  }
}
```

### AMPLENOTE_DELETE
Delete an Amplenote note.

**Request:**
```json
{
  "operation": "AMPLENOTE_DELETE",
  "payload": {
    "note_id": "note-uuid"
  }
}
```

### AMPLENOTE_TASKS
List Amplenote tasks.

**Request:**
```json
{
  "operation": "AMPLENOTE_TASKS",
  "payload": {
    "note_id": "note-uuid"
  }
}
```

### AMPLENOTE_TAGS
List all Amplenote tags.

**Request:**
```json
{
  "operation": "AMPLENOTE_TAGS",
  "payload": {}
}
```

---

## System Operations

### QUIT / EXIT
Terminate the MCP session.

**Request:**
```json
{
  "operation": "QUIT",
  "payload": {}
}
```

**Response:**
```json
{
  "status": "ok",
  "message": "Goodbye!"
}
```

---

## Authentication & Configuration

### Environment Variables

**Google:**
```bash
GOOGLE_CLIENT_SECRET=your-client-secret
```

**Todoist:**
```bash
TODOIST_API_TOKEN=your-todoist-token
```

**Amplenote:**
```bash
AMPLENOTE_API_TOKEN=your-amplenote-token
```

### Config File (config.yaml)

```yaml
configs:
  providers:
    - provider: google
      client_id: "your-client-id"
      client_secret: "${GOOGLE_CLIENT_SECRET}"
      redirect_uri: "http://localhost:8080/callback"
    
    - provider: todoist
      apiKey: "${TODOIST_API_TOKEN}"
    
    - provider: amplenote
      apiKey: "${AMPLENOTE_API_TOKEN}"
```

---

## Error Handling

All operations return errors in this format:

```json
{
  "status": "error",
  "error": "Error message here"
}
```

**Common Errors:**
- `"Not authenticated with Google"` - Need to authenticate first
- `"Google service not initialized"` - Service not configured
- `"Missing required field"` - Required parameter not provided
- `"Path not allowed"` - File path outside allowed roots
- `"Permission denied"` - Insufficient permissions

---

## Usage Examples

### Python Client

```python
import requests
import json

MCP_URL = "http://localhost:2500"
TOKEN = "your-token"

def call_mcp(operation, payload):
    body = f"{operation} {json.dumps(payload)}"
    response = requests.post(
        MCP_URL,
        headers={
            "Authorization": f"Bearer {TOKEN}",
            "Content-Type": "text/plain"
        },
        data=body
    )
    return response.json()

# List calendars
result = call_mcp("GCAL_LIST", {})
print(result)

# Create event
result = call_mcp("GEVENT_CREATE", {
    "summary": "Meeting",
    "start_time": "2025-11-17T10:00:00",
    "end_time": "2025-11-17T11:00:00"
})
print(result)
```

### JavaScript Client

```javascript
async function callMCP(operation, payload) {
  const response = await fetch('http://localhost:2500', {
    method: 'POST',
    headers: {
      'Authorization': 'Bearer your-token',
      'Content-Type': 'text/plain'
    },
    body: `${operation} ${JSON.stringify(payload)}`
  });
  return response.json();
}

// List tasks
const result = await callMCP('TODOIST_TASKS', {});
console.log(result);
```

---

## Operation Summary

| Category | Operations | Status |
|----------|------------|--------|
| **File System** | 11 | ✅ |
| **TODO** | 4 | ✅ |
| **Google Auth** | 3 | ✅ |
| **Google Docs** | 5 | ✅ |
| **Gmail** | 5 | ✅ |
| **Google Calendar** | 12 | ✅ |
| **Todoist** | 8 | ✅ |
| **Amplenote** | 7 | ✅ |
| **System** | 1 | ✅ |
| **TOTAL** | **56** | ✅ |

---

## Testing

Run the MCP server:
```bash
python -m robodog.cli --folders ./project --port 2500 --token testtoken --config config.yaml
```

Test operations:
```bash
# Test Google Calendar
python test_calendar.py

# Test Gmail
python list_emails.py

# Test MCP operations
python test_mcp_google.py
```

---

## Support

For issues or questions:
- Check error messages in response
- Verify authentication status
- Ensure environment variables are set
- Check config.yaml format
- Review operation documentation above

---

**Last Updated:** 2025-11-17  
**Version:** 2.0  
**Status:** Production Ready ✅
