"""
Create field trip calendar event directly with Google service
"""

import os
import sys
import json
from datetime import datetime, timedelta

# Add robodogcli to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'robodogcli'))

from robodog.google_service import GoogleService


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


def main():
    print("=" * 70)
    print("CREATE FIELD TRIP CALENDAR EVENT")
    print("=" * 70)
    
    # Check for client secret
    client_secret = os.getenv('GOOGLE_CLIENT_SECRET')
    if not client_secret:
        print("\n❌ GOOGLE_CLIENT_SECRET not set!")
        print("\nRun: $env:GOOGLE_CLIENT_SECRET='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'")
        return
    
    print(f"\n✅ Client secret found")
    
    # Load emails
    print("\n📧 Loading emails...")
    emails = load_emails()
    
    # Find field trip email
    print("\n🔍 Looking for field trip email...")
    field_trip_email = find_field_trip_email(emails)
    
    if not field_trip_email:
        print("❌ No field trip email found")
        return
    
    print(f"✅ Found field trip email:")
    print(f"   Subject: {field_trip_email.get('subject')}")
    print(f"   From: {field_trip_email.get('from')}")
    
    # Initialize Google service
    print("\n📝 Initializing Google service...")
    service = GoogleService()
    service.client_secret = client_secret
    
    # Authenticate (will reuse existing token if available)
    print("\n🔐 Authenticating...")
    try:
        service.authenticate()
        print("✅ Authentication successful!")
    except Exception as e:
        print(f"❌ Authentication failed: {e}")
        return
    
    # Check existing events
    print("\n📅 Checking for existing events...")
    try:
        now = datetime.now()
        time_min = now.isoformat() + 'Z'
        time_max = (now + timedelta(days=30)).isoformat() + 'Z'
        
        events_result = service.list_events(
            calendar_id='primary',
            max_results=50,
            time_min=time_min,
            time_max=time_max
        )
        
        existing_events = events_result.get('items', [])
        print(f"✅ Found {len(existing_events)} upcoming events")
        
        # Check for duplicate
        subject = field_trip_email.get('subject')
        for event in existing_events:
            if subject.lower() in event.get('summary', '').lower():
                print(f"\n⏭️  Event already exists: {event.get('summary')}")
                print(f"   Event ID: {event.get('id')}")
                print(f"   Start: {event.get('start', {}).get('dateTime', 'TBD')}")
                return
        
    except Exception as e:
        print(f"⚠️  Could not check existing events: {e}")
        existing_events = []
    
    # Create event
    print("\n➕ Creating calendar event...")
    
    # Set event for 1 week from now, 9 AM - 3 PM
    event_date = datetime.now() + timedelta(days=7)
    start_time = event_date.replace(hour=9, minute=0, second=0, microsecond=0)
    end_time = event_date.replace(hour=15, minute=0, second=0, microsecond=0)
    
    start_str = start_time.strftime("%Y-%m-%dT%H:%M:%S")
    end_str = end_time.strftime("%Y-%m-%dT%H:%M:%S")
    
    try:
        event = service.create_event(
            calendar_id='primary',
            summary=field_trip_email.get('subject'),
            description=f"Field trip information from {field_trip_email.get('from')}\n\n"
                       f"Email received: {field_trip_email.get('date')}\n"
                       f"Email ID: {field_trip_email.get('id')}\n\n"
                       f"⚠️ IMPORTANT: Check the original email for:\n"
                       f"- Actual date and time\n"
                       f"- Payment link\n"
                       f"- Permission forms\n"
                       f"- What to bring\n\n"
                       f"This is a placeholder event - update with correct details!",
            start_time=start_str,
            end_time=end_str,
            location="TBD - Check email for location details"
        )
        
        print("\n" + "="*70)
        print("✅ CALENDAR EVENT CREATED!")
        print("="*70)
        
        print(f"\n📅 Event Details:")
        print(f"   Title: {event.get('summary')}")
        print(f"   Event ID: {event.get('id')}")
        print(f"   Date: {start_time.strftime('%A, %B %d, %Y')}")
        print(f"   Time: {start_time.strftime('%I:%M %p')} - {end_time.strftime('%I:%M %p')}")
        print(f"   Location: {event.get('location')}")
        
        print(f"\n🔗 View/Edit in Google Calendar:")
        print(f"   https://calendar.google.com/calendar/r")
        print(f"   Or click: {event.get('htmlLink', 'N/A')}")
        
        print(f"\n⚠️  IMPORTANT NEXT STEPS:")
        print(f"   1. Open Google Calendar")
        print(f"   2. Find the 'Field Trip Information' event")
        print(f"   3. Update with actual date/time from email")
        print(f"   4. Check email from Lisa Prescott for payment link")
        print(f"   5. Add any additional details (what to bring, etc.)")
        
        # Save event info
        with open('field_trip_event.txt', 'w') as f:
            f.write(f"Event: {event.get('summary')}\n")
            f.write(f"Event ID: {event.get('id')}\n")
            f.write(f"Date: {start_time.strftime('%Y-%m-%d %H:%M')}\n")
            f.write(f"Link: {event.get('htmlLink')}\n")
        
        print(f"\n💾 Event info saved to: field_trip_event.txt")
        
        print("\n🎉 Field trip event created successfully!")
        
    except Exception as e:
        print(f"\n❌ Failed to create event: {e}")
        import traceback
        traceback.print_exc()
        
        if "Calendar API has not been used" in str(e) or "SERVICE_DISABLED" in str(e):
            print(f"\n⚠️  Google Calendar API is not enabled!")
            print(f"\nEnable it here:")
            print(f"https://console.developers.google.com/apis/api/calendar-json.googleapis.com/overview?project=837032747486")


if __name__ == '__main__':
    main()
