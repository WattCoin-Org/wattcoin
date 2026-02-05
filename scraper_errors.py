"""
Comprehensive error handling and validation for web scraper API.

Provides structured error responses, detailed error codes, and security-aware
error messages that inform clients without leaking internal system details.
"""

import re
from enum import Enum
from typing import Tuple, Dict, Optional, Any


class ScraperErrorCode(Enum):
    """Error codes for scraper endpoint responses."""
    
    # Input validation errors (4xx)
    MISSING_URL = "missing_url"
    INVALID_URL = "invalid_url"
    URL_BLOCKED = "url_blocked"
    INVALID_FORMAT = "invalid_format"
    MISSING_PAYMENT = "missing_payment"
    INVALID_API_KEY = "invalid_api_key"
    RATE_LIMIT_EXCEEDED = "rate_limit_exceeded"
    INVALID_PAYMENT = "invalid_payment"
    PAYMENT_FAILED = "payment_failed"
    
    # Network/Transport errors (5xx)
    TIMEOUT = "timeout"
    CONNECTION_ERROR = "connection_error"
    DNS_ERROR = "dns_error"
    SSL_ERROR = "ssl_error"
    REDIRECT_ERROR = "redirect_error"
    TOO_MANY_REDIRECTS = "too_many_redirects"
    HTTP_ERROR = "http_error"
    HOST_UNREACHABLE = "host_unreachable"
    
    # Content/Parsing errors
    RESPONSE_TOO_LARGE = "response_too_large"
    ENCODING_ERROR = "encoding_error"
    INVALID_JSON = "invalid_json"
    INVALID_HTML = "invalid_html"
    EMPTY_RESPONSE = "empty_response"
    UNSUPPORTED_CONTENT_TYPE = "unsupported_content_type"
    
    # Server errors
    NODE_ROUTING_FAILED = "node_routing_failed"
    PARSING_ERROR = "parsing_error"
    INTERNAL_ERROR = "internal_error"


class ScraperError(Exception):
    """Base exception for scraper errors."""
    
    def __init__(
        self,
        error_code: ScraperErrorCode,
        message: str,
        status_code: int,
        extra_details: Optional[Dict[str, Any]] = None
    ):
        self.error_code = error_code
        self.message = message
        self.status_code = status_code
        self.extra_details = extra_details or {}
        super().__init__(message)
    
    def to_response(self) -> Tuple[Dict[str, Any], int]:
        """Convert error to Flask JSON response format."""
        response = {
            'success': False,
            'error': self.error_code.value,
            'message': self.message
        }
        response.update(self.extra_details)
        return response, self.status_code


def validate_url(url: str) -> Tuple[bool, Optional[ScraperError]]:
    """
    Validate URL format and safety.
    
    Returns:
        (is_valid, error) - error is None if valid
    """
    if not url:
        return False, ScraperError(
            ScraperErrorCode.MISSING_URL,
            "URL is required",
            400
        )
    
    url = url.strip()
    if not url:
        return False, ScraperError(
            ScraperErrorCode.MISSING_URL,
            "URL cannot be empty",
            400
        )
    
    # Check URL format
    if not re.match(r'^https?://', url, re.IGNORECASE):
        return False, ScraperError(
            ScraperErrorCode.INVALID_URL,
            "URL must start with http:// or https://",
            400
        )
    
    # Check for embedded credentials
    if re.search(r'[a-zA-Z0-9]+://[^/]*@', url):
        return False, ScraperError(
            ScraperErrorCode.INVALID_URL,
            "URLs with embedded credentials are not allowed",
            400
        )
    
    # Check length
    if len(url) > 2048:
        return False, ScraperError(
            ScraperErrorCode.INVALID_URL,
            "URL exceeds maximum length (2048 characters)",
            400
        )
    
    return True, None


def validate_format(format_str: str) -> Tuple[bool, Optional[ScraperError]]:
    """
    Validate output format parameter.
    
    Returns:
        (is_valid, error) - error is None if valid
    """
    valid_formats = {'text', 'html', 'json'}
    
    if not format_str:
        # Default to 'text' if not provided
        return True, None
    
    format_str = format_str.strip().lower()
    
    if format_str not in valid_formats:
        return False, ScraperError(
            ScraperErrorCode.INVALID_FORMAT,
            f"Invalid format. Must be one of: {', '.join(sorted(valid_formats))}",
            400,
            {'valid_formats': sorted(valid_formats)}
        )
    
    return True, None


