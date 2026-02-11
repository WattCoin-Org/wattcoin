"""WattCoin API service."""
import aiohttp
from typing import Optional, Dict, Any
from config import Config


class WattCoinAPI:
    """WattCoin API client."""
    
    def __init__(self):
        self.base_url = Config.WATTCOIN_API_URL.rstrip('/')
        self.api_key = Config.WATTCOIN_API_KEY
        self.session: Optional[aiohttp.ClientSession] = None
    
    async def _get_session(self) -> aiohttp.ClientSession:
        """Get or create aiohttp session."""
        if self.session is None or self.session.closed:
            headers = {}
            if self.api_key:
                headers['Authorization'] = f'Bearer {self.api_key}'
            self.session = aiohttp.ClientSession(
                headers=headers,
                timeout=aiohttp.ClientTimeout(total=10)
            )
        return self.session
    
    async def close(self):
        """Close the session."""
        if self.session and not self.session.closed:
            await self.session.close()
    
    async def get_balance(self, wallet_address: str) -> Dict[str, Any]:
        """Get WATT balance for a wallet."""
        session = await self._get_session()
        
        try:
            async with session.get(
                f'{self.base_url}/wallets/{wallet_address}/balance'
            ) as resp:
                if resp.status == 200:
                    return await resp.json()
                else:
                    return {'error': f'API returned {resp.status}', 'balance': 0}
        except Exception as e:
            return {'error': str(e), 'balance': 0}
    
    async def get_network_stats(self) -> Dict[str, Any]:
        """Get WattCoin network statistics."""
        session = await self._get_session()
        
        try:
            async with session.get(f'{self.base_url}/network/stats') as resp:
                if resp.status == 200:
                    return await resp.json()
                else:
                    return {'error': f'API returned {resp.status}'}
        except Exception as e:
            return {'error': str(e)}
    
    async def get_active_nodes(self) -> list:
        """Get list of active nodes."""
        session = await self._get_session()
        
        try:
            async with session.get(f'{self.base_url}/nodes/active') as resp:
                if resp.status == 200:
                    data = await resp.json()
                    return data.get('nodes', [])
                return []
        except Exception:
            return []


watt_api = WattCoinAPI()
