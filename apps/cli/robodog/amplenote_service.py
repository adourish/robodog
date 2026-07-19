# file: amplenote_service.py
#!/usr/bin/env python3
"""Amplenote API integration with OAuth2 PKCE authentication."""

import os
import json
import hashlib
import base64
import secrets
import webbrowser
import requests
from pathlib import Path
from typing import Dict, List, Optional, Any
from urllib.parse import urlencode, parse_qs, urlparse
import logging

logger = logging.getLogger('robodog.amplenote')


class AmplenoteService:
    """Service for interacting with Amplenote API using OAuth2 PKCE flow."""
    
    def __init__(self, config: Dict[str, Any]):
        """
        Initialize Amplenote service.
        
        Args:
            config: Configuration dictionary containing:
                - baseUrl: API base URL
                - authUrl: OAuth authorization URL
                - tokenUrl: OAuth token URL
                - apiKey: Direct API token (alternative to OAuth)
                - clientId: OAuth client ID (optional, for registered apps)
                - scopes: List of OAuth scopes
        """
        self.base_url = config.get("baseUrl", "https://api.amplenote.com/v4")
        self.auth_url = config.get("authUrl", "https://login.amplenote.com/login")
        self.token_url = config.get("tokenUrl", "https://api.amplenote.com/oauth/token")
        self.client_id = config.get("clientId", "")
        self.api_key = config.get("apiKey", "")
        self.scopes = config.get("scopes", [
            "notes:create",
            "notes:create-content-action",
            "notes:create-image",
            "notes:list"
        ])
        
        # Token storage
        self.token_file = Path.home() / ".robodog" / "amplenote_token.json"
        self.token_file.parent.mkdir(parents=True, exist_ok=True)
        
        self.access_token = None
        self.refresh_token = None
        
        # If API key is provided, use it directly
        if self.api_key:
            self.access_token = self.api_key
            logger.info("Using Amplenote API key from config")
        else:
            self._load_token()
    
    def _generate_pkce_pair(self) -> tuple[str, str]:
        """Generate PKCE code verifier and challenge."""
        # Generate code verifier (43-128 characters)
        code_verifier = base64.urlsafe_b64encode(secrets.token_bytes(32)).decode('utf-8').rstrip('=')
        
        # Generate code challenge (SHA256 hash of verifier)
        code_challenge = base64.urlsafe_b64encode(
            hashlib.sha256(code_verifier.encode('utf-8')).digest()
        ).decode('utf-8').rstrip('=')
        
        return code_verifier, code_challenge
    
    def _load_token(self):
        """Load stored access token if available."""
        if self.token_file.exists():
            try:
                with open(self.token_file, 'r') as f:
                    data = json.load(f)
                    self.access_token = data.get("access_token")
                    self.refresh_token = data.get("refresh_token")
                    logger.info("Loaded Amplenote access token from storage")
            except Exception as e:
                logger.warning(f"Failed to load token: {e}")
    
    def _save_token(self, token_data: Dict[str, str]):
        """Save access token to storage."""
        try:
            with open(self.token_file, 'w') as f:
                json.dump(token_data, f, indent=2)
            logger.info("Saved Amplenote access token to storage")
        except Exception as e:
            logger.error(f"Failed to save token: {e}")
    
    def authenticate(self, redirect_uri: str = "http://localhost:8080/callback") -> bool:
        """
        Perform OAuth2 PKCE authentication flow.
        Note: If API key is configured, authentication is not needed.
        
        Args:
            redirect_uri: OAuth redirect URI
            
        Returns:
            True if authentication successful, False otherwise
        """
        # If API key is already set, no need to authenticate
        if self.api_key:
            print("\n✓ Using API key from config.yaml - no OAuth needed!")
            return True
        # Generate PKCE pair
        code_verifier, code_challenge = self._generate_pkce_pair()
        
        # Build authorization URL
        auth_params = {
            "response_type": "code",
            "client_id": self.client_id or "robodog",
            "redirect_uri": redirect_uri,
            "scope": " ".join(self.scopes),
            "code_challenge": code_challenge,
            "code_challenge_method": "S256",
            "state": secrets.token_urlsafe(16)
        }
        
        auth_url_full = f"{self.auth_url}?{urlencode(auth_params)}"
        
        print("\n" + "="*60)
        print("AMPLENOTE AUTHENTICATION")
        print("="*60)
        print(f"\nOpening browser for authentication...")
        print(f"\nIf browser doesn't open, visit this URL:")
        print(f"\n{auth_url_full}\n")
        print(f"After authorization, you'll be redirected to:")
        print(f"{redirect_uri}")
        print("\nPaste the full redirect URL here:")
        
        # Open browser
        webbrowser.open(auth_url_full)
        
        # Get authorization code from user
        redirect_url = input("\nRedirect URL: ").strip()
        
        # Parse authorization code
        parsed = urlparse(redirect_url)
        params = parse_qs(parsed.query)
        
        if "code" not in params:
            logger.error("No authorization code found in redirect URL")
            return False
        
        auth_code = params["code"][0]
        
        # Exchange authorization code for access token
        token_data = {
            "grant_type": "authorization_code",
            "code": auth_code,
            "redirect_uri": redirect_uri,
            "code_verifier": code_verifier,
            "client_id": self.client_id or "robodog"
        }
        
        try:
            response = requests.post(self.token_url, data=token_data)
            response.raise_for_status()
            
            token_response = response.json()
            self.access_token = token_response.get("access_token")
            self.refresh_token = token_response.get("refresh_token")
            
            self._save_token(token_response)
            
            print("\n✓ Authentication successful!")
            return True
            
        except requests.exceptions.RequestException as e:
            logger.error(f"Token exchange failed: {e}")
            return False
    
    def _make_request(self, method: str, endpoint: str, **kwargs) -> requests.Response:
        """
        Make authenticated API request.
        
        Args:
            method: HTTP method (GET, POST, etc.)
            endpoint: API endpoint (without base URL)
            **kwargs: Additional arguments for requests
            
        Returns:
            Response object
        """
        if not self.access_token:
            raise RuntimeError("Not authenticated. Call authenticate() first.")
        
        url = f"{self.base_url}/{endpoint.lstrip('/')}"
        headers = kwargs.pop("headers", {})
        
        # Amplenote uses Bearer token for OAuth, but API key might need different format
        # Try Bearer first, but log the request for debugging
        headers["Authorization"] = f"Bearer {self.access_token}"
        
        logger.debug(f"Making {method} request to {url}")
        logger.debug(f"Using token: {self.access_token[:20]}...")
        
        response = requests.request(method, url, headers=headers, **kwargs)
        
        # Log response for debugging
        if response.status_code != 200 and response.status_code != 201:
            logger.error(f"Request failed with status {response.status_code}: {response.text}")
        
        response.raise_for_status()
        return response
    
    # ==================== Notes API ====================
    
    def list_notes(self, since: Optional[int] = None) -> List[Dict[str, Any]]:
        """
        List all notes.
        
        Args:
            since: Unix timestamp for partial updates (optional)
            
        Returns:
            List of note objects
        """
        params = {}
        if since:
            params["since"] = since
        
        response = self._make_request("GET", "/notes", params=params)
        return response.json()
    
    def list_deleted_notes(self) -> List[Dict[str, Any]]:
        """
        List deleted notes.
        
        Returns:
            List of deleted note objects
        """
        response = self._make_request("GET", "/notes/deleted")
        return response.json()
    
    def create_note(
        self,
        name: str,
        tags: Optional[List[str]] = None,
        created_timestamp: Optional[int] = None,
        changed_timestamp: Optional[int] = None
    ) -> Dict[str, Any]:
        """
        Create a new note.
        
        Args:
            name: Note title
            tags: List of tag names (optional)
            created_timestamp: Unix timestamp for creation time (optional)
            changed_timestamp: Unix timestamp for last change time (optional)
            
        Returns:
            Created note object
        """
        data = {"name": name}
        
        if tags:
            data["tags"] = [{"text": tag} for tag in tags]
        
        if created_timestamp or changed_timestamp:
            data["timestamps"] = {}
            if created_timestamp:
                data["timestamps"]["created"] = created_timestamp
            if changed_timestamp:
                data["timestamps"]["changed"] = changed_timestamp
        
        response = self._make_request("POST", "/notes", json=data)
        return response.json()
    
    def restore_note(self, note_uuid: str) -> Dict[str, Any]:
        """
        Restore a deleted note.
        
        Args:
            note_uuid: UUID of the note to restore
            
        Returns:
            Restored note object
        """
        response = self._make_request("PATCH", f"/notes/{note_uuid}/restore")
        return response.json()
    
    # ==================== Content Actions API ====================
    
    def insert_content(
        self,
        note_uuid: str,
        content: str,
        content_type: str = "paragraph",
        silent: bool = False
    ) -> None:
        """
        Insert content into a note.
        
        Args:
            note_uuid: UUID of the note
            content: Text content to insert
            content_type: Type of content (paragraph, check_list_item, bullet_list_item)
            silent: If True, don't trigger notifications
        """
        nodes = self._build_content_nodes(content, content_type)
        
        action_data = {
            "type": "INSERT_NODES",
            "nodes": nodes,
            "silent": silent
        }
        
        self._make_request("POST", f"/notes/{note_uuid}/actions", json=action_data)
    
    def insert_task(
        self,
        note_uuid: str,
        task_text: str,
        due: Optional[int] = None,
        flags: Optional[str] = None,
        silent: bool = False
    ) -> None:
        """
        Insert a task into a note.
        
        Args:
            note_uuid: UUID of the note
            task_text: Task description
            due: Unix timestamp for due date (optional)
            flags: Task flags like "I" (important), "U" (urgent) (optional)
            silent: If True, don't trigger notifications
        """
        task_node = {
            "type": "check_list_item",
            "content": [
                {
                    "type": "paragraph",
                    "content": [{"type": "text", "text": task_text}]
                }
            ]
        }
        
        # Add task attributes
        if due or flags:
            task_node["attrs"] = {}
            if due:
                task_node["attrs"]["due"] = due
            if flags:
                task_node["attrs"]["flags"] = flags
        
        action_data = {
            "type": "INSERT_NODES",
            "nodes": [task_node],
            "silent": silent
        }
        
        self._make_request("POST", f"/notes/{note_uuid}/actions", json=action_data)
    
    def insert_link(
        self,
        note_uuid: str,
        url: str,
        link_text: str,
        description: Optional[str] = None,
        silent: bool = False
    ) -> None:
        """
        Insert a link into a note.
        
        Args:
            note_uuid: UUID of the note
            url: URL to link to
            link_text: Display text for the link
            description: Optional description for Rich Footnote
            silent: If True, don't trigger notifications
        """
        link_node = {
            "type": "paragraph",
            "content": [
                {
                    "type": "link",
                    "attrs": {"href": url},
                    "content": [{"type": "text", "text": link_text}]
                }
            ]
        }
        
        # Add description if provided
        if description:
            link_node["content"][0]["attrs"]["description"] = description
        
        action_data = {
            "type": "INSERT_NODES",
            "nodes": [link_node],
            "silent": silent
        }
        
        self._make_request("POST", f"/notes/{note_uuid}/actions", json=action_data)
    
    def _build_content_nodes(self, content: str, content_type: str) -> List[Dict[str, Any]]:
        """Build content nodes for INSERT_NODES action."""
        if content_type == "paragraph":
            return [
                {
                    "type": "paragraph",
                    "content": [{"type": "text", "text": content}]
                }
            ]
        elif content_type == "check_list_item":
            return [
                {
                    "type": "check_list_item",
                    "content": [
                        {
                            "type": "paragraph",
                            "content": [{"type": "text", "text": content}]
                        }
                    ]
                }
            ]
        elif content_type == "bullet_list_item":
            return [
                {
                    "type": "bullet_list_item",
                    "content": [
                        {
                            "type": "paragraph",
                            "content": [{"type": "text", "text": content}]
                        }
                    ]
                }
            ]
        else:
            raise ValueError(f"Unsupported content type: {content_type}")
    
    # ==================== Media API ====================
    
    def upload_media(
        self,
        note_uuid: str,
        file_path: str,
        mime_type: Optional[str] = None
    ) -> str:
        """
        Upload a media file to a note.
        
        Args:
            note_uuid: UUID of the note
            file_path: Path to the media file
            mime_type: MIME type (auto-detected if not provided)
            
        Returns:
            URL of the uploaded media file
        """
        file_path = Path(file_path)
        
        if not file_path.exists():
            raise FileNotFoundError(f"File not found: {file_path}")
        
        # Detect MIME type if not provided
        if not mime_type:
            import mimetypes
            mime_type, _ = mimetypes.guess_type(str(file_path))
            if not mime_type:
                mime_type = "application/octet-stream"
        
        file_size = file_path.stat().st_size
        
        # Step 1: Get pre-signed upload URL
        presign_data = {
            "size": file_size,
            "type": mime_type
        }
        
        response = self._make_request(
            "POST",
            f"/notes/{note_uuid}/media",
            json=presign_data
        )
        upload_info = response.json()
        
        upload_url = upload_info["url"]
        file_uuid = upload_info["uuid"]
        src_url = upload_info["src"]
        
        # Step 2: Upload file to pre-signed URL
        with open(file_path, 'rb') as f:
            file_data = f.read()
        
        headers = {
            "Content-Type": mime_type,
            "Content-Length": str(file_size)
        }
        
        upload_response = requests.put(upload_url, data=file_data, headers=headers)
        upload_response.raise_for_status()
        
        # Step 3: Mark upload as completed
        complete_data = {
            "local_uuid": file_uuid,
            "silent": False
        }
        
        self._make_request(
            "PUT",
            f"/notes/{note_uuid}/media/{file_uuid}",
            json=complete_data
        )
        
        logger.info(f"Media uploaded successfully: {src_url}")
        return src_url
    
    # ==================== Utility Methods ====================
    
    def is_authenticated(self) -> bool:
        """Check if service is authenticated."""
        return self.access_token is not None
    
    def clear_authentication(self):
        """Clear stored authentication tokens."""
        self.access_token = None
        self.refresh_token = None
        if self.token_file.exists():
            self.token_file.unlink()
        logger.info("Cleared Amplenote authentication")
