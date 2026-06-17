"""
Wallet signing for sensor reports.
Uses simple HMAC-SHA256 signing with the private key.
"""
import hmac
import hashlib
import base64


class WalletSigner:
    """Signs sensor reports using HMAC-SHA256."""
    
    def __init__(self, private_key: str):
        self.private_key = private_key.encode('utf-8')
        # Derive wallet address from key (first 8 bytes of hash, base58-like)
        self.wallet_address = self._derive_address()
    
    def _derive_address(self) -> str:
        """Derive a wallet address from the private key."""
        h = hashlib.sha256(self.private_key).digest()
        return "WATT_" + base64.b64encode(h[:8]).decode('utf-8').replace('/', '_').replace('+', '-')
    
    def sign(self, payload: str) -> str:
        """Sign a payload string and return base64 signature."""
        sig = hmac.new(
            self.private_key,
            payload.encode('utf-8'),
            hashlib.sha256
        ).digest()
        return base64.b64encode(sig).decode('utf-8')
