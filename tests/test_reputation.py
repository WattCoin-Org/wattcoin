import requests

def test_get_reputation(base_url):
    response = requests.get(f"{base_url}/reputation")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list) or isinstance(data, dict)
