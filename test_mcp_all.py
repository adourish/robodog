"""
Test all MCP operations
"""

import requests
import json


MCP_URL = "http://localhost:2500"
TOKEN = "testtoken"


def call_mcp(operation, payload):
    """Call MCP operation"""
    try:
        body = f"{operation} {json.dumps(payload)}"
        response = requests.post(
            MCP_URL,
            headers={
                "Authorization": f"Bearer {TOKEN}",
                "Content-Type": "text/plain"
            },
            data=body,
            timeout=10
        )
        return response.json()
    except requests.exceptions.ConnectionError:
        return {"status": "error", "error": "MCP server not running"}
    except Exception as e:
        return {"status": "error", "error": str(e)}


def test_help():
    """Test HELP command"""
    print("\n" + "="*70)
    print("TEST: HELP Command")
    print("="*70)
    
    result = call_mcp("HELP", {})
    if result.get("status") == "ok":
        commands = result.get("commands", [])
        print(f"✅ Total commands: {len(commands)}")
        
        # Count by category
        google_ops = [c for c in commands if c.startswith(('GOOGLE', 'GDOC', 'GMAIL', 'GCAL', 'GEVENT'))]
        todoist_ops = [c for c in commands if c.startswith('TODOIST')]
        amplenote_ops = [c for c in commands if c.startswith('AMPLENOTE')]
        
        print(f"   - Google operations: {len(google_ops)}")
        print(f"   - Todoist operations: {len(todoist_ops)}")
        print(f"   - Amplenote operations: {len(amplenote_ops)}")
        
        return True
    else:
        print(f"❌ Failed: {result.get('error')}")
        return False


def test_google_status():
    """Test Google authentication status"""
    print("\n" + "="*70)
    print("TEST: Google Status")
    print("="*70)
    
    result = call_mcp("GOOGLE_STATUS", {})
    if result.get("status") == "ok":
        print(f"✅ Google service available: {result.get('available')}")
        print(f"   Authenticated: {result.get('authenticated')}")
        print(f"   Has token: {result.get('has_token')}")
        return True
    else:
        print(f"❌ Failed: {result.get('error')}")
        return False


def test_todoist_projects():
    """Test Todoist projects"""
    print("\n" + "="*70)
    print("TEST: Todoist Projects")
    print("="*70)
    
    result = call_mcp("TODOIST_PROJECTS", {})
    if result.get("status") == "ok":
        projects = result.get("projects", [])
        print(f"✅ Found {len(projects)} projects:")
        for proj in projects[:3]:  # Show first 3
            print(f"   - {proj.get('name')} (ID: {proj.get('id')})")
        if len(projects) > 3:
            print(f"   ... and {len(projects) - 3} more")
        return True
    else:
        print(f"❌ Failed: {result.get('error')}")
        return False


def test_todoist_tasks():
    """Test Todoist tasks"""
    print("\n" + "="*70)
    print("TEST: Todoist Tasks")
    print("="*70)
    
    result = call_mcp("TODOIST_TASKS", {})
    if result.get("status") == "ok":
        tasks = result.get("tasks", [])
        print(f"✅ Found {len(tasks)} tasks:")
        for task in tasks[:5]:  # Show first 5
            print(f"   - {task.get('content')}")
        if len(tasks) > 5:
            print(f"   ... and {len(tasks) - 5} more")
        return True
    else:
        print(f"❌ Failed: {result.get('error')}")
        return False


def test_gcal_list():
    """Test Google Calendar list"""
    print("\n" + "="*70)
    print("TEST: Google Calendar List")
    print("="*70)
    
    result = call_mcp("GCAL_LIST", {})
    if result.get("status") == "ok":
        calendars = result.get("calendars", {}).get("items", [])
        print(f"✅ Found {len(calendars)} calendars:")
        for cal in calendars[:3]:
            print(f"   - {cal.get('summary')}")
        return True
    elif "Not authenticated" in result.get("error", ""):
        print(f"⚠️  Not authenticated (expected): {result.get('error')}")
        print(f"   To authenticate, run: python test_calendar.py")
        return True  # This is expected
    else:
        print(f"❌ Failed: {result.get('error')}")
        return False


