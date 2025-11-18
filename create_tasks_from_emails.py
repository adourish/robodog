"""
Analyze emails and create Todoist tasks or Calendar events for actionable items
"""

import json
import requests
import re
from datetime import datetime, timedelta

MCP_URL = "http://localhost:2500"
TOKEN = "testtoken"


def call_mcp(operation, payload):
    """Call MCP operation"""
    body = f"{operation} {json.dumps(payload)}"
    response = requests.post(
        MCP_URL,
        headers={
            "Authorization": f"Bearer {TOKEN}",
            "Content-Type": "text/plain"
        },
        data=body,
        timeout=30
    )
    return response.json()


def load_emails():
    """Load emails from JSON file"""
    try:
        with open('last_100_emails.json', 'r', encoding='utf-8') as f:
            return json.load(f)
    except FileNotFoundError:
        print("❌ Email file not found. Run get_my_emails.py first.")
        return []


def get_existing_tasks():
    """Get all existing Todoist tasks"""
    result = call_mcp("TODOIST_TASKS", {})
    if result.get("status") == "ok":
        return result.get("tasks", [])
    return []


def extract_actionable_items(emails):
    """Extract actionable items from emails"""
    actionable = []
    
    # Keywords that indicate action items
    action_keywords = [
        'pay', 'payment', 'due', 'bill', 'invoice', 'reminder',
        'field trip', 'rsvp', 'register', 'confirm', 'booking',
        'appointment', 'meeting', 'deadline', 'expires', 'renew'
    ]
    
    for email in emails:
        subject = email.get('subject', '').lower()
        from_addr = email.get('from', '').lower()
        
        # Check for action keywords
        has_action = any(keyword in subject for keyword in action_keywords)
        
        if has_action:
            # Determine type and priority
            item = {
                'email_id': email.get('id'),
                'subject': email.get('subject'),
                'from': email.get('from'),
                'date': email.get('date'),
                'type': 'task',  # Default to task
                'priority': 1
            }
            
            # Categorize
            if 'pay' in subject or 'bill' in subject or 'invoice' in subject:
                item['category'] = 'Bills'
                item['priority'] = 3  # High priority
                item['task_content'] = f"Pay: {email.get('subject')}"
                
            elif 'field trip' in subject or 'rsvp' in subject:
                item['category'] = 'Personal'
                item['priority'] = 2
                item['task_content'] = f"RSVP/Action: {email.get('subject')}"
                item['type'] = 'event'  # Could be calendar event
                
            elif 'appointment' in subject or 'meeting' in subject:
                item['category'] = 'Appointments'
                item['priority'] = 2
                item['task_content'] = f"Schedule: {email.get('subject')}"
                item['type'] = 'event'
                
            elif 'expires' in subject or 'renew' in subject:
                item['category'] = 'Renewals'
                item['priority'] = 2
                item['task_content'] = f"Renew: {email.get('subject')}"
                
            else:
                item['category'] = 'Action Items'
                item['priority'] = 1
                item['task_content'] = f"Review: {email.get('subject')}"
            
            actionable.append(item)
    
    return actionable


def task_exists(task_content, existing_tasks):
    """Check if a similar task already exists"""
    # Normalize for comparison
    normalized_new = task_content.lower().strip()
    
    for task in existing_tasks:
        existing_content = task.get('content', '').lower().strip()
        
        # Check for exact match or very similar
        if normalized_new == existing_content:
            return True
        
        # Check if key parts match (fuzzy matching)
        new_words = set(normalized_new.split())
        existing_words = set(existing_content.split())
        
        # If 70% of words match, consider it a duplicate
        if len(new_words) > 0:
            overlap = len(new_words & existing_words) / len(new_words)
            if overlap > 0.7:
                return True
    
    return False


def create_todoist_task(item, project_id):
    """Create a Todoist task"""
    payload = {
        "content": item['task_content'],
        "project_id": project_id,
        "priority": item['priority']
    }
    
    # Add due date if it's high priority
    if item['priority'] >= 3:
        payload['due_string'] = 'today'
    
    result = call_mcp("TODOIST_CREATE", payload)
    return result


def main():
    print("\n" + "="*70)
    print("CREATE TASKS FROM EMAILS")
    print("="*70)
    
    # Load emails
    print("\n📧 Loading emails...")
    emails = load_emails()
    if not emails:
        return
    
    print(f"✅ Loaded {len(emails)} emails")
    
    # Get existing tasks
    print("\n📋 Getting existing Todoist tasks...")
    existing_tasks = get_existing_tasks()
    print(f"✅ Found {len(existing_tasks)} existing tasks")
    
    # Get projects
    print("\n📁 Getting Todoist projects...")
    projects_result = call_mcp("TODOIST_PROJECTS", {})
    projects = projects_result.get("projects", [])
    
    # Find or use default project (Inbox)
    inbox_project = next((p for p in projects if p.get('is_inbox_project')), None)
    todo_project = next((p for p in projects if p.get('name') == 'Todo'), None)
    
    default_project_id = (todo_project or inbox_project or projects[0]).get('id')
    print(f"✅ Using project: {(todo_project or inbox_project or projects[0]).get('name')}")
    
    # Extract actionable items
    print("\n🔍 Analyzing emails for actionable items...")
    actionable_items = extract_actionable_items(emails)
    print(f"✅ Found {len(actionable_items)} actionable items")
    
    # Create tasks for new items
    print("\n" + "="*70)
    print("CREATING NEW TASKS")
    print("="*70)
    
    created_count = 0
    skipped_count = 0
    
    for item in actionable_items:
        task_content = item['task_content']
        
        # Check if task already exists
        if task_exists(task_content, existing_tasks):
            print(f"\n⏭️  SKIPPED (already exists): {task_content[:60]}...")
            skipped_count += 1
            continue
        
        # Create the task
        print(f"\n➕ CREATING: {task_content}")
        print(f"   Category: {item['category']}")
        print(f"   Priority: {item['priority']}")
        print(f"   From: {item['from'][:50]}...")
        
        result = create_todoist_task(item, default_project_id)
        
        if result.get("status") == "ok":
            task = result.get("task", {})
            print(f"   ✅ Created task ID: {task.get('id')}")
            created_count += 1
            
            # Add to existing tasks to avoid duplicates in this run
            existing_tasks.append({"content": task_content})
        else:
            print(f"   ❌ Failed: {result.get('error')}")
    
    # Summary
    print("\n" + "="*70)
    print("SUMMARY")
    print("="*70)
    print(f"✅ Created: {created_count} new tasks")
    print(f"⏭️  Skipped: {skipped_count} existing tasks")
    print(f"📧 Analyzed: {len(emails)} emails")
    print(f"🎯 Actionable: {len(actionable_items)} items found")
    
    if created_count > 0:
        print(f"\n🎉 Successfully created {created_count} new tasks in Todoist!")
        print(f"\nView them at: https://app.todoist.com/")
    else:
        print(f"\n✅ All actionable items already have tasks!")
    
    return created_count > 0


if __name__ == '__main__':
    success = main()
