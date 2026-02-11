class Reputation:
    def __init__(self, client):
        self.client = client

    def leaderboard(self):
        return self.client._request("GET", "reputation")

    def score(self, username):
        return self.client._request("GET", f"reputation/{username}")
