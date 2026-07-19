"""
Email Automation Workflow
Automatically check last 100 emails and create appropriate Todoist tasks and Calendar events
"""

import os
import sys
import json
import requests
import re
from datetime import datetime, timedelta
from typing import List, Dict, Tuple

# Add robodogcli to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'robodogcli'))

from robodog.google_service import GoogleService

# Configuration
MCP_URL = "http://localhost:2500"
TOKEN = "testtoken"
EMAIL_COUNT = 100


class EmailAutomationWorkflow:
    """Automated workflow for processing emails into tasks and events"""
    
    def __init__(self):
        self.google_service = None
        self.emails = []
        self.existing_tasks = []
        self.existing_events = []
        self.created_tasks = []
        self.created_events = []
        self.skipped_items = []
        
    def call_mcp(self, operation: str, payload: dict) -> dict:
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
    
    def authenticate_google(self) -> bool:
        """Authenticate with Google services"""
        print("\n🔐 Authenticating with Google...")
        
        client_secret = os.getenv('GOOGLE_CLIENT_SECRET')
        if not client_secret:
            print("❌ GOOGLE_CLIENT_SECRET not set!")
            print("\nRun: $env:GOOGLE_CLIENT_SECRET='YOUR_SECRET'")
            return False
        
        try:
            self.google_service = GoogleService()
            self.google_service.client_secret = client_secret
            self.google_service.authenticate()
            print("✅ Google authentication successful")
            return True
        except Exception as e:
            print(f"❌ Authentication failed: {e}")
            return False
    
    def fetch_emails(self) -> bool:
        """Fetch last 100 emails from Gmail"""
        print(f"\n📧 Fetching last {EMAIL_COUNT} emails...")
        
        try:
            result = self.google_service.list_emails(max_results=EMAIL_COUNT, query='')
            messages = result.get('messages', [])
            
            print(f"   Found {len(messages)} emails, fetching details...")
            
            for i, msg in enumerate(messages, 1):
                msg_id = msg['id']
                email = self.google_service.get_email(msg_id)
                
                # Extract headers
                headers = {h['name']: h['value'] 
                          for h in email.get('payload', {}).get('headers', [])}
                
                self.emails.append({
                    'id': msg_id,
                    'thread_id': email.get('threadId'),
                    'from': headers.get('From', 'Unknown'),
                    'to': headers.get('To', 'Unknown'),
                    'subject': headers.get('Subject', 'No Subject'),
                    'date': headers.get('Date', 'Unknown'),
                    'labels': email.get('labelIds', [])
                })
                
                if i % 25 == 0:
                    print(f"   Processed {i}/{len(messages)} emails...")
            
            print(f"✅ Fetched {len(self.emails)} emails")
            
            # Save to file
            with open('last_100_emails.json', 'w', encoding='utf-8') as f:
                json.dump(self.emails, f, indent=2, ensure_ascii=False)
            
            return True
            
        except Exception as e:
            print(f"❌ Failed to fetch emails: {e}")
            return False
    
    def load_existing_data(self) -> bool:
        """Load existing tasks and events"""
        print("\n📋 Loading existing tasks and events...")
        
        # Get Todoist tasks
        try:
            result = self.call_mcp("TODOIST_TASKS", {})
            if result.get("status") == "ok":
                self.existing_tasks = result.get("tasks", [])
                print(f"   ✅ Loaded {len(self.existing_tasks)} Todoist tasks")
        except Exception as e:
            print(f"   ⚠️  Could not load Todoist tasks: {e}")
        
        # Get Calendar events
        try:
            now = datetime.now()
            time_min = now.isoformat() + 'Z'
            time_max = (now + timedelta(days=60)).isoformat() + 'Z'
            
            events_result = self.google_service.list_events(
                calendar_id='primary',
                max_results=100,
                time_min=time_min,
                time_max=time_max
            )
            
            self.existing_events = events_result.get('items', [])
            print(f"   ✅ Loaded {len(self.existing_events)} calendar events")
            
        except Exception as e:
            print(f"   ⚠️  Could not load calendar events: {e}")
        
        return True
    
    def analyze_email(self, email: dict) -> Tuple[str, dict]:
        """
        Analyze email and determine if it needs a task or event
        Returns: (type, details) where type is 'task', 'event', or 'none'
        """
        subject = email.get('subject', '').lower()
        from_addr = email.get('from', '').lower()
        
        # Keywords for different categories
        bill_keywords = ['pay', 'payment', 'bill', 'invoice', 'due', 'statement']
        event_keywords = ['meeting', 'appointment', 'field trip', 'rsvp', 'invitation', 'webinar']
        action_keywords = ['confirm', 'register', 'renew', 'expires', 'reminder', 'deadline']
        
        # Skip promotional/social emails
        labels = email.get('labels', [])
        if 'CATEGORY_PROMOTIONS' in labels and not any(kw in subject for kw in bill_keywords):
            return 'none', {}
        
        # Determine type
        item_type = 'none'
        priority = 1
        category = 'General'
        
        # Check for bills/payments (high priority tasks)
        if any(kw in subject for kw in bill_keywords):
            item_type = 'task'
            priority = 3
            category = 'Bills'
            content = f"Pay: {email.get('subject')}"
        
        # Check for events
        elif any(kw in subject for kw in event_keywords):
            item_type = 'event'
            priority = 2
            category = 'Events'
            content = email.get('subject')
        
        # Check for action items
        elif any(kw in subject for kw in action_keywords):
            item_type = 'task'
            priority = 2
            category = 'Action Items'
            content = f"Action: {email.get('subject')}"
        
        # Check for personal emails (not promotions)
        elif 'CATEGORY_PERSONAL' in labels:
            item_type = 'task'
            priority = 1
            category = 'Personal'
            content = f"Review: {email.get('subject')}"
        
        if item_type == 'none':
            return 'none', {}
        
        return item_type, {
            'email_id': email.get('id'),
            'subject': email.get('subject'),
            'from': email.get('from'),
            'date': email.get('date'),
            'category': category,
            'priority': priority,
            'content': content
        }
    
    def task_exists(self, content: str) -> bool:
        """Check if task already exists"""
        normalized = content.lower().strip()
        
        for task in self.existing_tasks:
            existing = task.get('content', '').lower().strip()
            
            if normalized == existing:
                return True
            
            # Fuzzy match (70% word overlap)
            new_words = set(normalized.split())
            existing_words = set(existing.split())
            
            if len(new_words) > 0:
                overlap = len(new_words & existing_words) / len(new_words)
                if overlap > 0.7:
                    return True
        
        return False
    
    def event_exists(self, title: str) -> bool:
        """Check if calendar event already exists"""
        title_lower = title.lower()
        
        for event in self.existing_events:
            event_title = event.get('summary', '').lower()
            if title_lower in event_title or event_title in title_lower:
                return True
        
        return False
    
    def create_task(self, item: dict, project_id: str) -> bool:
        """Create Todoist task"""
        payload = {
            "content": item['content'],
            "project_id": project_id,
            "priority": item['priority']
        }
        
        if item['priority'] >= 3:
            payload['due_string'] = 'today'
        
        result = self.call_mcp("TODOIST_CREATE", payload)
        
        if result.get("status") == "ok":
            task = result.get("task", {})
            self.created_tasks.append({
                'id': task.get('id'),
                'content': item['content'],
                'category': item['category']
            })
            return True
        
        return False
    
    def create_event(self, item: dict) -> bool:
        """Create calendar event"""
        # Default to 1 week from now, 9 AM - 3 PM
        event_date = datetime.now() + timedelta(days=7)
        start_time = event_date.replace(hour=9, minute=0, second=0, microsecond=0)
        end_time = event_date.replace(hour=15, minute=0, second=0, microsecond=0)
        
        start_str = start_time.strftime("%Y-%m-%dT%H:%M:%S")
        end_str = end_time.strftime("%Y-%m-%dT%H:%M:%S")
        
        try:
            event = self.google_service.create_event(
                calendar_id='primary',
                summary=item['subject'],
                description=f"From: {item['from']}\n"
                           f"Email ID: {item['email_id']}\n"
                           f"Date received: {item['date']}\n\n"
                           f"⚠️ Check original email for actual date/time and details.",
                start_time=start_str,
                end_time=end_str,
                location="TBD - Check email"
            )
            
            self.created_events.append({
                'id': event.get('id'),
                'title': item['subject'],
                'category': item['category']
            })
            return True
            
        except Exception as e:
            print(f"   ❌ Failed to create event: {e}")
            return False
    
    def process_emails(self) -> bool:
        """Process all emails and create tasks/events"""
        print("\n🔍 Analyzing emails...")
        
        # Get Todoist project
        projects_result = self.call_mcp("TODOIST_PROJECTS", {})
        projects = projects_result.get("projects", [])
        todo_project = next((p for p in projects if p.get('name') == 'Todo'), None)
        inbox_project = next((p for p in projects if p.get('is_inbox_project')), None)
        default_project_id = (todo_project or inbox_project or projects[0]).get('id')
        
        tasks_to_create = []
        events_to_create = []
        
        # Analyze each email
        for email in self.emails:
            item_type, details = self.analyze_email(email)
            
            if item_type == 'task':
                tasks_to_create.append(details)
            elif item_type == 'event':
                events_to_create.append(details)
        
        print(f"   ✅ Found {len(tasks_to_create)} potential tasks")
        print(f"   ✅ Found {len(events_to_create)} potential events")
        
        # Create tasks
        print("\n➕ Creating tasks...")
        for item in tasks_to_create:
            if self.task_exists(item['content']):
                self.skipped_items.append(('task', item['content']))
                continue
            
            if self.create_task(item, default_project_id):
                print(f"   ✅ Created: {item['content'][:60]}...")
            else:
                print(f"   ❌ Failed: {item['content'][:60]}...")
        
        # Create events
        print("\n📅 Creating calendar events...")
        for item in events_to_create:
            if self.event_exists(item['subject']):
                self.skipped_items.append(('event', item['subject']))
                continue
            
            if self.create_event(item):
                print(f"   ✅ Created: {item['subject'][:60]}...")
            else:
                print(f"   ❌ Failed: {item['subject'][:60]}...")
        
        return True
    
    def generate_report(self):
        """Generate workflow report"""
        print("\n" + "="*70)
        print("WORKFLOW SUMMARY")
        print("="*70)
        
        print(f"\n📧 Emails Processed: {len(self.emails)}")
        print(f"✅ Tasks Created: {len(self.created_tasks)}")
        print(f"📅 Events Created: {len(self.created_events)}")
        print(f"⏭️  Items Skipped: {len(self.skipped_items)}")
        
        if self.created_tasks:
            print(f"\n📋 New Tasks by Category:")
            categories = {}
            for task in self.created_tasks:
                cat = task['category']
                categories[cat] = categories.get(cat, 0) + 1
            
            for cat, count in sorted(categories.items()):
                print(f"   - {cat}: {count}")
        
        if self.created_events:
            print(f"\n📅 New Events:")
            for event in self.created_events:
                print(f"   - {event['title'][:60]}...")
        
        # Save report
        report = {
            'timestamp': datetime.now().isoformat(),
            'emails_processed': len(self.emails),
            'tasks_created': len(self.created_tasks),
            'events_created': len(self.created_events),
            'items_skipped': len(self.skipped_items),
            'created_tasks': self.created_tasks,
            'created_events': self.created_events
        }
        
        with open('workflow_report.json', 'w', encoding='utf-8') as f:
            json.dump(report, f, indent=2)
        
        print(f"\n💾 Report saved to: workflow_report.json")
    
    def run(self):
        """Run the complete workflow"""
        print("="*70)
        print("EMAIL AUTOMATION WORKFLOW")
        print("="*70)
        print(f"Processing last {EMAIL_COUNT} emails...")
        
        # Step 1: Authenticate
        if not self.authenticate_google():
            return False
        
        # Step 2: Fetch emails
        if not self.fetch_emails():
            return False
        
        # Step 3: Load existing data
        if not self.load_existing_data():
            return False
        
        # Step 4: Process emails
        if not self.process_emails():
            return False
        
        # Step 5: Generate report
        self.generate_report()
        
        print("\n" + "="*70)
        print("✅ WORKFLOW COMPLETE!")
        print("="*70)
        
        print(f"\n🎉 Successfully processed {len(self.emails)} emails!")
        print(f"   Created {len(self.created_tasks)} tasks")
        print(f"   Created {len(self.created_events)} events")
        
        if len(self.created_tasks) > 0 or len(self.created_events) > 0:
            print(f"\n📱 View your updates:")
            print(f"   Todoist: https://app.todoist.com/")
            print(f"   Calendar: https://calendar.google.com/")
        
        return True


def main():
    """Main entry point"""
    workflow = EmailAutomationWorkflow()
    success = workflow.run()
    
    if not success:
        print("\n❌ Workflow failed. See errors above.")
        return 1
    
    return 0


if __name__ == '__main__':
    exit(main())
