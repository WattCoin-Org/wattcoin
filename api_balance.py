"""
WattCoin Balance API - Check WATT token balance
GET /api/v1/balance/<wallet> - Get balance for wallet
"""

import requests
from flask import Blueprint, jsonify

balance_bp = Blueprint('balance', __name__)

WATT_MINT = "Gpmbh4PoQnL1kNgpMYDED3iv4fczcr7d3qNBLf8rpump"
SOLANA_RPC = "https://solana.publicnode.com"
WATT_DECIMALS = 6

@balance_bp.route('/api/v1/balance/<wallet>', methods=['GET'])
def get_balance(wallet):
    """Get WATT balance for a wallet address."""
    try:
        # Get token accounts for wallet
        resp = requests.post(SOLANA_RPC, json={
            "jsonrpc": "2.0",
            "id": 1,
            "method": "getTokenAccountsByOwner",
            "params": [
                wallet,
                {"mint": WATT_MINT},
                {"encoding": "jsonParsed"}
            ]
        }, timeout=15)
        
        data = resp.json()
        accounts = data.get("result", {}).get("value", [])
        
        if not accounts:
            return jsonify({"balance": 0.0, "success": True})
        
        # Sum balances from all token accounts
        total = 0.0
        for acc in accounts:
            info = acc.get("account", {}).get("data", {}).get("parsed", {}).get("info", {})
            amount = info.get("tokenAmount", {}).get("uiAmount", 0)
            total += amount or 0
        
        return jsonify({"balance": total, "success": True})
        
    except Exception as e:
        return jsonify({"error": str(e), "success": False}), 500