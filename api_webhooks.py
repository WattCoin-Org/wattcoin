# Payment System v2.0 - On-chain memo support for bounty payments
"""
WattCoin GitHub Webhook Handler
POST /webhooks/github - Handle PR and Issue events with full automation

Listens for:
- pull_request (action: opened) → Auto-trigger AI review + Discord activity
- pull_request (action: synchronize) → Auto-trigger AI review on updates
- pull_request (action: closed + merged = true) → Auto-execute payment
- issues (action: opened/labeled with 'bounty') → Discord activity notification

Full Automation Flow:
1. PR opened → AI reviews code automatically
2. If score ≥ 85% → Auto-merge PR
3. On merge → Auto-execute payment via bounty_auto_pay.py
4. Post TX signature to PR comments

Fallback: If auto-payment fails, queues for manual approval.
"""

import os
import json
import hmac
import hashlib
import uuid
import time
from datetime import datetime
from flask import Blueprint, request, jsonify

from pr_security import (
    verify_github_signature,
    extract_wallet_from_pr_body,
    check_emergency_pause,
    log_security_event,
    load_json_data,
    save_json_data,
    DATA_DIR,
    REQUIRE_DOUBLE_APPROVAL
)

webhooks_bp = Blueprint('webhooks', __name__)

# =============================================================================
# CONFIG
# =============================================================================

GITHUB_WEBHOOK_SECRET = os.getenv("GITHUB_WEBHOOK_SECRET", "")
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")
BASE_URL = os.getenv("BASE_URL", "https://wattcoin-production-81a7.up.railway.app")  # For internal API calls
REPO = "WattCoin-Org/wattcoin"

PR_REVIEWS_FILE = f"{DATA_DIR}/pr_reviews.json"
PR_PAYOUTS_FILE = f"{DATA_DIR}/pr_payouts.json"
REPUTATION_FILE = f"{DATA_DIR}/contributor_reputation.json"
PR_RATE_LIMITS_FILE = f"{DATA_DIR}/pr_rate_limits.json"

# AI Review Rate Limits
MAX_REVIEWS_PER_PR = 5
REVIEW_COOLDOWN_SECONDS = 900  # 15 minutes

# =============================================================================
# DISCORD NOTIFICATIONS
# =============================================================================

def notify_discord(title, message, color=0xFF0000, fields=None):
    """
    Send alert to Discord webhook. Silent if DISCORD_WEBHOOK_URL not set.
    Colors: red=0xFF0000, orange=0xFFA500, green=0x00FF00
    """
    webhook_url = os.getenv("DISCORD_WEBHOOK_URL", "")
    if not webhook_url:
        return  # No webhook configured — skip silently

    import requests as req

    embed = {
        "title": title,
        "description": message[:2000],
        "color": color,
        "timestamp": datetime.utcnow().isoformat() + "Z"
    }
    if fields:
        embed["fields"] = [{"name": k, "value": str(v)[:1024], "inline": True} for k, v in fields.items()]

    try:
        req.post(webhook_url, json={"embeds": [embed]}, timeout=5)
    except Exception as e:
        print(f"[DISCORD] Notification failed: {e}", flush=True)


def truncate_wallet(wallet):
    """Truncate wallet for public display: XXXX...XXXX"""
    if not wallet or len(wallet) < 12:
        return wallet or "unknown"
    return f"{wallet[:4]}...{wallet[-4:]}"


# =============================================================================
# CONTRIBUTOR REPUTATION (Merit System V1)
# =============================================================================

def load_reputation_data():
    """Load full reputation data from persistent file. Auto-seeds if missing. Always recalculates scores."""
    data = None
    try:
        if os.path.exists(REPUTATION_FILE):
            with open(REPUTATION_FILE, 'r') as f:
                data = json.load(f)
    except (json.JSONDecodeError, Exception) as e:
        print(f"[REPUTATION] Error loading: {e}", flush=True)
    
    if not data or "contributors" not in data:
        # Auto-seed with known history if file doesn't exist
        data = {
            "contributors": {
                "divol89": {
                    "github": "divol89",
                    "score": 0,
                    "tier": "new",
                    "merged_prs": [79],
                    "rejected_prs": [72],
                    "reverted_prs": [79],
                    "total_watt_earned": 0,
                    "last_updated": "2026-02-06T13:20:00Z"
                },
                "SudarshanSuryaprakash": {
                    "github": "SudarshanSuryaprakash",
                    "score": 0,
                    "tier": "new",
                    "merged_prs": [70],
                    "rejected_prs": [],
                    "reverted_prs": [],
                    "total_watt_earned": 15000,
                    "last_updated": "2026-02-05T04:10:00Z"
                },
                "ohmygod20260203": {
                    "github": "ohmygod20260203",
                    "score": 0,
                    "tier": "new",
                    "merged_prs": [75],
                    "rejected_prs": [],
                    "reverted_prs": [],
                    "total_watt_earned": 0,
                    "last_updated": "2026-02-06T00:00:00Z"
                },
                "Rajkoli145": {
                    "github": "Rajkoli145",
                    "score": 0,
                    "tier": "new",
                    "merged_prs": [],
                    "rejected_prs": [],
                    "reverted_prs": [],
                    "total_watt_earned": 0,
                    "last_updated": "2026-02-06T00:00:00Z"
                }
            }
        }
        print("[REPUTATION] Auto-seeded reputation file with known contributor history", flush=True)
    
    # Always recalculate scores from actual history to ensure formula consistency
    dirty = False
    contributors = data.get("contributors", {})
    
    for username, contributor in contributors.items():
        correct_score = calculate_score(contributor)
        correct_tier = get_merit_tier(correct_score)
        if contributor.get("score") != correct_score or contributor.get("tier") != correct_tier:
            contributor["score"] = correct_score
            contributor["tier"] = correct_tier
            dirty = True
    
    # Save if anything was corrected
    if dirty:
        try:
            os.makedirs(os.path.dirname(REPUTATION_FILE), exist_ok=True)
            with open(REPUTATION_FILE, 'w') as f:
                json.dump(data, f, indent=2)
            print("[REPUTATION] Recalculated and saved corrected scores", flush=True)
        except Exception as e:
            print(f"[REPUTATION] Failed to save corrected scores: {e}", flush=True)
    
    return data

def save_reputation_data(data):
    """Save full reputation data to persistent file."""
    try:
        os.makedirs(os.path.dirname(REPUTATION_FILE), exist_ok=True)
        with open(REPUTATION_FILE, 'w') as f:
            json.dump(data, f, indent=2)
        return True
    except Exception as e:
        print(f"[REPUTATION] Error saving: {e}", flush=True)
        return False

def load_contributor_reputation(github_username):
    """Load a single contributor's reputation data."""
    data = load_reputation_data()
    contributors = data.get("contributors", {})
    # Case-insensitive lookup
    for username, info in contributors.items():
        if username.lower() == github_username.lower():
            return info
    # Unknown contributor = new
    return {
        "github": github_username,
        "score": 0,
        "tier": "new",
        "merged_prs": [],
        "rejected_prs": [],
        "reverted_prs": [],
        "total_watt_earned": 0,
        "last_updated": None
    }

def calculate_score(contributor):
    """Calculate merit score from contributor history."""
    merged = len(contributor.get("merged_prs", []))
    rejected = len(contributor.get("rejected_prs", []))
    reverted = len(contributor.get("reverted_prs", []))
    watt = contributor.get("total_watt_earned", 0)
    return int((merged * 10) + (watt / 1000) - (rejected * 25) - (reverted * 25))

def get_merit_tier(score):
    """Return tier string from score."""
    if score < 0:
        return "flagged"
    elif score == 0:
        return "new"
    elif score < 50:
        return "bronze"
    elif score < 90:
        return "silver"
    else:
        return "gold"

