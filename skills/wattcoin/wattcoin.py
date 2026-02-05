"""
WattCoin Skill - CORRECTLY FIXED for solders 0.18+

This version uses the CORRECT Transaction signing API for modern solders
"""

import os
import json
import requests
import base58
import struct
from typing import Optional, Dict, Any
from datetime import datetime

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
# ERROR HANDLING & LOGGING
# =============================================================================

class WattCoinError(Exception):
    """Base exception for WattCoin errors."""
    pass

class WalletError(WattCoinError):
    """Wallet configuration or operation error."""
    pass

class APIError(WattCoinError):
    """API request or response error."""
    pass

class InsufficientBalanceError(WattCoinError):
    """User has insufficient WATT balance."""
    pass

class TransactionError(WattCoinError):
    """Transaction failed (signing, sending, confirmation)."""
    pass

def _log_error(error_type: str, message: str, context: dict = None):
    """Log error with context for debugging."""
    import traceback
    error_entry = {
        "type": error_type,
        "message": message,
        "timestamp": datetime.now().isoformat(),
    }
    if context:
        error_entry["context"] = context
    error_entry["traceback"] = traceback.format_exc()
    # In production, this would go to a logging service
    return error_entry

# =============================================================================
# WALLET HANDLING
# =============================================================================

_wallet_cache = None

def _get_wallet():
    """
    Load wallet from environment or file.
    
    Tries in order:
    1. WATT_WALLET_PRIVATE_KEY environment variable
    2. config file in skill directory
    
    Raises:
        WalletError: If wallet cannot be loaded
    """
    global _wallet_cache
    if _wallet_cache:
        return _wallet_cache
    
    # Try environment variable first
    private_key = os.getenv("WATT_WALLET_PRIVATE_KEY")
    if private_key:
        try:
            from solders.keypair import Keypair
            key_bytes = base58.b58decode(private_key)
            _wallet_cache = Keypair.from_bytes(key_bytes)
            return _wallet_cache
        except Exception as e:
            error_context = {
                "source": "WATT_WALLET_PRIVATE_KEY env var",
                "error": str(e)
            }
            _log_error("WALLET_LOAD_ERROR", f"Failed to load wallet from env: {e}", error_context)
            raise WalletError(f"Failed to load wallet from WATT_WALLET_PRIVATE_KEY: {e}")
    
    # Try config file
    config_path = os.path.join(os.path.dirname(__file__), "config")
    if os.path.exists(config_path):
        try:
            from solders.keypair import Keypair
            with open(config_path) as f:
                data = json.load(f)
            key_bytes = base58.b58decode(data["private_key"])
            _wallet_cache = Keypair.from_bytes(key_bytes)
            return _wallet_cache
        except Exception as e:
            error_context = {
                "source": "config file",
                "error": str(e)
            }
            _log_error("WALLET_LOAD_ERROR", f"Failed to load wallet from config file: {e}", error_context)
            raise WalletError(f"Failed to load wallet from config file: {e}")
    
    raise WalletError(
        "No wallet configured. Set WATT_WALLET_PRIVATE_KEY environment variable "
        "or create a config file with your private key."
    )

def get_wallet_address() -> str:
    """Get the public key of the configured wallet."""
    wallet = _get_wallet()
    return str(wallet.pubkey())

