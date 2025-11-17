"""
Send the Amplenote support email using Google Gmail API

This script reads the email draft from amplenote_support_email.txt
and sends it via Gmail.

Usage:
    1. Set your Google client secret:
       $env:GOOGLE_CLIENT_SECRET="your_secret_here"
    
    2. Run the script:
       python send_amplenote_email.py
    
    3. Follow the browser authentication flow
    
    4. Email will be sent!
"""

import os
import sys

# Add robodogcli to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'robodogcli'))

from google_service import GoogleService


def read_email_draft():
    """Read the email draft from file"""
    email_file = 'amplenote_support_email.txt'
    
    if not os.path.exists(email_file):
        print(f"❌ Error: {email_file} not found")
        print("Please create the email draft first")
        return None, None
    
    with open(email_file, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # Parse email
    lines = content.split('\n')
    subject = ''
    body_lines = []
    in_body = False
    
    for line in lines:
        if line.startswith('Subject:'):
            subject = line.replace('Subject:', '').strip()
        elif line.strip() == '' and subject:
            in_body = True
        elif in_body:
            body_lines.append(line)
    
    body = '\n'.join(body_lines).strip()
    
    return subject, body


def main():
    """Main function"""
    print("=" * 70)
    print("Send Amplenote Support Email")
    print("=" * 70)
    print()
    
    # Check for client secret
    client_secret = os.getenv('GOOGLE_CLIENT_SECRET')
    if not client_secret:
        print("❌ Error: GOOGLE_CLIENT_SECRET not set")
        print()
        print("Please set your Google client secret:")
        print("  PowerShell: $env:GOOGLE_CLIENT_SECRET=\"your_secret_here\"")
        print("  Bash: export GOOGLE_CLIENT_SECRET=\"your_secret_here\"")
        print()
        print("Get your client secret from:")
        print("  https://console.cloud.google.com/apis/credentials")
        return
    
    # Read email draft
    print("📧 Reading email draft...")
    subject, body = read_email_draft()
    
    if not subject or not body:
        print("❌ Failed to read email draft")
        return
    
    print(f"✅ Email draft loaded")
    print(f"   Subject: {subject}")
    print(f"   Body length: {len(body)} characters")
    print()
    
    # Show preview
    print("=" * 70)
    print("EMAIL PREVIEW")
    print("=" * 70)
    print(f"To: support@amplenote.com")
    print(f"Subject: {subject}")
    print()
    print(body[:200] + "..." if len(body) > 200 else body)
    print("=" * 70)
    print()
    
    # Confirm
    response = input("Send this email? (yes/no): ").strip().lower()
    if response not in ['yes', 'y']:
        print("❌ Email not sent")
        return
    
    # Initialize service
    print()
    print("🔐 Initializing Google service...")
    service = GoogleService()
    service.client_secret = client_secret
    
    # Authenticate
    print("🔑 Starting authentication...")
    print("   A browser window will open for Google sign-in")
    print("   Please complete the authentication flow")
    print()
    
    try:
        service.authenticate()
        print("✅ Authentication successful!")
        print()
    except Exception as e:
        print(f"❌ Authentication failed: {e}")
        return
    
    # Send email
    print("📤 Sending email...")
    try:
        result = service.send_email(
            to='support@amplenote.com',
            subject=subject,
            body=body
        )
        
        print("✅ Email sent successfully!")
        print(f"   Message ID: {result['id']}")
        print(f"   Thread ID: {result['threadId']}")
        print()
        print("=" * 70)
        print("SUCCESS! Your email has been sent to Amplenote support.")
        print("=" * 70)
        
    except Exception as e:
        print(f"❌ Failed to send email: {e}")
        return


if __name__ == '__main__':
    main()
