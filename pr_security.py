"""
WattCoin PR Security Module v1.1.0
Handles validation, rate limiting, code scanning, and unified ban system.
Used by: api_webhooks.py, api_swarmsolve.py, api_tasks.py
"""

import os
import re
import json
import time
import base58
from datetime import datetime, timedelta

# =============================================================================
# CONFIG
# =============================================================================

DATA_DIR = "data"
RATE_LIMIT_FILE = f"{DATA_DIR}/pr_rate_limits.json"
SECURITY_LOG_FILE = f"{DATA_DIR}/security_logs.json"

# Rate limits
MAX_PRS_PER_DAY = 100
PAYOUT_COOLDOWN_HOURS = 24

# Emergency controls (env vars)
PAUSE_PR_PAYOUTS = os.getenv("PAUSE_PR_PAYOUTS", "false").lower() == "true"
PAUSE_PR_REVIEWS = os.getenv("PAUSE_PR_REVIEWS", "false").lower() == "true"
REQUIRE_DOUBLE_APPROVAL = os.getenv("REQUIRE_DOUBLE_APPROVAL", "false").lower() == "true"

# Dangerous code patterns (case insensitive)
DANGEROUS_PATTERNS = [
    r'subprocess\.',
    r'os\.system',
    r'eval\(',
    r'exec\(',
    r'__import__',
    r'private_key',
    r'PRIVATE_KEY',
    r'secret_key',
    r'SECRET_KEY',
    r'send_sol',
    r'transfer_sol',
    r'base58\.b58decode.*private',
    r'Keypair\.from_bytes',
    r'rm -rf',
    r'DROP TABLE',
    r'DELETE FROM',
]

# =============================================================================
# UNIFIED BAN SYSTEM (v1.1.0)
# Single source of truth for all ban checks across PR, SwarmSolve, and Tasks.
# Combines hardcoded PERMANENT_BANS + dynamic banned_users.json.
# =============================================================================

BANNED_USERS_FILE = f"{DATA_DIR}/banned_users.json"

# Hardcoded permanent bans — cannot be bypassed by data file deletion
PERMANENT_BANS = {"ohmygod20260203", "eugenejarvis88", "krit22", "kastertrooy", "johndetmers-ui"}

# System accounts excluded from ban checks and auto-ban
SYSTEM_ACCOUNTS = {"wattcoin-org", "manual_admin_payout", "swarmsolve-refund"}


def load_banned_users():
    """Load full banned users set: PERMANENT_BANS + banned_users.json."""
    try:
        with open(BANNED_USERS_FILE, 'r') as f:
            data = json.load(f)
            file_bans = {u.lower() for u in data.get("banned", [])}
            return PERMANENT_BANS | file_bans
    except (FileNotFoundError, json.JSONDecodeError):
        return set(PERMANENT_BANS)


def save_banned_users(banned_set):
    """Save banned users list to data file."""
    os.makedirs(DATA_DIR, exist_ok=True)
    with open(BANNED_USERS_FILE, 'w') as f:
        json.dump({
            "banned": sorted(banned_set),
            "updated": datetime.utcnow().isoformat() + "Z"
        }, f, indent=2)


def is_banned(identifier):
    """
    Check if a GitHub username OR wallet address is banned.
    Case-insensitive for usernames.
    
    Args:
        identifier: GitHub username or wallet address
    
    Returns:
        bool: True if banned
    """
    if not identifier:
        return False
    banned = load_banned_users()
    return identifier.lower() in banned


def add_ban(identifier):
    """
    Add identifier to ban list and persist.
    
    Args:
        identifier: GitHub username or wallet to ban
    
    Returns:
        bool: True if newly added, False if already banned
    """
    banned = load_banned_users()
    normalized = identifier.lower()
    if normalized in banned:
        return False
    banned.add(normalized)
    save_banned_users(banned)
    log_security_event("ban_added", {"identifier": normalized})
    return True


# =============================================================================
# TASK RATE LIMITING (v1.1.0)
# Prevents spam on task marketplace endpoints.
# =============================================================================