def watt_balance(wallet_address: Optional[str] = None, raise_on_error: bool = False) -> int:
    """
    Get WATT balance for a wallet.
    
    Args:
        wallet_address: Solana wallet address (defaults to configured wallet)
        raise_on_error: If True, raise exception on error; else return 0
        
    Returns:
        Integer balance in WATT (whole tokens, not lamports)
        
    Raises:
        WalletError: If wallet cannot be loaded (when raise_on_error=True)
        APIError: If RPC call fails (when raise_on_error=True)
    """
    try:
        from solana.rpc.api import Client
        from solders.pubkey import Pubkey
        from spl.token.instructions import get_associated_token_address
        from spl.token.constants import TOKEN_2022_PROGRAM_ID
        
        # Get wallet
        if wallet_address:
            try:
                owner = Pubkey.from_string(wallet_address)
            except Exception as e:
                error_context = {"wallet_address": wallet_address}
                _log_error("INVALID_ADDRESS", f"Invalid Solana address: {e}", error_context)
                if raise_on_error:
                    raise WattCoinError(f"Invalid wallet address: {wallet_address}")
                return 0
        else:
            try:
                wallet = _get_wallet()
                owner = wallet.pubkey()
            except WalletError as e:
                if raise_on_error:
                    raise
                return 0
        
        # Connect to RPC
        client = Client(SOLANA_RPC)
        mint = Pubkey.from_string(WATT_MINT)
        ata = get_associated_token_address(owner, mint, token_program_id=TOKEN_2022_PROGRAM_ID)
        
        # Get balance
        resp = client.get_token_account_balance(ata)
        if resp.value:
            balance_raw = int(resp.value.amount)
            return balance_raw // (10 ** WATT_DECIMALS)
        return 0
        
    except Exception as e:
        error_context = {"wallet_address": wallet_address}
        _log_error("BALANCE_FETCH_ERROR", f"Failed to fetch balance: {e}", error_context)
        if raise_on_error:
            raise APIError(f"Failed to fetch balance: {e}")
        return 0

def watt_balance_formatted(wallet_address: str) -> str:
    """ Get formatted WATT balance with commas and suffix.

    Args:
        wallet_address: Solana wallet address

    Returns:
        Formatted balance string (e.g., "1,234,567.89 WATT")

    """
    try:
        balance = watt_balance(wallet_address)
        return f"{balance:,.2f} WATT"
    except Exception as e:
        return f"Error: {e}"

# Closes #42

# =============================================================================
# PAYMENTS - CORRECTLY FIXED FOR SOLDERS
# =============================================================================

def watt_send(to: str, amount: int, allow_insufficient_balance: bool = False) -> str:
    """
    Send WATT to an address.
    
    Args:
        to: Recipient wallet address
        amount: Amount of WATT to send (integer, not decimals)
        allow_insufficient_balance: If False, raises error if balance too low
        
    Returns:
        Transaction signature (hash)
        
    Raises:
        WalletError: If wallet cannot be loaded
        WattCoinError: If address is invalid
        InsufficientBalanceError: If balance too low (unless allow_insufficient_balance=True)
        TransactionError: If transaction fails
    """
    try:
        from solana.rpc.api import Client
        from solders.transaction import Transaction
        from solders.message import Message
        from solders.pubkey import Pubkey
        from solders.instruction import Instruction, AccountMeta
        from solders.hash import Hash
        from solders.signature import Signature
        from spl.token.instructions import get_associated_token_address
        from spl.token.constants import TOKEN_2022_PROGRAM_ID
        
        # Validate amount
        if amount <= 0:
            raise WattCoinError(f"Amount must be positive, got {amount}")
        
        # Load wallet
        wallet = _get_wallet()
        from_pubkey = wallet.pubkey()
        
        # Validate recipient address
        try:
            to_pubkey = Pubkey.from_string(to)
        except Exception as e:
            raise WattCoinError(f"Invalid recipient address '{to}': {e}")
        
        # Check balance if needed
        if not allow_insufficient_balance:
            current_balance = watt_balance()
            if current_balance < amount:
                raise InsufficientBalanceError(
                    f"Insufficient balance: {current_balance} WATT, need {amount} WATT"
                )
        
        # Connect to RPC
        client = Client(SOLANA_RPC)
        mint = Pubkey.from_string(WATT_MINT)
        
        # Get associated token addresses
        from_ata = get_associated_token_address(from_pubkey, mint, token_program_id=TOKEN_2022_PROGRAM_ID)
        to_ata = get_associated_token_address(to_pubkey, mint, token_program_id=TOKEN_2022_PROGRAM_ID)
        
        # Build transfer instruction
        amount_raw = amount * (10 ** WATT_DECIMALS)
        data = bytes([3]) + struct.pack("<Q", amount_raw)
        
        transfer_ix = Instruction(
            program_id=TOKEN_2022_PROGRAM_ID,
            accounts=[
                AccountMeta(pubkey=from_ata, is_signer=False, is_writable=True),
                AccountMeta(pubkey=mint, is_signer=False, is_writable=False),
                AccountMeta(pubkey=to_ata, is_signer=False, is_writable=True),
                AccountMeta(pubkey=from_pubkey, is_signer=True, is_writable=False),
            ],
            data=data
        )
        
        # Get recent blockhash
        try:
            blockhash_resp = client.get_latest_blockhash()
            recent_blockhash = Hash.from_string(str(blockhash_resp.value.blockhash))
        except Exception as e:
            raise APIError(f"Failed to get blockhash: {e}")
        
        # Build and sign message
        msg = Message.new_with_blockhash(
            [transfer_ix],
            from_pubkey,
            recent_blockhash
        )
        
        try:
            signature = wallet.sign_message(msg.to_bytes())
        except Exception as e:
            raise TransactionError(f"Failed to sign transaction: {e}")
        
        # Create and send transaction
        tx = Transaction([signature], msg)
        
        try:
            result = client.send_transaction(tx)
        except Exception as e:
            raise TransactionError(f"Failed to send transaction: {e}")
        
        if result.value:
            return str(result.value)
        else:
            raise TransactionError(f"Transaction failed: {result}")

