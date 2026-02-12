#!/usr/bin/env python3
"""
WattCoin Bounty Auto-Payment Script
Automates payment for already-approved PRs in the payout queue.

Usage:
    python bounty_auto_pay.py <pr_number>

Requirements:
    - PR must be in payout queue (approved & merged via dashboard)
    - BOUNTY_WALLET_KEY env var (base58 private key)
    - GITHUB_TOKEN env var

Safety:
    - Only pays PRs already approved by admin
    - Does NOT bypass Grok review or admin approval
    - Validates all data before sending
"""

import os
import sys
import json
import base58
import struct
import requests
from datetime import datetime
from solana.rpc.api import Client
from solders.transaction import Transaction
from solders.message import Message
from solders.pubkey import Pubkey
from solders.instruction import Instruction, AccountMeta
from solders.hash import Hash
from solders.keypair import Keypair
from spl.token.instructions import get_associated_token_address
from spl.token.constants import TOKEN_2022_PROGRAM_ID

# =============================================================================
# CONFIGURATION
# =============================================================================

SOLANA_RPC = "https://api.mainnet-beta.solana.com"
WATT_MINT = "Gpmbh4PoQnL1kNgpMYDED3iv4fczcr7d3qNBLf8rpump"
WATT_DECIMALS = 6
REPO = "WattCoin-Org/wattcoin"
DATA_FILE = "/app/data/bounty_reviews.json"

# Get credentials from env
BOUNTY_WALLET_PRIVATE_KEY = os.getenv("BOUNTY_WALLET_PRIVATE_KEY", "")
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN", "")

if not BOUNTY_WALLET_PRIVATE_KEY:
    print("❌ ERROR: BOUNTY_WALLET_PRIVATE_KEY not set in environment")
    sys.exit(1)

if not GITHUB_TOKEN:
    print("❌ ERROR: GITHUB_TOKEN not set in environment")
    sys.exit(1)

# =============================================================================
# DATA HANDLING
# =============================================================================

def load_data():
    """Load dashboard data."""
    try:
        with open(DATA_FILE, 'r') as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError) as e:
        print(f"❌ ERROR: Failed to load data: {e}")
        sys.exit(1)

def save_data(data):
    """Save dashboard data."""
    try:
        with open(DATA_FILE, 'w') as f:
            json.dump(data, f, indent=2)
        return True
    except Exception as e:
        print(f"❌ ERROR: Failed to save data: {e}")
        return False

# =============================================================================
# WALLET HANDLING
# =============================================================================

def get_bounty_wallet():
    """Load bounty wallet from private key."""
    try:
        key_bytes = base58.b58decode(BOUNTY_WALLET_PRIVATE_KEY)
        return Keypair.from_bytes(key_bytes)
    except Exception as e:
        print(f"❌ ERROR: Invalid bounty wallet key: {e}")
        sys.exit(1)

# =============================================================================
# SOLANA PAYMENT
# =============================================================================

def send_watt(recipient: str, amount: int, memo: str = None) -> str:
    """
    Send WATT to recipient address with optional on-chain memo.
    
    Args:
        recipient: Solana wallet address
        amount: WATT amount (whole tokens, not lamports)
        memo: Optional transaction memo (shows on explorer)
    
    Returns:
        Transaction signature
    """
    print(f"💸 Sending {amount:,} WATT to {recipient[:8]}...")
    if memo:
        print(f"📝 Memo: {memo}")
    
    try:
        # Load wallet
        wallet = get_bounty_wallet()
        from_pubkey = wallet.pubkey()
        
        # Validate recipient
        try:
            to_pubkey = Pubkey.from_string(recipient)
        except Exception as e:
            raise ValueError(f"Invalid recipient address: {e}")
        
        # Connect to RPC
        client = Client(SOLANA_RPC)
        mint = Pubkey.from_string(WATT_MINT)
        
        # Get token accounts
        from_ata = get_associated_token_address(
            from_pubkey, mint, token_program_id=TOKEN_2022_PROGRAM_ID
        )
        to_ata = get_associated_token_address(
            to_pubkey, mint, token_program_id=TOKEN_2022_PROGRAM_ID
        )
        
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
        
        # Build instructions list
        instructions = []
        
        # Add memo instruction if provided
        if memo:
            # SPL Memo Program ID
            memo_program = Pubkey.from_string("MemoSq4gqABAXKb96qnH8TysNcWxMyWCqXgDLGmfcHr")
            memo_ix = Instruction(
                program_id=memo_program,
                accounts=[
                    AccountMeta(pubkey=from_pubkey, is_signer=True, is_writable=False),
                ],
                data=memo.encode('utf-8')
            )
            instructions.append(memo_ix)
        
        # Add transfer instruction
        instructions.append(transfer_ix)
        
        # Get blockhash
        blockhash_resp = client.get_latest_blockhash()
        recent_blockhash = Hash.from_string(str(blockhash_resp.value.blockhash))
        
        # Build message with all instructions
        msg = Message.new_with_blockhash(
            instructions,
            from_pubkey,
            recent_blockhash
        )
        
        # Sign
        signature = wallet.sign_message(msg.to_bytes())
        
        # Create transaction
        tx = Transaction([signature], msg)
        
        # Send
        result = client.send_transaction(tx)
        
        if result.value:
            tx_sig = str(result.value)
            print(f"✅ Transaction sent: {tx_sig}")
            return tx_sig
        else:
            raise RuntimeError(f"Transaction failed: {result}")
            
    except Exception as e:
        print(f"❌ ERROR: Payment failed: {e}")
        raise

