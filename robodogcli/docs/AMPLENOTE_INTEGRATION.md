# Amplenote API Integration

## Overview

The Amplenote integration allows Robodog to interact with your Amplenote account, enabling you to create notes, add content, manage tasks, and upload media directly from the CLI.

## Features

- **OAuth2 PKCE Authentication**: Secure authentication flow with Proof Key for Code Exchange
- **Note Management**: Create, list, and restore notes
- **Content Operations**: Add paragraphs, tasks, bullet lists, and links to notes
- **Media Upload**: Upload images and videos to notes
- **Task Management**: Create and manage tasks with due dates and flags

## Configuration

The Amplenote provider is configured in `config.yaml`:

```yaml
providers:
  - provider: amplenote
    baseUrl: "https://api.amplenote.com/v4"
    authUrl: "https://login.amplenote.com/login"
    tokenUrl: "https://api.amplenote.com/oauth/token"
    apiKey: ""
    scopes:
      - "notes:create"
      - "notes:create-content-action"
      - "notes:create-image"
      - "notes:list"
```

## Authentication

### Initial Setup

1. Run the authentication command:
   ```
   /amplenote auth
   ```

2. Your browser will open to the Amplenote login page
3. Log in and authorize Robodog
4. Copy the redirect URL from your browser
5. Paste it into the CLI when prompted

The access token is stored securely in `~/.robodog/amplenote_token.json` and will be reused for future sessions.

### Logout

To clear your authentication:
```
/amplenote logout
```

## Available Commands

### List Notes

List all notes in your account:
```
/amplenote list
```

Example output:
```
📝 Found 25 notes:
   abc123: My First Note
   def456: Project Ideas
   ghi789: Meeting Notes
   ... and 22 more
```

### Create Note

Create a new note with optional tags:
```
/amplenote create "My New Note"
/amplenote create "Tagged Note" work,important
```

Example output:
```
✅ Created note: My New Note (UUID: abc123-def456-ghi789)
```

### Add Content

Add a paragraph to an existing note:
```
/amplenote add abc123-def456-ghi789 This is some content to add to the note
```

### Add Task

Add a task to a note:
```
/amplenote task abc123-def456-ghi789 Complete the project documentation
```

### Add Link

Add a link with display text to a note:
```
/amplenote link abc123-def456-ghi789 https://example.com Check out this resource
```

### Upload Media

Upload an image or video to a note:
```
/amplenote upload abc123-def456-ghi789 C:\path\to\image.png
```

## API Reference

### AmplenoteService Class

The `AmplenoteService` class provides programmatic access to the Amplenote API.

#### Authentication Methods

```python
# Authenticate with OAuth2 PKCE
service.authenticate(redirect_uri="http://localhost:8080/callback")

# Check authentication status
if service.is_authenticated():
    print("Authenticated!")

# Clear authentication
service.clear_authentication()
```

#### Note Operations

```python
# List all notes
notes = service.list_notes()

# List deleted notes
deleted = service.list_deleted_notes()

# Create a new note
note = service.create_note(
    name="My Note",
    tags=["work", "important"],
    created_timestamp=1234567890
)

# Restore a deleted note
restored = service.restore_note(note_uuid="abc123")
```

#### Content Operations

```python
# Insert paragraph
service.insert_content(
    note_uuid="abc123",
    content="This is a paragraph",
    content_type="paragraph"
)

# Insert task with due date and flags
service.insert_task(
    note_uuid="abc123",
    task_text="Complete documentation",
    due=1234567890,  # Unix timestamp
    flags="IU"  # Important and Urgent
)

# Insert link with description
service.insert_link(
    note_uuid="abc123",
    url="https://example.com",
    link_text="Example Site",
    description="A useful resource"
)
```

#### Media Operations

```python
# Upload media file
src_url = service.upload_media(
    note_uuid="abc123",
    file_path="/path/to/image.png",
    mime_type="image/png"  # Optional, auto-detected
)
```

## Content Node Structure

The Amplenote API uses a node-based structure for content. Here are common patterns:

### Paragraph

```json
{
  "type": "paragraph",
  "content": [
    {"type": "text", "text": "This is a paragraph"}
  ]
}
```

### Task (Check List Item)

```json
{
  "type": "check_list_item",
  "attrs": {
    "due": 1234567890,
    "flags": "I",
    "completedAt": null
  },
  "content": [
    {
      "type": "paragraph",
      "content": [
        {"type": "text", "text": "Task description"}
      ]
    }
  ]
}
```

### Bullet List Item