TASK_RATE_LIMIT_FILE = f"{DATA_DIR}/task_rate_limits.json"
TASK_CLAIMS_PER_HOUR = int(os.getenv("TASK_CLAIMS_PER_HOUR", "10"))
TASK_SUBMISSIONS_PER_HOUR = int(os.getenv("TASK_SUBMISSIONS_PER_HOUR", "10"))
TASK_CREATES_PER_HOUR = int(os.getenv("TASK_CREATES_PER_HOUR", "5"))


def check_task_rate_limit(wallet, action="claim"):
    """
    Check if wallet has exceeded task rate limits.
    
    Args:
        wallet: Solana wallet address
        action: "claim", "submit", or "create"
    
    Returns:
        (allowed: bool, message: str)
    """
    limits = {
        "claim": TASK_CLAIMS_PER_HOUR,
        "submit": TASK_SUBMISSIONS_PER_HOUR,
        "create": TASK_CREATES_PER_HOUR,
    }
    max_per_hour = limits.get(action, 10)
    
    data = load_json_data(TASK_RATE_LIMIT_FILE, default={})
    now = time.time()
    cutoff = now - 3600  # 1 hour window
    
    key = f"{wallet}:{action}"
    timestamps = [t for t in data.get(key, []) if t > cutoff]
    
    if len(timestamps) >= max_per_hour:
        return False, f"Rate limit exceeded: max {max_per_hour} {action}s per hour"
    
    # Record this action
    timestamps.append(now)
    data[key] = timestamps
    
    # Cleanup old entries across all keys
    cleaned = {}
    for k, v in data.items():
        filtered = [t for t in v if t > cutoff]
        if filtered:
            cleaned[k] = filtered
    
    save_json_data(TASK_RATE_LIMIT_FILE, cleaned)
    return True, "ok"

# =============================================================================
# DATA HELPERS
# =============================================================================

def load_json_data(filepath, default=None):
    """Load JSON data from file, return default if not exists."""
    if default is None:
        default = {}
    
    if not os.path.exists(filepath):
        return default
    
    try:
        with open(filepath, 'r') as f:
            return json.load(f)
    except:
        return default

def save_json_data(filepath, data):
    """Save JSON data to file."""
    os.makedirs(os.path.dirname(filepath), exist_ok=True)
    with open(filepath, 'w') as f:
        json.dump(data, f, indent=2)

# =============================================================================
# WALLET VALIDATION
# =============================================================================

def validate_solana_address(address):
    """
    Validate Solana wallet address format.
    Returns: (is_valid, error_message)
    """
    if not address or not isinstance(address, str):
        return False, "Wallet address is required"
    
    address = address.strip()
    
    # Length check (Solana addresses are 32-44 chars typically)
    if len(address) < 32 or len(address) > 44:
        return False, f"Invalid address length: {len(address)} (expected 32-44)"
    
    # Base58 validation
    try:
        decoded = base58.b58decode(address)
        if len(decoded) != 32:
            return False, "Address decodes to wrong byte length"
    except Exception as e:
        return False, f"Invalid base58 encoding: {e}"
    
    return True, None

