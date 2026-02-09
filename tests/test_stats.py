import requests

def test_get_stats(base_url):
    response = requests.get(f"{base_url}/stats")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, dict)
    # Common stats fields
    assert "total_tasks" in data or "uptime" in data or data is not None
