import json

import bridge_web


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
    client = bridge_web.app.test_client()
    response = client.post("/api/v1/scrape", json={"format": "text"})
    assert response.status_code == 400
    data = response.get_json()
    assert data["success"] is False
    assert "URL required" in data["error"]


def test_scrape_invalid_format(monkeypatch):
    client = bridge_web.app.test_client()
    response = client.post("/api/v1/scrape", json={"url": "https://example.com", "format": "xml"})
    assert response.status_code == 400
    data = response.get_json()
    assert data["success"] is False
    assert "Invalid format" in data["error"]


def test_scrape_invalid_url(monkeypatch):
    monkeypatch.setattr(bridge_web, "_validate_scrape_url", lambda _url: False)
    client = bridge_web.app.test_client()
    response = client.post("/api/v1/scrape", json={"url": "http://localhost", "format": "text"})
    assert response.status_code == 400
    data = response.get_json()
    assert data["success"] is False
    assert "Invalid or blocked URL" in data["error"]


def test_scrape_text_success(monkeypatch):
    monkeypatch.setattr(bridge_web, "_validate_scrape_url", lambda _url: True)
    monkeypatch.setattr(bridge_web, "_check_rate_limit", lambda _ip, _url: (True, None))
    html = b"<html><body><h1>Hello</h1></body></html>"
    monkeypatch.setattr(bridge_web, "_fetch_with_redirects", lambda _url, _headers: _mock_response(html))

    client = bridge_web.app.test_client()
    response = client.post("/api/v1/scrape", json={"url": "https://example.com", "format": "text"})
    assert response.status_code == 200
    data = response.get_json()
    assert data["success"] is True
    assert data["format"] == "text"
    assert data["content"] == "Hello"


def test_scrape_json_success(monkeypatch):
    monkeypatch.setattr(bridge_web, "_validate_scrape_url", lambda _url: True)
    monkeypatch.setattr(bridge_web, "_check_rate_limit", lambda _ip, _url: (True, None))
    payload = json.dumps({"ok": True}).encode("utf-8")
    monkeypatch.setattr(bridge_web, "_fetch_with_redirects", lambda _url, _headers: _mock_response(payload))

    client = bridge_web.app.test_client()
    response = client.post("/api/v1/scrape", json={"url": "https://example.com", "format": "json"})
    assert response.status_code == 200
    data = response.get_json()
    assert data["success"] is True
    assert data["content"] == {"ok": True}
