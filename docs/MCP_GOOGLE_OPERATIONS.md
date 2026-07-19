# MCP Google API Operations

Complete reference for Google Docs and Gmail operations via MCP protocol.

## Overview

The Robodog MCP handler now supports all Google API operations, allowing you to:
- Authenticate with Google OAuth2
- Create, read, update, and delete Google Docs
- Send emails, create drafts, and manage Gmail

## Authentication Operations

### GOOGLE_AUTH
Initiate OAuth2 authentication flow.

**Request:**
```json
{
  "operation": "GOOGLE_AUTH",
  "payload": {}
}
```

**Response:**
```json
{
  "status": "ok",
  "authenticated": true,
  "result": {...}
}
```

### GOOGLE_SET_TOKEN
Set access token manually (for pre-authenticated sessions).

**Request:**
```json
{
  "operation": "GOOGLE_SET_TOKEN",
  "payload": {
    "token": "ya29.a0AfH6SMBx...",
    "refresh_token": "1//0gH..." (optional)
  }
}
```

**Response:**
```json
{
  "status": "ok",
  "authenticated": true
}
```

### GOOGLE_STATUS
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
  "has_token": true,
  "available": true
}
```

---

## Google Docs Operations

### GDOC_CREATE
Create a new Google Doc.

**Request:**
```json
{
  "operation": "GDOC_CREATE",
  "payload": {
    "title": "My Document",
    "content": "Initial content here" (optional)
  }
}
```

**Response:**
```json
{
  "status": "ok",
  "document": {
    "documentId": "1abc123xyz",
    "title": "My Document",
    ...
  }
}
```

**Example:**
```javascript
// Create meeting notes
{
  "operation": "GDOC_CREATE",
  "payload": {
    "title": "Team Meeting - 2025-11-16",
    "content": "# Meeting Notes\n\n## Attendees\n- Team Member 1\n- Team Member 2"
  }
}
```

### GDOC_GET
Get full document structure.

**Request:**
```json
{
  "operation": "GDOC_GET",
  "payload": {
    "document_id": "1abc123xyz"
  }
}
```

**Response:**
```json
{
  "status": "ok",
  "document": {
    "documentId": "1abc123xyz",
    "title": "My Document",
    "body": {...},
    ...
  }
}
```

### GDOC_READ
Read plain text content from a document.

**Request:**
```json
{
  "operation": "GDOC_READ",
  "payload": {
    "document_id": "1abc123xyz"
  }
}
```

**Response:**
```json
{
  "status": "ok",
  "document_id": "1abc123xyz",
  "text": "Plain text content of the document..."
}
```

### GDOC_UPDATE
Update document content.

**Request:**
```json
{
  "operation": "GDOC_UPDATE",
  "payload": {
    "document_id": "1abc123xyz",
    "content": "New content to add",
    "insert_index": 1 (optional, default: 1)
  }
}
```

**Response:**
```json
{
  "status": "ok",
  "document_id": "1abc123xyz",
  "result": {...}
}
```

**Example:**
```javascript
// Append to document
{
  "operation": "GDOC_UPDATE",
  "payload": {
    "document_id": "1abc123xyz",
    "content": "\n\n## New Section\nAdditional content here"
  }
}
```

### GDOC_DELETE
Delete a document (move to trash).

**Request:**
```json
{
  "operation": "GDOC_DELETE",
  "payload": {
    "document_id": "1abc123xyz"
  }
}
```

**Response:**
```json
{
  "status": "ok",
  "document_id": "1abc123xyz",
  "deleted": true
}
```

---

## Gmail Operations

### GMAIL_SEND
Send an email.

**Request:**
```json
{
  "operation": "GMAIL_SEND",
  "payload": {
    "to": "recipient@example.com",
    "subject": "Email Subject",
    "body": "Email body content",
    "is_html": false (optional),
    "cc": "cc@example.com" (optional),
    "bcc": "bcc@example.com" (optional)
  }
}
```

**Response:**
```json
{
  "status": "ok",
  "email": {
    "id": "17d...",
    "threadId": "17d...",
    ...
  }
}
```

**Example - Plain Text:**
```javascript
{
  "operation": "GMAIL_SEND",
  "payload": {
    "to": "support@amplenote.com",
    "subject": "Request for Renewed Client Key",
    "body": "Dear Support Team,\n\nI need a renewed client key..."
  }
}
```

**Example - HTML:**
```javascript
{
  "operation": "GMAIL_SEND",
  "payload": {
    "to": "team@company.com",
    "subject": "Weekly Report",
    "body": "<h1>Weekly Report</h1><p>Here are the highlights...</p>",
    "is_html": true
  }
}
```

### GMAIL_LIST
List emails with optional filtering.

**Request:**
```json
{
  "operation": "GMAIL_LIST",
  "payload": {
    "max_results": 10 (optional, default: 10),
    "query": "from:someone@example.com" (optional)
  }
}
```

**Response:**
```json
{
  "status": "ok",
  "emails": {
    "messages": [
      {"id": "17d...", "threadId": "17d..."},
      ...
    ]
  }
}
```

**Query Examples:**
```javascript
// Recent unread emails
{"query": "is:unread"}

