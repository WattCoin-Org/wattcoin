import requests

def test_get_solutions(base_url):
    response = requests.get(f"{base_url}/solutions")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    if len(data) > 0:
        solution = data[0]
        assert "id" in solution
        assert "task_id" in solution
