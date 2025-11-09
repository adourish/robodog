# Code Map React Integration Guide

## Overview

This guide shows how to integrate the Code Map feature into your RoboDog React application.

## MCP API Endpoints

### MAP_SCAN
Scan codebase and create map.

**Request:**
```json
{
  "op": "MAP_SCAN",
  "payload": {
    "extensions": [".py", ".js", ".ts"]  // optional
  }
}
```

**Response:**
```json
{
  "status": "ok",
  "file_count": 45,
  "class_count": 12,
  "function_count": 87
}
```

### MAP_FIND
Find definition of a class or function.

**Request:**
```json
{
  "op": "MAP_FIND",
  "payload": {
    "name": "TodoManager"
  }
}
```

**Response:**
```json
{
  "status": "ok",
  "results": [
    {
      "type": "class",
      "name": "TodoManager",
      "file": "/path/to/todo_manager.py",
      "line_start": 18,
      "line_end": 250,
      "docstring": "High-level todo.md management",
      "args": []
    }
  ]
}
```

### MAP_CONTEXT
Get relevant files for a task.

**Request:**
```json
{
  "op": "MAP_CONTEXT",
  "payload": {
    "task_description": "implement user authentication",
    "include_patterns": ["**/auth/*.py"]  // optional
  }
}
```

**Response:**
```json
{
  "status": "ok",
  "context": {
    "task": "implement user authentication",
    "keywords": ["implement", "user", "authentication"],
    "relevant_files": {
      "/path/to/auth_service.py": {
        "score": 5,
        "summary": {
          "path": "/path/to/auth_service.py",
          "language": "python",
          "lines": 156,
          "classes": ["AuthService", "TokenManager"],
          "functions": ["login", "logout", "verify_token"],
          "dependencies": ["jwt", "bcrypt"]
        }
      }
    },
    "total_files": 3
  }
}
```

### MAP_SUMMARY
Get summary of a specific file.

**Request:**
```json
{
  "op": "MAP_SUMMARY",
  "payload": {
    "file_path": "/path/to/file.py"
  }
}
```

**Response:**
```json
{
  "status": "ok",
  "summary": {
    "path": "/path/to/file.py",
    "language": "python",
    "size": 5432,
    "lines": 156,
    "classes": ["TodoManager"],
    "functions": ["add_task", "list_tasks"],
    "imports": ["os", "json", "pathlib"],
    "dependencies": ["pathlib"],
    "docstring": "Todo management module"
  }
}
```

### MAP_USAGES
Find which files import a module.

**Request:**
```json
{
  "op": "MAP_USAGES",
  "payload": {
    "module": "requests"
  }
}
```

**Response:**
```json
{
  "status": "ok",
  "module": "requests",
  "files": [
    "/path/to/api_client.py",
    "/path/to/http_service.py"
  ]
}
```

### MAP_SAVE
Save map to file.

**Request:**
```json
{
  "op": "MAP_SAVE",
  "payload": {
    "output_path": "codemap.json"  // optional, defaults to "codemap.json"
  }
}
```

**Response:**
```json
{
  "status": "ok",
  "path": "codemap.json"
}
```

### MAP_LOAD
Load map from file.

**Request:**
```json
{
  "op": "MAP_LOAD",
  "payload": {
    "input_path": "codemap.json"  // optional, defaults to "codemap.json"
  }
}
```

**Response:**
```json
{
  "status": "ok",
  "path": "codemap.json",
  "file_count": 45
}
```

### MAP_INDEX
Get index statistics.

**Request:**
```json
{
  "op": "MAP_INDEX",
  "payload": {}
}
```

**Response:**
```json
{
  "status": "ok",
  "index": {
    "classes": {
      "TodoManager": 1,
      "CodeMapper": 1,
      "AuthService": 1
    },
    "functions": {
      "add_task": 1,
      "scan_codebase": 1,
      "login": 2
    },
    "imports": {
      "os": 15,
      "json": 12,
      "requests": 3
    }
  },
  "total_files": 45
}
```

## TypeScript Client

### Installation

Copy `CodeMapClient.ts` to your React project:

```bash
cp typescript/CodeMapClient.ts src/lib/
```

### Basic Usage

```typescript
import { CodeMapClient } from './lib/CodeMapClient';

const client = new CodeMapClient('http://localhost:2500', 'your-token');

// Scan codebase
const scanResult = await client.scan();
console.log(`Scanned ${scanResult.file_count} files`);

// Find definition
const results = await client.findDefinition('TodoManager');
console.log(results);

// Get context for task
const context = await client.getContext('implement authentication');
console.log(context.relevant_files);
```

### React Hook

```typescript
import { useCodeMap } from './lib/CodeMapClient';

function MyComponent() {
  const codeMap = useCodeMap('http://localhost:2500', 'your-token');
  
  const handleScan = async () => {
    const result = await codeMap.scan();
    console.log(`Found ${result.class_count} classes`);
  };
  
  return <button onClick={handleScan}>Scan</button>;
}
```

## React Component

### Installation

Copy `CodeMapView.tsx` to your React project:

```bash
cp typescript/components/CodeMapView.tsx src/components/
```

### Usage

```typescript
import { CodeMapView } from './components/CodeMapView';

function App() {
  return (
    <CodeMapView
      baseUrl="http://localhost:2500"
      token="your-token"
    />
  );
}
```

### Styling

Add CSS for the component:

