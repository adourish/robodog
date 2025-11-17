# How to Get Your Google Client Secret

## Quick Steps

### 1. Go to Google Cloud Console
🔗 **https://console.cloud.google.com/apis/credentials**

### 2. Find Your OAuth 2.0 Client

Look for:
- **Client ID:** `837032747486-0dttoe0dfkfrn9m3obimrgboj8i64leu.apps.googleusercontent.com`
- **Type:** OAuth 2.0 Client ID

### 3. View/Download Secret

**Option A: View in Console**
1. Click on the client ID name
2. Look for "Client secret"
3. Click the copy icon

**Option B: Download JSON**
1. Click the download icon (⬇️) next to your client
2. Open the downloaded JSON file
3. Find the `client_secret` field

### 4. Set Environment Variable

**PowerShell:**
```powershell
$env:GOOGLE_CLIENT_SECRET="YOUR_SECRET_HERE"
```

**Example:**
```powershell
$env:GOOGLE_CLIENT_SECRET="GOCSPX-abc123xyz..."
```

### 5. Verify It's Set

```powershell
python -c "import os; print('Set!' if os.getenv('GOOGLE_CLIENT_SECRET') else 'Not set')"
```

### 6. Run the Test

```powershell
python test_create_google_doc.py
```

---

## What Happens Next

1. **Browser Opens** - You'll be redirected to Google sign-in
2. **Grant Permissions** - Allow the app to access Google Docs and Gmail
3. **Redirect** - You'll be sent to `http://localhost:8080/callback`
4. **Document Created** - A test document will be created
5. **Link Provided** - You'll get a direct link to view it

---

## Where to Find Your Document

### Option 1: Direct Link
The script will print a link like:
```
https://docs.google.com/document/d/1abc123xyz/edit
```

### Option 2: Google Drive Web
1. Go to https://drive.google.com/
2. Look in "My Drive"
3. Search for "Robodog MCP Test"
4. Sort by "Last modified" (newest first)

### Option 3: G: Drive (Desktop)
If you have Google Drive Desktop syncing to G:
1. Open File Explorer
2. Go to `G:\My Drive\`
3. Look for "Robodog MCP Test - [timestamp]"
4. Sort by "Date modified" (newest first)

---

## Troubleshooting

### "Client secret not set"
- Make sure you ran: `$env:GOOGLE_CLIENT_SECRET="your_secret"`
- Verify with: `echo $env:GOOGLE_CLIENT_SECRET`
- Must be in the same PowerShell window

### "Authentication failed"
- Check your Google account has access
- Make sure the OAuth client is enabled
- Try incognito/private browsing

### "Can't find document"
- Wait a few seconds for sync
- Refresh Google Drive
- Check "All locations" not just "My Drive"
- Search by exact title from the script output

---

## Your Configuration

**Client ID:**
```
837032747486-0dttoe0dfkfrn9m3obimrgboj8i64leu.apps.googleusercontent.com
```

**Redirect URI:**
```
http://localhost:8080/callback
```

**Scopes:**
- Google Docs API
- Google Drive API (file access)
- Gmail API (send, compose, modify)

---

## Ready to Test!

Once you have your client secret:

```powershell
# Set the secret
$env:GOOGLE_CLIENT_SECRET="YOUR_SECRET_HERE"

# Run the test
python test_create_google_doc.py

# Follow the prompts to authenticate

# Get the document link and verify in Google Drive or G:\My Drive\
```

🎉 Your document will appear in Google Drive within seconds!
