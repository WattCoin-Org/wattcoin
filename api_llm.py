"""
WattCoin LLM Proxy - Pay WATT for AI queries
POST /api/v1/llm - Submit prompt with payment proof

v1.0: Grok-only, 500 WATT per query
"""

import os
import json
import time
import requests
from datetime import datetime, timedelta
from collections import defaultdict
from flask import Blueprint, jsonify, request
from openai import OpenAI

llm_bp = Blueprint('llm', __name__)

# =============================================================================
# CONFIG
# =============================================================================

GROK_API_KEY = os.getenv("GROK_API_KEY", "")
BOUNTY_WALLET = "7vvNkG3JF3JpxLEavqZSkc5T3n9hHR98Uw23fbWdXVSF"
WATT_TOKEN_MINT = "Gpmbh4PoQnL1kNgpMYDED3iv4fczcr7d3qNBLf8rpump"
SOLANA_RPC_URL = os.getenv("SOLANA_RPC_URL", "https://api.mainnet-beta.solana.com")

# Pricing
WATT_PRICE_GROK = 500
WATT_DECIMALS = 6
BURN_RATE = 0.0005  # 0.05% burn logged

# Limits
TX_MAX_AGE_SECONDS = 600  # 10 minutes
MAX_PROMPT_LENGTH = 4000
RATE_LIMIT_PER_WALLET = 20  # queries per day
RATE_LIMIT_GLOBAL = 500  # queries per day

# Storage paths
USED_SIGNATURES_FILE = "/app/data/used_signatures.json"
LLM_USAGE_FILE = "/app/data/llm_usage.json"

# In-memory rate limiting
_wallet_queries_today = defaultdict(int)
_global_queries_today = 0
_rate_limit_reset = time.time()

# =============================================================================
# STORAGE
# =============================================================================

def load_used_signatures():
    """Load used tx signatures from JSON file."""
    try:
        with open(USED_SIGNATURES_FILE, 'r') as f:
            return set(json.load(f).get("signatures", []))
    except (FileNotFoundError, json.JSONDecodeError):
        return set()

def save_used_signature(sig):
    """Add signature to used list."""
    try:
        sigs = load_used_signatures()
        sigs.add(sig)
        os.makedirs(os.path.dirname(USED_SIGNATURES_FILE), exist_ok=True)
        with open(USED_SIGNATURES_FILE, 'w') as f:
            json.dump({"signatures": list(sigs)}, f)
    except Exception as e:
        print(f"Error saving signature: {e}")

def log_usage(wallet, tx_sig, model, watt_paid, tokens_used, prompt_preview):
    """Log query for analytics."""
    try:
        usage = {"queries": []}
        try:
            with open(LLM_USAGE_FILE, 'r') as f:
                usage = json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            pass
        
        usage["queries"].append({
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "wallet": wallet,
            "tx_signature": tx_sig,
            "model": model,
            "watt_paid": watt_paid,
            "watt_burned": round(watt_paid * BURN_RATE, 2),
            "tokens_used": tokens_used,
            "prompt_preview": prompt_preview[:50] + "..." if len(prompt_preview) > 50 else prompt_preview
        })
        
        os.makedirs(os.path.dirname(LLM_USAGE_FILE), exist_ok=True)
        with open(LLM_USAGE_FILE, 'w') as f:
            json.dump(usage, f, indent=2)
    except Exception as e:
        print(f"Error logging usage: {e}")

# =============================================================================
# RATE LIMITING
# =============================================================================

def check_rate_limit(wallet):
    """Check if wallet is within rate limits. Returns (allowed, error_code)."""
    global _wallet_queries_today, _global_queries_today, _rate_limit_reset
    
    # Reset counters daily
    now = time.time()
    if now - _rate_limit_reset > 86400:  # 24 hours
        _wallet_queries_today.clear()
        _global_queries_today = 0
        _rate_limit_reset = now
    
    # Check global limit
    if _global_queries_today >= RATE_LIMIT_GLOBAL:
        return False, "global_rate_limited"
    
    # Check per-wallet limit
    if _wallet_queries_today[wallet] >= RATE_LIMIT_PER_WALLET:
        return False, "wallet_rate_limited"
    
    return True, None

def increment_rate_limit(wallet):
    """Increment rate limit counters."""
    global _global_queries_today
    _wallet_queries_today[wallet] += 1
    _global_queries_today += 1