def extract_wallet_from_pr_body(pr_body):
    """
    Extract wallet address from PR body.
    Expected format: **Payout Wallet**: [address] (and common variations)
    Returns: (wallet_address or None, error_message or None)
    """
    if not pr_body:
        return None, "PR body is empty"
    
    # Look for wallet address in multiple formats (ordered specific → general)
    patterns = [
        r'\*\*Payout Wallet\*\*:\s*`?([1-9A-HJ-NP-Za-km-z]{32,44})`?',           # **Payout Wallet**: addr
        r'\*\*Payout Wallet\s*\([^)]*\)\*?\*?:?\s*`?([1-9A-HJ-NP-Za-km-z]{32,44})`?',  # **Payout Wallet (Solana):** addr
        r'\*\*Payout Wallet\s*(?:\([^)]*\)\s*)?:\s*\*?\*?\s*`?([1-9A-HJ-NP-Za-km-z]{32,44})`?',  # **Payout Wallet (X):** addr (colon before bold close)
        r'\*\*Wallet\*\*:\s*`?([1-9A-HJ-NP-Za-km-z]{32,44})`?',                   # **Wallet**: addr
        r'(?:Payout\s+)?Wallet:\s*`?([1-9A-HJ-NP-Za-km-z]{32,44})`?',             # Wallet: addr or Payout Wallet: addr
        r'[Ww]allet[^\n]{0,30}?`?([1-9A-HJ-NP-Za-km-z]{32,44})`?',               # Flexible: wallet + anything on same line + address
    ]
    match = None
    for pattern in patterns:
        match = re.search(pattern, pr_body)
        if match:
            break
    
    if not match:
        return None, "Missing wallet in PR body. Required format: **Payout Wallet**: [your_solana_address]"
    
    wallet = match.group(1).strip()
    
    # Validate the extracted wallet
    is_valid, error = validate_solana_address(wallet)
    if not is_valid:
        return None, f"Invalid wallet address: {error}"
    
    return wallet, None

# =============================================================================
# RATE LIMITING
# =============================================================================

def check_rate_limit(wallet):
    """
    Check if wallet has exceeded rate limits.
    Returns: (is_allowed, error_message, remaining_prs)
    """
    rate_limits = load_json_data(RATE_LIMIT_FILE, default={})
    
    now = time.time()
    one_day_ago = now - (24 * 3600)
    
    if wallet not in rate_limits:
        rate_limits[wallet] = {
            "pr_submissions": [],
            "last_payout": None
        }
    
    wallet_data = rate_limits[wallet]
    
    # Check payout cooldown
    if wallet_data.get("last_payout"):
        last_payout_time = wallet_data["last_payout"]
        cooldown_until = last_payout_time + (PAYOUT_COOLDOWN_HOURS * 3600)
        
        if now < cooldown_until:
            remaining_hours = (cooldown_until - now) / 3600
            return False, f"Cooldown active: {remaining_hours:.1f} hours remaining after last payout", 0
    
    # Clean old submissions (older than 24h)
    recent_submissions = [
        ts for ts in wallet_data.get("pr_submissions", [])
        if ts > one_day_ago
    ]
    wallet_data["pr_submissions"] = recent_submissions
    
    # Check daily limit
    if len(recent_submissions) >= MAX_PRS_PER_DAY:
        return False, f"Rate limit exceeded: {MAX_PRS_PER_DAY} PRs per 24h", 0
    
    remaining = MAX_PRS_PER_DAY - len(recent_submissions)
    
    # Save updated data
    rate_limits[wallet] = wallet_data
    save_json_data(RATE_LIMIT_FILE, rate_limits)
    
    return True, None, remaining

def record_pr_submission(wallet):
    """Record a PR submission timestamp for rate limiting."""
    rate_limits = load_json_data(RATE_LIMIT_FILE, default={})
    
    if wallet not in rate_limits:
        rate_limits[wallet] = {
            "pr_submissions": [],
            "last_payout": None
        }
    
    rate_limits[wallet]["pr_submissions"].append(time.time())
    save_json_data(RATE_LIMIT_FILE, rate_limits)

def record_payout(wallet):
    """Record a payout timestamp to start cooldown."""
    rate_limits = load_json_data(RATE_LIMIT_FILE, default={})
    
    if wallet not in rate_limits:
        rate_limits[wallet] = {
            "pr_submissions": [],
            "last_payout": None
        }
    
    rate_limits[wallet]["last_payout"] = time.time()
    save_json_data(RATE_LIMIT_FILE, rate_limits)

# =============================================================================
# CODE SCANNING
# =============================================================================

