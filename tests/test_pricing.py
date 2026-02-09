import requests

def test_get_pricing(base_url):
    response = requests.get(f"{base_url}/pricing")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, dict) or isinstance(data, list)
