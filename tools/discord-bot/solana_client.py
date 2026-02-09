from solana.rpc.async_api import AsyncClient
from solders.pubkey import Pubkey
from config import SOLANA_RPC_URL, WATT_MINT_ADDRESS

class SolanaClient:
    def __init__(self):
        self.rpc_url = SOLANA_RPC_URL
        self.mint_address = Pubkey.from_string(WATT_MINT_ADDRESS)

    async def get_watt_balance(self, wallet_address: str):
        async with AsyncClient(self.rpc_url) as client:
            try:
                owner_pubkey = Pubkey.from_string(wallet_address)
                opts = {"mint": self.mint_address}
                
                # Get token accounts by owner
                response = await client.get_token_accounts_by_owner(owner_pubkey, opts)
                
                if not response.value:
                    return 0.0

                total_balance = 0.0
                for account in response.value:
                    balance_resp = await client.get_token_account_balance(account.pubkey)
                    if balance_resp.value:
                        total_balance += float(balance_resp.value.ui_amount)
                
                return total_balance
            except Exception as e:
                print(f"Error fetching Solana balance: {e}")
                return None