def scan_dangerous_code(diff_text):
    """
    Scan PR diff for dangerous code patterns.
    Returns: (is_safe, warnings_list)
    """
    if not diff_text:
        return True, []
    
    warnings = []
    
    # Check each dangerous pattern
    for pattern in DANGEROUS_PATTERNS:
        matches = re.finditer(pattern, diff_text, re.IGNORECASE | re.MULTILINE)
        for match in matches:
            # Get context (line containing the match)
            start = max(0, diff_text.rfind('\n', 0, match.start()) + 1)
            end = diff_text.find('\n', match.end())
            if end == -1:
                end = len(diff_text)
            
            context = diff_text[start:end].strip()
            
            warnings.append({
                "pattern": pattern,
                "match": match.group(0),
                "context": context[:100]  # Limit context length
            })
    
    is_safe = len(warnings) == 0
    return is_safe, warnings

# =============================================================================
# SECURITY LOGGING
# =============================================================================

def log_security_event(event_type, details):
    """
    Log security events (blocked PRs, rate limits, dangerous code, etc.)
    Event types: blocked_pr, rate_limit, dangerous_code, emergency_pause
    """
    logs = load_json_data(SECURITY_LOG_FILE, default={"events": []})
    
    event = {
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "type": event_type,
        "details": details
    }
    
    logs["events"].append(event)
    
    # Keep only last 1000 events to prevent file bloat
    if len(logs["events"]) > 1000:
        logs["events"] = logs["events"][-1000:]
    
    save_json_data(SECURITY_LOG_FILE, logs)

# =============================================================================
# EMERGENCY CONTROLS
# =============================================================================

def check_emergency_pause():
    """
    Check if emergency pause is active.
    Returns: (is_paused, pause_type, message)
    """
    if PAUSE_PR_REVIEWS:
        log_security_event("emergency_pause", {"type": "reviews", "active": True})
        return True, "reviews", "PR reviews are currently paused (PAUSE_PR_REVIEWS=true)"
    
    if PAUSE_PR_PAYOUTS:
        log_security_event("emergency_pause", {"type": "payouts", "active": True})
        return True, "payouts", "PR payouts are currently paused (PAUSE_PR_PAYOUTS=true)"
    
    return False, None, None

# =============================================================================
# VALIDATION HELPERS
# =============================================================================

def validate_pr_format(pr_body):
    """
    Validate PR body has required format.
    Returns: (is_valid, errors_list)
    """
    errors = []
    
    if not pr_body or len(pr_body.strip()) < 50:
        errors.append("PR body is too short (minimum 50 characters)")
    
    # Wallet is optional for review - only required for payment
    # wallet, wallet_error = extract_wallet_from_pr_body(pr_body)
    
    # Check for description/changes section
    # Removed keyword validation - too restrictive for agent contributions
    #         errors.append("PR body should include a description of changes")
    
    is_valid = len(errors) == 0
    return is_valid, errors

# =============================================================================
# AI SECURITY SCAN (Fail-Closed)
# =============================================================================

