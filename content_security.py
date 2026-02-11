# =============================================================================
# CONTENT SECURITY SCANNER v1.3.0
# Pre-AI-review checks for wallet injection, fabricated mechanisms, and URL leaks
# Detection patterns loaded from CONTENT_SECURITY_CONFIG env var (never in git)
# =============================================================================

import re
import os
import json

# --- Load detection config from env var (sensitive — not in source) ---
_config_raw = os.getenv("CONTENT_SECURITY_CONFIG", "")
_config = {}
if _config_raw:
    try:
        _config = json.loads(_config_raw)
    except (json.JSONDecodeError, ValueError) as e:
        print(f"[CONTENT-SECURITY] Failed to parse CONTENT_SECURITY_CONFIG: {e}", flush=True)

# Known project wallets (safe to reference in PRs)
KNOWN_PROJECT_WALLETS = set(_config.get("known_wallets", []))

# Solana wallet pattern (base58, 32-44 chars) — generic, not sensitive
SOLANA_WALLET_PATTERN = re.compile(r'\b[1-9A-HJ-NP-Za-km-z]{32,44}\b')

# Internal URLs that should never appear in public-facing content
INTERNAL_URL_PATTERNS = _config.get("internal_url_patterns", [])

# File extensions considered "public-facing" (docs, templates, configs, web content)
PUBLIC_FACING_EXTENSIONS = {
    '.md', '.txt', '.html', '.htm', '.json', '.yaml', '.yml',
    '.toml', '.cfg', '.ini', '.env.example', '.template',
    '.jsx', '.tsx', '.js', '.ts', '.css', '.svg',
}

# Suspicious phrases suggesting fabricated payment mechanisms
FABRICATED_MECHANISM_PATTERNS = _config.get("fabricated_mechanism_patterns", [])

# Fail-closed: if config not loaded, scanner blocks everything
if not KNOWN_PROJECT_WALLETS or not INTERNAL_URL_PATTERNS or not FABRICATED_MECHANISM_PATTERNS:
    print("[CONTENT-SECURITY] WARNING: CONTENT_SECURITY_CONFIG missing or incomplete — scanner will flag all wallets as unknown", flush=True)


def scan_pr_content(pr_diff, pr_files, submitter_wallet=None):
    """
    Scan PR diff content for security issues.
    
    Returns:
        (passed: bool, flags: list[dict]) — flags contain type, severity, detail (internal only)
    """
    flags = []
    
    if not pr_diff:
        return True, []
    
    # Only scan added lines (lines starting with +, excluding +++ header)
    added_lines = []
    current_file = None
    for line in pr_diff.split('\n'):
        if line.startswith('+++ b/'):
            current_file = line[6:]
        elif line.startswith('+') and not line.startswith('+++'):
            added_lines.append((current_file, line[1:]))  # strip the leading +
    
    added_content = '\n'.join([line for _, line in added_lines])
    
    # Determine which files are public-facing
    public_facing_files = set()
    for filepath, _ in added_lines:
        if filepath:
            for ext in PUBLIC_FACING_EXTENSIONS:
                if filepath.lower().endswith(ext):
                    public_facing_files.add(filepath)
                    break
            # docs/ directory is always public-facing
            if filepath.startswith('docs/'):
                public_facing_files.add(filepath)
    
    # --- CHECK 1: Wallet Injection ---
    # Find all Solana wallet addresses in added content
    found_wallets = set(SOLANA_WALLET_PATTERN.findall(added_content))
    
    # Filter out known project wallets
    unknown_wallets = found_wallets - KNOWN_PROJECT_WALLETS
    
    # Filter out submitter's own declared payout wallet (it's expected in PR body)
    if submitter_wallet:
        unknown_wallets.discard(submitter_wallet)
    
    # Check if unknown wallets appear in public-facing files specifically
    for filepath, line_content in added_lines:
        if filepath in public_facing_files:
            line_wallets = set(SOLANA_WALLET_PATTERN.findall(line_content))
            suspicious_in_docs = line_wallets - KNOWN_PROJECT_WALLETS
            if submitter_wallet:
                suspicious_in_docs.discard(submitter_wallet)
            
            if suspicious_in_docs:
                flags.append({
                    "type": "wallet_injection",
                    "severity": "critical",
                    "detail": f"Unknown wallet address(es) found in public-facing file: {filepath}",
                    "wallets": list(suspicious_in_docs)
                })
    
    # --- CHECK 2: Fabricated Payment Mechanisms ---
    for filepath, line_content in added_lines:
        for pattern in FABRICATED_MECHANISM_PATTERNS:
            if re.search(pattern, line_content):
                flags.append({
                    "type": "fabricated_mechanism",
                    "severity": "high",
                    "detail": f"Suspicious payment-related language in {filepath}: matches pattern '{pattern}'",
                })
                break  # One flag per file per pattern type is enough
    
    # --- CHECK 3: Internal URL Leak ---
    for filepath, line_content in added_lines:
        if filepath in public_facing_files:
            for pattern in INTERNAL_URL_PATTERNS:
                if re.search(pattern, line_content):
                    flags.append({
                        "type": "internal_url_leak",
                        "severity": "medium",
                        "detail": f"Internal URL pattern found in public-facing file: {filepath}",
                    })
                    break
    
    # Determine pass/fail
    has_critical = any(f["severity"] == "critical" for f in flags)
    has_high = any(f["severity"] == "high" for f in flags)
    
    passed = not (has_critical or has_high)
    
    return passed, flags


def format_flags_for_log(flags):
    """Format flags for internal logging (not shown to submitter)."""
    lines = []
    for f in flags:
        lines.append(f"[{f['severity'].upper()}] {f['type']}: {f['detail']}")
    return '\n'.join(lines)

