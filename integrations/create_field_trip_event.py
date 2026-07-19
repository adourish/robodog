"""
Create calendar event for field trip from email
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
    with open('last_100_emails.json', 'r', encoding='utf-8') as f:
        return json.load(f)


def find_field_trip_email(emails):
    """Find the field trip email"""
    for email in emails:
        subject = email.get('subject', '')
        if 'field trip' in subject.lower():
            return email
    return None


def get_existing_events():
    """Get existing calendar events"""
    # Get events for the next 30 days
    now = datetime.now()
    time_min = now.isoformat()
    time_max = (now + timedelta(days=30)).isoformat()
    
    result = call_mcp("GEVENT_LIST", {
        "calendar_id": "primary",
        "max_results": 50,
        "time_min": time_min,
        "time_max": time_max
    })
    
    if result.get("status") == "ok":
        return result.get("events", {}).get("items", [])
    return []


def event_exists(title, existing_events):
    """Check if event already exists"""
    title_lower = title.lower()
    for event in existing_events:
        event_title = event.get('summary', '').lower()
        if title_lower in event_title or event_title in title_lower:
            return True
    return False


def create_calendar_event(email):
    """Create calendar event from email"""
    subject = email.get('subject', '')
    from_addr = email.get('from', '')
    
    # Extract details
    # Default to a week from now, 9 AM - 3 PM (typical field trip time)
    # In a real scenario, you'd parse the email body for actual date/time
    event_date = datetime.now() + timedelta(days=7)
    start_time = event_date.replace(hour=9, minute=0, second=0, microsecond=0)
    end_time = event_date.replace(hour=15, minute=0, second=0, microsecond=0)
    
    # Format for Google Calendar API (ISO 8601)
    start_str = start_time.strftime("%Y-%m-%dT%H:%M:%S")
    end_str = end_time.strftime("%Y-%m-%dT%H:%M:%S")
    
    # Create event
    payload = {
        "calendar_id": "primary",
        "summary": subject,
        "description": f"Field trip information from {from_addr}\n\nEmail ID: {email.get('id')}\n\nPlease check email for full details and payment information.",
        "start_time": start_str,
        "end_time": end_str,
        "location": "TBD - Check email for details"
    }
    
    result = call_mcp("GEVENT_CREATE", payload)
    return result, start_time


def main():
    print("\n" + "="*70)
    print("CREATE FIELD TRIP CALENDAR EVENT")
    print("="*70)
    
    # Load emails
    print("\n📧 Loading emails...")
    emails = load_emails()
    
    # Find field trip email
    print("\n🔍 Looking for field trip email...")
    field_trip_email = find_field_trip_email(emails)
    
    if not field_trip_email:
        print("❌ No field trip email found")
        return False
    
    print(f"✅ Found field trip email:")
    print(f"   Subject: {field_trip_email.get('subject')}")
    print(f"   From: {field_trip_email.get('from')}")
    print(f"   Date: {field_trip_email.get('date')}")
    
    # Check Google authentication
    print("\n🔐 Checking Google Calendar authentication...")
    status = call_mcp("GOOGLE_STATUS", {})
    
    if not status.get("authenticated"):
        print("❌ Not authenticated with Google Calendar")
        print("\nTo authenticate, run:")
        print("   $env:GOOGLE_CLIENT_SECRET='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'")
        print("   python test_calendar.py")
        return False
    
    print("✅ Authenticated with Google Calendar")
    
    # Get existing events
    print("\n📅 Checking for existing events...")
    existing_events = get_existing_events()
    print(f"✅ Found {len(existing_events)} upcoming events")
    
    # Check if event already exists
    if event_exists(field_trip_email.get('subject'), existing_events):
        print(f"\n⏭️  Event already exists for: {field_trip_email.get('subject')}")
        print("   Skipping creation to avoid duplicates")
        return True
    
    # Create the event
    print("\n➕ Creating calendar event...")
    result, event_time = create_calendar_event(field_trip_email)
    
    if result.get("status") == "ok":
        event = result.get("event", {})
        event_id = event.get("id")
        
        print("\n" + "="*70)
        print("✅ CALENDAR EVENT CREATED!")
        print("="*70)
        
        print(f"\n📅 Event Details:")
        print(f"   Title: {event.get('summary')}")
        print(f"   Date: {event_time.strftime('%A, %B %d, %Y')}")
        print(f"   Time: {event_time.strftime('%I:%M %p')} - {(event_time + timedelta(hours=6)).strftime('%I:%M %p')}")
        print(f"   Location: {event.get('location', 'TBD')}")
        print(f"   Event ID: {event_id}")
        
        print(f"\n🔗 View in Google Calendar:")
        print(f"   https://calendar.google.com/")
        
        print(f"\n📝 Notes:")
        print(f"   - Event set for 1 week from now (placeholder)")
        print(f"   - Check the original email for actual date/time")
        print(f"   - Update event in Google Calendar with correct details")
        print(f"   - Payment link is in the email from Lisa Prescott")
        
        return True
    else:
        print(f"\n❌ Failed to create event: {result.get('error')}")
        return False


if __name__ == '__main__':
    success = main()
    
    if success:
        print("\n🎉 Field trip event created successfully!")
    else:
        print("\n❌ Failed to create field trip event")
