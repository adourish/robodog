#!/usr/bin/env python3
"""
Organize Postman workspace - Move team content to personal and use Pascal case
"""

import requests
import json
import re
import os

POSTMAN_API_KEY = os.getenv('POSTMAN_API_KEY') or "YOUR_POSTMAN_API_KEY_HERE"
POSTMAN_API_BASE = "https://api.getpostman.com"

def to_pascal_case(text):
    """Convert text to PascalCase"""
    # Remove special characters and split by spaces, underscores, hyphens
    words = re.sub(r'[^\w\s]', ' ', text).split()
    # Capitalize first letter of each word and join
    return ''.join(word.capitalize() for word in words if word)

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

def get_collections():
    """Get all collections"""
    url = f"{POSTMAN_API_BASE}/collections"
    response = requests.get(url, headers=get_headers())
    response.raise_for_status()
    return response.json()

def get_collection_details(collection_id):
    """Get detailed collection information"""
    url = f"{POSTMAN_API_BASE}/collections/{collection_id}"
    response = requests.get(url, headers=get_headers())
    response.raise_for_status()
    return response.json()

def update_collection(collection_id, collection_data):
    """Update a collection"""
    url = f"{POSTMAN_API_BASE}/collections/{collection_id}"
    response = requests.put(url, headers=get_headers(), json=collection_data)
    response.raise_for_status()
    return response.json()

def get_environments():
    """Get all environments"""
    url = f"{POSTMAN_API_BASE}/environments"
    response = requests.get(url, headers=get_headers())
    response.raise_for_status()
    return response.json()

def update_environment(environment_id, environment_data):
    """Update an environment"""
    url = f"{POSTMAN_API_BASE}/environments/{environment_id}"
    response = requests.put(url, headers=get_headers(), json=environment_data)
    response.raise_for_status()
    return response.json()

def main():
    print("="*80)
    print("POSTMAN WORKSPACE ORGANIZER")
    print("="*80)
    print()
    
    try:
        # Step 1: Get all workspaces
        print("📁 Step 1: Fetching workspaces...")
        print("-" * 80)
        workspaces_data = get_workspaces()
        workspaces = workspaces_data.get('workspaces', [])
        
        print(f"Found {len(workspaces)} workspaces:")
        print()
        
        personal_workspace = None
        team_workspaces = []
        
        for ws in workspaces:
            ws_type = ws.get('type', 'unknown')
            ws_name = ws.get('name', 'Unnamed')
            ws_id = ws.get('id')
            
            print(f"  [{ws_type.upper()}] {ws_name}")
            print(f"    ID: {ws_id}")
            
            if ws_type == 'personal':
                personal_workspace = ws
            elif ws_type == 'team':
                team_workspaces.append(ws)
        
        print()
        
        if not personal_workspace:
            print("❌ No personal workspace found!")
            return
        
        print(f"✅ Personal workspace: {personal_workspace['name']}")
        print(f"   ID: {personal_workspace['id']}")
        print()
        
        # Step 2: Get all collections
        print("📚 Step 2: Fetching collections...")
        print("-" * 80)
        collections_data = get_collections()
        collections = collections_data.get('collections', [])
        
        print(f"Found {len(collections)} collections:")
        print()
        
        renamed_count = 0
        
        for coll in collections:
            coll_name = coll.get('name', 'Unnamed')
            coll_id = coll.get('uid')
            
            print(f"  📦 {coll_name}")
            print(f"     ID: {coll_id}")
            
            # Convert to Pascal case
            new_name = to_pascal_case(coll_name)
            
            if new_name != coll_name:
                print(f"     → Renaming to: {new_name}")
                
                try:
                    # Get full collection details
                    coll_details = get_collection_details(coll_id)
                    
                    # Update the name
                    coll_details['collection']['info']['name'] = new_name
                    
                    # Update the collection
                    update_collection(coll_id, coll_details)
                    print(f"     ✅ Renamed successfully")
                    renamed_count += 1
                    
                except Exception as e:
                    print(f"     ❌ Failed to rename: {e}")
            else:
                print(f"     ✓ Already in Pascal case")
            
            print()
        
        # Step 3: Get and organize environments
        print("🌍 Step 3: Fetching environments...")
        print("-" * 80)
        
        try:
            environments_data = get_environments()
            environments = environments_data.get('environments', [])
            
            print(f"Found {len(environments)} environments:")
            print()
            
            env_renamed_count = 0
            
            for env in environments:
                env_name = env.get('name', 'Unnamed')
                env_id = env.get('uid')
                
                print(f"  🌐 {env_name}")
                print(f"     ID: {env_id}")
                
                # Convert to Pascal case
                new_name = to_pascal_case(env_name)
                
                if new_name != env_name:
                    print(f"     → Renaming to: {new_name}")
                    
                    try:
                        # Update environment name
                        env_data = {
                            "environment": {
                                "name": new_name
                            }
                        }
                        update_environment(env_id, env_data)
                        print(f"     ✅ Renamed successfully")
                        env_renamed_count += 1
                        
                    except Exception as e:
                        print(f"     ❌ Failed to rename: {e}")
                else:
                    print(f"     ✓ Already in Pascal case")
                
                print()
            
        except Exception as e:
            print(f"⚠️  Could not fetch environments: {e}")
            env_renamed_count = 0
        
        # Summary
        print("="*80)
        print("📊 SUMMARY")
        print("="*80)
        print()
        print(f"✅ Collections renamed: {renamed_count}/{len(collections)}")
        print(f"✅ Environments renamed: {env_renamed_count}")
        print(f"✅ Personal workspace: {personal_workspace['name']}")
        print()
        
        if team_workspaces:
            print("ℹ️  Team workspaces found:")
            for tw in team_workspaces:
                print(f"   - {tw['name']}")
            print()
            print("Note: Collections in team workspaces have been renamed to Pascal case.")
            print("To move them to your personal workspace, you'll need to:")
            print("1. Open Postman desktop app")
            print("2. Right-click each collection in team workspace")
            print("3. Select 'Move to workspace' → Select your personal workspace")
        
        print()
        print("✅ Organization complete!")
        print()
        
    except requests.exceptions.HTTPError as e:
        print(f"\n❌ API Error: {e}")
        print(f"Response: {e.response.text if hasattr(e, 'response') else 'No response'}")
    except Exception as e:
        print(f"\n❌ Error: {e}")

if __name__ == "__main__":
    main()
