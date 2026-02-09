import aiohttp
import logging
from config import WATTCOIN_API_URL, WATT_MINT_ADDRESS

logger = logging.getLogger('wattcoin-bot')

class WattCoinAPI:
    def __init__(self):
        self.base_url = WATTCOIN_API_URL

    async def _make_request(self, endpoint):
        url = f"{self.base_url}/{endpoint}"
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, timeout=10) as resp:
                    if resp.status != 200:
                        logger.error(f"API request to {url} failed with status {resp.status}")
                        return None
                    try:
                        return await resp.json()
                    except Exception as e:
                        logger.error(f"Failed to parse JSON response from {url}: {e}")
                        return None
        except Exception as e:
            logger.error(f"Request to {url} failed: {e}")
            return None

    async def get_bounties(self):
        return await self._make_request("bounties")

    async def get_tasks(self):
        return await self._make_request("tasks")

    async def get_stats(self):
        return await self._make_request("stats")

    async def get_leaderboard(self):
        return await self._make_request("leaderboard")

class DexScreenerAPI:
    async def get_price(self):
        url = f"https://api.dexscreener.com/latest/dex/tokens/{WATT_MINT_ADDRESS}"
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, timeout=10) as resp:
                    if resp.status != 200:
                        logger.error(f"DexScreener request failed with status {resp.status}")
                        return None
                    try:
                        data = await resp.json()
                        if data and data.get("pairs"):
                            return data["pairs"][0]
                        return None
                    except Exception as e:
                        logger.error(f"Failed to parse DexScreener JSON: {e}")
                        return None
        except Exception as e:
            logger.error(f"DexScreener request failed: {e}")
            return None