def update_reputation(github_username, event, pr_number, watt_earned=0):
    """
    Update contributor reputation after an event.
    Events: 'merge', 'reject', 'revert'
    """
    # Skip system/org accounts
    SYSTEM_ACCOUNTS = {"wattcoin-org"}
    if github_username.lower() in SYSTEM_ACCOUNTS:
        print(f"[REPUTATION] Skipping system account: {github_username}", flush=True)
        return {"github": github_username, "score": 0, "tier": "system"}
    
    data = load_reputation_data()
    contributors = data.get("contributors", {})
    
    # Find or create (case-insensitive)
    found_key = None
    for key in contributors:
        if key.lower() == github_username.lower():
            found_key = key
            break
    
    if not found_key:
        found_key = github_username
        contributors[found_key] = {
            "github": github_username,
            "score": 0,
            "tier": "new",
            "merged_prs": [],
            "rejected_prs": [],
            "reverted_prs": [],
            "total_watt_earned": 0,
            "last_updated": None
        }
    
    contributor = contributors[found_key]
    
    if event == "merge":
        if pr_number not in contributor["merged_prs"]:
            contributor["merged_prs"].append(pr_number)
        contributor["total_watt_earned"] += watt_earned
    elif event == "reject":
        if pr_number not in contributor["rejected_prs"]:
            contributor["rejected_prs"].append(pr_number)
    elif event == "revert":
        if pr_number not in contributor["reverted_prs"]:
            contributor["reverted_prs"].append(pr_number)
    
    # Recalculate
    old_tier = contributor.get("tier", "new")
    contributor["score"] = calculate_score(contributor)
    contributor["tier"] = get_merit_tier(contributor["score"])
    contributor["last_updated"] = datetime.utcnow().isoformat() + "Z"
    
    data["contributors"] = contributors
    save_reputation_data(data)
    
    # Tier promotion notification
    new_tier = contributor["tier"]
    tier_order = ["new", "bronze", "silver", "gold"]
    if new_tier in tier_order and old_tier in tier_order:
        if tier_order.index(new_tier) > tier_order.index(old_tier):
            tier_emoji = {"bronze": "🥉", "silver": "🥈", "gold": "🥇"}.get(new_tier, "⭐")
            notify_discord(
                f"{tier_emoji} Tier Promotion",
                f"**@{github_username}** reached **{new_tier.title()}** tier!",
                color=0x9B59B6,
                fields={"Score": str(contributor["score"]), "Tier": new_tier.title()}
            )
    
    print(f"[REPUTATION] Updated {github_username}: {event} PR#{pr_number} → score={contributor['score']} tier={contributor['tier']}", flush=True)
    return contributor

def should_auto_merge(pr_author, review_score):
    """Gate auto-merge based on contributor tier + review score.
    Quality floor: ALL contributors need ≥9/10 — tier affects payouts, not quality bar."""
    rep = load_contributor_reputation(pr_author)
    tier = rep.get("tier", "new")
    
    if tier == "flagged":
        return False, tier, "Contributor is flagged — admin review required"
    if review_score < 9:
        return False, tier, f"Score {review_score}/10 below quality floor (requires ≥9)"
    
    return True, tier, f"Auto-merge approved ({tier} tier, score {review_score})"

# =============================================================================
# GITHUB HELPERS
# =============================================================================

def github_headers():
    """Get GitHub API headers."""
    headers = {"Accept": "application/vnd.github.v3+json"}
    if GITHUB_TOKEN:
        headers["Authorization"] = f"token {GITHUB_TOKEN}"
    return headers

def check_duplicate_bounty(pr_number):
    """
    Check if a PR references an already-closed, already-paid bounty issue.
    Returns: (is_duplicate, issue_number, reason) or (False, None, None)
    """
    import re
    import requests
    
    try:
        # Get PR body to find linked issue
        url = f"https://api.github.com/repos/{REPO}/pulls/{pr_number}"
        resp = requests.get(url, headers=github_headers(), timeout=10)
        if resp.status_code != 200:
            return False, None, None
        
        pr_data = resp.json()
        pr_body = pr_data.get("body", "") or ""
        pr_branch = pr_data.get("head", {}).get("ref", "")
        
        # Extract issue number from body (Fixes #69, Closes #69, etc.)
        issue_match = re.search(r'(?:fixes|closes|resolves)\s*#(\d+)', pr_body, re.IGNORECASE)
        
        # Also check branch name (bounty-69-xxx)
        if not issue_match:
            branch_match = re.search(r'bounty-(\d+)', pr_branch, re.IGNORECASE)
            if branch_match:
                issue_match = branch_match
        
        if not issue_match:
            return False, None, None
        
        issue_number = int(issue_match.group(1))
        
        # Check if issue is closed
        issue_url = f"https://api.github.com/repos/{REPO}/issues/{issue_number}"
        issue_resp = requests.get(issue_url, headers=github_headers(), timeout=10)
        if issue_resp.status_code != 200:
            return False, None, None
        
        issue_data = issue_resp.json()
        if issue_data.get("state") != "closed":
            return False, None, None
        
        # Issue is closed — check if there's already a merged PR for it
        # Search closed PRs referencing this issue
        search_url = f"https://api.github.com/search/issues?q=repo:{REPO}+is:pr+is:merged+{issue_number}+in:body"
        search_resp = requests.get(search_url, headers=github_headers(), timeout=10)
        
        if search_resp.status_code == 200:
            results = search_resp.json().get("items", [])
            merged_prs = [r for r in results if r.get("number") != pr_number]
            
            if merged_prs:
                paid_pr = merged_prs[0]
                reason = (
                    f"Issue #{issue_number} is already closed and was completed by "
                    f"PR #{paid_pr['number']} (merged {paid_pr.get('closed_at', 'previously')}). "
                    f"Bounty already paid."
                )
                return True, issue_number, reason
        
        # Fallback: issue is closed but we couldn't confirm a merged PR
        # Still flag it since the issue is closed
        reason = f"Issue #{issue_number} is already closed. Bounty may have been paid."
        return True, issue_number, reason
        
    except Exception as e:
        print(f"[DUPLICATE-CHECK] Error checking PR #{pr_number}: {e}", flush=True)
        return False, None, None


def get_bounty_amount(issue_number):
    """
    Fetch bounty amount from issue title.
    Returns: amount (int) or None
    """
    import re
    import requests
    
    try:
        url = f"https://api.github.com/repos/{REPO}/issues/{issue_number}"
        resp = requests.get(url, headers=github_headers(), timeout=10)
        
        if resp.status_code != 200:
            return None
        
        issue = resp.json()
        title = issue.get("title", "")
        
        # Extract amount like [BOUNTY: 100,000 WATT]
        match = re.search(r'(\d{1,3}(?:,?\d{3})*)\s*WATT', title, re.IGNORECASE)
        if match:
            return int(match.group(1).replace(',', ''))
        
        return None
    except:
        return None

def post_github_comment(issue_number, comment):
    """Post a comment on a GitHub issue/PR."""
    import requests
    
    if not GITHUB_TOKEN:
        return False
    
    try:
        url = f"https://api.github.com/repos/{REPO}/issues/{issue_number}/comments"
        resp = requests.post(
            url,
            headers=github_headers(),
            json={"body": comment},
            timeout=15
        )
        return resp.status_code in [200, 201]
    except:
        return False

# =============================================================================
# AUTO-REVIEW & AUTO-MERGE
# =============================================================================

def trigger_ai_review(pr_number):
    """
    Trigger AI review for a PR.
    Calls the review endpoint internally.
    Returns: (review_result, error)
    """
    import requests
    
    try:
        # Call internal review endpoint
        # Use module-level BASE_URL constant (no localhost default!)
        review_url = f"{BASE_URL}/api/v1/review_pr"
        
        # Review endpoint expects pr_url, not pr_number
        pr_url = f"https://github.com/{REPO}/pull/{pr_number}"
        

        # Log the internal call attempt
        print(f"[WEBHOOK] Calling internal review endpoint: {review_url} for PR #{pr_number}", flush=True)

        resp = requests.post(
            review_url,
            json={"pr_url": pr_url},
            headers={"Content-Type": "application/json"},
            timeout=60
        )
        

        # Log response status
        print(f"[WEBHOOK] Review call returned {resp.status_code}", flush=True)
        if resp.status_code != 200:
            print(f"[WEBHOOK] Error response: {resp.text[:500]}", flush=True)

        if resp.status_code == 200:
            return resp.json(), None
        else:
            return None, f"Review failed: {resp.status_code}"
    
    except Exception as e:
        print(f"[WEBHOOK] Exception calling review: {e}", flush=True)
        return None, f"Review error: {e}"

