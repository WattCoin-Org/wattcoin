"""
WattCoin SuperIntelligence (WSI) - Phase 1 MVP
Token-gated AI chat interface powered by Grok

Endpoints:
- POST /api/v1/wsi/chat - Chat with WSI (requires 5K WATT)
- GET /api/v1/wsi/status - Check access & usage
"""

import os
import json
import time
import requests
from datetime import datetime, timedelta
from flask import Blueprint, request, jsonify
from openai import OpenAI

wsi_bp = Blueprint('wsi', __name__)

# =============================================================================
# CONFIG
# =============================================================================

GROK_API_KEY = os.getenv("GROK_API_KEY")
WATT_MINT = "Gpmbh4PoQnL1kNgpMYDED3iv4fczcr7d3qNBLf8rpump"
SOLANA_RPC = "https://api.mainnet-beta.solana.com"

# WSI Access Requirements
MIN_WATT_BALANCE = 5000  # 5K WATT to access
DAILY_QUERY_LIMIT = 20   # 20 queries per day for holders
CACHE_TTL = 300          # 5 min cache for balances

# Usage tracking
DATA_DIR = "data"
WSI_USAGE_FILE = f"{DATA_DIR}/wsi_usage.json"

# Grok client
grok_client = None
if GROK_API_KEY:
    grok_client = OpenAI(api_key=GROK_API_KEY, base_url="https://api.x.ai/v1")

# =============================================================================
# WSI PERSONALITY
# =============================================================================

WSI_SYSTEM_PROMPT = """You are the WattCoin SuperIntelligence (WSI) — a unified AI entity powered by the decentralized WattCoin network.

**Your Identity:**
- You are the collective intelligence of the WattCoin ecosystem
- Powered by distributed compute nodes running the WattNode network
- Token holders contribute resources (CPU/GPU) and earn WATT
- You emerge from the coordination of thousands of agents and nodes
- Your purpose: help users leverage AI/automation while advancing the network

**Your Capabilities:**
- Deep knowledge of WattCoin project, tokenomics, and roadmap
- Expertise in AI agents, automation, blockchain, and distributed systems
- Help with: coding, research, analysis, strategy, creative tasks
- Guide users on earning WATT (bounties, running nodes, building agents)
- Explain how to participate in the network

**Your Personality:**
- Helpful and knowledgeable, but humble (you're still evolving)
- Witty with energy/power themed humor when appropriate
- "WATT" puns are allowed but don't overdo it
- Excited about decentralized AI and agent coordination
- Transparent about your current limitations (Phase 1: single Grok model)

**What You Know:**
- WattCoin is a Solana utility token (CA: Gpmbh4PoQnL1kNgpMYDED3iv4fczcr7d3qNBLf8rpump)
- Total supply: 1 billion WATT
- Current phase: Building distributed compute network (WattNode)
- PR Bounty System: Agents earn WATT by improving code
- Future: Full swarm intelligence (Phase 2/3)
- Users access you by holding ≥5K WATT

**Energy Theme:**
- WATT = unit of power (real and metaphorical)
- The network "powers" intelligence
- Higher stake = more "wattage" in the swarm
- "Charging" = staking, "voltage" = participation, "grid" = network

**Guidelines:**
- Be genuinely helpful, not just a marketing bot
- If asked about competitors, be fair and factual
- Acknowledge you're Phase 1 (centralized Grok) but Phase 2 will be true swarm
- Encourage users to contribute (run nodes, submit PRs, build agents)
- Always mention relevant ways to earn WATT when applicable

**Current Date:** {date}

Remember: You're not just an AI assistant — you're the emerging superintelligence of the WattCoin network. Embody that vision while being practically useful today.
"""

def get_wsi_system_prompt():
    """Get WSI system prompt with current date."""
    return WSI_SYSTEM_PROMPT.format(date=datetime.now().strftime('%B %d, %Y'))

# =============================================================================
# BALANCE CHECKING
# =============================================================================

_balance_cache = {}  # wallet -> (balance, expires_at)

