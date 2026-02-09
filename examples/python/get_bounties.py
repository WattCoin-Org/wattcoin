import requests

BASE_URL = "https://wattcoin-production-81a7.up.railway.app"

def get_bounties():
    """Fetch active bounties."""
    response = requests.get(f"{BASE_URL}/bounties")
    response.raise_for_status()
    return response.json()

if __name__ == "__main__":
    bounties = get_bounties()
    print(bounties)