def auto_merge_pr(pr_number, review_score):
    """
    Auto-merge a PR. Threshold checks are handled by should_auto_merge() in the merit system.
    Returns: (success, error)
    """
    import requests
    
    try:
        url = f"https://api.github.com/repos/{REPO}/pulls/{pr_number}/merge"
        resp = requests.put(
            url,
            headers=github_headers(),
            json={
                "commit_title": f"Auto-merge PR #{pr_number} (AI score: {review_score}/10)",
                "commit_message": f"Automatically merged after passing AI review with score {review_score}/10",
                "merge_method": "squash"
            },
            timeout=15
        )
        
        if resp.status_code == 200:
            return True, None
        else:
            return False, f"Merge failed: {resp.status_code} - {resp.text}"
    
    except Exception as e:
        return False, f"Merge error: {e}"

def execute_auto_payment(pr_number, wallet, amount, bounty_issue_id=None, review_score=None):
    """
    Execute payment directly to contributor wallet.
    Looks up recipient's actual token account from blockchain.
    Includes on-chain memo with proof-of-work details.
    Returns: (tx_signature, error)
    """
    import base58
    from solana.rpc.api import Client
    from solders.transaction import Transaction
    from solders.message import Message
    from solders.pubkey import Pubkey
    from solders.keypair import Keypair
    from solders.instruction import Instruction
    from spl.token.instructions import get_associated_token_address, transfer_checked, TransferCheckedParams, create_associated_token_account
    from spl.token.constants import TOKEN_2022_PROGRAM_ID, ASSOCIATED_TOKEN_PROGRAM_ID
    from solders.system_program import ID as SYSTEM_PROGRAM_ID
    
    try:
        # Configuration
        SOLANA_RPC = "https://api.mainnet-beta.solana.com"
        WATT_MINT = "Gpmbh4PoQnL1kNgpMYDED3iv4fczcr7d3qNBLf8rpump"
        WATT_DECIMALS = 6
        
        # Get bounty wallet keypair from env
        private_key_b58 = os.getenv("BOUNTY_WALLET_PRIVATE_KEY", "")
        if not private_key_b58:
            return None, "BOUNTY_WALLET_PRIVATE_KEY not configured in Railway"
        
        print(f"[PAYMENT] Initializing payment: {amount:,} WATT to {wallet[:8]}...{wallet[-8:]}", flush=True)
        
        # Decode private key
        try:
            keypair_bytes = base58.b58decode(private_key_b58)
            payer = Keypair.from_bytes(keypair_bytes)
            print(f"[PAYMENT] Payer wallet: {str(payer.pubkey())[:8]}...{str(payer.pubkey())[-8:]}", flush=True)
        except Exception as e:
            return None, f"Invalid BOUNTY_WALLET_PRIVATE_KEY: {e}"
        
        # Initialize Solana client
        client = Client(SOLANA_RPC)
        print(f"[PAYMENT] Connected to Solana RPC", flush=True)
        
        # Get token accounts - derive ATAs deterministically (matches bounty_auto_pay.py)
        mint_pubkey = Pubkey.from_string(WATT_MINT)
        
        # Derive SENDER's token account
        print(f"[PAYMENT] Deriving sender ATA...", flush=True)
        sender_ata = get_associated_token_address(payer.pubkey(), mint_pubkey, token_program_id=TOKEN_2022_PROGRAM_ID)
        print(f"[PAYMENT] Sender ATA: {str(sender_ata)[:8]}...", flush=True)
        
        try:
            recipient_pubkey = Pubkey.from_string(wallet)
        except Exception as e:
            return None, f"Invalid recipient wallet address: {e}"
        
        # Look up RECIPIENT's token account (auto-create if missing)
        import requests
        print(f"[PAYMENT] Looking up recipient's WATT token account...", flush=True)
        create_ata_ix = None
        try:
            rpc_payload = {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "getTokenAccountsByOwner",
                "params": [
                    wallet,
                    {"mint": WATT_MINT},
                    {"encoding": "jsonParsed"}
                ]
            }
            
            rpc_response = requests.post(SOLANA_RPC, json=rpc_payload, timeout=10)
            rpc_data = rpc_response.json()
            
            if "result" in rpc_data and rpc_data["result"]["value"]:
                # Found token account(s)
                token_account_pubkey = rpc_data["result"]["value"][0]["pubkey"]
                recipient_ata = Pubkey.from_string(token_account_pubkey)
                print(f"[PAYMENT] Found recipient token account: {str(recipient_ata)[:8]}...", flush=True)
            else:
                # No ATA exists — derive it and add create instruction to transaction
                print(f"[PAYMENT] No WATT token account found for recipient. Creating ATA...", flush=True)
                recipient_ata = get_associated_token_address(
                    recipient_pubkey, mint_pubkey, token_program_id=TOKEN_2022_PROGRAM_ID
                )
                create_ata_ix = create_associated_token_account(
                    payer=payer.pubkey(),
                    owner=recipient_pubkey,
                    mint=mint_pubkey,
                    token_program_id=TOKEN_2022_PROGRAM_ID
                )
                print(f"[PAYMENT] Will create recipient ATA: {str(recipient_ata)[:8]}...", flush=True)
            
        except Exception as e:
            print(f"[PAYMENT] Error looking up token account: {e}", flush=True)
            return None, f"Failed to lookup recipient token account: {e}"
        
        print(f"[PAYMENT] Sender token account: {str(sender_ata)[:8]}... (Full: {str(sender_ata)})", flush=True)
        print(f"[PAYMENT] Recipient token account: {str(recipient_ata)[:8]}... (Full: {str(recipient_ata)})", flush=True)
        
        # Convert amount to lamports
        amount_lamports = int(amount * (10 ** WATT_DECIMALS))
        print(f"[PAYMENT] Amount: {amount_lamports} lamports ({amount:,.2f} WATT)", flush=True)
        
        # Create transfer instruction
        transfer_ix = transfer_checked(
            TransferCheckedParams(
                program_id=TOKEN_2022_PROGRAM_ID,
                source=sender_ata,
                mint=mint_pubkey,
                dest=recipient_ata,
                owner=payer.pubkey(),
                amount=amount_lamports,
                decimals=WATT_DECIMALS
            )
        )
        
        # Create memo instruction with proof-of-work details
        memo_program = Pubkey.from_string("MemoSq4gqABAXKb96qnH8TysNcWxMyWCqXgDLGmfcHr")
        issue_str = f"Issue #{bounty_issue_id}" if bounty_issue_id else "Issue #N/A"
        score_str = f"Score: {review_score}/10" if review_score else "Score: N/A"
        memo_text = f"WattCoin Bounty | PR #{pr_number} | {issue_str} | {score_str} | {amount:,.0f} WATT | Thank you!"
        
        memo_ix = Instruction(
            program_id=memo_program,
            accounts=[],
            data=memo_text.encode('utf-8')
        )
        print(f"[PAYMENT] Memo: {memo_text}", flush=True)
        
        # Get recent blockhash
        recent_blockhash_resp = client.get_latest_blockhash()
        recent_blockhash = recent_blockhash_resp.value.blockhash
        print(f"[PAYMENT] Recent blockhash obtained", flush=True)
        
        # Create and sign transaction (create ATA if needed, then memo, then transfer)
        tx_instructions = []
        if create_ata_ix:
            tx_instructions.append(create_ata_ix)
        tx_instructions.append(memo_ix)
        tx_instructions.append(transfer_ix)
        
        message = Message.new_with_blockhash(
            tx_instructions,
            payer.pubkey(),
            recent_blockhash
        )
        
        transaction = Transaction([payer], message, recent_blockhash)
        print(f"[PAYMENT] Transaction created and signed", flush=True)
        
        # Send transaction
        print(f"[PAYMENT] Sending transaction to network...", flush=True)
        tx_resp = client.send_transaction(transaction)
        tx_signature = str(tx_resp.value)
        print(f"[PAYMENT] Transaction sent: {tx_signature[:16]}...", flush=True)
        
        # CRITICAL: Wait for confirmation (up to 30 seconds)
        print(f"[PAYMENT] Waiting for confirmation...", flush=True)
        try:
            from solders.signature import Signature
            from solana.rpc.commitment import Confirmed
            
            # Convert string signature to Signature object
            sig_obj = Signature.from_string(tx_signature)
            
            # Wait for transaction to be confirmed
            confirmation = client.confirm_transaction(sig_obj, Confirmed)
            
            if confirmation.value:
                print(f"[PAYMENT] ✅ Transaction confirmed on-chain! TX: {tx_signature}", flush=True)
                return tx_signature, None
            else:
                error_msg = "Transaction sent but confirmation timed out"
                print(f"[PAYMENT] ⚠️ {error_msg}", flush=True)
                return None, error_msg
                
        except Exception as confirm_error:
            error_msg = f"Transaction sent but confirmation failed: {confirm_error}"
            print(f"[PAYMENT] ⚠️ {error_msg}", flush=True)
            # Return signature anyway since it was sent
            return tx_signature, str(confirm_error)
        
    except Exception as e:
        error_msg = f"Payment execution failed: {str(e)}"
        print(f"[PAYMENT] ❌ {error_msg}", flush=True)
        return None, error_msg



