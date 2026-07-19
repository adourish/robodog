"""Quick demo of MCP operations"""
import requests
import json

MCP_URL = "http://localhost:2500"
TOKEN = "testtoken"

def call_mcp(op, payload):
    r = requests.post(MCP_URL, 
        headers={'Authorization': f'Bearer {TOKEN}', 'Content-Type': 'text/plain'},
        data=f'{op} {json.dumps(payload)}')
    return r.json()

print("\n=== MCP Service Demo ===\n")

# 1. Todoist Projects
print("📋 Todoist Projects:")
result = call_mcp("TODOIST_PROJECTS", {})
for p in result['projects']:
    print(f"   • {p['name']} ({p['color']})")

# 2. Todoist Tasks
print("\n✅ Todoist Tasks (first 5):")
result = call_mcp("TODOIST_TASKS", {})
for i, t in enumerate(result['tasks'][:5], 1):
    print(f"   {i}. {t['content']}")

# 3. Google Status
print("\n🔐 Google Status:")
result = call_mcp("GOOGLE_STATUS", {})
print(f"   Available: {result['available']}")
print(f"   Authenticated: {result['authenticated']}")

# 4. TODO List
print("\n📝 TODO Tasks:")
result = call_mcp("TODO_LIST", {})
print(f"   Total tasks: {len(result.get('tasks', []))}")

print("\n✅ MCP Service is working!\n")
