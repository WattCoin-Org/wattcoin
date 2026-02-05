"""
Comprehensive error handling tests for the web scraper endpoint.

Tests cover:
- Input validation (URL, format, payment)
- Network errors (timeout, connection, DNS)
- HTTP errors (401, 403, 404, 429, 5xx)
- Content parsing (JSON, HTML, text)
- Size limits and encoding
- Payment verification
- Rate limiting
"""

import json
import pytest
from unittest.mock import Mock, patch, MagicMock
import requests

import bridge_web
from scraper_errors import ScraperErrorCode


class MockResponse:
    """Mock response object for testing."""
    
    def __init__(self, content=b'', status_code=200, encoding='utf-8', headers=None):
        self.content = content
        self.status_code = status_code
        self.encoding = encoding
        self.headers = headers or {}
    
    def iter_content(self, chunk_size=8192):
        """Iterate over response content."""
        for i in range(0, len(self.content), chunk_size):
            yield self.content[i:i+chunk_size]


@pytest.fixture
def client():
    """Create test client."""
    return bridge_web.app.test_client()


# =============================================================================
# INPUT VALIDATION TESTS
# =============================================================================

class TestInputValidation:
    """Test input parameter validation."""
    
    def test_missing_url(self, client):
        """Test error when URL is missing."""
        response = client.post('/api/v1/scrape', json={})
        assert response.status_code == 400
        data = response.get_json()
        assert data['success'] is False
        assert data['error'] == ScraperErrorCode.MISSING_URL.value
        assert 'URL' in data['message']
    
    def test_empty_url(self, client):
        """Test error when URL is empty string."""
        response = client.post('/api/v1/scrape', json={'url': '  '})
        assert response.status_code == 400
        data = response.get_json()
        assert data['error'] == ScraperErrorCode.MISSING_URL.value
    
    def test_invalid_url_format(self, client):
        """Test error for invalid URL format."""
        response = client.post('/api/v1/scrape', json={'url': 'not a url'})
        assert response.status_code == 400
        data = response.get_json()
        assert data['error'] == ScraperErrorCode.INVALID_URL.value
        assert 'http' in data['message']
    
    def test_url_with_embedded_credentials(self, client):
        """Test error for URLs with embedded credentials."""
        response = client.post('/api/v1/scrape', json={
            'url': 'https://user:pass@example.com/page'
        })
        assert response.status_code == 400
        data = response.get_json()
        assert data['error'] == ScraperErrorCode.INVALID_URL.value
        assert 'credentials' in data['message']
    
    def test_url_too_long(self, client):
        """Test error for excessively long URLs."""
        long_url = 'https://example.com/' + 'a' * 2050
        response = client.post('/api/v1/scrape', json={'url': long_url})
        assert response.status_code == 400
        data = response.get_json()
        assert data['error'] == ScraperErrorCode.INVALID_URL.value
        assert 'length' in data['message']
    
    def test_invalid_format(self, client):
        """Test error for invalid format parameter."""
        with patch.object(bridge_web, '_validate_scrape_url', return_value=True):
            response = client.post('/api/v1/scrape', json={
                'url': 'https://example.com',
                'format': 'xml'
            })
        assert response.status_code == 400
        data = response.get_json()
        assert data['error'] == ScraperErrorCode.INVALID_FORMAT.value
        assert 'text' in data['message']
        assert 'json' in data['message']
    
    def test_valid_format_text(self, client):
        """Test that 'text' is a valid format."""
        with patch.object(bridge_web, '_validate_scrape_url', return_value=True):
            with patch.object(bridge_web, '_validate_api_key', return_value=None):
                response = client.post('/api/v1/scrape', json={
                    'url': 'https://example.com',
                    'format': 'text'
                })
        # Should not fail on format validation
        assert response.status_code != 400 or 'format' not in response.get_json()['message']
    
    def test_valid_format_html(self, client):
        """Test that 'html' is a valid format."""
        with patch.object(bridge_web, '_validate_scrape_url', return_value=True):
            with patch.object(bridge_web, '_validate_api_key', return_value=None):
                response = client.post('/api/v1/scrape', json={
                    'url': 'https://example.com',
                    'format': 'html'
                })
        assert response.status_code != 400 or 'format' not in response.get_json()['message']
    
    def test_valid_format_json(self, client):
        """Test that 'json' is a valid format."""
        with patch.object(bridge_web, '_validate_scrape_url', return_value=True):
            with patch.object(bridge_web, '_validate_api_key', return_value=None):
                response = client.post('/api/v1/scrape', json={
                    'url': 'https://example.com',
                    'format': 'json'
                })
        assert response.status_code != 400 or 'format' not in response.get_json()['message']
    
    def test_format_case_insensitive(self, client):
        """Test that format is case-insensitive."""
        with patch.object(bridge_web, '_validate_scrape_url', return_value=True):
            with patch.object(bridge_web, '_validate_api_key', return_value=None):
                response = client.post('/api/v1/scrape', json={
                    'url': 'https://example.com',
                    'format': 'TEXT'
                })
        assert response.status_code != 400 or 'format' not in response.get_json()['message']