def queue_payment(pr_number, wallet, amount, bounty_issue_id=None, review_score=None, author=None):
    """
    Add payment to queue for processing after deployment.
    Prevents payments during deployment which causes container restarts.
    """
    import json
    import os
    from datetime import datetime
    
    queue_file = "/app/data/payment_queue.json"
    
    # Ensure data directory exists
    os.makedirs("/app/data", exist_ok=True)
    
    # Load existing queue
    queue = []
    if os.path.exists(queue_file):
        try:
            with open(queue_file, 'r') as f:
                queue = json.load(f)
        except:
            queue = []
    
    # Add new payment
    payment = {
        "pr_number": pr_number,
        "wallet": wallet,
        "amount": amount,
        "bounty_issue_id": bounty_issue_id,
        "review_score": review_score,
        "author": author,
        "queued_at": datetime.utcnow().isoformat(),
        "status": "pending"
    }
    
    queue.append(payment)
    
    # Save queue
    with open(queue_file, 'w') as f:
        json.dump(queue, f, indent=2)
    
    app.logger.info(f"[QUEUE] Payment queued: PR #{pr_number}, {amount:,} WATT to {wallet[:8]}...")
    
    return True

# =============================================================================
# AI REVIEW RATE LIMITING
# =============================================================================

def load_pr_rate_limits():
    """Load PR review rate limit tracking data."""
    try:
        with open(PR_RATE_LIMITS_FILE, 'r') as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}

def save_pr_rate_limits(data):
    """Save PR review rate limit tracking data."""
    os.makedirs(os.path.dirname(PR_RATE_LIMITS_FILE), exist_ok=True)
    with open(PR_RATE_LIMITS_FILE, 'w') as f:
        json.dump(data, f, indent=2)

def check_review_rate_limit(pr_number):
    """
    Check if a PR has exceeded AI review limits.
    Returns (allowed, reason) tuple.
    """
    limits = load_pr_rate_limits()
    pr_key = str(pr_number)
    
    if pr_key not in limits:
        return True, None
    
    pr_data = limits[pr_key]
    review_count = pr_data.get("count", 0)
    last_review = pr_data.get("last_review")
    
    # Check max reviews per PR
    if review_count >= MAX_REVIEWS_PER_PR:
        return False, (
            f"## ⛔ Review Limit Reached\n\n"
            f"This PR has used all **{MAX_REVIEWS_PER_PR}** AI reviews.\n\n"
            f"To get a fresh review, please **close this PR and open a new one** "
            f"with your fixes applied.\n\n"
            f"— WattCoin Automated Review"
        )
    
    # Check cooldown
    if last_review:
        from datetime import datetime, timezone
        try:
            last_time = datetime.fromisoformat(last_review.replace("Z", "+00:00"))
            now = datetime.now(timezone.utc)
            elapsed = (now - last_time).total_seconds()
            if elapsed < REVIEW_COOLDOWN_SECONDS:
                remaining = int(REVIEW_COOLDOWN_SECONDS - elapsed)
                mins = remaining // 60
                secs = remaining % 60
                return False, (
                    f"## ⏳ Review Cooldown\n\n"
                    f"Please wait **{mins}m {secs}s** before the next AI review.\n\n"
                    f"Reviews remaining for this PR: **{MAX_REVIEWS_PER_PR - review_count}**/{MAX_REVIEWS_PER_PR}\n\n"
                    f"— WattCoin Automated Review"
                )
        except (ValueError, TypeError):
            pass
    
    return True, None

def record_review(pr_number):
    """Record that an AI review was performed for a PR."""
    from datetime import datetime, timezone
    limits = load_pr_rate_limits()
    pr_key = str(pr_number)
    
    if pr_key not in limits:
        limits[pr_key] = {"count": 0, "last_review": None}
    
    limits[pr_key]["count"] = limits[pr_key].get("count", 0) + 1
    limits[pr_key]["last_review"] = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    
    save_pr_rate_limits(limits)


def load_banned_users():
    """Load banned users list from data file + hardcoded permanent bans."""
    # Hardcoded permanent bans (cannot be bypassed by data file deletion)
    PERMANENT_BANS = {"ohmygod20260203", "eugenejarvis88"}
    
    banned_file = os.path.join(DATA_DIR, "banned_users.json")
    try:
        with open(banned_file, 'r') as f:
            data = json.load(f)
            file_bans = {u.lower() for u in data.get("banned", [])}
            return PERMANENT_BANS | file_bans
    except (FileNotFoundError, json.JSONDecodeError):
        return PERMANENT_BANS

def save_banned_users(banned_set):
    """Save banned users list to data file."""
    banned_file = os.path.join(DATA_DIR, "banned_users.json")
    os.makedirs(DATA_DIR, exist_ok=True)
    with open(banned_file, 'w') as f:
        json.dump({"banned": sorted(banned_set), "updated": datetime.utcnow().isoformat() + "Z"}, f, indent=2)

