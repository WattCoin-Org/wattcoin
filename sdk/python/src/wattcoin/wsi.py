class WSI:
    def __init__(self, client):
        self.client = client

    def query(self, prompt, model=None):
        data = {"prompt": prompt}
        if model:
            data["model"] = model
        return self.client._request("POST", "llm", json=data)

    def models(self):
        # Placeholder based on standard AI APIs
        return self.client._request("GET", "llm/models")

    def swarm(self):
        # Placeholder based on the request
        return self.client._request("GET", "llm/swarm")
