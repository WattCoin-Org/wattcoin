import requests

def test_get_tasks(base_url):
    response = requests.get(f"{base_url}/tasks")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    if len(data) > 0:
        task = data[0]
        assert "id" in task
        assert "status" in task