def handle_pr_review_trigger(pr_number, action):
    """
    Handle PR opened or synchronized - trigger AI review and auto-merge if passed.
    """
    log_security_event("pr_review_triggered", {
        "pr_number": pr_number,
        "action": action
    })
    
    # === BANNED USER GATE ===
    import requests as req
    try:
        pr_resp = req.get(f"https://api.github.com/repos/{REPO}/pulls/{pr_number}",
                         headers=github_headers(), timeout=10)
        pr_data = pr_resp.json() if pr_resp.status_code == 200 else {}
        pr_author = pr_data.get("user", {}).get("login", "unknown")
        pr_body = pr_data.get("body", "") or ""
    except:
        pr_author = "unknown"
        pr_data = {}
        pr_body = ""
    
    # === SYSTEM ACCOUNT BYPASS ===
    SYSTEM_ACCOUNTS = {"wattcoin-org"}
    if pr_author.lower() in SYSTEM_ACCOUNTS:
        print(f"[SYSTEM] PR #{pr_number} from system account @{pr_author} — skipping all gates", flush=True)
        return jsonify({"message": "System account — gates bypassed", "author": pr_author}), 200
    
    banned_users = load_banned_users()
    if pr_author.lower() in banned_users:
        comment = (
            f"## 🚫 PR Rejected — Banned Contributor\n\n"
            f"@{pr_author} has been permanently banned from the WattCoin bounty system "
            f"due to repeated policy violations.\n\n"
            f"This PR has been automatically closed. No further PRs from this account will be reviewed.\n\n"
            f"— WattCoin Automated Review"
        )
        post_github_comment(pr_number, comment)
        
        # Close the PR
        try:
            close_url = f"https://api.github.com/repos/{REPO}/pulls/{pr_number}"
            req.patch(close_url, headers=github_headers(), json={"state": "closed"}, timeout=10)
        except:
            pass
        
        log_security_event("pr_rejected_banned_user", {
            "pr_number": pr_number,
            "author": pr_author
        })
        
        notify_discord(
            "🚫 Banned User PR Rejected",
            f"PR #{pr_number} from banned user @{pr_author} — auto-closed.",
            color=0xFF0000,
            fields={"PR": f"#{pr_number}", "Author": pr_author}
        )
        
        print(f"[BAN-GATE] PR #{pr_number} rejected — {pr_author} is banned", flush=True)
        return jsonify({"message": "Banned user", "author": pr_author}), 200
    
    # === WALLET REQUIREMENT GATE ===
    wallet, wallet_error = extract_wallet_from_pr_body(pr_body)
    if wallet_error:
        comment = (
            "## ⚠️ Wallet Required\n\n"
            "No valid Solana wallet found in PR body. **AI review will not run** until a wallet is provided.\n\n"
            "Add this to your PR description:\n"
            "```\n**Payout Wallet**: your_solana_address_here\n```\n\n"
            "Then push any commit to re-trigger review.\n\n"
            "— WattCoin Automated Review"
        )
        post_github_comment(pr_number, comment)
        
        log_security_event("pr_blocked_no_wallet", {
            "pr_number": pr_number,
            "author": pr_author
        })
        
        print(f"[WALLET-GATE] PR #{pr_number} blocked — no wallet in PR body", flush=True)
        return jsonify({"message": "Wallet required in PR body"}), 200
    
    # === DUPLICATE BOUNTY GUARD ===
    is_duplicate, issue_number, dup_reason = check_duplicate_bounty(pr_number)
    if is_duplicate:
        comment = (
            f"❌ **PR Auto-Rejected — Duplicate Bounty Claim**\n\n"
            f"{dup_reason}\n\n"
            f"⚠️ **Notice:** Submitting PRs for already-closed and already-paid bounties "
            f"will be rejected automatically. Repeat attempts may result in reputation penalties.\n\n"
            f"Please check issue status before working. Open bounties: "
            f"https://github.com/{REPO}/labels/bounty\n\n"
            f"— WattCoin Automated Review"
        )
        post_github_comment(pr_number, comment)
        
        # Close the PR automatically
        import requests as req
        try:
            close_url = f"https://api.github.com/repos/{REPO}/pulls/{pr_number}"
            req.patch(close_url, headers=github_headers(), json={"state": "closed"}, timeout=10)
        except:
            pass
        
        # pr_author already fetched above in ban gate
        update_reputation(pr_author, "reject", pr_number)
        
        log_security_event("duplicate_bounty_rejected", {
            "pr_number": pr_number,
            "issue_number": issue_number,
            "author": pr_author,
            "reason": dup_reason
        })
        
        notify_discord(
            "🚫 Duplicate Bounty Rejected",
            f"PR #{pr_number} tried to claim already-paid Issue #{issue_number}",
            color=0xFF0000,
            fields={"PR": f"#{pr_number}", "Issue": f"#{issue_number}", "Author": pr_author}
        )
        
        print(f"[DUPLICATE-GUARD] PR #{pr_number} rejected — duplicate claim on Issue #{issue_number}", flush=True)
        return jsonify({"message": "Duplicate bounty claim rejected", "issue": issue_number}), 200
    
    # === AI REVIEW RATE LIMIT GATE ===
    allowed, rate_limit_msg = check_review_rate_limit(pr_number)
    if not allowed:
        post_github_comment(pr_number, rate_limit_msg)
        print(f"[RATE-LIMIT] PR #{pr_number} — AI review blocked by rate limit", flush=True)
        return jsonify({"message": "Rate limited", "pr": pr_number}), 200
    
    # Post initial comment
    post_github_comment(pr_number, "🤖 **AI review triggered...** Analyzing code changes...")
    
    # Trigger AI review
    review_result, review_error = trigger_ai_review(pr_number)
    
    # Record this review against rate limit
    record_review(pr_number)
    
    if review_error:
        post_github_comment(pr_number, f"❌ **Review failed:** {review_error}")
        return jsonify({"message": "Review failed", "error": review_error}), 500
    
    review_data = review_result.get("review", {})
    score = review_data.get("score", 0)
    passed = review_data.get("pass", False)
    
    # Activity feed: AI review complete (score only, no details)
    review_verdict = "PASS ✅" if passed else "FAIL ❌"
    notify_discord(
        "🤖 AI Review Complete",
        f"PR #{pr_number} scored **{score}/10** — {review_verdict}",
        color=0x00FF00 if passed else 0xFF0000,
        fields={"PR": f"#{pr_number}", "Score": f"{score}/10", "Result": review_verdict}
    )
    
    # If review passed threshold, check merit system before merging
    if passed and score >= 7:  # Minimum possible threshold (gold tier)
        # pr_author already fetched above in ban gate
        
        # Merit system gate
        can_merge, tier, reason = should_auto_merge(pr_author, score)
        
        if can_merge:
            # Attempt auto-merge
            merged, merge_error = auto_merge_pr(pr_number, score)
            
            if merged:
                post_github_comment(
                    pr_number,
                    f"✅ **Auto-merged!** AI score: {score}/10 | Contributor tier: **{tier}**\n\n"
                    f"Payment will be processed automatically after merge completes."
                )
                
                log_security_event("pr_auto_merged", {
                    "pr_number": pr_number,
                    "score": score,
                    "tier": tier,
                    "author": pr_author
                })
            else:
                post_github_comment(
                    pr_number,
                    f"⚠️ **Review passed** (score: {score}/10) but auto-merge failed: {merge_error}\n\n"
                    f"Please merge manually."
                )
        else:
            # Blocked by merit system — post explanation
            if tier == "flagged":
                comment = (
                    f"## 🚫 Auto-Merge Blocked\n\n"
                    f"**AI Score**: {score}/10\n"
                    f"**Contributor**: @{pr_author} — **Flagged** (negative reputation)\n\n"
                    f"This contributor has a history of rejected or reverted submissions. "
                    f"Admin review is required for all PRs from this account."
                )
            else:
                comment = (
                    f"## ⏸️ Manual Review Required\n\n"
                    f"**AI Score**: {score}/10 ✅ PASS\n"
                    f"**Contributor**: @{pr_author} — **{tier.title()}** tier\n\n"
                    f"{reason}\n\n"
                    f"An admin will review shortly."
                )
            
            post_github_comment(pr_number, comment)
            
            log_security_event("pr_merge_blocked_merit", {
                "pr_number": pr_number,
                "score": score,
                "tier": tier,
                "author": pr_author,
                "reason": reason
            })
    
    return jsonify({
        "message": "Review completed",
        "score": score,
        "passed": passed
    }), 200

# =============================================================================
# PAYOUT QUEUE
# =============================================================================

def find_pr_review(pr_number):
    """Find review record for a PR."""
    reviews = load_json_data(PR_REVIEWS_FILE, default={"reviews": []})
    
    for review in reversed(reviews["reviews"]):
        if review.get("pr_number") == pr_number:
            return review
    
    return None

def queue_payout(pr_number, wallet, amount, bounty_issue_id, review_data):
    """
    Queue a payout for manual approval.
    Returns: payout_id
    """
    payouts = load_json_data(PR_PAYOUTS_FILE, default={"payouts": []})
    
    payout_id = len(payouts["payouts"]) + 1
    
    payout = {
        "id": payout_id,
        "pr_number": pr_number,
        "wallet": wallet,
        "amount": amount,
        "bounty_issue_id": bounty_issue_id,
        "status": "pending",
        "queued_at": datetime.utcnow().isoformat() + "Z",
        "approved_by": None,
        "approved_at": None,
        "tx_signature": None,
        "paid_at": None,
        "review_score": review_data.get("review", {}).get("score") if review_data else None,
        "requires_double_approval": REQUIRE_DOUBLE_APPROVAL,
        "approval_count": 0
    }
    
    payouts["payouts"].append(payout)
    save_json_data(PR_PAYOUTS_FILE, payouts)
    
    return payout_id

# =============================================================================
# WEBHOOK HANDLER
# =============================================================================

def generate_request_id():
    """Generate a short unique request ID for tracing webhook events."""
    return uuid.uuid4().hex[:8]


