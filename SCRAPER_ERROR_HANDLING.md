# Web Scraper Error Handling (WattCoin-28)

## Overview

Comprehensive error handling implementation for the `/api/v1/scrape` endpoint. This document describes all error codes, status codes, and messages returned by the web scraper API.

## Error Response Format

All error responses follow a consistent JSON format:

```json
{
  "success": false,
  "error": "error_code",
  "message": "Human-readable error description",
  "optional_field": "Additional context (varies by error)"
}
```

### Example Error Response

```json
{
  "success": false,
  "error": "invalid_json",
  "message": "Response is not valid JSON. Verify the URL returns valid JSON."
}
```

---

## Error Codes and HTTP Status Codes

### Input Validation Errors (4xx)

#### `missing_url` - HTTP 400
- **Cause**: URL parameter is missing or empty
- **Message**: "URL is required" or "URL cannot be empty"
- **Example**:
  ```json
  {
    "success": false,
    "error": "missing_url",
    "message": "URL is required"
  }
  ```

#### `invalid_url` - HTTP 400
- **Cause**: URL format is invalid
- **Possible causes**:
  - Missing `http://` or `https://` protocol
  - Embedded credentials in URL (e.g., `https://user:pass@example.com`)
  - URL exceeds maximum length (2048 characters)
- **Message**: Specific reason for invalidity
- **Example**:
  ```json
  {
    "success": false,
    "error": "invalid_url",
    "message": "URL must start with http:// or https://"
  }
  ```

#### `url_blocked` - HTTP 400
- **Cause**: URL is blocked for security reasons
- **Possible causes**:
  - Domain is on blocklist
  - URL resolves to private/internal IP
  - Localhost or 127.0.0.1
- **Message**: "URL is blocked or invalid for security reasons"
- **Example**:
  ```json
  {
    "success": false,
    "error": "url_blocked",
    "message": "URL is blocked or invalid for security reasons"
  }
  ```

#### `invalid_format` - HTTP 400
- **Cause**: Output format is invalid
- **Valid formats**: `text`, `html`, `json`
- **Message**: Lists valid formats
- **Example**:
  ```json
  {
    "success": false,
    "error": "invalid_format",
    "message": "Invalid format. Must be one of: html, json, text",
    "valid_formats": ["html", "json", "text"]
  }
  ```

---

### Payment Errors (4xx)

#### `missing_payment` - HTTP 402
- **Cause**: Neither API key nor WATT payment provided
- **Fix**: Provide either:
  1. `X-API-Key` header with valid API key, OR
  2. Both `wallet` and `tx_signature` in request body
- **Message**: "Payment required: either API key or WATT transaction signature"
- **Example**:
  ```json
  {
    "success": false,
    "error": "missing_payment",
    "message": "Payment required: either API key or WATT transaction signature",
    "price_watt": 100,
    "payment_to": "7vvNkG3JF3JpxLEavqZSkc5T3n9hHR98Uw23fbWdXVSF",
    "methods": ["api_key", "watt_payment"]
  }
  ```

#### `invalid_api_key` - HTTP 401
- **Cause**: API key provided but invalid or inactive
- **Fix**: Check API key is correct and active
- **Message**: "The provided API key is invalid or inactive"
- **Example**:
  ```json
  {
    "success": false,
    "error": "invalid_api_key",
    "message": "The provided API key is invalid or inactive"
  }
  ```

#### `invalid_payment` - HTTP 400
- **Cause**: WATT transaction signature is invalid
- **Possible causes**:
  - Signature doesn't verify against wallet
  - Signature format is incorrect
- **Message**: Specific verification error
- **Example**:
  ```json
  {
    "success": false,
    "error": "invalid_payment",
    "message": "Transaction signature verification failed"
  }
  ```

#### `payment_failed` - HTTP 400
- **Cause**: Payment verification failed
- **Possible causes**:
  - Insufficient WATT amount in transaction
  - Transaction signature already used
  - Transaction not found
