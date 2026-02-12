import types

import skills.wattcoin.wattcoin as wc


def _mock_response(status_code=200, payload=None):
    if payload is None:
        payload = {"total_watt": 12.5, "jobs_completed": 3, "success_rate": 0.9}

    def json_func():
        return payload

    return types.SimpleNamespace(status_code=status_code, json=json_func)


def test_invalid_node_id():
    try:
        wc.get_node_earnings("@@")
    except ValueError as exc:
        assert "Invalid node ID" in str(exc)
    else:
        raise AssertionError("Expected ValueError")


def test_missing_base_url(monkeypatch):
    monkeypatch.delenv("WATTNODE_API_BASE_URL", raising=False)
    try:
        wc.get_node_earnings("node_abc123")
    except RuntimeError as exc:
        assert "WATTNODE_API_BASE_URL" in str(exc)
    else:
        raise AssertionError("Expected RuntimeError")


def test_success(monkeypatch):
    monkeypatch.setenv("WATTNODE_API_BASE_URL", "https://api.example.com")
    monkeypatch.setattr(wc.requests, "get", lambda _url, timeout: _mock_response())

    result = wc.get_node_earnings("node_abc123")
    assert result == {"total_watt": 12.5, "jobs_completed": 3, "success_rate": 0.9}


def test_success_with_data_wrapper(monkeypatch):
    monkeypatch.setenv("WATTNODE_API_BASE_URL", "https://api.example.com")
    payload = {"data": {"total_watt": 5, "jobs_completed": 1, "success_rate": 1.0}}
    monkeypatch.setattr(wc.requests, "get", lambda _url, timeout: _mock_response(payload=payload))

    result = wc.get_node_earnings("node_abc123")
    assert result == {"total_watt": 5.0, "jobs_completed": 1, "success_rate": 1.0}


def test_invalid_node_id_from_api(monkeypatch):
    monkeypatch.setenv("WATTNODE_API_BASE_URL", "https://api.example.com")
    monkeypatch.setattr(wc.requests, "get", lambda _url, timeout: _mock_response(status_code=404))

    try:
        wc.get_node_earnings("node_abc123")
    except ValueError as exc:
        assert "Invalid node ID" in str(exc)
    else:
        raise AssertionError("Expected ValueError")


def test_timeout_raises_runtime_error(monkeypatch):
    monkeypatch.setenv("WATTNODE_API_BASE_URL", "https://api.example.com")

    def _raise_timeout(_url, timeout):
        raise wc.requests.Timeout("boom")

    monkeypatch.setattr(wc.requests, "get", _raise_timeout)

    try:
        wc.get_node_earnings("node_abc123")
    except RuntimeError as exc:
        assert "timed out" in str(exc)
    else:
        raise AssertionError("Expected RuntimeError")


def test_server_error(monkeypatch):
    monkeypatch.setenv("WATTNODE_API_BASE_URL", "https://api.example.com")
    monkeypatch.setattr(wc.requests, "get", lambda _url, timeout: _mock_response(status_code=500))

    try:
        wc.get_node_earnings("node_abc123")
    except RuntimeError as exc:
        assert "Server error" in str(exc)
    else:
        raise AssertionError("Expected RuntimeError")


def test_rejects_out_of_range_success_rate(monkeypatch):
    monkeypatch.setenv("WATTNODE_API_BASE_URL", "https://api.example.com")
    payload = {"total_watt": 12.5, "jobs_completed": 3, "success_rate": 1.2}
    monkeypatch.setattr(wc.requests, "get", lambda _url, timeout: _mock_response(payload=payload))

    try:
        wc.get_node_earnings("node_abc123")
    except RuntimeError as exc:
        assert "Malformed response" in str(exc)
    else:
        raise AssertionError("Expected RuntimeError")
