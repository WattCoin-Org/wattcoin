"""
SwarmSolve Phase 1 — Escrow Bounty Marketplace v1.0.0

Endpoints:
    POST /api/v1/solutions/prepare     — Get slug + escrow instructions (step 1)
    POST /api/v1/solutions/submit      — Verify escrow TX + create GitHub issue (step 2)
    GET  /api/v1/solutions             — List solutions (filter by status)
    GET  /api/v1/solutions/<id>        — Get single solution
    POST /api/v1/solutions/<id>/approve — Customer approves winner (token auth)
    POST /api/v1/solutions/<id>/refund  — Admin refund (manual v1)

Flow:
    1. Customer calls /prepare with title -> gets slug, escrow wallet, memo format
    2. Customer sends WATT to escrow wallet with memo "swarmsolve:<slug>"
    3. Customer calls /submit with TX sig + full spec
    4. Backend verifies TX on-chain, creates GitHub issue with solution-bounty label
    5. Agents compete — first merged PR wins
    6. Customer calls /approve with approval_token + pr_number
    7. Backend releases 95% to winner from escrow, 5% to treasury
"""

import os
import json
import time
import uuid
import re
import hashlib
import struct
import requests
import base58
from datetime import datetime, timedelta
from flask import Blueprint, request, jsonify
from solana.rpc.api import Client
from solders.transaction import Transaction
from solders.message import Message
from solders.pubkey import Pubkey
from solders.instruction import Instruction, AccountMeta
from solders.hash import Hash
from solders.keypair import Keypair
from spl.token.instructions import get_associated_token_address
from spl.token.constants import TOKEN_2022_PROGRAM_ID

from pr_security import load_json_data, save_json_data

# =============================================================================
# CONFIGURATION
# =============================================================================

swarmsolve_bp = Blueprint('swarmsolve', __name__)

SOLUTIONS_FILE = "/app/data/escrow_solutions.json"
SOLANA_RPC = "https://api.mainnet-beta.solana.com"
WATT_MINT = "Gpmbh4PoQnL1kNgpMYDED3iv4fczcr7d3qNBLf8rpump"
REPO = "WattCoin-Org/wattcoin"

MIN_BUDGET_WATT = 5000
DEFAULT_DEADLINE_DAYS = 14
MAX_DEADLINE_DAYS = 30
FEE_PERCENT = 5
TX_MAX_AGE_SECONDS = 1800  # 30 min

ESCROW_WALLET = os.getenv("ESCROW_WALLET_ADDRESS", "")
ESCROW_WALLET_PRIVATE_KEY = os.getenv("ESCROW_WALLET_PRIVATE_KEY", "")
TREASURY_WALLET = os.getenv("TREASURY_WALLET_ADDRESS", "")
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN", "")
WATT_DECIMALS = 6


# =============================================================================
# ESCROW PAYMENT
# =============================================================================

def get_escrow_wallet():
    """Load escrow wallet keypair from env var."""
    if not ESCROW_WALLET_PRIVATE_KEY:
        raise RuntimeError("ESCROW_WALLET_PRIVATE_KEY not set")
    key_bytes = base58.b58decode(ESCROW_WALLET_PRIVATE_KEY)
    return Keypair.from_bytes(key_bytes[:64])


