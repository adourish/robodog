#!/usr/bin/env python3
"""
Diagnose Postman API access and show all available content
"""

import requests
import json
import os

POSTMAN_API_KEY = os.getenv('POSTMAN_API_KEY') or "YOUR_POSTMAN_API_KEY_HERE"
POSTMAN_API_BASE = "https://api.getpostman.com"

def get_headers():
    return {
        "X-Api-Key": POSTMAN_API_KEY,
        "Content-Type": "application/json"
    }

def main():
    print("="*80)
    print("POSTMAN API DIAGNOSTIC")
    print("="*80)
    print()
    
    # Test 1: Get user info
    print("👤 User Information")
    print("-" * 80)
    try:
        response = requests.get(f"{POSTMAN_API_BASE}/me", headers=get_headers())
        response.raise_for_status()
        user = response.json()
        print(json.dumps(user, indent=2))
    except Exception as e:
        print(f"❌ Error: {e}")
    print()
    
    # Test 2: Get all workspaces
    print("📁 All Workspaces")
    print("-" * 80)
    try:
        response = requests.get(f"{POSTMAN_API_BASE}/workspaces", headers=get_headers())
        response.raise_for_status()
        data = response.json()
        workspaces = data.get('workspaces', [])
        
        for ws in workspaces:
            print(f"\nWorkspace: {ws.get('name')}")
            print(f"  ID: {ws.get('id')}")
            print(f"  Type: {ws.get('type')}")
            print(f"  Visibility: {ws.get('visibility', 'N/A')}")
            
            # Get detailed info
            try:
                detail_response = requests.get(
                    f"{POSTMAN_API_BASE}/workspaces/{ws.get('id')}", 
                    headers=get_headers()
                )
                detail_response.raise_for_status()
                details = detail_response.json().get('workspace', {})
                
                collections = details.get('collections', [])
                environments = details.get('environments', [])
                
                print(f"  Collections: {len(collections)}")
                if collections:
                    for coll in collections[:5]:  # Show first 5
                        print(f"    - {coll.get('name')}")
                    if len(collections) > 5:
                        print(f"    ... and {len(collections) - 5} more")
                
                print(f"  Environments: {len(environments)}")
                if environments:
                    for env in environments[:5]:
                        print(f"    - {env.get('name')}")
                    if len(environments) > 5:
                        print(f"    ... and {len(environments) - 5} more")
                        
            except Exception as e:
                print(f"  ⚠️  Could not get details: {e}")
                
    except Exception as e:
        print(f"❌ Error: {e}")
    print()
    
    # Test 3: Get all collections (global view)
    print("📚 All Collections (Global)")
    print("-" * 80)
    try:
        response = requests.get(f"{POSTMAN_API_BASE}/collections", headers=get_headers())
        response.raise_for_status()
        data = response.json()
        collections = data.get('collections', [])
        
        print(f"Total collections accessible: {len(collections)}")
        for coll in collections:
            print(f"  - {coll.get('name')} (ID: {coll.get('uid')})")
            
    except Exception as e:
        print(f"❌ Error: {e}")
    print()
    
    # Test 4: Get all environments (global view)
    print("🌍 All Environments (Global)")
    print("-" * 80)
    try:
        response = requests.get(f"{POSTMAN_API_BASE}/environments", headers=get_headers())
        response.raise_for_status()
        data = response.json()
        environments = data.get('environments', [])
        
        print(f"Total environments accessible: {len(environments)}")
        for env in environments:
            print(f"  - {env.get('name')} (ID: {env.get('uid')})")
            
    except Exception as e:
        print(f"❌ Error: {e}")
    print()
    
    print("="*80)
    print("RECOMMENDATIONS")
    print("="*80)
    print()
    print("If you don't see team workspace content:")
    print()
    print("1. Check if you're a member of the team workspace")
    print("2. Verify your API key has team workspace permissions")
    print("3. Team workspace might require different API key or permissions")
    print()
    print("Alternative: Use Postman Desktop App")
    print("  - Open Postman desktop application")
    print("  - Navigate to team workspace 'interstellar-meadow-83444'")
    print("  - Right-click each collection → 'Move to workspace' → 'robodog'")
    print()

if __name__ == "__main__":
    main()
