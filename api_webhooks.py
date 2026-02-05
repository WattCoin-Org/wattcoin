"""
WattCoin GitHub Webhook Handler
POST /webhooks/github - Handle PR events with full automation

Listens for:
- pull_request (action: opened) → Auto-trigger Grok review
- pull_request (action: synchronize) → Auto-trigger Grok review on updates
- pull_request (action: closed + merged = true) → Auto-execute payment

Full Automation Flow:
1. PR opened → Grok reviews code automatically
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

def trigger_grok_review(pr_number):
    """
    Trigger Grok review for a PR.
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
    Auto-merge a PR if it passes threshold.
    Returns: (success, error)
    """
    import requests
    
    MERGE_THRESHOLD = 8  # Grok scores are 1-10, not 1-100 (8/10 = 80%)
    
    if review_score < MERGE_THRESHOLD:
        return False, f"Score {review_score} < {MERGE_THRESHOLD} threshold"
    
    try:
        url = f"https://api.github.com/repos/{REPO}/pulls/{pr_number}/merge"
        resp = requests.put(
            url,
            headers=github_headers(),
            json={
                "commit_title": f"Auto-merge PR #{pr_number} (Grok score: {review_score}/100)",
                "commit_message": f"Automatically merged after passing Grok review with score {review_score}/100",
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

def execute_auto_payment(pr_number, wallet, amount):
    """
    Execute payment directly to contributor wallet.
    Looks up recipient's actual token account from blockchain.
    Returns: (tx_signature, error)
    """
    import base58
    from solana.rpc.api import Client
    from solders.transaction import Transaction
    from solders.message import Message
    from solders.pubkey import Pubkey
    from solders.keypair import Keypair
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
        
        # Get token accounts
        mint_pubkey = Pubkey.from_string(WATT_MINT)
        sender_ata = get_associated_token_address(payer.pubkey(), mint_pubkey)
        
        try:
            recipient_pubkey = Pubkey.from_string(wallet)
        except Exception as e:
            return None, f"Invalid recipient wallet address: {e}"
        
        # For Token-2022, we need to query the actual token account, not calculate ATA
        print(f"[PAYMENT] Looking up recipient's WATT token account...", flush=True)
        try:
            from solders.rpc.config import RpcTokenAccountsFilterMint
            token_accounts = client.get_token_accounts_by_owner(
                recipient_pubkey,
                RpcTokenAccountsFilterMint(mint_pubkey)
            )
            
            if not token_accounts.value:
                return None, f"Recipient wallet has no WATT token account. Please have them receive WATT once first."
            
            # Use the first token account found
            recipient_ata = Pubkey.from_string(token_accounts.value[0].pubkey)
            print(f"[PAYMENT] Found recipient token account: {str(recipient_ata)[:8]}...", flush=True)
            
        except Exception as e:
            print(f"[PAYMENT] Error looking up token account: {e}, falling back to ATA calculation", flush=True)
            recipient_ata = get_associated_token_address(recipient_pubkey, mint_pubkey)
        
        print(f"[PAYMENT] Sender ATA: {str(sender_ata)[:8]}...", flush=True)
        print(f"[PAYMENT] Recipient ATA: {str(recipient_ata)[:8]}...", flush=True)
        
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
        
        # Get recent blockhash
        recent_blockhash_resp = client.get_latest_blockhash()
        recent_blockhash = recent_blockhash_resp.value.blockhash
        print(f"[PAYMENT] Recent blockhash obtained", flush=True)
        
        # Create and sign transaction
        message = Message.new_with_blockhash(
            [transfer_ix],
            payer.pubkey(),
            recent_blockhash
        )
        
        transaction = Transaction([payer], message, recent_blockhash)
        print(f"[PAYMENT] Transaction created and signed", flush=True)
        
        # Send transaction
        print(f"[PAYMENT] Sending transaction to network...", flush=True)
        tx_resp = client.send_transaction(transaction)
        tx_signature = str(tx_resp.value)
        
        print(f"[PAYMENT] ✅ Payment successful! TX: {tx_signature}", flush=True)
        return tx_signature, None
        
    except Exception as e:
        error_msg = f"Payment execution failed: {str(e)}"
        print(f"[PAYMENT] ❌ {error_msg}", flush=True)
        return None, error_msg



def queue_payment(pr_number, wallet, amount):
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
    Handle PR opened or synchronized - trigger Grok review and auto-merge if passed.
    """
    log_security_event("pr_review_triggered", {
        "pr_number": pr_number,
        "action": action
    })
    
    # Post initial comment
    post_github_comment(pr_number, "🤖 **Grok review triggered...** Analyzing code changes...")
    
    # Trigger Grok review
    review_result, review_error = trigger_grok_review(pr_number)
    
    if review_error:
        post_github_comment(pr_number, f"❌ **Review failed:** {review_error}")
        return jsonify({"message": "Review failed", "error": review_error}), 500
    
    review_data = review_result.get("review", {})
    score = review_data.get("score", 0)
    passed = review_data.get("pass", False)
    
    # If review passed threshold, auto-merge
    if passed and score >= 8:  # 8/10 = 80% threshold
        # Attempt auto-merge
        merged, merge_error = auto_merge_pr(pr_number, score)
        
        if merged:
            post_github_comment(
                pr_number,
                f"✅ **Auto-merged!** Grok score: {score}/100\n\n"
                f"Payment will be processed automatically after merge completes."
            )
            
            log_security_event("pr_auto_merged", {
                "pr_number": pr_number,
                "score": score
            })
        else:
            post_github_comment(
                pr_number,
                f"⚠️ **Review passed** (score: {score}/100) but auto-merge failed: {merge_error}\n\n"
                f"Please merge manually."
            )
    
    return jsonify({
        "message": "Review completed",
        "score": score,
        "passed": passed,
        "auto_merged": passed and score >= 85
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

This PR was merged but no Grok review was found in our system.

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

This PR was merged but the Grok review score was {review_result.get('score')}/10 (requires ≥8).

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
    
    queue_payment(pr_number, wallet, amount)
    tx_signature = None
    payment_error = None
    
    if payment_error:
        # Payment failed - queue for manual review
        payout_id = queue_payout(pr_number, wallet, amount, bounty_issue_id, review_data)
        
        comment = f"""## ⚠️ Auto-Payment Failed

**Bounty Amount**: {amount:,} WATT
**Payout Wallet**: `{wallet[:8]}...{wallet[-8:]}`
**Error**: {payment_error}

Your payout has been queued (#{payout_id}) for manual processing by an admin.
"""
        post_github_comment(pr_number, comment)
        
        log_security_event("auto_payment_failed", {
            "pr_number": pr_number,
            "wallet": wallet,
            "amount": amount,
            "error": payment_error,
            "payout_id": payout_id
        })
        
        return jsonify({
            "message": "Payment failed, queued for manual review",
            "payout_id": payout_id
        }), 200
    
    # Payment succeeded!
    comment = f"""## 🎉 Payment Sent!

**Bounty Amount**: {amount:,} WATT
**Payout Wallet**: `{wallet}`
**Review Score**: {review_result.get('score', 'N/A')}/10
**TX Signature**: [{tx_signature[:8]}...{tx_signature[-8:]}](https://solscan.io/tx/{tx_signature})

Thank you for your contribution! 🚀
"""
    
    post_github_comment(pr_number, comment)
    
    log_security_event("auto_payment_success", {
        "pr_number": pr_number,
        "wallet": wallet,
        "amount": amount,
        "tx_signature": tx_signature,
        "bounty_issue_id": bounty_issue_id
    })
    
    return jsonify({
        "message": "Payment sent",
        "amount": amount,
        "wallet": wallet,
        "tx_signature": tx_signature
    }), 200

# =============================================================================
# HEALTH CHECK
# =============================================================================

@webhooks_bp.route('/webhooks/health', methods=['GET'])
def webhook_health():
    """Simple health check for webhook endpoint."""
    return jsonify({
        "status": "ok",
        "webhook_secret_configured": bool(GITHUB_WEBHOOK_SECRET)
    }), 200