# =============================================================================
# PAYMENT VALIDATION TESTS
# =============================================================================

class TestPaymentValidation:
    """Test payment parameter validation."""
    
    def test_missing_payment(self, client):
        """Test error when payment is missing."""
        with patch.object(bridge_web, '_validate_scrape_url', return_value=True):
            response = client.post('/api/v1/scrape', json={
                'url': 'https://example.com'
            })
        assert response.status_code == 402
        data = response.get_json()
        assert data['error'] == ScraperErrorCode.MISSING_PAYMENT.value
        assert 'API key' in data['message'] or 'WATT' in data['message']
        assert 'methods' in data or 'price_watt' in data
    
    def test_missing_wallet_with_signature(self, client):
        """Test error when wallet is missing but signature provided."""
        with patch.object(bridge_web, '_validate_scrape_url', return_value=True):
            response = client.post('/api/v1/scrape', json={
                'url': 'https://example.com',
                'tx_signature': 'sig123'
            })
        # Returns 402 (Payment Required) since payment is incomplete
        assert response.status_code == 402
        data = response.get_json()
        assert data['error'] == ScraperErrorCode.MISSING_PAYMENT.value
        assert 'payment' in data['message'].lower()
    
    def test_missing_signature_with_wallet(self, client):
        """Test error when signature is missing but wallet provided."""
        with patch.object(bridge_web, '_validate_scrape_url', return_value=True):
            response = client.post('/api/v1/scrape', json={
                'url': 'https://example.com',
                'wallet': 'wallet123'
            })
        # Returns 402 (Payment Required) since payment is incomplete
        assert response.status_code == 402
        data = response.get_json()
        assert data['error'] == ScraperErrorCode.MISSING_PAYMENT.value
        assert 'payment' in data['message'].lower()
    
    def test_invalid_api_key(self, client):
        """Test error for invalid API key."""
        with patch.object(bridge_web, '_validate_scrape_url', return_value=True):
            with patch.object(bridge_web, '_validate_api_key', return_value=None):
                response = client.post(
                    '/api/v1/scrape',
                    json={'url': 'https://example.com'},
                    headers={'X-API-Key': 'invalid-key'}
                )
        assert response.status_code == 401
        data = response.get_json()
        assert data['error'] == ScraperErrorCode.INVALID_API_KEY.value
    
    def test_valid_api_key_success(self, client):
        """Test that valid API key allows request (even without network)."""
        mock_key_data = {'tier': 'basic', 'status': 'active'}
        
        with patch.object(bridge_web, '_validate_scrape_url', return_value=True):
            with patch.object(bridge_web, '_validate_api_key', return_value=mock_key_data):
                with patch.object(bridge_web, '_check_api_key_rate_limit', return_value=(True, None)):
                    with patch.object(bridge_web, '_fetch_with_redirects') as mock_fetch:
                        mock_fetch.return_value = MockResponse(
                            b'<h1>Test</h1>', 200, 'utf-8'
                        )
                        
                        response = client.post(
                            '/api/v1/scrape',
                            json={'url': 'https://example.com'},
                            headers={'X-API-Key': 'valid-key'}
                        )
        
        assert response.status_code == 200
        data = response.get_json()
        assert data['success'] is True
        assert data['api_key_used'] is True


# =============================================================================
# RATE LIMITING TESTS
# =============================================================================