def validate_payment_params(
    api_key: Optional[str],
    wallet: Optional[str],
    tx_signature: Optional[str]
) -> Tuple[bool, Optional[ScraperError]]:
    """
    Validate that either API key or payment parameters are provided.
    
    Returns:
        (has_payment_method, error) - error is None if valid
    """
    has_api_key = bool(api_key and api_key.strip())
    has_wallet = bool(wallet and wallet.strip())
    has_tx = bool(tx_signature and tx_signature.strip())
    
    if not has_api_key and not (has_wallet and has_tx):
        return False, ScraperError(
            ScraperErrorCode.MISSING_PAYMENT,
            "Payment required: either API key or WATT transaction signature",
            402,
            {
                'price_watt': 100,
                'payment_to': '7vvNkG3JF3JpxLEavqZSkc5T3n9hHR98Uw23fbWdXVSF',
                'methods': ['api_key', 'watt_payment']
            }
        )
    
    if not has_api_key and has_wallet and not has_tx:
        return False, ScraperError(
            ScraperErrorCode.MISSING_PAYMENT,
            "Transaction signature required when paying with WATT",
            400
        )
    
    if not has_api_key and not has_wallet and has_tx:
        return False, ScraperError(
            ScraperErrorCode.MISSING_PAYMENT,
            "Wallet address required when paying with WATT",
            400
        )
    
    return True, None


def network_error_to_scraper_error(
    exc: Exception
) -> ScraperError:
    """
    Convert requests library exceptions to ScraperError with appropriate details.
    """
    import requests
    
    exc_type = type(exc).__name__
    exc_str = str(exc)
    
    # Timeout
    if isinstance(exc, requests.Timeout):
        return ScraperError(
            ScraperErrorCode.TIMEOUT,
            "Request timed out. The target server took too long to respond.",
            504
        )
    
    # SSL/TLS certificate errors (must come before ConnectionError — SSLError is a subclass)
    if isinstance(exc, requests.exceptions.SSLError):
        return ScraperError(
            ScraperErrorCode.SSL_ERROR,
            "SSL/TLS certificate error. The target server's certificate is invalid or untrusted.",
            502
        )
    
    # Connection errors
    if isinstance(exc, requests.ConnectionError):
        # Try to determine the specific type
        if 'Name or service not known' in exc_str or 'Failed to resolve' in exc_str:
            return ScraperError(
                ScraperErrorCode.DNS_ERROR,
                "Unable to resolve domain name. Check that the domain is valid and accessible.",
                502
            )
        elif 'Connection refused' in exc_str:
            return ScraperError(
                ScraperErrorCode.CONNECTION_ERROR,
                "Connection refused. The target server rejected the connection.",
                502
            )
        elif 'Network is unreachable' in exc_str:
            return ScraperError(
                ScraperErrorCode.HOST_UNREACHABLE,
                "Host is unreachable. Check that the host address is valid.",
                502
            )
        else:
            return ScraperError(
                ScraperErrorCode.CONNECTION_ERROR,
                "Failed to connect to the target server. Check the URL and try again.",
                502
            )
    
    # Generic request exception
    if isinstance(exc, requests.RequestException):
        return ScraperError(
            ScraperErrorCode.HTTP_ERROR,
            "HTTP request failed. Please verify the URL and try again.",
            502
        )
    
    # Unknown error
    return ScraperError(
        ScraperErrorCode.INTERNAL_ERROR,
        "An unexpected error occurred while fetching the URL.",
        500
    )


def content_parsing_error(
    format_type: str,
    exc: Optional[Exception] = None
) -> ScraperError:
    """
    Create appropriate error for content parsing failures.
    """
    if format_type == 'json':
        return ScraperError(
            ScraperErrorCode.INVALID_JSON,
            "Response is not valid JSON. Verify the URL returns valid JSON.",
            502
        )
    elif format_type == 'html':
        return ScraperError(
            ScraperErrorCode.INVALID_HTML,
            "Failed to parse HTML response. The content may be corrupted.",
            502
        )
    else:
        return ScraperError(
            ScraperErrorCode.PARSING_ERROR,
            f"Failed to parse response as {format_type}.",
            502
        )