// Emails from specific sender
{"query": "from:boss@company.com"}

// Emails with attachment
{"query": "has:attachment"}

// Emails in date range
{"query": "after:2025/11/01 before:2025/11/16"}
```

### GMAIL_GET
Get a specific email.

**Request:**
```json
{
  "operation": "GMAIL_GET",
  "payload": {
    "message_id": "17d..."
  }
}
```

**Response:**
```json
{
  "status": "ok",
  "email": {
    "id": "17d...",
    "threadId": "17d...",
    "payload": {
      "headers": [...],
      "body": {...}
    },
    ...
  }
}
```

### GMAIL_DRAFT
Create an email draft.

**Request:**
```json
{
  "operation": "GMAIL_DRAFT",
  "payload": {
    "to": "recipient@example.com",
    "subject": "Draft Subject",
    "body": "Draft content",
    "is_html": false (optional),
    "cc": "cc@example.com" (optional),
    "bcc": "bcc@example.com" (optional)
  }
}
```

**Response:**
```json
{
  "status": "ok",
  "draft": {
    "id": "r123...",
    "message": {...}
  }
}
```

### GMAIL_DELETE_DRAFT
Delete an email draft.

**Request:**
```json
{
  "operation": "GMAIL_DELETE_DRAFT",
  "payload": {
    "draft_id": "r123..."
  }
}
```

**Response:**
```json
{
  "status": "ok",
  "draft_id": "r123...",
  "deleted": true
}
```

---

## Complete Workflow Examples

### Example 1: Create Document and Email Link

```javascript
// Step 1: Create document
{
  "operation": "GDOC_CREATE",
  "payload": {
    "title": "Project Proposal",
    "content": "# Project Proposal\n\n## Overview\n..."
  }
}
// Response: {"status":"ok","document":{"documentId":"1abc123"}}

// Step 2: Email the link
{
  "operation": "GMAIL_SEND",
  "payload": {
    "to": "team@company.com",
    "subject": "New Project Proposal",
    "body": "Hi Team,\n\nI've created a new project proposal:\nhttps://docs.google.com/document/d/1abc123\n\nPlease review."
  }
}
```

### Example 2: Read Document and Send Summary

```javascript
// Step 1: Read document
{
  "operation": "GDOC_READ",
  "payload": {
    "document_id": "1abc123"
  }
}
// Response: {"status":"ok","text":"Document content..."}

