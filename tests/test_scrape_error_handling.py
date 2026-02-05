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
    
    def test_ssl_certificate_error(self, client):
        """Test error handling for SSL/TLS certificate errors."""
        with patch.object(bridge_web, '_validate_scrape_url', return_value=True):
            with patch.object(bridge_web, '_validate_api_key', return_value=None):
                with patch.object(bridge_web, 'verify_watt_payment', return_value=(True, None, None)):
                    with patch.object(bridge_web, '_fetch_with_redirects') as mock_fetch:
                        mock_fetch.side_effect = requests.exceptions.SSLError(
                            'certificate verify failed: unable to get local issuer certificate'
                        )
                        
                        response = client.post('/api/v1/scrape', json={
                            'url': 'https://self-signed.example.com',
                            'wallet': 'wallet123',
                            'tx_signature': 'sig123'
                        })
        
        assert response.status_code == 502
        data = response.get_json()
        assert data['error'] == ScraperErrorCode.SSL_ERROR.value
        assert 'SSL' in data['message'] or 'certificate' in data['message'].lower()
    
    def test_host_unreachable(self, client):
        """Test error handling for unreachable host."""
        with patch.object(bridge_web, '_validate_scrape_url', return_value=True):
            with patch.object(bridge_web, '_validate_api_key', return_value=None):
                with patch.object(bridge_web, 'verify_watt_payment', return_value=(True, None, None)):
                    with patch.object(bridge_web, '_fetch_with_redirects') as mock_fetch:
                        mock_fetch.side_effect = requests.ConnectionError(
                            'Network is unreachable'
                        )
                        
                        response = client.post('/api/v1/scrape', json={
                            'url': 'https://example.com',
                            'wallet': 'wallet123',
                            'tx_signature': 'sig123'
                        })
        
        assert response.status_code == 502
        data = response.get_json()
        assert data['error'] == ScraperErrorCode.HOST_UNREACHABLE.value
        assert 'unreachable' in data['message'].lower()


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
    
    def test_http_503_service_unavailable(self, client):
        """Test handling of HTTP 503 Service Unavailable."""
        with patch.object(bridge_web, '_validate_scrape_url', return_value=True):
            with patch.object(bridge_web, '_validate_api_key', return_value=None):
                with patch.object(bridge_web, 'verify_watt_payment', return_value=(True, None, None)):
                    with patch.object(bridge_web, '_fetch_with_redirects') as mock_fetch:
                        mock_fetch.return_value = MockResponse(b'', 503, 'utf-8')
                        
                        response = client.post('/api/v1/scrape', json={
                            'url': 'https://example.com',
                            'wallet': 'wallet123',
                            'tx_signature': 'sig123'
                        })
        
        assert response.status_code == 502
        data = response.get_json()
        assert data['error'] == ScraperErrorCode.HTTP_ERROR.value
        assert '503' in data['message']
        assert data['status_code'] == 503


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


# =============================================================================
# LOGGING TESTS
# =============================================================================