# =============================================================================
# GITHUB HANDLING
# =============================================================================

def github_headers():
    """Get GitHub API headers."""
    return {
        "Authorization": f"token {GITHUB_TOKEN}",
        "Accept": "application/vnd.github.v3+json"
    }

def get_issue_from_pr(pr_number: int):
    """Get issue number from PR body."""
    url = f"https://api.github.com/repos/{REPO}/pulls/{pr_number}"
    try:
        resp = requests.get(url, headers=github_headers(), timeout=15)
        if resp.status_code == 200:
            pr_data = resp.json()
            body = pr_data.get("body", "")
            
            # Look for "Closes #123" or "Fixes #123"
            import re
            match = re.search(r'(?:Closes|Fixes|Resolves)\s+#(\d+)', body, re.IGNORECASE)
            if match:
                return int(match.group(1))
        return None
    except Exception as e:
        print(f"⚠️  Warning: Could not get issue from PR: {e}")
        return None

def post_payment_to_issue(issue_number: int, amount: int, tx_sig: str):
    """Post payment proof to GitHub issue."""
    print(f"📝 Posting payment proof to issue #{issue_number}...")
    
    comment = f"""✅ **BOUNTY PAID**

**Amount:** {amount:,} WATT
**Transaction:** `{tx_sig}`
**Explorer:** https://solscan.io/tx/{tx_sig}

Thank you for your contribution!"""
    
    url = f"https://api.github.com/repos/{REPO}/issues/{issue_number}/comments"
    try:
        resp = requests.post(
            url,
            headers=github_headers(),
            json={"body": comment},
            timeout=15
        )
        if resp.status_code in [200, 201]:
            print(f"✅ Comment posted to issue #{issue_number}")
            return True
        else:
            print(f"⚠️  Warning: Failed to post comment: {resp.status_code}")
            return False
    except Exception as e:
        print(f"⚠️  Warning: Failed to post comment: {e}")
        return False

def add_paid_label(issue_number: int):
    """Add 'paid' label to GitHub issue for activity feed tracking."""
    print(f"🏷️  Adding 'paid' label to issue #{issue_number}...")
    
    url = f"https://api.github.com/repos/{REPO}/issues/{issue_number}/labels"
    try:
        resp = requests.post(
            url,
            headers=github_headers(),
            json={"labels": ["paid"]},
            timeout=15
        )
        if resp.status_code in (200, 201):
            print(f"✅ 'paid' label added to issue #{issue_number}")
            return True
        else:
            print(f"⚠️  Warning: Failed to add label: {resp.status_code}")
            return False
    except Exception as e:
        print(f"⚠️  Warning: Failed to add label: {e}")
        return False


def close_issue(issue_number: int):
    """Close GitHub issue."""
    print(f"🔒 Closing issue #{issue_number}...")
    
    url = f"https://api.github.com/repos/{REPO}/issues/{issue_number}"
    try:
        resp = requests.patch(
            url,
            headers=github_headers(),
            json={"state": "closed"},
            timeout=15
        )
        if resp.status_code == 200:
            print(f"✅ Issue #{issue_number} closed")
            return True
        else:
            print(f"⚠️  Warning: Failed to close issue: {resp.status_code}")
            return False
    except Exception as e:
        print(f"⚠️  Warning: Failed to close issue: {e}")
        return False

