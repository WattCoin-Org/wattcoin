"""
WattCoin PR Security Module
Handles validation, rate limiting, and code scanning for PR bounty system
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
    Expected format: **Payout Wallet**: [address]
    Returns: (wallet_address or None, error_message or None)
    """
    if not pr_body:
        return None, "PR body is empty"
    
    # Look for wallet address in multiple formats
    patterns = [
        r'\*\*Payout Wallet\*\*:\s*`?([1-9A-HJ-NP-Za-km-z]{32,44})`?',   # **Payout Wallet**: addr
        r'(?:Payout\s+)?Wallet:\s*`?([1-9A-HJ-NP-Za-km-z]{32,44})`?',    # Wallet: addr or Payout Wallet: addr
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
    prompt = f"""You are a code security auditor for an open-source cryptocurrency project.
Review this PR diff for SAFETY ISSUES ONLY. This is NOT a code quality review.

SCAN FOR:
1. Malware, backdoors, reverse shells, keyloggers
2. Credential theft (harvesting API keys, wallet private keys, passwords)
3. Phishing code (fake login pages, spoofed URLs)
4. Cryptocurrency theft (unauthorized wallet operations, address swapping, draining funds)
5. Data exfiltration (sending user data to external servers)
6. Obfuscated/encoded malicious payloads (base64-encoded exploit code, eval() abuse)
7. Dependency hijacking (typosquatted packages, suspicious npm/pip installs)
8. Environment variable harvesting (reading secrets and sending them externally)
9. Supply chain attacks (modifying build/deploy scripts to inject malicious code)

PR #{pr_number} on {check_repo}

DIFF:
```
{diff_text}
```

Respond in this EXACT format:

VERDICT: PASS or FAIL
RISK_LEVEL: NONE / LOW / MEDIUM / HIGH / CRITICAL
FLAGS: (list any specific concerns, or "None")
SUMMARY: (one sentence explanation)

Be strict — if in doubt, FAIL. False positives are better than letting malicious code through.
Only PASS if the code is clearly benign."""

    try:
        report, ai_error = call_ai(prompt, temperature=0.1, max_tokens=500, timeout=30)
        
        if ai_error:
            print(f"[SECURITY] AI API error for PR #{pr_number}: {ai_error}", flush=True)
            return False, f"Security scan unavailable: AI error ({ai_error}).", False
        
        print(f"[SECURITY] Scan result PR #{pr_number}:\n{report}", flush=True)
        
        # Parse verdict
        verdict_line = [l for l in report.split("\n") if l.strip().startswith("VERDICT:")]
        if verdict_line:
            verdict = verdict_line[0].split(":", 1)[1].strip().upper()
            if "FAIL" in verdict:
                log_security_event("security_scan_failed", {
                    "pr_number": pr_number,
                    "report": report
                })
                return False, report, True
        
        # Also fail on CRITICAL/HIGH risk even if verdict parsing is off
        risk_line = [l for l in report.split("\n") if l.strip().startswith("RISK_LEVEL:")]
        if risk_line:
            risk = risk_line[0].split(":", 1)[1].strip().upper()
            if risk in ("CRITICAL", "HIGH"):
                log_security_event("security_scan_high_risk", {
                    "pr_number": pr_number,
                    "risk": risk,
                    "report": report
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
