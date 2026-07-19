/**
 * GoogleService - Handles Google Docs and Gmail API integration
 * Supports OAuth2 authentication and CRUD operations
 */

class GoogleService {
  constructor() {
    this.clientId = '837032747486-0dttoe0dfkfrn9m3obimrgboj8i64leu.apps.googleusercontent.com';
    this.redirectUri = 'http://localhost:8080/callback';
    this.scopes = [
      'https://www.googleapis.com/auth/documents',
      'https://www.googleapis.com/auth/drive.file',
      'https://www.googleapis.com/auth/gmail.send',
      'https://www.googleapis.com/auth/gmail.compose',
      'https://www.googleapis.com/auth/gmail.modify'
    ];
    this.accessToken = null;
    this.tokenExpiry = null;
  }

  /**
   * Initialize OAuth2 flow
   */
  async authenticate() {
    const authUrl = this.buildAuthUrl();
    
    // Open popup for OAuth
    const popup = window.open(
      authUrl,
      'Google OAuth',
      'width=600,height=700'
    );

    return new Promise((resolve, reject) => {
      // Listen for callback
      window.addEventListener('message', (event) => {
        if (event.data.type === 'google_oauth_callback') {
          popup.close();
          if (event.data.code) {
            this.exchangeCodeForToken(event.data.code)
              .then(resolve)
              .catch(reject);
          } else {
            reject(new Error('Authentication failed'));
          }
        }
      });

      // Check if popup was closed
      const checkClosed = setInterval(() => {
        if (popup.closed) {
          clearInterval(checkClosed);
          reject(new Error('Authentication popup closed'));
        }
      }, 1000);
    });
  }

  buildAuthUrl() {
    const params = new URLSearchParams({
      client_id: this.clientId,
      redirect_uri: this.redirectUri,
      response_type: 'code',
      scope: this.scopes.join(' '),
      access_type: 'offline',
      prompt: 'consent'
    });

    return `https://accounts.google.com/o/oauth2/v2/auth?${params.toString()}`;
  }

  async exchangeCodeForToken(code) {
    // Note: This should be done server-side for security
    // For now, we'll store the code and let the backend handle it
    console.warn('Token exchange should be handled server-side');
    
    // Store the authorization code
    localStorage.setItem('google_auth_code', code);
    
    return { success: true, code };
  }

  setAccessToken(token, expiresIn = 3600) {
    this.accessToken = token;
    this.tokenExpiry = Date.now() + (expiresIn * 1000);
    localStorage.setItem('google_access_token', token);
    localStorage.setItem('google_token_expiry', this.tokenExpiry.toString());
  }

  getAccessToken() {
    if (!this.accessToken) {
      this.accessToken = localStorage.getItem('google_access_token');
      this.tokenExpiry = parseInt(localStorage.getItem('google_token_expiry'));
    }

    if (this.tokenExpiry && Date.now() >= this.tokenExpiry) {
      console.warn('Access token expired');
      return null;
    }

    return this.accessToken;
  }

  isAuthenticated() {
    return !!this.getAccessToken();
  }

  /**
   * Google Docs API Methods
   */

  async createDocument(title, content = '') {
    const token = this.getAccessToken();
    if (!token) throw new Error('Not authenticated');

    const response = await fetch('https://docs.googleapis.com/v1/documents', {
      method: 'POST',
      headers: {
        'Authorization': `Bearer ${token}`,
        'Content-Type': 'application/json'
      },
      body: JSON.stringify({ title })
    });

    if (!response.ok) {
      throw new Error(`Failed to create document: ${response.statusText}`);
    }

    const doc = await response.json();

    // Add content if provided
    if (content) {
      await this.updateDocument(doc.documentId, content);
    }

    return doc;
  }

  async getDocument(documentId) {
    const token = this.getAccessToken();
    if (!token) throw new Error('Not authenticated');

    const response = await fetch(
      `https://docs.googleapis.com/v1/documents/${documentId}`,
      {
        headers: {
          'Authorization': `Bearer ${token}`
        }
      }
    );

    if (!response.ok) {
      throw new Error(`Failed to get document: ${response.statusText}`);
    }

    return await response.json();
  }

