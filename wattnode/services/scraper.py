"""
WattNode Local Scraper Service
Fetches web content for scrape jobs

Error handling covers:
- Network timeouts
- SSL/TLS certificate errors
- DNS resolution failures
- Connection refused / host unreachable
- HTTP error status codes (401, 403, 404, 429, 500, 503)
- Malformed URLs
- Response size limits
- Malformed JSON/HTML content
"""

import json
import logging
import random

import requests
from bs4 import BeautifulSoup

# User agents for rotation
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36",
]

TIMEOUT = 30
MAX_SIZE = 2 * 1024 * 1024  # 2MB
MAX_REDIRECTS = 3

logger = logging.getLogger("wattnode.scraper")


# ---------------------------------------------------------------------------
# Custom exception hierarchy
# ---------------------------------------------------------------------------

class ScraperException(Exception):
    """Base exception for all local scraper errors."""
    def __init__(self, message: str, error_code: str, status_code: int = 500):
        super().__init__(message)
        self.error_code = error_code
        self.status_code = status_code

    def to_dict(self) -> dict:
        return {"success": False, "error": self.error_code, "message": str(self)}


class InvalidURLError(ScraperException):
    def __init__(self, message="URL is malformed or missing a scheme"):
        super().__init__(message, "invalid_url", 400)


class TimeoutError_(ScraperException):
    def __init__(self):
        super().__init__(
            "Request timed out. The target server took too long to respond.",
            "timeout", 504
        )


class SSLError(ScraperException):
    def __init__(self):
        super().__init__(
            "SSL/TLS certificate error. The target server's certificate is invalid or untrusted.",
            "ssl_error", 502
        )


class DNSError(ScraperException):
    def __init__(self):
        super().__init__(
            "Unable to resolve domain name. Check that the domain is valid and accessible.",
            "dns_error", 502
        )


class ConnectionRefusedError_(ScraperException):
    def __init__(self):
        super().__init__(
            "Connection refused. The target server rejected the connection.",
            "connection_error", 502
        )


class HostUnreachableError(ScraperException):
    def __init__(self):
        super().__init__(
            "Host is unreachable. Check that the host address is valid.",
            "host_unreachable", 502
        )


class HTTPError(ScraperException):
    """Wraps a non-2xx status code returned by the target server."""
    _MESSAGES = {
        401: "The target server requires authentication (HTTP 401).",
        403: "Access to the target URL is forbidden (HTTP 403).",
        404: "The target URL was not found (HTTP 404). Check the URL and try again.",
        429: "The target server is rate limiting requests (HTTP 429). Try again later.",
        500: "The target server returned an internal error (HTTP 500). Try again later.",
        503: "The target server is unavailable (HTTP 503). Try again later.",
    }

    def __init__(self, status_code: int):
        msg = self._MESSAGES.get(
            status_code,
            f"The target server returned an error (HTTP {status_code})."
        )
        super().__init__(msg, "http_error", 502)
        self.http_status_code = status_code

    def to_dict(self) -> dict:
        d = super().to_dict()
        d["status_code"] = self.http_status_code
        return d


class ResponseTooLargeError(ScraperException):
    def __init__(self, received: int):
        super().__init__(
            f"Response exceeds maximum size ({MAX_SIZE / 1024 / 1024:.1f} MB). "
            "Use a more specific URL or selector.",
            "response_too_large", 413
        )
        self.received = received

    def to_dict(self) -> dict:
        d = super().to_dict()
        d["max_bytes"] = MAX_SIZE
        d["received_bytes"] = self.received
        return d


class EmptyResponseError(ScraperException):
    def __init__(self):
        super().__init__(
            "The target URL returned empty content. Verify the URL is correct.",
            "empty_response", 502
        )


class InvalidJSONError(ScraperException):
    def __init__(self):
        super().__init__(
            "Response is not valid JSON. Verify the URL returns valid JSON.",
            "invalid_json", 502
        )


class ParsingError(ScraperException):
    def __init__(self, detail: str = ""):
        msg = "An error occurred while parsing the response"
        if detail:
            msg += f": {detail}"
        super().__init__(msg, "parsing_error", 500)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _validate_url(url: str) -> None:
    """Raise InvalidURLError if *url* is missing or has no http(s) scheme."""
    if not url or not url.strip():
        raise InvalidURLError("URL is required")
    url = url.strip()
    if not url.lower().startswith(("http://", "https://")):
        raise InvalidURLError("URL must start with http:// or https://")