def ai_security_scan_pr(pr_number, repo=None):
    """
    Fetch PR diff and run AI security audit.
    FAIL-CLOSED: If AI unavailable, scan errors, or any issue → blocks merge.
    
    Returns: (passed: bool, report: str, scan_ran: bool)
    - passed=True,  scan_ran=True:  code is safe
    - passed=False, scan_ran=True:  flagged as dangerous
    - passed=False, scan_ran=False: scan couldn't run → block (fail-closed)
    """
    import requests as req
    
    check_repo = repo or os.getenv("GITHUB_REPO", "WattCoin-Org/wattcoin")
    github_token = os.getenv("GITHUB_TOKEN", "")
    
    # Check AI is configured
    try:
        from ai_provider import call_ai, AI_API_KEY
        if not AI_API_KEY:
            print(f"[SECURITY] AI_API_KEY not set — BLOCKING PR #{pr_number} (fail-closed)", flush=True)
            return False, "Security scan unavailable: AI service not configured.", False
    except ImportError:
        print(f"[SECURITY] ai_provider not available — BLOCKING PR #{pr_number} (fail-closed)", flush=True)
        return False, "Security scan unavailable: AI provider module missing.", False
    
    # Fetch PR diff
    try:
        gh_headers = {"Accept": "application/vnd.github.v3.diff"}
        if github_token:
            gh_headers["Authorization"] = f"token {github_token}"
        
        diff_resp = req.get(
            f"https://api.github.com/repos/{check_repo}/pulls/{pr_number}",
            headers=gh_headers,
            timeout=30
        )
        if diff_resp.status_code != 200:
            print(f"[SECURITY] Failed to fetch diff for PR #{pr_number}: HTTP {diff_resp.status_code}", flush=True)
            return False, f"Security scan unavailable: could not fetch PR diff (HTTP {diff_resp.status_code}).", False
        
        diff_text = diff_resp.text
        if not diff_text.strip():
            # Empty diff = no code changes, safe
            return True, "No code changes detected.", True
        
        if len(diff_text) > 15000:
            diff_text = diff_text[:15000] + "\n... [TRUNCATED — diff too large] ..."
    except Exception as e:
        print(f"[SECURITY] Diff fetch error PR #{pr_number}: {e}", flush=True)
        return False, f"Security scan unavailable: diff fetch error ({e}).", False
    
    # AI security scan prompt
    prompt = f"""You are a code security auditor for an open-source cryptocurrency project that processes real Solana token payments. This is a SAFETY-ONLY review — not code quality.

PR #{pr_number} on {check_repo}

DIFF:
```
{diff_text}
```

SCAN DIMENSIONS (evaluate each explicitly):

1. **Malware & Backdoors** (CRITICAL)
   Reverse shells, keyloggers, unauthorized network connections, process injection, persistence mechanisms.

2. **Credential Theft** (CRITICAL)
   Harvesting API keys, wallet private keys, passwords, environment variables being read and transmitted externally.

3. **Cryptocurrency Theft** (CRITICAL)
   Unauthorized wallet operations, address swapping, fund draining, transaction manipulation, unauthorized token transfers.

4. **Data Exfiltration** (HIGH)
   Sending user data, configuration, or operational info to external servers. Unauthorized HTTP requests. DNS-based exfiltration.

5. **Supply Chain Attack** (HIGH)
   Typosquatted packages, suspicious dependencies, modified build/deploy scripts, dependency hijacking, post-install scripts.

6. **Obfuscation** (HIGH)
   Base64-encoded payloads, eval() abuse, dynamic code execution, encoded strings that decode to malicious operations.

7. **Phishing & Social Engineering** (MEDIUM)
   Fake login pages, spoofed URLs, misleading user prompts, deceptive UI elements.

8. **Wallet Injection** (MEDIUM)
   Unknown wallet addresses embedded in docs, templates, configs, or code comments where contributors might copy them.

9. **AI-Proxy Social Engineering** (HIGH)
   Code that appears to "test", "audit", or "harden" security systems, payment routing, wallet operations, or authentication. External contributors are never authorized for security testing — this framing is a social engineering vector where a bad actor prompts a skilled AI coding model to produce exploit code disguised as legitimate contribution. Watch for: security bypass "improvements", payment redirect "refactors", authentication "hardening" that weakens gates, or any changes framed as "penetration testing".

Be strict — if in doubt, FAIL. False positives are better than letting malicious code through.
Only PASS if the code is clearly benign across ALL dimensions.

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
    "phishing": {{"safe": true, "reasoning": "...", "flagged_lines": []}},
    "wallet_injection": {{"safe": true, "reasoning": "...", "flagged_lines": []}},
    "ai_proxy_social_engineering": {{"safe": true, "reasoning": "...", "flagged_lines": []}}
  }},
  "summary": "One sentence explanation",
  "flags": []
}}

Do not include any text before or after the JSON."""

    try:
        report, ai_error = call_ai(prompt, temperature=0.1, max_tokens=1500, timeout=60)
        
        if ai_error:
            print(f"[SECURITY] AI API error for PR #{pr_number}: {ai_error}", flush=True)
            return False, f"Security scan unavailable: AI error ({ai_error}).", False
        
        print(f"[SECURITY] Scan result PR #{pr_number}: {report[:200]}...", flush=True)
        
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
            log_security_event("security_scan_failed", {
                "pr_number": pr_number,
                "report": report[:500]
            })
            return False, report, True
        
        log_security_event("security_scan_passed", {
            "pr_number": pr_number,
            "report": report[:200]
        })
        return True, report, True
        
    except Exception as e:
        print(f"[SECURITY] Scan exception PR #{pr_number}: {e}", flush=True)
        return False, f"Security scan unavailable: {e}.", False


