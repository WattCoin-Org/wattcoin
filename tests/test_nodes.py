import requests

def test_get_nodes(base_url):
    response = requests.get(f"{base_url}/nodes")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    if len(data) > 0:
        node = data[0]
        assert "id" in node
        assert "status" in node