// Step 2: Send summary email
{
  "operation": "GMAIL_SEND",
  "payload": {
    "to": "manager@company.com",
    "subject": "Document Summary",
    "body": "Summary of the document:\n\n[AI-generated summary]"
  }
}
```

### Example 3: Automated Report Generation

```javascript
// Step 1: Create report document
{
  "operation": "GDOC_CREATE",
  "payload": {
    "title": "Weekly Report - Week 46",
    "content": "# Weekly Report\n\n## Metrics\n- Tasks completed: 15\n- In progress: 3"
  }
}

// Step 2: Send to stakeholders
{
  "operation": "GMAIL_SEND",
  "payload": {
    "to": "stakeholders@company.com",
    "subject": "Weekly Report - Week 46",
    "body": "<h2>Weekly Report Available</h2><p>View the full report here...</p>",
    "is_html": true
  }
}
```

---

## Error Handling

All operations return standard error responses:

```json
{
  "status": "error",
  "error": "Error message here"
}
```

**Common Errors:**

- `"Google service not initialized"` - Google service not available
- `"Not authenticated with Google"` - Need to run GOOGLE_AUTH first
- `"Missing 'title'"` - Required parameter missing
- `"Missing 'document_id'"` - Document ID required
- `"Missing 'to', 'subject', or 'body'"` - Email parameters missing

---

## Configuration

### Option 1: Config File

Add to your `config.yaml`:

```yaml
configs:
  providers:
    - provider: google
      client_id: "837032747486-0dttoe0dfkfrn9m3obimrgboj8i64leu.apps.googleusercontent.com"
      client_secret: "YOUR_CLIENT_SECRET"
      redirect_uri: "http://localhost:8080/callback"
```

### Option 2: Environment Variable

```bash
# PowerShell
$env:GOOGLE_CLIENT_SECRET="your_secret_here"

# Bash
export GOOGLE_CLIENT_SECRET="your_secret_here"
```

---

## Testing MCP Operations

### Using curl

```bash
# Check Google status
curl -X POST http://localhost:2500 \
  -H "Authorization: Bearer testtoken" \
  -H "Content-Type: application/json" \
  -d '{"operation":"GOOGLE_STATUS","payload":{}}'

# Create document
curl -X POST http://localhost:2500 \
  -H "Authorization: Bearer testtoken" \
  -H "Content-Type: application/json" \
  -d '{"operation":"GDOC_CREATE","payload":{"title":"Test Doc","content":"Hello"}}'

# Send email
curl -X POST http://localhost:2500 \
  -H "Authorization: Bearer testtoken" \
  -H "Content-Type: application/json" \
  -d '{"operation":"GMAIL_SEND","payload":{"to":"test@example.com","subject":"Test","body":"Test email"}}'
```

### Using Python

```python
import requests
import json

MCP_URL = "http://localhost:2500"
TOKEN = "testtoken"

def call_mcp(operation, payload):
    response = requests.post(
        MCP_URL,
        headers={
            "Authorization": f"Bearer {TOKEN}",
            "Content-Type": "application/json"
        },
        json={"operation": operation, "payload": payload}
    )
    return response.json()

# Check status
status = call_mcp("GOOGLE_STATUS", {})
print(status)

# Create document
doc = call_mcp("GDOC_CREATE", {
    "title": "My Document",
    "content": "Hello World"
})
print(f"Created: {doc['document']['documentId']}")

# Send email
email = call_mcp("GMAIL_SEND", {
    "to": "someone@example.com",
    "subject": "Test",
    "body": "Test email from MCP"
})
print(f"Sent: {email['email']['id']}")
```

---

## Summary

**Total Operations:** 13

**Authentication (3):**
- GOOGLE_AUTH
- GOOGLE_SET_TOKEN
- GOOGLE_STATUS

**Google Docs (5):**
- GDOC_CREATE
- GDOC_GET
- GDOC_READ
- GDOC_UPDATE
- GDOC_DELETE

**Gmail (5):**
- GMAIL_SEND
- GMAIL_LIST
- GMAIL_GET
- GMAIL_DRAFT
- GMAIL_DELETE_DRAFT

All operations are production-ready and integrated into the MCP handler! 🎉