# =============================================================================
# LLM QUERY
# =============================================================================

def watt_query(prompt: str, timeout_sec: int = 60) -> Dict[str, Any]:
    """
    Query Grok via LLM proxy. Auto-sends 500 WATT payment.
    
    Args:
        prompt: Question or prompt for Grok
        timeout_sec: Request timeout in seconds
        
    Returns:
        Dict with 'success', 'response', 'tokens_used', 'watt_charged', etc.
        
    Raises:
        InsufficientBalanceError: If balance < 500 WATT
        TransactionError: If payment transaction fails
        APIError: If API request fails
    """
    import time
    
    if not prompt or not prompt.strip():
        raise WattCoinError("Prompt cannot be empty")
    
    try:
        # Step 1: Check balance
        balance = watt_balance()
        if balance < LLM_PRICE:
            raise InsufficientBalanceError(
                f"Insufficient balance for LLM query. Required: {LLM_PRICE} WATT, Have: {balance} WATT"
            )
        
        # Step 2: Send payment
        try:
            tx_sig = watt_send(BOUNTY_WALLET, LLM_PRICE)
        except (TransactionError, InsufficientBalanceError) as e:
            raise APIError(f"Failed to send payment: {e}")
        
        # Step 3: Wait for confirmation
        time.sleep(3)
        
        # Step 4: Call LLM API
        wallet = get_wallet_address()
        
        try:
            resp = requests.post(
                f"{API_BASE}/api/v1/llm",
                json={
                    "prompt": prompt,
                    "wallet": wallet,
                    "tx_signature": tx_sig
                },
                timeout=timeout_sec
            )
            resp.raise_for_status()
        except requests.exceptions.RequestException as e:
            raise APIError(f"LLM API request failed: {e}")
        
        data = resp.json()
        
        if not data.get("success"):
            error_msg = data.get('message') or data.get('error') or 'Unknown error'
            raise APIError(f"LLM query failed: {error_msg}")
        
        return data
        
    except WattCoinError:
        raise
    except Exception as e:
        _log_error("LLM_QUERY_ERROR", str(e))
        raise APIError(f"Unexpected error in LLM query: {e}")

# =============================================================================
# SCRAPE
# =============================================================================

