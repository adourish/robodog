"""
Get last 100 emails from Gmail
"""

import os
import sys
import json
from datetime import datetime

# Add robodogcli to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'robodogcli'))

from robodog.google_service import GoogleService


def main():
    print("=" * 70)
    print("Gmail - Get Last 100 Emails")
    print("=" * 70)
    
    # Check for client secret
    client_secret = os.getenv('GOOGLE_CLIENT_SECRET')
    if not client_secret:
        print("\n❌ GOOGLE_CLIENT_SECRET not set!")
        print("\nRun: $env:GOOGLE_CLIENT_SECRET='YOUR_SECRET'")
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
    
    # List emails
    print(f"\n📧 Fetching last 100 emails...")
    try:
        result = service.list_emails(max_results=100, query='')
        messages = result.get('messages', [])
        
        print(f"\n✅ Found {len(messages)} emails")
        print("=" * 70)
        
        # Get details for each email
        emails_data = []
        for i, msg in enumerate(messages, 1):
            msg_id = msg['id']
            
            # Get full message details
            email = service.get_email(msg_id)
            
            # Extract headers
            headers = {h['name']: h['value'] for h in email.get('payload', {}).get('headers', [])}
            
            email_info = {
                'number': i,
                'id': msg_id,
                'thread_id': email.get('threadId'),
                'from': headers.get('From', 'Unknown'),
                'to': headers.get('To', 'Unknown'),
                'subject': headers.get('Subject', 'No Subject'),
                'date': headers.get('Date', 'Unknown'),
                'labels': email.get('labelIds', [])
            }
            
            emails_data.append(email_info)
            
            # Print progress
            if i % 10 == 0:
                print(f"   Processed {i}/{len(messages)} emails...")
        
        # Display results
        print("\n" + "=" * 70)
        print("EMAIL LIST")
        print("=" * 70)
        
        for email in emails_data:
            print(f"\n📧 Email #{email['number']}")
            print(f"   Message ID: {email['id']}")
            print(f"   Thread ID: {email['thread_id']}")
            print(f"   From: {email['from']}")
            print(f"   To: {email['to']}")
            print(f"   Subject: {email['subject'][:60]}{'...' if len(email['subject']) > 60 else ''}")
            print(f"   Date: {email['date']}")
            
            # Show labels
            if email['labels']:
                label_str = ', '.join(email['labels'])
                if len(label_str) > 50:
                    label_str = label_str[:50] + '...'
                print(f"   Labels: {label_str}")
        
        # Save to file
        output_file = "last_100_emails.json"
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(emails_data, f, indent=2, ensure_ascii=False)
        
        print("\n" + "=" * 70)
        print(f"💾 Email list saved to: {output_file}")
        print("=" * 70)
        
        # Summary
        print(f"\n📊 Summary:")
        print(f"   ✅ Total emails retrieved: {len(emails_data)}")
        print(f"   ✅ Data saved to: {output_file}")
        
        # Count by label
        label_counts = {}
        for email in emails_data:
            for label in email['labels']:
                label_counts[label] = label_counts.get(label, 0) + 1
        
        if label_counts:
            print(f"\n📋 Emails by label:")
            for label, count in sorted(label_counts.items(), key=lambda x: -x[1])[:10]:
                print(f"   - {label}: {count}")
        
        print("\n🎉 Successfully retrieved all emails!")
        
        return True
        
    except Exception as e:
        print(f"\n❌ Failed to list emails: {e}")
        print(f"\nError details: {type(e).__name__}")
        import traceback
        traceback.print_exc()
        
        # Check if Gmail API is enabled
        if "SERVICE_DISABLED" in str(e) or "has not been used" in str(e):
            print(f"\n⚠️  Gmail API is not enabled!")
            print(f"\nEnable it here:")
            print(f"https://console.developers.google.com/apis/api/gmail.googleapis.com/overview?project=837032747486")
        
        return False


if __name__ == '__main__':
    success = main()
    if not success:
        print("\n❌ Failed to retrieve emails. See errors above.")