```css
.code-map-view {
  padding: 20px;
  max-width: 1200px;
  margin: 0 auto;
}

.header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 20px;
}

.stats {
  display: flex;
  gap: 20px;
}

.stats span {
  padding: 5px 10px;
  background: #f0f0f0;
  border-radius: 4px;
}

.error-banner {
  padding: 10px;
  background: #fee;
  border: 1px solid #fcc;
  border-radius: 4px;
  margin-bottom: 20px;
}

.tabs {
  display: flex;
  gap: 10px;
  margin-bottom: 20px;
  border-bottom: 2px solid #ddd;
}

.tabs button {
  padding: 10px 20px;
  border: none;
  background: none;
  cursor: pointer;
  border-bottom: 2px solid transparent;
  margin-bottom: -2px;
}

.tabs button.active {
  border-bottom-color: #007bff;
  color: #007bff;
}

.primary-button {
  padding: 10px 20px;
  background: #007bff;
  color: white;
  border: none;
  border-radius: 4px;
  cursor: pointer;
}

.primary-button:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.result-grid {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 20px;
  margin-top: 20px;
}

.result-card {
  padding: 20px;
  background: #f8f9fa;
  border-radius: 8px;
  text-align: center;
}

.result-value {
  font-size: 32px;
  font-weight: bold;
  color: #007bff;
}

.result-label {
  margin-top: 10px;
  color: #666;
}

.search-box {
  display: flex;
  gap: 10px;
  margin-bottom: 20px;
}

.search-box input {
  flex: 1;
  padding: 10px;
  border: 1px solid #ddd;
  border-radius: 4px;
}

.result-item {
  padding: 15px;
  border: 1px solid #ddd;
  border-radius: 4px;
  margin-bottom: 10px;
}

.result-header {
  display: flex;
  gap: 10px;
  align-items: center;
  margin-bottom: 5px;
}

.result-type {
  padding: 2px 8px;
  background: #007bff;
  color: white;
  border-radius: 3px;
  font-size: 12px;
}

.result-name {
  font-weight: bold;
  font-size: 16px;
}

.result-location {
  color: #666;
  font-size: 14px;
}

.file-item {
  padding: 15px;
  border: 1px solid #ddd;
  border-radius: 4px;
  margin-bottom: 10px;
}

.file-header {
  display: flex;
  gap: 10px;
  align-items: center;
  margin-bottom: 5px;
}

.file-score {
  padding: 2px 8px;
  background: #28a745;
  color: white;
  border-radius: 3px;
  font-weight: bold;
}

.file-name {
  font-weight: bold;
}

.file-path {
  color: #666;
  font-size: 14px;
  margin-bottom: 5px;
}

.file-details {
  display: flex;
  gap: 15px;
  font-size: 14px;
  color: #666;
}
```

## Complete Example

```typescript
import React, { useState, useEffect } from 'react';
import { CodeMapClient } from './lib/CodeMapClient';

function CodeMapDashboard() {
  const [client] = useState(() => new CodeMapClient(
    'http://localhost:2500',
    'your-token'
  ));
  
  const [stats, setStats] = useState(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    // Load map on mount
    loadMap();
  }, []);

  const loadMap = async () => {
    try {
      const fileCount = await client.loadMap();
      const index = await client.getIndex();
      setStats({
        files: fileCount,
        classes: Object.keys(index.index.classes).length,
        functions: Object.keys(index.index.functions).length
      });
    } catch (err) {
      console.error('Failed to load map:', err);
    }
  };

  const scanCodebase = async () => {
    setLoading(true);
    try {
      const result = await client.scan();
      setStats({
        files: result.file_count,
        classes: result.class_count,
        functions: result.function_count
      });
      // Save for next time
      await client.saveMap();
    } catch (err) {
      console.error('Scan failed:', err);
    } finally {
      setLoading(false);
    }
  };

  const findClass = async (name: string) => {
    try {
      const results = await client.findDefinition(name);
      console.log('Found:', results);
    } catch (err) {
      console.error('Find failed:', err);
    }
  };

  return (
    <div className="dashboard">
      <h1>Code Map Dashboard</h1>
      
      {stats && (
        <div className="stats">
          <div>Files: {stats.files}</div>
          <div>Classes: {stats.classes}</div>
          <div>Functions: {stats.functions}</div>
        </div>
      )}
      
      <button onClick={scanCodebase} disabled={loading}>
        {loading ? 'Scanning...' : 'Scan Codebase'}
      </button>
      
      <button onClick={() => findClass('TodoManager')}>
        Find TodoManager
      </button>
    </div>
  );
}

export default CodeMapDashboard;
```

## Best Practices

### 1. Cache the Map

```typescript
// Load on app startup
useEffect(() => {
  client.loadMap().catch(() => {
    // If no cached map, scan
    client.scan().then(() => client.saveMap());
  });
}, []);
```

### 2. Debounce Search

```typescript
import { debounce } from 'lodash';

const debouncedSearch = debounce(async (name: string) => {
  const results = await client.findDefinition(name);
  setResults(results);
}, 300);
```

### 3. Handle Errors

```typescript
try {
  const context = await client.getContext(taskDesc);
  setContext(context);
} catch (err) {
  if (err.message.includes('Authentication')) {
    // Handle auth error
  } else {
    // Handle other errors
  }
}
```

### 4. Show Loading States

```typescript
const [scanning, setScanning] = useState(false);

const handleScan = async () => {
  setScanning(true);
  try {
    await client.scan();
  } finally {
    setScanning(false);
  }
};
```

## Summary

✅ **8 MCP endpoints** for code mapping
✅ **TypeScript client** with type safety
✅ **React hook** for easy integration
✅ **Complete UI component** ready to use
✅ **Full documentation** with examples
✅ **Best practices** for production use

The Code Map feature is now fully integrated and ready for your React app!