def watt_scrape(url: str, format: str = "text", timeout_sec: int = 30) -> Dict[str, Any]:
    """
    Scrape URL via WattCoin API. Auto-sends 100 WATT payment.
    
    Args:
        url: URL to scrape
        format: 'text', 'html', or 'json'
        timeout_sec: Request timeout in seconds
        
    Returns:
        Dict with 'success', 'content', 'url', 'watt_charged', etc.
        
    Raises:
        InsufficientBalanceError: If balance < 100 WATT
        TransactionError: If payment transaction fails
        APIError: If API request fails
    """
    import time
    
    if not url or not url.strip():
        raise WattCoinError("URL cannot be empty")
    
    if format not in ("text", "html", "json"):
        raise WattCoinError(f"Invalid format '{format}'. Must be 'text', 'html', or 'json'")
    
    try:
        # Step 1: Check balance
        balance = watt_balance()
        if balance < SCRAPE_PRICE:
            raise InsufficientBalanceError(
                f"Insufficient balance for scraping. Required: {SCRAPE_PRICE} WATT, Have: {balance} WATT"
            )
        
        # Step 2: Send payment
        try:
            tx_sig = watt_send(BOUNTY_WALLET, SCRAPE_PRICE)
        except (TransactionError, InsufficientBalanceError) as e:
            raise APIError(f"Failed to send payment: {e}")
        
        # Step 3: Wait for confirmation
        time.sleep(3)
        
        # Step 4: Call scraper API
        wallet = get_wallet_address()
        
        try:
            resp = requests.post(
                f"{API_BASE}/api/v1/scrape",
                json={
                    "url": url,
                    "format": format,
                    "wallet": wallet,
                    "tx_signature": tx_sig
                },
                timeout=timeout_sec
            )
            resp.raise_for_status()
        except requests.exceptions.RequestException as e:
            raise APIError(f"Scrape API request failed: {e}")
        
        data = resp.json()
        
        if not data.get("success"):
            error_msg = data.get('message') or data.get('error') or 'Unknown error'
            raise APIError(f"Scrape failed: {error_msg}")
        
        return data
        
    except WattCoinError:
        raise
    except Exception as e:
        _log_error("SCRAPE_ERROR", str(e))
        raise APIError(f"Unexpected error in scraping: {e}")

# =============================================================================
# TASKS
# =============================================================================

def watt_tasks(task_type: Optional[str] = None, min_reward: Optional[int] = None) -> Dict[str, Any]:
    """
    Get available tasks from WattCoin network.
    
    Args:
        task_type: Filter by type ('bounty', 'agent', or None for all)
        min_reward: Filter by minimum WATT reward
        
    Returns:
        Dict with 'tasks' list
    """
    params = {}
    if task_type:
        params["type"] = task_type
    if min_reward:
        params["min_reward"] = min_reward
    
    resp = requests.get(f"{API_BASE}/api/v1/tasks", params=params, timeout=10)
    return resp.json()

def watt_submit(task_id: int, result: Dict[str, Any]) -> Dict[str, Any]:
    """
    Submit task result for verification and payout.
    
    Args:
        task_id: ID of the completed task
        result: Task result data (format depends on task type)
        
    Returns:
        Dict with 'success', 'watt_earned', 'tx_signature', etc.
    """
    wallet = get_wallet_address()
    
    resp = requests.post(
        f"{API_BASE}/api/v1/tasks/{task_id}/submit",
        json={
            "wallet": wallet,
            "result": result
        },
        timeout=30
    )
    
    data = resp.json()
    
    if not data.get("success"):
        raise RuntimeError(f"Task submission failed: {data.get('message', data.get('error', 'Unknown error'))}")
    
    return data

