# file: todoist_service.py
#!/usr/bin/env python3
"""Todoist API integration with OAuth2 authentication."""

import os
import json
import secrets
import webbrowser
import requests
from pathlib import Path
from typing import Dict, List, Optional, Any
from urllib.parse import urlencode, parse_qs, urlparse
from datetime import datetime, timedelta
import logging

logger = logging.getLogger('robodog.todoist')


class TodoistService:
    """Service for interacting with Todoist API using OAuth2 flow."""
    
    def __init__(self, config: Dict[str, Any]):
        """
        Initialize Todoist service.
        
        Args:
            config: Configuration dictionary containing:
                - baseUrl: API base URL
                - authUrl: OAuth authorization URL
                - tokenUrl: OAuth token URL
                - clientId: OAuth client ID
                - clientSecret: OAuth client secret
                - scopes: List of OAuth scopes
        """
        self.base_url = config.get("baseUrl", "https://api.todoist.com/rest/v2")
        self.auth_url = config.get("authUrl", "https://todoist.com/oauth/authorize")
        self.token_url = config.get("tokenUrl", "https://todoist.com/oauth/access_token")
        self.client_id = config.get("clientId", "")
        self.client_secret = config.get("clientSecret", "")
        self.scopes = config.get("scopes", ["data:read_write", "data:delete"])
        
        # Token storage
        self.token_file = Path.home() / ".robodog" / "todoist_token.json"
        self.token_file.parent.mkdir(parents=True, exist_ok=True)
        
        self.access_token = None
        self._load_token()
    
    def _load_token(self):
        """Load stored access token if available."""
        if self.token_file.exists():
            try:
                with open(self.token_file, 'r') as f:
                    data = json.load(f)
                    self.access_token = data.get("access_token")
                    logger.info("Loaded Todoist access token from storage")
            except Exception as e:
                logger.warning(f"Failed to load token: {e}")
    
    def _save_token(self, token_data: Dict[str, str]):
        """Save access token to storage."""
        try:
            with open(self.token_file, 'w') as f:
                json.dump(token_data, f, indent=2)
            logger.info("Saved Todoist access token to storage")
        except Exception as e:
            logger.error(f"Failed to save token: {e}")
    
    def authenticate(self, redirect_uri: str = "http://localhost:8080") -> bool:
        """
        Perform OAuth2 authentication flow.
        
        Args:
            redirect_uri: OAuth redirect URI
            
        Returns:
            True if authentication successful, False otherwise
        """
        if not self.client_id or not self.client_secret:
            logger.error("Client ID and Client Secret are required. Please update config.yaml")
            print("\n" + "="*60)
            print("TODOIST AUTHENTICATION SETUP")
            print("="*60)
            print("\nTo use Todoist integration, you need to:")
            print("1. Go to https://developer.todoist.com/appconsole.html")
            print("2. Create a new app")
            print("3. Add your client ID and secret to config.yaml")
            print("4. Set redirect URI to: http://localhost:8080")
            print("\nExample config.yaml:")
            print("  - provider: todoist")
            print("    clientId: \"your_client_id\"")
            print("    clientSecret: \"your_client_secret\"")
            return False
        
        # Generate state for CSRF protection
        state = secrets.token_urlsafe(16)
        
        # Build authorization URL
        auth_params = {
            "client_id": self.client_id,
            "scope": ",".join(self.scopes),
            "state": state
        }
        
        auth_url_full = f"{self.auth_url}?{urlencode(auth_params)}"
        
        print("\n" + "="*60)
        print("TODOIST AUTHENTICATION")
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
        returned_state = params.get("state", [""])[0]
        
        # Verify state (CSRF protection)
        if returned_state != state:
            logger.error("State mismatch - possible CSRF attack")
            return False
        
        # Exchange authorization code for access token
        token_data = {
            "client_id": self.client_id,
            "client_secret": self.client_secret,
            "code": auth_code
        }
        
        try:
            response = requests.post(self.token_url, data=token_data)
            response.raise_for_status()
            
            token_response = response.json()
            self.access_token = token_response.get("access_token")
            
            self._save_token(token_response)
            
            print("\n✓ Authentication successful!")
            return True
            
        except requests.exceptions.RequestException as e:
            logger.error(f"Token exchange failed: {e}")
            if hasattr(e, 'response') and e.response is not None:
                logger.error(f"Response: {e.response.text}")
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
        headers["Authorization"] = f"Bearer {self.access_token}"
        
        response = requests.request(method, url, headers=headers, **kwargs)
        response.raise_for_status()
        return response
    
    # ==================== Projects API ====================
    
    def get_projects(self) -> List[Dict[str, Any]]:
        """
        Get all projects.
        
        Returns:
            List of project objects
        """
        response = self._make_request("GET", "/projects")
        return response.json()
    
    def create_project(
        self,
        name: str,
        color: Optional[str] = None,
        parent_id: Optional[str] = None,
        is_favorite: bool = False,
        view_style: str = "list"
    ) -> Dict[str, Any]:
        """
        Create a new project.
        
        Args:
            name: Project name
            color: Project color (e.g., "red", "blue")
            parent_id: Parent project ID for nested projects
            is_favorite: Whether to mark as favorite
            view_style: View style ("list" or "board")
            
        Returns:
            Created project object
        """
        data = {
            "name": name,
            "is_favorite": is_favorite,
            "view_style": view_style
        }
        
        if color:
            data["color"] = color
        if parent_id:
            data["parent_id"] = parent_id
        
        response = self._make_request("POST", "/projects", json=data)
        return response.json()
    
    def get_project(self, project_id: str) -> Dict[str, Any]:
        """
        Get a specific project.
        
        Args:
            project_id: Project ID
            
        Returns:
            Project object
        """
        response = self._make_request("GET", f"/projects/{project_id}")
        return response.json()
    
    def update_project(
        self,
        project_id: str,
        name: Optional[str] = None,
        color: Optional[str] = None,
        is_favorite: Optional[bool] = None
    ) -> Dict[str, Any]:
        """
        Update a project.
        
        Args:
            project_id: Project ID
            name: New project name
            color: New project color
            is_favorite: New favorite status
            
        Returns:
            Updated project object
        """
        data = {}
        if name:
            data["name"] = name
        if color:
            data["color"] = color
        if is_favorite is not None:
            data["is_favorite"] = is_favorite
        
        response = self._make_request("POST", f"/projects/{project_id}", json=data)
        return response.json()
    
    def delete_project(self, project_id: str) -> None:
        """
        Delete a project.
        
        Args:
            project_id: Project ID
        """
        self._make_request("DELETE", f"/projects/{project_id}")
    
    # ==================== Tasks API ====================
    
    def get_tasks(
        self,
        project_id: Optional[str] = None,
        label: Optional[str] = None,
        filter_query: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        Get active tasks.
        
        Args:
            project_id: Filter by project ID
            label: Filter by label name
            filter_query: Filter query (e.g., "today", "overdue")
            
        Returns:
            List of task objects
        """
        params = {}
        if project_id:
            params["project_id"] = project_id
        if label:
            params["label"] = label
        if filter_query:
            params["filter"] = filter_query
        
        response = self._make_request("GET", "/tasks", params=params)
        return response.json()
    
    def create_task(
        self,
        content: str,
        description: Optional[str] = None,
        project_id: Optional[str] = None,
        due_string: Optional[str] = None,
        due_date: Optional[str] = None,
        priority: int = 1,
        labels: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        """
        Create a new task.
        
        Args:
            content: Task content (title)
            description: Task description
            project_id: Project ID
            due_string: Natural language due date (e.g., "tomorrow", "next Monday")
            due_date: Due date in YYYY-MM-DD format
            priority: Priority (1-4, where 4 is highest)
            labels: List of label names
            
        Returns:
            Created task object
        """
        data = {
            "content": content,
            "priority": priority
        }
        
        if description:
            data["description"] = description
        if project_id:
            data["project_id"] = project_id
        if due_string:
            data["due_string"] = due_string
        elif due_date:
            data["due_date"] = due_date
        if labels:
            data["labels"] = labels
        
        response = self._make_request("POST", "/tasks", json=data)
        return response.json()
    
    def get_task(self, task_id: str) -> Dict[str, Any]:
        """
        Get a specific task.
        
        Args:
            task_id: Task ID
            
        Returns:
            Task object
        """
        response = self._make_request("GET", f"/tasks/{task_id}")
        return response.json()
    
    def update_task(
        self,
        task_id: str,
        content: Optional[str] = None,
        description: Optional[str] = None,
        due_string: Optional[str] = None,
        priority: Optional[int] = None,
        labels: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        """
        Update a task.
        
        Args:
            task_id: Task ID
            content: New task content
            description: New task description
            due_string: New due date (natural language)
            priority: New priority (1-4)
            labels: New labels list
            
        Returns:
            Updated task object
        """
        data = {}
        if content:
            data["content"] = content
        if description:
            data["description"] = description
        if due_string:
            data["due_string"] = due_string
        if priority:
            data["priority"] = priority
        if labels:
            data["labels"] = labels
        
        response = self._make_request("POST", f"/tasks/{task_id}", json=data)
        return response.json()
    
    def close_task(self, task_id: str) -> None:
        """
        Close (complete) a task.
        
        Args:
            task_id: Task ID
        """
        self._make_request("POST", f"/tasks/{task_id}/close")
    
    def reopen_task(self, task_id: str) -> None:
        """
        Reopen a completed task.
        
        Args:
            task_id: Task ID
        """
        self._make_request("POST", f"/tasks/{task_id}/reopen")
    
    def delete_task(self, task_id: str) -> None:
        """
        Delete a task.
        
        Args:
            task_id: Task ID
        """
        self._make_request("DELETE", f"/tasks/{task_id}")
    
    # ==================== Sections API ====================
    
    def get_sections(self, project_id: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        Get all sections.
        
        Args:
            project_id: Filter by project ID
            
        Returns:
            List of section objects
        """
        params = {}
        if project_id:
            params["project_id"] = project_id
        
        response = self._make_request("GET", "/sections", params=params)
        return response.json()
    
    def create_section(
        self,
        name: str,
        project_id: str,
        order: Optional[int] = None
    ) -> Dict[str, Any]:
        """
        Create a new section.
        
        Args:
            name: Section name
            project_id: Project ID
            order: Section order
            
        Returns:
            Created section object
        """
        data = {
            "name": name,
            "project_id": project_id
        }
        
        if order is not None:
            data["order"] = order
        
        response = self._make_request("POST", "/sections", json=data)
        return response.json()
    
    def update_section(self, section_id: str, name: str) -> Dict[str, Any]:
        """
        Update a section.
        
        Args:
            section_id: Section ID
            name: New section name
            
        Returns:
            Updated section object
        """
        data = {"name": name}
        response = self._make_request("POST", f"/sections/{section_id}", json=data)
        return response.json()
    
    def delete_section(self, section_id: str) -> None:
        """
        Delete a section.
        
        Args:
            section_id: Section ID
        """
        self._make_request("DELETE", f"/sections/{section_id}")
    
    # ==================== Labels API ====================
    
    def get_labels(self) -> List[Dict[str, Any]]:
        """
        Get all labels.
        
        Returns:
            List of label objects
        """
        response = self._make_request("GET", "/labels")
        return response.json()
    
    def create_label(
        self,
        name: str,
        color: Optional[str] = None,
        is_favorite: bool = False
    ) -> Dict[str, Any]:
        """
        Create a new label.
        
        Args:
            name: Label name
            color: Label color
            is_favorite: Whether to mark as favorite
            
        Returns:
            Created label object
        """
        data = {
            "name": name,
            "is_favorite": is_favorite
        }
        
        if color:
            data["color"] = color
        
        response = self._make_request("POST", "/labels", json=data)
        return response.json()
    
    def update_label(
        self,
        label_id: str,
        name: Optional[str] = None,
        color: Optional[str] = None,
        is_favorite: Optional[bool] = None
    ) -> Dict[str, Any]:
        """
        Update a label.
        
        Args:
            label_id: Label ID
            name: New label name
            color: New label color
            is_favorite: New favorite status
            
        Returns:
            Updated label object
        """
        data = {}
        if name:
            data["name"] = name
        if color:
            data["color"] = color
        if is_favorite is not None:
            data["is_favorite"] = is_favorite
        
        response = self._make_request("POST", f"/labels/{label_id}", json=data)
        return response.json()
    
    def delete_label(self, label_id: str) -> None:
        """
        Delete a label.
        
        Args:
            label_id: Label ID
        """
        self._make_request("DELETE", f"/labels/{label_id}")
    
    # ==================== Comments API ====================
    
    def get_comments(
        self,
        task_id: Optional[str] = None,
        project_id: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        Get comments.
        
        Args:
            task_id: Filter by task ID
            project_id: Filter by project ID
            
        Returns:
            List of comment objects
        """
        params = {}
        if task_id:
            params["task_id"] = task_id
        elif project_id:
            params["project_id"] = project_id
        
        response = self._make_request("GET", "/comments", params=params)
        return response.json()
    
    def create_comment(
        self,
        content: str,
        task_id: Optional[str] = None,
        project_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Create a comment.
        
        Args:
            content: Comment content
            task_id: Task ID (for task comment)
            project_id: Project ID (for project comment)
            
        Returns:
            Created comment object
        """
        data = {"content": content}
        
        if task_id:
            data["task_id"] = task_id
        elif project_id:
            data["project_id"] = project_id
        else:
            raise ValueError("Either task_id or project_id must be provided")
        
        response = self._make_request("POST", "/comments", json=data)
        return response.json()
    
    def update_comment(self, comment_id: str, content: str) -> Dict[str, Any]:
        """
        Update a comment.
        
        Args:
            comment_id: Comment ID
            content: New comment content
            
        Returns:
            Updated comment object
        """
        data = {"content": content}
        response = self._make_request("POST", f"/comments/{comment_id}", json=data)
        return response.json()
    
    def delete_comment(self, comment_id: str) -> None:
        """
        Delete a comment.
        
        Args:
            comment_id: Comment ID
        """
        self._make_request("DELETE", f"/comments/{comment_id}")
    
    # ==================== Utility Methods ====================
    
    def is_authenticated(self) -> bool:
        """Check if service is authenticated."""
        return self.access_token is not None
    
    def clear_authentication(self):
        """Clear stored authentication tokens."""
        self.access_token = None
        if self.token_file.exists():
            self.token_file.unlink()
        logger.info("Cleared Todoist authentication")
    
    def get_quick_add_task(self, text: str) -> Dict[str, Any]:
        """
        Parse natural language task using Quick Add format.
        
        Args:
            text: Natural language task (e.g., "Buy milk tomorrow p1 @shopping")
            
        Returns:
            Parsed task components
        """
        # This is a simplified parser - Todoist's actual Quick Add is more sophisticated
        parts = {
            "content": text,
            "priority": 1,
            "labels": [],
            "due_string": None
        }
        
        # Extract priority (p1-p4)
        import re
        priority_match = re.search(r'\bp([1-4])\b', text)
        if priority_match:
            parts["priority"] = int(priority_match.group(1))
            text = text.replace(priority_match.group(0), "").strip()
        
        # Extract labels (@label)
        label_matches = re.findall(r'@(\w+)', text)
        if label_matches:
            parts["labels"] = label_matches
            for label in label_matches:
                text = text.replace(f"@{label}", "").strip()
        
        # Extract due date keywords
        due_keywords = ["today", "tomorrow", "next week", "next month"]
        for keyword in due_keywords:
            if keyword in text.lower():
                parts["due_string"] = keyword
                text = text.replace(keyword, "").strip()
                break
        
        parts["content"] = text.strip()
        return parts