- **Message**: Specific reason for failure
- **Example**:
  ```json
  {
    "success": false,
    "error": "payment_failed",
    "message": "Transaction signature has already been used"
  }
  ```

#### `rate_limit_exceeded` - HTTP 429
- **Cause**: API key rate limit exceeded
- **Rate limits**:
  - `basic`: 500 requests/hour
  - `premium`: 2000 requests/hour
- **Fix**: Wait `retry_after_seconds` before retrying
- **Example**:
  ```json
  {
    "success": false,
    "error": "rate_limit_exceeded",
    "message": "Rate limit exceeded for tier 'basic'. Try again in 3600 seconds.",
    "retry_after_seconds": 3600,
    "tier": "basic"
  }
  ```

---

### Network Errors (5xx)

#### `timeout` - HTTP 504
- **Cause**: Request to target server timed out
- **Timeout limit**: 30 seconds
- **Fix**: Try again or use a faster URL
- **Message**: "Request timed out. The target server took too long to respond."
- **Example**:
  ```json
  {
    "success": false,
    "error": "timeout",
    "message": "Request timed out. The target server took too long to respond."
  }
  ```

#### `dns_error` - HTTP 502
- **Cause**: Unable to resolve domain name
- **Possible causes**:
  - Domain doesn't exist
  - DNS server unreachable
  - Typo in domain
- **Fix**: Check that domain name is correct
- **Message**: "Unable to resolve domain name. Check that the domain is valid and accessible."
- **Example**:
  ```json
  {
    "success": false,
    "error": "dns_error",
    "message": "Unable to resolve domain name. Check that the domain is valid and accessible."
  }
  ```

#### `connection_error` - HTTP 502
- **Cause**: Failed to establish connection to target server
- **Possible causes**:
  - Server rejected connection
  - Network unreachable
  - Firewall blocking connection
- **Fix**: Verify URL is accessible and server is online
- **Message**: "Failed to connect to the target server. Check the URL and try again."
- **Example**:
  ```json
  {
    "success": false,
    "error": "connection_error",
    "message": "Failed to connect to the target server. Check the URL and try again."
  }
  ```

#### `host_unreachable` - HTTP 502
- **Cause**: Host address is unreachable
- **Possible causes**:
  - Network down
  - IP address unreachable
- **Fix**: Try again later or use different URL
- **Message**: "Host is unreachable. Check that the host address is valid."
- **Example**:
  ```json
  {
    "success": false,
    "error": "host_unreachable",
    "message": "Host is unreachable. Check that the host address is valid."
  }
  ```

---

### HTTP Status Code Errors (5xx)

#### `http_error` - HTTP 502
- **Cause**: Target server returned an HTTP error (4xx or 5xx)
- **HTTP codes handled**:
  - `401`: Requires authentication
  - `403`: Access forbidden
  - `404`: Page not found
  - `429`: Too many requests (rate limit)
  - `5xx`: Server error
- **Message**: Varies by status code
- **Examples**:
  ```json
  {
    "success": false,
    "error": "http_error",
    "message": "The target server requires authentication (HTTP 401).",
    "status_code": 401
  }
  ```
  ```json
  {
    "success": false,
    "error": "http_error",
    "message": "The target URL was not found (HTTP 404). Check the URL and try again.",
    "status_code": 404
  }
  ```

---

### Redirect Errors (5xx)

#### `redirect_error` - HTTP 502
- **Cause**: Error during redirect chain following
- **Possible causes**:
  - Redirect to blocked/invalid URL
  - Malformed Location header
- **Message**: "The page redirects to a URL that is blocked or invalid."
- **Example**:
  ```json
  {
    "success": false,
    "error": "redirect_error",
    "message": "The page redirects to a URL that is blocked or invalid."
  }
  ```

#### `too_many_redirects` - HTTP 502
- **Cause**: Redirect chain exceeded limit
- **Redirect limit**: 3 redirects maximum
- **Fix**: URL may be in a redirect loop
- **Message**: "The page caused too many redirects. The URL may be in a redirect loop."
- **Example**:
  ```json
  {
    "success": false,
    "error": "too_many_redirects",
    "message": "The page caused too many redirects. The URL may be in a redirect loop."
  }
  ```