  async updateDocument(documentId, content, insertIndex = 1) {
    const token = this.getAccessToken();
    if (!token) throw new Error('Not authenticated');

    const requests = [
      {
        insertText: {
          location: { index: insertIndex },
          text: content
        }
      }
    ];

    const response = await fetch(
      `https://docs.googleapis.com/v1/documents/${documentId}:batchUpdate`,
      {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${token}`,
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({ requests })
      }
    );

    if (!response.ok) {
      throw new Error(`Failed to update document: ${response.statusText}`);
    }

    return await response.json();
  }

  async deleteDocument(documentId) {
    const token = this.getAccessToken();
    if (!token) throw new Error('Not authenticated');

    // Google Docs doesn't have a direct delete API
    // We need to use Drive API to trash the file
    const response = await fetch(
      `https://www.googleapis.com/drive/v3/files/${documentId}`,
      {
        method: 'DELETE',
        headers: {
          'Authorization': `Bearer ${token}`
        }
      }
    );

    if (!response.ok && response.status !== 204) {
      throw new Error(`Failed to delete document: ${response.statusText}`);
    }

    return { success: true };
  }

  /**
   * Gmail API Methods
   */

  async sendEmail(to, subject, body, isHtml = false) {
    const token = this.getAccessToken();
    if (!token) throw new Error('Not authenticated');

    const email = this.createEmailMessage(to, subject, body, isHtml);
    const encodedEmail = btoa(email).replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '');

    const response = await fetch(
      'https://gmail.googleapis.com/gmail/v1/users/me/messages/send',
      {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${token}`,
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({ raw: encodedEmail })
      }
    );

    if (!response.ok) {
      throw new Error(`Failed to send email: ${response.statusText}`);
    }

    return await response.json();
  }

  createEmailMessage(to, subject, body, isHtml = false) {
    const contentType = isHtml ? 'text/html' : 'text/plain';
    
    const message = [
      `To: ${to}`,
      `Subject: ${subject}`,
      `Content-Type: ${contentType}; charset=utf-8`,
      '',
      body
    ].join('\r\n');

    return message;
  }

  async listEmails(maxResults = 10, query = '') {
    const token = this.getAccessToken();
    if (!token) throw new Error('Not authenticated');

    const params = new URLSearchParams({
      maxResults: maxResults.toString(),
      q: query
    });

    const response = await fetch(
      `https://gmail.googleapis.com/gmail/v1/users/me/messages?${params.toString()}`,
      {
        headers: {
          'Authorization': `Bearer ${token}`
        }
      }
    );

    if (!response.ok) {
      throw new Error(`Failed to list emails: ${response.statusText}`);
    }

    return await response.json();
  }

  async getEmail(messageId) {
    const token = this.getAccessToken();
    if (!token) throw new Error('Not authenticated');

    const response = await fetch(
      `https://gmail.googleapis.com/gmail/v1/users/me/messages/${messageId}`,
      {
        headers: {
          'Authorization': `Bearer ${token}`
        }
      }
    );

    if (!response.ok) {
      throw new Error(`Failed to get email: ${response.statusText}`);
    }

    return await response.json();
  }

  async createDraft(to, subject, body, isHtml = false) {
    const token = this.getAccessToken();
    if (!token) throw new Error('Not authenticated');

    const email = this.createEmailMessage(to, subject, body, isHtml);
    const encodedEmail = btoa(email).replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '');

    const response = await fetch(
      'https://gmail.googleapis.com/gmail/v1/users/me/drafts',
      {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${token}`,
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({
          message: { raw: encodedEmail }
        })
      }
    );

    if (!response.ok) {
      throw new Error(`Failed to create draft: ${response.statusText}`);
    }

    return await response.json();
  }

  async deleteDraft(draftId) {
    const token = this.getAccessToken();
    if (!token) throw new Error('Not authenticated');

    const response = await fetch(
      `https://gmail.googleapis.com/gmail/v1/users/me/drafts/${draftId}`,
      {
        method: 'DELETE',
        headers: {
          'Authorization': `Bearer ${token}`
        }
      }
    );

    if (!response.ok && response.status !== 204) {
      throw new Error(`Failed to delete draft: ${response.statusText}`);
    }

    return { success: true };
  }

  /**
   * Helper method to extract document ID from URL
   */
  extractDocumentId(url) {
    const match = url.match(/\/document\/d\/([a-zA-Z0-9-_]+)/);
    return match ? match[1] : null;
  }
}

// Export singleton instance
const googleService = new GoogleService();
export default googleService;