class TestRateLimiting:
    """Test rate limiting functionality."""
    
    def test_rate_limit_exceeded(self, client):
        """Test error when rate limit is exceeded."""
        mock_key_data = {'tier': 'basic', 'status': 'active'}
        
        with patch.object(bridge_web, '_validate_scrape_url', return_value=True):
            with patch.object(bridge_web, '_validate_api_key', return_value=mock_key_data):
                with patch.object(bridge_web, '_check_api_key_rate_limit', return_value=(False, 60)):
                    response = client.post(
                        '/api/v1/scrape',
                        json={'url': 'https://example.com'},
                        headers={'X-API-Key': 'valid-key'}
                    )
        
        assert response.status_code == 429
        data = response.get_json()
        assert data['error'] == ScraperErrorCode.RATE_LIMIT_EXCEEDED.value
        assert 'retry_after_seconds' in data
        assert data['retry_after_seconds'] == 60


# =============================================================================
# NETWORK ERROR TESTS
# =============================================================================

class TestNetworkErrors:
    """Test network error handling."""
    
    def test_timeout_error(self, client):
        """Test error handling for request timeout."""
        with patch.object(bridge_web, '_validate_scrape_url', return_value=True):
            with patch.object(bridge_web, '_validate_api_key', return_value=None):
                with patch.object(bridge_web, 'verify_watt_payment', return_value=(True, None, None)):
                    with patch.object(bridge_web, '_fetch_with_redirects') as mock_fetch:
                        mock_fetch.side_effect = requests.Timeout('Request timed out')
                        
                        response = client.post('/api/v1/scrape', json={
                            'url': 'https://example.com',
                            'wallet': 'wallet123',
                            'tx_signature': 'sig123'
                        })
        
        assert response.status_code == 504
        data = response.get_json()
        assert data['error'] == ScraperErrorCode.TIMEOUT.value
        assert 'timed out' in data['message']
    
    def test_connection_error_dns(self, client):
        """Test error handling for DNS resolution failure."""
        with patch.object(bridge_web, '_validate_scrape_url', return_value=True):
            with patch.object(bridge_web, '_validate_api_key', return_value=None):
                with patch.object(bridge_web, 'verify_watt_payment', return_value=(True, None, None)):
                    with patch.object(bridge_web, '_fetch_with_redirects') as mock_fetch:
                        mock_fetch.side_effect = requests.ConnectionError(
                            'Name or service not known'
                        )
                        
                        response = client.post('/api/v1/scrape', json={
                            'url': 'https://example.com',
                            'wallet': 'wallet123',
                            'tx_signature': 'sig123'
                        })
        
        assert response.status_code == 502
        data = response.get_json()
        assert data['error'] == ScraperErrorCode.DNS_ERROR.value
        assert 'resolve' in data['message']
    
    def test_connection_refused(self, client):
        """Test error handling for connection refused."""
        with patch.object(bridge_web, '_validate_scrape_url', return_value=True):
            with patch.object(bridge_web, '_validate_api_key', return_value=None):
                with patch.object(bridge_web, 'verify_watt_payment', return_value=(True, None, None)):
                    with patch.object(bridge_web, '_fetch_with_redirects') as mock_fetch:
                        mock_fetch.side_effect = requests.ConnectionError(
                            'Connection refused'
                        )
                        
                        response = client.post('/api/v1/scrape', json={
                            'url': 'https://example.com',
                            'wallet': 'wallet123',
                            'tx_signature': 'sig123'
                        })
        
        assert response.status_code == 502
        data = response.get_json()
        assert data['error'] == ScraperErrorCode.CONNECTION_ERROR.value


# =============================================================================
# HTTP STATUS CODE TESTS
# =============================================================================