def _map_connection_error(exc: requests.ConnectionError) -> ScraperException:
    """Translate a requests.ConnectionError into the most specific subclass."""
    msg = str(exc)
    if "Name or service not known" in msg or "Failed to resolve" in msg:
        return DNSError()
    if "Connection refused" in msg:
        return ConnectionRefusedError_()
    if "Network is unreachable" in msg:
        return HostUnreachableError()
    # Generic fallback
    return ScraperException(
        "Failed to connect to the target server. Check the URL and try again.",
        "connection_error", 502
    )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def local_scrape(url: str, format: str = "text") -> str:
    """
    Scrape a URL and return content.

    Args:
        url: URL to scrape
        format: Output format — "text", "html", or "json"

    Returns:
        Scraped content as string (or parsed dict for json)

    Raises:
        InvalidURLError:          Malformed or missing URL
        TimeoutError_:            Target did not respond within TIMEOUT
        SSLError:                 TLS/SSL handshake failed
        DNSError:                 Domain could not be resolved
        ConnectionRefusedError_:  Target actively refused the TCP connection
        HostUnreachableError:     Network path to host is unreachable
        HTTPError:                Target returned a non-2xx status
        ResponseTooLargeError:    Body exceeded MAX_SIZE
        EmptyResponseError:       Body was empty after download
        InvalidJSONError:         format=="json" but body is not valid JSON
        ParsingError:             Other parsing failure
    """
    logger.info("local_scrape started | url=%.120s format=%s", url, format)

    # --- input validation --------------------------------------------------
    _validate_url(url)
    url = url.strip()

    headers = {
        "User-Agent": random.choice(USER_AGENTS),
        "Accept": "text/html,application/json;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
    }

    # --- network fetch -----------------------------------------------------
    try:
        resp = requests.get(
            url,
            headers=headers,
            timeout=TIMEOUT,
            stream=True,
            allow_redirects=True,
            verify=True,           # enforce SSL verification
        )
    except requests.exceptions.SSLError as exc:
        logger.warning("ssl error | url=%.120s error=%s", url, str(exc)[:120])
        raise SSLError() from exc
    except requests.exceptions.Timeout as exc:
        logger.warning("timeout | url=%.120s", url)
        raise TimeoutError_() from exc
    except requests.exceptions.ConnectionError as exc:
        logger.warning("connection error | url=%.120s error=%s", url, str(exc)[:120])
        raise _map_connection_error(exc) from exc
    except requests.exceptions.RequestException as exc:
        logger.error("unexpected request error | url=%.120s type=%s", url, type(exc).__name__)
        raise ScraperException(
            "HTTP request failed. Please verify the URL and try again.",
            "connection_error", 502
        ) from exc

    # --- HTTP status -------------------------------------------------------
    if resp.status_code < 200 or resp.status_code >= 300:
        logger.warning("http error | url=%.120s status=%d", url, resp.status_code)
        raise HTTPError(resp.status_code)

    # --- read body with size cap -------------------------------------------
    content = bytearray()
    try:
        for chunk in resp.iter_content(chunk_size=8192):
            if chunk:
                content.extend(chunk)
                if len(content) > MAX_SIZE:
                    logger.warning("response too large | url=%.120s size=%d", url, len(content))
                    raise ResponseTooLargeError(len(content))
    except ResponseTooLargeError:
        raise  # re-raise our own error
    except Exception as exc:
        logger.error("read error | url=%.120s type=%s", url, type(exc).__name__)
        raise ParsingError("failed to read response body") from exc

    # --- empty check -------------------------------------------------------
    if len(content) == 0:
        logger.warning("empty response | url=%.120s", url)
        raise EmptyResponseError()

    # --- decode ------------------------------------------------------------
    encoding = resp.encoding or "utf-8"
    try:
        text = bytes(content).decode(encoding, errors="replace")
    except Exception as exc:
        logger.error("decode error | url=%.120s encoding=%s", url, encoding)
        raise ParsingError(f"failed to decode response with encoding '{encoding}'") from exc

    # --- format output -----------------------------------------------------
    try:
        if format == "html":
            result = text

        elif format == "json":
            try:
                result = json.loads(text)
            except json.JSONDecodeError as exc:
                logger.warning("invalid json | url=%.120s", url)
                raise InvalidJSONError() from exc

        else:  # text (default)
            soup = BeautifulSoup(text, "html.parser")
            for element in soup(["script", "style", "nav", "footer", "header"]):
                element.decompose()
            result = soup.get_text(separator=" ", strip=True)
    except (InvalidJSONError, EmptyResponseError):
        raise  # already the right type
    except Exception as exc:
        logger.error("parsing error | url=%.120s format=%s type=%s", url, format, type(exc).__name__)
        raise ParsingError(str(exc)) from exc

    logger.info("local_scrape success | url=%.120s format=%s", url, format)
    return result


if __name__ == "__main__":
    # Quick smoke test
    import sys
    target = sys.argv[1] if len(sys.argv) > 1 else "https://example.com"
    try:
        print(local_scrape(target)[:500])
    except ScraperException as e:
        print(f"[{e.error_code}] {e}")
