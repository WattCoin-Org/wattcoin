import bridge_web


def test_health_rate_limit_enforced():
    client = bridge_web.app.test_client()

    # 60/min default for public endpoints
    for _ in range(60):
        resp = client.get('/health')
        assert resp.status_code in (200, 503)

    blocked = client.get('/health')
    assert blocked.status_code == 429
    assert blocked.headers.get('Retry-After')


def test_rate_limit_headers_present():
    client = bridge_web.app.test_client()
    resp = client.get('/api/v1/pricing')

    assert resp.status_code == 200
    assert 'X-RateLimit-Limit' in resp.headers
    assert 'X-RateLimit-Remaining' in resp.headers
    assert 'X-RateLimit-Reset' in resp.headers
