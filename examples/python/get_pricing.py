import requests

BASE_URL = "https://wattcoin-production-81a7.up.railway.app"

def get_pricing():
    """Fetch current energy pricing information."""
    response = requests.get(f"{BASE_URL}/pricing")
    response.raise_for_status()
    return response.json()

if __name__ == "__main__":
    pricing = get_pricing()
    print(pricing)