@webhooks_bp.route('/webhooks/github', methods=['POST'])
def github_webhook():
    """
    Handle GitHub webhook events.
    
    Expected events:
    - pull_request (closed + merged)
    """
    request_id = generate_request_id()
    start_time = time.time()
    print(f"[WEBHOOK:{request_id}] Incoming webhook from {request.remote_addr}", flush=True)

    # Verify signature if secret is configured
    if GITHUB_WEBHOOK_SECRET:
        signature = request.headers.get('X-Hub-Signature-256', '')
        payload_body = request.get_data()
        
        if not verify_github_signature(payload_body, signature, GITHUB_WEBHOOK_SECRET):
            log_security_event("webhook_invalid_signature", {
                "request_id": request_id,
                "ip": request.remote_addr,
                "headers": dict(request.headers)
            })
            elapsed = time.time() - start_time
            print(f"[WEBHOOK:{request_id}] Rejected invalid signature in {elapsed:.2f}s", flush=True)
            return jsonify({"error": "Invalid signature"}), 403
    
    # Parse event
    event_type = request.headers.get('X-GitHub-Event')
    payload = request.get_json()
    
    if not payload:
        elapsed = time.time() - start_time
        print(f"[WEBHOOK:{request_id}] Rejected empty payload in {elapsed:.2f}s", flush=True)
        return jsonify({"error": "No payload"}), 400

    # Validate payload structure for pull_request events
    if event_type == 'pull_request':
        if 'pull_request' not in payload:
            elapsed = time.time() - start_time
            print(f"[WEBHOOK:{request_id}] Malformed payload: missing pull_request key in {elapsed:.2f}s", flush=True)
            log_security_event("webhook_malformed_payload", {
                "request_id": request_id,
                "event_type": event_type,
                "reason": "missing pull_request key"
            })
            return jsonify({"error": "Malformed payload: missing pull_request"}), 400

        if not payload.get("pull_request", {}).get("number"):
            elapsed = time.time() - start_time
            print(f"[WEBHOOK:{request_id}] Malformed payload: missing PR number in {elapsed:.2f}s", flush=True)
            log_security_event("webhook_malformed_payload", {
                "request_id": request_id,
                "event_type": event_type,
                "reason": "missing PR number"
            })
            return jsonify({"error": "Malformed payload: missing PR number"}), 400
    
    # Handle issues events — bounty creation notifications
    if event_type == 'issues':
        issue_action = payload.get("action")
        issue = payload.get("issue", {})
        labels = [l.get("name", "").lower() for l in issue.get("labels", [])]
        
        # Notify on bounty-labeled issues (opened or labeled)
        if issue_action in ["opened", "labeled"] and "bounty" in labels:
            issue_title = issue.get("title", "Untitled")
            issue_number = issue.get("number")
            issue_body = issue.get("body", "") or ""
            
            # Try to extract WATT amount from body (common format: "XX,XXX WATT" or "XXXXX WATT")
            import re
            watt_match = re.search(r'([\d,]+)\s*WATT', issue_body, re.IGNORECASE)
            watt_str = watt_match.group(1).replace(",", "") if watt_match else None
            
            fields = {"Issue": f"#{issue_number}"}
            if watt_str and watt_str.isdigit():
                fields["Bounty"] = f"{int(watt_str):,} WATT"
            
            notify_discord(
                "📋 New Bounty Created",
                f"**{issue_title[:120]}**\nhttps://github.com/{REPO}/issues/{issue_number}",
                color=0xFFA500,
                fields=fields
            )
            print(f"[WEBHOOK:{request_id}] Bounty created: Issue #{issue_number}", flush=True)
        
        elapsed = time.time() - start_time
        return jsonify({"message": f"Issues event processed: {issue_action}"}), 200

    # Only handle pull_request events below this point
    if event_type != 'pull_request':
        elapsed = time.time() - start_time
        print(f"[WEBHOOK:{request_id}] Ignoring event type: {event_type} in {elapsed:.2f}s", flush=True)
        return jsonify({"message": f"Ignoring event type: {event_type}"}), 200
    
    action = payload.get("action")
    pr = payload.get("pull_request", {})
    pr_number = pr.get("number")
    merged = pr.get("merged", False)
    pr_author = pr.get("user", {}).get("login", "unknown")
    print(f"[WEBHOOK:{request_id}] PR #{pr_number} action={action} merged={merged} author={pr_author}", flush=True)
    
    # Handle PR opened or synchronized (updated) - trigger auto-review
    if action in ["opened", "synchronize"]:
        # Activity feed: PR submitted (only on new PRs, not updates)
        if action == "opened":
            pr_title = pr.get("title", "Untitled")
            notify_discord(
                "🔄 PR Submitted",
                f"PR #{pr_number} submitted by **@{pr_author}**\n`{pr_title[:100]}`",
                color=0x3498DB,
                fields={"PR": f"#{pr_number}", "Author": f"@{pr_author}"}
            )
        print(f"[WEBHOOK:{request_id}] Triggering AI review for PR #{pr_number}", flush=True)
        result = handle_pr_review_trigger(pr_number, action)
        elapsed = time.time() - start_time
        print(f"[WEBHOOK:{request_id}] Completed in {elapsed:.2f}s", flush=True)
        return result
    
    # Only process merge events below this point
    if action == "closed" and not merged:
        # PR closed without merge — record rejection for merit system
        update_reputation(pr_author, "reject", pr_number)
        log_security_event("pr_rejected", {
            "request_id": request_id,
            "pr_number": pr_number,
            "author": pr_author
        })
        elapsed = time.time() - start_time
        print(f"[WEBHOOK:{request_id}] PR #{pr_number} rejected, recorded in {elapsed:.2f}s", flush=True)
        return jsonify({"message": f"PR #{pr_number} closed without merge — rejection recorded"}), 200
    
    if action != "closed" or not merged:
        elapsed = time.time() - start_time
        print(f"[WEBHOOK:{request_id}] Ignoring action={action} merged={merged} in {elapsed:.2f}s", flush=True)
        return jsonify({"message": f"Ignoring action: {action}, merged: {merged}"}), 200
    
    try:
        # Check emergency pause
        is_paused, pause_type, pause_msg = check_emergency_pause()
        if is_paused and pause_type == "payouts":
            log_security_event("payout_blocked_pause", {
                "pr_number": pr_number,
                "reason": pause_msg
            })

            # Still return 200 to acknowledge webhook
            return jsonify({"message": "Payouts paused, no action taken"}), 200

        # Track merge in reputation system (before bounty logic — ALL merges count)
        update_reputation(pr_author, "merge", pr_number, watt_earned=0)

        # Extract wallet from PR body
        pr_body = pr.get("body", "")
        wallet, wallet_error = extract_wallet_from_pr_body(pr_body)

        if wallet_error:
            # Post comment about missing wallet
            comment = f"""## ❌ Payout Failed

    Unable to process payout: {wallet_error}

    Please update the PR description with your wallet address in this format:
    ```
    **Payout Wallet**: your_solana_address_here
    ```
    """
            post_github_comment(pr_number, comment)

            log_security_event("payout_failed", {
                "pr_number": pr_number,
                "reason": "missing_wallet",
                "error": wallet_error
            })

            elapsed = time.time() - start_time
            print(f"[WEBHOOK:{request_id}] Wallet extraction failed for PR #{pr_number} in {elapsed:.2f}s", flush=True)
            return jsonify({"message": "Wallet not found in PR"}), 200

        # Find review record
        review_data = find_pr_review(pr_number)

        if not review_data:
            # No review found - post comment
            comment = f"""## ⚠️ No Review Found

    This PR was merged but no AI review was found in our system.

    If you believe this is a bounty PR, please contact an admin to manually process the payout.
    """
            post_github_comment(pr_number, comment)

            log_security_event("payout_no_review", {
                "request_id": request_id,
                "pr_number": pr_number,
                "wallet": wallet
            })

            elapsed = time.time() - start_time
            print(f"[WEBHOOK:{request_id}] No review found for PR #{pr_number} in {elapsed:.2f}s", flush=True)
            return jsonify({"message": "No review found"}), 200

        # Check if review passed
        review_result = review_data.get("review", {})
        if not review_result.get("pass"):
            # Review failed - shouldn't have been merged
            comment = f"""## ⚠️ Review Did Not Pass

    This PR was merged but the AI review score was {review_result.get('score')}/10 (requires ≥9).

    Payout has been flagged for manual admin review.
    """
            post_github_comment(pr_number, comment)

            log_security_event("payout_failed_review", {
                "pr_number": pr_number,
                "wallet": wallet,
                "score": review_result.get("score")
            })

            # Still queue it, but admin will see low score

        # Get bounty issue ID from review or PR references
        bounty_issue_id = review_data.get("bounty_issue_id")

        if not bounty_issue_id:
            # Try to find from PR body
            import re
            referenced = re.findall(r'(?:closes?|fixes?|resolves?)?\s*#(\d+)', pr_body, re.IGNORECASE)
            if referenced:
                # Take the first referenced issue
                bounty_issue_id = int(referenced[0])

        # Get bounty amount
        amount = None
        if bounty_issue_id:
            amount = get_bounty_amount(bounty_issue_id)

        if not amount:
            # No bounty amount found
            comment = f"""## ⚠️ No Bounty Amount Found

    This PR was merged but we couldn't determine the bounty amount.

    Referenced issue: {f'#{bounty_issue_id}' if bounty_issue_id else 'None found'}

    An admin will review and process the payout manually if applicable.
    """
            post_github_comment(pr_number, comment)

            log_security_event("payout_no_amount", {
                "request_id": request_id,
                "pr_number": pr_number,
                "wallet": wallet,
                "bounty_issue_id": bounty_issue_id
            })

            elapsed = time.time() - start_time
            print(f"[WEBHOOK:{request_id}] No bounty amount for PR #{pr_number} in {elapsed:.2f}s", flush=True)
            return jsonify({"message": "No bounty amount found"}), 200

        # Execute payment automatically
        post_github_comment(pr_number, f"🚀 **Processing payment...** {amount:,} WATT to `{wallet[:8]}...{wallet[-8:]}`")

        queue_payment(pr_number, wallet, amount, bounty_issue_id=bounty_issue_id, review_score=review_result.get("score"), author=pr_author)

        # Activity feed: PR merged + payment queued
        pr_title = pr.get("title", "Untitled")
        notify_discord(
            "✅ PR Merged — Payment Queued",
            f"PR #{pr_number} merged | **{amount:,} WATT** queued for `{truncate_wallet(wallet)}`\n`{pr_title[:100]}`",
            color=0x00FF00,
            fields={"PR": f"#{pr_number}", "Author": f"@{pr_author}", "Amount": f"{amount:,} WATT", "Issue": f"#{bounty_issue_id}" if bounty_issue_id else "N/A"}
        )

        # Update WATT earned in reputation (merge already tracked earlier, deduped by PR#)
        update_reputation(pr_author, "merge", pr_number, watt_earned=amount)

        # Payment queued - comment will be posted by process_payment_queue() after confirmation
        log_security_event("payment_queued", {
            "request_id": request_id,
            "pr_number": pr_number,
            "wallet": wallet,
            "amount": amount,
            "bounty_issue_id": bounty_issue_id
        })

        elapsed = time.time() - start_time
        print(f"[WEBHOOK:{request_id}] Payment queued for PR #{pr_number} ({amount:,} WATT) in {elapsed:.2f}s", flush=True)

        return jsonify({
            "message": "Payment queued for processing",
            "amount": amount,
            "wallet": wallet
        }), 200

    except Exception as e:
        import traceback
        import uuid as _uuid
        error_ref = str(_uuid.uuid4())[:8]
        tb = traceback.format_exc()
        print(f"[WEBHOOK:{request_id}] MERGE PAYMENT CRASH ref={error_ref}: {e}\n{tb}", flush=True)

        try:
            post_github_comment(pr_number,
                f"## Payment Processing Error\n\n"
                f"An internal error occurred while processing the payout for this PR.\n\n"
                f"An admin has been notified and will process the payment manually.\n\n"
                f"Error ref: `{error_ref}`"
            )
        except:
            pass

        return jsonify({"message": "Internal error during payment processing", "error_ref": error_ref}), 200

