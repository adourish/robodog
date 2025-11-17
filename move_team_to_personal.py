#!/usr/bin/env python3
"""
Move all content from team workspace to personal workspace
"""

import requests
import json
import time
import os

POSTMAN_API_KEY = os.getenv('POSTMAN_API_KEY') or "YOUR_POSTMAN_API_KEY_HERE"
POSTMAN_API_BASE = "https://api.getpostman.com"

def get_headers():
    """Get headers for Postman API requests"""
    return {
        "X-Api-Key": POSTMAN_API_KEY,
        "Content-Type": "application/json"
    }

def get_workspaces():
    """Get all workspaces"""
    url = f"{POSTMAN_API_BASE}/workspaces"
    response = requests.get(url, headers=get_headers())
    response.raise_for_status()
    return response.json()

def get_workspace_details(workspace_id):
    """Get detailed workspace information"""
    url = f"{POSTMAN_API_BASE}/workspaces/{workspace_id}"
    response = requests.get(url, headers=get_headers())
    response.raise_for_status()
    return response.json()

def get_collection_details(collection_id):
    """Get detailed collection information"""
    url = f"{POSTMAN_API_BASE}/collections/{collection_id}"
    response = requests.get(url, headers=get_headers())
    response.raise_for_status()
    return response.json()

def create_collection(collection_data):
    """Create a new collection"""
    url = f"{POSTMAN_API_BASE}/collections"
    response = requests.post(url, headers=get_headers(), json=collection_data)
    response.raise_for_status()
    return response.json()

def get_environment_details(environment_id):
    """Get detailed environment information"""
    url = f"{POSTMAN_API_BASE}/environments/{environment_id}"
    response = requests.get(url, headers=get_headers())
    response.raise_for_status()
    return response.json()

def create_environment(environment_data):
    """Create a new environment"""
    url = f"{POSTMAN_API_BASE}/environments"
    response = requests.post(url, headers=get_headers(), json=environment_data)
    response.raise_for_status()
    return response.json()

def main():
    print("="*80)
    print("MOVE TEAM CONTENT TO PERSONAL WORKSPACE")
    print("="*80)
    print()
    
    try:
        # Step 1: Find workspaces
        print("📁 Step 1: Finding workspaces...")
        print("-" * 80)
        
        workspaces_data = get_workspaces()
        workspaces = workspaces_data.get('workspaces', [])
        
        team_workspace = None
        personal_workspace = None
        
        for ws in workspaces:
            ws_name = ws.get('name', '')
            ws_id = ws.get('id')
            ws_type = ws.get('type', 'unknown')
            
            print(f"  [{ws_type.upper()}] {ws_name}")
            print(f"    ID: {ws_id}")
            
            # Look for team workspace with "interstellar-meadow" or team type
            if 'interstellar-meadow' in ws_name.lower() or ws_type == 'team':
                team_workspace = ws
                print(f"    ⭐ TEAM WORKSPACE FOUND")
            
            # Find personal workspace (prefer "robodog")
            if ws_type == 'personal':
                if ws_name.lower() == 'robodog' or personal_workspace is None:
                    personal_workspace = ws
                    if ws_name.lower() == 'robodog':
                        print(f"    ⭐ TARGET PERSONAL WORKSPACE")
            
            print()
        
        if not team_workspace:
            print("❌ Team workspace 'interstellar-meadow-83444' not found!")
            print("\nAvailable workspaces:")
            for ws in workspaces:
                print(f"  - {ws.get('name')} ({ws.get('type')})")
            return
        
        if not personal_workspace:
            print("❌ No personal workspace found!")
            return
        
        print(f"✅ Source (Team): {team_workspace['name']}")
        print(f"   ID: {team_workspace['id']}")
        print()
        print(f"✅ Target (Personal): {personal_workspace['name']}")
        print(f"   ID: {personal_workspace['id']}")
        print()
        
        # Step 2: Get team workspace details
        print("📚 Step 2: Fetching team workspace content...")
        print("-" * 80)
        
        team_details = get_workspace_details(team_workspace['id'])
        team_ws = team_details.get('workspace', {})
        
        collections = team_ws.get('collections', [])
        environments = team_ws.get('environments', [])
        
        print(f"Found in team workspace:")
        print(f"  📦 Collections: {len(collections)}")
        print(f"  🌍 Environments: {len(environments)}")
        print()
        
        if not collections and not environments:
            print("⚠️  No content found in team workspace!")
            return
        
        # Step 3: Copy collections
        copied_collections = 0
        
        if collections:
            print("📦 Step 3: Copying collections...")
            print("-" * 80)
            
            for coll in collections:
                coll_name = coll.get('name', 'Unnamed')
                coll_id = coll.get('uid')
                
                print(f"\n  📦 {coll_name}")
                print(f"     ID: {coll_id}")
                
                try:
                    # Get full collection details
                    print(f"     → Fetching collection details...")
                    coll_details = get_collection_details(coll_id)
                    
                    # Create a copy in personal workspace
                    print(f"     → Creating copy in personal workspace...")
                    new_coll = create_collection(coll_details)
                    
                    print(f"     ✅ Copied successfully!")
                    print(f"     New ID: {new_coll.get('collection', {}).get('uid')}")
                    copied_collections += 1
                    
                    # Small delay to avoid rate limiting
                    time.sleep(0.5)
                    
                except Exception as e:
                    print(f"     ❌ Failed to copy: {e}")
        
        # Step 4: Copy environments
        copied_environments = 0
        
        if environments:
            print()
            print("🌍 Step 4: Copying environments...")
            print("-" * 80)
            
            for env in environments:
                env_name = env.get('name', 'Unnamed')
                env_id = env.get('uid')
                
                print(f"\n  🌐 {env_name}")
                print(f"     ID: {env_id}")
                
                try:
                    # Get full environment details
                    print(f"     → Fetching environment details...")
                    env_details = get_environment_details(env_id)
                    
                    # Create a copy in personal workspace
                    print(f"     → Creating copy in personal workspace...")
                    new_env = create_environment(env_details)
                    
                    print(f"     ✅ Copied successfully!")
                    print(f"     New ID: {new_env.get('environment', {}).get('uid')}")
                    copied_environments += 1
                    
                    # Small delay to avoid rate limiting
                    time.sleep(0.5)
                    
                except Exception as e:
                    print(f"     ❌ Failed to copy: {e}")
        
        # Summary
        print()
        print("="*80)
        print("📊 MIGRATION SUMMARY")
        print("="*80)
        print()
        print(f"Source: {team_workspace['name']} (Team)")
        print(f"Target: {personal_workspace['name']} (Personal)")
        print()
        print(f"✅ Collections copied: {copied_collections}/{len(collections)}")
        print(f"✅ Environments copied: {copied_environments}/{len(environments)}")
        print()
        
        if copied_collections == len(collections) and copied_environments == len(environments):
            print("🎉 All content successfully migrated to your personal workspace!")
        else:
            print("⚠️  Some items failed to copy. Check the errors above.")
        
        print()
        print("Next steps:")
        print("1. Open Postman and verify the copied content")
        print("2. If everything looks good, you can delete items from team workspace")
        print("3. Or keep them in team workspace for collaboration")
        print()
        
    except requests.exceptions.HTTPError as e:
        print(f"\n❌ API Error: {e}")
        if hasattr(e, 'response'):
            print(f"Status Code: {e.response.status_code}")
            print(f"Response: {e.response.text}")
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()