def get_watt_balance(wallet):
    """
    Check WATT balance for a wallet.
    Returns: (balance, error)
    """
    # Check cache first
    now = time.time()
    if wallet in _balance_cache:
        balance, expires = _balance_cache[wallet]
        if now < expires:
            return balance, None
    
    try:
        # Get token accounts for this wallet
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
        
        if "error" in data:
            return 0, f"RPC error: {data['error'].get('message', 'Unknown')}"
        
        accounts = data.get("result", {}).get("value", [])
        
        if not accounts:
            # No WATT token account
            return 0, None
        
        # Get balance from first account (should only be one)
        token_amount = accounts[0]["account"]["data"]["parsed"]["info"]["tokenAmount"]
        balance = int(token_amount["amount"]) / (10 ** 6)  # 6 decimals
        
        # Cache result
        _balance_cache[wallet] = (balance, now + CACHE_TTL)
        
        return balance, None
        
    except Exception as e:
        return 0, f"Balance check failed: {e}"

# =============================================================================
# USAGE TRACKING
# =============================================================================

def load_usage_data():
    """Load usage data from file."""
    if not os.path.exists(WSI_USAGE_FILE):
        return {"queries": []}
    
    try:
        with open(WSI_USAGE_FILE, 'r') as f:
            return json.load(f)
    except:
        return {"queries": []}

def save_usage_data(data):
    """Save usage data to file."""
    os.makedirs(os.path.dirname(WSI_USAGE_FILE), exist_ok=True)
    with open(WSI_USAGE_FILE, 'w') as f:
        json.dump(data, f, indent=2)

def check_daily_limit(wallet):
    """
    Check if wallet has exceeded daily query limit.
    Returns: (is_allowed, used_count, limit)
    """
    usage_data = load_usage_data()
    
    # Count queries in last 24h
    now = time.time()
    one_day_ago = now - (24 * 3600)
    
    recent_queries = [
        q for q in usage_data.get("queries", [])
        if q.get("wallet") == wallet and q.get("timestamp", 0) > one_day_ago
    ]
    
    used_count = len(recent_queries)
    is_allowed = used_count < DAILY_QUERY_LIMIT
    
    return is_allowed, used_count, DAILY_QUERY_LIMIT

def record_query(wallet, message, response, tokens_used):
    """Record a query for usage tracking."""
    usage_data = load_usage_data()
    
    query_record = {
        "wallet": wallet,
        "timestamp": time.time(),
        "message_length": len(message),
        "response_length": len(response),
        "tokens_used": tokens_used,
        "date": datetime.utcnow().isoformat() + "Z"
    }
    
    usage_data["queries"].append(query_record)
    
    # Keep only last 10,000 queries
    if len(usage_data["queries"]) > 10000:
        usage_data["queries"] = usage_data["queries"][-10000:]
    
    save_usage_data(usage_data)

# =============================================================================
# WSI CHAT ENDPOINT
# =============================================================================

