class Bounties:
    def __init__(self, client):
        self.client = client

    def list(self, bounty_type=None):
        params = {}
        if bounty_type:
            params["type"] = bounty_type
        return self.client._request("GET", "bounties", params=params)

    def propose(self, title, description, reward):
        # Based on typical bounty platforms, this might be a POST
        # For now, following the requested method name
        data = {
            "title": title,
            "description": description,
            "reward": reward,
            "wallet": self.client.wallet
        }
        return self.client._request("POST", "bounties", json=data)
