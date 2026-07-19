"""
Test Google Docs and Gmail integration
"""

import os
import sys

# Add robodogcli to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'robodogcli'))

from google_service import GoogleService


def test_google_docs():
    """Test Google Docs operations"""
    print("\n=== Testing Google Docs ===\n")
    
    service = GoogleService()
    
    # Note: Set your client secret from Google Cloud Console
    # service.client_secret = os.getenv('GOOGLE_CLIENT_SECRET')
    
    print("Client ID:", service.client_id)
    print("\nTo use this service, you need to:")
    print("1. Go to https://console.cloud.google.com/apis/credentials")
    print("2. Get your Client Secret")
    print("3. Set it via environment variable: GOOGLE_CLIENT_SECRET")
    print("\nThen run:")
    print("  service.authenticate()")
    print("  doc = service.create_document('Test Doc', 'Hello World')")
    print("  print(doc)")
    
    # Uncomment to test (requires client secret):
    # service.authenticate()
    # doc = service.create_document('Robodog Test Document', 'This is a test from Robodog!')
    # print(f"✅ Document created: https://docs.google.com/document/d/{doc['documentId']}")


def test_gmail():
    """Test Gmail operations"""
    print("\n=== Testing Gmail ===\n")
    
    service = GoogleService()
    
    print("Client ID:", service.client_id)
    print("\nTo send emails, you need to:")
    print("1. Authenticate: service.authenticate()")
    print("2. Send email: service.send_email('to@example.com', 'Subject', 'Body')")
    
    # Example: Create draft for Amplenote support
    print("\n--- Example: Create Amplenote Support Email Draft ---")
    
    to_email = "support@amplenote.com"
    subject = "Request for Renewed Client Key - Robodog CLI Integration"
    body = """Dear Amplenote Support Team,

I am writing to request assistance with renewing my API client key for my approved application "Robodog CLI Integration."

My current client key is no longer working, and I need a renewed key to continue using the API.

Account Details:
- Account Type: PI Account
- Current Client Key: b889d2968aaee9169fc6981dcf175c2f63af8cddf1bfdce0a431fa1757534502
- API Application Status: Approved
- Application Submitted: May 17, 2023

Application Information:
- Company/Developer Name: Robodog CLI Integration
- Application Name: Robodog CLI
- Application Description: CLI tool for programmatic Amplenote note and task management.
- Redirect URI: http://localhost:8080/callback

Could you please provide guidance on how to obtain a renewed client key?

Thank you for your assistance.

Best regards,
[Your Name]
"""
    
    print(f"To: {to_email}")
    print(f"Subject: {subject}")
    print("\nTo send this email:")
    print("  service.authenticate()")
    print(f"  service.send_email('{to_email}', '{subject}', body)")
    print("\nOr create a draft:")
    print(f"  draft = service.create_draft('{to_email}', '{subject}', body)")


def test_document_operations():
    """Test various document operations"""
    print("\n=== Document Operations Examples ===\n")
    
    examples = [
        ("Create Document", "service.create_document('My Doc', 'Content')"),
        ("Get Document", "service.get_document('DOCUMENT_ID')"),
        ("Read Text", "service.read_document_text('DOCUMENT_ID')"),
        ("Update Document", "service.update_document('DOCUMENT_ID', 'New content')"),
        ("Delete Document", "service.delete_document('DOCUMENT_ID')"),
    ]
    
    for name, code in examples:
        print(f"• {name}:")
        print(f"  {code}")
        print()


def test_email_operations():
    """Test various email operations"""
    print("\n=== Email Operations Examples ===\n")
    
    examples = [
        ("Send Email", "service.send_email('to@example.com', 'Subject', 'Body')"),
        ("Send HTML Email", "service.send_email('to@example.com', 'Subject', '<h1>HTML</h1>', is_html=True)"),
        ("List Emails", "service.list_emails(max_results=10, query='from:someone@example.com')"),
        ("Get Email", "service.get_email('MESSAGE_ID')"),
        ("Create Draft", "service.create_draft('to@example.com', 'Subject', 'Body')"),
        ("Delete Draft", "service.delete_draft('DRAFT_ID')"),
    ]
    
    for name, code in examples:
        print(f"• {name}:")
        print(f"  {code}")
        print()


def main():
    """Run all tests"""
    print("=" * 60)
    print("Google Integration Test Suite")
    print("=" * 60)
    
    test_google_docs()
    test_gmail()
    test_document_operations()
    test_email_operations()
    
    print("\n" + "=" * 60)
    print("Setup Instructions:")
    print("=" * 60)
    print("\n1. Get your Client Secret:")
    print("   https://console.cloud.google.com/apis/credentials")
    print("\n2. Set environment variable:")
    print("   export GOOGLE_CLIENT_SECRET='your_secret_here'")
    print("\n3. Run authentication:")
    print("   from google_service import GoogleService")
    print("   service = GoogleService()")
    print("   service.client_secret = os.getenv('GOOGLE_CLIENT_SECRET')")
    print("   service.authenticate()")
    print("\n4. Start using the APIs!")
    print("=" * 60)


if __name__ == '__main__':
    main()
