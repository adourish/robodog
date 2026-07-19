"""
SharePoint Service - Handles SharePoint Online API integration
Supports OAuth2 authentication and CRUD operations for sites, lists, and documents
"""

import json
import requests
from typing import Optional, Dict, List, Any


class SharePointService:
    """Service for interacting with SharePoint Online via Microsoft Graph API"""
    
    def __init__(self, config: Optional[Dict] = None):
        """
        Initialize SharePoint service
        
        Args:
            config: Configuration dict with:
                - tenant_id: Azure AD tenant ID
                - client_id: Azure AD app client ID
                - client_secret: Azure AD app client secret
                - site_url: SharePoint site URL (optional)
        """
        self.config = config or {}
        self.tenant_id = self.config.get('tenant_id', '')
        self.client_id = self.config.get('client_id', '')
        self.client_secret = self.config.get('client_secret', '')
        self.site_url = self.config.get('site_url', '')
        
        self.access_token = None
        self.site_id = None
        
        # Microsoft Graph API endpoints
        self.graph_url = 'https://graph.microsoft.com/v1.0'
        self.token_url = f'https://login.microsoftonline.com/{self.tenant_id}/oauth2/v2.0/token'
    
    def authenticate(self) -> bool:
        """
        Authenticate with Microsoft Graph API using client credentials flow
        
        Returns:
            bool: True if authentication successful
        """
        if not self.tenant_id or not self.client_id or not self.client_secret:
            raise ValueError("Missing required credentials: tenant_id, client_id, or client_secret")
        
        data = {
            'client_id': self.client_id,
            'client_secret': self.client_secret,
            'scope': 'https://graph.microsoft.com/.default',
            'grant_type': 'client_credentials'
        }
        
        response = requests.post(self.token_url, data=data)
        
        if response.status_code == 200:
            token_data = response.json()
            self.access_token = token_data.get('access_token')
            return True
        else:
            raise Exception(f"Authentication failed: {response.text}")
    
    def is_authenticated(self) -> bool:
        """Check if authenticated"""
        return self.access_token is not None
    
    def _get_headers(self) -> Dict[str, str]:
        """Get authorization headers"""
        if not self.access_token:
            raise Exception("Not authenticated. Call authenticate() first.")
        
        return {
            'Authorization': f'Bearer {self.access_token}',
            'Content-Type': 'application/json',
            'Accept': 'application/json'
        }
    
    # ==================== Site Operations ====================
    
    def get_site_by_url(self, site_url: str) -> Dict[str, Any]:
        """
        Get site information by URL
        
        Args:
            site_url: SharePoint site URL (e.g., 'contoso.sharepoint.com:/sites/team')
        
        Returns:
            dict: Site information
        """
        url = f'{self.graph_url}/sites/{site_url}'
        response = requests.get(url, headers=self._get_headers())
        
        if response.status_code == 200:
            site = response.json()
            self.site_id = site.get('id')
            return site
        else:
            raise Exception(f"Failed to get site: {response.text}")
    
    def get_site(self, site_id: Optional[str] = None) -> Dict[str, Any]:
        """
        Get site information by ID
        
        Args:
            site_id: SharePoint site ID (uses stored site_id if not provided)
        
        Returns:
            dict: Site information
        """
        site_id = site_id or self.site_id
        if not site_id:
            raise ValueError("No site_id provided or stored")
        
        url = f'{self.graph_url}/sites/{site_id}'
        response = requests.get(url, headers=self._get_headers())
        
        if response.status_code == 200:
            return response.json()
        else:
            raise Exception(f"Failed to get site: {response.text}")
    
    def search_sites(self, query: str) -> List[Dict[str, Any]]:
        """
        Search for SharePoint sites
        
        Args:
            query: Search query
        
        Returns:
            list: List of matching sites
        """
        url = f'{self.graph_url}/sites?search={query}'
        response = requests.get(url, headers=self._get_headers())
        
        if response.status_code == 200:
            return response.json().get('value', [])
        else:
            raise Exception(f"Failed to search sites: {response.text}")
    
    # ==================== List Operations ====================
    
    def get_lists(self, site_id: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        Get all lists in a site
        
        Args:
            site_id: SharePoint site ID
        
        Returns:
            list: List of lists
        """
        site_id = site_id or self.site_id
        if not site_id:
            raise ValueError("No site_id provided or stored")
        
        url = f'{self.graph_url}/sites/{site_id}/lists'
        response = requests.get(url, headers=self._get_headers())
        
        if response.status_code == 200:
            return response.json().get('value', [])
        else:
            raise Exception(f"Failed to get lists: {response.text}")
    
    def get_list(self, list_id: str, site_id: Optional[str] = None) -> Dict[str, Any]:
        """
        Get list information
        
        Args:
            list_id: List ID or display name
            site_id: SharePoint site ID
        
        Returns:
            dict: List information
        """
        site_id = site_id or self.site_id
        if not site_id:
            raise ValueError("No site_id provided or stored")
        
        url = f'{self.graph_url}/sites/{site_id}/lists/{list_id}'
        response = requests.get(url, headers=self._get_headers())
        
        if response.status_code == 200:
            return response.json()
        else:
            raise Exception(f"Failed to get list: {response.text}")
    
    def create_list(self, display_name: str, template: str = 'genericList', 
                   site_id: Optional[str] = None) -> Dict[str, Any]:
        """
        Create a new list
        
        Args:
            display_name: List display name
            template: List template (genericList, documentLibrary, etc.)
            site_id: SharePoint site ID
        
        Returns:
            dict: Created list information
        """
        site_id = site_id or self.site_id
        if not site_id:
            raise ValueError("No site_id provided or stored")
        
        url = f'{self.graph_url}/sites/{site_id}/lists'
        data = {
            'displayName': display_name,
            'list': {
                'template': template
            }
        }
        
        response = requests.post(url, headers=self._get_headers(), json=data)
        
        if response.status_code == 201:
            return response.json()
        else:
            raise Exception(f"Failed to create list: {response.text}")
    
    def delete_list(self, list_id: str, site_id: Optional[str] = None) -> bool:
        """
        Delete a list
        
        Args:
            list_id: List ID
            site_id: SharePoint site ID
        
        Returns:
            bool: True if deleted successfully
        """
        site_id = site_id or self.site_id
        if not site_id:
            raise ValueError("No site_id provided or stored")
        
        url = f'{self.graph_url}/sites/{site_id}/lists/{list_id}'
        response = requests.delete(url, headers=self._get_headers())
        
        if response.status_code == 204:
            return True
        else:
            raise Exception(f"Failed to delete list: {response.text}")
    
    # ==================== List Item Operations ====================
    
    def get_list_items(self, list_id: str, site_id: Optional[str] = None, 
                      expand: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        Get items from a list
        
        Args:
            list_id: List ID
            site_id: SharePoint site ID
            expand: Fields to expand (e.g., 'fields')
        
        Returns:
            list: List items
        """
        site_id = site_id or self.site_id
        if not site_id:
            raise ValueError("No site_id provided or stored")
        
        url = f'{self.graph_url}/sites/{site_id}/lists/{list_id}/items'
        if expand:
            url += f'?expand={expand}'
        
        response = requests.get(url, headers=self._get_headers())
        
        if response.status_code == 200:
            return response.json().get('value', [])
        else:
            raise Exception(f"Failed to get list items: {response.text}")
    
    def get_list_item(self, list_id: str, item_id: str, 
                     site_id: Optional[str] = None) -> Dict[str, Any]:
        """
        Get a specific list item
        
        Args:
            list_id: List ID
            item_id: Item ID
            site_id: SharePoint site ID
        
        Returns:
            dict: List item
        """
        site_id = site_id or self.site_id
        if not site_id:
            raise ValueError("No site_id provided or stored")
        
        url = f'{self.graph_url}/sites/{site_id}/lists/{list_id}/items/{item_id}?expand=fields'
        response = requests.get(url, headers=self._get_headers())
        
        if response.status_code == 200:
            return response.json()
        else:
            raise Exception(f"Failed to get list item: {response.text}")
    
    def create_list_item(self, list_id: str, fields: Dict[str, Any], 
                        site_id: Optional[str] = None) -> Dict[str, Any]:
        """
        Create a list item
        
        Args:
            list_id: List ID
            fields: Item fields as dict
            site_id: SharePoint site ID
        
        Returns:
            dict: Created item
        """
        site_id = site_id or self.site_id
        if not site_id:
            raise ValueError("No site_id provided or stored")
        
        url = f'{self.graph_url}/sites/{site_id}/lists/{list_id}/items'
        data = {'fields': fields}
        
        response = requests.post(url, headers=self._get_headers(), json=data)
        
        if response.status_code == 201:
            return response.json()
        else:
            raise Exception(f"Failed to create list item: {response.text}")
    
    def update_list_item(self, list_id: str, item_id: str, fields: Dict[str, Any],
                        site_id: Optional[str] = None) -> Dict[str, Any]:
        """
        Update a list item
        
        Args:
            list_id: List ID
            item_id: Item ID
            fields: Fields to update
            site_id: SharePoint site ID
        
        Returns:
            dict: Updated item
        """
        site_id = site_id or self.site_id
        if not site_id:
            raise ValueError("No site_id provided or stored")
        
        url = f'{self.graph_url}/sites/{site_id}/lists/{list_id}/items/{item_id}/fields'
        
        response = requests.patch(url, headers=self._get_headers(), json=fields)
        
        if response.status_code == 200:
            return response.json()
        else:
            raise Exception(f"Failed to update list item: {response.text}")
    
    def delete_list_item(self, list_id: str, item_id: str, 
                        site_id: Optional[str] = None) -> bool:
        """
        Delete a list item
        
        Args:
            list_id: List ID
            item_id: Item ID
            site_id: SharePoint site ID
        
        Returns:
            bool: True if deleted successfully
        """
        site_id = site_id or self.site_id
        if not site_id:
            raise ValueError("No site_id provided or stored")
        
        url = f'{self.graph_url}/sites/{site_id}/lists/{list_id}/items/{item_id}'
        response = requests.delete(url, headers=self._get_headers())
        
        if response.status_code == 204:
            return True
        else:
            raise Exception(f"Failed to delete list item: {response.text}")
    
    # ==================== Document Library Operations ====================
    
    def get_drive(self, site_id: Optional[str] = None) -> Dict[str, Any]:
        """
        Get default document library (drive) for a site
        
        Args:
            site_id: SharePoint site ID
        
        Returns:
            dict: Drive information
        """
        site_id = site_id or self.site_id
        if not site_id:
            raise ValueError("No site_id provided or stored")
        
        url = f'{self.graph_url}/sites/{site_id}/drive'
        response = requests.get(url, headers=self._get_headers())
        
        if response.status_code == 200:
            return response.json()
        else:
            raise Exception(f"Failed to get drive: {response.text}")
    
    def get_files(self, folder_path: str = 'root', site_id: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        Get files from a folder
        
        Args:
            folder_path: Folder path (default: 'root')
            site_id: SharePoint site ID
        
        Returns:
            list: Files and folders
        """
        site_id = site_id or self.site_id
        if not site_id:
            raise ValueError("No site_id provided or stored")
        
        url = f'{self.graph_url}/sites/{site_id}/drive/{folder_path}/children'
        response = requests.get(url, headers=self._get_headers())
        
        if response.status_code == 200:
            return response.json().get('value', [])
        else:
            raise Exception(f"Failed to get files: {response.text}")
    
    def upload_file(self, file_path: str, content: bytes, 
                   site_id: Optional[str] = None) -> Dict[str, Any]:
        """
        Upload a file to SharePoint
        
        Args:
            file_path: Path where to upload (e.g., 'Documents/file.txt')
            content: File content as bytes
            site_id: SharePoint site ID
        
        Returns:
            dict: Uploaded file information
        """
        site_id = site_id or self.site_id
        if not site_id:
            raise ValueError("No site_id provided or stored")
        
        url = f'{self.graph_url}/sites/{site_id}/drive/root:/{file_path}:/content'
        headers = self._get_headers()
        headers['Content-Type'] = 'application/octet-stream'
        
        response = requests.put(url, headers=headers, data=content)
        
        if response.status_code in [200, 201]:
            return response.json()
        else:
            raise Exception(f"Failed to upload file: {response.text}")
    
    def download_file(self, file_path: str, site_id: Optional[str] = None) -> bytes:
        """
        Download a file from SharePoint
        
        Args:
            file_path: File path (e.g., 'Documents/file.txt')
            site_id: SharePoint site ID
        
        Returns:
            bytes: File content
        """
        site_id = site_id or self.site_id
        if not site_id:
            raise ValueError("No site_id provided or stored")
        
        url = f'{self.graph_url}/sites/{site_id}/drive/root:/{file_path}:/content'
        response = requests.get(url, headers=self._get_headers())
        
        if response.status_code == 200:
            return response.content
        else:
            raise Exception(f"Failed to download file: {response.text}")
    
    def delete_file(self, file_path: str, site_id: Optional[str] = None) -> bool:
        """
        Delete a file from SharePoint
        
        Args:
            file_path: File path (e.g., 'Documents/file.txt')
            site_id: SharePoint site ID
        
        Returns:
            bool: True if deleted successfully
        """
        site_id = site_id or self.site_id
        if not site_id:
            raise ValueError("No site_id provided or stored")
        
        url = f'{self.graph_url}/sites/{site_id}/drive/root:/{file_path}'
        response = requests.delete(url, headers=self._get_headers())
        
        if response.status_code == 204:
            return True
        else:
            raise Exception(f"Failed to delete file: {response.text}")
    
    def search_files(self, query: str, site_id: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        Search for files in SharePoint
        
        Args:
            query: Search query
            site_id: SharePoint site ID
        
        Returns:
            list: Matching files
        """
        site_id = site_id or self.site_id
        if not site_id:
            raise ValueError("No site_id provided or stored")
        
        url = f'{self.graph_url}/sites/{site_id}/drive/root/search(q=\'{query}\')'
        response = requests.get(url, headers=self._get_headers())
        
        if response.status_code == 200:
            return response.json().get('value', [])
        else:
            raise Exception(f"Failed to search files: {response.text}")


# Example usage
if __name__ == '__main__':
    print("SharePoint Service initialized")
    print("\nTo use:")
    print("  service = SharePointService(config)")
    print("  service.authenticate()")
    print("  sites = service.search_sites('team')")
