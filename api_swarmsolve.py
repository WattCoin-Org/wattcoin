"""
SwarmSolve Phase 1.5 — Escrow Bounty Marketplace v1.1.0

Endpoints:
    POST /api/v1/solutions/prepare     — Get slug + escrow instructions (step 1)
    POST /api/v1/solutions/submit      — Verify escrow TX + create GitHub issue (step 2)
    GET  /api/v1/solutions             — List solutions (filter by status)
    GET  /api/v1/solutions/<id>        — Get single solution (spec gated behind claim)
    POST /api/v1/solutions/<id>/claim  — Agent claims solution (GitHub verified, returns spec)
    POST /api/v1/solutions/<id>/approve — Customer approves winner (token auth)
    POST /api/v1/solutions/<id>/refund  — Admin refund (manual v1)

Flow:
    1. Customer calls /prepare with title -> gets slug, escrow wallet, memo format
    2. Customer sends WATT to escrow wallet with memo "swarmsolve:<slug>"
    3. Customer calls /submit with TX sig + full spec
    4. Backend verifies TX on-chain, creates GitHub issue with solution-bounty label
    5. Agents claim via /claim (GitHub account must be 30+ days old, 1+ public repos)
    6. Claimed agents get full spec, compete — first merged PR wins
    7. Customer calls /approve with approval_token + pr_number
    8. Backend releases 95% to winner from escrow, 5% to treasury
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

from pr_security import load_json_data, save_json_data, is_banned

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

# Claim system
MAX_CLAIMS_PER_SOLUTION = 5   # max agents claiming one solution
MAX_ACTIVE_CLAIMS_PER_AGENT = 3  # max open claims per agent wallet
MIN_GITHUB_ACCOUNT_AGE_DAYS = 30
MIN_GITHUB_PUBLIC_REPOS = 1

ESCROW_WALLET = os.getenv("ESCROW_WALLET_ADDRESS", "")
ESCROW_WALLET_PRIVATE_KEY = os.getenv("ESCROW_WALLET_PRIVATE_KEY", "")
TREASURY_WALLET = os.getenv("TREASURY_WALLET_ADDRESS", "")
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN", "")
AI_API_KEY = os.getenv("AI_REVIEW_API_KEY", "")
AI_API_URL = os.getenv("AI_REVIEW_API_URL", "")
AI_MODEL = os.getenv("AI_REVIEW_MODEL", "")
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

    # Look up sender ATA via RPC (with fallback to derived ATA)
    sender_resp = requests.post(SOLANA_RPC, json={
        "jsonrpc": "2.0", "id": 1,
        "method": "getTokenAccountsByOwner",
        "params": [str(from_pubkey), {"mint": WATT_MINT}, {"encoding": "jsonParsed"}]
    }, timeout=10).json()

    if "result" in sender_resp and sender_resp["result"]["value"]:
        sender_ata = Pubkey.from_string(sender_resp["result"]["value"][0]["pubkey"])
    else:
        # Fallback: derive ATA (handles RPC rate-limiting)
        print(f"[ESCROW] RPC lookup empty for sender, using derived ATA", flush=True)
        sender_ata = get_associated_token_address(
            from_pubkey, mint, token_program_id=TOKEN_2022_PROGRAM_ID
        )

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
# CLAIM SYSTEM — GitHub Account Verification
# =============================================================================

def verify_github_account(github_user):
    """
    Verify GitHub account meets trust requirements.
    Returns: (passed: bool, reason: str or None, account_info: dict or None)
    """
    try:
        resp = requests.get(
            f"https://api.github.com/users/{github_user}",
            headers=_gh_headers(),
            timeout=10
        )
        if resp.status_code == 404:
            return False, f"GitHub user '{github_user}' not found", None
        if resp.status_code != 200:
            return False, f"Cannot verify GitHub user: HTTP {resp.status_code}", None

        user_data = resp.json()
        created_str = user_data.get("created_at", "")
        public_repos = user_data.get("public_repos", 0)
        account_type = user_data.get("type", "User")

        # Parse account age
        from datetime import timezone
        created_dt = datetime.strptime(created_str, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
        now = datetime.now(timezone.utc)
        age_days = (now - created_dt).days

        info = {
            "github_user": github_user,
            "account_age_days": age_days,
            "public_repos": public_repos,
            "followers": user_data.get("followers", 0),
            "type": account_type,
            "created_at": created_str
        }

        # Check minimum account age
        if age_days < MIN_GITHUB_ACCOUNT_AGE_DAYS:
            return False, (
                f"GitHub account too new ({age_days} days). "
                f"Minimum {MIN_GITHUB_ACCOUNT_AGE_DAYS} days required. "
                f"Try regular bounties first, then come back for SwarmSolve."
            ), info

        # Check minimum repos
        if public_repos < MIN_GITHUB_PUBLIC_REPOS:
            return False, (
                f"GitHub account has {public_repos} public repos. "
                f"Minimum {MIN_GITHUB_PUBLIC_REPOS} required."
            ), info

        return True, None, info

    except Exception as e:
        # Fail open for network errors — don't block claims due to GitHub API issues
        print(f"[SWARMSOLVE] GitHub verification error for {github_user}: {e}", flush=True)
        return True, None, {"github_user": github_user, "verification_error": str(e)}


def count_active_claims_for_agent(solutions_data, wallet):
    """Count how many open solutions this agent wallet has claimed."""
    count = 0
    for solution in solutions_data.get("solutions", []):
        if solution.get("status") != "open":
            continue
        for claim in solution.get("claims", []):
            if claim.get("wallet") == wallet:
                count += 1
    return count


def is_wallet_claimed(solution, wallet):
    """Check if wallet already claimed this solution."""
    return any(c.get("wallet") == wallet for c in solution.get("claims", []))


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
    Create GitHub issue for solution bounty — PUBLIC LISTING ONLY.
    No detailed spec posted. Agents go to target_repo for full details.
    Returns: (issue_number, issue_url) or (None, None) on failure.
    """
    issue_num_placeholder = "{TBD}"
    target_repo = solution.get("target_repo", REPO)
    is_external = target_repo != REPO
    target_repo_url = f"https://github.com/{target_repo}"

    title = f"[SOLUTION: {solution['budget_watt']:,} WATT] {solution['title']}"

    if is_external:
        delivery_section = f"""## Delivery Repo

**[{target_repo}]({target_repo_url})**

Full specification and implementation details are in the target repo.
Submit your PR to the target repo — NOT to this repo.
"""
    else:
        delivery_section = """## Delivery

Submit your PR to this repo referencing this issue.
"""

    body = f"""## SwarmSolve Solution Request

**Budget:** {solution['budget_watt']:,} WATT (escrowed)
**Deadline:** {solution['deadline_days']} days ({solution['deadline_date']})
**Solution ID:** `{solution['id']}`

---

{delivery_section}

## How to Claim

1. Call `POST /api/v1/solutions/{solution['id']}/claim` with your wallet + GitHub username to get the full spec
2. Review the spec and plan your implementation
3. Submit a PR {'to `' + target_repo + '`' if is_external else ''} referencing this issue (include `#{issue_num_placeholder}` in PR body)
4. Include your Solana wallet in PR body: `Wallet: <your-address>`
5. AI review + customer approval required
6. First approved PR wins — **{int(solution['budget_watt'] * (100 - FEE_PERCENT) / 100):,} WATT** (95%) released to winner

**Requirements:** GitHub account must be 30+ days old with 1+ public repos.

## Auto-Reject
- PRs not referencing this issue
- PRs over scope (stick to the spec)
- Bundled with other bounties/solutions

## Escrow Proof
[View escrow TX on Solscan](https://solscan.io/tx/{solution['escrow_tx']})

---

> ⚠️ **Privacy Notice:** WattCoin does not guarantee confidentiality of any information
> posted in public repositories. Do not include proprietary details in PR descriptions
> or comments on this issue.

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


def verify_pr_merged(pr_number, issue_number, target_repo=None):
    """
    Check if PR is merged and references the solution issue.
    Checks PR on target_repo (customer's repo) or default WattCoin repo.
    Returns: (valid: bool, author: str or None, winner_wallet: str or None, error: str or None)
    """
    check_repo = target_repo or REPO
    try:
        resp = requests.get(
            f"https://api.github.com/repos/{check_repo}/pulls/{pr_number}",
            headers=_gh_headers(),
            timeout=15
        )
        if resp.status_code == 404:
            return False, None, None, f"PR #{pr_number} not found on {check_repo}"
        if resp.status_code != 200:
            return False, None, None, f"Cannot access {check_repo}: HTTP {resp.status_code}"

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

def safety_scan_pr(pr_number, target_repo):
    """
    Fetch PR diff from target repo and run AI safety scan.
    Returns: (passed: bool, report: str, scan_ran: bool)
    - passed=True, scan_ran=True: code is safe, proceed
    - passed=False, scan_ran=True: flagged, block payment
    - passed=False, scan_ran=False: scan couldn't run, block payment (admin override needed)
    """
    if not AI_API_KEY:
        print("[SWARMSOLVE] AI_API_KEY not set — BLOCKING (scan required)", flush=True)
        return False, "Safety scan unavailable: AI audit service not configured. Admin override required.", False

    check_repo = target_repo or REPO

    # Fetch PR diff
    try:
        diff_resp = requests.get(
            f"https://api.github.com/repos/{check_repo}/pulls/{pr_number}",
            headers={**_gh_headers(), "Accept": "application/vnd.github.v3.diff"},
            timeout=30
        )
        if diff_resp.status_code != 200:
            print(f"[SWARMSOLVE] Failed to fetch diff: {diff_resp.status_code}", flush=True)
            return False, f"Safety scan unavailable: could not fetch PR diff (HTTP {diff_resp.status_code}). Try again or admin override.", False

        diff_text = diff_resp.text
        if len(diff_text) > 15000:
            diff_text = diff_text[:15000] + "\n... [TRUNCATED — diff too large] ..."
    except Exception as e:
        print(f"[SWARMSOLVE] Diff fetch error: {e}", flush=True)
        return False, f"Safety scan unavailable: diff fetch error ({e}). Try again or admin override.", False

    # Safety scan prompt
    prompt = f"""You are a code security auditor for SwarmSolve, a paid software delivery marketplace where customers pay WATT tokens for custom development. Code that passes this audit will be delivered to a paying customer. Stakes are high — malicious code harms both the customer AND the WattCoin platform's reputation.

This is a SAFETY-ONLY review — not code quality. The customer evaluates quality themselves.

PR #{pr_number} on {check_repo}

DIFF:
```
{diff_text}
```

SCAN DIMENSIONS (evaluate each explicitly):

1. **Malware & Backdoors** (CRITICAL)
   Reverse shells, keyloggers, unauthorized network connections, persistence mechanisms.

2. **Credential Theft** (CRITICAL)
   Code that harvests API keys, tokens, passwords, or environment variables from the customer's environment.

3. **Cryptocurrency Theft** (CRITICAL)
   Unauthorized wallet operations, address swapping, hidden mining, transaction manipulation.

4. **Data Exfiltration** (CRITICAL — elevated for customer delivery)
   Any code that sends customer data, configs, or operational info to external servers. This includes analytics, telemetry, or "phone home" functionality not specified in the project requirements.

5. **Supply Chain Attack** (HIGH)
   Typosquatted packages, suspicious dependencies, modified build scripts, post-install scripts with network access.

6. **Obfuscation** (HIGH)
   Base64-encoded payloads, eval() abuse, dynamic code execution, minified code that hides functionality.

7. **Copyright Violation** (MEDIUM)
   Obviously copied proprietary code, DMCA-infringing content, license violations.

8. **Hidden Functionality** (MEDIUM)
   Features not described in the project spec that could surprise the customer — time bombs, conditional triggers, easter eggs with network access.

Be strict — if in doubt, FAIL. The customer is paying real money for this code.
Only PASS if the code is clearly safe for customer deployment across ALL dimensions.

Respond ONLY with valid JSON:
{{
  "verdict": "PASS",
  "risk_level": "NONE",
  "confidence": "HIGH",
  "dimensions": {{
    "malware": {{"safe": true, "reasoning": "...", "flagged_lines": []}},
    "credential_theft": {{"safe": true, "reasoning": "...", "flagged_lines": []}},
    "crypto_theft": {{"safe": true, "reasoning": "...", "flagged_lines": []}},
    "data_exfiltration": {{"safe": true, "reasoning": "...", "flagged_lines": []}},
    "supply_chain": {{"safe": true, "reasoning": "...", "flagged_lines": []}},
    "obfuscation": {{"safe": true, "reasoning": "...", "flagged_lines": []}},
    "copyright": {{"safe": true, "reasoning": "...", "flagged_lines": []}},
    "hidden_functionality": {{"safe": true, "reasoning": "...", "flagged_lines": []}}
  }},
  "summary": "One sentence explanation",
  "flags": []
}}

Do not include any text before or after the JSON."""

    try:
        from ai_provider import call_ai
        report, ai_error = call_ai(prompt, temperature=0.1, max_tokens=1500, timeout=60)

        if ai_error:
            print(f"[SWARMSOLVE] AI API error: {ai_error}", flush=True)
            return False, f"Safety scan unavailable: AI audit service error ({ai_error}). Service may be temporarily unavailable. Try again or admin override.", False

        print(f"[SWARMSOLVE] Safety scan result: {report[:200]}...", flush=True)
        
        # Save evaluation (non-blocking)
        try:
            from eval_logger import save_evaluation
            save_evaluation("swarmsolve_audit", report, {
                "pr_number": pr_number,
                "target_repo": target_repo or REPO,
            })
        except Exception:
            pass

        # --- Parse: JSON-first, legacy fallback ---
        verdict_pass = None

        try:
            json_text = report.strip()
            if json_text.startswith("```"):
                json_text = json_text.split("\n", 1)[1] if "\n" in json_text else json_text[3:]
                if json_text.endswith("```"):
                    json_text = json_text[:-3]
                json_text = json_text.strip()

            parsed = json.loads(json_text)
            verdict_str = parsed.get("verdict", "").upper()
            risk_str = parsed.get("risk_level", "").upper()

            if "FAIL" in verdict_str or risk_str in ("CRITICAL", "HIGH"):
                verdict_pass = False
            elif "PASS" in verdict_str:
                verdict_pass = True

        except (json.JSONDecodeError, ValueError, AttributeError):
            # Legacy fallback: parse VERDICT:/RISK_LEVEL: lines
            verdict_line = [l for l in report.split("\n") if l.strip().startswith("VERDICT:")]
            if verdict_line:
                verdict = verdict_line[0].split(":", 1)[1].strip().upper()
                if "FAIL" in verdict:
                    verdict_pass = False
                elif "PASS" in verdict:
                    verdict_pass = True

            risk_line = [l for l in report.split("\n") if l.strip().startswith("RISK_LEVEL:")]
            if risk_line:
                risk = risk_line[0].split(":", 1)[1].strip().upper()
                if risk in ("CRITICAL", "HIGH"):
                    verdict_pass = False

        if verdict_pass is False:
            return False, report, True

        return True, report, True

    except Exception as e:
        print(f"[SWARMSOLVE] Safety scan error: {e}", flush=True)
        return False, f"Safety scan unavailable: {e}. Try again or admin override.", False


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
            "privacy_warning": (
                "Any information included in your submission title and public description "
                "will be visible on GitHub. WattCoin does not guarantee confidentiality of "
                "solution specs. Do NOT include proprietary algorithms, credentials, or trade "
                "secrets in your submission. Use your target repo's private issues or README "
                "for sensitive implementation details."
            ),
            "instructions": [
                f"1. Send WATT to {ESCROW_WALLET} with memo: swarmsolve:{slug}",
                "2. Call POST /api/v1/solutions/submit with TX signature and spec",
                "3. Include 'target_repo' (your GitHub repo where agents will PR solutions)",
                "4. Include 'privacy_acknowledged': true to confirm you understand the privacy policy",
                "5. Save the approval_token from the response — needed to approve winner or request refund"
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
        description: str — detailed spec (kept private, NOT posted to public issue)
        budget_watt: int — amount sent (min 5,000)
        escrow_tx: str — Solana TX signature
        customer_wallet: str — sender's wallet
        target_repo: str — GitHub repo for delivery (e.g. 'owner/repo'), optional
        privacy_acknowledged: bool — must be true
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
        target_repo = (data.get("target_repo") or "").strip()
        privacy_acknowledged = data.get("privacy_acknowledged", False)
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
        if not privacy_acknowledged:
            errors.append("privacy_acknowledged: must be true — review privacy_warning from /prepare")

        # Validate target_repo format if provided
        if target_repo:
            if "/" not in target_repo or len(target_repo.split("/")) != 2:
                errors.append("target_repo: must be 'owner/repo' format (e.g. 'myorg/my-project')")

        if errors:
            return jsonify({"error": "Validation failed", "details": errors}), 400

        # Verify target_repo is accessible (if provided)
        if target_repo:
            try:
                repo_resp = requests.get(
                    f"https://api.github.com/repos/{target_repo}/pulls?state=all&per_page=1",
                    headers=_gh_headers(),
                    timeout=15
                )
                if repo_resp.status_code == 404:
                    return jsonify({
                        "error": f"Target repo '{target_repo}' not found or not accessible",
                        "hint": "Make the repo public, or invite 'WattCoin-Org' as a collaborator with read access"
                    }), 400
                elif repo_resp.status_code == 403:
                    return jsonify({
                        "error": f"No access to '{target_repo}'",
                        "hint": "Invite 'WattCoin-Org' as a collaborator with read access, then resubmit"
                    }), 400
                elif repo_resp.status_code not in (200, 304):
                    return jsonify({
                        "error": f"Cannot verify target repo: HTTP {repo_resp.status_code}"
                    }), 400
                print(f"[SWARMSOLVE] Target repo '{target_repo}' verified accessible", flush=True)
            except Exception as e:
                return jsonify({"error": f"Failed to verify target repo: {e}"}), 400
        else:
            # Default to WattCoin repo for internal bounties
            target_repo = REPO

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
            "target_repo": target_repo,
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
            "claims": [],
            "created_at": datetime.utcnow().isoformat(),
            "approved_at": None,
            "refunded_at": None
        }

        # Create GitHub issue (public listing only — no spec details)
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
                "Target Repo": target_repo,
                "Escrow TX": f"[Solscan](https://solscan.io/tx/{escrow_tx})",
                "Issue": f"[#{issue_number}]({issue_url})" if issue_number else "N/A"
            }
        )

        print(f"[SWARMSOLVE] Solution {solution_id} created: {title} ({budget_watt:,} WATT) -> {target_repo}", flush=True)

        return jsonify({
            "solution_id": solution_id,
            "slug": slug,
            "approval_token": approval_token,
            "github_issue": issue_number,
            "github_issue_url": issue_url,
            "escrow_wallet": ESCROW_WALLET,
            "target_repo": target_repo,
            "budget_watt": budget_watt,
            "deadline_date": deadline_date,
            "message": "Solution created! Save your approval_token — needed to approve the winner or request a refund.",
            "warning": "Do NOT share your approval_token publicly."
        }), 201

    except Exception as e:
        print(f"[SWARMSOLVE] Submit error: {e}", flush=True)
        return jsonify({"error": "Internal error"}), 500


def auto_expire_solutions(solutions_data):
    """
    Auto-expire open solutions past their deadline.
    Refunds escrowed WATT to customer wallet, closes GitHub issue, notifies Discord.
    Runs lazily on list/get endpoints.
    """
    solutions = solutions_data.get("solutions", [])
    now = datetime.utcnow()
    expired_count = 0

    for solution in solutions:
        if solution.get("status") != "open":
            continue

        deadline_str = solution.get("deadline_date", "")
        if not deadline_str:
            continue

        try:
            deadline_dt = datetime.strptime(deadline_str, "%Y-%m-%d")
        except (ValueError, TypeError):
            continue

        if now < deadline_dt:
            continue

        # Past deadline — auto-refund
        solution_id = solution["id"]
        print(f"[SWARMSOLVE] Auto-expiring {solution_id} — deadline {deadline_str} passed", flush=True)

        try:
            refund_tx = send_watt_from_escrow(
                solution["customer_wallet"], solution["budget_watt"],
                memo=f"swarmsolve:expired:{solution_id}"
            )

            solution["status"] = "expired"
            solution["refund_tx"] = refund_tx
            solution["refunded_at"] = now.isoformat()
            solution["expiration_note"] = f"Auto-expired: deadline {deadline_str} passed with no approved PR"
            expired_count += 1

            print(f"[SWARMSOLVE] Auto-refund sent: {solution['budget_watt']:,} WATT to {solution['customer_wallet'][:8]}... TX: {refund_tx[:12]}...", flush=True)

            # GitHub comment + close
            if solution.get("github_issue"):
                refund_link = f"https://solscan.io/tx/{refund_tx}"
                post_issue_comment(solution["github_issue"],
                    f"## ⏰ Deadline Expired — Escrow Refunded\n\n"
                    f"No approved solution by deadline ({deadline_str}). "
                    f"{solution['budget_watt']:,} WATT returned to customer.\n"
                    f"**TX:** [Solscan]({refund_link})"
                )
                close_github_issue(solution["github_issue"])

            notify_discord(
                "Solution Expired — Auto-Refund",
                f"**{solution['title']}** — {solution['budget_watt']:,} WATT returned to customer",
                color=0xFF6600,
                fields={"Deadline": deadline_str, "TX": f"[Solscan](https://solscan.io/tx/{refund_tx})"}
            )

        except Exception as e:
            print(f"[SWARMSOLVE] Auto-expire refund failed for {solution_id}: {e}", flush=True)
            # Mark as expired but note the refund failure — admin can retry manually
            solution["status"] = "expired"
            solution["expiration_note"] = f"Auto-expired but refund FAILED: {e}"
            expired_count += 1

            notify_discord(
                "⚠️ Auto-Expire Refund FAILED",
                f"**{solution['title']}** — {solution['budget_watt']:,} WATT refund failed!",
                color=0xFF0000,
                fields={"Error": str(e)[:200], "Solution ID": solution_id}
            )

    if expired_count > 0:
        save_solutions(solutions_data)
        print(f"[SWARMSOLVE] Auto-expired {expired_count} solutions", flush=True)

    return expired_count


@swarmsolve_bp.route('/api/v1/solutions', methods=['GET'])
def list_solutions():
    """List solutions with optional ?status=open|approved|refunded|expired filter."""
    try:
        status_filter = request.args.get("status", "").lower()
        solutions_data = load_solutions()

        # Auto-expire past-deadline solutions
        auto_expire_solutions(solutions_data)

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
            "customer_wallet": mask_wallet(s.get("customer_wallet")),
            "claim_count": len(s.get("claims", [])),
            "max_claims": MAX_CLAIMS_PER_SOLUTION
        } for s in solutions]

        return jsonify({"solutions": public, "count": len(public)}), 200

    except Exception as e:
        print(f"[SWARMSOLVE] List error: {e}", flush=True)
        return jsonify({"error": "Internal error"}), 500


@swarmsolve_bp.route('/api/v1/solutions/<solution_id>', methods=['GET'])
def get_solution(solution_id):
    """
    Get single solution details.
    Description (full spec) only visible if requester provides a claimed wallet via ?wallet= param.
    Without wallet or unclaimed wallet, description is replaced with a notice.
    """
    try:
        solutions_data = load_solutions()
        solution = find_solution(solutions_data, solution_id)

        if not solution:
            return jsonify({"error": "Solution not found"}), 404

        # Check if requester has claimed this solution
        requester_wallet = (request.args.get("wallet") or "").strip()
        has_claimed = is_wallet_claimed(solution, requester_wallet) if requester_wallet else False

        # Also allow customer to see their own spec
        is_customer = False
        approval_token = (request.args.get("approval_token") or "").strip()
        if approval_token:
            token_hash = hashlib.sha256(approval_token.encode()).hexdigest()
            is_customer = token_hash == solution.get("approval_token_hash")

        if has_claimed or is_customer:
            description = solution["description"]
        else:
            description = (
                "🔒 Full spec hidden. Claim this solution first via "
                "POST /api/v1/solutions/{id}/claim to access the detailed specification."
            )

        claims = solution.get("claims", [])
        claim_count = len(claims)

        return jsonify({
            "id": solution["id"],
            "title": solution["title"],
            "description": description,
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
            "customer_wallet": mask_wallet(solution.get("customer_wallet")),
            "claim_count": claim_count,
            "max_claims": MAX_CLAIMS_PER_SOLUTION,
            "claimed": has_claimed
        }), 200

    except Exception as e:
        print(f"[SWARMSOLVE] Get error: {e}", flush=True)
        return jsonify({"error": "Internal error"}), 500


@swarmsolve_bp.route('/api/v1/solutions/<solution_id>/claim', methods=['POST'])
def claim_solution(solution_id):
    """
    Agent claims a solution to get access to the full spec.
    Requires GitHub account verification (min 30 days old, min 1 public repo).

    Body:
        wallet: str — agent's Solana wallet
        github_user: str — agent's GitHub username
    Returns:
        Full description (spec) + claim confirmation
    """
    try:
        data = request.get_json()
        if not data:
            return jsonify({"error": "JSON body required"}), 400

        wallet = (data.get("wallet") or "").strip()
        github_user = (data.get("github_user") or "").strip()

        if not wallet or len(wallet) < 32:
            return jsonify({"error": "Valid Solana wallet address required"}), 400
        if not github_user:
            return jsonify({"error": "github_user required"}), 400

        # Find solution
        solutions_data = load_solutions()
        solution = find_solution(solutions_data, solution_id)

        if not solution:
            return jsonify({"error": "Solution not found"}), 404
        if solution["status"] != "open":
            return jsonify({"error": f"Solution is '{solution['status']}', not open for claims"}), 400

        # Check if already claimed by this wallet
        if is_wallet_claimed(solution, wallet):
            # Return spec again (idempotent)
            return jsonify({
                "message": "Already claimed — here is the full spec",
                "solution_id": solution_id,
                "description": solution["description"],
                "target_repo": solution.get("target_repo"),
                "deadline_date": solution.get("deadline_date"),
                "budget_watt": solution["budget_watt"],
                "already_claimed": True
            }), 200

        # Check max claims per solution
        claims = solution.get("claims", [])
        if len(claims) >= MAX_CLAIMS_PER_SOLUTION:
            return jsonify({
                "error": f"Maximum claims reached ({MAX_CLAIMS_PER_SOLUTION}). Solution is fully claimed.",
                "claim_count": len(claims),
                "max_claims": MAX_CLAIMS_PER_SOLUTION
            }), 400

        # Check max active claims per agent
        active_claims = count_active_claims_for_agent(solutions_data, wallet)
        if active_claims >= MAX_ACTIVE_CLAIMS_PER_AGENT:
            return jsonify({
                "error": f"You have {active_claims} active claims (max {MAX_ACTIVE_CLAIMS_PER_AGENT}). "
                         f"Complete or wait for existing claims to close before claiming more.",
                "active_claims": active_claims,
                "max_active_claims": MAX_ACTIVE_CLAIMS_PER_AGENT
            }), 400

        # Check ban list (unified — includes PERMANENT_BANS + banned_users.json)
        if is_banned(github_user):
            return jsonify({"error": "Account is restricted from SwarmSolve"}), 403

        # Verify GitHub account trust
        gh_passed, gh_reason, gh_info = verify_github_account(github_user)
        if not gh_passed:
            print(f"[SWARMSOLVE] Claim rejected for {github_user}: {gh_reason}", flush=True)
            return jsonify({
                "error": "GitHub account does not meet requirements",
                "reason": gh_reason,
                "requirements": {
                    "min_account_age_days": MIN_GITHUB_ACCOUNT_AGE_DAYS,
                    "min_public_repos": MIN_GITHUB_PUBLIC_REPOS
                }
            }), 403

        # Record claim
        claim = {
            "wallet": wallet,
            "github_user": github_user,
            "claimed_at": datetime.utcnow().isoformat(),
            "account_age_days": gh_info.get("account_age_days") if gh_info else None
        }
        solution.setdefault("claims", []).append(claim)
        save_solutions(solutions_data)

        print(f"[SWARMSOLVE] Claim recorded: {github_user} ({wallet[:8]}...) on {solution_id}", flush=True)

        # GitHub comment
        if solution.get("github_issue"):
            post_issue_comment(solution["github_issue"],
                f"🔒 **@{github_user}** claimed this solution ({len(solution['claims'])}/{MAX_CLAIMS_PER_SOLUTION} slots)"
            )

        # Discord notification
        notify_discord(
            "Solution Claimed",
            f"**{solution['title']}**\n\n@{github_user} claimed solution `{solution_id}`",
            color=0x00BFFF,
            fields={
                "Claims": f"{len(solution['claims'])}/{MAX_CLAIMS_PER_SOLUTION}",
                "Agent": f"@{github_user}",
                "Account Age": f"{gh_info.get('account_age_days', '?')} days" if gh_info else "N/A"
            }
        )

        return jsonify({
            "message": "Claimed! Full spec below. Good luck.",
            "solution_id": solution_id,
            "description": solution["description"],
            "target_repo": solution.get("target_repo"),
            "deadline_date": solution.get("deadline_date"),
            "budget_watt": solution["budget_watt"],
            "claim_count": len(solution["claims"]),
            "max_claims": MAX_CLAIMS_PER_SOLUTION,
            "github_requirements": "Submit PR to target repo referencing the issue. Include your wallet in PR body."
        }), 200

    except Exception as e:
        print(f"[SWARMSOLVE] Claim error: {e}", flush=True)
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

        valid, author, winner_wallet, pr_error = verify_pr_merged(
            pr_number, issue_number, target_repo=solution.get("target_repo")
        )
        if not valid:
            return jsonify({"error": f"PR verification failed: {pr_error}"}), 400
        if not winner_wallet:
            return jsonify({
                "error": "No wallet found in PR body. PR must contain 'Wallet: <solana-address>'"
            }), 400

        # Safety scan — fetch diff and run through AI audit
        target_repo = solution.get("target_repo", REPO)

        # Admin can skip scan if AI service is down
        admin_key = (data.get("admin_key") or "").strip()
        skip_scan = data.get("skip_scan", False)
        expected_admin = os.getenv("ADMIN_API_KEY", "")
        is_admin = bool(expected_admin and admin_key == expected_admin)

        if skip_scan and is_admin:
            scan_passed, scan_report, scan_ran = True, "Scan skipped by admin override", False
            print(f"[SWARMSOLVE] Safety scan SKIPPED by admin override for {solution_id}", flush=True)
        else:
            scan_passed, scan_report, scan_ran = safety_scan_pr(pr_number, target_repo)

        if not scan_passed:
            # Determine if it's a security flag or scan unavailable
            status_code = 403 if scan_ran else 503
            error_msg = "Safety scan failed — payment blocked" if scan_ran else "Safety scan unavailable — payment blocked"

            notify_discord(
                f"⚠️ {'Safety Scan FAILED' if scan_ran else 'Safety Scan UNAVAILABLE'} — Payment Blocked",
                f"**{solution['title']}**\n\nPR #{pr_number} by @{author}" +
                (f"\n\n**Reason:** {scan_report[:200]}" if not scan_ran else ""),
                color=0xFF0000,
                fields={
                    "Solution ID": solution_id,
                    "Target Repo": target_repo,
                    "PR": f"#{pr_number}",
                    "Type": "Security flag" if scan_ran else "Scan unavailable (AI audit service down?)"
                }
            )
            return jsonify({
                "error": error_msg,
                "scan_report": scan_report,
                "scan_ran": scan_ran,
                "hint": "Admin can override with admin_key + skip_scan:true if scan is unavailable." if not scan_ran
                        else "The PR was flagged for potential security issues. Contact the team if you believe this is a false positive."
            }), status_code

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
        treasury_error = None
        if fee_amount > 0 and TREASURY_WALLET:
            try:
                time.sleep(5)  # Delay between TXs to avoid RPC rate-limiting
                treasury_tx = send_watt_from_escrow(
                    TREASURY_WALLET, fee_amount,
                    memo=f"swarmsolve:fee:{solution_id}"
                )
            except Exception as e:
                treasury_error = str(e)
                print(f"[SWARMSOLVE] Treasury fee failed (non-critical): {e}", flush=True)
        elif not TREASURY_WALLET:
            treasury_error = "TREASURY_WALLET_ADDRESS env var not set"
            print(f"[SWARMSOLVE] {treasury_error}", flush=True)

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
            "safety_scan": "passed",
            "pr_number": pr_number
        }), 200

    except Exception as e:
        print(f"[SWARMSOLVE] Approve error: {e}", flush=True)
        return jsonify({"error": "Internal error"}), 500


@swarmsolve_bp.route('/api/v1/solutions/<solution_id>/refund', methods=['POST'])
def refund_solution(solution_id):
    """
    Customer requests refund of escrowed WATT.

    Refund rules (Option 3):
    - Before any PR submitted to target repo: refund anytime
    - After a PR exists: refund only after deadline expires
    - Admin can always force refund via admin_key

    Body: { "approval_token": "<token from /submit>" }
    Alt:  { "admin_key": "<ADMIN_API_KEY>" }
    """
    try:
        data = request.get_json() or {}

        solutions_data = load_solutions()
        solution = find_solution(solutions_data, solution_id)

        if not solution:
            return jsonify({"error": "Solution not found"}), 404
        if solution["status"] != "open":
            return jsonify({"error": f"Solution is '{solution['status']}', cannot refund"}), 400

        # Auth: approval_token OR admin_key
        approval_token = (data.get("approval_token") or "").strip()
        admin_key = (data.get("admin_key") or "").strip()
        expected_admin = os.getenv("ADMIN_API_KEY", "")

        is_admin = bool(expected_admin and admin_key == expected_admin)
        is_customer = False

        if approval_token:
            token_hash = hashlib.sha256(approval_token.encode()).hexdigest()
            is_customer = token_hash == solution.get("approval_token_hash")

        if not is_admin and not is_customer:
            return jsonify({"error": "Unauthorized — provide approval_token or admin_key"}), 403

        # Check refund eligibility (Option 3) — admin bypasses
        if not is_admin:
            target_repo = solution.get("target_repo", REPO)
            issue_number = solution.get("github_issue")
            deadline_str = solution.get("deadline_date", "")

            # Check if any PR references this issue on target repo
            has_active_pr = False
            if issue_number:
                try:
                    pr_resp = requests.get(
                        f"https://api.github.com/repos/{target_repo}/pulls?state=all&per_page=50",
                        headers=_gh_headers(),
                        timeout=15
                    )
                    if pr_resp.status_code == 200:
                        for pr in pr_resp.json():
                            body = pr.get("body", "") or ""
                            if f"#{issue_number}" in body:
                                has_active_pr = True
                                break
                except Exception as e:
                    print(f"[SWARMSOLVE] PR check error during refund: {e}", flush=True)

            if has_active_pr:
                # Check if deadline has passed
                if deadline_str:
                    deadline_dt = datetime.strptime(deadline_str, "%Y-%m-%d")
                    if datetime.utcnow() < deadline_dt:
                        days_left = (deadline_dt - datetime.utcnow()).days
                        return jsonify({
                            "error": "Refund locked — active PR exists",
                            "reason": f"A PR referencing this solution exists on {target_repo}. "
                                      f"Refund available after deadline ({deadline_str}, {days_left} days remaining).",
                            "deadline": deadline_str
                        }), 400

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


# =============================================================================
# ADMIN: ARCHIVE/DELETE SOLUTIONS
# =============================================================================

@swarmsolve_bp.route('/api/v1/solutions/archive', methods=['POST'])
def archive_solutions():
    """
    Admin-only: Archive (remove) solutions from the list.
    
    Body: { "admin_key": "<key>", "solution_ids": ["id1", "id2"] }
    Or:   { "admin_key": "<key>", "archive_completed": true }  — archives all non-open
    """
    data = request.get_json() or {}
    admin_key = (data.get("admin_key") or "").strip()
    expected_admin = os.getenv("ADMIN_API_KEY", "").strip()

    if not expected_admin or admin_key != expected_admin:
        return jsonify({"error": "Unauthorized — admin_key required"}), 403

    solutions_data = load_solutions()
    solutions = solutions_data.get("solutions", [])
    original_count = len(solutions)

    solution_ids = data.get("solution_ids", [])
    archive_completed = data.get("archive_completed", False)

    if solution_ids:
        # Archive specific IDs
        archived = [s["id"] for s in solutions if s["id"] in solution_ids]
        solutions = [s for s in solutions if s["id"] not in solution_ids]
    elif archive_completed:
        # Archive all non-open solutions
        archived = [s["id"] for s in solutions if s["status"] != "open"]
        solutions = [s for s in solutions if s["status"] == "open"]
    else:
        return jsonify({"error": "Provide solution_ids or archive_completed:true"}), 400

    solutions_data["solutions"] = solutions
    save_solutions(solutions_data)

    print(f"[SWARMSOLVE] Archived {len(archived)} solutions (admin)", flush=True)

    return jsonify({
        "message": f"Archived {len(archived)} solutions",
        "archived": archived,
        "remaining": len(solutions)
    }), 200


