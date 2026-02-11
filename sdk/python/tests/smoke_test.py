import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../src')))

from wattcoin import WattClient
from wattcoin.exceptions import WattCoinError

def test_api_smoke():
    client = WattClient()
    print("Testing WattCoin API Smoke Tests...")
    
    # 1. Stats
    try:
        stats = client.stats()
        print(f"✅ Stats: {stats}")
    except Exception as e:
        print(f"❌ Stats failed: {e}")

    # 2. Pricing
    try:
        pricing = client.pricing()
        print(f"✅ Pricing: {pricing}")
    except Exception as e:
        print(f"❌ Pricing failed: {e}")

    # 3. Tasks List
    try:
        tasks = client.tasks.list()
        print(f"✅ Tasks List: Found {len(tasks)} tasks")
    except Exception as e:
        print(f"❌ Tasks List failed: {e}")

    # 4. Reputation
    try:
        repro = client.reputation.leaderboard()
        print(f"✅ Reputation: {repro}")
    except Exception as e:
        print(f"❌ Reputation failed: {e}")

if __name__ == "__main__":
    test_api_smoke()
