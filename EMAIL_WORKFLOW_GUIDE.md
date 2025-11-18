# Email Automation Workflow Guide

## Overview

Automated workflow that checks your last 100 emails and creates appropriate Todoist tasks and Google Calendar events.

---

## Features

### ✅ Automatic Email Analysis
- Fetches last 100 emails from Gmail
- Analyzes subject lines and labels
- Categorizes emails by type
- Filters out promotional spam

### 📋 Smart Task Creation
- Creates Todoist tasks for:
  - **Bills/Payments** (High Priority)
  - **Action Items** (Medium Priority)
  - **Personal Items** (Normal Priority)
- Avoids duplicates automatically
- Sets appropriate priorities and due dates

### 📅 Calendar Event Creation
- Creates events for:
  - Meetings and appointments
  - Field trips and RSVPs
  - Webinars and invitations
- Sets placeholder dates (1 week out)
- Includes email details in description

### 🔄 Duplicate Prevention
- Checks existing tasks before creating
- Checks existing events before creating
- Uses fuzzy matching (70% word overlap)
- Skips promotional emails

---

## Quick Start

### Run Once
```bash
# Set your Google client secret
$env:GOOGLE_CLIENT_SECRET="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"

# Run the workflow
python email_automation_workflow.py
```

### Run on Schedule
```bash
# Interactive scheduler
python schedule_email_workflow.py

# Options:
# 1. Run once now
# 2. Run every hour
# 3. Run every 6 hours
# 4. Run daily at 9 AM
# 5. Run daily at 6 PM
# 6. Custom schedule
```

---

## What Gets Created

### Tasks Created For:

**High Priority (🟡 - Due Today):**
- Emails with: "pay", "payment", "bill", "invoice", "due", "statement"
- Examples:
  - "Pay: Verizon bill"
  - "Pay: Credit card statement"
  - "Pay: Mortgage due"

**Medium Priority (🔵):**
- Emails with: "confirm", "register", "renew", "expires", "reminder", "deadline"
- Examples:
  - "Action: Confirm appointment"
  - "Renew: License expires soon"
  - "Reminder: Registration deadline"

**Normal Priority (⚪):**
- Personal emails (not promotions)
- Examples:
  - "Review: Message from friend"
  - "Review: Family update"

### Events Created For:

**Calendar Events:**
- Emails with: "meeting", "appointment", "field trip", "rsvp", "invitation", "webinar"
- Examples:
  - "Field Trip Information"
  - "Team Meeting - Q4 Review"
  - "Doctor Appointment Confirmation"

### Skipped:

**Not Created:**
- Promotional emails (unless they contain bill keywords)
- Social media notifications
- Duplicate items
- Generic newsletters

---

## Workflow Steps

### 1. Authentication
```
🔐 Authenticating with Google...
✅ Google authentication successful
```

### 2. Fetch Emails
```
📧 Fetching last 100 emails...
   Found 100 emails, fetching details...
   Processed 25/100 emails...
   Processed 50/100 emails...
   Processed 75/100 emails...
   Processed 100/100 emails...
✅ Fetched 100 emails
```

### 3. Load Existing Data
```
📋 Loading existing tasks and events...
   ✅ Loaded 18 Todoist tasks
   ✅ Loaded 20 calendar events
```

### 4. Analyze & Create
```
🔍 Analyzing emails...
   ✅ Found 12 potential tasks
   ✅ Found 3 potential events

➕ Creating tasks...
   ✅ Created: Pay: Verizon bill...
   ✅ Created: Action: Confirm appointment...
   ⏭️  Skipped: Pay: Mortgage (already exists)

📅 Creating calendar events...
   ✅ Created: Field Trip Information...
   ⏭️  Skipped: Team Meeting (already exists)
```

### 5. Generate Report
```
==================================================================
WORKFLOW SUMMARY
==================================================================

📧 Emails Processed: 100
✅ Tasks Created: 9
📅 Events Created: 2
⏭️  Items Skipped: 8

📋 New Tasks by Category:
   - Bills: 5
   - Action Items: 3
   - Personal: 1

📅 New Events:
   - Field Trip Information
   - Doctor Appointment

💾 Report saved to: workflow_report.json
```

---

## Output Files

### `last_100_emails.json`
Complete email data with:
- Email ID and thread ID
- From, to, subject
- Date and labels
- Used for analysis

### `workflow_report.json`
Workflow results:
```json
{
  "timestamp": "2025-11-17T21:30:00",
  "emails_processed": 100,
  "tasks_created": 9,
  "events_created": 2,
  "items_skipped": 8,
  "created_tasks": [...],
  "created_events": [...]
}
```

---

## Customization

### Adjust Email Count
Edit `email_automation_workflow.py`:
```python
EMAIL_COUNT = 100  # Change to 50, 200, etc.
```