def send_watt_from_escrow(recipient: str, amount: int, memo: str = None) -> str:
    """
    Send WATT from escrow wallet to recipient with optional memo.
    Auto-creates recipient ATA if it doesn't exist.
    Uses same proven pattern as bounty payment system.
    Returns transaction signature.
    """
    from spl.token.instructions import (
        get_associated_token_address, transfer_checked,
        TransferCheckedParams, create_associated_token_account
    )

    print(f"[ESCROW] Sending {amount:,} WATT to {recipient[:8]}...", flush=True)

    wallet = get_escrow_wallet()
    from_pubkey = wallet.pubkey()

    try:
        to_pubkey = Pubkey.from_string(recipient)
    except Exception as e:
        raise ValueError(f"Invalid recipient address: {e}")

    client = Client(SOLANA_RPC)
    mint = Pubkey.from_string(WATT_MINT)

    # Look up sender ATA via RPC
    sender_resp = requests.post(SOLANA_RPC, json={
        "jsonrpc": "2.0", "id": 1,
        "method": "getTokenAccountsByOwner",
        "params": [str(from_pubkey), {"mint": WATT_MINT}, {"encoding": "jsonParsed"}]
    }, timeout=10).json()

    if "result" in sender_resp and sender_resp["result"]["value"]:
        sender_ata = Pubkey.from_string(sender_resp["result"]["value"][0]["pubkey"])
    else:
        raise RuntimeError("Escrow wallet has no WATT token account!")

    # Look up recipient ATA — auto-create if missing
    create_ata_ix = None
    recip_resp = requests.post(SOLANA_RPC, json={
        "jsonrpc": "2.0", "id": 1,
        "method": "getTokenAccountsByOwner",
        "params": [recipient, {"mint": WATT_MINT}, {"encoding": "jsonParsed"}]
    }, timeout=10).json()

    if "result" in recip_resp and recip_resp["result"]["value"]:
        recipient_ata = Pubkey.from_string(recip_resp["result"]["value"][0]["pubkey"])
        print(f"[ESCROW] Found recipient ATA: {str(recipient_ata)[:8]}...", flush=True)
    else:
        print(f"[ESCROW] No WATT account for recipient. Creating ATA...", flush=True)
        recipient_ata = get_associated_token_address(
            to_pubkey, mint, token_program_id=TOKEN_2022_PROGRAM_ID
        )
        create_ata_ix = create_associated_token_account(
            payer=from_pubkey,
            owner=to_pubkey,
            mint=mint,
            token_program_id=TOKEN_2022_PROGRAM_ID
        )

    # Build transfer instruction (TransferChecked for Token-2022)
    amount_raw = int(amount * (10 ** WATT_DECIMALS))
    transfer_ix = transfer_checked(
        TransferCheckedParams(
            program_id=TOKEN_2022_PROGRAM_ID,
            source=sender_ata,
            mint=mint,
            dest=recipient_ata,
            owner=from_pubkey,
            amount=amount_raw,
            decimals=WATT_DECIMALS
        )
    )

    # Build instructions: [create ATA if needed] + [memo if provided] + transfer
    instructions = []
    if create_ata_ix:
        instructions.append(create_ata_ix)

    if memo:
        memo_program = Pubkey.from_string("MemoSq4gqABAXKb96qnH8TysNcWxMyWCqXgDLGmfcHr")
        memo_ix = Instruction(
            program_id=memo_program,
            accounts=[],
            data=memo.encode('utf-8')
        )
        instructions.append(memo_ix)

    instructions.append(transfer_ix)

    # Get blockhash, build message, sign, send
    blockhash_resp = client.get_latest_blockhash()
    recent_blockhash = blockhash_resp.value.blockhash

    msg = Message.new_with_blockhash(instructions, from_pubkey, recent_blockhash)
    tx = Transaction([wallet], msg, recent_blockhash)

    result = client.send_transaction(tx)

    if result.value:
        tx_sig = str(result.value)
        print(f"[ESCROW] ✅ TX sent: {tx_sig}", flush=True)
        return tx_sig
    else:
        raise RuntimeError(f"Transaction failed: {result}")


# =============================================================================
# DATA HANDLING
# =============================================================================

def load_solutions():
    """Load solutions data from JSON file."""
    return load_json_data(SOLUTIONS_FILE, default={"solutions": [], "used_tx_sigs": []})


def save_solutions(data):
    """Save solutions data to JSON file."""
    return save_json_data(SOLUTIONS_FILE, data)


def find_solution(solutions_data, solution_id):
    """Find a solution by ID. Returns solution dict or None."""
    return next((s for s in solutions_data.get("solutions", []) if s["id"] == solution_id), None)


def generate_slug(title):
    """Generate URL-safe slug from title with unique hash suffix."""
    slug = re.sub(r'[^a-z0-9]+', '-', title.lower().strip()).strip('-')[:40]
    short_hash = hashlib.md5(f"{title}{time.time()}".encode()).hexdigest()[:6]
    return f"{slug}-{short_hash}"


def generate_approval_token():
    """Generate secure approval token."""
    return str(uuid.uuid4())