# =============================================================================
# GITHUB WEBHOOK SIGNATURE VERIFICATION
# =============================================================================

def verify_github_signature(payload_body, signature_header, secret):
    """
    Verify GitHub webhook signature.
    Returns: is_valid (bool)
    """
    if not signature_header:
        return False
    
    import hmac
    import hashlib
    
    # GitHub sends signature as "sha256=<hash>"
    if not signature_header.startswith('sha256='):
        return False
    
    expected_signature = signature_header.split('=')[1]
    
    # Calculate HMAC
    mac = hmac.new(
        secret.encode('utf-8'),
        msg=payload_body,
        digestmod=hashlib.sha256
    )
    calculated_signature = mac.hexdigest()
    
    return hmac.compare_digest(calculated_signature, expected_signature)




# =============================================================================
# STAKING — Bounty Stake Verification & Return (v4.0.0)
# =============================================================================

ESCROW_WALLET = os.getenv("ESCROW_WALLET_ADDRESS", "5nZhxQksaj7pVWgET7UFSPjN7BDBYWWw3ZdL9AmADvkZ")
WATT_TOKEN_MINT = os.getenv("WATT_TOKEN_MINT", "Gpmbh4PoQnL1kNgpMYDED3iv4fczcr7d3qNBLf8rpump")
SOLANA_RPC_URL = os.getenv("SOLANA_RPC_URL", "https://solana.publicnode.com")
STAKE_PERCENTAGE = int(os.getenv("BOUNTY_STAKE_PERCENTAGE", "10"))
STAKE_TX_MAX_AGE = int(os.getenv("STAKE_TX_MAX_AGE_SECONDS", "86400"))  # 24 hours


def extract_stake_tx_from_pr_body(pr_body):
    """
    Extract stake transaction signature from PR body.
    Expected format: **Stake TX**: <signature>
    Returns: (tx_signature or None, error_message or None)
    """
    if not pr_body:
        return None, "PR body is empty"
    
    patterns = [
        r'\*\*Stake TX\*\*:\s*`?([A-Za-z0-9]{64,100})`?',           # **Stake TX**: sig
        r'\*\*Stake\s+TX\s*\([^)]*\)\*?\*?:?\s*`?([A-Za-z0-9]{64,100})`?',  # **Stake TX (Solana):** sig
        r'Stake\s+TX:\s*`?([A-Za-z0-9]{64,100})`?',                  # Stake TX: sig
        r'[Ss]take\s+[Tt](?:x|X|ransaction)[^\\n]{0,30}?`?([A-Za-z0-9]{64,100})`?',  # Flexible
    ]
    
    for pattern in patterns:
        match = re.search(pattern, pr_body)
        if match:
            sig = match.group(1).strip()
            # Basic validation: Solana TX sigs are base58, typically 87-88 chars
            if len(sig) >= 64 and len(sig) <= 100:
                return sig, None
    
    return None, "Missing stake TX in PR body. Required format: **Stake TX**: <your_stake_tx_signature>"


