import json

import bridge_web
from scraper_errors import ScraperErrorCode


def _mock_response(body_bytes, status_code=200, encoding="utf-8"):
    class MockResponse:
        def __init__(self):
            self.status_code = status_code
            self.encoding = encoding
            self.headers = {}

        def iter_content(self, chunk_size=8192):
            yield body_bytes

    return MockResponse()


def test_scrape_requires_url(monkeypatch):
    """Test that URL is required."""
    client = bridge_web.app.test_client()
    response = client.post("/api/v1/scrape", json={"format": "text"})
    assert response.status_code == 400
    data = response.get_json()
    assert data["success"] is False
    assert data["error"] == ScraperErrorCode.MISSING_URL.value


def test_scrape_invalid_format(monkeypatch):
    """Test that invalid format is rejected."""
    client = bridge_web.app.test_client()
    response = client.post("/api/v1/scrape", json={"url": "https://example.com", "format": "xml"})
    assert response.status_code == 400
    data = response.get_json()
    assert data["success"] is False
    assert data["error"] == ScraperErrorCode.INVALID_FORMAT.value


def test_scrape_invalid_url(monkeypatch):
    """Test that invalid URLs are blocked."""
    monkeypatch.setattr(bridge_web, "_validate_scrape_url", lambda _url: False)
    client = bridge_web.app.test_client()
    response = client.post("/api/v1/scrape", json={"url": "http://localhost", "format": "text"})
    assert response.status_code == 400
    data = response.get_json()
    assert data["success"] is False
    assert data["error"] == ScraperErrorCode.URL_BLOCKED.value


def test_scrape_text_success(monkeypatch):
    """Test successful text scraping with payment."""
    monkeypatch.setattr(bridge_web, "_validate_scrape_url", lambda _url: True)
    monkeypatch.setattr(bridge_web, "_check_rate_limit", lambda _ip, _url: (True, None))
    html = b"<html><body><h1>Hello</h1></body></html>"
    monkeypatch.setattr(bridge_web, "_fetch_with_redirects", lambda _url, _headers: _mock_response(html))
    # Mock payment verification
    monkeypatch.setattr(bridge_web, "verify_watt_payment", lambda sig, wallet, amt: (True, None, None))

    client = bridge_web.app.test_client()
    response = client.post("/api/v1/scrape", json={
        "url": "https://example.com",
        "format": "text",
        "wallet": "test_wallet",
        "tx_signature": "test_sig"
    })
    assert response.status_code == 200
    data = response.get_json()
    assert data["success"] is True
    assert data["format"] == "text"
    assert data["content"] == "Hello"


def test_scrape_json_success(monkeypatch):
    """Test successful JSON scraping with payment."""
    monkeypatch.setattr(bridge_web, "_validate_scrape_url", lambda _url: True)
    monkeypatch.setattr(bridge_web, "_check_rate_limit", lambda _ip, _url: (True, None))
    payload = json.dumps({"ok": True}).encode("utf-8")
    monkeypatch.setattr(bridge_web, "_fetch_with_redirects", lambda _url, _headers: _mock_response(payload))
    # Mock payment verification
    monkeypatch.setattr(bridge_web, "verify_watt_payment", lambda sig, wallet, amt: (True, None, None))

    client = bridge_web.app.test_client()
    response = client.post("/api/v1/scrape", json={
        "url": "https://example.com",
        "format": "json",
        "wallet": "test_wallet",
        "tx_signature": "test_sig"
    })
    assert response.status_code == 200
    data = response.get_json()
    assert data["success"] is True
    assert data["content"] == {"ok": True}