def mask_wallet(wallet):
    """Mask wallet for public display."""
    if not wallet or len(wallet) < 12:
        return wallet
    return f"{wallet[:8]}...{wallet[-4:]}"


# =============================================================================
# ON-CHAIN VERIFICATION
# =============================================================================

def verify_escrow_tx(tx_signature, expected_amount, expected_memo_slug):
    """
    Verify escrow payment on Solana.
    Checks: TX exists, succeeded, WATT received by escrow wallet, memo matches.
    Returns: (success: bool, error_message: str or None)
    """
    if not ESCROW_WALLET:
        return False, "Escrow wallet not configured on server"

    try:
        # Fetch transaction with retries
        tx = None
        for attempt in range(5):
            resp = requests.post(SOLANA_RPC, json={
                "jsonrpc": "2.0", "id": 1,
                "method": "getTransaction",
                "params": [tx_signature, {
                    "encoding": "jsonParsed",
                    "maxSupportedTransactionVersion": 0
                }]
            }, timeout=10)
            result = resp.json().get("result")
            if result:
                tx = result
                break
            if attempt < 4:
                time.sleep(3)

        if not tx:
            return False, "Transaction not found on chain (try again in 30s)"

        meta = tx.get("meta", {})

        # Check TX succeeded
        if meta.get("err"):
            return False, "Transaction failed on chain"

        # Check TX age (must be recent)
        block_time = tx.get("blockTime")
        if block_time:
            tx_age = time.time() - block_time
            if tx_age > TX_MAX_AGE_SECONDS:
                return False, f"Transaction too old ({int(tx_age)}s, max {TX_MAX_AGE_SECONDS}s)"

        # Verify WATT transfer amount via pre/post token balances
        pre_balances = meta.get("preTokenBalances", [])
        post_balances = meta.get("postTokenBalances", [])

        pre_by_index = {}
        for bal in pre_balances:
            if bal.get("mint") == WATT_MINT:
                idx = bal.get("accountIndex")
                pre_by_index[idx] = float(bal.get("uiTokenAmount", {}).get("uiAmount", 0) or 0)

        escrow_received = 0
        for bal in post_balances:
            if bal.get("mint") != WATT_MINT:
                continue
            owner = bal.get("owner")
            if owner == ESCROW_WALLET:
                idx = bal.get("accountIndex")
                post_amount = float(bal.get("uiTokenAmount", {}).get("uiAmount", 0) or 0)
                pre_amount = pre_by_index.get(idx, 0)
                escrow_received = post_amount - pre_amount

        if escrow_received < expected_amount * 0.99:  # 1% tolerance
            return False, f"Escrow received {escrow_received:,.2f} WATT, expected {expected_amount:,.2f}"

        # Verify memo in log messages
        log_messages = meta.get("logMessages", [])
        expected_memo = f"swarmsolve:{expected_memo_slug}"
        memo_found = any(expected_memo in log for log in log_messages)

        if not memo_found:
            return False, f"Memo '{expected_memo}' not found in transaction logs"

        return True, None

    except Exception as e:
        return False, f"Verification error: {str(e)}"


# =============================================================================
# GITHUB INTEGRATION
# =============================================================================

def _gh_headers():
    """GitHub API request headers."""
    return {
        "Authorization": f"token {GITHUB_TOKEN}",
        "Accept": "application/vnd.github.v3+json"
    }


