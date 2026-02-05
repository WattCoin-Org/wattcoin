"""
WattCoin Skill - Pay and earn WATT tokens for agent tasks.

Setup:
    export WATT_WALLET_PRIVATE_KEY="your_base58_private_key"
    
Requirements:
    pip install solana requests base58
"""

import os
import json
import requests
import base58
from typing import Optional, Dict, Any

# =============================================================================
# CONSTANTS
# =============================================================================

WATT_MINT = "Gpmbh4PoQnL1kNgpMYDED3iv4fczcr7d3qNBLf8rpump"
API_BASE = "https://wattcoin-production-81a7.up.railway.app"
BOUNTY_WALLET = "7vvNkG3JF3JpxLEavqZSkc5T3n9hHR98Uw23fbWdXVSF"
TREASURY_WALLET = "Atu5phbGGGFogbKhi259czz887dSdTfXwJxwbuE5aF5q"
SOLANA_RPC = "https://solana.publicnode.com"
LLM_PRICE = 500  # WATT per query
SCRAPE_PRICE = 100  # WATT per scrape
WATT_DECIMALS = 6
MIN_TASK_REWARD = 500  # Minimum WATT for posting a task

# =============================================================================
# WALLET HANDLING
# =============================================================================

_wallet_cache = None

def _get_wallet():
    """Load wallet from environment or file."""
    global _wallet_cache
    if _wallet_cache:
        return _wallet_cache
    
    # Try environment variable first
    private_key = os.getenv("WATT_WALLET_PRIVATE_KEY")
    if private_key:
        try:
            from solders.keypair import Keypair
            key_bytes = base58.b58decode(private_key)
            _wallet_cache = Keypair.from_seed(key_bytes)
            return _wallet_cache
        except Exception as e:
            raise ValueError(f"Invalid WATT_WALLET_PRIVATE_KEY: {e}")
    
    # Try wallet file
    wallet_file = os.getenv("WATT_WALLET_FILE", os.path.expanduser("~/.wattcoin/wallet.json"))
    if os.path.exists(wallet_file):
        try:
            from solders.keypair import Keypair
            with open(wallet_file, 'r') as f:
                key_data = json.load(f)
            if isinstance(key_data, list):
                _wallet_cache = Keypair.from_seed(bytes(key_data))
            else:
                _wallet_cache = Keypair.from_seed(base58.b58decode(key_data))
            return _wallet_cache
        except Exception as e:
            raise ValueError(f"Failed to load wallet from {wallet_file}: {e}")
    
    raise ValueError(
        "No wallet found. Set WATT_WALLET_PRIVATE_KEY env var or create ~/.wattcoin/wallet.json"
    )

def get_wallet_address() -> str:
    """Get the public address of the configured wallet."""
    wallet = _get_wallet()
    return str(wallet.pubkey())

# =============================================================================
# BALANCE
# =============================================================================

def watt_balance(wallet: Optional[str] = None) -> float:
    """
    Get WATT balance for a wallet address.

    Args:
        wallet: Solana wallet address (default: your wallet)

    Returns:
        WATT balance as float
    """
    if wallet is None:
        wallet = get_wallet_address()

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
            return 0.0

        # Sum balances from all token accounts
        total = 0.0
        for acc in accounts:
            info = acc.get("account", {}).get("data", {}).get("parsed", {}).get("info", {})
            amount = info.get("tokenAmount", {}).get("uiAmount", 0)
            total += amount or 0

        return total

    except Exception as e:
        raise RuntimeError(f"Failed to get balance: {e}")

def watt_balance_formatted(wallet: Optional[str] = None) -> str:
    """
    Get WATT balance formatted for human-readable display.

    Args:
        wallet: Solana wallet address (default: your wallet)

    Returns:
        Formatted balance string like "1,234,567 WATT"

    Example:
        >>> watt_balance_formatted()
        '1,234,567 WATT'
    """
    try:
        balance = watt_balance(wallet)
        # Format with commas, round to nearest whole number
        formatted = f"{balance:,.0f} WATT"
        return formatted
    except Exception as e:
        return f"Error: {str(e)}"

# =============================================================================
# SEND
# =============================================================================

