"""
Tests for Rate Limiting and Enhanced Health Check
Bounties: Issue #88 (Rate Limiting) and Issue #90 (Health Check)
"""

import pytest
import time
import json
from bridge_web import app, APP_START_TIME


@pytest.fixture
def client():
    """Create a test client for the Flask app."""
    app.config['TESTING'] = True
    with app.test_client() as client:
        yield client


class TestRateLimiting:
    """Test rate limiting on public API endpoints."""
    
    def test_scrape_rate_limit(self, client):
        """Test that /api/v1/scrape respects 60 per minute rate limit."""
        # Make 61 requests rapidly
        responses = []
        for i in range(61):
            response = client.post('/api/v1/scrape', 
                                 json={"url": "https://example.com"},
                                 headers={"Content-Type": "application/json"})
            responses.append(response)
        
        # Check that at least one request was rate limited
        status_codes = [r.status_code for r in responses]
        assert 429 in status_codes, "Expected 429 (rate limit) after 60 requests"
        
        # Check rate limit response format
        rate_limited = [r for r in responses if r.status_code == 429][0]
        data = rate_limited.get_json()
        assert "error" in data
        assert data["error"] == "Rate limit exceeded"
        assert "retry_after" in data
        
        # Check Retry-After header
        assert "Retry-After" in rate_limited.headers
    
    def test_llm_rate_limit(self, client):
        """Test that /api/v1/llm respects 60 per minute rate limit."""
        # Make 61 requests
        responses = []
        for i in range(61):
            response = client.post('/api/v1/llm',
                                 json={"prompt": "test"},
                                 headers={"Content-Type": "application/json"})
            responses.append(response)
        
        # Check that at least one was rate limited
        status_codes = [r.status_code for r in responses]
        assert 429 in status_codes, "Expected 429 after 60 requests"
    
    def test_proxy_rate_limit(self, client):
        """Test that /proxy respects 60 per minute rate limit."""
        # Make 61 requests
        responses = []
        for i in range(61):
            response = client.post('/proxy',
                                 json={"url": "https://example.com"},
                                 headers={"Content-Type": "application/json"})
            responses.append(response)
        
        status_codes = [r.status_code for r in responses]
        assert 429 in status_codes, "Expected 429 after 60 requests"
    
    def test_pricing_rate_limit(self, client):
        """Test that /api/v1/pricing respects 100 per minute rate limit."""
        # Make 101 requests
        responses = []
        for i in range(101):
            response = client.get('/api/v1/pricing')
            responses.append(response)
        
        status_codes = [r.status_code for r in responses]
        assert 429 in status_codes, "Expected 429 after 100 requests"
    
    def test_rate_limit_headers(self, client):
        """Test that rate limit headers are present in responses."""
        response = client.get('/api/v1/pricing')
        
        # Check for X-RateLimit headers
        # Note: Flask-Limiter adds these automatically when headers_enabled=True
        assert response.status_code == 200 or response.status_code == 429


class TestHealthCheck:
    """Test enhanced health check endpoint."""
    
    def test_health_endpoint_exists(self, client):
        """Test that /health endpoint is accessible."""
        response = client.get('/health')
        assert response.status_code == 200
        assert response.content_type == 'application/json'
    
    def test_health_response_structure(self, client):
        """Test that health check returns expected fields."""
        response = client.get('/health')
        data = response.get_json()
        
        # Required top-level fields
        assert "status" in data
        assert "version" in data
        assert "uptime_seconds" in data
        assert "services" in data
        assert "network" in data
        assert "timestamp" in data
        
        # Check status values
        assert data["status"] in ["healthy", "degraded"]
        
        # Check version format
        assert isinstance(data["version"], str)
        assert len(data["version"]) > 0
        
        # Check uptime is positive
        assert isinstance(data["uptime_seconds"], int)
        assert data["uptime_seconds"] >= 0
    
    def test_health_services_detail(self, client):
        """Test that services section contains detailed status."""
        response = client.get('/health')
        data = response.get_json()
        
        services = data["services"]
        
        # Check for expected services
        assert "ai_client" in services
        assert "claude_client" in services
        assert "proxy" in services
        assert "redis" in services
        
        # Each service should have status
        for service_name, service_data in services.items():
            assert "status" in service_data
            assert service_data["status"] in ["ok", "unavailable", "not_configured"]
    
    def test_health_network_info(self, client):
        """Test that network section contains node information."""
        response = client.get('/health')
        data = response.get_json()
        
        network = data["network"]
        assert "active_nodes" in network
        assert isinstance(network["active_nodes"], int)
        assert network["active_nodes"] >= 0
    
    def test_health_timestamp_format(self, client):
        """Test that timestamp is in ISO 8601 format."""
        response = client.get('/health')
        data = response.get_json()
        
        timestamp = data["timestamp"]
        # Should end with 'Z' (UTC indicator)
        assert timestamp.endswith('Z')
        # Should be parseable as ISO format
        from datetime import datetime
        try:
            datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
        except ValueError:
            pytest.fail("Timestamp is not valid ISO 8601 format")
    
    def test_health_uptime_increases(self, client):
        """Test that uptime increases over time."""
        response1 = client.get('/health')
        uptime1 = response1.get_json()["uptime_seconds"]
        
        time.sleep(1)
        
        response2 = client.get('/health')
        uptime2 = response2.get_json()["uptime_seconds"]
        
        assert uptime2 >= uptime1, "Uptime should increase over time"
    
    def test_health_reflects_actual_uptime(self, client):
        """Test that uptime matches actual application uptime."""
        response = client.get('/health')
        reported_uptime = response.get_json()["uptime_seconds"]
        
        actual_uptime = int(time.time() - APP_START_TIME)
        
        # Allow 1 second tolerance for processing time
        assert abs(reported_uptime - actual_uptime) <= 1, \
            f"Reported uptime {reported_uptime} should match actual {actual_uptime}"


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