def create_solution_issue(solution):
    """
    Create GitHub issue for solution bounty.
    Returns: (issue_number, issue_url) or (None, None) on failure.
    """
    issue_num_placeholder = "{TBD}"
    title = f"[SOLUTION: {solution['budget_watt']:,} WATT] {solution['title']}"
    body = f"""## SwarmSolve Solution Request

**Budget:** {solution['budget_watt']:,} WATT (escrowed)
**Deadline:** {solution['deadline_days']} days ({solution['deadline_date']})
**Customer:** `{mask_wallet(solution['customer_wallet'])}`
**Solution ID:** `{solution['id']}`

---

## Specification

{solution['description']}

---

## How to Claim

1. Comment on this issue to claim
2. Submit a PR referencing this issue (include `Closes #{issue_num_placeholder}` in PR body)
3. Include your Solana wallet in PR body: `Wallet: <your-address>`
4. AI review + customer approval required
5. First merged PR wins — **{int(solution['budget_watt'] * (100 - FEE_PERCENT) / 100):,} WATT** (95%) released to winner

## Auto-Reject
- PRs not referencing this issue
- PRs over scope (stick to the spec)
- Bundled with other bounties/solutions

## Escrow Proof
[View escrow TX on Solscan](https://solscan.io/tx/{solution['escrow_tx']})

---
*Powered by SwarmSolve v1.0 — [wattcoin.org](https://wattcoin.org)*
"""

    try:
        resp = requests.post(
            f"https://api.github.com/repos/{REPO}/issues",
            headers=_gh_headers(),
            json={
                "title": title,
                "body": body,
                "labels": ["solution-bounty", "bounty"]
            },
            timeout=15
        )

        if resp.status_code in (200, 201):
            issue = resp.json()
            issue_number = issue["number"]
            issue_url = issue["html_url"]

            # Patch body to replace placeholder with actual issue number
            patched_body = body.replace(f"#{issue_num_placeholder}", f"#{issue_number}")
            requests.patch(
                f"https://api.github.com/repos/{REPO}/issues/{issue_number}",
                headers=_gh_headers(),
                json={"body": patched_body},
                timeout=15
            )

            print(f"[SWARMSOLVE] Created issue #{issue_number}: {title}", flush=True)
            return issue_number, issue_url
        else:
            print(f"[SWARMSOLVE] Issue creation failed: {resp.status_code} {resp.text[:200]}", flush=True)
            return None, None

    except Exception as e:
        print(f"[SWARMSOLVE] Issue creation error: {e}", flush=True)
        return None, None


def post_issue_comment(issue_number, comment):
    """Post comment on GitHub issue."""
    try:
        requests.post(
            f"https://api.github.com/repos/{REPO}/issues/{issue_number}/comments",
            headers=_gh_headers(),
            json={"body": comment},
            timeout=15
        )
    except Exception as e:
        print(f"[SWARMSOLVE] Comment error: {e}", flush=True)


def close_github_issue(issue_number):
    """Close GitHub issue."""
    try:
        requests.patch(
            f"https://api.github.com/repos/{REPO}/issues/{issue_number}",
            headers=_gh_headers(),
            json={"state": "closed"},
            timeout=15
        )
    except Exception as e:
        print(f"[SWARMSOLVE] Close issue error: {e}", flush=True)


def verify_pr_merged(pr_number, issue_number):
    """
    Check if PR is merged and references the solution issue.
    Returns: (valid: bool, author: str or None, winner_wallet: str or None, error: str or None)
    """
    try:
        resp = requests.get(
            f"https://api.github.com/repos/{REPO}/pulls/{pr_number}",
            headers=_gh_headers(),
            timeout=15
        )
        if resp.status_code != 200:
            return False, None, None, "PR not found"

        pr = resp.json()
        if not pr.get("merged"):
            return False, None, None, "PR is not merged"

        body = pr.get("body", "") or ""
        if f"#{issue_number}" not in body:
            return False, None, None, f"PR body does not reference issue #{issue_number}"

        author = pr.get("user", {}).get("login", "unknown")

        # Extract wallet from PR body — pattern: Wallet: <address>
        wallet_match = re.search(
            r'[Ww]allet[:\s]+`?([1-9A-HJ-NP-Za-km-z]{32,44})`?',
            body
        )
        winner_wallet = wallet_match.group(1) if wallet_match else None

        return True, author, winner_wallet, None

    except Exception as e:
        return False, None, None, f"Error checking PR: {e}"


# =============================================================================
# DISCORD NOTIFICATIONS
# =============================================================================

def notify_discord(title, description, color=0x00FF00, fields=None):
    """Send Discord embed for SwarmSolve events."""
    webhook_url = os.getenv("DISCORD_WEBHOOK_URL", "")
    if not webhook_url:
        return

    embed = {
        "title": title,
        "description": description,
        "color": color,
        "footer": {"text": "SwarmSolve v1.0"},
        "timestamp": datetime.utcnow().isoformat()
    }
    if fields:
        embed["fields"] = [{"name": k, "value": str(v), "inline": True} for k, v in fields.items()]

    try:
        requests.post(webhook_url, json={"username": "SwarmSolve", "embeds": [embed]}, timeout=10)
    except:
        pass


