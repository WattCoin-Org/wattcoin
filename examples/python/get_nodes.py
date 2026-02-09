import requests

BASE_URL = "https://wattcoin-production-81a7.up.railway.app"

def get_nodes():
    """Fetch registered network nodes."""
    response = requests.get(f"{BASE_URL}/nodes")
    response.raise_for_status()
    return response.json()

if __name__ == "__main__":
    nodes = get_nodes()
    print(nodes)
