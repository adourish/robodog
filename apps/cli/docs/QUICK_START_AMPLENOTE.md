# Quick Start: Amplenote Integration

Get started with Amplenote integration in 5 minutes.

## Prerequisites

- Robodog CLI installed
- Amplenote account (free or paid)
- Internet connection for OAuth authentication

## Step 1: Install Dependencies

```bash
pip install --upgrade authlib
```

## Step 2: Start Robodog

```bash
python -m robodogcli.cli
```

## Step 3: Authenticate

```
/amplenote auth
```

Your browser will open. Log in to Amplenote and authorize Robodog. Copy the redirect URL and paste it back into the CLI.

## Step 4: Create Your First Note

```
/amplenote create "My Robodog Note"
```

You'll receive a note UUID. Save it for the next steps.

## Step 5: Add Content

Replace `<note_uuid>` with your actual note UUID:

```
/amplenote add <note_uuid> This is my first note created from Robodog!
```

## Step 6: Add a Task

```
/amplenote task <note_uuid> Learn more about Robodog features
```

## Step 7: List Your Notes

```
/amplenote list
```

## Common Workflows

### Daily Standup Notes

```
# Create daily note
/amplenote create "Standup 2025-01-15" standup,daily

# Add what you did yesterday
/amplenote add <uuid> ## Yesterday

# Add tasks for today
/amplenote task <uuid> Complete feature X
/amplenote task <uuid> Review PR #123
/amplenote task <uuid> Meeting with team at 2pm
```

### Project Documentation

```
# Create project note
/amplenote create "Project Alpha" project,documentation

# Add overview
/amplenote add <uuid> ## Project Overview
/amplenote add <uuid> This project aims to build a new feature...

# Add reference links
/amplenote link <uuid> https://github.com/org/repo GitHub Repository
/amplenote link <uuid> https://docs.example.com Documentation

# Upload diagrams
/amplenote upload <uuid> C:\projects\diagrams\architecture.png
```

### Meeting Notes

```
# Create meeting note
/amplenote create "Team Meeting 2025-01-15" meetings

# Add attendees
/amplenote add <uuid> ## Attendees
/amplenote add <uuid> - Alice, Bob, Charlie

# Add agenda items as tasks
/amplenote task <uuid> Discuss Q1 roadmap
/amplenote task <uuid> Review sprint progress
/amplenote task <uuid> Plan next release
```

## Tips

1. **Save Note UUIDs**: Keep frequently-used note UUIDs in a text file for easy access
2. **Use Tags**: Organize notes with tags for better filtering
3. **Batch Operations**: Create scripts to automate repetitive note operations
4. **Integration**: Combine with Robodog's AI features to generate content

## Next Steps

- Read the [full documentation](AMPLENOTE_INTEGRATION.md)
- Explore the [Amplenote API](https://api.amplenote.com/)
- Check out [advanced examples](#advanced-examples)

## Advanced Examples

### AI-Generated Content

Use Robodog's AI to generate content, then save to Amplenote:

```
# Ask AI to generate content
What are the key features of OAuth2 PKCE?

# Copy the response and add to note
/amplenote add <uuid> [paste AI response here]
```

### Automated Task Creation

Create a script to add daily tasks:

```python
from robodog.amplenote_service import AmplenoteService

# Initialize service
config = {
    "baseUrl": "https://api.amplenote.com/v4",
    "authUrl": "https://login.amplenote.com/login",
    "tokenUrl": "https://api.amplenote.com/oauth/token",
    "scopes": ["notes:create", "notes:create-content-action"]
}
service = AmplenoteService(config)

# Create daily tasks
daily_note_uuid = "your-daily-note-uuid"
tasks = [
    "Check emails",
    "Review PRs",
    "Daily standup",
    "Focus time: 2 hours"
]

for task in tasks:
    service.insert_task(daily_note_uuid, task)
```

## Troubleshooting

**Problem**: Authentication fails  
**Solution**: Make sure to copy the entire redirect URL, including all query parameters

**Problem**: "Not authenticated" error  
**Solution**: Run `/amplenote auth` to authenticate first

**Problem**: Invalid note UUID  
**Solution**: Use `/amplenote list` to get valid note UUIDs

## Getting Help

- Type `/help` in Robodog CLI for all commands
- Read the [full documentation](AMPLENOTE_INTEGRATION.md)
- Check the logs: `robodog.log`