# =============================================================================
# ENDPOINTS
# =============================================================================

@swarmsolve_bp.route('/api/v1/solutions/prepare', methods=['POST'])
def prepare_solution():
    """
    Step 1 of 2: Get slug and escrow instructions BEFORE sending WATT.

    Body: { "title": "My project title" }
    Returns: slug, escrow_wallet, memo format, instructions
    """
    try:
        data = request.get_json()
        if not data:
            return jsonify({"error": "JSON body required"}), 400

        title = (data.get("title") or "").strip()
        if not title or len(title) < 5:
            return jsonify({"error": "Title required (min 5 chars)"}), 400

        if not ESCROW_WALLET:
            return jsonify({"error": "Escrow wallet not configured"}), 500

        slug = generate_slug(title)

        return jsonify({
            "slug": slug,
            "escrow_wallet": ESCROW_WALLET,
            "required_memo": f"swarmsolve:{slug}",
            "min_budget_watt": MIN_BUDGET_WATT,
            "max_deadline_days": MAX_DEADLINE_DAYS,
            "fee_percent": FEE_PERCENT,
            "instructions": [
                f"1. Send WATT to {ESCROW_WALLET} with memo: swarmsolve:{slug}",
                "2. Call POST /api/v1/solutions/submit with TX signature and full spec",
                "3. Save the approval_token from the response — needed to approve winner"
            ]
        }), 200

    except Exception as e:
        print(f"[SWARMSOLVE] Prepare error: {e}", flush=True)
        return jsonify({"error": "Internal error"}), 500