def test_gmail_list():
    """Test Gmail list"""
    print("\n" + "="*70)
    print("TEST: Gmail List")
    print("="*70)
    
    result = call_mcp("GMAIL_LIST", {"max_results": 5})
    if result.get("status") == "ok":
        messages = result.get("messages", [])
        print(f"✅ Found {len(messages)} emails")
        return True
    elif "Not authenticated" in result.get("error", ""):
        print(f"⚠️  Not authenticated (expected): {result.get('error')}")
        return True  # This is expected
    else:
        print(f"❌ Failed: {result.get('error')}")
        return False


def test_file_operations():
    """Test file operations"""
    print("\n" + "="*70)
    print("TEST: File Operations")
    print("="*70)
    
    # Test READ_FILE
    result = call_mcp("READ_FILE", {"path": "c:\\projects\\robodog\\README.md"})
    if result.get("status") == "ok":
        content = result.get("content", "")
        print(f"✅ READ_FILE: Read {len(content)} characters from README.md")
    else:
        print(f"❌ READ_FILE failed: {result.get('error')}")
        return False
    
    # Test LIST_DIR
    result = call_mcp("LIST_DIR", {"path": "c:\\projects\\robodog"})
    if result.get("status") == "ok":
        files = result.get("files", [])
        print(f"✅ LIST_DIR: Found {len(files)} items")
    else:
        print(f"❌ LIST_DIR failed: {result.get('error')}")
        return False
    
    return True


def test_todo_operations():
    """Test TODO operations"""
    print("\n" + "="*70)
    print("TEST: TODO Operations")
    print("="*70)
    
    result = call_mcp("TODO_LIST", {})
    if result.get("status") == "ok":
        tasks = result.get("tasks", [])
        print(f"✅ TODO_LIST: Found {len(tasks)} tasks")
        for task in tasks[:3]:
            print(f"   - {task.get('content', task.get('title', 'Unknown'))}")
        return True
    else:
        print(f"❌ Failed: {result.get('error')}")
        return False


def test_amplenote_list():
    """Test Amplenote list"""
    print("\n" + "="*70)
    print("TEST: Amplenote List")
    print("="*70)
    
    result = call_mcp("AMPLENOTE_LIST", {})
    if result.get("status") == "ok":
        notes = result.get("notes", [])
        print(f"✅ Found {len(notes)} notes")
        return True
    elif "Not authenticated" in result.get("error", ""):
        print(f"⚠️  Not authenticated (expected): {result.get('error')}")
        return True  # This is expected
    else:
        print(f"❌ Failed: {result.get('error')}")
        return False


def main():
    print("\n" + "="*70)
    print("MCP OPERATIONS TEST SUITE")
    print("="*70)
    print(f"Server: {MCP_URL}")
    print(f"Token: {TOKEN}")
    
    tests = [
        ("HELP Command", test_help),
        ("Google Status", test_google_status),
        ("Todoist Projects", test_todoist_projects),
        ("Todoist Tasks", test_todoist_tasks),
        ("Google Calendar", test_gcal_list),
        ("Gmail", test_gmail_list),
        ("File Operations", test_file_operations),
        ("TODO Operations", test_todo_operations),
        ("Amplenote", test_amplenote_list),
    ]
    
    results = []
    for name, test_func in tests:
        try:
            success = test_func()
            results.append((name, success))
        except Exception as e:
            print(f"❌ Exception in {name}: {e}")
            results.append((name, False))
    
    # Summary
    print("\n" + "="*70)
    print("TEST SUMMARY")
    print("="*70)
    
    passed = sum(1 for _, success in results if success)
    total = len(results)
    
    for name, success in results:
        status = "✅ PASS" if success else "❌ FAIL"
        print(f"{status}: {name}")
    
    print(f"\n{passed}/{total} tests passed ({passed*100//total}%)")
    
    if passed == total:
        print("\n🎉 All tests passed!")
    else:
        print(f"\n⚠️  {total - passed} test(s) failed")
    
    return passed == total


if __name__ == '__main__':
    success = main()
    exit(0 if success else 1)