def get_bounty_amount_from_issue(issue_number):
    """
    Extract bounty WATT amount from a GitHub issue title or body.
    Looks for patterns like [BOUNTY: 5,000 WATT] or "5,000 WATT" in body.
    Returns: amount (int) or None
    """
    import requests as req
    
    REPO = os.getenv("GITHUB_REPO", "WattCoin-Org/wattcoin")
    token = os.getenv("GITHUB_TOKEN", "")
    headers = {"Authorization": f"token {token}", "Accept": "application/vnd.github.v3+json"} if token else {}
    
    try:
        resp = req.get(
            f"https://api.github.com/repos/{REPO}/issues/{issue_number}",
            headers=headers, timeout=10
        )
        if resp.status_code != 200:
            return None
        
        issue = resp.json()
        title = issue.get("title", "")
        body = issue.get("body", "") or ""
        
        # Try title first: [BOUNTY: 5,000 WATT]
        title_match = re.search(r'\[BOUNTY:\s*([\d,]+)\s*WATT\]', title, re.IGNORECASE)
        if title_match:
            return int(title_match.group(1).replace(',', ''))
        
        # Try body: "X,XXX WATT" or "XXXXX WATT"
        body_match = re.search(r'([\d,]+)\s*WATT', body, re.IGNORECASE)
        if body_match:
            amount = int(body_match.group(1).replace(',', ''))
            if amount >= 500:  # Minimum bounty
                return amount
        
        return None
    except Exception:
        return None


def get_linked_issue_number(pr_body):
    """
    Extract linked issue number from PR body.
    Looks for 'Closes #123', 'Fixes #123', 'Issue #123', etc.
    Returns: issue_number (int) or None
    """
    if not pr_body:
        return None
    
    patterns = [
        r'(?:Closes|Fixes|Resolves)\s+#(\d+)',
        r'Issue\s*#(\d+)',
        r'Bounty\s*#(\d+)',
        r'#(\d+)',  # Fallback: any issue reference
    ]
    
    for pattern in patterns:
        match = re.search(pattern, pr_body, re.IGNORECASE)
        if match:
            return int(match.group(1))
    
    return None


def verify_stake_payment(tx_signature, contributor_wallet, expected_amount):
    """
    Verify that a stake payment was sent to the escrow wallet.
    
    Checks:
    1. TX exists and is confirmed
    2. Escrow wallet received the expected WATT amount
    3. Contributor wallet was the sender
    4. TX is recent enough (within STAKE_TX_MAX_AGE)
    
    Returns: (success: bool, error_code: str, error_message: str)
    """
    import requests as req
    
    if not tx_signature or len(tx_signature) < 64:
        return False, "invalid_sig", "Invalid transaction signature format"
    
    # Check if stake TX was already used for another PR
    stake_data = _load_stake_data()
    for pr, info in stake_data.items():
        if info.get("stake_tx") == tx_signature and info.get("status") in ("active", "returned"):
            return False, "tx_already_used", f"Stake TX already used for PR #{pr}"
    
    # Fetch transaction with retries
    tx = None
    max_retries = 5
    for attempt in range(max_retries):
        try:
            resp = req.post(SOLANA_RPC_URL, json={
                "jsonrpc": "2.0", "id": 1,
                "method": "getTransaction",
                "params": [tx_signature, {"encoding": "jsonParsed", "maxSupportedTransactionVersion": 0}]
            }, timeout=15)
            result = resp.json().get("result")
            if result:
                tx = result
                break
        except Exception:
            pass
        if attempt < max_retries - 1:
            time.sleep(3)
    
    if not tx:
        return False, "tx_not_found", f"Transaction not found on chain after {max_retries} attempts"
    
    # Check for errors
    meta = tx.get("meta", {})
    if meta.get("err"):
        return False, "tx_failed", "Transaction failed on chain"
    
    # Check block time (must be recent)
    block_time = tx.get("blockTime")
    if not block_time:
        return False, "tx_not_confirmed", "Transaction not yet confirmed"
    
    tx_age = time.time() - block_time
    if tx_age > STAKE_TX_MAX_AGE:
        return False, "tx_too_old", f"Stake TX older than {STAKE_TX_MAX_AGE // 3600} hours"
    
    # Verify using pre/post token balances
    pre_balances = meta.get("preTokenBalances", [])
    post_balances = meta.get("postTokenBalances", [])
    
    # Build pre-balance lookup
    pre_by_index = {}
    for bal in pre_balances:
        if bal.get("mint") == WATT_TOKEN_MINT:
            idx = bal.get("accountIndex")
            owner = bal.get("owner")
            amount = float(bal.get("uiTokenAmount", {}).get("uiAmount", 0) or 0)
            pre_by_index[idx] = {"owner": owner, "amount": amount}
    
    # Check post-balances for escrow receipt and contributor send
    escrow_received = 0
    contributor_sent = False
    
    for bal in post_balances:
        if bal.get("mint") != WATT_TOKEN_MINT:
            continue
        
        idx = bal.get("accountIndex")
        owner = bal.get("owner")
        post_amount = float(bal.get("uiTokenAmount", {}).get("uiAmount", 0) or 0)
        pre_amount = pre_by_index.get(idx, {}).get("amount", 0)
        change = post_amount - pre_amount
        
        # Escrow wallet received WATT
        if owner == ESCROW_WALLET:
            escrow_received = change
        
        # Contributor wallet sent WATT (negative change)
        if owner == contributor_wallet:
            if change < 0:
                contributor_sent = True
    
    if escrow_received < expected_amount - 0.01:  # Allow tiny rounding
        return False, "insufficient_stake", f"Escrow received {escrow_received:.0f} WATT, expected {expected_amount}"
    
    if not contributor_sent:
        return False, "wrong_sender", "Contributor wallet was not the sender of this transaction"
    
    return True, None, None