class TestLogging:
    """Verify that scraper actions produce structured log output."""
    
    def test_logs_on_successful_scrape(self, client, caplog):
        """Successful scrape produces INFO-level log with url and format."""
        import logging
        with caplog.at_level(logging.INFO, logger='wattcoin.scraper'):
            with patch.object(bridge_web, '_validate_scrape_url', return_value=True):
                with patch.object(bridge_web, '_validate_api_key', return_value=None):
                    with patch.object(bridge_web, 'verify_watt_payment', return_value=(True, None, None)):
                        with patch.object(bridge_web, '_fetch_with_redirects') as mock_fetch:
                            mock_fetch.return_value = MockResponse(
                                b'<html><body><p>log test</p></body></html>', 200, 'utf-8'
                            )
                            client.post('/api/v1/scrape', json={
                                'url': 'https://example.com',
                                'format': 'text',
                                'wallet': 'w1',
                                'tx_signature': 's1'
                            })
        
        # Should have at least a "request received" and "success" log
        messages = ' '.join(caplog.messages)
        assert 'scrape request received' in messages
        assert 'scrape success' in messages
    
    def test_logs_on_network_error(self, client, caplog):
        """Network errors are logged at WARNING level."""
        import logging
        with caplog.at_level(logging.WARNING, logger='wattcoin.scraper'):
            with patch.object(bridge_web, '_validate_scrape_url', return_value=True):
                with patch.object(bridge_web, '_validate_api_key', return_value=None):
                    with patch.object(bridge_web, 'verify_watt_payment', return_value=(True, None, None)):
                        with patch.object(bridge_web, '_fetch_with_redirects') as mock_fetch:
                            mock_fetch.side_effect = requests.Timeout('timed out')
                            client.post('/api/v1/scrape', json={
                                'url': 'https://slow.example.com',
                                'wallet': 'w1',
                                'tx_signature': 's1'
                            })
        
        messages = ' '.join(caplog.messages)
        assert 'timed out' in messages
    
    def test_logs_on_ssl_error(self, client, caplog):
        """SSL errors are logged at WARNING level with truncated detail."""
        import logging
        with caplog.at_level(logging.WARNING, logger='wattcoin.scraper'):
            with patch.object(bridge_web, '_validate_scrape_url', return_value=True):
                with patch.object(bridge_web, '_validate_api_key', return_value=None):
                    with patch.object(bridge_web, 'verify_watt_payment', return_value=(True, None, None)):
                        with patch.object(bridge_web, '_fetch_with_redirects') as mock_fetch:
                            mock_fetch.side_effect = requests.exceptions.SSLError(
                                'certificate verify failed'
                            )
                            client.post('/api/v1/scrape', json={
                                'url': 'https://bad-cert.example.com',
                                'wallet': 'w1',
                                'tx_signature': 's1'
                            })
        
        messages = ' '.join(caplog.messages)
        assert 'ssl' in messages.lower()


# =============================================================================
# WATTNODE LOCAL SCRAPER TESTS
# =============================================================================

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'wattnode', 'services'))
from scraper import (
    local_scrape,
    InvalidURLError,
    TimeoutError_,
    SSLError as NodeSSLError,
    DNSError as NodeDNSError,
    ConnectionRefusedError_ as NodeConnRefused,
    HostUnreachableError as NodeHostUnreachable,
    HTTPError as NodeHTTPError,
    ResponseTooLargeError,
    EmptyResponseError as NodeEmptyResponse,
    InvalidJSONError as NodeInvalidJSON,
    ParsingError as NodeParsingError,
    ScraperException,
)


