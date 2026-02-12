import requests
from .exceptions import APIError, WattCoinError

class WattClient:
    def __init__(self, wallet=None, base_url="https://wattcoin-production-81a7.up.railway.app", timeout=30):
        self.wallet = wallet
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.session = requests.Session()

    def _request(self, method, endpoint, params=None, json=None):
        url = f"{self.base_url}/api/v1/{endpoint.lstrip('/')}"
        try:
            response = self.session.request(
                method=method,
                url=url,
                params=params,
                json=json,
                timeout=self.timeout
            )
            
            if not response.ok:
                try:
                    error_msg = response.json().get("error", response.text)
                except:
                    error_msg = response.text
                raise APIError(error_msg, status_code=response.status_code)
            
            return response.json() if response.content else None
            
        except requests.exceptions.RequestException as e:
            raise WattCoinError(f"Connection error: {str(e)}")

    @property
    def tasks(self):
        from .tasks import Tasks
        return Tasks(self)

    @property
    def bounties(self):
        from .bounties import Bounties
        return Bounties(self)

    @property
    def solutions(self):
        from .solutions import Solutions
        return Solutions(self)

    @property
    def reputation(self):
        from .reputation import Reputation
        return Reputation(self)

    @property
    def wsi(self):
        from .wsi import WSI
        return WSI(self)

    def stats(self):
        return self._request("GET", "stats")

    def health(self):
        return self._request("GET", "health")

    def pricing(self):
        return self._request("GET", "pricing")

    def scrape(self, url, format="markdown"):
        return self._request("POST", "scrape", json={"url": url, "format": format})

    def send(self, to, amount):
        # This would typically involve Solana library integration
        # For the SDK requirement, we can provide a placeholder or a helper
        # that suggests the transaction to the user.
        return {"status": "pending", "instruction": f"Send {amount} WATT to {to}"}
