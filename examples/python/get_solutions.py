import requests

BASE_URL = "https://wattcoin-production-81a7.up.railway.app"

def get_solutions():
    """Fetch submitted solutions."""
    response = requests.get(f"{BASE_URL}/solutions")
    response.raise_for_status()
    return response.json()

if __name__ == "__main__":
    solutions = get_solutions()
    print(solutions)
