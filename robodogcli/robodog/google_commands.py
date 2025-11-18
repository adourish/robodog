"""
Google Commands for Robodog CLI
Provides command-line interface for Google Docs and Gmail operations
"""

import os
import sys
import yaml
from .google_service import GoogleService


class GoogleCommands:
    """Command handler for Google operations"""
    
    def __init__(self, config_path='google_config.yaml'):
        self.service = GoogleService()
        self.config_path = config_path
        self.load_config()
    
    def load_config(self):
        """Load configuration from YAML file"""
        if os.path.exists(self.config_path):
            try:
                with open(self.config_path, 'r') as f:
                    config = yaml.safe_load(f)
                    if 'google' in config:
                        self.service.client_secret = config['google'].get('client_secret')
                        print(f"✅ Loaded config from {self.config_path}")
            except Exception as e:
                print(f"⚠️  Warning: Could not load config: {e}")
        else:
            # Try environment variable
            self.service.client_secret = os.getenv('GOOGLE_CLIENT_SECRET')
            if self.service.client_secret:
                print("✅ Using GOOGLE_CLIENT_SECRET from environment")
    
    def authenticate(self):
        """Authenticate with Google"""
        if not self.service.client_secret:
            print("❌ Error: Client secret not configured")
            print("Set GOOGLE_CLIENT_SECRET environment variable or create google_config.yaml")
            return False
        
        try:
            self.service.authenticate()
            print("✅ Authentication successful!")
            return True
        except Exception as e:
            print(f"❌ Authentication failed: {e}")
            return False
    
    def handle_command(self, command, args):
        """Handle Google commands"""
        if not self.service.is_authenticated():
            print("⚠️  Not authenticated. Authenticating...")
            if not self.authenticate():
                return
        
        try:
            if command == 'gdoc':
                self.handle_gdoc(args)
            elif command == 'gmail':
                self.handle_gmail(args)
            else:
                print(f"Unknown command: {command}")
                self.print_help()
        except Exception as e:
            print(f"❌ Error: {e}")
    
    def handle_gdoc(self, args):
        """Handle Google Docs commands"""
        if not args:
            print("Usage: gdoc <create|read|update|delete|list> [options]")
            return
        
        action = args[0]
        
        if action == 'create':
            if len(args) < 2:
                print("Usage: gdoc create <title> [content]")
                return
            
            title = args[1]
            content = args[2] if len(args) > 2 else ''
            
            doc = self.service.create_document(title, content)
            doc_id = doc['documentId']
            url = f"https://docs.google.com/document/d/{doc_id}"
            
            print(f"✅ Document created!")
            print(f"   Title: {title}")
            print(f"   ID: {doc_id}")
            print(f"   URL: {url}")
        
        elif action == 'read':
            if len(args) < 2:
                print("Usage: gdoc read <document_id>")
                return
            
            doc_id = args[1]
            text = self.service.read_document_text(doc_id)
            
            print(f"📄 Document content:\n")
            print(text)
        
        elif action == 'update':
            if len(args) < 3:
                print("Usage: gdoc update <document_id> <content>")
                return
            
            doc_id = args[1]
            content = args[2]
            
            self.service.update_document(doc_id, content)
            print(f"✅ Document updated!")
        
        elif action == 'delete':
            if len(args) < 2:
                print("Usage: gdoc delete <document_id>")
                return
            
            doc_id = args[1]
            self.service.delete_document(doc_id)
            print(f"✅ Document deleted (moved to trash)")
        
        else:
            print(f"Unknown action: {action}")
            print("Available actions: create, read, update, delete")
    
    def handle_gmail(self, args):
        """Handle Gmail commands"""
        if not args:
            print("Usage: gmail <send|draft|list|read> [options]")
            return
        
        action = args[0]
        
        if action == 'send':
            if len(args) < 4:
                print("Usage: gmail send <to> <subject> <body> [--html]")
                return
            
            to = args[1]
            subject = args[2]
            body = args[3]
            is_html = '--html' in args
            
            result = self.service.send_email(to, subject, body, is_html)
            print(f"✅ Email sent!")
            print(f"   To: {to}")
            print(f"   Subject: {subject}")
            print(f"   Message ID: {result['id']}")
        
        elif action == 'draft':
            if len(args) < 4:
                print("Usage: gmail draft <to> <subject> <body> [--html]")
                return
            
            to = args[1]
            subject = args[2]
            body = args[3]
            is_html = '--html' in args
            
            draft = self.service.create_draft(to, subject, body, is_html)
            print(f"✅ Draft created!")
            print(f"   To: {to}")
            print(f"   Subject: {subject}")
            print(f"   Draft ID: {draft['id']}")
        
        elif action == 'list':
            max_results = 10
            query = ''
            
            if len(args) > 1:
                try:
                    max_results = int(args[1])
                except:
                    query = args[1]
            
            if len(args) > 2:
                query = args[2]
            
            emails = self.service.list_emails(max_results, query)
            
            if 'messages' in emails:
                print(f"📧 Found {len(emails['messages'])} emails:")
                for msg in emails['messages']:
                    print(f"   - ID: {msg['id']}")
            else:
                print("No emails found")
        
        elif action == 'read':
            if len(args) < 2:
                print("Usage: gmail read <message_id>")
                return
            
            msg_id = args[1]
            email = self.service.get_email(msg_id)
            
            print(f"📧 Email details:")
            print(f"   ID: {email['id']}")
            print(f"   Thread ID: {email['threadId']}")
            
            # Extract headers
            headers = {h['name']: h['value'] for h in email['payload']['headers']}
            print(f"   From: {headers.get('From', 'N/A')}")
            print(f"   To: {headers.get('To', 'N/A')}")
            print(f"   Subject: {headers.get('Subject', 'N/A')}")
            print(f"   Date: {headers.get('Date', 'N/A')}")
        
        else:
            print(f"Unknown action: {action}")
            print("Available actions: send, draft, list, read")
    
    def print_help(self):
        """Print help message"""
        help_text = """
Google Commands for Robodog

Google Docs:
  gdoc create <title> [content]       - Create a new document
  gdoc read <document_id>             - Read document content
  gdoc update <document_id> <content> - Update document
  gdoc delete <document_id>           - Delete document (move to trash)

Gmail:
  gmail send <to> <subject> <body> [--html]  - Send email
  gmail draft <to> <subject> <body> [--html] - Create draft
  gmail list [max_results] [query]           - List emails
  gmail read <message_id>                    - Read email

Examples:
  gdoc create "Meeting Notes" "Today's agenda..."
  gdoc read 1abc123xyz
  gmail send user@example.com "Hello" "Email body"
  gmail list 5 "from:someone@example.com"

Configuration:
  Set GOOGLE_CLIENT_SECRET environment variable or
  Create google_config.yaml with your credentials
"""
        print(help_text)


def main():
    """Main entry point for CLI"""
    if len(sys.argv) < 2:
        print("Usage: python google_commands.py <command> [args...]")
        print("Run with 'help' for more information")
        return
    
    cmd_handler = GoogleCommands()
    
    if sys.argv[1] == 'help':
        cmd_handler.print_help()
        return
    
    if sys.argv[1] == 'auth':
        cmd_handler.authenticate()
        return
    
    command = sys.argv[1]
    args = sys.argv[2:] if len(sys.argv) > 2 else []
    
    cmd_handler.handle_command(command, args)


if __name__ == '__main__':
    main()