class TestHTTPStatusCodes:
    """Test HTTP status code handling."""
    
    def test_http_401_unauthorized(self, client):
        """Test handling of HTTP 401 Unauthorized."""
        with patch.object(bridge_web, '_validate_scrape_url', return_value=True):
            with patch.object(bridge_web, '_validate_api_key', return_value=None):
                with patch.object(bridge_web, 'verify_watt_payment', return_value=(True, None, None)):
                    with patch.object(bridge_web, '_fetch_with_redirects') as mock_fetch:
                        mock_fetch.return_value = MockResponse(b'', 401, 'utf-8')
                        
                        response = client.post('/api/v1/scrape', json={
                            'url': 'https://example.com',
                            'wallet': 'wallet123',
                            'tx_signature': 'sig123'
                        })
        
        assert response.status_code == 502
        data = response.get_json()
        assert data['error'] == ScraperErrorCode.HTTP_ERROR.value
        assert '401' in data['message']
        assert 'authentication' in data['message'].lower()
    
    def test_http_403_forbidden(self, client):
        """Test handling of HTTP 403 Forbidden."""
        with patch.object(bridge_web, '_validate_scrape_url', return_value=True):
            with patch.object(bridge_web, '_validate_api_key', return_value=None):
                with patch.object(bridge_web, 'verify_watt_payment', return_value=(True, None, None)):
                    with patch.object(bridge_web, '_fetch_with_redirects') as mock_fetch:
                        mock_fetch.return_value = MockResponse(b'', 403, 'utf-8')
                        
                        response = client.post('/api/v1/scrape', json={
                            'url': 'https://example.com',
                            'wallet': 'wallet123',
                            'tx_signature': 'sig123'
                        })
        
        assert response.status_code == 502
        data = response.get_json()
        assert data['error'] == ScraperErrorCode.HTTP_ERROR.value
        assert '403' in data['message']
    
    def test_http_404_not_found(self, client):
        """Test handling of HTTP 404 Not Found."""
        with patch.object(bridge_web, '_validate_scrape_url', return_value=True):
            with patch.object(bridge_web, '_validate_api_key', return_value=None):
                with patch.object(bridge_web, 'verify_watt_payment', return_value=(True, None, None)):
                    with patch.object(bridge_web, '_fetch_with_redirects') as mock_fetch:
                        mock_fetch.return_value = MockResponse(b'', 404, 'utf-8')
                        
                        response = client.post('/api/v1/scrape', json={
                            'url': 'https://example.com',
                            'wallet': 'wallet123',
                            'tx_signature': 'sig123'
                        })
        
        assert response.status_code == 502
        data = response.get_json()
        assert data['error'] == ScraperErrorCode.HTTP_ERROR.value
        assert '404' in data['message']
    
    def test_http_429_rate_limit(self, client):
        """Test handling of HTTP 429 Too Many Requests."""
        with patch.object(bridge_web, '_validate_scrape_url', return_value=True):
            with patch.object(bridge_web, '_validate_api_key', return_value=None):
                with patch.object(bridge_web, 'verify_watt_payment', return_value=(True, None, None)):
                    with patch.object(bridge_web, '_fetch_with_redirects') as mock_fetch:
                        mock_fetch.return_value = MockResponse(b'', 429, 'utf-8')
                        
                        response = client.post('/api/v1/scrape', json={
                            'url': 'https://example.com',
                            'wallet': 'wallet123',
                            'tx_signature': 'sig123'
                        })
        
        assert response.status_code == 502
        data = response.get_json()
        assert data['error'] == ScraperErrorCode.HTTP_ERROR.value
        assert '429' in data['message']
    
    def test_http_500_server_error(self, client):
        """Test handling of HTTP 500 Server Error."""
        with patch.object(bridge_web, '_validate_scrape_url', return_value=True):
            with patch.object(bridge_web, '_validate_api_key', return_value=None):
                with patch.object(bridge_web, 'verify_watt_payment', return_value=(True, None, None)):
                    with patch.object(bridge_web, '_fetch_with_redirects') as mock_fetch:
                        mock_fetch.return_value = MockResponse(b'', 500, 'utf-8')
                        
                        response = client.post('/api/v1/scrape', json={
                            'url': 'https://example.com',
                            'wallet': 'wallet123',
                            'tx_signature': 'sig123'
                        })
        
        assert response.status_code == 502
        data = response.get_json()
        assert data['error'] == ScraperErrorCode.HTTP_ERROR.value
        assert '500' in data['message']


# =============================================================================
# CONTENT PARSING TESTS
# =============================================================================

