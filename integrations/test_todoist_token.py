#!/usr/bin/env python3
"""Test Todoist API token"""

import requests

# Your API token from config.yaml
API_TOKEN = "62c623e2ae7407e805dabe692f8af45ad582bcfc"
BASE_URL = "https://api.todoist.com/rest/v2"

def test_token():
    """Test if the API token works"""
    
    print("Testing Todoist API token...")
    print(f"Token: {API_TOKEN[:20]}...")
    print(f"Base URL: {BASE_URL}")
    print()
    
    # Try to list projects
    url = f"{BASE_URL}/projects"
    headers = {
        "Authorization": f"Bearer {API_TOKEN}"
    }
    
    print(f"Making GET request to: {url}")
    print(f"Headers: Authorization: Bearer {API_TOKEN[:20]}...")
    print()
    
    try:
        response = requests.get(url, headers=headers)
        print(f"Status Code: {response.status_code}")
        print()
        
        if response.status_code == 200:
            print("✅ SUCCESS! Token is valid")
            projects = response.json()
            print(f"Found {len(projects)} projects")
            if projects:
                print("\nYour projects:")
                for project in projects:
                    fav = "⭐" if project.get('is_favorite') else ""
                    print(f"  - {project.get('name')} (ID: {project.get('id')}) {fav}")
        else:
            print(f"❌ FAILED with status {response.status_code}")
            print(f"Response: {response.text}")
            
            if response.status_code == 401:
                print("\n⚠️  Token is invalid or expired")
                print("\nTo get a new token:")
                print("1. Go to https://todoist.com/app/settings/integrations")
                print("2. Scroll to 'Developer' section")
                print("3. Copy your API token")
                print("4. Update config.yaml with the new token")
                
    except Exception as e:
        print(f"❌ ERROR: {e}")

if __name__ == "__main__":
    test_token()
