# Google Integration - Quick Start Guide

Get started with Google Docs and Gmail in 5 minutes!

## ⚡ Quick Setup

### 1. Get Your Client Secret (2 minutes)

Your Client ID is already configured:
```
837032747486-0dttoe0dfkfrn9m3obimrgboj8i64leu.apps.googleusercontent.com
```

Now get your Client Secret:

1. Go to: https://console.cloud.google.com/apis/credentials
2. Click on your OAuth 2.0 Client ID
3. Copy the **Client Secret**

### 2. Set Environment Variable (30 seconds)

**Windows (PowerShell):**
```powershell
$env:GOOGLE_CLIENT_SECRET="paste_your_secret_here"
```

**Linux/Mac:**
```bash
export GOOGLE_CLIENT_SECRET="paste_your_secret_here"
```

### 3. Run Your First Command (1 minute)

```bash
cd C:\Projects\robodog

# Test the integration
python test_google_integration.py

# Or use the CLI directly
python robodogcli\google_commands.py auth
```

## 🎯 Common Tasks

### Send an Email

```python
from robodogcli.google_service import GoogleService
import os

service = GoogleService()
service.client_secret = os.getenv('GOOGLE_CLIENT_SECRET')
service.authenticate()  # Opens browser once

# Send email
service.send_email(
    to='support@amplenote.com',
    subject='Request for Renewed Client Key',
    body='Your email content here...'
)
print("✅ Email sent!")
```

### Create a Google Doc

```python
# Create document
doc = service.create_document(
    title='My Document',
    content='Document content here...'
)

print(f"Document URL: https://docs.google.com/document/d/{doc['documentId']}")
```

### Using the CLI

```bash
# Authenticate (one time)
python robodogcli\google_commands.py auth

# Create a document
python robodogcli\google_commands.py gdoc create "Meeting Notes" "Today's agenda"

# Send an email
python robodogcli\google_commands.py gmail send "user@example.com" "Subject" "Body text"

# Read a document
python robodogcli\google_commands.py gdoc read YOUR_DOCUMENT_ID

# List recent emails
python robodogcli\google_commands.py gmail list 10
```

## 📧 Send Your Amplenote Support Email

Ready to send that email to Amplenote support?

```python
from robodogcli.google_service import GoogleService
import os

service = GoogleService()
service.client_secret = os.getenv('GOOGLE_CLIENT_SECRET')
service.authenticate()

# Read the email draft you created
with open('amplenote_support_email.txt', 'r') as f:
    email_content = f.read()

# Extract subject and body
lines = email_content.split('\n')
subject = lines[0].replace('Subject: ', '')
body = '\n'.join(lines[2:])  # Skip subject and blank line

# Send it!
service.send_email(
    to='support@amplenote.com',
    subject=subject,
    body=body
)

print("✅ Email sent to Amplenote support!")
```

Or use the CLI:

```bash
python robodogcli\google_commands.py gmail send support@amplenote.com "Request for Renewed Client Key - Robodog CLI Integration" "Dear Amplenote Support Team, I am writing to request assistance with renewing my API client key..."
```

## 🔧 Troubleshooting

### "Client secret not configured"
- Make sure you set the `GOOGLE_CLIENT_SECRET` environment variable
- Or create `google_config.yaml` (see GOOGLE_INTEGRATION.md)

### "Browser doesn't open"
- Copy the URL from the console and paste it in your browser
- Make sure port 8080 is available

### "Invalid grant"
- Your auth code expired - just run `authenticate()` again

## 📚 Next Steps

- Read the full guide: [GOOGLE_INTEGRATION.md](GOOGLE_INTEGRATION.md)
- Check examples: `python test_google_integration.py`
- View API reference in GOOGLE_INTEGRATION.md

## 🎉 You're Ready!

You can now:
- ✅ Send emails programmatically
- ✅ Create and edit Google Docs
- ✅ Automate your workflows
- ✅ Integrate with Robodog AI

Happy automating! 🚀
