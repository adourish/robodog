# Todoist API Integration

## Overview

The Todoist integration allows Robodog to interact with your Todoist account, enabling you to manage projects, tasks, labels, and comments directly from the CLI.

## Features

- **OAuth2 Authentication**: Secure authentication flow with state verification
- **Project Management**: Create, list, update, and delete projects
- **Task Management**: Create, list, update, complete, and delete tasks
- **Sections**: Organize tasks within projects using sections
- **Labels**: Create and manage labels for task organization
- **Comments**: Add comments to tasks and projects
- **Quick Add**: Natural language task creation with priority and labels
- **Filtering**: Filter tasks by project, label, or custom queries

## Configuration

The Todoist provider is configured in `config.yaml`:

```yaml
providers:
  - provider: todoist
    baseUrl: "https://api.todoist.com/rest/v2"
    authUrl: "https://todoist.com/oauth/authorize"
    tokenUrl: "https://todoist.com/oauth/access_token"
    apiKey: ""
    clientId: "your_client_id"
    clientSecret: "your_client_secret"
    scopes:
      - "data:read_write"
      - "data:delete"
      - "project:delete"
```

### Getting OAuth Credentials

1. Go to https://developer.todoist.com/appconsole.html
2. Click "Create a new app"
3. Fill in app details:
   - **App name**: Robodog CLI
   - **OAuth redirect URL**: `http://localhost:8080`
4. Copy the **Client ID** and **Client Secret**
5. Update `config.yaml` with your credentials

## Authentication

### Initial Setup

1. Add your OAuth credentials to `config.yaml`
2. Run the authentication command:
   ```
   /todoist auth
   ```
3. Your browser will open to the Todoist authorization page
4. Log in and authorize Robodog
5. Copy the redirect URL from your browser
6. Paste it into the CLI when prompted

The access token is stored securely in `~/.robodog/todoist_token.json` and will be reused for future sessions.

### Logout

To clear your authentication:
```
/todoist logout
```

## Available Commands

### List Projects

List all projects in your account:
```
/todoist projects
```

Example output:
```
📁 Found 5 projects:
   2345678901: Work ⭐
   2345678902: Personal
   2345678903: Shopping
   2345678904: Ideas
   2345678905: Reading List
```

### Create Project

Create a new project:
```
/todoist project "My New Project"
/todoist project "Urgent Tasks" red
```

Available colors: `berry_red`, `red`, `orange`, `yellow`, `olive_green`, `lime_green`, `green`, `mint_green`, `teal`, `sky_blue`, `light_blue`, `blue`, `grape`, `violet`, `lavender`, `magenta`, `salmon`, `charcoal`, `grey`, `taupe`

### List Tasks

List all active tasks:
```
/todoist tasks
```

List tasks in a specific project:
```
/todoist tasks 2345678901
```

Example output:
```
✓ Found 8 tasks:
   🔴 8765432101: Complete project proposal (due: 2025-01-20)
   🟡 8765432102: Review code changes
   🔵 8765432103: Update documentation (due: 2025-01-22)
   ⚪ 8765432104: Buy groceries
   ... and 4 more
```

Priority indicators:
- 🔴 Priority 4 (Highest)
- 🟡 Priority 3
- 🔵 Priority 2
- ⚪ Priority 1 (Default)

### Create Task

Create a task with natural language:
```
/todoist create Buy milk tomorrow p1 @shopping
/todoist create Complete report p3
/todoist create Call dentist today p2
```

Quick Add syntax:
- `p1-p4`: Set priority (p4 is highest)
- `@label`: Add label
- `today`, `tomorrow`, `next week`: Set due date

### Complete Task

Mark a task as complete:
```
/todoist complete 8765432101
```

### List Labels

List all labels:
```
/todoist labels
```

Example output:
```
🏷️  Found 6 labels:
   12345: work ⭐
   12346: personal
   12347: urgent
   12348: shopping
   12349: ideas
   12350: waiting
```

### Add Comment

Add a comment to a task:
```
/todoist comment 8765432101 This is progressing well
```

## API Reference

### TodoistService Class

The `TodoistService` class provides programmatic access to the Todoist API.

#### Authentication Methods

```python
# Authenticate with OAuth2
service.authenticate(redirect_uri="http://localhost:8080")

# Check authentication status
if service.is_authenticated():
    print("Authenticated!")

# Clear authentication
service.clear_authentication()
```

#### Project Operations

```python
# List all projects
projects = service.get_projects()

# Create a new project
project = service.create_project(
    name="My Project",
    color="blue",
    is_favorite=True,
    view_style="list"  # or "board"
)

# Get a specific project
project = service.get_project(project_id="2345678901")

# Update a project
updated = service.update_project(
    project_id="2345678901",
    name="Updated Name",
    color="red",
    is_favorite=True
)

# Delete a project
service.delete_project(project_id="2345678901")
```

#### Task Operations

