"""
List recent emails from Gmail
"""

import os
import sys
import json

# Add robodogcli to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'robodogcli'))

from google_service import GoogleService


def main():
    print("=" * 70)
    print("Gmail - List Recent Emails")
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
    
    # List recent emails
    print(f"\n📬 Fetching your recent emails...")
    
    try:
        emails = service.list_emails(max_results=10)
        
        messages = emails.get('messages', [])
        result_size = emails.get('resultSizeEstimate', 0)
        
        print(f"\n📊 Email Summary:")
        print(f"   Total emails in account: ~{result_size}")
        print(f"   Showing: {len(messages)} most recent")
        
        print(f"\n" + "=" * 70)
        print("Recent Emails:")
        print("=" * 70)
        
        for i, msg in enumerate(messages, 1):
            msg_id = msg.get('id')
            thread_id = msg.get('threadId')
            
            print(f"\n📧 Email #{i}")
            print(f"   Message ID: {msg_id}")
            print(f"   Thread ID: {thread_id}")
            
            # Get full email details
            try:
                email_data = service.get_email(msg_id)
                
                # Extract headers
                payload = email_data.get('payload', {})
                headers = payload.get('headers', [])
                
                # Get important headers
                subject = next((h['value'] for h in headers if h['name'].lower() == 'subject'), 'No Subject')
                from_addr = next((h['value'] for h in headers if h['name'].lower() == 'from'), 'Unknown')
                to_addr = next((h['value'] for h in headers if h['name'].lower() == 'to'), 'Unknown')
                date = next((h['value'] for h in headers if h['name'].lower() == 'date'), 'Unknown')
                
                print(f"   From: {from_addr}")
                print(f"   To: {to_addr}")
                print(f"   Subject: {subject}")
                print(f"   Date: {date}")
                
                # Get snippet (preview)
                snippet = email_data.get('snippet', '')
                if snippet:
                    print(f"   Preview: {snippet[:100]}...")
                
                # Get labels
                labels = email_data.get('labelIds', [])
                if labels:
                    print(f"   Labels: {', '.join(labels)}")
                
            except Exception as e:
                print(f"   ⚠️  Could not fetch details: {e}")
        
        print(f"\n" + "=" * 70)
        print("✅ Email listing complete!")
        print("=" * 70)
        
        # Save to file
        output_file = "recent_emails.json"
        with open(output_file, 'w') as f:
            json.dump({
                'total_estimate': result_size,
                'messages_shown': len(messages),
                'messages': messages
            }, f, indent=2)
        
        print(f"\n💾 Email list saved to: {output_file}")
        
        print(f"\n📊 Summary:")
        print(f"   ✅ Gmail API is working")
        print(f"   ✅ Can list emails")
        print(f"   ✅ Can read email details")
        print(f"   ✅ Ready for email organization!")
        
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
    if success:
        print("\n🎉 Successfully listed emails!")
        print("\nNext: We can organize them, search, filter, etc.")
    else:
        print("\n❌ Failed to list emails. See errors above.")