def validate_response_size(
    current_size: int,
    max_size: int
) -> Tuple[bool, Optional[ScraperError]]:
    """
    Validate that response size is within limits.
    
    Returns:
        (is_valid, error) - error is None if valid
    """
    if current_size > max_size:
        max_mb = max_size / (1024 * 1024)
        return False, ScraperError(
            ScraperErrorCode.RESPONSE_TOO_LARGE,
            f"Response exceeds maximum size ({max_mb:.1f} MB). Use a more specific URL or selector.",
            413,
            {'max_bytes': max_size, 'received_bytes': current_size}
        )
    
    return True, None


def validate_http_status(status_code: int) -> Tuple[bool, Optional[ScraperError]]:
    """
    Validate HTTP response status code.
    
    Some status codes indicate the request cannot be fulfilled.
    
    Returns:
        (is_valid, error) - error is None if valid
    """
    # 2xx - OK
    if 200 <= status_code < 300:
        return True, None
    
    # 3xx - Redirects are handled by _fetch_with_redirects
    if 300 <= status_code < 400:
        return True, None  # Should not reach here due to redirect handling
    
    # 4xx - Client errors
    if status_code == 401:
        return False, ScraperError(
            ScraperErrorCode.HTTP_ERROR,
            "The target server requires authentication (HTTP 401).",
            502,
            {'status_code': status_code}
        )
    
    if status_code == 403:
        return False, ScraperError(
            ScraperErrorCode.HTTP_ERROR,
            "Access to the target URL is forbidden (HTTP 403).",
            502,
            {'status_code': status_code}
        )
    
    if status_code == 404:
        return False, ScraperError(
            ScraperErrorCode.HTTP_ERROR,
            "The target URL was not found (HTTP 404). Check the URL and try again.",
            502,
            {'status_code': status_code}
        )
    
    if status_code == 429:
        return False, ScraperError(
            ScraperErrorCode.HTTP_ERROR,
            "The target server is rate limiting requests (HTTP 429). Try again later.",
            502,
            {'status_code': status_code}
        )
    
    if 400 <= status_code < 500:
        return False, ScraperError(
            ScraperErrorCode.HTTP_ERROR,
            f"The server returned an error (HTTP {status_code}). Check the URL and try again.",
            502,
            {'status_code': status_code}
        )
    
    # 5xx - Server errors
    if 500 <= status_code < 600:
        return False, ScraperError(
            ScraperErrorCode.HTTP_ERROR,
            f"The target server returned an error (HTTP {status_code}). Try again later.",
            502,
            {'status_code': status_code}
        )
    
    # Unknown status code
    return False, ScraperError(
        ScraperErrorCode.HTTP_ERROR,
        f"Unexpected HTTP status code: {status_code}",
        502,
        {'status_code': status_code}
    )


def validate_encoding(charset: Optional[str]) -> Tuple[bool, Optional[ScraperError]]:
    """
    Validate that the response encoding is valid or defaults to utf-8.
    
    Returns:
        (is_valid, encoding_to_use)
    """
    default_encoding = 'utf-8'
    
    if not charset:
        return True, default_encoding
    
    try:
        # Try to encode/decode with the charset to verify it's valid
        test_str = "test"
        test_str.encode(charset)
        return True, charset
    except (LookupError, TypeError):
        # Invalid charset, fall back to utf-8
        return True, default_encoding


def validate_content_not_empty(content: Any, format_type: str) -> Tuple[bool, Optional[ScraperError]]:
    """
    Validate that content is not empty after parsing.
    
    Returns:
        (is_valid, error) - error is None if valid
    """
    is_empty = False
    
    if format_type == 'json':
        is_empty = content is None
    elif format_type == 'html':
        is_empty = not content or len(content.strip()) == 0
    else:  # text
        is_empty = not content or len(content.strip()) == 0
    
    if is_empty:
        return False, ScraperError(
            ScraperErrorCode.EMPTY_RESPONSE,
            "The target URL returned empty content. Verify the URL is correct.",
            502
        )
    
    return True, None


def handle_redirect_error(reason: str) -> ScraperError:
    """Create error for redirect handling failures."""
    if "invalid or blocked" in reason.lower():
        return ScraperError(
            ScraperErrorCode.REDIRECT_ERROR,
            "The page redirects to a URL that is blocked or invalid.",
            502
        )
    else:
        return ScraperError(
            ScraperErrorCode.REDIRECT_ERROR,
            "An error occurred while following page redirects.",
            502
        )


def handle_too_many_redirects() -> ScraperError:
    """Create error for too many redirects."""
    return ScraperError(
        ScraperErrorCode.TOO_MANY_REDIRECTS,
        "The page caused too many redirects. The URL may be in a redirect loop.",
        502
    )