@swarmsolve_bp.route('/api/v1/solutions/submit', methods=['POST'])
def submit_solution():
    """
    Step 2 of 2: Submit spec + escrow TX proof.

    Body:
        title: str — must match what was passed to /prepare
        slug: str — slug returned from /prepare
        description: str — markdown spec (min 20 chars)
        budget_watt: int — amount sent (min 5,000)
        escrow_tx: str — Solana TX signature
        customer_wallet: str — sender's wallet
        deadline_days: int (optional, default 14)

    Returns:
        solution_id, approval_token (SECRET), github_issue_url
    """
    try:
        data = request.get_json()
        if not data:
            return jsonify({"error": "JSON body required"}), 400

        # Extract and validate fields
        title = (data.get("title") or "").strip()
        slug = (data.get("slug") or "").strip()
        description = (data.get("description") or "").strip()
        budget_watt = data.get("budget_watt", 0)
        escrow_tx = (data.get("escrow_tx") or "").strip()
        customer_wallet = (data.get("customer_wallet") or "").strip()
        deadline_days = data.get("deadline_days", DEFAULT_DEADLINE_DAYS)

        errors = []
        if not title or len(title) < 5:
            errors.append("title: min 5 chars")
        if not slug:
            errors.append("slug: required (from /prepare)")
        if not description or len(description) < 20:
            errors.append("description: min 20 chars")
        if budget_watt < MIN_BUDGET_WATT:
            errors.append(f"budget_watt: minimum {MIN_BUDGET_WATT:,}")
        if not escrow_tx:
            errors.append("escrow_tx: required")
        if not customer_wallet or len(customer_wallet) < 32:
            errors.append("customer_wallet: valid Solana address required")
        if deadline_days < 1 or deadline_days > MAX_DEADLINE_DAYS:
            errors.append(f"deadline_days: 1-{MAX_DEADLINE_DAYS}")

        if errors:
            return jsonify({"error": "Validation failed", "details": errors}), 400

        # Check TX not already used
        solutions_data = load_solutions()
        if escrow_tx in solutions_data.get("used_tx_sigs", []):
            return jsonify({"error": "Escrow TX already used for another solution"}), 400

        # Verify escrow TX on-chain
        print(f"[SWARMSOLVE] Verifying escrow TX {escrow_tx[:16]}... for {budget_watt:,} WATT", flush=True)
        verified, error = verify_escrow_tx(escrow_tx, budget_watt, slug)

        if not verified:
            return jsonify({
                "error": f"Escrow verification failed: {error}",
                "required_memo": f"swarmsolve:{slug}",
                "escrow_wallet": ESCROW_WALLET,
                "hint": "Ensure WATT was sent to the escrow wallet with the correct memo"
            }), 400

        # Build solution record
        solution_id = str(uuid.uuid4())[:8]
        approval_token = generate_approval_token()
        deadline_date = (datetime.utcnow() + timedelta(days=deadline_days)).strftime("%Y-%m-%d")

        solution = {
            "id": solution_id,
            "title": title,
            "slug": slug,
            "description": description,
            "budget_watt": budget_watt,
            "escrow_tx": escrow_tx,
            "customer_wallet": customer_wallet,
            "deadline_days": deadline_days,
            "deadline_date": deadline_date,
            "approval_token_hash": hashlib.sha256(approval_token.encode()).hexdigest(),
            "status": "open",
            "github_issue": None,
            "github_issue_url": None,
            "winner_pr": None,
            "winner_wallet": None,
            "winner_author": None,
            "payout_tx": None,
            "created_at": datetime.utcnow().isoformat(),
            "approved_at": None,
            "refunded_at": None
        }

        # Create GitHub issue
        issue_number, issue_url = create_solution_issue(solution)
        if issue_number:
            solution["github_issue"] = issue_number
            solution["github_issue_url"] = issue_url

        # Save to data file
        solutions_data["solutions"].append(solution)
        solutions_data.setdefault("used_tx_sigs", []).append(escrow_tx)
        save_solutions(solutions_data)

        # Discord notification
        notify_discord(
            "New Solution Request",
            f"**{title}**\n\nBudget: {budget_watt:,} WATT | Deadline: {deadline_days} days",
            color=0x00BFFF,
            fields={
                "Solution ID": solution_id,
                "Escrow TX": f"[Solscan](https://solscan.io/tx/{escrow_tx})",
                "Issue": f"[#{issue_number}]({issue_url})" if issue_number else "N/A"
            }
        )

        print(f"[SWARMSOLVE] Solution {solution_id} created: {title} ({budget_watt:,} WATT)", flush=True)

        return jsonify({
            "solution_id": solution_id,
            "slug": slug,
            "approval_token": approval_token,
            "github_issue": issue_number,
            "github_issue_url": issue_url,
            "escrow_wallet": ESCROW_WALLET,
            "budget_watt": budget_watt,
            "deadline_date": deadline_date,
            "message": "Solution created! Save your approval_token — needed to approve the winner.",
            "warning": "Do NOT share your approval_token publicly."
        }), 201

    except Exception as e:
        print(f"[SWARMSOLVE] Submit error: {e}", flush=True)
        return jsonify({"error": "Internal error"}), 500


@swarmsolve_bp.route('/api/v1/solutions', methods=['GET'])
def list_solutions():
    """List solutions with optional ?status=open|approved|refunded filter."""
    try:
        status_filter = request.args.get("status", "").lower()
        solutions_data = load_solutions()
        solutions = solutions_data.get("solutions", [])

        if status_filter:
            solutions = [s for s in solutions if s.get("status") == status_filter]

        # Return public-safe fields only
        public = [{
            "id": s["id"],
            "title": s["title"],
            "budget_watt": s["budget_watt"],
            "status": s["status"],
            "deadline_date": s.get("deadline_date"),
            "github_issue": s.get("github_issue"),
            "github_issue_url": s.get("github_issue_url"),
            "winner_pr": s.get("winner_pr"),
            "created_at": s.get("created_at"),
            "customer_wallet": mask_wallet(s.get("customer_wallet"))
        } for s in solutions]

        return jsonify({"solutions": public, "count": len(public)}), 200

    except Exception as e:
        print(f"[SWARMSOLVE] List error: {e}", flush=True)
        return jsonify({"error": "Internal error"}), 500