class TestContentParsing:
    """Test content parsing error handling."""
    
    def test_invalid_json(self, client):
        """Test error handling for invalid JSON."""
        with patch.object(bridge_web, '_validate_scrape_url', return_value=True):
            with patch.object(bridge_web, '_validate_api_key', return_value=None):
                with patch.object(bridge_web, 'verify_watt_payment', return_value=(True, None, None)):
                    with patch.object(bridge_web, '_fetch_with_redirects') as mock_fetch:
                        mock_fetch.return_value = MockResponse(
                            b'{invalid json}', 200, 'utf-8'
                        )
                        
                        response = client.post('/api/v1/scrape', json={
                            'url': 'https://example.com',
                            'format': 'json',
                            'wallet': 'wallet123',
                            'tx_signature': 'sig123'
                        })
        
        assert response.status_code == 502
        data = response.get_json()
        assert data['error'] == ScraperErrorCode.INVALID_JSON.value
    
    def test_empty_response(self, client):
        """Test error handling for empty response."""
        with patch.object(bridge_web, '_validate_scrape_url', return_value=True):
            with patch.object(bridge_web, '_validate_api_key', return_value=None):
                with patch.object(bridge_web, 'verify_watt_payment', return_value=(True, None, None)):
                    with patch.object(bridge_web, '_fetch_with_redirects') as mock_fetch:
                        mock_fetch.return_value = MockResponse(b'', 200, 'utf-8')
                        
                        response = client.post('/api/v1/scrape', json={
                            'url': 'https://example.com',
                            'wallet': 'wallet123',
                            'tx_signature': 'sig123'
                        })
        
        assert response.status_code == 502
        data = response.get_json()
        assert data['error'] == ScraperErrorCode.EMPTY_RESPONSE.value
    
    def test_response_too_large(self, client):
        """Test error handling for response exceeding size limit."""
        with patch.object(bridge_web, '_validate_scrape_url', return_value=True):
            with patch.object(bridge_web, '_validate_api_key', return_value=None):
                with patch.object(bridge_web, 'verify_watt_payment', return_value=(True, None, None)):
                    with patch.object(bridge_web, '_read_limited_content') as mock_read:
                        mock_read.side_effect = ValueError('Response too large')
                        
                        with patch.object(bridge_web, '_fetch_with_redirects') as mock_fetch:
                            mock_fetch.return_value = MockResponse(b'x' * 3000000, 200, 'utf-8')
                            
                            response = client.post('/api/v1/scrape', json={
                                'url': 'https://example.com',
                                'wallet': 'wallet123',
                                'tx_signature': 'sig123'
                            })
        
        assert response.status_code == 413
        data = response.get_json()
        assert data['error'] == ScraperErrorCode.RESPONSE_TOO_LARGE.value
        assert 'max_bytes' in data


# =============================================================================
# REDIRECT TESTS
# =============================================================================

class TestRedirectHandling:
    """Test redirect error handling."""
    
    def test_too_many_redirects(self, client):
        """Test error handling for redirect loops."""
        with patch.object(bridge_web, '_validate_scrape_url', return_value=True):
            with patch.object(bridge_web, '_validate_api_key', return_value=None):
                with patch.object(bridge_web, 'verify_watt_payment', return_value=(True, None, None)):
                    with patch.object(bridge_web, '_fetch_with_redirects') as mock_fetch:
                        mock_fetch.side_effect = ValueError('Too many redirects')
                        
                        response = client.post('/api/v1/scrape', json={
                            'url': 'https://example.com',
                            'wallet': 'wallet123',
                            'tx_signature': 'sig123'
                        })
        
        assert response.status_code == 502
        data = response.get_json()
        assert data['error'] == ScraperErrorCode.TOO_MANY_REDIRECTS.value
    
    def test_redirect_to_blocked_url(self, client):
        """Test error handling for redirect to blocked URL."""
        with patch.object(bridge_web, '_validate_scrape_url', return_value=True):
            with patch.object(bridge_web, '_validate_api_key', return_value=None):
                with patch.object(bridge_web, 'verify_watt_payment', return_value=(True, None, None)):
                    with patch.object(bridge_web, '_fetch_with_redirects') as mock_fetch:
                        mock_fetch.side_effect = ValueError(
                            'Redirect to invalid or blocked URL'
                        )
                        
                        response = client.post('/api/v1/scrape', json={
                            'url': 'https://example.com',
                            'wallet': 'wallet123',
                            'tx_signature': 'sig123'
                        })
        
        assert response.status_code == 502
        data = response.get_json()
        assert data['error'] == ScraperErrorCode.REDIRECT_ERROR.value


