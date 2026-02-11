from wattcoin import WattClient

client = WattClient()

# 1. Test Stats
stats = client.stats()
print(f"Stats OK: {stats.get('success')}")

# 2. Test Tasks List
tasks = client.tasks.list()
print(f"Tasks List OK: Found {len(tasks)} items")

# 3. Test Leaderboard
repro = client.reputation.leaderboard()
print(f"Reputation OK: Found {len(repro.get('contributors', []))} contributors")

# 4. Test Scraper (costs 100 WATT, so this should fail with APIError unless we have a token/payment)
try:
    client.scrape("https://example.com")
except Exception as e:
    print(f"Scraper correctly failed/handled: {e}")