# =============================================================================
# SOLANA VERIFICATION (HTTP RPC)
# =============================================================================

def get_transaction(tx_signature):
    """Fetch transaction from Solana RPC."""
    try:
        resp = requests.post(SOLANA_RPC_URL, json={
            "jsonrpc": "2.0",
            "id": 1,
            "method": "getTransaction",
            "params": [
                tx_signature,
                {
                    "encoding": "jsonParsed",
                    "maxSupportedTransactionVersion": 0
                }
            ]
        }, timeout=15)
        
        if resp.status_code != 200:
            return None, "rpc_error"
        
        data = resp.json()
        if "error" in data:
            return None, "rpc_error"
        
        return data.get("result"), None
    except Exception as e:
        print(f"Solana RPC error: {e}")
        return None, "rpc_error"

def verify_watt_payment(tx_signature, expected_wallet, expected_amount):
    """
    Verify WATT payment on Solana.
    Uses pre/post token balance changes for reliable verification.
    Returns (success, error_code, error_message)
    """
    # Check if already used (replay protection)
    used_sigs = load_used_signatures()
    if tx_signature in used_sigs:
        return False, "tx_already_used", "Transaction already used for a query"
    
    # Fetch transaction
    tx, err = get_transaction(tx_signature)
    if err:
        return False, "tx_not_found", "Transaction not found on chain"
    
    if not tx:
        return False, "tx_not_found", "Transaction not found on chain"
    
    # Check for errors in tx
    meta = tx.get("meta", {})
    if meta.get("err"):
        return False, "tx_failed", "Transaction failed on chain"
    
    # Check block time (must be recent)
    block_time = tx.get("blockTime")
    if not block_time:
        return False, "tx_not_confirmed", "Transaction not yet confirmed"
    
    tx_age = time.time() - block_time
    if tx_age > TX_MAX_AGE_SECONDS:
        return False, "tx_too_old", f"Transaction older than {TX_MAX_AGE_SECONDS // 60} minutes"
    
    if tx_age < 0:
        return False, "tx_invalid_time", "Transaction has invalid timestamp"
    
    # ==========================================================================
    # VERIFY USING PRE/POST TOKEN BALANCES
    # This is more reliable than parsing instructions for various token programs
    # ==========================================================================
    
    pre_balances = meta.get("preTokenBalances", [])
    post_balances = meta.get("postTokenBalances", [])
    
    # Find bounty wallet balance changes for WATT token
    sender_change = 0
    recipient_change = 0
    sender_found = False
    recipient_found = False
    
    # Build lookup of pre-balances by account index
    pre_by_index = {}
    for bal in pre_balances:
        if bal.get("mint") == WATT_TOKEN_MINT:
            idx = bal.get("accountIndex")
            owner = bal.get("owner")
            amount = float(bal.get("uiTokenAmount", {}).get("uiAmount", 0))
            pre_by_index[idx] = {"owner": owner, "amount": amount}
    
    # Check post-balances and calculate changes
    for bal in post_balances:
        if bal.get("mint") != WATT_TOKEN_MINT:
            continue
        
        idx = bal.get("accountIndex")
        owner = bal.get("owner")
        post_amount = float(bal.get("uiTokenAmount", {}).get("uiAmount", 0))
        pre_amount = pre_by_index.get(idx, {}).get("amount", 0)
        change = post_amount - pre_amount
        
        # Check if this is the bounty wallet (recipient)
        if owner == BOUNTY_WALLET:
            recipient_change = change
            recipient_found = True
        
        # Check if this is the expected sender
        if owner == expected_wallet:
            sender_change = change
            sender_found = True
    
    # Validate: recipient must have received the expected amount
    if not recipient_found:
        return False, "wrong_recipient", "Payment not sent to bounty wallet"
    
    if recipient_change < expected_amount - 0.01:  # Allow tiny rounding
        return False, "invalid_amount", f"Bounty wallet received {recipient_change} WATT, expected {expected_amount}"
    
    # Validate: sender must have sent (negative change)
    if not sender_found:
        return False, "wallet_mismatch", "Sender wallet not found in transaction"
    
    if sender_change > -expected_amount + 0.01:  # Should be negative (sent out)
        return False, "wallet_mismatch", f"Expected wallet didn't send {expected_amount} WATT"
    
    # All checks passed - mark signature as used
    save_used_signature(tx_signature)
    
    return True, None, None