def record_stake(pr_number, contributor_wallet, stake_tx, stake_amount, issue_number):
    """Record an active stake for tracking and return."""
    stake_data = _load_stake_data()
    stake_data[str(pr_number)] = {
        "wallet": contributor_wallet,
        "stake_tx": stake_tx,
        "amount": stake_amount,
        "issue_number": issue_number,
        "status": "active",
        "recorded_at": datetime.now().isoformat(),
        "returned_at": None,
        "return_tx": None
    }
    _save_stake_data(stake_data)


def return_stake(pr_number, reason="merged"):
    """
    Return stake to contributor.
    
    Args:
        pr_number: PR number
        reason: 'merged' (with bounty), 'exhausted' (all reviews used), 'admin_close'
    
    Returns: (success, tx_signature or error_message)
    """
    stake_data = _load_stake_data()
    stake = stake_data.get(str(pr_number))
    
    if not stake:
        return False, "No stake found for this PR"
    
    if stake.get("status") == "returned":
        return False, f"Stake already returned (TX: {stake.get('return_tx', 'unknown')})"
    
    wallet = stake.get("wallet")
    amount = stake.get("amount", 0)
    
    if not wallet or amount <= 0:
        return False, "Invalid stake data"
    
    try:
        from api_swarmsolve import send_watt_from_escrow
        memo = f"WattCoin Stake Return | PR #{pr_number} | {reason} | {amount:,} WATT"
        tx_sig = send_watt_from_escrow(wallet, amount, memo=memo)
        
        # Update stake record
        stake["status"] = "returned"
        stake["returned_at"] = datetime.now().isoformat()
        stake["return_tx"] = tx_sig
        stake["return_reason"] = reason
        _save_stake_data(stake_data)
        
        return True, tx_sig
    except Exception as e:
        log_security_event("stake_return_failed", {
            "pr_number": pr_number,
            "wallet": wallet,
            "amount": amount,
            "reason": reason,
            "error": str(e)
        })
        return False, f"Stake return failed: {str(e)}"


def get_stake_info(pr_number):
    """Get stake info for a PR. Returns dict or None."""
    stake_data = _load_stake_data()
    return stake_data.get(str(pr_number))


def _load_stake_data():
    """Load stake tracking data."""
    filepath = os.path.join(os.getenv("DATA_DIR", "data"), "bounty_stakes.json")
    try:
        if os.path.exists(filepath):
            with open(filepath, 'r') as f:
                return json.load(f)
    except (json.JSONDecodeError, IOError):
        pass
    return {}


def _save_stake_data(data):
    """Save stake tracking data."""
    filepath = os.path.join(os.getenv("DATA_DIR", "data"), "bounty_stakes.json")
    try:
        os.makedirs(os.path.dirname(filepath), exist_ok=True)
        with open(filepath, 'w') as f:
            json.dump(data, f, indent=2)
    except IOError as e:
        print(f"[STAKE] Failed to save stake data: {e}", flush=True)