---

### Content Parsing Errors (5xx)

#### `response_too_large` - HTTP 413
- **Cause**: Response exceeds maximum size
- **Size limit**: 2 MB
- **Fix**: Use more specific URL or selector
- **Message**: "Response exceeds maximum size (2.0 MB). Use a more specific URL or selector."
- **Example**:
  ```json
  {
    "success": false,
    "error": "response_too_large",
    "message": "Response exceeds maximum size (2.0 MB). Use a more specific URL or selector.",
    "max_bytes": 2097152,
    "received_bytes": 3145728
  }
  ```

#### `empty_response` - HTTP 502
- **Cause**: Target URL returned empty content
- **Possible causes**:
  - Page is blank or minimal
  - JavaScript-required content not loaded
  - Server returned empty body
- **Fix**: Check URL is correct and loads content
- **Message**: "The target URL returned empty content. Verify the URL is correct."
- **Example**:
  ```json
  {
    "success": false,
    "error": "empty_response",
    "message": "The target URL returned empty content. Verify the URL is correct."
  }
  ```

#### `invalid_json` - HTTP 502
- **Cause**: Response is not valid JSON
- **When**: format=json but response isn't JSON
- **Fix**: Verify URL returns valid JSON
- **Message**: "Response is not valid JSON. Verify the URL returns valid JSON."
- **Example**:
  ```json
  {
    "success": false,
    "error": "invalid_json",
    "message": "Response is not valid JSON. Verify the URL returns valid JSON."
  }
  ```

#### `invalid_html` - HTTP 502
- **Cause**: Failed to parse HTML response
- **Possible causes**:
  - Corrupted content
  - Unsupported encoding
  - Binary content instead of HTML
- **Fix**: Check that URL returns HTML content
- **Message**: "Failed to parse HTML response. The content may be corrupted."
- **Example**:
  ```json
  {
    "success": false,
    "error": "invalid_html",
    "message": "Failed to parse HTML response. The content may be corrupted."
  }
  ```

#### `parsing_error` - HTTP 500
- **Cause**: General error while parsing response
- **Message**: "An error occurred while parsing the response"
- **Example**:
  ```json
  {
    "success": false,
    "error": "parsing_error",
    "message": "An error occurred while parsing the response"
  }
  ```

---

### Server Errors (5xx)

#### `node_routing_failed` - HTTP 502
- **Cause**: WattNode routing failed, using centralized fallback
- **Details**: See response for more info
- **Message**: "Node routing failed, falling back to centralized scraper"
- **Example**:
  ```json
  {
    "success": false,
    "error": "node_routing_failed",
    "message": "Node routing failed, falling back to centralized scraper"
  }
  ```

#### `internal_error` - HTTP 500
- **Cause**: Unexpected server error
- **Contact**: Support if error persists
- **Message**: "An unexpected error occurred while processing your request"
- **Example**:
  ```json
  {
    "success": false,
    "error": "internal_error",
    "message": "An unexpected error occurred while processing your request"
  }
  ```

---

## Success Response

### HTTP 200 - Success

```json
{
  "success": true,
  "url": "https://example.com",
  "content": "...",
  "format": "text",
  "status_code": 200,
  "timestamp": "2026-02-05T10:30:45.123456Z",
  "tx_verified": true,
  "watt_charged": 100
}
```

**Fields**:
- `success`: Always `true` for successful scrapes
- `url`: The URL that was scraped
- `content`: The extracted content
- `format`: The format returned (text, html, or json)
- `status_code`: HTTP status code of the target URL
- `timestamp`: ISO 8601 timestamp of the scrape
- `tx_verified`: (Optional) `true` if paid with WATT
- `watt_charged`: (Optional) Amount of WATT charged (100)
- `api_key_used`: (Optional) `true` if API key was used
- `tier`: (Optional) API key tier (basic, premium, etc.)

---

## Error Recovery Guide

### By HTTP Status Code