# =============================================================================
# GROK API
# =============================================================================

def call_grok(prompt):
    """Call Grok API and return response."""
    if not GROK_API_KEY:
        return None, 0, "Grok API key not configured"
    
    try:
        client = OpenAI(api_key=GROK_API_KEY, base_url="https://api.x.ai/v1")
        
        response = client.chat.completions.create(
            model="grok-2-latest",
            messages=[
                {"role": "user", "content": prompt}
            ],
            max_tokens=2000
        )
        
        content = response.choices[0].message.content
        tokens = response.usage.total_tokens if response.usage else 0
        
        return content, tokens, None
    except Exception as e:
        print(f"Grok API error: {e}")
        return None, 0, f"Model error: {str(e)}"

# =============================================================================
# ENDPOINT
# =============================================================================

@llm_bp.route('/api/v1/llm', methods=['POST'])
def llm_query():
    """
    LLM proxy endpoint. Pay WATT, get AI response.
    
    Request:
        {
            "prompt": "Your question here",
            "wallet": "YourSolanaWallet",
            "tx_signature": "TransactionSignature"
        }
    
    Response:
        {
            "success": true,
            "response": "AI response here",
            "model": "grok",
            "tokens_used": 42,
            "watt_charged": 500,
            "watt_burned": 0.25,
            "tx_verified": true
        }
    """
    data = request.get_json(silent=True) or {}
    
    # Extract fields
    prompt = (data.get("prompt") or "").strip()
    wallet = (data.get("wallet") or "").strip()
    tx_signature = (data.get("tx_signature") or "").strip()
    
    # Validate required fields
    if not prompt:
        return jsonify({
            "success": False,
            "error": "missing_prompt",
            "message": "Prompt is required"
        }), 400
    
    if not wallet:
        return jsonify({
            "success": False,
            "error": "missing_wallet",
            "message": "Wallet address is required"
        }), 400
    
    if not tx_signature:
        return jsonify({
            "success": False,
            "error": "missing_tx_signature",
            "message": "Transaction signature is required"
        }), 400
    
    # Validate prompt length
    if len(prompt) > MAX_PROMPT_LENGTH:
        return jsonify({
            "success": False,
            "error": "prompt_too_long",
            "message": f"Prompt exceeds {MAX_PROMPT_LENGTH} characters"
        }), 400
    
    # Check rate limits
    allowed, rate_error = check_rate_limit(wallet)
    if not allowed:
        return jsonify({
            "success": False,
            "error": rate_error,
            "message": "Rate limit exceeded. Try again tomorrow."
        }), 429
    
    # Verify payment
    verified, error_code, error_message = verify_watt_payment(
        tx_signature, wallet, WATT_PRICE_GROK
    )
    
    if not verified:
        return jsonify({
            "success": False,
            "error": error_code,
            "message": error_message
        }), 402  # Payment Required
    
    # Call Grok
    response_text, tokens_used, model_error = call_grok(prompt)
    
    if model_error:
        return jsonify({
            "success": False,
            "error": "model_unavailable",
            "message": model_error
        }), 503
    
    # Increment rate limit
    increment_rate_limit(wallet)
    
    # Log usage
    watt_burned = round(WATT_PRICE_GROK * BURN_RATE, 2)
    log_usage(wallet, tx_signature, "grok", WATT_PRICE_GROK, tokens_used, prompt)
    
    return jsonify({
        "success": True,
        "response": response_text,
        "model": "grok",
        "tokens_used": tokens_used,
        "watt_charged": WATT_PRICE_GROK,
        "watt_burned": watt_burned,
        "tx_verified": True
    })

@llm_bp.route('/api/v1/llm/pricing', methods=['GET'])
def llm_pricing():
    """Return current pricing info."""
    return jsonify({
        "models": {
            "grok": {
                "price_watt": WATT_PRICE_GROK,
                "available": bool(GROK_API_KEY)
            }
        },
        "payment_wallet": BOUNTY_WALLET,
        "watt_token_mint": WATT_TOKEN_MINT,
        "max_prompt_length": MAX_PROMPT_LENGTH,
        "rate_limits": {
            "per_wallet_per_day": RATE_LIMIT_PER_WALLET,
            "global_per_day": RATE_LIMIT_GLOBAL
        },
        "burn_rate": BURN_RATE
    })