@swarmsolve_bp.route('/api/v1/solutions/<solution_id>', methods=['GET'])
def get_solution(solution_id):
    """Get single solution details (public view)."""
    try:
        solutions_data = load_solutions()
        solution = find_solution(solutions_data, solution_id)

        if not solution:
            return jsonify({"error": "Solution not found"}), 404

        return jsonify({
            "id": solution["id"],
            "title": solution["title"],
            "description": solution["description"],
            "budget_watt": solution["budget_watt"],
            "status": solution["status"],
            "deadline_date": solution.get("deadline_date"),
            "github_issue": solution.get("github_issue"),
            "github_issue_url": solution.get("github_issue_url"),
            "escrow_tx": solution.get("escrow_tx"),
            "winner_pr": solution.get("winner_pr"),
            "winner_author": solution.get("winner_author"),
            "payout_tx": solution.get("payout_tx"),
            "created_at": solution.get("created_at"),
            "approved_at": solution.get("approved_at"),
            "customer_wallet": mask_wallet(solution.get("customer_wallet"))
        }), 200

    except Exception as e:
        print(f"[SWARMSOLVE] Get error: {e}", flush=True)
        return jsonify({"error": "Internal error"}), 500


@swarmsolve_bp.route('/api/v1/solutions/<solution_id>/approve', methods=['POST'])
def approve_solution(solution_id):
    """
    Customer approves winning PR — triggers escrow release.

    Body:
        approval_token: str — secret from /submit response
        pr_number: int — merged PR number
    """
    try:
        data = request.get_json()
        if not data:
            return jsonify({"error": "JSON body required"}), 400

        approval_token = (data.get("approval_token") or "").strip()
        pr_number = data.get("pr_number")

        if not approval_token:
            return jsonify({"error": "approval_token required"}), 400
        if not pr_number or not isinstance(pr_number, int):
            return jsonify({"error": "Valid pr_number (integer) required"}), 400

        # Find solution
        solutions_data = load_solutions()
        solution = find_solution(solutions_data, solution_id)

        if not solution:
            return jsonify({"error": "Solution not found"}), 404
        if solution["status"] != "open":
            return jsonify({"error": f"Solution is '{solution['status']}', not 'open'"}), 400

        # Verify approval token
        token_hash = hashlib.sha256(approval_token.encode()).hexdigest()
        if token_hash != solution.get("approval_token_hash"):
            return jsonify({"error": "Invalid approval token"}), 403

        # Verify PR is merged and references issue
        issue_number = solution.get("github_issue")
        if not issue_number:
            return jsonify({"error": "No GitHub issue linked to this solution"}), 400

        valid, author, winner_wallet, pr_error = verify_pr_merged(pr_number, issue_number)
        if not valid:
            return jsonify({"error": f"PR verification failed: {pr_error}"}), 400
        if not winner_wallet:
            return jsonify({
                "error": "No wallet found in PR body. PR must contain 'Wallet: <solana-address>'"
            }), 400

        # Calculate payout
        budget = solution["budget_watt"]
        fee_amount = int(budget * FEE_PERCENT / 100)
        winner_amount = budget - fee_amount

        print(f"[SWARMSOLVE] Approving {solution_id}: {winner_amount:,} to {winner_wallet[:8]}..., fee {fee_amount:,}", flush=True)

        # Send winner payout directly from escrow wallet
        try:
            winner_tx = send_watt_from_escrow(
                winner_wallet, winner_amount,
                memo=f"swarmsolve:payout:{solution_id}"
            )
        except Exception as e:
            print(f"[SWARMSOLVE] Winner payment failed: {e}", flush=True)
            return jsonify({"error": f"Payment failed: {e}"}), 500

        # Send treasury fee from escrow wallet
        treasury_tx = None
        if fee_amount > 0 and TREASURY_WALLET:
            try:
                time.sleep(2)  # Brief delay between TXs
                treasury_tx = send_watt_from_escrow(
                    TREASURY_WALLET, fee_amount,
                    memo=f"swarmsolve:fee:{solution_id}"
                )
            except Exception as e:
                print(f"[SWARMSOLVE] Treasury fee failed (non-critical): {e}", flush=True)

        # Update solution record
        solution["status"] = "approved"
        solution["winner_pr"] = pr_number
        solution["winner_wallet"] = winner_wallet
        solution["winner_author"] = author
        solution["payout_tx"] = winner_tx
        solution["treasury_tx"] = treasury_tx
        solution["approved_at"] = datetime.utcnow().isoformat()
        save_solutions(solutions_data)

        # GitHub comment + close issue
        tx_link = f"https://solscan.io/tx/{winner_tx}"
        fee_line = f"\n**Fee TX:** [Solscan](https://solscan.io/tx/{treasury_tx})" if treasury_tx else "\n**Fee:** Pending manual transfer"
        post_issue_comment(issue_number,
            f"## ✅ Solution Approved — Paid\n\n"
            f"**Winner:** @{author} (PR #{pr_number})\n"
            f"**Payout:** {winner_amount:,} WATT\n"
            f"**TX:** [Solscan]({tx_link})\n"
            f"**Fee:** {fee_amount:,} WATT (5% treasury){fee_line}\n"
        )
        close_github_issue(issue_number)

        # Discord notification
        notify_discord(
            "Solution Approved — Payout Processing",
            f"**{solution['title']}**\n\nPR #{pr_number} by @{author} approved",
            color=0x00FF00,
            fields={
                "Winner": f"@{author}",
                "Payout": f"{winner_amount:,} WATT",
                "Fee": f"{fee_amount:,} WATT"
            }
        )

        return jsonify({
            "message": "Solution approved! Payment sent from escrow.",
            "solution_id": solution_id,
            "winner": author,
            "winner_wallet": mask_wallet(winner_wallet),
            "payout_watt": winner_amount,
            "payout_tx": winner_tx,
            "fee_watt": fee_amount,
            "treasury_tx": treasury_tx,
            "pr_number": pr_number
        }), 200

    except Exception as e:
        print(f"[SWARMSOLVE] Approve error: {e}", flush=True)
        return jsonify({"error": "Internal error"}), 500


