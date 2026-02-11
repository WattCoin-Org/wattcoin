class Tasks:
    def __init__(self, client):
        self.client = client

    def list(self):
        return self.client._request("GET", "tasks")

    def post(self, title, description, reward, tx_signature):
        data = {
            "title": title,
            "description": description,
            "reward": reward,
            "tx_signature": tx_signature,
            "poster_wallet": self.client.wallet
        }
        return self.client._request("POST", "tasks", json=data)

    def submit(self, task_id, result):
        data = {
            "result": result,
            "wallet": self.client.wallet
        }
        return self.client._request("POST", f"tasks/{task_id}/submit", json=data)