# =============================================================================
# MAIN PROCESS
# =============================================================================

def process_payout(pr_number: int):
    """
    Process payout for an approved PR.
    
    Steps:
        1. Load payout from queue
        2. Validate status and data
        3. Send WATT payment
        4. Post TX to issue
        5. Close issue
        6. Update dashboard
    """
    print(f"\n🚀 Processing payout for PR #{pr_number}\n")
    print("=" * 60)
    
    # Step 1: Load data
    print("\n📂 Loading dashboard data...")
    data = load_data()
    
    # Step 2: Find payout
    payout = None
    for p in data.get("payouts", []):
        if p.get("pr_number") == pr_number:
            payout = p
            break
    
    if not payout:
        print(f"❌ ERROR: PR #{pr_number} not found in payout queue")
        print("\n💡 TIP: PR must be approved & merged via dashboard first")
        sys.exit(1)
    
    # Step 3: Validate status
    if payout.get("status") == "paid":
        print(f"⚠️  WARNING: PR #{pr_number} already marked as paid")
        print(f"   TX: {payout.get('tx_sig', 'N/A')}")
        print("\n❓ Continue anyway? (y/N): ", end='')
        if input().lower() != 'y':
            print("Aborted.")
            sys.exit(0)
    
    # Step 4: Validate wallet and amount
    wallet = payout.get("wallet")
    amount = payout.get("amount", 0)
    
    if not wallet:
        print(f"❌ ERROR: No wallet address found for PR #{pr_number}")
        sys.exit(1)
    
    if amount <= 0:
        print(f"❌ ERROR: Invalid amount: {amount}")
        sys.exit(1)
    
    print(f"\n✅ Payout validated:")
    print(f"   PR: #{pr_number}")
    print(f"   Author: {payout.get('author', 'N/A')}")
    print(f"   Wallet: {wallet}")
    print(f"   Amount: {amount:,} WATT")
    
    # Step 5: Confirm
    print(f"\n❓ Send payment? (y/N): ", end='')
    if input().lower() != 'y':
        print("Aborted.")
        sys.exit(0)
    
    # Step 6: Send payment
    try:
        # Build memo for on-chain proof
        author = payout.get('author', 'unknown')
        memo = f"WattCoin Agent Payment | PR #{pr_number} | @{author} | {amount:,} WATT"
        tx_sig = send_watt(wallet, amount, memo=memo)
    except Exception as e:
        print(f"\n❌ PAYMENT FAILED: {e}")
        sys.exit(1)
    
    # Step 7: Get issue number
    issue_number = get_issue_from_pr(pr_number)
    if not issue_number:
        print(f"\n⚠️  Could not find issue for PR #{pr_number}")
        print(f"   TX sent but issue not updated: {tx_sig}")
        print(f"\n💡 Manually post TX to issue and close it")
    else:
        # Step 8: Post to issue
        post_payment_to_issue(issue_number, amount, tx_sig)
        
        # Step 8b: Add 'paid' label (for activity feed accuracy)
        add_paid_label(issue_number)
        
        # Step 9: Close issue
        close_issue(issue_number)
    
    # Step 10: Update dashboard
    print(f"\n💾 Updating dashboard...")
    payout["status"] = "paid"
    payout["paid_at"] = datetime.now().isoformat()
    payout["tx_sig"] = tx_sig
    
    if save_data(data):
        print(f"✅ Dashboard updated")
    else:
        print(f"⚠️  Warning: Failed to update dashboard")
        print(f"   Payment sent but dashboard not updated")
    
    # Summary
    print("\n" + "=" * 60)
    print("✅ PAYMENT COMPLETE")
    print("=" * 60)
    print(f"PR: #{pr_number}")
    print(f"Amount: {amount:,} WATT")
    print(f"Recipient: {wallet}")
    print(f"TX: {tx_sig}")
    print(f"Explorer: https://solscan.io/tx/{tx_sig}")
    if issue_number:
        print(f"Issue #{issue_number}: Closed ✓")
    print("=" * 60 + "\n")

# =============================================================================
# CLI
# =============================================================================

if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python bounty_auto_pay.py <pr_number>")
        print("\nExample: python bounty_auto_pay.py 32")
        sys.exit(1)
    
    try:
        pr_number = int(sys.argv[1])
    except ValueError:
        print("❌ ERROR: PR number must be an integer")
        sys.exit(1)
    
    process_payout(pr_number)