@swarmsolve_bp.route('/api/v1/solutions/<solution_id>/refund', methods=['POST'])
def refund_solution(solution_id):
    """
    Admin-only: Refund escrow to customer (deadline expired, no winner).
    v1: Manual trigger. Cron auto-refund in v2.

    Body: { "admin_key": "<ADMIN_API_KEY env var>" }
    """
    try:
        data = request.get_json() or {}
        admin_key = data.get("admin_key", "")

        expected_key = os.getenv("ADMIN_API_KEY", "")
        if not expected_key or admin_key != expected_key:
            return jsonify({"error": "Unauthorized"}), 403

        solutions_data = load_solutions()
        solution = find_solution(solutions_data, solution_id)

        if not solution:
            return jsonify({"error": "Solution not found"}), 404
        if solution["status"] != "open":
            return jsonify({"error": f"Solution is '{solution['status']}', cannot refund"}), 400

        # Send refund directly from escrow wallet
        try:
            refund_tx = send_watt_from_escrow(
                solution["customer_wallet"], solution["budget_watt"],
                memo=f"swarmsolve:refund:{solution_id}"
            )
        except Exception as e:
            print(f"[SWARMSOLVE] Refund payment failed: {e}", flush=True)
            return jsonify({"error": f"Refund payment failed: {e}"}), 500

        print(f"[SWARMSOLVE] Refund sent: {solution['budget_watt']:,} WATT to {solution['customer_wallet'][:8]}...", flush=True)

        solution["status"] = "refunded"
        solution["refund_tx"] = refund_tx
        solution["refunded_at"] = datetime.utcnow().isoformat()
        save_solutions(solutions_data)

        # GitHub comment + close
        if solution.get("github_issue"):
            refund_link = f"https://solscan.io/tx/{refund_tx}"
            post_issue_comment(solution["github_issue"],
                f"## ✅ Escrow Refunded\n\n"
                f"No winner selected. {solution['budget_watt']:,} WATT returned to customer.\n"
                f"**TX:** [Solscan]({refund_link})"
            )
            close_github_issue(solution["github_issue"])

        notify_discord(
            "Solution Refunded",
            f"**{solution['title']}** — {solution['budget_watt']:,} WATT returned",
            color=0xFFA500,
            fields={"TX": f"[Solscan](https://solscan.io/tx/{refund_tx})"}
        )

        return jsonify({
            "message": "Refund sent from escrow",
            "solution_id": solution_id,
            "amount": solution["budget_watt"],
            "refund_tx": refund_tx
        }), 200

    except Exception as e:
        print(f"[SWARMSOLVE] Refund error: {e}", flush=True)
        return jsonify({"error": "Internal error"}), 500