class TestWattNodeScraperValidation:
    """Unit tests for wattnode/services/scraper.py error handling."""
    
    def test_missing_url_raises(self):
        """Empty URL raises InvalidURLError."""
        with pytest.raises(InvalidURLError):
            local_scrape('')
    
    def test_malformed_url_raises(self):
        """URL without scheme raises InvalidURLError."""
        with pytest.raises(InvalidURLError):
            local_scrape('example.com/no-scheme')
    
    def test_timeout_raises(self):
        """requests.Timeout maps to TimeoutError_."""
        with patch('scraper.requests.get') as mock_get:
            mock_get.side_effect = requests.Timeout('timed out')
            with pytest.raises(TimeoutError_) as exc_info:
                local_scrape('https://example.com')
            assert exc_info.value.error_code == 'timeout'
            assert exc_info.value.status_code == 504
    
    def test_ssl_error_raises(self):
        """requests SSLError maps to node SSLError."""
        with patch('scraper.requests.get') as mock_get:
            mock_get.side_effect = requests.exceptions.SSLError('cert verify failed')
            with pytest.raises(NodeSSLError) as exc_info:
                local_scrape('https://example.com')
            assert exc_info.value.error_code == 'ssl_error'
            assert exc_info.value.status_code == 502
    
    def test_dns_error_raises(self):
        """DNS failure maps to DNSError."""
        with patch('scraper.requests.get') as mock_get:
            mock_get.side_effect = requests.ConnectionError('Name or service not known')
            with pytest.raises(NodeDNSError) as exc_info:
                local_scrape('https://nonexistent.invalid')
            assert exc_info.value.error_code == 'dns_error'
    
    def test_connection_refused_raises(self):
        """Connection refused maps correctly."""
        with patch('scraper.requests.get') as mock_get:
            mock_get.side_effect = requests.ConnectionError('Connection refused')
            with pytest.raises(NodeConnRefused) as exc_info:
                local_scrape('https://example.com')
            assert exc_info.value.error_code == 'connection_error'
    
    def test_host_unreachable_raises(self):
        """Network unreachable maps to HostUnreachableError."""
        with patch('scraper.requests.get') as mock_get:
            mock_get.side_effect = requests.ConnectionError('Network is unreachable')
            with pytest.raises(NodeHostUnreachable) as exc_info:
                local_scrape('https://example.com')
            assert exc_info.value.error_code == 'host_unreachable'
    
    def test_http_404_raises(self):
        """HTTP 404 maps to HTTPError with status_code field."""
        mock_resp = Mock()
        mock_resp.status_code = 404
        with patch('scraper.requests.get', return_value=mock_resp):
            with pytest.raises(NodeHTTPError) as exc_info:
                local_scrape('https://example.com')
            assert exc_info.value.http_status_code == 404
            assert '404' in str(exc_info.value)
            assert exc_info.value.to_dict()['status_code'] == 404
    
    def test_http_503_raises(self):
        """HTTP 503 maps to HTTPError with correct message."""
        mock_resp = Mock()
        mock_resp.status_code = 503
        with patch('scraper.requests.get', return_value=mock_resp):
            with pytest.raises(NodeHTTPError) as exc_info:
                local_scrape('https://example.com')
            assert exc_info.value.http_status_code == 503
            assert '503' in str(exc_info.value)
    
    def test_response_too_large_raises(self):
        """Oversized response raises ResponseTooLargeError."""
        mock_resp = Mock()
        mock_resp.status_code = 200
        mock_resp.encoding = 'utf-8'
        # Return chunks that exceed MAX_SIZE (2 MB)
        mock_resp.iter_content = Mock(return_value=[b'x' * (2 * 1024 * 1024 + 1)])
        with patch('scraper.requests.get', return_value=mock_resp):
            with pytest.raises(ResponseTooLargeError) as exc_info:
                local_scrape('https://example.com')
            d = exc_info.value.to_dict()
            assert d['max_bytes'] == 2 * 1024 * 1024
            assert 'received_bytes' in d
    
    def test_empty_response_raises(self):
        """Empty body raises EmptyResponseError."""
        mock_resp = Mock()
        mock_resp.status_code = 200
        mock_resp.encoding = 'utf-8'
        mock_resp.iter_content = Mock(return_value=[b''])
        with patch('scraper.requests.get', return_value=mock_resp):
            with pytest.raises(NodeEmptyResponse):
                local_scrape('https://example.com')
    
    def test_invalid_json_raises(self):
        """Non-JSON body with format='json' raises InvalidJSONError."""
        mock_resp = Mock()
        mock_resp.status_code = 200
        mock_resp.encoding = 'utf-8'
        mock_resp.iter_content = Mock(return_value=[b'this is not json'])
        with patch('scraper.requests.get', return_value=mock_resp):
            with pytest.raises(NodeInvalidJSON) as exc_info:
                local_scrape('https://example.com', format='json')
            assert exc_info.value.error_code == 'invalid_json'
    
    def test_json_success(self):
        """Valid JSON is parsed and returned as dict."""
        mock_resp = Mock()
        mock_resp.status_code = 200
        mock_resp.encoding = 'utf-8'
        mock_resp.iter_content = Mock(return_value=[b'{"hello": "world"}'])
        with patch('scraper.requests.get', return_value=mock_resp):
            result = local_scrape('https://example.com', format='json')
        assert result == {"hello": "world"}
    
    def test_text_success(self):
        """HTML is stripped to text correctly."""
        mock_resp = Mock()
        mock_resp.status_code = 200
        mock_resp.encoding = 'utf-8'
        mock_resp.iter_content = Mock(return_value=[
            b'<html><body><script>bad</script><p>Good text</p></body></html>'
        ])
        with patch('scraper.requests.get', return_value=mock_resp):
            result = local_scrape('https://example.com', format='text')
        assert 'Good text' in result
        assert 'bad' not in result
    
    def test_html_success(self):
        """HTML format returns raw HTML string."""
        html = b'<html><body><div>Raw</div></body></html>'
        mock_resp = Mock()
        mock_resp.status_code = 200
        mock_resp.encoding = 'utf-8'
        mock_resp.iter_content = Mock(return_value=[html])
        with patch('scraper.requests.get', return_value=mock_resp):
            result = local_scrape('https://example.com', format='html')
        assert result == html.decode('utf-8')
    
    def test_error_to_dict_format(self):
        """ScraperException.to_dict() returns canonical error envelope."""
        err = ScraperException("test msg", "test_code", 418)
        d = err.to_dict()
        assert d == {
            'success': False,
            'error': 'test_code',
            'message': 'test msg'
        }