| Code | Meaning | Action |
|------|---------|--------|
| 400 | Bad Request | Fix request parameters |
| 401 | Unauthorized | Fix API key or payment |
| 402 | Payment Required | Provide payment |
| 413 | Payload Too Large | Use more specific URL |
| 429 | Too Many Requests | Wait and retry (see retry_after_seconds) |
| 502 | Bad Gateway | Check URL accessibility, retry |
| 504 | Gateway Timeout | Retry request |
| 500 | Server Error | Contact support |

### Common Scenarios

#### "URL not found" (404)
```json
{
  "error": "http_error",
  "status_code": 404,
  "message": "The target URL was not found (HTTP 404)..."
}
```
**Fix**: Check URL spelling and try again

#### "Permission denied" (403)
```json
{
  "error": "http_error",
  "status_code": 403,
  "message": "Access to the target URL is forbidden (HTTP 403)..."
}
```
**Fix**: Verify you have access to the URL, may require authentication

#### "Payment required"
```json
{
  "error": "missing_payment",
  "price_watt": 100,
  "payment_to": "7vvNkG3JF3JpxLEavqZSkc5T3n9hHR98Uw23fbWdXVSF"
}
```
**Fix**: Send 100 WATT to payment_to address, use tx signature in next request

#### "JSON parsing failed"
```json
{
  "error": "invalid_json",
  "message": "Response is not valid JSON..."
}
```
**Fix**: Verify URL returns JSON; try format=text if HTML instead

---

## Testing

All error handling is tested in `tests/test_scrape_error_handling.py`:

```bash
# Run all error handling tests
pytest tests/test_scrape_error_handling.py -v

# Run specific test class
pytest tests/test_scrape_error_handling.py::TestNetworkErrors -v

# Run single test
pytest tests/test_scrape_error_handling.py::TestNetworkErrors::test_timeout_error -v
```

Test coverage includes:
- Input validation (10 tests)
- Payment validation (5 tests)
- Rate limiting (1 test)
- Network errors (3 tests)
- HTTP status codes (5 tests)
- Content parsing (3 tests)
- Redirect handling (2 tests)
- Success scenarios (4 tests)

---

## Security Considerations

### Error Message Design

Error messages are designed to be **informative but not leaky**:

✅ **Safe**: "Unable to resolve domain name. Check that the domain is valid."
❌ **Unsafe**: "DNS lookup failed for example.com: NXDOMAIN"

✅ **Safe**: "The target server returned an error (HTTP 404)."
❌ **Unsafe**: "404 Not Found: /admin/users.json"

### Data Protection

- No request/response bodies shown in errors
- No internal system details exposed
- No sensitive headers displayed
- No stack traces in error messages
- All error responses scrubbed of PII

---

## Error Code Reference

| Error Code | HTTP | Category | Retryable |
|-----------|------|----------|-----------|
| `missing_url` | 400 | Input | No |
| `invalid_url` | 400 | Input | No |
| `url_blocked` | 400 | Input | No |
| `invalid_format` | 400 | Input | No |
| `missing_payment` | 402 | Auth | No |
| `invalid_api_key` | 401 | Auth | No |
| `invalid_payment` | 400 | Auth | No |
| `payment_failed` | 400 | Auth | No |
| `rate_limit_exceeded` | 429 | Auth | Yes (after retry_after) |
| `timeout` | 504 | Network | Yes |
| `dns_error` | 502 | Network | Yes |
| `connection_error` | 502 | Network | Yes |
| `host_unreachable` | 502 | Network | Yes |
| `http_error` | 502 | HTTP | Depends on code |
| `redirect_error` | 502 | HTTP | No |
| `too_many_redirects` | 502 | HTTP | No |
| `response_too_large` | 413 | Content | No |
| `empty_response` | 502 | Content | No |
| `invalid_json` | 502 | Content | No |
| `invalid_html` | 502 | Content | No |
| `parsing_error` | 500 | Content | Yes |
| `node_routing_failed` | 502 | Server | Yes |
| `internal_error` | 500 | Server | Yes |
