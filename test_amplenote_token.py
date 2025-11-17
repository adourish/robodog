#!/usr/bin/env python3
"""Test Amplenote API token"""

import requests
import os

# Your API token - testing new key
API_TOKEN = os.getenv('AMPLENOTE_API_TOKEN') or "YOUR_AMPLENOTE_API_TOKEN_HERE"
BASE_URL = "https://api.amplenote.com/v4"
print("Testing with NEW token (PMAK)...")

def test_token():
    """Test if the API token works"""
    
    print("Testing Amplenote API token...")
    print(f"Token: {API_TOKEN[:20]}...")
    print(f"Base URL: {BASE_URL}")
    print()
    
    # Try to list notes
    url = f"{BASE_URL}/notes"
    headers = {
        "Authorization": f"Bearer {API_TOKEN}"
    }
    
    print(f"Making GET request to: {url}")
    print(f"Headers: Authorization: Bearer {API_TOKEN[:20]}...")
    print()
    
    try:
        response = requests.get(url, headers=headers)
        print(f"Status Code: {response.status_code}")
        print(f"Response Headers: {dict(response.headers)}")
        print()
        
        if response.status_code == 200:
            print("✅ SUCCESS! Token is valid")
            notes = response.json()
            print(f"Found {len(notes)} notes")
            if notes:
                print("\nFirst note:")
                print(f"  Name: {notes[0].get('name')}")
                print(f"  UUID: {notes[0].get('uuid')}")
        else:
            print(f"❌ FAILED with status {response.status_code}")
            print(f"Response: {response.text}")
            
            if response.status_code == 401:
                print("\n⚠️  Token is invalid or expired")
                print("\nTo get a new token:")
                print("1. Go to https://www.amplenote.com/settings")
                print("2. Look for 'API' or 'Developer' section")
                print("3. Generate a new API token")
                print("4. Update config.yaml with the new token")
                
    except Exception as e:
        print(f"❌ ERROR: {e}")

if __name__ == "__main__":
    test_token()
