# Payment System v2.0 - On-chain memo support for bounty payments
"""
WattCoin GitHub Webhook Handler
POST /webhooks/github - Handle PR events with full automation

Listens for:
- pull_request (action: opened) → Auto-trigger AI review
- pull_request (action: synchronize) → Auto-trigger AI review on updates
- pull_request (action: closed + merged = true) → Auto-execute payment

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
    contributor["score"] = calculate_score(contributor)
    contributor["tier"] = get_merit_tier(contributor["score"])
    contributor["last_updated"] = datetime.utcnow().isoformat() + "Z"
    
    data["contributors"] = contributors
    save_reputation_data(data)
    
    print(f"[REPUTATION] Updated {github_username}: {event} PR#{pr_number} → score={contributor['score']} tier={contributor['tier']}", flush=True)
    return contributor

def should_auto_merge(pr_author, review_score):
    """Gate auto-merge based on contributor tier + review score.
    Quality floor: ALL contributors need ≥9/10 — tier affects payouts, not quality bar."""
    rep = load_contributor_reputation(pr_author)
    tier = rep.get("tier", "new")
    
    if tier == "flagged":
        return False, tier, "Contributor is flagged — admin review required"
    if tier == "new":
        return False, tier, "New contributor — admin review required"
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
    from spl.token.instructions import get_associated_token_address, transfer_checked, TransferCheckedParams
    from spl.token.constants import TOKEN_2022_PROGRAM_ID
    
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
        
        # Get token accounts - BOTH must be looked up via RPC for Token-2022
        mint_pubkey = Pubkey.from_string(WATT_MINT)
        
        # Look up SENDER's token account
        print(f"[PAYMENT] Looking up sender's WATT token account...", flush=True)
        try:
            import requests
            sender_rpc_payload = {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "getTokenAccountsByOwner",
                "params": [
                    str(payer.pubkey()),
                    {"mint": WATT_MINT},
                    {"encoding": "jsonParsed"}
                ]
            }
            
            sender_rpc_response = requests.post(SOLANA_RPC, json=sender_rpc_payload, timeout=10)
            sender_rpc_data = sender_rpc_response.json()
            
            if "result" in sender_rpc_data and sender_rpc_data["result"]["value"]:
                sender_token_account = sender_rpc_data["result"]["value"][0]["pubkey"]
                sender_ata = Pubkey.from_string(sender_token_account)
                print(f"[PAYMENT] Found sender token account: {str(sender_ata)[:8]}...", flush=True)
            else:
                return None, f"Bounty wallet has no WATT token account!"
        except Exception as e:
            print(f"[PAYMENT] Error looking up sender token account: {e}", flush=True)
            return None, f"Failed to lookup sender token account: {e}"
        
        try:
            recipient_pubkey = Pubkey.from_string(wallet)
        except Exception as e:
            return None, f"Invalid recipient wallet address: {e}"
        
        # Look up RECIPIENT's token account
        print(f"[PAYMENT] Looking up recipient's WATT token account...", flush=True)
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
                return None, f"Recipient wallet has no WATT token account. Please have them receive WATT once first to create the account."
            
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
        
        # Create and sign transaction (memo first, then transfer)
        message = Message.new_with_blockhash(
            [memo_ix, transfer_ix],
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

def handle_pr_review_trigger(pr_number, action):
    """
    Handle PR opened or synchronized - trigger AI review and auto-merge if passed.
    """
    log_security_event("pr_review_triggered", {
        "pr_number": pr_number,
        "action": action
    })
    
    # Post initial comment
    post_github_comment(pr_number, "🤖 **AI review triggered...** Analyzing code changes...")
    
    # Trigger AI review
    review_result, review_error = trigger_ai_review(pr_number)
    
    if review_error:
        post_github_comment(pr_number, f"❌ **Review failed:** {review_error}")
        return jsonify({"message": "Review failed", "error": review_error}), 500
    
    review_data = review_result.get("review", {})
    score = review_data.get("score", 0)
    passed = review_data.get("pass", False)
    
    # If review passed threshold, check merit system before merging
    if passed and score >= 7:  # Minimum possible threshold (gold tier)
        # Get PR author
        import requests as req
        try:
            pr_resp = req.get(f"https://api.github.com/repos/{REPO}/pulls/{pr_number}",
                            headers=github_headers(), timeout=10)
            pr_author = pr_resp.json().get("user", {}).get("login", "unknown") if pr_resp.status_code == 200 else "unknown"
        except:
            pr_author = "unknown"
        
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

@webhooks_bp.route('/webhooks/github', methods=['POST'])
def github_webhook():
    """
    Handle GitHub webhook events.
    
    Expected events:
    - pull_request (closed + merged)
    """
    # Verify signature if secret is configured
    if GITHUB_WEBHOOK_SECRET:
        signature = request.headers.get('X-Hub-Signature-256', '')
        payload_body = request.get_data()
        
        if not verify_github_signature(payload_body, signature, GITHUB_WEBHOOK_SECRET):
            log_security_event("webhook_invalid_signature", {
                "ip": request.remote_addr,
                "headers": dict(request.headers)
            })
            return jsonify({"error": "Invalid signature"}), 403
    
    # Parse event
    event_type = request.headers.get('X-GitHub-Event')
    payload = request.get_json()
    
    if not payload:
        return jsonify({"error": "No payload"}), 400
    
    # Only handle pull_request events
    if event_type != 'pull_request':
        return jsonify({"message": f"Ignoring event type: {event_type}"}), 200
    
    action = payload.get("action")
    pr = payload.get("pull_request", {})
    pr_number = pr.get("number")
    merged = pr.get("merged", False)
    
    # Handle PR opened or synchronized (updated) - trigger auto-review
    if action in ["opened", "synchronize"]:
        return handle_pr_review_trigger(pr_number, action)
    
    # Only process merge events below this point
    if action == "closed" and not merged:
        # PR closed without merge — record rejection for merit system
        pr_author = pr.get("user", {}).get("login", "unknown")
        update_reputation(pr_author, "reject", pr_number)
        log_security_event("pr_rejected", {
            "pr_number": pr_number,
            "author": pr_author
        })
        return jsonify({"message": f"PR #{pr_number} closed without merge — rejection recorded"}), 200
    
    if action != "closed" or not merged:
        return jsonify({"message": f"Ignoring action: {action}, merged: {merged}"}), 200
    
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
    pr_author = pr.get("user", {}).get("login", "unknown")
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
            "pr_number": pr_number,
            "wallet": wallet
        })
        
        return jsonify({"message": "No review found"}), 200
    
    # Check if review passed
    review_result = review_data.get("review", {})
    if not review_result.get("pass"):
        # Review failed - shouldn't have been merged
        comment = f"""## ⚠️ Review Did Not Pass

This PR was merged but the AI review score was {review_result.get('score')}/10 (requires ≥8).

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
            "pr_number": pr_number,
            "wallet": wallet,
            "bounty_issue_id": bounty_issue_id
        })
        
        return jsonify({"message": "No bounty amount found"}), 200
    
    # Execute payment automatically
    post_github_comment(pr_number, f"🚀 **Processing payment...** {amount:,} WATT to `{wallet[:8]}...{wallet[-8:]}`")
    
    queue_payment(pr_number, wallet, amount, bounty_issue_id=bounty_issue_id, review_score=review_result.get("score"), author=pr_author)
    
    # Update WATT earned in reputation (merge already tracked earlier, deduped by PR#)
    update_reputation(pr_author, "merge", pr_number, watt_earned=amount)
    
    # Payment queued - comment will be posted by process_payment_queue() after confirmation
    log_security_event("payment_queued", {
        "pr_number": pr_number,
        "wallet": wallet,
        "amount": amount,
        "bounty_issue_id": bounty_issue_id
    })
    
    return jsonify({
        "message": "Payment queued for processing",
        "amount": amount,
        "wallet": wallet
    }), 200

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




