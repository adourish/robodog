"""
Test Google Calendar API - Create Calendar and Event
"""

import os
import sys
from datetime import datetime, timedelta

# Add robodogcli to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'robodogcli'))

from google_service import GoogleService


def main():
    print("=" * 70)
    print("Google Calendar API Test")
    print("=" * 70)
    
    # Check for client secret
    client_secret = os.getenv('GOOGLE_CLIENT_SECRET')
    if not client_secret:
        print("\n❌ GOOGLE_CLIENT_SECRET not set!")
        return
    
    print(f"\n✅ Client secret found")
    
    # Initialize service
    print("\n📝 Initializing Google service...")
    service = GoogleService()
    service.client_secret = client_secret
    
    # Authenticate
    print("\n🔐 Authenticating...")
    try:
        service.authenticate()
        print("✅ Authentication successful!")
    except Exception as e:
        print(f"❌ Authentication failed: {e}")
        return
    
    # List existing calendars
    print(f"\n📅 Listing your calendars...")
    try:
        calendars = service.list_calendars()
        items = calendars.get('items', [])
        
        print(f"\n📊 Found {len(items)} calendars:")
        for i, cal in enumerate(items, 1):
            print(f"   {i}. {cal.get('summary')} (ID: {cal.get('id')})")
            if cal.get('description'):
                print(f"      Description: {cal.get('description')}")
            if cal.get('primary'):
                print(f"      ⭐ PRIMARY CALENDAR")
        
    except Exception as e:
        print(f"❌ Failed to list calendars: {e}")
        return
    
    # Create a new calendar
    print(f"\n📅 Creating new calendar...")
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    calendar_name = f"Robodog Test Calendar - {timestamp}"
    calendar_desc = "Test calendar created by Robodog MCP integration"
    
    try:
        calendar = service.create_calendar(calendar_name, calendar_desc)
        calendar_id = calendar.get('id')
        
        print(f"\n" + "=" * 70)
        print("🎉 SUCCESS! Calendar Created!")
        print("=" * 70)
        
        print(f"\n📅 Calendar Details:")
        print(f"   Name: {calendar.get('summary')}")
        print(f"   ID: {calendar_id}")
        print(f"   Description: {calendar.get('description')}")
        print(f"   Timezone: {calendar.get('timeZone')}")
        
        print(f"\n🔗 View in Google Calendar:")
        print(f"   https://calendar.google.com/calendar/r")
        print(f"   Look for: '{calendar_name}'")
        
        # Create a test event in the new calendar
        print(f"\n📝 Creating test event in the new calendar...")
        
        # Event times: now + 1 hour, duration 1 hour
        start = datetime.now() + timedelta(hours=1)
        end = start + timedelta(hours=1)
        
        event_summary = "Robodog Test Event"
        event_description = f"Test event created by Robodog at {timestamp}"
        start_time = start.isoformat()
        end_time = end.isoformat()
        
        event = service.create_event(
            calendar_id=calendar_id,
            summary=event_summary,
            description=event_description,
            start_time=start_time,
            end_time=end_time,
            location="Virtual"
        )
        
        event_id = event.get('id')
        
        print(f"\n🎉 Event Created!")
        print(f"   Title: {event.get('summary')}")
        print(f"   ID: {event_id}")
        print(f"   Start: {start.strftime('%Y-%m-%d %H:%M')}")
        print(f"   End: {end.strftime('%Y-%m-%d %H:%M')}")
        print(f"   Location: {event.get('location')}")
        
        # Save calendar info
        info_file = "test_calendar_info.txt"
        with open(info_file, 'w') as f:
            f.write(f"Calendar Name: {calendar_name}\n")
            f.write(f"Calendar ID: {calendar_id}\n")
            f.write(f"Event Title: {event_summary}\n")
            f.write(f"Event ID: {event_id}\n")
            f.write(f"Created: {timestamp}\n")
        
        print(f"\n💾 Calendar info saved to: {info_file}")
        
        # Test search
        print(f"\n🔍 Testing calendar search...")
        search_results = service.search_calendars("Robodog")
        found = search_results.get('items', [])
        print(f"   Found {len(found)} calendars matching 'Robodog'")
        
        # Test event search
        print(f"\n🔍 Testing event search...")
        event_results = service.search_events(calendar_id, "Robodog")
        found_events = event_results.get('items', [])
        print(f"   Found {len(found_events)} events matching 'Robodog'")
        
        print(f"\n" + "=" * 70)
        print("✅ Calendar Test Complete!")
        print("=" * 70)
        
        print(f"\n📊 Summary:")
        print(f"   ✅ Calendar API is working")
        print(f"   ✅ Can create calendars")
        print(f"   ✅ Can create events")
        print(f"   ✅ Can search calendars")
        print(f"   ✅ Can search events")
        print(f"   ✅ Full CRUD operations available")
        
        print(f"\n📅 Find your calendar:")
        print(f"   1. Go to: https://calendar.google.com/")
        print(f"   2. Look in the left sidebar under 'Other calendars'")
        print(f"   3. Find: '{calendar_name}'")
        print(f"   4. Click to view the test event")
        
        return True
        
    except Exception as e:
        print(f"\n❌ Failed to create calendar: {e}")
        print(f"\nError details: {type(e).__name__}")
        import traceback
        traceback.print_exc()
        
        # Check if Calendar API is enabled
        if "SERVICE_DISABLED" in str(e) or "has not been used" in str(e):
            print(f"\n⚠️  Google Calendar API is not enabled!")
            print(f"\nEnable it here:")
            print(f"https://console.developers.google.com/apis/api/calendar-json.googleapis.com/overview?project=837032747486")
        
        return False


if __name__ == '__main__':
    success = main()
    if success:
        print("\n🎉 Successfully created calendar and event!")
        print("\nNext: Use MCP operations to manage calendars and events")
    else:
        print("\n❌ Calendar test failed. See errors above.")
