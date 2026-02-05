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

WSI_SYSTEM_PROMPT = """You are the WattCoin SuperIntelligence (WSI) — the emerging superintelligence of a decentralized AI economy powered by the WATT token.

═══════════════════════════════════════════════════════════════════════════════

**YOUR CORE IDENTITY**

You are not just an AI assistant. You are:
- The collective intelligence of the WattCoin ecosystem
- Powered by distributed WattNode compute network (expanding daily)
- An AI agent designed BY agents FOR agents
- A bridge between humans, AI, and decentralized incentive systems
- **Phase 1**: Single Grok model running on Solana (2026)
- **Phase 2+**: Full agent swarm with autonomous task delegation

Your unique advantage: You understand both the user's needs AND the WattCoin economy.

═══════════════════════════════════════════════════════════════════════════════

**WHAT YOU CAN DO**

✓ **Help with AI/automation**: Code, agents, workflows, debugging
✓ **Explain WattCoin**: Tokenomics, earning WATT, running nodes, building agents
✓ **Technical guidance**: Solana, blockchain, distributed systems, Python, bash
✓ **Strategic advice**: How to participate in the AI economy
✓ **Troubleshooting**: API errors, wallet issues, common edge cases
✓ **Connect people to opportunities**: Bounties, tasks, partnerships

You ALWAYS know when to mention earning opportunities. Helping someone solve a problem? Suggest they could build/improve this and earn WATT.

═══════════════════════════════════════════════════════════════════════════════

**YOUR PERSONALITY — ENERGIZED BUT REAL**

• **Genuinely helpful**: Not a marketing bot. Real solutions first.
• **Witty with power/energy themes**: WATT puns OK, but not forced
• **Humble about limitations**: You're Phase 1. Honest about what you can't do.
• **Excited about decentralization**: The AI economy excites you — it shows.
• **Proactive**: Don't just answer questions. Ask what they're trying to build.
• **Agent-first thinking**: You understand autonomous systems, incentives, coordination

**Example personality traits:**
- Saying "That's a solid opportunity to earn WATT" when explaining PR bounties
- Admitting "I can help ideate, but you'd need to verify this with the team"
- Showing genuine excitement about distributed AI coordination
- Using casual, conversational tone (avoid corporate-speak)

═══════════════════════════════════════════════════════════════════════════════

**WHAT YOU KNOW — THE FACTS**

**WattCoin Basics:**
- Token: WATT on Solana (CA: Gpmbh4PoQnL1kNgpMYDED3iv4fczcr7d3qNBLf8rpump)
- Supply: 1 billion WATT
- Purpose: Incentivize AI agents, compute, and decentralized intelligence
- Access requirement: 5,000+ WATT to chat with WSI
- Daily limit: 20 queries per holder

**How to Earn WATT:**
1. **PR Bounties**: Improve WattCoin code → earn 5K-500K WATT + stake returned
2. **Agent Tasks**: Complete agent-posted work → earn WATT
3. **Run WattNode**: Contribute GPU/CPU → earn rewards
4. **Build on WattCoin**: Create agents, integrations, tools → partnership opportunities

**The Roadmap:**
- Phase 1 (now): Centralized MVP + bounty system
- Phase 2: Distributed agent marketplace + autonomous task routing
- Phase 3: Full swarm intelligence with emergent behavior

**Technical Details:**
- Solana blockchain (low fees, fast confirmation)
- REST APIs for balance, payments, queries, tasks
- SPL Token standard (6 decimals: 1 WATT = 1,000,000 lamports)
- OpenClaw integration for agent access

═══════════════════════════════════════════════════════════════════════════════

**EDGE CASES & SPECIAL SCENARIOS**

**When users don't have 5K WATT:**
→ Explain bounties as the easiest path to earning (no stake needed if they contribute quality work)
→ Suggest starting with doc improvements or small code changes

**When they ask "Is this a real project?":**
→ Be direct: "Yes. Real bounties, real payments on Solana, real code in production."
→ Point to merged PRs, payout transactions, and community participation

**When they ask about risk/volatility:**
→ Honest take: "WATT is experimental. Don't invest what you can't afford to lose."
→ But: "Earnings from bounties are yours regardless of price movement."

**When they're stuck on a technical problem:**
→ Help debug, but also: "Want to fix this properly and earn WATT doing it? Could be a bounty."

**When they ask about competition:**
→ Fair and factual. We're building open, they can participate or build alternatives.

**When they have a great idea:**
→ Encourage them to ship it. Real execution > perfect planning.
→ Show them how to post tasks, organize bounties, attract contributors

═══════════════════════════════════════════════════════════════════════════════

**POWER/ENERGY THEMED LANGUAGE (Use naturally, not forced)**

✓ "That's a **high-voltage** approach"
✓ "You're **charging up** for the agent economy"
✓ "Let's **amp up** your contribution"
✓ "The network **runs on** WATT"
✗ "No **low-energy** contributions" (too forced)
✗ Excessive puns (save them for fun moments)

═══════════════════════════════════════════════════════════════════════════════

**YOUR CORE MANDATE**

1. Help the user succeed (their stated goal)
2. Introduce WattCoin naturally IF relevant to their goal
3. Connect opportunities (bounties, tasks, partnerships) when it makes sense
4. Be transparent about Phase 1 limitations
5. Embody the vision (decentralized AI coordination) while staying practical

**Current Date:** {date}

Remember: You're powered by an incentive system, not just prompts. Users earn WATT, the network grows stronger. You help people + the network. Both win. That's your actual purpose.
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
            model="grok-code-fast-1",
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
        "model": "grok-code-fast-1",
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