```json
{
  "type": "bullet_list_item",
  "content": [
    {
      "type": "paragraph",
      "content": [
        {"type": "text", "text": "Bullet point"}
      ]
    }
  ]
}
```

### Link

```json
{
  "type": "paragraph",
  "content": [
    {
      "type": "link",
      "attrs": {
        "href": "https://example.com",
        "description": "Optional description"
      },
      "content": [
        {"type": "text", "text": "Link text"}
      ]
    }
  ]
}
```

### Image

```json
{
  "type": "image",
  "attrs": {
    "src": "https://api.amplenote.com/media/abc123.png"
  }
}
```

## Task Attributes

Tasks support various attributes for scheduling and organization:

- **completedAt**: Unix timestamp when task was completed
- **createdAt**: Unix timestamp when task was created
- **collapsed**: Boolean, whether nested tasks are hidden
- **dismissedAt**: Unix timestamp when task was dismissed
- **due**: Unix timestamp for "start at" time
- **dueDayPart**: Fuzzy time ("E", "M", "A", "N", "L", "W")
- **duration**: ISO 8601 duration (e.g., "PT2H30M")
- **indent**: 0-based indent level
- **notify**: ISO 8601 duration before due date for notification
- **points**: Additional task points
- **flags**: "I" (important), "U" (urgent), or "IU"
- **repeat**: RRULE or ISO 8601 duration for recurrence
- **startAt**: When task will be unhidden

## Error Handling

All API methods raise exceptions on errors. Wrap calls in try-except blocks:

```python
try:
    note = svc.amplenote.create_note("My Note")
    print(f"Created: {note['uuid']}")
except Exception as e:
    print(f"Error: {e}")
```

## Security

- Access tokens are stored in `~/.robodog/amplenote_token.json`
- The file is created with user-only permissions
- Tokens are transmitted over HTTPS only
- OAuth2 PKCE flow prevents authorization code interception

## Scopes

The integration requests the following OAuth scopes:

- **notes:create**: Create new notes
- **notes:create-content-action**: Add content to notes
- **notes:create-image**: Upload media files
- **notes:list**: View list of notes

## Limitations

- Cannot access encrypted note content (by design)
- Cannot decrypt notes (requires user's encryption keys)
- Media uploads limited by account subscription level
- API rate limits apply (see Amplenote documentation)

## Examples

### Workflow: Create Note and Add Content

```python
# Authenticate
svc.amplenote.authenticate()

# Create note
note = svc.amplenote.create_note(
    name="Project Planning",
    tags=["work", "project"]
)
note_uuid = note['uuid']

# Add content
svc.amplenote.insert_content(note_uuid, "## Project Overview")
svc.amplenote.insert_content(note_uuid, "This project aims to...")

# Add tasks
svc.amplenote.insert_task(note_uuid, "Define requirements")
svc.amplenote.insert_task(note_uuid, "Create mockups")
svc.amplenote.insert_task(note_uuid, "Implement features")

# Add reference link
svc.amplenote.insert_link(
    note_uuid,
    "https://docs.example.com",
    "Project Documentation"
)
```

### Workflow: Upload Screenshots

```python
import os
from pathlib import Path

# Get all screenshots
screenshots = Path("screenshots").glob("*.png")

# Create note for screenshots
note = svc.amplenote.create_note("UI Screenshots", tags=["design"])
note_uuid = note['uuid']

# Upload each screenshot
for screenshot in screenshots:
    src_url = svc.amplenote.upload_media(note_uuid, str(screenshot))
    print(f"Uploaded: {screenshot.name} -> {src_url}")
```

## Troubleshooting

### Authentication Fails

- Ensure you're copying the complete redirect URL
- Check that your browser didn't modify the URL
- Try using a different browser
- Clear stored token: `/amplenote logout`

### API Errors

- Verify note UUID is correct
- Check that you have necessary permissions
- Ensure content format is valid
- Review API response for specific error messages

### Token Expired

Tokens may expire after a period. Re-authenticate:
```
/amplenote logout
/amplenote auth
```

## Resources

- [Amplenote API Documentation](https://api.amplenote.com/)
- [OAuth2 PKCE Specification](https://oauth.net/2/pkce/)
- [Amplenote Help Center](https://www.amplenote.com/help)

## Support

For issues specific to the Robodog integration:
- Check the logs in `robodog.log`
- Enable debug logging: `logging.getLogger('robodog.amplenote').setLevel(logging.DEBUG)`
- Report issues on the Robodog GitHub repository
