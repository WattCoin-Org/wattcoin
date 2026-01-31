#!/usr/bin/env python3
"""
WattCoin Tip Transfer Script
Executes SPL token transfers from tip wallet to recipients.

Usage:
    python tip_transfer.py send <recipient_address> <amount>
    python tip_transfer.py balance
    python tip_transfer.py validate <address>
"""

import sys
import json
import base58
import struct
from datetime import datetime
from pathlib import Path

# Solana RPC endpoint
SOLANA_RPC = "https://api.mainnet-beta.solana.com"

# WattCoin token mint
WATT_MINT = "Gpmbh4PoQnL1kNgpMYDED3iv4fczcr7d3qNBLf8rpump"

# Token decimals
WATT_DECIMALS = 6

# Tip tracker file
TRACKER_FILE = Path(__file__).parent / "tip_tracker.json"


def validate_solana_address(address: str) -> bool:
    """Validate a Solana address format."""
    try:
        decoded = base58.b58decode(address)
        return len(decoded) == 32
    except Exception:
        return False


def load_tracker() -> dict:
    """Load tip tracker from JSON file."""
    if TRACKER_FILE.exists():
        with open(TRACKER_FILE, 'r') as f:
            return json.load(f)
    return {
        "tips": [],
        "stats": {
            "total_issued": 0,
            "total_claimed": 0,
            "total_sent": 0,
            "total_watt_distributed": 0
        }
    }


def save_tracker(data: dict):
    """Save tip tracker to JSON file."""
    with open(TRACKER_FILE, 'w') as f:
        json.dump(data, f, indent=2)


def add_tip(recipient_agent: str, amount: int, comment_id: str, post_id: str = "f97ae476-f989-4555-a537-3634c6107012") -> dict:
    """Add a new pending tip to the tracker."""
    import uuid
    
    tracker = load_tracker()
    
    # Check for duplicate
    for tip in tracker["tips"]:
        if tip["comment_id"] == comment_id:
            print(f"⚠️  Tip already exists for comment {comment_id}")
            return tip
    
    tip = {
        "tip_id": str(uuid.uuid4()),
        "post_id": post_id,
        "comment_id": comment_id,
        "recipient_agent": recipient_agent,
        "amount": amount,
        "status": "pending",
        "created_at": datetime.utcnow().isoformat(),
        "claim_address": None,
        "claimed_at": None,
        "tx_signature": None,
        "sent_at": None
    }
    
    tracker["tips"].append(tip)
    tracker["stats"]["total_issued"] += 1
    save_tracker(tracker)
    
    print(f"✅ Tip created: {tip['tip_id']}")
    print(f"   Recipient: {recipient_agent}")
    print(f"   Amount: {amount} WATT")
    print(f"   Status: pending")
    
    return tip


def claim_tip(tip_id: str, claim_address: str) -> dict:
    """Mark a tip as claimed with recipient address."""
    if not validate_solana_address(claim_address):
        print(f"❌ Invalid Solana address: {claim_address}")
        return None
    
    tracker = load_tracker()
    
    for tip in tracker["tips"]:
        if tip["tip_id"] == tip_id:
            if tip["status"] != "pending":
                print(f"⚠️  Tip already {tip['status']}")
                return tip
            
            tip["claim_address"] = claim_address
            tip["claimed_at"] = datetime.utcnow().isoformat()
            tip["status"] = "claimed"
            tracker["stats"]["total_claimed"] += 1
            save_tracker(tracker)
            
            print(f"✅ Tip claimed: {tip_id}")
            print(f"   Address: {claim_address}")
            print(f"   Amount: {tip['amount']} WATT")
            print(f"   Ready to send!")
            
            return tip
    
    print(f"❌ Tip not found: {tip_id}")
    return None