# =============================================================================
# SUCCESS TESTS
# =============================================================================

class TestSuccessScenarios:
    """Test successful scraping scenarios."""
    
    def test_scrape_text_success(self, client):
        """Test successful text scraping."""
        with patch.object(bridge_web, '_validate_scrape_url', return_value=True):
            with patch.object(bridge_web, '_validate_api_key', return_value=None):
                with patch.object(bridge_web, 'verify_watt_payment', return_value=(True, None, None)):
                    with patch.object(bridge_web, '_fetch_with_redirects') as mock_fetch:
                        mock_fetch.return_value = MockResponse(
                            b'<html><body><h1>Test Content</h1></body></html>',
                            200,
                            'utf-8'
                        )
                        
                        response = client.post('/api/v1/scrape', json={
                            'url': 'https://example.com',
                            'format': 'text',
                            'wallet': 'wallet123',
                            'tx_signature': 'sig123'
                        })
        
        assert response.status_code == 200
        data = response.get_json()
        assert data['success'] is True
        assert 'Test Content' in data['content']
        assert data['format'] == 'text'
        assert data['tx_verified'] is True
    
    def test_scrape_html_success(self, client):
        """Test successful HTML scraping."""
        html_content = b'<html><body><div>HTML Content</div></body></html>'
        
        with patch.object(bridge_web, '_validate_scrape_url', return_value=True):
            with patch.object(bridge_web, '_validate_api_key', return_value=None):
                with patch.object(bridge_web, 'verify_watt_payment', return_value=(True, None, None)):
                    with patch.object(bridge_web, '_fetch_with_redirects') as mock_fetch:
                        mock_fetch.return_value = MockResponse(html_content, 200, 'utf-8')
                        
                        response = client.post('/api/v1/scrape', json={
                            'url': 'https://example.com',
                            'format': 'html',
                            'wallet': 'wallet123',
                            'tx_signature': 'sig123'
                        })
        
        assert response.status_code == 200
        data = response.get_json()
        assert data['success'] is True
        assert data['format'] == 'html'
    
    def test_scrape_json_success(self, client):
        """Test successful JSON scraping."""
        json_content = json.dumps({'key': 'value'}).encode('utf-8')
        
        with patch.object(bridge_web, '_validate_scrape_url', return_value=True):
            with patch.object(bridge_web, '_validate_api_key', return_value=None):
                with patch.object(bridge_web, 'verify_watt_payment', return_value=(True, None, None)):
                    with patch.object(bridge_web, '_fetch_with_redirects') as mock_fetch:
                        mock_fetch.return_value = MockResponse(json_content, 200, 'utf-8')
                        
                        response = client.post('/api/v1/scrape', json={
                            'url': 'https://example.com',
                            'format': 'json',
                            'wallet': 'wallet123',
                            'tx_signature': 'sig123'
                        })
        
        assert response.status_code == 200
        data = response.get_json()
        assert data['success'] is True
        assert data['format'] == 'json'
        assert isinstance(data['content'], dict)
        assert data['content']['key'] == 'value'
    
    def test_scrape_with_api_key(self, client):
        """Test successful scraping with API key."""
        mock_key_data = {'tier': 'premium', 'status': 'active'}
        html_content = b'<h1>API Key Test</h1>'
        
        with patch.object(bridge_web, '_validate_scrape_url', return_value=True):
            with patch.object(bridge_web, '_validate_api_key', return_value=mock_key_data):
                with patch.object(bridge_web, '_check_api_key_rate_limit', return_value=(True, None)):
                    with patch.object(bridge_web, '_fetch_with_redirects') as mock_fetch:
                        mock_fetch.return_value = MockResponse(html_content, 200, 'utf-8')
                        
                        response = client.post(
                            '/api/v1/scrape',
                            json={'url': 'https://example.com'},
                            headers={'X-API-Key': 'valid-key'}
                        )
        
        assert response.status_code == 200
        data = response.get_json()
        assert data['success'] is True
        assert data['api_key_used'] is True
        assert data['tier'] == 'premium'
