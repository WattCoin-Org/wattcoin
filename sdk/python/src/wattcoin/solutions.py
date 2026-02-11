class Solutions:
    def __init__(self, client):
        self.client = client

    def list(self, task_id=None):
        endpoint = "solutions"
        params = {}
        if task_id:
            params["task_id"] = task_id
        return self.client._request("GET", endpoint, params=params)

    def claim(self, solution_id):
        return self.client._request("POST", f"solutions/{solution_id}/claim", json={"wallet": self.client.wallet})