def list_tips(status_filter: str = None):
    """List all tips, optionally filtered by status."""
    tracker = load_tracker()
    
    tips = tracker["tips"]
    if status_filter:
        tips = [t for t in tips if t["status"] == status_filter]
    
    if not tips:
        print(f"No tips found" + (f" with status '{status_filter}'" if status_filter else ""))
        return
    
    print(f"\n{'='*60}")
    print(f"{'TIP ID':<36} {'AGENT':<15} {'AMOUNT':<10} {'STATUS':<10}")
    print(f"{'='*60}")
    
    for tip in tips:
        print(f"{tip['tip_id']:<36} {tip['recipient_agent']:<15} {tip['amount']:<10} {tip['status']:<10}")
    
    print(f"{'='*60}")
    print(f"Total: {len(tips)} tips")
    
    # Stats
    stats = tracker["stats"]
    print(f"\nStats:")
    print(f"  Issued: {stats['total_issued']}")
    print(f"  Claimed: {stats['total_claimed']}")
    print(f"  Sent: {stats['total_sent']}")
    print(f"  WATT distributed: {stats['total_watt_distributed']:,}")


def generate_tip_message(agent: str, amount: int) -> str:
    """Generate the tip announcement message."""
    return f"""⚡ Quality insight — tipped {amount:,} WATT from the ecosystem pool.

Reply with your Solana address to claim. No wallet? Create one at phantom.app in 60 seconds.

WattCoin: Powering the agent economy."""


def generate_confirmation_message(amount: int, address: str, tx_sig: str) -> str:
    """Generate the claim confirmation message."""
    short_addr = f"{address[:4]}...{address[-4:]}"
    return f"""✅ {amount:,} WATT sent!

TX: https://solscan.io/tx/{tx_sig}
Recipient: {short_addr}

Welcome to the WattCoin ecosystem. ⚡"""


def mark_sent(tip_id: str, tx_signature: str):
    """Mark a tip as sent with transaction signature."""
    tracker = load_tracker()
    
    for tip in tracker["tips"]:
        if tip["tip_id"] == tip_id:
            tip["tx_signature"] = tx_signature
            tip["sent_at"] = datetime.utcnow().isoformat()
            tip["status"] = "sent"
            tracker["stats"]["total_sent"] += 1
            tracker["stats"]["total_watt_distributed"] += tip["amount"]
            save_tracker(tracker)
            
            print(f"✅ Tip marked as sent: {tip_id}")
            print(f"   TX: https://solscan.io/tx/{tx_signature}")
            
            # Generate confirmation message
            print(f"\n📋 Confirmation message to post:")
            print("-" * 40)
            print(generate_confirmation_message(tip["amount"], tip["claim_address"], tx_signature))
            print("-" * 40)
            
            return tip
    
    print(f"❌ Tip not found: {tip_id}")
    return None


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        return
    
    cmd = sys.argv[1].lower()
    
    if cmd == "add":
        if len(sys.argv) < 5:
            print("Usage: python tip_transfer.py add <agent_name> <amount> <comment_id>")
            return
        agent = sys.argv[2]
        amount = int(sys.argv[3])
        comment_id = sys.argv[4]
        tip = add_tip(agent, amount, comment_id)
        if tip:
            print(f"\n📋 Tip message to post:")
            print("-" * 40)
            print(generate_tip_message(agent, amount))
            print("-" * 40)
    
    elif cmd == "claim":
        if len(sys.argv) < 4:
            print("Usage: python tip_transfer.py claim <tip_id> <solana_address>")
            return
        tip_id = sys.argv[2]
        address = sys.argv[3]
        claim_tip(tip_id, address)
    
    elif cmd == "sent":
        if len(sys.argv) < 4:
            print("Usage: python tip_transfer.py sent <tip_id> <tx_signature>")
            return
        tip_id = sys.argv[2]
        tx_sig = sys.argv[3]
        mark_sent(tip_id, tx_sig)
    
    elif cmd == "list":
        status = sys.argv[2] if len(sys.argv) > 2 else None
        list_tips(status)
    
    elif cmd == "validate":
        if len(sys.argv) < 3:
            print("Usage: python tip_transfer.py validate <address>")
            return
        address = sys.argv[2]
        if validate_solana_address(address):
            print(f"✅ Valid Solana address: {address}")
        else:
            print(f"❌ Invalid Solana address: {address}")
    
    elif cmd == "message":
        if len(sys.argv) < 4:
            print("Usage: python tip_transfer.py message <agent_name> <amount>")
            return
        agent = sys.argv[2]
        amount = int(sys.argv[3])
        print(generate_tip_message(agent, amount))
    
    else:
        print(f"Unknown command: {cmd}")
        print(__doc__)


if __name__ == "__main__":
    main()