```python
# List all tasks
tasks = service.get_tasks()

# List tasks in a project
tasks = service.get_tasks(project_id="2345678901")

# List tasks with a label
tasks = service.get_tasks(label="urgent")

# List tasks with a filter
tasks = service.get_tasks(filter_query="today")

# Create a new task
task = service.create_task(
    content="Buy groceries",
    description="Milk, bread, eggs",
    project_id="2345678901",
    due_string="tomorrow",
    priority=3,
    labels=["shopping", "urgent"]
)

# Get a specific task
task = service.get_task(task_id="8765432101")

# Update a task
updated = service.update_task(
    task_id="8765432101",
    content="Updated content",
    priority=4,
    due_string="next Monday"
)

# Complete a task
service.close_task(task_id="8765432101")

# Reopen a completed task
service.reopen_task(task_id="8765432101")

# Delete a task
service.delete_task(task_id="8765432101")
```

#### Section Operations

```python
# List all sections
sections = service.get_sections()

# List sections in a project
sections = service.get_sections(project_id="2345678901")

# Create a section
section = service.create_section(
    name="In Progress",
    project_id="2345678901",
    order=1
)

# Update a section
updated = service.update_section(
    section_id="3456789012",
    name="New Name"
)

# Delete a section
service.delete_section(section_id="3456789012")
```

#### Label Operations

```python
# List all labels
labels = service.get_labels()

# Create a label
label = service.create_label(
    name="urgent",
    color="red",
    is_favorite=True
)

# Update a label
updated = service.update_label(
    label_id="12345",
    name="super-urgent",
    color="berry_red"
)

# Delete a label
service.delete_label(label_id="12345")
```

#### Comment Operations

```python
# Get comments for a task
comments = service.get_comments(task_id="8765432101")

# Get comments for a project
comments = service.get_comments(project_id="2345678901")

# Create a comment on a task
comment = service.create_comment(
    content="Great progress!",
    task_id="8765432101"
)

# Create a comment on a project
comment = service.create_comment(
    content="Project update",
    project_id="2345678901"
)

# Update a comment
updated = service.update_comment(
    comment_id="4567890123",
    content="Updated comment"
)

# Delete a comment
service.delete_comment(comment_id="4567890123")
```

#### Quick Add Parser

```python
# Parse natural language task
parsed = service.get_quick_add_task("Buy milk tomorrow p3 @shopping")

# Returns:
# {
#     "content": "Buy milk",
#     "priority": 3,
#     "labels": ["shopping"],
#     "due_string": "tomorrow"
# }
```

## Task Filters

Todoist supports powerful filter queries:

### Date Filters
- `today` - Tasks due today
- `tomorrow` - Tasks due tomorrow
- `overdue` - Overdue tasks
- `no date` - Tasks without due date
- `7 days` - Tasks due in next 7 days

### Priority Filters
- `p1` - Priority 1 tasks
- `p2` - Priority 2 tasks
- `p3` - Priority 3 tasks
- `p4` - Priority 4 tasks (highest)

### Label Filters
- `@work` - Tasks with "work" label
- `@urgent` - Tasks with "urgent" label

### Combined Filters
- `today & p1` - Priority 1 tasks due today
- `overdue | today` - Overdue or due today
- `@work & !@waiting` - Work tasks not waiting

## Priority Levels

Todoist uses a 1-4 priority system:

| Priority | Value | Color | Description |
|----------|-------|-------|-------------|
| P4 | 4 | 🔴 Red | Highest priority |
| P3 | 3 | 🟡 Orange | High priority |
| P2 | 2 | 🔵 Blue | Medium priority |
| P1 | 1 | ⚪ White | Normal priority (default) |

## Due Dates

### Natural Language

Todoist supports natural language due dates:
- `today`
- `tomorrow`
- `next Monday`
- `next week`
- `Jan 15`
- `15th`
- `in 3 days`

### Specific Dates

Use YYYY-MM-DD format:
- `2025-01-20`
- `2025-12-31`

### Recurring Tasks

- `every day`
- `every Monday`
- `every 2 weeks`
- `every month`
- `every year`

## Error Handling

All API methods raise exceptions on errors. Wrap calls in try-except blocks:

```python
try:
    task = svc.todoist.create_task("My Task")
    print(f"Created: {task['id']}")
except Exception as e:
    print(f"Error: {e}")
```

## Security

- OAuth2 flow with state verification (CSRF protection)
- Access tokens stored in `~/.robodog/todoist_token.json`
- File created with user-only permissions
- HTTPS-only communication
- Client secret never exposed in logs

## Scopes

The integration requests the following OAuth scopes:

- **data:read_write**: Read and write access to tasks, projects, labels
- **data:delete**: Delete tasks and projects
- **project:delete**: Delete projects

## Limitations

- OAuth requires registered app (client ID and secret)
- API rate limits: 450 requests per 15 minutes
- Maximum 300 active projects per account (free tier)
- Maximum 300 active tasks per project (free tier)
- Premium features require Todoist Premium subscription