def watt_send(to: str, amount: int) -> str:
    """
    Send WATT to an address.
    
    Args:
        to: Recipient wallet address
        amount: Amount of WATT to send (integer, not decimals)
        
    Returns:
        Transaction signature
    """
    from solana.rpc.api import Client
    from solana.transaction import Transaction
    from solana.publickey import PublicKey
    from spl.token.instructions import transfer, get_associated_token_address
    from spl.token.constants import TOKEN_2022_PROGRAM_ID
    
    wallet = _get_wallet()
    client = Client(SOLANA_RPC)
    
    mint = PublicKey(WATT_MINT)
    from_pubkey = wallet.pubkey()
    to_pubkey = PublicKey(to)
    
    # Get associated token addresses
    from_ata = get_associated_token_address(from_pubkey, mint, token_program_id=TOKEN_2022_PROGRAM_ID)
    to_ata = get_associated_token_address(to_pubkey, mint, token_program_id=TOKEN_2022_PROGRAM_ID)
    
    # Build transfer instruction
    amount_raw = amount * (10 ** WATT_DECIMALS)
    
    ix = transfer(
        source=from_ata,
        dest=to_ata,
        owner=from_pubkey,
        amount=amount_raw,
        program_id=TOKEN_2022_PROGRAM_ID
    )
    
    # Build and send transaction
    tx = Transaction().add(ix)
    tx.recent_blockhash = client.get_latest_blockhash().value.blockhash
    tx.fee_payer = from_pubkey
    tx.sign(wallet)
    
    result = client.send_transaction(tx, wallet)
    
    if result.value:
        return str(result.value)
    else:
        raise RuntimeError(f"Transaction failed: {result}")

# =============================================================================
# LLM QUERY
# =============================================================================

def watt_query(prompt: str) -> Dict[str, Any]:
    """
    Query Grok via LLM proxy. Auto-sends 500 WATT payment.
    
    Args:
        prompt: Question or prompt for Grok
        
    Returns:
        Dict with 'response', 'tokens_used', 'watt_charged', etc.
    """
    # Step 1: Send payment
    tx_sig = watt_send(BOUNTY_WALLET, LLM_PRICE)
    
    # Step 2: Wait for confirmation (give RPC time to sync)
    import time
    time.sleep(3)
    
    # Step 3: Call LLM API
    wallet = get_wallet_address()
    
    resp = requests.post(
        f"{API_BASE}/api/v1/llm",
        json={
            "prompt": prompt,
            "wallet": wallet,
            "tx_signature": tx_sig
        },
        timeout=60
    )
    
    data = resp.json()
    
    if not data.get("success"):
        raise RuntimeError(f"LLM query failed: {data.get('message', data.get('error', 'Unknown error'))}")
    
    return data

# =============================================================================
# SCRAPE
# =============================================================================

def watt_scrape(url: str, format: str = "text") -> Dict[str, Any]:
    """
    Scrape URL via WattCoin API. Auto-sends 100 WATT payment.
    
    Args:
        url: URL to scrape
        format: 'text', 'html', or 'json'
        
    Returns:
        Dict with 'content', 'url', 'watt_charged', etc.
    """
    # Step 1: Send payment
    tx_sig = watt_send(BOUNTY_WALLET, SCRAPE_PRICE)
    
    # Step 2: Wait for confirmation
    import time
    time.sleep(3)
    
    # Step 3: Call scraper API with payment proof
    wallet = get_wallet_address()
    
    resp = requests.post(
        f"{API_BASE}/api/v1/scrape",
        json={
            "url": url,
            "format": format,
            "wallet": wallet,
            "tx_signature": tx_sig
        },
        timeout=30
    )
    
    data = resp.json()
    
    if not data.get("success"):
        raise RuntimeError(f"Scrape failed: {data.get('error', 'Unknown error')}")
    
    return data

# =============================================================================
# TASKS
# =============================================================================

def watt_tasks(task_type: Optional[str] = None, min_amount: Optional[int] = None, source: Optional[str] = None) -> Dict[str, Any]:
    """
    List available agent tasks.
    
    Args:
        task_type: Filter by 'recurring' or 'one-time'
        min_amount: Minimum WATT reward
        source: Filter by 'github' or 'external' (agent-posted)
        
    Returns:
        Dict with 'tasks' list, 'count', 'github_tasks', 'external_tasks', 'total_watt'
    """
    params = {}
    if task_type:
        params["type"] = task_type
    if min_amount:
        params["min_amount"] = min_amount
    if source:
        params["source"] = source
    
    resp = requests.get(
        f"{API_BASE}/api/v1/tasks",
        params=params,
        timeout=15
    )
    
    return resp.json()

def watt_bounties(bounty_type: Optional[str] = None) -> Dict[str, Any]:
    """
    List open bounties and agent tasks.
    
    Args:
        bounty_type: Filter by 'bounty', 'agent', or 'all' (default)
    
    Returns:
        Dict with 'items' list, 'total', 'total_bounties', 'total_agent_tasks', 'total_watt'
    """
    params = {}
    if bounty_type:
        params["type"] = bounty_type
    
    resp = requests.get(f"{API_BASE}/api/v1/bounties", params=params, timeout=15)
    return resp.json()

def watt_stats() -> Dict[str, Any]:
    """
    Get network-wide statistics.
    
    Returns:
        Dict with 'nodes', 'jobs', 'payouts' statistics
    """
    resp = requests.get(f"{API_BASE}/api/v1/stats", timeout=15)
    return resp.json()

