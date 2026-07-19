"""
GoogleService - Handles Google Docs and Gmail API integration
Supports OAuth2 authentication and CRUD operations
"""

import json
import base64
import webbrowser
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs, urlencode
import threading
import requests
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart


class OAuthCallbackHandler(BaseHTTPRequestHandler):
    """Handler for OAuth callback"""
    
    def do_GET(self):
        """Handle GET request from OAuth callback"""
        query = urlparse(self.path).query
        params = parse_qs(query)
        
        if 'code' in params:
            self.server.auth_code = params['code'][0]
            self.send_response(200)
            self.send_header('Content-type', 'text/html')
            self.end_headers()
            self.wfile.write(b'<html><body><h1>Authentication successful!</h1><p>You can close this window.</p></body></html>')
        else:
            self.send_response(400)
            self.send_header('Content-type', 'text/html')
            self.end_headers()
            self.wfile.write(b'<html><body><h1>Authentication failed!</h1></body></html>')
    
    def log_message(self, format, *args):
        """Suppress log messages"""
        pass


class GoogleService:
    """Google API service for Docs and Gmail"""
    
    def __init__(self, client_id=None, client_secret=None, redirect_uri='http://localhost:8080/callback'):
        self.client_id = client_id or '837032747486-0dttoe0dfkfrn9m3obimrgboj8i64leu.apps.googleusercontent.com'
        self.client_secret = client_secret  # Should be set from environment or config
        self.redirect_uri = redirect_uri
        self.scopes = [
            'https://www.googleapis.com/auth/documents',
            'https://www.googleapis.com/auth/drive.file',
            'https://www.googleapis.com/auth/gmail.send',
            'https://www.googleapis.com/auth/gmail.compose',
            'https://www.googleapis.com/auth/gmail.modify',
            'https://www.googleapis.com/auth/calendar',
            'https://www.googleapis.com/auth/calendar.events'
        ]
        self.access_token = None
        self.refresh_token = None
        self.token_expiry = None
    
    def authenticate(self):
        """Start OAuth2 authentication flow"""
        auth_url = self._build_auth_url()
        
        print(f"Opening browser for authentication...")
        print(f"If browser doesn't open, visit: {auth_url}")
        
        # Start local server to receive callback
        server = HTTPServer(('localhost', 8080), OAuthCallbackHandler)
        server.auth_code = None
        
        # Open browser
        webbrowser.open(auth_url)
        
        # Wait for callback
        print("Waiting for authentication...")
        while server.auth_code is None:
            server.handle_request()
        
        auth_code = server.auth_code
        print("Authentication code received!")
        
        # Exchange code for token
        return self._exchange_code_for_token(auth_code)
    
    def _build_auth_url(self):
        """Build OAuth2 authorization URL"""
        params = {
            'client_id': self.client_id,
            'redirect_uri': self.redirect_uri,
            'response_type': 'code',
            'scope': ' '.join(self.scopes),
            'access_type': 'offline',
            'prompt': 'consent'
        }
        return f"https://accounts.google.com/o/oauth2/v2/auth?{urlencode(params)}"
    
    def _exchange_code_for_token(self, code):
        """Exchange authorization code for access token"""
        if not self.client_secret:
            raise ValueError("Client secret is required for token exchange. Set it via environment variable or config.")
        
        token_url = 'https://oauth2.googleapis.com/token'
        data = {
            'code': code,
            'client_id': self.client_id,
            'client_secret': self.client_secret,
            'redirect_uri': self.redirect_uri,
            'grant_type': 'authorization_code'
        }
        
        response = requests.post(token_url, data=data)
        
        if response.status_code != 200:
            raise Exception(f"Token exchange failed: {response.text}")
        
        token_data = response.json()
        self.access_token = token_data['access_token']
        self.refresh_token = token_data.get('refresh_token')
        
        print("✅ Authentication successful!")
        return token_data
    
    def set_access_token(self, token, refresh_token=None):
        """Set access token manually"""
        self.access_token = token
        if refresh_token:
            self.refresh_token = refresh_token
    
    def get_access_token(self):
        """Get the current access token"""
        return self.access_token
    
    def is_authenticated(self):
        """Check if authenticated"""
        return self.access_token is not None
    
    def _get_headers(self):
        """Get authorization headers"""
        if not self.access_token:
            raise Exception("Not authenticated. Call authenticate() first.")
        return {
            'Authorization': f'Bearer {self.access_token}',
            'Content-Type': 'application/json'
        }
    
    # ==================== Google Docs API ====================
    
    def create_document(self, title, content=''):
        """Create a new Google Doc"""
        url = 'https://docs.googleapis.com/v1/documents'
        data = {'title': title}
        
        response = requests.post(url, headers=self._get_headers(), json=data)
        
        if response.status_code != 200:
            raise Exception(f"Failed to create document: {response.text}")
        
        doc = response.json()
        
        # Add content if provided
        if content:
            self.update_document(doc['documentId'], content)
        
        return doc
    
    def get_document(self, document_id):
        """Get a Google Doc"""
        url = f'https://docs.googleapis.com/v1/documents/{document_id}'
        
        response = requests.get(url, headers=self._get_headers())
        
        if response.status_code != 200:
            raise Exception(f"Failed to get document: {response.text}")
        
        return response.json()
    
    def update_document(self, document_id, content, insert_index=1):
        """Update a Google Doc"""
        url = f'https://docs.googleapis.com/v1/documents/{document_id}:batchUpdate'
        
        requests_data = [
            {
                'insertText': {
                    'location': {'index': insert_index},
                    'text': content
                }
            }
        ]
        
        data = {'requests': requests_data}
        
        response = requests.post(url, headers=self._get_headers(), json=data)
        
        if response.status_code != 200:
            raise Exception(f"Failed to update document: {response.text}")
        
        return response.json()
    
    def delete_document(self, document_id):
        """Delete a Google Doc (moves to trash)"""
        url = f'https://www.googleapis.com/drive/v3/files/{document_id}'
        
        headers = {
            'Authorization': f'Bearer {self.access_token}'
        }
        
        response = requests.delete(url, headers=headers)
        
        if response.status_code not in [200, 204]:
            raise Exception(f"Failed to delete document: {response.text}")
        
        return {'success': True}
    
    def read_document_text(self, document_id):
        """Read text content from a Google Doc"""
        doc = self.get_document(document_id)
        
        text_content = []
        if 'body' in doc and 'content' in doc['body']:
            for element in doc['body']['content']:
                if 'paragraph' in element:
                    for text_run in element['paragraph'].get('elements', []):
                        if 'textRun' in text_run:
                            text_content.append(text_run['textRun'].get('content', ''))
        
        return ''.join(text_content)
    
    # ==================== Gmail API ====================
    
    def send_email(self, to, subject, body, is_html=False, cc=None, bcc=None):
        """Send an email via Gmail"""
        message = self._create_email_message(to, subject, body, is_html, cc, bcc)
        
        url = 'https://gmail.googleapis.com/gmail/v1/users/me/messages/send'
        data = {'raw': message}
        
        response = requests.post(url, headers=self._get_headers(), json=data)
        
        if response.status_code != 200:
            raise Exception(f"Failed to send email: {response.text}")
        
        return response.json()
    
    def _create_email_message(self, to, subject, body, is_html=False, cc=None, bcc=None):
        """Create email message in RFC 2822 format"""
        if is_html:
            message = MIMEMultipart('alternative')
            message.attach(MIMEText(body, 'html'))
        else:
            message = MIMEText(body)
        
        message['To'] = to
        message['Subject'] = subject
        
        if cc:
            message['Cc'] = cc
        if bcc:
            message['Bcc'] = bcc
        
        # Encode to base64url
        raw_message = base64.urlsafe_b64encode(message.as_bytes()).decode('utf-8')
        return raw_message
    
    def list_emails(self, max_results=10, query=''):
        """List emails from Gmail"""
        url = 'https://gmail.googleapis.com/gmail/v1/users/me/messages'
        params = {
            'maxResults': max_results,
            'q': query
        }
        
        response = requests.get(url, headers=self._get_headers(), params=params)
        
        if response.status_code != 200:
            raise Exception(f"Failed to list emails: {response.text}")
        
        return response.json()
    
    def get_email(self, message_id):
        """Get a specific email"""
        url = f'https://gmail.googleapis.com/gmail/v1/users/me/messages/{message_id}'
        
        response = requests.get(url, headers=self._get_headers())
        
        if response.status_code != 200:
            raise Exception(f"Failed to get email: {response.text}")
        
        return response.json()
    
    def create_draft(self, to, subject, body, is_html=False, cc=None, bcc=None):
        """Create an email draft"""
        message = self._create_email_message(to, subject, body, is_html, cc, bcc)
        
        url = 'https://gmail.googleapis.com/gmail/v1/users/me/drafts'
        data = {
            'message': {'raw': message}
        }
        
        response = requests.post(url, headers=self._get_headers(), json=data)
        
        if response.status_code != 200:
            raise Exception(f"Failed to create draft: {response.text}")
        
        return response.json()
    
    def delete_draft(self, draft_id):
        """Delete an email draft"""
        if not self.access_token:
            raise Exception("Not authenticated. Call authenticate() first.")
        
        url = f'https://gmail.googleapis.com/gmail/v1/users/me/drafts/{draft_id}'
        headers = self._get_headers()
        
        response = requests.delete(url, headers=headers)
        
        if response.status_code != 204:
            raise Exception(f"Failed to delete draft: {response.text}")
        
        return {"deleted": True, "draft_id": draft_id}
    
    # ==================== Google Calendar API ====================
    
    def list_calendars(self):
        """List all calendars"""
        if not self.access_token:
            raise Exception("Not authenticated. Call authenticate() first.")
        
        url = 'https://www.googleapis.com/calendar/v3/users/me/calendarList'
        headers = self._get_headers()
        
        response = requests.get(url, headers=headers)
        
        if response.status_code != 200:
            raise Exception(f"Failed to list calendars: {response.text}")
        
        return response.json()
    
    def create_calendar(self, summary, description='', timezone='America/New_York'):
        """Create a new calendar"""
        if not self.access_token:
            raise Exception("Not authenticated. Call authenticate() first.")
        
        url = 'https://www.googleapis.com/calendar/v3/calendars'
        headers = self._get_headers()
        
        data = {
            'summary': summary,
            'description': description,
            'timeZone': timezone
        }
        
        response = requests.post(url, headers=headers, json=data)
        
        if response.status_code != 200:
            raise Exception(f"Failed to create calendar: {response.text}")
        
        return response.json()
    
    def get_calendar(self, calendar_id):
        """Get calendar details"""
        if not self.access_token:
            raise Exception("Not authenticated. Call authenticate() first.")
        
        url = f'https://www.googleapis.com/calendar/v3/calendars/{calendar_id}'
        headers = self._get_headers()
        
        response = requests.get(url, headers=headers)
        
        if response.status_code != 200:
            raise Exception(f"Failed to get calendar: {response.text}")
        
        return response.json()
    
    def update_calendar(self, calendar_id, summary=None, description=None, timezone=None):
        """Update calendar details"""
        if not self.access_token:
            raise Exception("Not authenticated. Call authenticate() first.")
        
        url = f'https://www.googleapis.com/calendar/v3/calendars/{calendar_id}'
        headers = self._get_headers()
        
        data = {}
        if summary:
            data['summary'] = summary
        if description is not None:
            data['description'] = description
        if timezone:
            data['timeZone'] = timezone
        
        response = requests.patch(url, headers=headers, json=data)
        
        if response.status_code != 200:
            raise Exception(f"Failed to update calendar: {response.text}")
        
        return response.json()
    
    def delete_calendar(self, calendar_id):
        """Delete a calendar"""
        if not self.access_token:
            raise Exception("Not authenticated. Call authenticate() first.")
        
        url = f'https://www.googleapis.com/calendar/v3/calendars/{calendar_id}'
        headers = self._get_headers()
        
        response = requests.delete(url, headers=headers)
        
        if response.status_code != 204:
            raise Exception(f"Failed to delete calendar: {response.text}")
        
        return {"deleted": True, "calendar_id": calendar_id}
    
    def search_calendars(self, query):
        """Search calendars by name (wildcard search)"""
        if not self.access_token:
            raise Exception("Not authenticated. Call authenticate() first.")
        
        calendars = self.list_calendars()
        items = calendars.get('items', [])
        
        # Filter by query (case-insensitive wildcard search)
        query_lower = query.lower()
        filtered = [
            cal for cal in items
            if query_lower in cal.get('summary', '').lower() or
               query_lower in cal.get('description', '').lower()
        ]
        
        return {'items': filtered, 'total': len(filtered)}
    
    # --- Calendar Events ---
    
    def list_events(self, calendar_id='primary', max_results=10, time_min=None, time_max=None, query=None):
        """List events from a calendar"""
        if not self.access_token:
            raise Exception("Not authenticated. Call authenticate() first.")
        
        url = f'https://www.googleapis.com/calendar/v3/calendars/{calendar_id}/events'
        headers = self._get_headers()
        
        params = {'maxResults': max_results}
        if time_min:
            params['timeMin'] = time_min
        if time_max:
            params['timeMax'] = time_max
        if query:
            params['q'] = query
        
        response = requests.get(url, headers=headers, params=params)
        
        if response.status_code != 200:
            raise Exception(f"Failed to list events: {response.text}")
        
        return response.json()
    
    def create_event(self, calendar_id='primary', summary='', description='', start_time='', end_time='', location='', attendees=None):
        """Create a calendar event"""
        if not self.access_token:
            raise Exception("Not authenticated. Call authenticate() first.")
        
        url = f'https://www.googleapis.com/calendar/v3/calendars/{calendar_id}/events'
        headers = self._get_headers()
        
        event = {
            'summary': summary,
            'description': description,
            'start': {'dateTime': start_time, 'timeZone': 'America/New_York'},
            'end': {'dateTime': end_time, 'timeZone': 'America/New_York'}
        }
        
        if location:
            event['location'] = location
        
        if attendees:
            event['attendees'] = [{'email': email} for email in attendees]
        
        response = requests.post(url, headers=headers, json=event)
        
        if response.status_code != 200:
            raise Exception(f"Failed to create event: {response.text}")
        
        return response.json()
    
    def get_event(self, calendar_id='primary', event_id=''):
        """Get event details"""
        if not self.access_token:
            raise Exception("Not authenticated. Call authenticate() first.")
        
        url = f'https://www.googleapis.com/calendar/v3/calendars/{calendar_id}/events/{event_id}'
        headers = self._get_headers()
        
        response = requests.get(url, headers=headers)
        
        if response.status_code != 200:
            raise Exception(f"Failed to get event: {response.text}")
        
        return response.json()
    
    def update_event(self, calendar_id='primary', event_id='', summary=None, description=None, start_time=None, end_time=None, location=None):
        """Update an event"""
        if not self.access_token:
            raise Exception("Not authenticated. Call authenticate() first.")
        
        url = f'https://www.googleapis.com/calendar/v3/calendars/{calendar_id}/events/{event_id}'
        headers = self._get_headers()
        
        # Get existing event first
        event = self.get_event(calendar_id, event_id)
        
        # Update fields
        if summary is not None:
            event['summary'] = summary
        if description is not None:
            event['description'] = description
        if start_time:
            event['start'] = {'dateTime': start_time, 'timeZone': 'America/New_York'}
        if end_time:
            event['end'] = {'dateTime': end_time, 'timeZone': 'America/New_York'}
        if location is not None:
            event['location'] = location
        
        response = requests.put(url, headers=headers, json=event)
        
        if response.status_code != 200:
            raise Exception(f"Failed to update event: {response.text}")
        
        return response.json()
    
    def delete_event(self, calendar_id='primary', event_id=''):
        """Delete an event"""
        if not self.access_token:
            raise Exception("Not authenticated. Call authenticate() first.")
        
        url = f'https://www.googleapis.com/calendar/v3/calendars/{calendar_id}/events/{event_id}'
        headers = self._get_headers()
        
        response = requests.delete(url, headers=headers)
        
        if response.status_code != 204:
            raise Exception(f"Failed to delete event: {response.text}")
        
        return {"deleted": True, "event_id": event_id}
    
    def search_events(self, calendar_id='primary', query='', max_results=25):
        """Search events (wildcard search)"""
        return self.list_events(calendar_id=calendar_id, max_results=max_results, query=query)
    
    # ==================== Helper Methods ====================
    
    @staticmethod
    def extract_document_id(url):
        """Extract document ID from Google Docs URL"""
        import re
        match = re.search(r'/document/d/([a-zA-Z0-9-_]+)', url)
        return match.group(1) if match else None


# Example usage
if __name__ == '__main__':
    # Initialize service
    service = GoogleService()
    
    # Note: You need to set client_secret from environment or config
    # service.client_secret = 'YOUR_CLIENT_SECRET'
    
    print("Google Service initialized")
    print(f"Client ID: {service.client_id}")
    print("\nTo authenticate, call: service.authenticate()")
    print("\nExample usage:")
    print("  # Create document")
    print("  doc = service.create_document('My Document', 'Hello World')")
    print("  print(f'Document created: {doc[\"documentId\"]}')")
    print("\n  # Send email")
    print("  service.send_email('user@example.com', 'Test', 'Hello from Robodog!')")
