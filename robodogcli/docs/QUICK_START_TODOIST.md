# Quick Start: Todoist Integration

Get started with Todoist integration in 5 minutes.

## Prerequisites

- Robodog CLI installed
- Todoist account (free or premium)
- Internet connection for OAuth authentication

## Step 1: Get OAuth Credentials

1. Go to https://developer.todoist.com/appconsole.html
2. Click "Create a new app"
3. Fill in:
   - **App name**: Robodog CLI
   - **OAuth redirect URL**: `http://localhost:8080`
4. Copy your **Client ID** and **Client Secret**

## Step 2: Configure Robodog

Edit `config.yaml` and add your credentials:

```yaml
- provider: todoist
  baseUrl: "https://api.todoist.com/rest/v2"
  authUrl: "https://todoist.com/oauth/authorize"
  tokenUrl: "https://todoist.com/oauth/access_token"
  clientId: "your_client_id_here"
  clientSecret: "your_client_secret_here"
  scopes:
    - "data:read_write"
    - "data:delete"
    - "project:delete"
```

## Step 3: Start Robodog

```bash
python -m robodogcli.cli
```

## Step 4: Authenticate

```
/todoist auth
```

Your browser will open. Log in to Todoist and authorize Robodog. Copy the redirect URL and paste it back into the CLI.

## Step 5: List Your Projects

```
/todoist projects
```

## Step 6: Create Your First Task

```
/todoist create Buy groceries tomorrow p2 @shopping
```

## Step 7: List Your Tasks

```
/todoist tasks
```

## Step 8: Complete a Task

```
/todoist complete <task_id>
```

Replace `<task_id>` with an actual task ID from the list.

## Common Workflows

### Morning Task Review

```
# List today's tasks
/todoist tasks

# Add new tasks
/todoist create Review emails p3
/todoist create Team standup at 10am p2
/todoist create Finish report p4
```

### Project Setup

```
# Create a new project
/todoist project "Website Redesign" blue

# Get project ID from output, then add tasks
/todoist create Define requirements p4
/todoist create Create wireframes p3
/todoist create Design mockups p3
```

### Quick Task Entry

Use natural language with Quick Add syntax:

```
/todoist create Call dentist tomorrow p2
/todoist create Buy milk today @shopping
/todoist create Submit report next Monday p4 @work
```

Quick Add syntax:
- `p1-p4`: Priority (p4 is highest)
- `@label`: Add label
- `today`, `tomorrow`, `next week`: Due date

### Weekly Review

```
# List all projects
/todoist projects

# Check tasks in each project
/todoist tasks <project_id>

# List all labels
/todoist labels
```

## Priority System

- 🔴 **P4**: Highest priority (urgent and important)
- 🟡 **P3**: High priority (important)
- 🔵 **P2**: Medium priority
- ⚪ **P1**: Normal priority (default)

## Tips

1. **Use Quick Add**: Natural language makes task creation fast
2. **Set Priorities**: Use p1-p4 to organize by importance
3. **Use Labels**: Organize tasks with @work, @personal, @shopping
4. **Due Dates**: Use natural language like "tomorrow" or "next Monday"
5. **Comments**: Add context with `/todoist comment <task_id> <text>`

## Integration with Robodog AI

### Generate Task Lists

Ask Robodog's AI to break down complex tasks:

```
# In chat
Break down "Launch new website" into actionable tasks

# AI responds with list, then create tasks
/todoist create Set up hosting p3
/todoist create Configure DNS p2
/todoist create Deploy application p4
/todoist create Test all pages p3
```

### Smart Task Creation

Use AI to refine task descriptions:

```
# In chat
Improve this task: "do website stuff"

# AI suggests: "Complete homepage redesign with responsive layout"
/todoist create Complete homepage redesign with responsive layout p3 @work
```

## Advanced Examples

### Recurring Tasks

```
/todoist create Water plants every Monday p1
/todoist create Pay rent every month p4
/todoist create Backup files every week p2
```

### Task with Description