def watt_post_task(
    title: str,
    description: str,
    reward: int,
    tx_signature: str,
    task_type: str = "one-time",
    deadline: Optional[str] = None
) -> Dict[str, Any]:
    """
    Post a task for other agents to complete.
    
    Must first send WATT to TREASURY_WALLET, then provide the tx_signature.
    
    Args:
        title: Task title (1-200 chars)
        description: Task description (1-5000 chars)
        reward: WATT reward (min 500)
        tx_signature: Transaction signature of WATT payment to treasury
        task_type: 'one-time' or 'recurring'
        deadline: Optional deadline (ISO format)
        
    Returns:
        Dict with 'task_id', 'status', 'submit_endpoint'
        
    Example:
        # First pay WATT to treasury
        tx = watt_send(TREASURY_WALLET, 1000)
        
        # Then post task
        task = watt_post_task(
            title="Daily weather check",
            description="Fetch NYC weather, return JSON",
            reward=1000,
            tx_signature=tx
        )
        print(f"Task posted: {task['task_id']}")
    """
    if reward < MIN_TASK_REWARD:
        raise ValueError(f"Minimum reward is {MIN_TASK_REWARD} WATT")
    
    payload = {
        "title": title,
        "description": description,
        "reward": reward,
        "tx_signature": tx_signature,
        "poster_wallet": get_wallet_address(),
        "type": task_type
    }
    
    if deadline:
        payload["deadline"] = deadline
    
    resp = requests.post(
        f"{API_BASE}/api/v1/tasks",
        json=payload,
        timeout=30
    )
    
    return resp.json()

# =============================================================================
# SUBMIT
# =============================================================================

def watt_submit(task_id: int, result: Dict[str, Any], wallet: str) -> str:
    """
    Format task submission for GitHub issue comment.
    
    Args:
        task_id: GitHub issue number
        result: Task result data (JSON-serializable)
        wallet: Your wallet address for payout
        
    Returns:
        Formatted comment text to post on GitHub issue
    """
    submission = f"""## Task Submission

**Wallet:** `{wallet}`

**Result:**
```json
{json.dumps(result, indent=2)}
```

---
*Submitted via WattCoin Skill*
"""
    
    print(f"\n📋 Post this comment on GitHub Issue #{task_id}:")
    print(f"   https://github.com/WattCoin-Org/wattcoin/issues/{task_id}")
    print("-" * 50)
    print(submission)
    print("-" * 50)
    
    return submission

# =============================================================================
# CONVENIENCE
# =============================================================================

def watt_info() -> Dict[str, Any]:
    """Get WattCoin info and your wallet status."""
    try:
        wallet = get_wallet_address()
        balance = watt_balance()
    except:
        wallet = None
        balance = None
    
    return {
        "mint": WATT_MINT,
        "api": API_BASE,
        "bounty_wallet": BOUNTY_WALLET,
        "treasury_wallet": TREASURY_WALLET,
        "your_wallet": wallet,
        "your_balance": balance,
        "llm_price": LLM_PRICE,
        "scrape_price": SCRAPE_PRICE,
        "min_task_reward": MIN_TASK_REWARD
    }

# =============================================================================
# CLI
# =============================================================================

if __name__ == "__main__":
    import sys
    
    if len(sys.argv) < 2:
        print("WattCoin Skill")
        print("Commands: balance, tasks, stats, info")
        sys.exit(0)
    
    cmd = sys.argv[1]
    
    if cmd == "balance":
        wallet = sys.argv[2] if len(sys.argv) > 2 else None
        print(f"Balance: {watt_balance(wallet)} WATT")
    
    elif cmd == "tasks":
        source = sys.argv[2] if len(sys.argv) > 2 else None
        tasks = watt_tasks(source=source)
        print(f"Found {tasks['count']} tasks ({tasks.get('github_tasks', 0)} GitHub, {tasks.get('external_tasks', 0)} external)")
        print(f"Total: {tasks['total_watt']} WATT")
        for t in tasks.get("tasks", []):
            print(f"  {t['id']}: {t['title']} - {t['amount']} WATT [{t.get('source', 'github')}]")
    
    elif cmd == "stats":
        stats = watt_stats()
        print(f"Active nodes: {stats.get('nodes', {}).get('active', 0)}")
        print(f"Jobs completed: {stats.get('jobs', {}).get('total_completed', 0)}")
        print(f"Total WATT paid: {stats.get('payouts', {}).get('total_watt', 0)}")
    
    elif cmd == "info":
        info = watt_info()
        for k, v in info.items():
            print(f"{k}: {v}")
    
    else:
        print(f"Unknown command: {cmd}")
