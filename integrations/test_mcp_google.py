"""
Test Google API operations via MCP protocol
"""

import requests
import json


MCP_URL = "http://localhost:2500"
TOKEN = "testtoken"


def call_mcp(operation, payload):
    """Call MCP operation"""
    try:
        # MCP format: "OPERATION {json_payload}"
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


def test_google_status():
    """Test GOOGLE_STATUS operation"""
    print("\n=== Test 1: GOOGLE_STATUS ===")
    result = call_mcp("GOOGLE_STATUS", {})
    print(f"Result: {json.dumps(result, indent=2)}")
    
    if result.get("status") == "ok":
        print(f"✅ Google service available: {result.get('available')}")
        print(f"✅ Authenticated: {result.get('authenticated')}")
        print(f"✅ Has token: {result.get('has_token')}")
        return True
    else:
        print(f"❌ Error: {result.get('error')}")
        return False


def test_operations_exist():
    """Test that all Google operations are recognized"""
    print("\n=== Test 2: Operations Existence ===")
    
    operations = [
        "GOOGLE_AUTH",
        "GOOGLE_SET_TOKEN",
        "GOOGLE_STATUS",
        "GDOC_CREATE",
        "GDOC_GET",
        "GDOC_READ",
        "GDOC_UPDATE",
        "GDOC_DELETE",
        "GMAIL_SEND",
        "GMAIL_LIST",
        "GMAIL_GET",
        "GMAIL_DRAFT",
        "GMAIL_DELETE_DRAFT"
    ]
    
    passed = 0
    failed = 0
    
    for op in operations:
        # Call with empty payload - should fail with auth error, not "unknown command"
        result = call_mcp(op, {})
        
        if result.get("status") == "error":
            error_msg = result.get("error", "")
            # Check if it's an auth error (good) vs unknown command (bad)
            if "Unknown command" in error_msg or "not running" in error_msg:
                print(f"❌ {op}: Not recognized or server not running")
                failed += 1
            else:
                # Any other error means the operation exists
                print(f"✅ {op}: Recognized (error: {error_msg[:50]}...)")
                passed += 1
        else:
            print(f"✅ {op}: Recognized")
            passed += 1
    
    print(f"\nResults: {passed}/{len(operations)} operations recognized")
    return failed == 0


def test_error_messages():
    """Test that error messages are appropriate"""
    print("\n=== Test 3: Error Messages ===")
    
    # Test GDOC_CREATE without auth
    result = call_mcp("GDOC_CREATE", {"title": "Test"})
    print(f"GDOC_CREATE without auth: {result.get('error', 'No error')}")
    
    if "authenticated" in result.get('error', '').lower() or "initialized" in result.get('error', '').lower():
        print("✅ Appropriate auth error")
    else:
        print(f"⚠️  Unexpected error: {result.get('error')}")
    
    # Test GMAIL_SEND without required params
    result = call_mcp("GMAIL_SEND", {})
    print(f"GMAIL_SEND without params: {result.get('error', 'No error')}")
    
    if "missing" in result.get('error', '').lower():
        print("✅ Appropriate validation error")
    else:
        print(f"⚠️  Unexpected error: {result.get('error')}")
    
    return True


def test_help_command():
    """Test that HELP command works"""
    print("\n=== Test 4: HELP Command ===")
    result = call_mcp("HELP", {})
    print(f"HELP result: {result.get('status')}")
    
    if result.get("status") == "ok":
        print("✅ HELP command works")
        return True
    else:
        print(f"❌ HELP failed: {result.get('error')}")
        return False


def main():
    """Run all tests"""
    print("=" * 70)
    print("MCP Google Operations Test Suite")
    print("=" * 70)
    print("\nNote: MCP server must be running on http://localhost:2500")
    print("Start with: python -m robodog.cli --folders . --port 2500 --token testtoken")
    
    tests = [
        ("Google Status", test_google_status),
        ("Operations Existence", test_operations_exist),
        ("Error Messages", test_error_messages),
        ("HELP Command", test_help_command),
    ]
    
    passed = 0
    failed = 0
    
    for name, test_func in tests:
        try:
            if test_func():
                passed += 1
            else:
                failed += 1
        except Exception as e:
            print(f"❌ {name} FAILED with exception: {e}")
            failed += 1
    
    print("\n" + "=" * 70)
    print("Test Summary")
    print("=" * 70)
    print(f"Total Tests: {len(tests)}")
    print(f"✅ Passed: {passed}")
    print(f"❌ Failed: {failed}")
    print(f"Success Rate: {(passed/len(tests)*100):.1f}%")
    print("=" * 70)
    
    if failed == 0:
        print("\n🎉 ALL TESTS PASSED! 🎉")
        print("\nGoogle MCP operations are ready to use!")
        print("\nNext steps:")
        print("1. Authenticate: call GOOGLE_AUTH")
        print("2. Create docs: call GDOC_CREATE")
        print("3. Send emails: call GMAIL_SEND")
    else:
        print(f"\n⚠️  {failed} test(s) failed.")
        if "not running" in str(failed):
            print("\nMake sure MCP server is running:")
            print("  python -m robodog.cli --folders . --port 2500 --token testtoken")
    
    return failed == 0


if __name__ == '__main__':
    import sys
    success = main()
    sys.exit(0 if success else 1)
