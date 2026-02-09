import requests

def test_get_bounties(base_url):
    response = requests.get(f"{base_url}/bounties")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    if len(data) > 0:
        bounty = data[0]
        assert "id" in bounty
        assert "amount" in bounty
