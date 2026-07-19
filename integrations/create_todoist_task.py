#!/usr/bin/env python3
"""Create a Todoist task via MCP server"""

import requests
import json

MCP_URL = "http://127.0.0.1:2500"
MCP_TOKEN = "testtoken"

def create_task():
    """Create a Todoist task named 'godzilla task 2'"""
    
    print("Creating Todoist task via MCP server...")
    print(f"MCP URL: {MCP_URL}")
    print()
    
    # MCP format: "OPERATION {json_payload}"
    operation = "TODOIST_CREATE"
    payload = {
        "content": "godzilla task 2",
        "priority": 2,
        "due_string": "today"
    }
    
    # Format as: OPERATION {json}
    body = f"{operation} {json.dumps(payload)}"
    
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {MCP_TOKEN}"
    }
    
    try:
        print(f"Sending request...")
        print(f"Operation: {operation}")
        print(f"Payload: {json.dumps(payload, indent=2)}")
        print(f"Body: {body}")
        print()
        
        response = requests.post(MCP_URL, headers=headers, data=body)
        
        print(f"Status Code: {response.status_code}")
        print(f"Response: {json.dumps(response.json(), indent=2)}")
        print()
        
        result = response.json()
        
        if result.get("status") == "ok":
            task = result.get("task", {})
            print("✅ SUCCESS! Task created:")
            print(f"   Task ID: {task.get('id')}")
            print(f"   Content: {task.get('content')}")
            print(f"   Priority: {task.get('priority')}")
            print(f"   Due: {task.get('due', {}).get('string', 'No due date')}")
            print(f"   URL: {task.get('url')}")
        else:
            print(f"❌ FAILED: {result.get('error')}")
            
    except requests.exceptions.ConnectionError:
        print("❌ ERROR: Cannot connect to MCP server")
        print("\nMake sure the MCP server is running:")
        print("python robodog\\cli.py --folders c:\\projects\\robodog\\robodogcli --port 2500 --token testtoken --config config.yaml")
    except Exception as e:
        print(f"❌ ERROR: {e}")

if __name__ == "__main__":
    create_task()
