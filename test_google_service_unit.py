"""
Unit tests for Google Service
Tests the GoogleService class without requiring authentication
"""

import sys
import os

# Add robodogcli to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'robodogcli'))

from google_service import GoogleService


def test_initialization():
    """Test GoogleService initialization"""
    print("\n=== Test 1: Initialization ===")
    
    service = GoogleService()
    
    # Check client ID is set
    assert service.client_id == '837032747486-0dttoe0dfkfrn9m3obimrgboj8i64leu.apps.googleusercontent.com'
    print(f"✅ Client ID: {service.client_id[:50]}...")
    
    # Check redirect URI
    assert service.redirect_uri == 'http://localhost:8080/callback'
    print(f"✅ Redirect URI: {service.redirect_uri}")
    
    # Check scopes are set
    assert len(service.scopes) == 5
    print(f"✅ Scopes configured: {len(service.scopes)} scopes")
    
    # Check initial state
    assert service.access_token is None
    assert service.refresh_token is None
    print("✅ Initial state: Not authenticated")
    
    print("✅ Initialization test PASSED\n")
    return True


def test_auth_url_building():
    """Test OAuth URL building"""
    print("=== Test 2: Auth URL Building ===")
    
    service = GoogleService()
    auth_url = service._build_auth_url()
    
    # Check URL components
    assert 'accounts.google.com/o/oauth2/v2/auth' in auth_url
    print("✅ Auth URL base correct")
    
    assert 'client_id=' in auth_url
    print("✅ Client ID in URL")
    
    assert 'redirect_uri=' in auth_url
    print("✅ Redirect URI in URL")
    
    assert 'scope=' in auth_url
    print("✅ Scopes in URL")
    
    assert 'response_type=code' in auth_url
    print("✅ Response type correct")
    
    assert 'access_type=offline' in auth_url
    print("✅ Access type correct")
    
    print(f"✅ Auth URL: {auth_url[:100]}...")
    print("✅ Auth URL building test PASSED\n")
    return True


def test_token_management():
    """Test token management methods"""
    print("=== Test 3: Token Management ===")
    
    service = GoogleService()
    
    # Test setting token
    test_token = "test_access_token_123"
    service.set_access_token(test_token, 3600)
    
    assert service.access_token == test_token
    print("✅ Token set successfully")
    
    # Test getting token
    retrieved_token = service.get_access_token()
    assert retrieved_token == test_token
    print("✅ Token retrieved successfully")
    
    # Test authentication check
    assert service.is_authenticated() == True
    print("✅ Authentication status correct")
    
    print("✅ Token management test PASSED\n")
    return True


def test_email_message_creation():
    """Test email message creation"""
    print("=== Test 4: Email Message Creation ===")
    
    service = GoogleService()
    
    # Test plain text email
    message = service._create_email_message(
        to='test@example.com',
        subject='Test Subject',
        body='Test body content',
        is_html=False
    )
    
    assert message is not None
    assert len(message) > 0
    print("✅ Plain text email message created")
    
    # Test HTML email
    html_message = service._create_email_message(
        to='test@example.com',
        subject='HTML Test',
        body='<h1>HTML Content</h1>',
        is_html=True
    )
    
    assert html_message is not None
    assert len(html_message) > 0
    print("✅ HTML email message created")
    
    # Test with CC and BCC
    cc_message = service._create_email_message(
        to='test@example.com',
        subject='Test with CC',
        body='Body',
        cc='cc@example.com',
        bcc='bcc@example.com'
    )
    
    assert cc_message is not None
    print("✅ Email with CC/BCC created")
    
    print("✅ Email message creation test PASSED\n")
    return True


