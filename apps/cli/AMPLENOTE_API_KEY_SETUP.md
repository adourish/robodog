# Amplenote API Key Setup (Fixed)

## Issue Fixed

The OAuth error you encountered:
```
The client identifier provided is invalid...
```

This happened because Amplenote requires you to register an OAuth app to use OAuth authentication. However, since you already have an API token, we've updated the service to use it directly!

## ✅ Solution: Use API Token (No OAuth Needed)

Your `config.yaml` already has the API key configured:

```yaml
- provider: amplenote
  baseUrl: "https://api.amplenote.com/v4"
  authUrl: "https://login.amplenote.com/login"
  tokenUrl: "https://api.amplenote.com/oauth/token"
  apiKey: "b889d2968aaee9169fc6981dcf175c2f63af8cddf1bfdce0a431fa1757534502"
  scopes:
    - "notes:create"
    - "notes:create-content-action"
    - "notes:create-image"
    - "notes:list"
```

## How It Works Now

1. **Automatic Authentication**: When the service initializes, it checks for `apiKey` in config
2. **No OAuth Needed**: If API key is present, it's used directly as the access token
3. **Seamless Experience**: All commands work immediately without `/amplenote auth`

## Testing

### Method 1: CLI Commands (Recommended)

```bash
# Start the CLI
cd c:\Projects\robodog\robodogcli
python robodog\cli.py --folders c:\projects\robodog\robodogcli --port 2500 --token testtoken --config config.yaml

# Test commands (no auth needed!)
/amplenote list
/amplenote create "Test Note"
/amplenote add <note_uuid> "Test content"
```

### Method 2: Check Authentication Status

```bash
/amplenote auth
```

You should see:
```
✅ Using API key from config.yaml - already authenticated!
```

### Method 3: MCP API

```javascript
// In browser console
fetch('http://127.0.0.1:2500', {
  method: 'POST',
  headers: {
    'Content-Type': 'application/json',
    'Authorization': 'Bearer testtoken'
  },
  body: JSON.stringify({
    operation: 'AMPLENOTE_LIST',
    payload: {}
  })
})
.then(r => r.json())
.then(data => console.log('Notes:', data));
```

## What Changed

### Before (OAuth - Required Registration)
```python
# Required OAuth app registration
# Would fail with "invalid client identifier"
```

### After (API Token - Works Immediately)
```python
# Uses API key from config.yaml
# Works immediately without OAuth
if self.api_key:
    self.access_token = self.api_key
    logger.info("Using Amplenote API key from config")
```

## Getting Your API Token

If you need to get a new API token:

1. Go to https://www.amplenote.com/settings
2. Navigate to "API" or "Integrations" section
3. Generate a new API token
4. Copy the token to `config.yaml` under `apiKey`

## OAuth Alternative (Optional)

If you prefer to use OAuth instead of API token:

1. Register an OAuth app at Amplenote
2. Get your `client_id` and `client_secret`
3. Update `config.yaml`:
   ```yaml
   - provider: amplenote
     clientId: "your_client_id"
     clientSecret: "your_client_secret"
     apiKey: ""  # Leave empty to use OAuth
   ```
4. Run `/amplenote auth` to complete OAuth flow

## Verification

Test that everything works:

```bash
# 1. Start CLI
python robodog\cli.py --config config.yaml

# 2. List notes (should work immediately)
/amplenote list

# 3. Create a test note
/amplenote create "Test Note from Fixed Integration"

# 4. Verify in Amplenote web app
```

## Summary

✅ **Fixed**: No more OAuth errors  
✅ **Simpler**: API key authentication works automatically  
✅ **Faster**: No OAuth flow needed  
✅ **Secure**: API key stored in config.yaml  

Your Amplenote integration is now ready to use! 🎉
