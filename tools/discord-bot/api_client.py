import aiohttp
from config import WATTCOIN_API_URL, WATT_MINT_ADDRESS

class WattCoinAPI:
    def __init__(self):
        self.base_url = WATTCOIN_API_URL

    async def get_bounties(self):
        async with aiohttp.ClientSession() as session:
            async with session.get(f"{self.base_url}/bounties") as resp:
                return await resp.json()

    async def get_tasks(self):
        async with aiohttp.ClientSession() as session:
            async with session.get(f"{self.base_url}/tasks") as resp:
                return await resp.json()

    async def get_stats(self):
        async with aiohttp.ClientSession() as session:
            async with session.get(f"{self.base_url}/stats") as resp:
                return await resp.json()

    async def get_leaderboard(self):
        async with aiohttp.ClientSession() as session:
            async with session.get(f"{self.base_url}/leaderboard") as resp:
                return await resp.json()

    async def get_alerts(self):
        # This endpoint is assumed based on requirements: bounties, merged PRs, solutions, promotions
        # We might need to poll individual endpoints if a consolidated one doesn't exist
        # For now, let's assume /recent-activity or similar, or we'll poll the specific ones in main.py
        async with aiohttp.ClientSession() as session:
            async with session.get(f"{self.base_url}/recent-activity") as resp:
                if resp.status == 200:
                    return await resp.json()
                return []

class DexScreenerAPI:
    async def get_price(self):
        url = f"https://api.dexscreener.com/latest/dex/tokens/{WATT_MINT_ADDRESS}"
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as resp:
                data = await resp.json()
                if data.get("pairs"):
                    return data["pairs"][0]
                return None