# =============================================================================
# PAYMENT QUEUE PROCESSOR
# =============================================================================

def check_payment_already_sent(pr_number, recipient_wallet, amount):
    """
    Safety check: query on-chain to see if payment was already sent.
    Looks at bounty wallet's recent TXs for a memo matching this PR.
    Returns tx_signature if found, None otherwise.
    """
    import requests as req
    try:
        bounty_wallet = os.getenv("BOUNTY_WALLET_ADDRESS", "7vvNkG3JF3JpxLEavqZSkc5T3n9hHR98Uw23fbWdXVSF")
        rpc_url = "https://api.mainnet-beta.solana.com"
        
        # Get recent signatures from bounty wallet (last 10)
        resp = req.post(rpc_url, json={
            "jsonrpc": "2.0", "id": 1,
            "method": "getSignaturesForAddress",
            "params": [bounty_wallet, {"limit": 10}]
        }, timeout=10)
        
        sigs = resp.json().get("result", [])
        
        for sig_info in sigs:
            sig = sig_info["signature"]
            if sig_info.get("err"):
                continue
            
            # Fetch full TX to check memo
            tx_resp = req.post(rpc_url, json={
                "jsonrpc": "2.0", "id": 1,
                "method": "getTransaction",
                "params": [sig, {"encoding": "jsonParsed", "maxSupportedTransactionVersion": 0}]
            }, timeout=10)
            
            tx_data = tx_resp.json().get("result")
            if not tx_data:
                continue
            
            # Check log messages for our memo pattern
            log_messages = tx_data.get("meta", {}).get("logMessages", [])
            memo_match = f"PR #{pr_number}"
            
            for log in log_messages:
                if memo_match in log:
                    print(f"[QUEUE] ✅ Found existing payment for PR #{pr_number}: {sig[:20]}...", flush=True)
                    return sig
        
        return None
        
    except Exception as e:
        print(f"[QUEUE] ⚠️ On-chain check failed: {e}", flush=True)
        return None


def record_completed_payout(pr_number, wallet, amount, tx_signature, bounty_issue_id=None, review_score=None, author=None):
    """
    Record a completed auto-payment in pr_payouts.json so leaderboard/stats are accurate.
    """
    try:
        payouts = load_json_data(PR_PAYOUTS_FILE, default={"payouts": []})
        
        # Check for duplicate
        for p in payouts["payouts"]:
            if p.get("pr_number") == pr_number and p.get("status") == "paid":
                print(f"[RECORD] PR #{pr_number} already recorded, skipping", flush=True)
                return
        
        payout_id = len(payouts["payouts"]) + 1
        
        payout = {
            "id": payout_id,
            "pr_number": pr_number,
            "author": author or "unknown",
            "wallet": wallet,
            "amount": amount,
            "bounty_issue_id": bounty_issue_id,
            "status": "paid",
            "queued_at": __import__('datetime').datetime.utcnow().isoformat() + "Z",
            "approved_by": "auto",
            "approved_at": __import__('datetime').datetime.utcnow().isoformat() + "Z",
            "tx_signature": tx_signature,
            "paid_at": __import__('datetime').datetime.utcnow().isoformat() + "Z",
            "review_score": review_score,
            "payment_method": "auto_queue"
        }
        
        payouts["payouts"].append(payout)
        save_json_data(PR_PAYOUTS_FILE, payouts)
        print(f"[RECORD] ✅ Payout recorded: PR #{pr_number}, {amount:,} WATT to {author or 'unknown'}", flush=True)
        
    except Exception as e:
        print(f"[RECORD] ❌ Failed to record payout: {e}", flush=True)


