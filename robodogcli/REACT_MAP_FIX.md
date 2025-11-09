# React App MAP Command Fix

## Issue

When running `/map scan` in the React app, you get error: "No verbs"

## Root Cause

The `/map` command is a CLI command, not an MCP endpoint. The React app should use the MCP API directly, not CLI commands.

## Solution

### Option 1: Use MCP API Directly (Recommended)

Instead of sending `/map scan` as a command, use the MCP endpoint:

```typescript
// In your React app
const response = await fetch('http://localhost:2500', {
  method: 'POST',
  headers: {
    'Authorization': 'Bearer testtoken',
    'Content-Type': 'application/json'
  },
  body: JSON.stringify({
    op: 'MAP_SCAN',
    payload: {}
  })
});

const data = await response.json();
console.log(data);
```

### Option 2: Use the CodeMapClient

```typescript
import { CodeMapClient } from './lib/CodeMapClient';

const client = new CodeMapClient('http://localhost:2500', 'testtoken');
const result = await client.scan();
console.log(result);
```

### Option 3: Add CLI Command Support to React App

If you want to support CLI commands in the React app, you need to add a command parser that converts `/map scan` to the appropriate MCP call.

## Quick Test

Test the MCP endpoint directly:

```bash
curl -X POST http://localhost:2500 \
  -H "Authorization: Bearer testtoken" \
  -H "Content-Type: application/json" \
  -d '{"op":"MAP_SCAN","payload":{}}'
```

Expected response:
```json
{
  "status": "ok",
  "file_count": 45,
  "class_count": 12,
  "function_count": 87
}
```

## Available MAP Endpoints

- `MAP_SCAN` - Scan codebase
- `MAP_FIND` - Find definitions
- `MAP_CONTEXT` - Get context for task
- `MAP_SUMMARY` - Get file summary
- `MAP_USAGES` - Find module usages
- `MAP_SAVE` - Save map
- `MAP_LOAD` - Load map
- `MAP_INDEX` - Get index stats

## Updated Files

✅ `mcphandler.py` - Added MAP commands to HELP list

Now the server will recognize MAP_* commands when called via MCP protocol.
