import requests

BASE_URL = "https://wattcoin-production-81a7.up.railway.app"

def get_reputation():
    """Fetch node reputation data."""
    response = requests.get(f"{BASE_URL}/reputation")
    response.raise_for_status()
    return response.json()

if __name__ == "__main__":
    reputation = get_reputation()
    print(reputation)