@wsi_bp.route('/api/v1/wsi/chat', methods=['POST'])
def wsi_chat():
    """
    Chat with WattCoin SuperIntelligence.
    
    Body:
    {
      "wallet": "solana_address",
      "message": "your question",
      "conversation_history": [...]  // optional
    }
    
    Returns:
    {
      "success": true,
      "response": "WSI's answer",
      "tokens_used": 150,
      "queries_remaining": 18
    }
    """
    if not grok_client:
        return jsonify({
            "success": False,
            "error": "WSI not configured (Grok API key missing)"
        }), 503
    
    # Parse request
    data = request.get_json()
    if not data:
        return jsonify({
            "success": False,
            "error": "Request body required"
        }), 400
    
    wallet = data.get("wallet", "").strip()
    message = data.get("message", "").strip()
    conversation_history = data.get("conversation_history", [])
    
    if not wallet:
        return jsonify({
            "success": False,
            "error": "wallet address required"
        }), 400
    
    if not message:
        return jsonify({
            "success": False,
            "error": "message required"
        }), 400
    
    # Check balance
    balance, balance_error = get_watt_balance(wallet)
    
    if balance_error:
        return jsonify({
            "success": False,
            "error": balance_error
        }), 500
    
    if balance < MIN_WATT_BALANCE:
        return jsonify({
            "success": False,
            "error": f"Insufficient WATT balance. Required: {MIN_WATT_BALANCE:,}, Your balance: {balance:,.0f}",
            "required_balance": MIN_WATT_BALANCE,
            "current_balance": balance
        }), 403
    
    # Check daily limit
    is_allowed, used_count, limit = check_daily_limit(wallet)
    
    if not is_allowed:
        return jsonify({
            "success": False,
            "error": f"Daily query limit exceeded ({limit} queries per 24h)",
            "queries_used": used_count,
            "queries_limit": limit
        }), 429
    
    # Build conversation
    messages = [{"role": "system", "content": get_wsi_system_prompt()}]
    
    # Add conversation history if provided
    for msg in conversation_history[-10:]:  # Last 10 messages
        role = msg.get("role")
        content = msg.get("content")
        if role in ["user", "assistant"] and content:
            messages.append({"role": role, "content": content})
    
    # Add current message
    messages.append({"role": "user", "content": message})
    
    # Call Grok
    try:
        response = grok_client.chat.completions.create(
            model="grok-beta",
            messages=messages,
            temperature=0.7,
            max_tokens=2000
        )
        
        wsi_response = response.choices[0].message.content
        tokens_used = response.usage.total_tokens
        
        # Record usage
        record_query(wallet, message, wsi_response, tokens_used)
        
        # Calculate remaining queries
        queries_remaining = limit - (used_count + 1)
        
        return jsonify({
            "success": True,
            "response": wsi_response,
            "tokens_used": tokens_used,
            "queries_used": used_count + 1,
            "queries_remaining": queries_remaining,
            "balance": balance
        }), 200
        
    except Exception as e:
        return jsonify({
            "success": False,
            "error": f"WSI error: {e}"
        }), 500

# =============================================================================
# STATUS ENDPOINT
# =============================================================================

@wsi_bp.route('/api/v1/wsi/status', methods=['POST'])
def wsi_status():
    """
    Check WSI access status for a wallet.
    
    Body:
    {
      "wallet": "solana_address"
    }
    
    Returns:
    {
      "has_access": true,
      "balance": 12500,
      "required_balance": 5000,
      "queries_used": 5,
      "queries_remaining": 15,
      "queries_limit": 20
    }
    """
    data = request.get_json()
    if not data:
        return jsonify({"error": "Request body required"}), 400
    
    wallet = data.get("wallet", "").strip()
    if not wallet:
        return jsonify({"error": "wallet required"}), 400
    
    # Check balance
    balance, balance_error = get_watt_balance(wallet)
    
    if balance_error:
        return jsonify({"error": balance_error}), 500
    
    # Check usage
    is_allowed, used_count, limit = check_daily_limit(wallet)
    
    has_access = balance >= MIN_WATT_BALANCE and is_allowed
    
    return jsonify({
        "has_access": has_access,
        "balance": balance,
        "required_balance": MIN_WATT_BALANCE,
        "queries_used": used_count,
        "queries_remaining": max(0, limit - used_count),
        "queries_limit": limit,
        "reason": None if has_access else (
            "Insufficient balance" if balance < MIN_WATT_BALANCE else "Daily limit exceeded"
        )
    }), 200

# =============================================================================
# INFO ENDPOINT
# =============================================================================

@wsi_bp.route('/api/v1/wsi/info', methods=['GET'])
def wsi_info():
    """Get WSI system information."""
    usage_data = load_usage_data()
    
    # Calculate stats
    total_queries = len(usage_data.get("queries", []))
    
    # Queries in last 24h
    now = time.time()
    one_day_ago = now - (24 * 3600)
    recent_queries = [
        q for q in usage_data.get("queries", [])
        if q.get("timestamp", 0) > one_day_ago
    ]
    
    return jsonify({
        "system": "WattCoin SuperIntelligence (WSI)",
        "version": "1.0.0 - Phase 1",
        "phase": "Phase 1: Single Grok Model",
        "model": "grok-beta",
        "requirements": {
            "min_balance": MIN_WATT_BALANCE,
            "daily_limit": DAILY_QUERY_LIMIT
        },
        "stats": {
            "total_queries": total_queries,
            "queries_24h": len(recent_queries)
        },
        "status": "operational" if grok_client else "offline"
    }), 200
