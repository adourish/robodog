#!/usr/bin/env python3
"""Test different Amplenote authentication methods"""

import requests

TOKEN = "b889d2968aaee9169fc6981dcf175c2f63af8cddf1bfdce0a431fa1757534502"
BASE_URL = "https://api.amplenote.com/v4"

def test_auth_methods():
    """Test different authentication header formats"""
    
    url = f"{BASE_URL}/notes"
    
    methods = [
        ("Bearer token", {"Authorization": f"Bearer {TOKEN}"}),
        ("Plain token", {"Authorization": TOKEN}),
        ("API-Key header", {"API-Key": TOKEN}),
        ("X-API-Key header", {"X-API-Key": TOKEN}),
        ("Token header", {"Token": TOKEN}),
    ]
    
    print("Testing different authentication methods for Amplenote API...")
    print(f"Token: {TOKEN[:20]}...")
    print()
    
    for method_name, headers in methods:
        print(f"Testing: {method_name}")
        print(f"  Headers: {headers}")
        
        try:
            response = requests.get(url, headers=headers)
            print(f"  Status: {response.status_code}")
            
            if response.status_code == 200:
                print(f"  ✅ SUCCESS with {method_name}!")
                notes = response.json()
                print(f"  Found {len(notes)} notes")
                return method_name, headers
            elif response.status_code == 401:
                print(f"  ❌ Unauthorized")
            else:
                print(f"  ⚠️  Unexpected status")
                
        except Exception as e:
            print(f"  ❌ Error: {e}")
        
        print()
    
    print("❌ None of the authentication methods worked.")
    print("\nThis token appears to be:")
    print("1. An OAuth client ID (not an API token)")
    print("2. Expired or revoked")
    print("3. Not a valid personal access token")
    print("\nPlease check Amplenote settings for a 'Personal Access Token' option.")

if __name__ == "__main__":
    test_auth_methods()