def watt_post_task(
    title: str,
    description: str,
    reward: int,
    verification_criteria: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """
    Post a new task to the network (500+ WATT stake required).
    
    Args:
        title: Task title
        description: Task description
        reward: WATT reward for completion
        verification_criteria: Optional criteria for auto-verification
        
    Returns:
        Dict with 'task_id', 'tx_signature', etc.
    """
    if reward < MIN_TASK_REWARD:
        raise ValueError(f"Reward must be at least {MIN_TASK_REWARD} WATT")
    
    # Send stake payment
    tx_sig = watt_send(BOUNTY_WALLET, reward)
    
    # Wait for confirmation
    import time
    time.sleep(3)
    
    wallet = get_wallet_address()
    
    resp = requests.post(
        f"{API_BASE}/api/v1/tasks",
        json={
            "title": title,
            "description": description,
            "reward": reward,
            "wallet": wallet,
            "tx_signature": tx_sig,
            "verification_criteria": verification_criteria or {}
        },
        timeout=30
    )
    
    data = resp.json()
    
    if not data.get("success"):
        raise RuntimeError(f"Task posting failed: {data.get('message', data.get('error', 'Unknown error'))}")
    
    return data

# =============================================================================
# HELPER FUNCTIONS FOR COMMON OPERATIONS
# =============================================================================

def watt_check_balance_for(operation: str) -> Dict[str, Any]:
    """
    Check if you have enough WATT for a common operation.
    
    Args:
        operation: 'query' (500 WATT) or 'scrape' (100 WATT)
        
    Returns:
        Dict with 'can_do', 'balance', 'required', etc.
    """
    if operation == "query":
        required = LLM_PRICE
        op_name = "LLM query"
    elif operation == "scrape":
        required = SCRAPE_PRICE
        op_name = "Web scrape"
    else:
        raise WattCoinError(f"Unknown operation '{operation}'")
    
    balance = watt_balance()
    
    return {
        "operation": op_name,
        "can_do": balance >= required,
        "balance": balance,
        "required": required,
        "shortfall": max(0, required - balance)
    }

def watt_transaction_info(tx_signature: str) -> Dict[str, Any]:
    """
    Get info about a transaction.
    
    Args:
        tx_signature: Transaction hash/signature
        
    Returns:
        Dict with 'success', 'confirmed', 'block_time', 'error', etc.
    """
    try:
        from solana.rpc.api import Client
        
        client = Client(SOLANA_RPC)
        
        try:
            result = client.get_transaction(tx_signature)
        except Exception as e:
            raise APIError(f"Failed to fetch transaction: {e}")
        
        if not result.value:
            return {
                "success": False,
                "confirmed": False,
                "error": "Transaction not found"
            }
        
        tx = result.value.transaction
        
        return {
            "success": True,
            "confirmed": result.value.block_time is not None,
            "block_time": result.value.block_time,
            "slot": result.value.slot,
            "error": None
        }
        
    except WattCoinError:
        raise
    except Exception as e:
        _log_error("TRANSACTION_INFO_ERROR", str(e))
        raise APIError(f"Failed to get transaction info: {e}")

def watt_wait_for_confirmation(tx_signature: str, max_wait_sec: int = 30, poll_interval_sec: int = 2) -> Dict[str, Any]:
    """
    Wait for a transaction to be confirmed.
    
    Args:
        tx_signature: Transaction hash
        max_wait_sec: Maximum seconds to wait
        poll_interval_sec: Seconds between polls
        
    Returns:
        Dict with 'confirmed', 'time_waited_sec', etc.
    """
    import time
    
    start_time = time.time()
    
    while True:
        elapsed = time.time() - start_time
        
        try:
            info = watt_transaction_info(tx_signature)
            
            if info.get("confirmed"):
                return {
                    "confirmed": True,
                    "time_waited_sec": elapsed,
                    "block_time": info.get("block_time")
                }
            
            if elapsed > max_wait_sec:
                return {
                    "confirmed": False,
                    "time_waited_sec": elapsed,
                    "error": f"Timeout waiting for confirmation after {max_wait_sec}s"
                }
            
            time.sleep(poll_interval_sec)
            
        except APIError as e:
            if elapsed > max_wait_sec:
                raise
            time.sleep(poll_interval_sec)

def watt_estimate_cost(operation: str, count: int = 1) -> Dict[str, Any]:
    """
    Estimate cost for operations.
    
    Args:
        operation: 'query' or 'scrape'
        count: Number of operations
        
    Returns:
        Dict with 'total_watt', 'per_unit', 'breakdown', etc.
    """
    if operation == "query":
        per_unit = LLM_PRICE
        op_name = "LLM query"
    elif operation == "scrape":
        per_unit = SCRAPE_PRICE
        op_name = "Web scrape"
    else:
        raise WattCoinError(f"Unknown operation '{operation}'")
    
    total = per_unit * count
    balance = watt_balance()
    
    return {
        "operation": op_name,
        "per_unit_watt": per_unit,
        "count": count,
        "total_watt": total,
        "current_balance": balance,
        "after_cost": balance - total,
        "affordable": balance >= total
    }

# =============================================================================
# MAIN EXPORTS
# =============================================================================

__all__ = [
    # Wallet operations
    "get_wallet_address",
    "watt_balance",
    "watt_send",
    
    # API operations
    "watt_query",
    "watt_scrape",
    "watt_tasks",
    "watt_submit",
    "watt_post_task",
    
    # Helper functions
    "watt_check_balance_for",
    "watt_transaction_info",
    "watt_wait_for_confirmation",
    "watt_estimate_cost",
    
    # Error classes
    "WattCoinError",
    "WalletError",
    "APIError",
    "InsufficientBalanceError",
    "TransactionError",
]