### Modify Keywords
Edit the `analyze_email` method:
```python
bill_keywords = ['pay', 'payment', 'bill', 'invoice', 'due']
event_keywords = ['meeting', 'appointment', 'field trip']
action_keywords = ['confirm', 'register', 'renew']
```

### Change Priorities
Edit the `analyze_email` method:
```python
if any(kw in subject for kw in bill_keywords):
    priority = 3  # Change to 1, 2, 3, or 4
```

### Adjust Event Timing
Edit the `create_event` method:
```python
event_date = datetime.now() + timedelta(days=7)  # Change days
start_time = event_date.replace(hour=9, minute=0)  # Change time
```

---

## Scheduling Options

### Windows Task Scheduler
1. Open Task Scheduler
2. Create Basic Task
3. Set trigger (daily, weekly, etc.)
4. Action: Start a program
5. Program: `python`
6. Arguments: `C:\Projects\robodog\email_automation_workflow.py`
7. Start in: `C:\Projects\robodog`

### Using Python Scheduler
```bash
python schedule_email_workflow.py
```

Options:
- **Every hour** - Good for active monitoring
- **Every 6 hours** - Balanced approach
- **Daily at 9 AM** - Morning review
- **Daily at 6 PM** - Evening review

---

## Troubleshooting

### "GOOGLE_CLIENT_SECRET not set"
```bash
$env:GOOGLE_CLIENT_SECRET="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"
```

### "Authentication failed"
- Browser should open automatically
- Complete OAuth flow
- Token is saved for future use

### "Gmail API has not been used"
Enable at: https://console.developers.google.com/apis/api/gmail.googleapis.com/overview?project=837032747486

### "Calendar API has not been used"
Enable at: https://console.developers.google.com/apis/api/calendar-json.googleapis.com/overview?project=837032747486

### "MCP server not running"
```bash
cd C:\Projects\robodog\robodogcli
python -m robodog.cli --folders c:\projects\robodog\robodogcli --port 2500 --token testtoken --config config.yaml
```

---

## Best Practices

### 1. Run Regularly
- Daily or twice daily for best results
- Catches time-sensitive items quickly
- Prevents inbox overload

### 2. Review Created Items
- Check Todoist for new tasks
- Update calendar events with actual dates
- Mark completed items

### 3. Adjust Keywords
- Add keywords for your specific needs
- Remove keywords that create noise
- Fine-tune priorities

### 4. Monitor Reports
- Check `workflow_report.json`
- Track what's being created
- Identify patterns

### 5. Clean Up
- Archive old emails
- Complete old tasks
- Remove past events

---

## Integration with MCP

The workflow uses MCP operations:
- `TODOIST_TASKS` - Get existing tasks
- `TODOIST_CREATE` - Create new tasks
- `TODOIST_PROJECTS` - Get project IDs
- `GEVENT_LIST` - Get existing events
- `GEVENT_CREATE` - Create new events

All operations go through the MCP server at `http://localhost:2500`

---

## Example Output

```
==================================================================
EMAIL AUTOMATION WORKFLOW
==================================================================
Processing last 100 emails...

🔐 Authenticating with Google...
✅ Google authentication successful

📧 Fetching last 100 emails...
   Found 100 emails, fetching details...
   Processed 100/100 emails...
✅ Fetched 100 emails

📋 Loading existing tasks and events...
   ✅ Loaded 18 Todoist tasks
   ✅ Loaded 20 calendar events

🔍 Analyzing emails...
   ✅ Found 12 potential tasks
   ✅ Found 3 potential events

➕ Creating tasks...
   ✅ Created: Pay: Verizon bill...
   ✅ Created: Pay: Credit card statement...
   ✅ Created: Action: Confirm appointment...
   ✅ Created: Renew: License expires...

📅 Creating calendar events...
   ✅ Created: Field Trip Information...
   ✅ Created: Doctor Appointment...

==================================================================
WORKFLOW SUMMARY
==================================================================

📧 Emails Processed: 100
✅ Tasks Created: 9
📅 Events Created: 2
⏭️  Items Skipped: 8

💾 Report saved to: workflow_report.json

==================================================================
✅ WORKFLOW COMPLETE!
==================================================================

🎉 Successfully processed 100 emails!
   Created 9 tasks
   Created 2 events

📱 View your updates:
   Todoist: https://app.todoist.com/
   Calendar: https://calendar.google.com/
```

---

## Files

- **`email_automation_workflow.py`** - Main workflow script
- **`schedule_email_workflow.py`** - Scheduler for automated runs
- **`EMAIL_WORKFLOW_GUIDE.md`** - This guide
- **`last_100_emails.json`** - Email data (generated)
- **`workflow_report.json`** - Workflow results (generated)

---

## Next Steps

1. **Run the workflow** once to test
2. **Review created items** in Todoist and Calendar
3. **Adjust keywords** if needed
4. **Set up scheduling** for automatic runs
5. **Monitor results** and fine-tune

---

**🎉 Automate your email inbox and never miss important tasks or events!**