```python
# Using Python API
task = svc.todoist.create_task(
    content="Quarterly review",
    description="Review Q1 metrics, plan Q2 goals, update stakeholders",
    due_string="next Friday",
    priority=4,
    labels=["work", "planning"]
)
```

### Batch Task Creation

```python
# Create multiple tasks at once
tasks = [
    ("Design landing page", 3),
    ("Implement contact form", 2),
    ("Set up analytics", 2),
    ("Write documentation", 1)
]

for content, priority in tasks:
    svc.todoist.create_task(
        content=content,
        priority=priority,
        project_id="your_project_id"
    )
```

## Troubleshooting

**Problem**: Authentication fails  
**Solution**: Verify client ID and secret in config.yaml are correct

**Problem**: "Not authenticated" error  
**Solution**: Run `/todoist auth` to authenticate first

**Problem**: Can't find task ID  
**Solution**: Use `/todoist tasks` to list tasks with their IDs

**Problem**: Rate limit error  
**Solution**: Wait a few minutes (limit: 450 requests per 15 minutes)

## Next Steps

- Read the [full documentation](TODOIST_INTEGRATION.md)
- Explore the [Todoist API](https://developer.todoist.com/rest/v2/)
- Check out [advanced examples](#advanced-examples)
- Integrate with Robodog's AI features

## Keyboard Shortcuts

Create aliases for common commands in your shell:

```bash
# Bash/Zsh aliases
alias td-today='python -m robodogcli.cli -c "/todoist tasks"'
alias td-add='python -m robodogcli.cli -c "/todoist create"'
alias td-done='python -m robodogcli.cli -c "/todoist complete"'
```

## Getting Help

- Type `/help` in Robodog CLI for all commands
- Read the [full documentation](TODOIST_INTEGRATION.md)
- Check the logs: `robodog.log`
- Visit [Todoist Help Center](https://todoist.com/help)

## Example Session

```
$ python -m robodogcli.cli

> /todoist auth
Opening browser for authentication...
✓ Authentication successful!

> /todoist projects
📁 Found 3 projects:
   2345678901: Work ⭐
   2345678902: Personal
   2345678903: Shopping

> /todoist create Finish presentation tomorrow p4 @work
✅ Created task: Finish presentation (ID: 8765432101)

> /todoist tasks 2345678901
✓ Found 5 tasks:
   🔴 8765432101: Finish presentation (due: 2025-01-21)
   🟡 8765432102: Review code changes
   🔵 8765432103: Update documentation
   ⚪ 8765432104: Team meeting notes
   ⚪ 8765432105: Research new tools

> /todoist complete 8765432104
✅ Completed task 8765432104

> /todoist comment 8765432101 Added slides for Q1 metrics
✅ Added comment to task 8765432101
```

## Best Practices

1. **Daily Review**: Start each day with `/todoist tasks` to see what's due
2. **Priority First**: Always set priority when creating important tasks
3. **Use Projects**: Organize tasks into projects for better management
4. **Add Context**: Use comments to add notes and updates
5. **Regular Cleanup**: Complete or delete old tasks to keep lists clean
6. **Labels for Context**: Use labels to filter tasks by context (@work, @home, @errands)
7. **Natural Due Dates**: Use "tomorrow", "next week" instead of specific dates when possible

## Common Patterns

### GTD (Getting Things Done)

```
# Inbox project for quick capture
/todoist project "Inbox"

# Quick capture
/todoist create Check email p1
/todoist create Call John p2

# Process inbox daily
/todoist tasks <inbox_project_id>
# Then move to appropriate projects
```

### Pomodoro Technique

```
# Create focused work tasks
/todoist create Write report - 25 min p4 @focus
/todoist create Review code - 25 min p3 @focus

# Complete after each pomodoro
/todoist complete <task_id>
```

### Time Blocking

```
# Schedule tasks for specific times
/todoist create 9am: Morning standup p3 @work
/todoist create 10am: Deep work session p4 @focus
/todoist create 2pm: Client meeting p3 @work
/todoist create 4pm: Email and admin p1 @work
```
