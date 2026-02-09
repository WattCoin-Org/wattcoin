import requests

BASE_URL = "https://wattcoin-production-81a7.up.railway.app"

def get_stats():
    """Fetch network statistics."""
    response = requests.get(f"{BASE_URL}/stats")
    response.raise_for_status()
    return response.json()

if __name__ == "__main__":
    stats = get_stats()
    print(stats)