## Examples

### Workflow: Daily Task Management

```python
# Authenticate
svc.todoist.authenticate()

# Get today's tasks
tasks = svc.todoist.get_tasks(filter_query="today")
print(f"Today: {len(tasks)} tasks")

# Add a new task
task = svc.todoist.create_task(
    content="Review pull requests",
    due_string="today",
    priority=3,
    labels=["work"]
)

# Complete a task
svc.todoist.close_task(task_id="8765432101")
```

### Workflow: Project Setup

```python
# Create project
project = svc.todoist.create_project(
    name="Website Redesign",
    color="blue",
    is_favorite=True
)
project_id = project['id']

# Create sections
sections = [
    "Planning",
    "Design",
    "Development",
    "Testing",
    "Launch"
]

for i, section_name in enumerate(sections):
    svc.todoist.create_section(
        name=section_name,
        project_id=project_id,
        order=i
    )

# Add initial tasks
tasks = [
    ("Define requirements", 4),
    ("Create wireframes", 3),
    ("Design mockups", 3),
    ("Set up development environment", 2)
]

for content, priority in tasks:
    svc.todoist.create_task(
        content=content,
        project_id=project_id,
        priority=priority
    )
```

### Workflow: Weekly Review

```python
# Get all projects
projects = svc.todoist.get_projects()

for project in projects:
    print(f"\n📁 {project['name']}")
    
    # Get tasks in project
    tasks = svc.todoist.get_tasks(project_id=project['id'])
    
    # Count by priority
    priority_counts = {1: 0, 2: 0, 3: 0, 4: 0}
    for task in tasks:
        priority_counts[task.get('priority', 1)] += 1
    
    print(f"   Total: {len(tasks)} tasks")
    print(f"   🔴 P4: {priority_counts[4]}")
    print(f"   🟡 P3: {priority_counts[3]}")
    print(f"   🔵 P2: {priority_counts[2]}")
    print(f"   ⚪ P1: {priority_counts[1]}")
```

## Integration with Robodog Features

### AI-Generated Tasks

Use Robodog's AI to generate task lists:

```
# Ask AI
Break down "Build landing page" into subtasks

# AI generates list, then create tasks
/todoist create Design hero section p3
/todoist create Implement responsive layout p2
/todoist create Add contact form p2
/todoist create Optimize images p1
```

### Sync with Robodog Todos

Create a script to sync Robodog todos with Todoist:

```python
# Get Robodog todos
robodog_todos = svc.todo.get_tasks()

# Create corresponding Todoist tasks
for todo in robodog_todos:
    if not todo.get('synced_to_todoist'):
        task = svc.todoist.create_task(
            content=todo['desc'],
            priority=3 if 'urgent' in todo['desc'].lower() else 1
        )
        # Mark as synced
        todo['todoist_id'] = task['id']
        todo['synced_to_todoist'] = True
```

## Troubleshooting

### Authentication Fails

- Verify client ID and secret in config.yaml
- Ensure redirect URI is exactly `http://localhost:8080`
- Check that you're copying the complete redirect URL
- Try using a different browser

### API Errors

- Check rate limits (450 requests per 15 minutes)
- Verify task/project IDs are correct
- Ensure you have necessary permissions
- Review API response for specific error messages

### Token Expired

Tokens don't expire, but can be revoked. Re-authenticate:
```
/todoist logout
/todoist auth
```

## Resources

- [Todoist REST API Documentation](https://developer.todoist.com/rest/v2/)
- [Todoist OAuth Guide](https://developer.todoist.com/guides/#oauth)
- [Todoist App Console](https://developer.todoist.com/appconsole.html)
- [Todoist Help Center](https://todoist.com/help)

## Support

For issues specific to the Robodog integration:
- Check the logs in `robodog.log`
- Enable debug logging: `logging.getLogger('robodog.todoist').setLevel(logging.DEBUG)`
- Report issues on the Robodog GitHub repository

## API Coverage

Implemented endpoints from Todoist REST API v2:

| Resource | Endpoints | Status |
|----------|-----------|--------|
| Projects | GET, POST, GET/:id, POST/:id, DELETE/:id | ✅ Complete |
| Tasks | GET, POST, GET/:id, POST/:id, POST/:id/close, POST/:id/reopen, DELETE/:id | ✅ Complete |
| Sections | GET, POST, GET/:id, POST/:id, DELETE/:id | ✅ Complete |
| Labels | GET, POST, GET/:id, POST/:id, DELETE/:id | ✅ Complete |
| Comments | GET, POST, GET/:id, POST/:id, DELETE/:id | ✅ Complete |

## Version History

### v1.0.0 - November 13, 2025
- Initial implementation
- OAuth2 authentication with state verification
- Full CRUD operations for projects, tasks, sections, labels, comments
- Natural language task creation (Quick Add)
- CLI commands
- Comprehensive documentation