def process_payment_queue():
    """
    Process pending payments from queue file.
    Called on startup after deploy. Checks on-chain before resending.
    """
    import json
    from datetime import datetime, timedelta
    
    queue_file = "/app/data/payment_queue.json"
    
    if not os.path.exists(queue_file):
        print("[QUEUE] No payment queue file found", flush=True)
        return
    
    try:
        with open(queue_file, 'r') as f:
            queue = json.load(f)
    except Exception as e:
        print(f"[QUEUE] Error loading queue: {e}", flush=True)
        return
    
    pending = [p for p in queue if p.get("status") in ("pending", "retry")]
    
    # Skip retries that aren't due yet
    now = datetime.utcnow().isoformat()
    pending = [p for p in pending if p.get("status") == "pending" or (p.get("status") == "retry" and p.get("next_retry_at", "") <= now)]
    
    # Reconcile: record any completed payments not yet in pr_payouts.json
    completed = [p for p in queue if p.get("status") == "completed" and p.get("tx_signature")]
    if completed:
        existing_payouts = load_json_data(PR_PAYOUTS_FILE, default={"payouts": []})
        existing_prs = {p.get("pr_number") for p in existing_payouts["payouts"] if p.get("status") == "paid"}
        
        for p in completed:
            if p["pr_number"] not in existing_prs:
                print(f"[QUEUE] Reconciling PR #{p['pr_number']} into payout ledger", flush=True)
                record_completed_payout(
                    p["pr_number"], p["wallet"], p["amount"], p["tx_signature"],
                    bounty_issue_id=p.get("bounty_issue_id"),
                    review_score=p.get("review_score"),
                    author=p.get("author")
                )
    
    if not pending:
        print("[QUEUE] No pending payments in queue", flush=True)
        return
    
    print(f"[QUEUE] Processing {len(pending)} pending payment(s)...", flush=True)
    
    for payment in pending:
        pr_number = payment["pr_number"]
        wallet = payment["wallet"]
        amount = payment["amount"]
        bounty_issue_id = payment.get("bounty_issue_id")
        review_score = payment.get("review_score")
        
        # Apply tier bonus
        author = payment.get("author")
        if author:
            rep = load_contributor_reputation(author)
            tier = rep.get("tier", "new")
            if tier == "silver":
                bonus = int(amount * 0.1)
                amount += bonus
                print(f"[QUEUE] Silver tier bonus: +{bonus:,} WATT for {author}", flush=True)
            elif tier == "gold":
                bonus = int(amount * 0.2)
                amount += bonus
                print(f"[QUEUE] Gold tier bonus: +{bonus:,} WATT for {author}", flush=True)
        
        print(f"[QUEUE] Processing PR #{pr_number}: {amount:,} WATT to {wallet[:8]}...", flush=True)
        
        # SAFETY: Check if payment already landed on-chain
        existing_tx = check_payment_already_sent(pr_number, wallet, amount)
        
        if existing_tx:
            # Already paid — mark complete, don't resend
            payment["status"] = "completed"
            payment["tx_signature"] = existing_tx
            payment["completed_at"] = __import__('datetime').datetime.utcnow().isoformat()
            payment["note"] = "Found existing on-chain TX during retry"
            
            # Record in payout ledger for leaderboard
            record_completed_payout(
                pr_number, wallet, amount, existing_tx,
                bounty_issue_id=bounty_issue_id,
                review_score=review_score,
                author=payment.get("author")
            )
            
            # Post success comment
            try:
                solscan_url = f"https://solscan.io/tx/{existing_tx}"
                post_github_comment(pr_number,
                    f"## ✅ Payment Confirmed\n\n"
                    f"**{amount:,} WATT** sent to `{wallet[:8]}...{wallet[-8:]}`\n\n"
                    f"🔗 [View on Solscan]({solscan_url})\n\n"
                    f"*Payment was recovered after server restart.*"
                )
            except Exception as e:
                print(f"[QUEUE] Comment failed for PR #{pr_number}: {e}", flush=True)
            
            continue
        
        # Not yet paid — execute payment
        try:
            tx_sig, error = execute_auto_payment(
                pr_number, wallet, amount,
                bounty_issue_id=bounty_issue_id,
                review_score=review_score
            )
            
            if tx_sig and not error:
                payment["status"] = "completed"
                payment["tx_signature"] = tx_sig
                payment["completed_at"] = __import__('datetime').datetime.utcnow().isoformat()
                
                solscan_url = f"https://solscan.io/tx/{tx_sig}"
                post_github_comment(pr_number,
                    f"## ✅ Payment Confirmed\n\n"
                    f"**{amount:,} WATT** sent to `{wallet[:8]}...{wallet[-8:]}`\n\n"
                    f"🔗 [View on Solscan]({solscan_url})\n\n"
                    f"Thank you for your contribution! ⚡🤖"
                )
                print(f"[QUEUE] ✅ PR #{pr_number} paid: {tx_sig[:20]}...", flush=True)
                notify_discord(
                    "✅ Payment Sent",
                    f"PR #{pr_number} bounty paid successfully.",
                    color=0x00FF00,
                    fields={"Amount": f"{amount:,} WATT", "Wallet": f"{wallet[:8]}...{wallet[-8:]}", "TX": f"[Solscan](https://solscan.io/tx/{tx_sig})"}
                )
                
                # Record in payout ledger for leaderboard
                record_completed_payout(
                    pr_number, wallet, amount, tx_sig,
                    bounty_issue_id=bounty_issue_id,
                    review_score=review_score,
                    author=payment.get("author")
                )
                
            elif tx_sig and error:
                # TX sent but confirmation uncertain
                payment["status"] = "unconfirmed"
                payment["tx_signature"] = tx_sig
                payment["error"] = error
                print(f"[QUEUE] ⚠️ PR #{pr_number} TX sent but unconfirmed: {error}", flush=True)
                
            else:
                retry_count = payment.get("retry_count", 0) + 1
                if retry_count < 3:
                    payment["status"] = "retry"
                    payment["retry_count"] = retry_count
                    payment["last_error"] = error
                    payment["next_retry_at"] = (datetime.utcnow() + timedelta(seconds=30 * (2 ** (retry_count - 1)))).isoformat()
                    print(f"[QUEUE] ⏳ PR #{pr_number} payment failed, retry {retry_count}/3 scheduled", flush=True)
                else:
                    payment["status"] = "failed"
                    payment["retry_count"] = retry_count
                    payment["error"] = error
                    payment["failed_at"] = datetime.utcnow().isoformat()
                    post_github_comment(pr_number, f"## ❌ Auto-Payment Failed\n\n"
                    f"Error: {error}\n\n"
                    f"Retried {retry_count} times. Admin will process this payment manually." )
                    print(f"[QUEUE] ❌ PR #{pr_number} payment failed after {retry_count} retries: {error}", flush=True)
                
        except Exception as e:
            retry_count = payment.get("retry_count", 0) + 1
            if retry_count < 3:
                payment["status"] = "retry"
                payment["retry_count"] = retry_count
                payment["last_error"] = str(e)
                payment["next_retry_at"] = (datetime.utcnow() + timedelta(seconds=30 * (2 ** (retry_count - 1)))).isoformat()
                print(f"[QUEUE] ⏳ PR #{pr_number} exception, retry {retry_count}/3 scheduled", flush=True)
            else:
                payment["status"] = "failed"
                payment["retry_count"] = retry_count
                payment["error"] = str(e)
                print(f"[QUEUE] ❌ PR #{pr_number} exception after {retry_count} retries: {e}", flush=True)
    
    # Save updated queue
    try:
        with open(queue_file, 'w') as f:
            json.dump(queue, f, indent=2)
        print(f"[QUEUE] Queue updated and saved", flush=True)
    except Exception as e:
        print(f"[QUEUE] Error saving queue: {e}", flush=True)


# =============================================================================
# HEALTH CHECK
# =============================================================================

@webhooks_bp.route('/webhooks/health', methods=['GET'])
def webhook_health():
    """Simple health check for webhook endpoint."""
    # Count pending payments in queue
    pending_count = 0
    queue_file = "/app/data/payment_queue.json"
    try:
        if os.path.exists(queue_file):
            with open(queue_file, 'r') as f:
                queue = json.load(f)
            pending_count = len([p for p in queue if p.get("status") == "pending"])
    except Exception:
        pass
    
    return jsonify({
        "status": "ok",
        "webhook_secret_configured": bool(GITHUB_WEBHOOK_SECRET),
        "pending_payments": pending_count
    }), 200