def test_document_id_extraction():
    """Test document ID extraction from URLs"""
    print("=== Test 5: Document ID Extraction ===")
    
    # Test valid URL
    url1 = "https://docs.google.com/document/d/1abc123xyz/edit"
    doc_id = GoogleService.extract_document_id(url1)
    assert doc_id == "1abc123xyz"
    print(f"✅ Extracted ID from URL: {doc_id}")
    
    # Test another valid URL
    url2 = "https://docs.google.com/document/d/ABC-123_xyz/edit?usp=sharing"
    doc_id2 = GoogleService.extract_document_id(url2)
    assert doc_id2 == "ABC-123_xyz"
    print(f"✅ Extracted ID with special chars: {doc_id2}")
    
    # Test invalid URL
    url3 = "https://example.com/not-a-doc"
    doc_id3 = GoogleService.extract_document_id(url3)
    assert doc_id3 is None
    print("✅ Invalid URL returns None")
    
    print("✅ Document ID extraction test PASSED\n")
    return True


def test_configuration():
    """Test custom configuration"""
    print("=== Test 6: Custom Configuration ===")
    
    # Test with custom parameters
    custom_service = GoogleService(
        client_id='custom_client_id',
        client_secret='custom_secret',
        redirect_uri='http://localhost:9000/callback'
    )
    
    assert custom_service.client_id == 'custom_client_id'
    print("✅ Custom client ID set")
    
    assert custom_service.client_secret == 'custom_secret'
    print("✅ Custom client secret set")
    
    assert custom_service.redirect_uri == 'http://localhost:9000/callback'
    print("✅ Custom redirect URI set")
    
    print("✅ Custom configuration test PASSED\n")
    return True


def test_api_methods_exist():
    """Test that all API methods exist"""
    print("=== Test 7: API Methods Availability ===")
    
    service = GoogleService()
    
    # Google Docs methods
    docs_methods = [
        'create_document',
        'get_document',
        'update_document',
        'delete_document',
        'read_document_text'
    ]
    
    for method in docs_methods:
        assert hasattr(service, method)
        print(f"✅ Google Docs method exists: {method}")
    
    # Gmail methods
    gmail_methods = [
        'send_email',
        'list_emails',
        'get_email',
        'create_draft',
        'delete_draft'
    ]
    
    for method in gmail_methods:
        assert hasattr(service, method)
        print(f"✅ Gmail method exists: {method}")
    
    # Helper methods
    helper_methods = [
        'authenticate',
        'set_access_token',
        'get_access_token',
        'is_authenticated',
        'extract_document_id'
    ]
    
    for method in helper_methods:
        assert hasattr(service, method) or hasattr(GoogleService, method)
        print(f"✅ Helper method exists: {method}")
    
    print("✅ API methods availability test PASSED\n")
    return True


def run_all_tests():
    """Run all tests"""
    print("=" * 70)
    print("Google Service Unit Tests")
    print("=" * 70)
    
    tests = [
        ("Initialization", test_initialization),
        ("Auth URL Building", test_auth_url_building),
        ("Token Management", test_token_management),
        ("Email Message Creation", test_email_message_creation),
        ("Document ID Extraction", test_document_id_extraction),
        ("Custom Configuration", test_configuration),
        ("API Methods Availability", test_api_methods_exist),
    ]
    
    passed = 0
    failed = 0
    
    for name, test_func in tests:
        try:
            if test_func():
                passed += 1
        except Exception as e:
            print(f"❌ {name} FAILED: {e}\n")
            failed += 1
    
    print("=" * 70)
    print("Test Summary")
    print("=" * 70)
    print(f"Total Tests: {len(tests)}")
    print(f"✅ Passed: {passed}")
    print(f"❌ Failed: {failed}")
    print(f"Success Rate: {(passed/len(tests)*100):.1f}%")
    print("=" * 70)
    
    if failed == 0:
        print("\n🎉 ALL TESTS PASSED! 🎉")
        print("\nGoogle Service is ready to use!")
        print("\nNext steps:")
        print("1. Get your client secret from Google Cloud Console")
        print("2. Set GOOGLE_CLIENT_SECRET environment variable")
        print("3. Run: python send_amplenote_email.py")
    else:
        print(f"\n⚠️  {failed} test(s) failed. Please review the errors above.")
    
    return failed == 0


if __name__ == '__main__':
    success = run_all_tests()
    sys.exit(0 if success else 1)
