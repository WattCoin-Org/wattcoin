import requests

BASE_URL = "https://wattcoin-production-81a7.up.railway.app"

def get_tasks():
    """Fetch all available tasks."""
    response = requests.get(f"{BASE_URL}/tasks")
    response.raise_for_status()
    return response.json()

if __name__ == "__main__":
    tasks = get_tasks()
    print(tasks)
