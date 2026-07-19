#!/usr/bin/env python3
"""
Interactive tool to help get Amplenote API token
"""

import webbrowser
import time
import requests

def main():
    print("="*70)
    print("AMPLENOTE API TOKEN SETUP HELPER")
    print("="*70)
    print()
    
    print("📝 STEP 1: Get Your Amplenote API Token")
    print("-" * 70)
    print()
    print("You need to get an API token from Amplenote. Here's how:")
    print()
    print("1. I'll open the Amplenote settings page in your browser")
    print("2. Log in to your Amplenote account if needed")
    print("3. Look for one of these sections:")
    print("   - 'API'")
    print("   - 'API Tokens'")
    print("   - 'Developer'")
    print("   - 'Integrations'")
    print("4. Generate a new API token")
    print("5. Copy the token")
    print()
    
    input("Press ENTER to open Amplenote settings in your browser...")
    
    # Open Amplenote settings
    urls_to_try = [
        "https://www.amplenote.com/settings",
        "https://www.amplenote.com/account",
        "https://www.amplenote.com/app/settings"
    ]
    
    print()
    print("Opening Amplenote settings...")
    for url in urls_to_try:
        print(f"  - {url}")
        webbrowser.open(url)
        time.sleep(1)
    
    print()
    print("-" * 70)
    print("📋 STEP 2: Enter Your Token")
    print("-" * 70)
    print()
    print("After you've generated your API token, paste it below:")
    print("(The token should be a long string of letters and numbers)")
    print()
    
    token = input("Paste your Amplenote API token here: ").strip()
    
    if not token:
        print("\n❌ No token provided. Exiting.")
        return
    
    print()
    print("-" * 70)
    print("🧪 STEP 3: Testing Your Token")
    print("-" * 70)
    print()
    
    # Test the token
    print(f"Token: {token[:20]}..." if len(token) > 20 else f"Token: {token}")
    print("Testing against Amplenote API...")
    print()
    
    base_url = "https://api.amplenote.com/v4"
    headers = {"Authorization": f"Bearer {token}"}
    
    try:
        response = requests.get(f"{base_url}/notes", headers=headers)
        
        print(f"Status Code: {response.status_code}")
        
        if response.status_code == 200:
            notes = response.json()
            print()
            print("✅ SUCCESS! Your token works!")
            print(f"✅ Found {len(notes)} notes in your account")
            print()
            
            if notes:
                print("Your first few notes:")
                for note in notes[:5]:
                    print(f"  - {note.get('name', 'Untitled')} ({note.get('uuid')})")
            
            print()
            print("-" * 70)
            print("📝 STEP 4: Update Your Config")
            print("-" * 70)
            print()
            print("Add this to your config.yaml:")
            print()
            print("    - provider: amplenote")
            print("      baseUrl: \"https://api.amplenote.com/v4\"")
            print(f"      apiKey: \"{token}\"")
            print("      scopes:")
            print("        - \"notes:create\"")
            print("        - \"notes:create-content-action\"")
            print("        - \"notes:create-image\"")
            print("        - \"notes:list\"")
            print()
            print("✅ Setup complete! You can now use Amplenote commands.")
            
        elif response.status_code == 401:
            print()
            print("❌ FAILED: Token is invalid or expired")
            print()
            print("The token you provided doesn't work. Please:")
            print("1. Make sure you copied the ENTIRE token")
            print("2. Generate a NEW token (the old one might be expired)")
            print("3. Make sure it's an API token, not an OAuth client ID")
            print()
            print(f"Error details: {response.text}")
            
        else:
            print()
            print(f"⚠️  Unexpected response: {response.status_code}")
            print(f"Response: {response.text}")
            
    except requests.exceptions.RequestException as e:
        print()
        print(f"❌ Network error: {e}")
        print()
        print("Make sure you have internet connection and try again.")
    
    print()
    print("="*70)

if __name__ == "__main__":
    main()
