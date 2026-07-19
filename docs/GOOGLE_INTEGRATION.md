# Google Integration for Robodog

Robodog now supports Google Docs and Gmail integration! Create, edit, and manage documents, and send emails programmatically.

## 🔑 Your Google OAuth Credentials

**Client ID:** `837032747486-0dttoe0dfkfrn9m3obimrgboj8i64leu.apps.googleusercontent.com`

**Redirect URI:** `http://localhost:8080/callback`

## 📋 Setup Instructions

### 1. Get Your Client Secret

1. Go to [Google Cloud Console - Credentials](https://console.cloud.google.com/apis/credentials)
2. Find your OAuth 2.0 Client ID (the one matching your client ID above)
3. Click on it to view details
4. Copy the **Client Secret**

### 2. Configure Credentials

Create a `google_config.yaml` file (copy from `google_config.example.yaml`):

```yaml
google:
  client_id: "837032747486-0dttoe0dfkfrn9m3obimrgboj8i64leu.apps.googleusercontent.com"
  client_secret: "YOUR_CLIENT_SECRET_HERE"  # Paste your secret here
  redirect_uri: "http://localhost:8080/callback"
```

**⚠️ IMPORTANT:** Never commit `google_config.yaml` to version control! It's already in `.gitignore`.

### 3. Enable Required APIs

Make sure these APIs are enabled in your Google Cloud project:

- ✅ Google Docs API
- ✅ Google Drive API
- ✅ Gmail API

Enable them at: https://console.cloud.google.com/apis/library

## 🚀 Quick Start

### Python (CLI)

```python
from robodogcli.google_service import GoogleService
import os

# Initialize service
service = GoogleService()
service.client_secret = os.getenv('GOOGLE_CLIENT_SECRET')

# Authenticate (opens browser)
service.authenticate()

# Create a Google Doc
doc = service.create_document('My First Doc', 'Hello from Robodog!')
print(f"Document created: https://docs.google.com/document/d/{doc['documentId']}")

# Send an email
service.send_email(
    to='someone@example.com',
    subject='Hello from Robodog',
    body='This email was sent programmatically!'
)
print("✅ Email sent!")
```

### JavaScript (Web UI)

```javascript
import googleService from './GoogleService.js';

// Authenticate
await googleService.authenticate();

// Create a document
const doc = await googleService.createDocument('My Doc', 'Content here');
console.log('Document ID:', doc.documentId);

// Send an email
await googleService.sendEmail(
  'someone@example.com',
  'Test Subject',
  'Email body content'
);
```

## 📚 API Reference

### Google Docs Operations

#### Create Document
```python
doc = service.create_document(title='My Document', content='Initial content')
# Returns: {'documentId': '...', 'title': '...', ...}
```

#### Get Document
```python
doc = service.get_document(document_id='DOCUMENT_ID')
# Returns: Full document structure with content
```

#### Read Document Text
```python
text = service.read_document_text(document_id='DOCUMENT_ID')
# Returns: Plain text content of the document
```

#### Update Document
```python
result = service.update_document(
    document_id='DOCUMENT_ID',
    content='New content to add',
    insert_index=1  # Position to insert (1 = beginning)
)
```

#### Delete Document
```python
result = service.delete_document(document_id='DOCUMENT_ID')
# Moves document to trash
```

### Gmail Operations

#### Send Email
```python
result = service.send_email(
    to='recipient@example.com',
    subject='Email Subject',
    body='Email body content',
    is_html=False,  # Set True for HTML emails
    cc='cc@example.com',  # Optional
    bcc='bcc@example.com'  # Optional
)
```

#### Send HTML Email
```python
html_body = '<h1>Hello!</h1><p>This is <strong>HTML</strong> email.</p>'
service.send_email(
    to='recipient@example.com',
    subject='HTML Email',
    body=html_body,
    is_html=True
)
```

#### List Emails
```python
emails = service.list_emails(
    max_results=10,
    query='from:someone@example.com'  # Gmail search query
)
# Returns: {'messages': [{'id': '...', 'threadId': '...'}, ...]}
```

#### Get Email
```python
email = service.get_email(message_id='MESSAGE_ID')
# Returns: Full email details including headers and body
```

#### Create Draft
```python
draft = service.create_draft(
    to='recipient@example.com',
    subject='Draft Subject',
    body='Draft content'
)
# Returns: {'id': '...', 'message': {...}}
```

#### Delete Draft
```python
result = service.delete_draft(draft_id='DRAFT_ID')
```

## 🎯 Use Cases

### 1. Send Support Email to Amplenote

```python
service.send_email(
    to='support@amplenote.com',
    subject='Request for Renewed Client Key - Robodog CLI Integration',
    body='''Dear Amplenote Support Team,

I am writing to request assistance with renewing my API client key...

Account Details:
- Account Type: PI Account
- Current Client Key: b889d2968aaee9169fc6981dcf175c2f63af8cddf1bfdce0a431fa1757534502
...

Best regards,
[Your Name]'''
)
```

### 2. Create Meeting Notes

```python
# Create a document for meeting notes
doc = service.create_document(
    title='Team Meeting - 2025-01-16',
    content='''# Team Meeting Notes

Date: January 16, 2025
Attendees: Team Members

## Agenda
1. Project updates
2. Q&A
3. Action items

## Notes
...
'''
)

print(f"Meeting notes: https://docs.google.com/document/d/{doc['documentId']}")
```

### 3. Automated Report Generation

```python
# Generate and email a report
report_doc = service.create_document(
    title='Weekly Report - Week 3',
    content=generate_report_content()  # Your report generation function
)

# Email the link
service.send_email(
    to='team@company.com',
    subject='Weekly Report - Week 3',
    body=f'''Hi Team,

The weekly report is ready:
https://docs.google.com/document/d/{report_doc['documentId']}

Best regards,
Robodog'''
)
```

### 4. Document Collaboration

```python
# Read existing document
text = service.read_document_text('DOCUMENT_ID')

# Process with AI
processed_text = ai_process(text)  # Your AI processing

# Update document with results
service.update_document('DOCUMENT_ID', f'\n\n## AI Analysis\n{processed_text}')
```

## 🔧 Advanced Configuration

### Environment Variables

```bash
# Set client secret via environment variable
export GOOGLE_CLIENT_SECRET="your_secret_here"

# Or in PowerShell
$env:GOOGLE_CLIENT_SECRET="your_secret_here"
```

### Load from Config File

```python
import yaml

with open('google_config.yaml', 'r') as f:
    config = yaml.safe_load(f)

service = GoogleService(
    client_id=config['google']['client_id'],
    client_secret=config['google']['client_secret'],
    redirect_uri=config['google']['redirect_uri']
)
```

### Token Management

```python
# Save tokens for reuse
with open('.google_token', 'w') as f:
    json.dump({
        'access_token': service.access_token,
        'refresh_token': service.refresh_token
    }, f)

# Load saved tokens
with open('.google_token', 'r') as f:
    tokens = json.load(f)
    service.set_access_token(
        tokens['access_token'],
        tokens['refresh_token']
    )
```

## 🛠️ Integration with Robodog CLI

Add Google commands to your Robodog workflow:

```python
# In your robodog CLI
from robodogcli.google_service import GoogleService

# Initialize once
google = GoogleService()
google.client_secret = config['google']['client_secret']
google.authenticate()

# Use in commands
def handle_google_command(cmd, args):
    if cmd == 'gdoc':
        if args[0] == 'create':
            doc = google.create_document(args[1], args[2] if len(args) > 2 else '')
            print(f"Created: {doc['documentId']}")
        elif args[0] == 'read':
            text = google.read_document_text(args[1])
            print(text)
    
    elif cmd == 'gmail':
        if args[0] == 'send':
            google.send_email(args[1], args[2], args[3])
            print("✅ Email sent!")
```

## 📝 Testing

Run the test suite:

```bash
python test_google_integration.py
```

This will show you examples and verify your setup.

## 🔒 Security Best Practices

1. **Never commit credentials** - `google_config.yaml` is in `.gitignore`
2. **Use environment variables** for production
3. **Rotate secrets regularly** in Google Cloud Console
4. **Limit OAuth scopes** to only what you need
5. **Store tokens securely** - never in plain text in production

## 🐛 Troubleshooting

### "Not authenticated" error
- Make sure you called `service.authenticate()` first
- Check that your client secret is correct

### "Invalid grant" error
- Your authorization code may have expired
- Run `service.authenticate()` again

### "Insufficient permissions" error
- Check that required APIs are enabled in Google Cloud Console
- Verify OAuth scopes include what you need

### Browser doesn't open for auth
- Copy the URL from console and open manually
- Check that port 8080 is available

## 📖 Additional Resources

- [Google Docs API Documentation](https://developers.google.com/docs/api)
- [Gmail API Documentation](https://developers.google.com/gmail/api)
- [Google OAuth 2.0 Guide](https://developers.google.com/identity/protocols/oauth2)
- [Google Cloud Console](https://console.cloud.google.com/)

## 🎉 What's Next?

With Google integration, you can now:

- ✅ Create and edit documents programmatically
- ✅ Send emails from your Robodog workflows
- ✅ Automate report generation
- ✅ Integrate with your existing Google Workspace
- ✅ Build document collaboration tools
- ✅ Create email automation workflows

Happy coding! 🚀
