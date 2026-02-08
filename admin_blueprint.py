"""
WattCoin Bounty Admin Dashboard - Blueprint v2.2.0
Admin routes for managing bounty PR reviews.

Requires env vars:
    ADMIN_PASSWORD - Dashboard login password
    AI_REVIEW_KEY - For PR reviews
    GITHUB_TOKEN - For GitHub API calls

v2.2.0 Changes:
- Ban management: /admin/ban/<username>, /admin/unban/<username>
- API ban endpoint: /admin/api/ban/<username>
- Banned users stored in /app/data/banned_users.json

v2.1.0 Changes:
- System health status light on dashboard header
- Live green/red/yellow indicator pinging /health endpoint
- Shows version + uptime at a glance
- Auto-refreshes every 30 seconds

v2.0.0 Changes:
- External Tasks monitoring on Agent Tasks page
- Shows open/completed counts, total WATT posted/paid
- View all externally posted tasks with status

v1.2.0 Changes:
- Connect Wallet for one-click Phantom payouts
- TX signature recording and Solscan links
- Bounty amount parsing from linked issues
- Mark Paid button with TX tracking

v1.1.0 Changes:
- Close PR on GitHub when rejected
- Add Rejected counter to dashboard
- Add agent callback notification support (callback_url in PR body)
"""

import os
import json
import requests
import functools
from datetime import datetime
from flask import Blueprint, render_template_string, request, session, redirect, url_for, jsonify

# Blueprint setup
admin_bp = Blueprint('admin', __name__, url_prefix='/admin')

# Config
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "")
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN", "")
AI_API_KEY = os.getenv("AI_REVIEW_API_KEY", "")
REPO = "WattCoin-Org/wattcoin"
BOUNTY_WALLET_ADDRESS = os.getenv("BOUNTY_WALLET_ADDRESS", "7vvNkG3JF3JpxLEavqZSkc5T3n9hHR98Uw23fbWdXVSF")
DATA_FILE = "/app/data/bounty_reviews.json"
API_KEYS_FILE = "/app/data/api_keys.json"

# =============================================================================
# DATA STORAGE (JSON file)
# =============================================================================

def load_data():
    """Load reviews data from JSON file."""
    try:
        with open(DATA_FILE, 'r') as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {"reviews": {}, "payouts": [], "history": []}

def save_data(data):
    """Save reviews data to JSON file."""
    try:
        os.makedirs(os.path.dirname(DATA_FILE), exist_ok=True)
        with open(DATA_FILE, 'w') as f:
            json.dump(data, f, indent=2)
        return True
    except Exception as e:
        print(f"Error saving data: {e}")
        return False

# =============================================================================
# API KEYS STORAGE
# =============================================================================

def load_api_keys():
    """Load API keys from JSON file."""
    try:
        with open(API_KEYS_FILE, 'r') as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {"keys": {}}

def save_api_keys(data):
    """Save API keys to JSON file."""
    try:
        os.makedirs(os.path.dirname(API_KEYS_FILE), exist_ok=True)
        with open(API_KEYS_FILE, 'w') as f:
            json.dump(data, f, indent=2)
        return True
    except Exception as e:
        print(f"Error saving API keys: {e}")
        return False

def generate_api_key():
    """Generate a new UUID4 API key."""
    import uuid
    return str(uuid.uuid4())

def get_tier_rate_limit(tier):
    """Get rate limit for a tier."""
    limits = {
        "basic": {"requests_per_hour": 500, "requests_per_url": 50},
        "premium": {"requests_per_hour": 2000, "requests_per_url": 200}
    }
    return limits.get(tier, limits["basic"])

# =============================================================================
# AUTH
# =============================================================================

def login_required(f):
    """Decorator to require login for admin routes."""
    @functools.wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get('admin_logged_in'):
            return redirect(url_for('admin.login'))
        return f(*args, **kwargs)
    return decorated_function

# =============================================================================
# GITHUB API
# =============================================================================

def github_headers():
    """Get GitHub API headers."""
    headers = {"Accept": "application/vnd.github.v3+json"}
    if GITHUB_TOKEN:
        headers["Authorization"] = f"token {GITHUB_TOKEN}"
    return headers

def get_open_prs():
    """Fetch open PRs from GitHub."""
    url = f"https://api.github.com/repos/{REPO}/pulls?state=open"
    try:
        resp = requests.get(url, headers=github_headers(), timeout=15)
        if resp.status_code == 200:
            return resp.json()
        return []
    except Exception as e:
        print(f"GitHub API error: {e}")
        return []

def get_pr_detail(pr_number):
    """Fetch PR details including diff."""
    try:
        # Get PR info
        url = f"https://api.github.com/repos/{REPO}/pulls/{pr_number}"
        resp = requests.get(url, headers=github_headers(), timeout=15)
        if resp.status_code != 200:
            return None
        pr_data = resp.json()
        
        # Get diff
        diff_headers = github_headers()
        diff_headers["Accept"] = "application/vnd.github.v3.diff"
        diff_resp = requests.get(url, headers=diff_headers, timeout=15)
        diff = diff_resp.text[:15000] if diff_resp.status_code == 200 else ""
        
        return {
            "number": pr_number,
            "title": pr_data.get("title", "Unknown"),
            "author": pr_data.get("user", {}).get("login", "Unknown"),
            "body": pr_data.get("body", "") or "",
            "diff": diff,
            "url": pr_data.get("html_url", ""),
            "state": pr_data.get("state", "unknown"),
            "created_at": pr_data.get("created_at", ""),
            "labels": [l.get("name", "") for l in pr_data.get("labels", [])]
        }
    except Exception as e:
        print(f"Error fetching PR {pr_number}: {e}")
        return None

def get_bounty_claims():
    """Scan GitHub issues for bounty claims."""
    import re
    from datetime import datetime, timedelta
    
    claims = []
    
    try:
        # Get open issues with bounty label
        url = f"https://api.github.com/repos/{REPO}/issues?state=open&labels=bounty&per_page=50"
        resp = requests.get(url, headers=github_headers(), timeout=15)
        if resp.status_code != 200:
            return []
        
        issues = resp.json()
        
        for issue in issues:
            # Skip PRs (they show up in issues endpoint too)
            if issue.get("pull_request"):
                continue
            
            issue_number = issue.get("number")
            issue_title = issue.get("title", "")
            
            # Get comments for this issue
            comments_url = f"https://api.github.com/repos/{REPO}/issues/{issue_number}/comments"
            comments_resp = requests.get(comments_url, headers=github_headers(), timeout=15)
            if comments_resp.status_code != 200:
                continue
            
            comments = comments_resp.json()
            
            for comment in comments:
                body = comment.get("body", "").lower()
                if "claiming" in body or "i claim" in body or "claim this" in body:
                    claimant = comment.get("user", {}).get("login", "Unknown")
                    claim_date = comment.get("created_at", "")[:10]
                    
                    # Look for stake TX in subsequent comments by same user
                    stake_tx = None
                    for c in comments:
                        if c.get("user", {}).get("login") == claimant:
                            tx_match = re.search(r'solscan\.io/tx/([A-Za-z0-9]+)', c.get("body", ""))
                            if tx_match:
                                stake_tx = tx_match.group(1)
                                break
                    
                    # Calculate status
                    status = "pending_stake"
                    if stake_tx:
                        status = "staked"
                    
                    # Check if PR opened (search PRs mentioning this issue)
                    prs = get_open_prs()
                    for pr in prs:
                        pr_body = (pr.get("body") or "").lower()
                        if f"#{issue_number}" in pr_body or f"closes #{issue_number}" in pr_body:
                            if pr.get("user", {}).get("login") == claimant:
                                status = "pr_opened"
                                break
                    
                    # Check expiry (7 days)
                    if claim_date and status in ["pending_stake", "staked"]:
                        try:
                            claim_dt = datetime.fromisoformat(claim_date)
                            if datetime.now() - claim_dt > timedelta(days=7):
                                status = "expired"
                        except:
                            pass
                    
                    claims.append({
                        "issue_number": issue_number,
                        "issue_title": issue_title,
                        "claimant": claimant,
                        "claim_date": claim_date,
                        "stake_tx": stake_tx,
                        "status": status
                    })
                    break  # Only first claim per issue
        
        return claims
    except Exception as e:
        print(f"Error fetching claims: {e}")
        return []

def get_issue_title(issue_number):
    """Fetch issue title from GitHub."""
    url = f"https://api.github.com/repos/{REPO}/issues/{issue_number}"
    try:
        resp = requests.get(url, headers=github_headers(), timeout=10)
        if resp.status_code == 200:
            return resp.json().get("title", "")
    except:
        pass
    return ""

def extract_bounty_amount(title="", body="", labels=None):
    """Extract bounty amount from PR title, body, linked issue, or labels."""
    import re
    
    # 1. Try PR title: "[BOUNTY] Description - 10000 WATT"
    if title:
        match = re.search(r'(\d{1,3}(?:,?\d{3})*)\s*WATT', title, re.IGNORECASE)
        if match:
            return int(match.group(1).replace(',', ''))
    
    # 2. Try PR body: "## Bounty\n50000 WATT" or "## Bounty Amount\n50000"
    if body:
        # Match ## Bounty or ## Bounty Amount section
        match = re.search(r'##\s*Bounty(?:\s+Amount)?[^\n]*\n\s*(\d{1,3}(?:,?\d{3})*)', body, re.IGNORECASE)
        if match:
            return int(match.group(1).replace(',', ''))
        
        # Also try inline: "Bounty: 50000 WATT"
        match = re.search(r'[Bb]ounty[:\s]+(\d{1,3}(?:,?\d{3})*)\s*WATT', body)
        if match:
            return int(match.group(1).replace(',', ''))
        
        # 3. Try linked issue: "Closes #6" or "Fixes #6"
        issue_match = re.search(r'(?:closes|fixes|resolves)\s*#(\d+)', body, re.IGNORECASE)
        if issue_match:
            issue_number = int(issue_match.group(1))
            issue_title = get_issue_title(issue_number)
            if issue_title:
                # Look for bounty amount in issue title: "[BOUNTY: 100,000 WATT]"
                amount_match = re.search(r'(\d{1,3}(?:,?\d{3})*)\s*WATT', issue_title, re.IGNORECASE)
                if amount_match:
                    return int(amount_match.group(1).replace(',', ''))
    
    # 4. Fallback to labels
    if labels:
        for label in labels:
            if "bounty" in label.lower():
                match = re.search(r'(\d+)k?', label.lower())
                if match:
                    amount = int(match.group(1))
                    if 'k' in label.lower():
                        amount *= 1000
                    return amount
    
    return 0

def extract_callback_url(body):
    """Extract callback_url from PR body."""
    import re
    if not body:
        return None
    # Look for callback_url: https://... or callback_url=https://...
    match = re.search(r'callback_url[:\s=]+\s*(https?://[^\s\n]+)', body, re.IGNORECASE)
    if match:
        return match.group(1).strip()
    return None

def extract_wallet(body):
    """Extract Solana wallet address from PR body."""
    import re
    if not body:
        return None
    # Look for wallet in ## Wallet section or wallet: <address>
    # Solana addresses are base58, typically 32-44 chars
    patterns = [
        r'##\s*Wallet[:\s]*\n*\s*([1-9A-HJ-NP-Za-km-z]{32,44})',  # ## Wallet section
        r'wallet[:\s=]+\s*([1-9A-HJ-NP-Za-km-z]{32,44})',  # wallet: <address>
        r'\b([1-9A-HJ-NP-Za-km-z]{43,44})\b'  # Raw Solana address (43-44 chars typical)
    ]
    for pattern in patterns:
        match = re.search(pattern, body, re.IGNORECASE)
        if match:
            return match.group(1).strip()
    return None

def send_callback(callback_url, payload):
    """Send callback notification to agent. Fail silently."""
    if not callback_url:
        return
    try:
        requests.post(
            callback_url,
            json=payload,
            headers={"Content-Type": "application/json"},
            timeout=10
        )
        print(f"Callback sent to {callback_url}")
    except Exception as e:
        print(f"Callback failed (non-blocking): {e}")

def close_pr(pr_number):
    """Close a PR on GitHub."""
    url = f"https://api.github.com/repos/{REPO}/pulls/{pr_number}"
    try:
        resp = requests.patch(
            url, 
            headers=github_headers(), 
            json={"state": "closed"},
            timeout=15
        )
        return resp.status_code == 200
    except Exception as e:
        print(f"Failed to close PR #{pr_number}: {e}")
        return False

# =============================================================================
# AI REVIEW
# =============================================================================

def call_ai_review(pr_info):
    """Send PR to AI for structured review with score."""
    if not AI_API_KEY:
        return {"error": "AI_API_KEY not configured"}
    
    prompt = f"""You are a strict code reviewer for the WattCoin project — a production Solana utility token with live payments.

PR #{pr_info['number']}: {pr_info['title']}
Author: {pr_info['author']}
Description: {pr_info['body'][:1500]}

DIFF:
```
{pr_info['diff']}
```

Review for: functionality, code quality, security, scope match, breaking changes, dead code, test validity.

STRICT RULES:
- If ANY existing functionality is removed or degraded, score MUST be ≤5.
- If ANY concern is listed, score CANNOT be 9 or higher.
- Score of 9+ passes review. Be strict — this is live production.

Respond ONLY with valid JSON:
{{
  "score": 1-10,
  "pass": true/false,
  "recommendation": "Approve / Request changes / Reject",
  "completeness": "X%",
  "feedback": "2-3 sentence summary",
  "concerns": ["concern 1", "concern 2"],
  "suggested_changes": ["change 1", "change 2"],
  "suggested_payout": "100% / X% / 0%"
}}

Do not include any text before or after the JSON."""

    try:
        from ai_provider import call_ai
        content, ai_error = call_ai(prompt, temperature=0.2, max_tokens=1500, timeout=60)
        
        if ai_error:
            return {"error": ai_error}
        
        # Parse structured JSON response
        parsed = None
        try:
            import re
            json_match = re.search(r'\{.*\}', content, re.DOTALL)
            if json_match:
                parsed = json.loads(json_match.group())
                # Enforce: concerns listed → cannot pass
                if parsed.get("concerns") and len(parsed["concerns"]) > 0:
                    parsed["pass"] = False
                    if parsed.get("score", 0) >= 9:
                        parsed["score"] = 8
        except (json.JSONDecodeError, Exception):
            pass
        
        result = {
            "success": True,
            "review": content,
            "timestamp": datetime.now().isoformat()
        }
        
        if parsed:
            result["score"] = parsed.get("score")
            result["passed"] = parsed.get("pass", False)
            result["feedback"] = parsed.get("feedback", "")
            result["concerns"] = parsed.get("concerns", [])
            result["suggested_changes"] = parsed.get("suggested_changes", [])
            result["recommendation"] = parsed.get("recommendation", "")
            result["completeness"] = parsed.get("completeness", "")
            result["suggested_payout"] = parsed.get("suggested_payout", "")
        
        return result
    except Exception as e:
        return {"error": f"AI request failed: {str(e)}"}

# =============================================================================
# HTML TEMPLATES
# =============================================================================

LOGIN_TEMPLATE = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>WattCoin Admin - Login</title>
    <script src="https://cdn.tailwindcss.com"></script>
</head>
<body class="bg-gray-900 text-gray-100 min-h-screen flex items-center justify-center">
    <div class="bg-gray-800 p-8 rounded-lg shadow-xl w-full max-w-md">
        <h1 class="text-2xl font-bold text-green-400 mb-6">⚡ WattCoin Admin</h1>
        {% if error %}
        <div class="bg-red-900/50 border border-red-500 text-red-300 px-4 py-2 rounded mb-4">{{ error }}</div>
        {% endif %}
        <form method="POST">
            <input type="password" name="password" placeholder="Password" 
                   class="w-full bg-gray-700 border border-gray-600 rounded px-4 py-3 mb-4 focus:outline-none focus:border-green-400">
            <button type="submit" class="w-full bg-green-500 hover:bg-green-600 text-black font-bold py-3 rounded transition">
                Login
            </button>
        </form>
    </div>
</body>
</html>
"""

DASHBOARD_TEMPLATE = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>PR Reviews & Payouts - WattCoin Admin</title>
    <script src="https://cdn.tailwindcss.com"></script>
</head>
<body class="bg-gray-900 text-gray-100 min-h-screen">
    <div class="max-w-6xl mx-auto p-6">
        <!-- Header -->
        <div class="flex justify-between items-center mb-4">
            <div>
                <h1 class="text-2xl font-bold text-green-400">⚡ WattCoin Admin</h1>
                <p class="text-gray-500 text-sm">v3.4.0 | PR Reviews & Bounty Payouts | Pass threshold: ≥9/10</p>
            </div>
            <div class="flex items-center gap-3">
                <!-- System Health -->
                <div id="health-widget" class="flex items-center gap-2 bg-gray-800 rounded-lg px-3 py-2">
                    <span id="health-dot" class="w-3 h-3 rounded-full bg-gray-600 animate-pulse"></span>
                    <div class="text-xs">
                        <span id="health-label" class="text-gray-500">Checking...</span>
                        <div id="health-detail" class="text-gray-600"></div>
                    </div>
                </div>
                <!-- Webhook Status -->
                <div id="webhook-widget" class="flex items-center gap-2 bg-gray-800 rounded-lg px-3 py-2">
                    <span id="webhook-dot" class="w-3 h-3 rounded-full bg-gray-600 animate-pulse"></span>
                    <div class="text-xs">
                        <span id="webhook-label" class="text-gray-500">Webhooks...</span>
                        <div id="webhook-detail" class="text-gray-600"></div>
                    </div>
                </div>
                <!-- Payment Queue Badge -->
                <div id="queue-widget" class="flex items-center gap-2 bg-gray-800 rounded-lg px-3 py-2" style="display:none;">
                    <span class="w-3 h-3 rounded-full bg-yellow-400 animate-pulse"></span>
                    <div class="text-xs">
                        <span id="queue-label" class="text-yellow-400">⏳ Payments</span>
                        <div id="queue-detail" class="text-yellow-500"></div>
                    </div>
                </div>
                <!-- Active Nodes -->
                <div id="nodes-widget" class="flex items-center gap-2 bg-gray-800 rounded-lg px-3 py-2">
                    <span class="text-xs">🖥️</span>
                    <div class="text-xs">
                        <span id="nodes-label" class="text-gray-500">Nodes</span>
                        <div id="nodes-detail" class="text-gray-600">...</div>
                    </div>
                </div>
                <a href="{{ url_for('admin.logout') }}" class="text-gray-400 hover:text-red-400 text-sm">Logout</a>
            </div>
        </div>
        
        <!-- Nav Tabs -->
        <div class="flex gap-1 mb-6 border-b border-gray-700">
            <a href="{{ url_for('admin.dashboard') }}" 
               class="px-4 py-2 text-sm font-medium border-b-2 border-green-400 text-green-400">
                🎯 PR Bounties
            </a>
            <a href="{{ url_for('admin.submissions') }}" 
               class="px-4 py-2 text-sm font-medium border-b-2 border-transparent text-gray-400 hover:text-gray-200">
                📋 Agent Tasks
            </a>
            <a href="{{ url_for('admin.api_keys') }}" 
               class="px-4 py-2 text-sm font-medium border-b-2 border-transparent text-gray-400 hover:text-gray-200">
                🔑 Scraper Keys
            </a>
            <a href="{{ url_for('admin.clear_data') }}" 
               class="px-4 py-2 text-sm font-medium border-b-2 border-transparent text-gray-400 hover:text-gray-200">
                🗑️ Clear Data
            </a>
        </div>
        
        {% if message %}
        <div class="bg-green-900/50 border border-green-500 text-green-300 px-4 py-2 rounded mb-6">{{ message }}</div>
        {% endif %}
        
        {% if error %}
        <div class="bg-red-900/50 border border-red-500 text-red-300 px-4 py-2 rounded mb-6">{{ error }}</div>
        {% endif %}
        
        <!-- Stats -->
        <div class="grid grid-cols-3 gap-4 mb-8">
            <div class="bg-gray-800 rounded-lg p-4">
                <div class="text-3xl font-bold text-blue-400">{{ stats.open_prs }}</div>
                <div class="text-gray-500 text-sm">Open PRs</div>
            </div>
            <div class="bg-gray-800 rounded-lg p-4">
                <div class="text-3xl font-bold text-green-400">{{ stats.approved }}</div>
                <div class="text-gray-500 text-sm">Approved</div>
            </div>
            <div class="bg-gray-800 rounded-lg p-4">
                <div class="text-3xl font-bold text-red-400">{{ stats.rejected }}</div>
                <div class="text-gray-500 text-sm">Rejected</div>
            </div>
        </div>
        
        <!-- PR List -->
        <h2 class="text-xl font-semibold mb-4">Open Pull Requests</h2>
        
        {% if prs %}
        <div class="space-y-4">
            {% for pr in prs %}
            <div class="bg-gray-800 rounded-lg p-4 border-l-4 {% if pr.number|string in reviews %}{% if reviews[pr.number|string].get('passed') %}border-green-500{% elif reviews[pr.number|string].get('score') %}border-red-500{% else %}border-blue-500{% endif %}{% else %}border-gray-600{% endif %}">
                <div class="flex justify-between items-start">
                    <div>
                        <a href="{{ pr.html_url }}" target="_blank" class="text-lg font-medium hover:text-green-400">
                            #{{ pr.number }} - {{ pr.title }}
                        </a>
                        <div class="text-gray-500 text-sm mt-1">
                            by {{ pr.user.login }} • {{ pr.created_at[:10] }}
                            {% for label in pr.labels %}
                            <span class="ml-2 px-2 py-0.5 bg-gray-700 rounded text-xs">{{ label.name }}</span>
                            {% endfor %}
                        </div>
                    </div>
                    <div class="flex gap-2 items-center">
                        {% if pr.number|string in reviews %}
                            {% set rev = reviews[pr.number|string] %}
                            {% if rev.get('score') %}
                                {% if rev.get('passed') %}
                                <span class="px-3 py-1 bg-green-900/50 text-green-400 rounded text-sm font-mono">✅ {{ rev.score }}/10 PASS</span>
                                {% elif rev.score >= 7 %}
                                <span class="px-3 py-1 bg-yellow-900/50 text-yellow-400 rounded text-sm font-mono">⚠️ {{ rev.score }}/10</span>
                                {% else %}
                                <span class="px-3 py-1 bg-red-900/50 text-red-400 rounded text-sm font-mono">❌ {{ rev.score }}/10 FAIL</span>
                                {% endif %}
                            {% elif rev.get('status') == 'approved' %}
                                <span class="px-3 py-1 bg-green-900/50 text-green-400 rounded text-sm">✅ Merged</span>
                            {% elif rev.get('status') == 'rejected' %}
                                <span class="px-3 py-1 bg-red-900/50 text-red-400 rounded text-sm">❌ Rejected</span>
                            {% else %}
                                <span class="px-3 py-1 bg-blue-900/50 text-blue-400 rounded text-sm">Reviewed</span>
                            {% endif %}
                        {% endif %}
                        <a href="{{ url_for('admin.pr_detail', pr_number=pr.number) }}" 
                           class="px-4 py-1 bg-blue-600 hover:bg-blue-700 rounded text-sm transition">
                            View
                        </a>
                    </div>
                </div>
                {% if pr.number|string in reviews and reviews[pr.number|string].get('feedback') %}
                <div class="mt-2 text-gray-400 text-sm">{{ reviews[pr.number|string].feedback[:120] }}{% if reviews[pr.number|string].feedback|length > 120 %}...{% endif %}</div>
                {% endif %}
            </div>
            {% endfor %}
        </div>
        {% else %}
        <div class="bg-gray-800 rounded-lg p-8 text-center text-gray-500">
            No open pull requests
        </div>
        {% endif %}
        
        <!-- Manual Payment Queue -->
        <div class="mt-8 pt-6 border-t border-gray-700">
            <div class="flex justify-between items-center mb-4">
                <h2 class="text-xl font-semibold">💳 Manual Payment</h2>
                <div class="flex gap-3">
                    <form method="POST" action="{{ url_for('admin.clear_payment_queue') }}" 
                          onsubmit="return confirm('Clear all pending payments from queue?')">
                        <button type="submit" class="px-4 py-2 bg-red-600 hover:bg-red-700 text-white font-bold rounded transition">
                            🗑️ Clear Queue
                        </button>
                    </form>
                    <button onclick="processQueue()" id="process-btn" 
                            class="px-4 py-2 bg-green-600 hover:bg-green-700 text-white font-bold rounded transition flex items-center gap-2">
                        ⚡ Process Payment Queue
                    </button>
                </div>
            </div>
            <div id="process-result" class="mb-4 hidden"></div>
            
            <div class="bg-gray-800 rounded-lg p-5">
                <p class="text-gray-400 text-sm mb-4">Queue a payment for a merged PR that missed auto-payment (e.g. wallet was missing at merge time).</p>
                <form method="POST" action="{{ url_for('admin.queue_manual_payment') }}" class="grid grid-cols-2 gap-4">
                    <div>
                        <label class="block text-gray-400 text-xs mb-1">PR Number *</label>
                        <input type="number" name="pr_number" required placeholder="e.g. 75"
                               class="w-full bg-gray-700 border border-gray-600 rounded px-3 py-2 text-sm focus:outline-none focus:border-green-400">
                    </div>
                    <div>
                        <label class="block text-gray-400 text-xs mb-1">Bounty Issue # (optional)</label>
                        <input type="number" name="bounty_issue_id" placeholder="e.g. 44"
                               class="w-full bg-gray-700 border border-gray-600 rounded px-3 py-2 text-sm focus:outline-none focus:border-green-400">
                    </div>
                    <div>
                        <label class="block text-gray-400 text-xs mb-1">Wallet Address *</label>
                        <input type="text" name="wallet" required placeholder="Solana wallet address" minlength="32" maxlength="44"
                               class="w-full bg-gray-700 border border-gray-600 rounded px-3 py-2 text-sm font-mono focus:outline-none focus:border-green-400">
                    </div>
                    <div>
                        <label class="block text-gray-400 text-xs mb-1">Amount (WATT) *</label>
                        <input type="number" name="amount" required placeholder="e.g. 5000" min="1" max="100000"
                               class="w-full bg-gray-700 border border-gray-600 rounded px-3 py-2 text-sm focus:outline-none focus:border-green-400">
                    </div>
                    <div class="col-span-2">
                        <label class="block text-gray-400 text-xs mb-1">Reason</label>
                        <input type="text" name="reason" value="Late payout - wallet missing at merge time" 
                               class="w-full bg-gray-700 border border-gray-600 rounded px-3 py-2 text-sm focus:outline-none focus:border-green-400">
                    </div>
                    <div class="col-span-2">
                        <button type="submit" class="px-4 py-2 bg-yellow-600 hover:bg-yellow-700 text-black font-bold rounded transition">
                            📥 Queue Payment
                        </button>
                        <span class="text-gray-500 text-xs ml-3">Queues only — hit "Process Payment Queue" to send on-chain.</span>
                    </div>
                </form>
            </div>
        </div>
        
        <!-- SwarmSolve Solutions Status -->
        <div class="mt-8 pt-6 border-t border-gray-700">
            <h2 class="text-xl font-semibold mb-4">🔬 SwarmSolve Solutions</h2>
            <div id="swarmsolve-section">
                <div class="text-gray-500 text-sm">Loading solutions...</div>
            </div>
        </div>
        
        <!-- Navigation Links -->
        <div class="mt-8 pt-6 border-t border-gray-700 flex justify-between items-center">
            <div class="flex gap-6">
                <a href="{{ url_for('admin.payouts') }}" class="text-green-400 hover:text-green-300">
                    💰 Payout Queue
                </a>
                <a href="{{ url_for('admin.claims') }}" class="text-blue-400 hover:text-blue-300">
                    🎯 Bounty Claims
                </a>
            </div>
        </div>
    </div>
    
    <script>
        async function processQueue() {
            const btn = document.getElementById('process-btn');
            const resultDiv = document.getElementById('process-result');
            
            btn.disabled = true;
            btn.textContent = '⏳ Processing...';
            resultDiv.className = 'mb-4 bg-gray-800 rounded-lg p-4';
            resultDiv.innerHTML = '<span class="text-yellow-400">Processing payments...</span>';
            
            try {
                const resp = await fetch('{{ url_for("admin.process_payment_queue") }}', { method: 'POST' });
                const data = await resp.json();
                
                if (data.success && data.results && data.results.length > 0) {
                    resultDiv.innerHTML = '<div class="text-green-400 font-bold mb-2">Payment Results:</div>' +
                        data.results.map(r => '<div class="text-sm py-1">' + r + '</div>').join('');
                } else if (data.success && data.processed === 0) {
                    resultDiv.innerHTML = '<span class="text-gray-400">No pending payments in queue.</span>';
                } else {
                    resultDiv.innerHTML = '<span class="text-red-400">Error: ' + (data.message || 'Unknown error') + '</span>';
                }
            } catch (err) {
                resultDiv.innerHTML = '<span class="text-red-400">Request failed: ' + err.message + '</span>';
            }
            
            btn.disabled = false;
            btn.textContent = '⚡ Process Payment Queue';
            
            // Refresh webhook health to update badge
            checkWebhooks();
        }
        
        async function checkHealth() {
            const dot = document.getElementById('health-dot');
            const label = document.getElementById('health-label');
            const detail = document.getElementById('health-detail');
            
            try {
                const resp = await fetch('/health', { timeout: 5000 });
                const data = await resp.json();
                
                if (data.status === 'ok') {
                    dot.className = 'w-3 h-3 rounded-full bg-green-400 shadow-lg shadow-green-400/50';
                    label.textContent = 'System Online';
                    label.className = 'text-green-400';
                    
                    // Format uptime
                    const secs = data.uptime_seconds || 0;
                    const hrs = Math.floor(secs / 3600);
                    const mins = Math.floor((secs % 3600) / 60);
                    const uptimeStr = hrs > 0 ? hrs + 'h ' + mins + 'm' : mins + 'm';
                    detail.textContent = 'v' + (data.version || '?') + ' · ' + uptimeStr + ' uptime';
                    detail.className = 'text-gray-500';
                    
                    // Active nodes/jobs
                    const nodesLabel = document.getElementById('nodes-label');
                    const nodesDetail = document.getElementById('nodes-detail');
                    const jobs = data.active_jobs || 0;
                    nodesLabel.textContent = 'Active Jobs';
                    nodesLabel.className = jobs > 0 ? 'text-blue-400' : 'text-gray-400';
                    nodesDetail.textContent = jobs + ' running';
                    nodesDetail.className = jobs > 0 ? 'text-blue-300' : 'text-gray-500';
                } else {
                    dot.className = 'w-3 h-3 rounded-full bg-yellow-400 shadow-lg shadow-yellow-400/50';
                    label.textContent = 'Degraded';
                    label.className = 'text-yellow-400';
                    detail.textContent = data.status || 'Unknown status';
                }
            } catch (err) {
                dot.className = 'w-3 h-3 rounded-full bg-red-500 shadow-lg shadow-red-500/50';
                label.textContent = 'System Offline';
                label.className = 'text-red-400';
                detail.textContent = 'Health check failed';
                detail.className = 'text-red-500';
            }
        }
        
        async function checkWebhooks() {
            const dot = document.getElementById('webhook-dot');
            const label = document.getElementById('webhook-label');
            const wDetail = document.getElementById('webhook-detail');
            const queueWidget = document.getElementById('queue-widget');
            const queueLabel = document.getElementById('queue-label');
            const queueDetail = document.getElementById('queue-detail');
            
            try {
                const resp = await fetch('/webhooks/health', { timeout: 5000 });
                const data = await resp.json();
                
                if (data.status === 'ok' && data.webhook_secret_configured) {
                    dot.className = 'w-3 h-3 rounded-full bg-green-400 shadow-lg shadow-green-400/50';
                    label.textContent = 'Webhooks OK';
                    label.className = 'text-green-400';
                    wDetail.textContent = 'Secret configured';
                    wDetail.className = 'text-gray-500';
                } else if (data.status === 'ok') {
                    dot.className = 'w-3 h-3 rounded-full bg-yellow-400 shadow-lg shadow-yellow-400/50';
                    label.textContent = 'Webhooks ⚠️';
                    label.className = 'text-yellow-400';
                    wDetail.textContent = 'No secret set';
                    wDetail.className = 'text-yellow-500';
                }
                
                // Payment queue badge
                const pending = data.pending_payments || 0;
                if (pending > 0) {
                    queueWidget.style.display = 'flex';
                    queueLabel.textContent = '⏳ ' + pending + ' Payment' + (pending > 1 ? 's' : '');
                    queueDetail.textContent = 'Pending in queue';
                } else {
                    queueWidget.style.display = 'none';
                }
            } catch (err) {
                dot.className = 'w-3 h-3 rounded-full bg-red-500 shadow-lg shadow-red-500/50';
                label.textContent = 'Webhooks Down';
                label.className = 'text-red-400';
                wDetail.textContent = 'Check failed';
                wDetail.className = 'text-red-500';
            }
        }
        
        // Check on load, then every 30s
        checkHealth();
        checkWebhooks();
        loadSwarmSolve();
        setInterval(checkHealth, 30000);
        setInterval(checkWebhooks, 30000);
        
        async function loadSwarmSolve() {
            const section = document.getElementById('swarmsolve-section');
            try {
                const resp = await fetch('/api/v1/solutions');
                const data = await resp.json();
                const solutions = data.solutions || [];
                
                if (solutions.length === 0) {
                    section.innerHTML = '<div class="bg-gray-800 rounded-lg p-6 text-center text-gray-500">No SwarmSolve solutions yet</div>';
                    return;
                }
                
                let html = '<div class="space-y-3">';
                for (const s of solutions) {
                    const statusColors = {
                        'open': 'bg-blue-900/40 border-blue-600 text-blue-400',
                        'approved': 'bg-green-900/40 border-green-600 text-green-400',
                        'refunded': 'bg-gray-800 border-gray-600 text-gray-400',
                        'expired': 'bg-gray-800 border-gray-600 text-gray-500'
                    };
                    const statusIcons = {
                        'open': '🔵',
                        'approved': '✅',
                        'refunded': '↩️',
                        'expired': '⏰'
                    };
                    const colors = statusColors[s.status] || 'bg-gray-800 border-gray-600 text-gray-400';
                    const icon = statusIcons[s.status] || '❓';
                    
                    html += '<div class="' + colors + ' border rounded-lg p-4">';
                    html += '<div class="flex justify-between items-start">';
                    html += '<div>';
                    html += '<div class="font-medium">' + icon + ' ' + (s.title || 'Untitled') + '</div>';
                    html += '<div class="text-xs text-gray-500 mt-1">';
                    html += 'ID: ' + (s.id || '-').substring(0, 12) + '... ';
                    html += '• Budget: ' + (s.budget_watt ? s.budget_watt.toLocaleString() : '?') + ' WATT ';
                    if (s.deadline_date) html += '• Deadline: ' + s.deadline_date;
                    html += '</div>';
                    html += '</div>';
                    html += '<div class="flex items-center gap-2">';
                    
                    // Scan status badge
                    if (s.status === 'approved') {
                        html += '<span class="px-2 py-1 bg-green-900/50 text-green-400 rounded text-xs">🛡️ Scan Passed</span>';
                    } else if (s.status === 'open') {
                        html += '<span class="px-2 py-1 bg-gray-700 text-gray-400 rounded text-xs">🔍 Scan on approve</span>';
                    }
                    
                    html += '<span class="px-2 py-1 bg-gray-700 rounded text-xs uppercase">' + s.status + '</span>';
                    html += '</div>';
                    html += '</div>';
                    
                    // Show GitHub issue link if exists
                    if (s.github_issue_url) {
                        html += '<div class="mt-2 text-xs"><a href="' + s.github_issue_url + '" target="_blank" class="text-blue-400 hover:underline">→ GitHub Issue</a></div>';
                    }
                    
                    html += '</div>';
                }
                html += '</div>';
                
                section.innerHTML = html;
            } catch (err) {
                section.innerHTML = '<div class="bg-gray-800 rounded-lg p-4 text-red-400 text-sm">Failed to load solutions: ' + err.message + '</div>';
            }
        }
    </script>
</body>
</html>
"""

PR_DETAIL_TEMPLATE = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>PR #{{ pr.number }} - WattCoin Admin</title>
    <script src="https://cdn.tailwindcss.com"></script>
</head>
<body class="bg-gray-900 text-gray-100 min-h-screen">
    <div class="max-w-4xl mx-auto p-6">
        <!-- Back link -->
        <a href="{{ url_for('admin.dashboard') }}" class="text-gray-500 hover:text-gray-300 text-sm mb-4 inline-block">
            ← Back to Dashboard
        </a>
        
        <!-- PR Header -->
        <div class="bg-gray-800 rounded-lg p-6 mb-6">
            <h1 class="text-xl font-bold mb-2">#{{ pr.number }} - {{ pr.title }}</h1>
            <div class="text-gray-400 text-sm mb-4">
                by <span class="text-blue-400">{{ pr.author }}</span> • 
                <a href="{{ pr.url }}" target="_blank" class="text-green-400 hover:underline">View on GitHub</a>
            </div>
            
            {% if pr.labels %}
            <div class="mb-4">
                {% for label in pr.labels %}
                <span class="px-2 py-1 bg-gray-700 rounded text-xs mr-2">{{ label }}</span>
                {% endfor %}
            </div>
            {% endif %}
            
            <div class="bg-gray-900 rounded p-4 text-sm">
                <pre class="whitespace-pre-wrap">{{ pr.body or 'No description provided.' }}</pre>
            </div>
        </div>
        
        {% if message %}
        <div class="bg-green-900/50 border border-green-500 text-green-300 px-4 py-2 rounded mb-6">{{ message }}</div>
        {% endif %}
        
        {% if error %}
        <div class="bg-red-900/50 border border-red-500 text-red-300 px-4 py-2 rounded mb-6">{{ error }}</div>
        {% endif %}
        
        <!-- AI Review Section -->
        <div class="bg-gray-800 rounded-lg p-6 mb-6">
            <h2 class="text-lg font-semibold mb-4 flex items-center gap-2">
                🤖 AI Review
                {% if review %}
                <span class="text-xs text-gray-500">{{ review.timestamp[:16] }}</span>
                {% endif %}
            </h2>
            
            {% if review %}
            
            <!-- Score Badge -->
            {% if review.score %}
            <div class="flex items-center gap-4 mb-4">
                {% if review.get('passed') %}
                <div class="px-4 py-2 bg-green-900/50 border border-green-600 rounded-lg text-green-400 font-bold text-lg">✅ {{ review.score }}/10 PASS</div>
                {% elif review.score >= 7 %}
                <div class="px-4 py-2 bg-yellow-900/50 border border-yellow-600 rounded-lg text-yellow-400 font-bold text-lg">⚠️ {{ review.score }}/10</div>
                {% else %}
                <div class="px-4 py-2 bg-red-900/50 border border-red-600 rounded-lg text-red-400 font-bold text-lg">❌ {{ review.score }}/10 FAIL</div>
                {% endif %}
                
                {% if review.recommendation %}
                <span class="text-gray-400 text-sm">{{ review.recommendation }}</span>
                {% endif %}
                {% if review.completeness %}
                <span class="text-gray-500 text-sm">• {{ review.completeness }} complete</span>
                {% endif %}
                {% if review.suggested_payout %}
                <span class="text-gray-500 text-sm">• Payout: {{ review.suggested_payout }}</span>
                {% endif %}
            </div>
            {% endif %}
            
            <!-- Feedback -->
            {% if review.feedback %}
            <div class="bg-gray-900 rounded p-4 mb-4">
                <div class="text-gray-300">{{ review.feedback }}</div>
            </div>
            {% endif %}
            
            <!-- Concerns -->
            {% if review.concerns %}
            <div class="bg-red-900/20 border border-red-800/50 rounded p-4 mb-4">
                <div class="text-red-400 font-semibold text-sm mb-2">⚠️ Concerns ({{ review.concerns|length }})</div>
                {% for c in review.concerns %}
                <div class="text-red-300 text-sm py-1">• {{ c }}</div>
                {% endfor %}
            </div>
            {% endif %}
            
            <!-- Suggested Changes -->
            {% if review.suggested_changes %}
            <div class="bg-blue-900/20 border border-blue-800/50 rounded p-4 mb-4">
                <div class="text-blue-400 font-semibold text-sm mb-2">💡 Suggested Changes</div>
                {% for s in review.suggested_changes %}
                <div class="text-blue-300 text-sm py-1">• {{ s }}</div>
                {% endfor %}
            </div>
            {% endif %}
            
            <!-- Raw Review (collapsible) -->
            {% if review.review %}
            <details class="mt-4">
                <summary class="cursor-pointer text-gray-500 hover:text-gray-300 text-sm">View raw AI response</summary>
                <div class="bg-gray-900 rounded p-4 mt-2">
                    <pre class="whitespace-pre-wrap text-sm text-gray-400">{{ review.review }}</pre>
                </div>
            </details>
            {% endif %}
            
            {% else %}
            <p class="text-gray-500 mb-4">No AI review yet.</p>
            {% endif %}
            
            <div class="mt-4">
                <form method="POST" action="{{ url_for('admin.trigger_review', pr_number=pr.number) }}">
                    <button type="submit" class="px-4 py-2 bg-orange-600 hover:bg-orange-700 rounded transition">
                        {% if review %}🔄 Re-run AI Review{% else %}🚀 Run AI Review{% endif %}
                    </button>
                </form>
            </div>
        </div>
        
        <!-- Actions -->
        <div class="bg-gray-800 rounded-lg p-6">
            <h2 class="text-lg font-semibold mb-4">Actions</h2>
            <div class="flex gap-4">
                <form method="POST" action="{{ url_for('admin.approve_pr', pr_number=pr.number) }}" 
                      onsubmit="return confirm('Approve and merge this PR?')">
                    <button type="submit" class="px-6 py-2 bg-green-600 hover:bg-green-700 rounded font-medium transition">
                        ✅ Approve & Merge
                    </button>
                </form>
                <form method="POST" action="{{ url_for('admin.reject_pr', pr_number=pr.number) }}"
                      onsubmit="return confirm('Reject this PR?')">
                    <button type="submit" class="px-6 py-2 bg-red-600 hover:bg-red-700 rounded font-medium transition">
                        ❌ Reject
                    </button>
                </form>
            </div>
        </div>
        
        <!-- Diff Preview -->
        <div class="mt-6">
            <details class="bg-gray-800 rounded-lg">
                <summary class="p-4 cursor-pointer hover:bg-gray-750">View Diff ({{ pr.diff|length }} chars)</summary>
                <div class="p-4 pt-0">
                    <pre class="bg-gray-900 rounded p-4 text-xs overflow-x-auto">{{ pr.diff }}</pre>
                </div>
            </details>
        </div>
    </div>
</body>
</html>
"""

PAYOUTS_TEMPLATE = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Payout Queue - WattCoin Admin</title>
    <script src="https://cdn.tailwindcss.com"></script>
    <style>
        .toast {
            position: fixed; bottom: 20px; right: 20px;
            background: #10b981; color: #000; padding: 12px 20px;
            border-radius: 8px; font-weight: 600; opacity: 0;
            transition: opacity 0.3s; z-index: 1000;
        }
        .toast.show { opacity: 1; }
        .toast.error { background: #ef4444; color: #fff; }
        .spinner { animation: spin 1s linear infinite; }
        @keyframes spin { to { transform: rotate(360deg); } }
    </style>
</head>
<body class="bg-gray-900 text-gray-100 min-h-screen">
    <div id="toast" class="toast"></div>
    
    <div class="max-w-5xl mx-auto p-6">
        <!-- Header with wallet connection -->
        <div class="flex justify-between items-center mb-4">
            <a href="{{ url_for('admin.dashboard') }}" class="text-gray-500 hover:text-gray-300 text-sm">
                ← Back to Dashboard
            </a>
            <div id="walletSection">
                <button onclick="connectWallet()" id="connectBtn"
                    class="px-4 py-2 bg-purple-600 hover:bg-purple-700 rounded text-sm font-medium transition">
                    🔌 Connect Phantom
                </button>
            </div>
        </div>
        
        <h1 class="text-2xl font-bold text-green-400 mb-6">💰 Payout Queue</h1>
        
        {% if payouts %}
        <div class="bg-gray-800 rounded-lg overflow-hidden">
            <table class="w-full">
                <thead class="bg-gray-700">
                    <tr>
                        <th class="px-4 py-3 text-left text-sm">PR</th>
                        <th class="px-4 py-3 text-left text-sm">Contributor</th>
                        <th class="px-4 py-3 text-left text-sm">Amount</th>
                        <th class="px-4 py-3 text-left text-sm">Status</th>
                        <th class="px-4 py-3 text-left text-sm">Action</th>
                    </tr>
                </thead>
                <tbody>
                    {% for payout in payouts %}
                    <tr class="border-t border-gray-700" id="row-{{ payout.pr_number }}">
                        <td class="px-4 py-3">
                            <a href="https://github.com/{{ repo }}/pull/{{ payout.pr_number }}" 
                               target="_blank" class="text-blue-400 hover:underline">
                                #{{ payout.pr_number }}
                            </a>
                        </td>
                        <td class="px-4 py-3">
                            {{ payout.author }}
                            {% if payout.wallet %}
                            <div class="text-xs text-gray-500 truncate max-w-[150px]" title="{{ payout.wallet }}">
                                {{ payout.wallet[:8] }}...{{ payout.wallet[-4:] }}
                            </div>
                            {% endif %}
                        </td>
                        <td class="px-4 py-3 text-green-400 font-mono">{{ "{:,}".format(payout.amount) }} WATT</td>
                        <td class="px-4 py-3">
                            <span id="status-{{ payout.pr_number }}" class="px-2 py-1 rounded text-xs 
                                {% if payout.status == 'pending' %}bg-yellow-900/50 text-yellow-400
                                {% elif payout.status == 'paid' %}bg-green-900/50 text-green-400
                                {% endif %}">
                                {{ payout.status }}
                            </span>
                            {% if payout.tx_sig %}
                            <a href="https://solscan.io/tx/{{ payout.tx_sig }}" target="_blank" 
                               class="text-xs text-green-400 hover:underline ml-2" id="txlink-{{ payout.pr_number }}">TX ↗</a>
                            {% else %}
                            <span id="txlink-{{ payout.pr_number }}"></span>
                            {% endif %}
                        </td>
                        <td class="px-4 py-3" id="actions-{{ payout.pr_number }}">
                            {% if payout.status == 'pending' and payout.wallet %}
                            <div class="flex gap-2">
                                <button onclick="sendPayout('{{ payout.wallet }}', {{ payout.amount }}, {{ payout.pr_number }})"
                                   class="px-3 py-1.5 bg-green-600 hover:bg-green-700 rounded text-sm font-medium transition inline-flex items-center gap-1"
                                   id="payBtn-{{ payout.pr_number }}">
                                    ⚡ Pay
                                </button>
                                <button onclick="copyWallet('{{ payout.wallet }}', {{ payout.amount }})"
                                   class="px-3 py-1.5 bg-gray-600 hover:bg-gray-700 rounded text-sm font-medium transition"
                                   title="Copy wallet for manual payment">
                                    📋
                                </button>
                            </div>
                            {% elif payout.status == 'pending' and not payout.wallet %}
                            <span class="text-xs text-red-400">No wallet</span>
                            {% else %}
                            <span class="text-xs text-gray-500">✓ Complete</span>
                            {% endif %}
                        </td>
                    </tr>
                    {% endfor %}
                </tbody>
            </table>
        </div>
        
        <div class="mt-6 p-4 bg-gray-800 rounded-lg">
            <p class="text-sm text-gray-400">
                <strong>Source Wallet:</strong> {{ bounty_wallet }} (bounty fund)
            </p>
            <p class="text-sm text-gray-500 mt-2" id="walletStatus">
                Connect Phantom to pay directly, or use 📋 to copy wallet for manual payment.
            </p>
        </div>
        {% else %}
        <div class="bg-gray-800 rounded-lg p-8 text-center text-gray-500">
            No pending payouts
        </div>
        {% endif %}
    </div>
    
    <script type="module">
        // Constants
        const WATT_MINT = 'Gpmbh4PoQnL1kNgpMYDED3iv4fczcr7d3qNBLf8rpump';
        const WATT_DECIMALS = 6;
        const RPC_URL = 'https://solana.publicnode.com';
        
        // State
        let walletConnected = false;
        let walletPubkey = null;
        
        // Make functions globally available
        window.connectWallet = connectWallet;
        window.sendPayout = sendPayout;
        window.copyWallet = copyWallet;
        
        // Toast helper
        function showToast(msg, isError = false) {
            const toast = document.getElementById('toast');
            toast.textContent = msg;
            toast.className = 'toast show' + (isError ? ' error' : '');
            setTimeout(() => toast.classList.remove('show'), 4000);
        }
        
        // Connect Phantom
        async function connectWallet() {
            try {
                if (!window.solana || !window.solana.isPhantom) {
                    window.open('https://phantom.app/', '_blank');
                    showToast('Please install Phantom wallet', true);
                    return;
                }
                
                const resp = await window.solana.connect();
                walletPubkey = resp.publicKey.toString();
                walletConnected = true;
                
                document.getElementById('connectBtn').innerHTML = 
                    '✓ ' + walletPubkey.slice(0,4) + '...' + walletPubkey.slice(-4);
                document.getElementById('connectBtn').className = 
                    'px-4 py-2 bg-green-600 rounded text-sm font-medium cursor-default';
                document.getElementById('walletStatus').textContent = 
                    'Connected: ' + walletPubkey.slice(0,8) + '...' + walletPubkey.slice(-8);
                
                showToast('Wallet connected!');
            } catch (err) {
                console.error(err);
                showToast('Connection failed: ' + err.message, true);
            }
        }
        
        // Send payout via Phantom
        async function sendPayout(recipientWallet, amount, prNumber) {
            // If not connected, fall back to manual
            if (!walletConnected) {
                const txSig = prompt('Wallet not connected.\\n\\nEnter TX signature after manual payment (or Cancel):');
                if (txSig !== null && txSig.trim()) {
                    markPaidOnServer(prNumber, txSig.trim());
                }
                return;
            }
            
            const btn = document.getElementById('payBtn-' + prNumber);
            const originalText = btn.innerHTML;
            btn.innerHTML = '<span class="spinner">⏳</span> Sending...';
            btn.disabled = true;
            
            try {
                // Dynamic import Solana libraries
                const { Connection, PublicKey, Transaction } = await import('https://esm.sh/@solana/web3.js@1.87.6');
                const { getAssociatedTokenAddress, createTransferInstruction, TOKEN_PROGRAM_ID } = 
                    await import('https://esm.sh/@solana/spl-token@0.3.9');
                
                const connection = new Connection(RPC_URL, 'confirmed');
                const mintPubkey = new PublicKey(WATT_MINT);
                const recipientPubkey = new PublicKey(recipientWallet);
                const senderPubkey = new PublicKey(walletPubkey);
                
                // Get token accounts
                const senderATA = await getAssociatedTokenAddress(mintPubkey, senderPubkey);
                const recipientATA = await getAssociatedTokenAddress(mintPubkey, recipientPubkey);
                
                // Build transfer instruction
                const amountInSmallestUnit = BigInt(amount) * BigInt(10 ** WATT_DECIMALS);
                const transferIx = createTransferInstruction(
                    senderATA,
                    recipientATA,
                    senderPubkey,
                    amountInSmallestUnit
                );
                
                // Build transaction
                const tx = new Transaction().add(transferIx);
                tx.feePayer = senderPubkey;
                const { blockhash } = await connection.getLatestBlockhash();
                tx.recentBlockhash = blockhash;
                
                // Sign and send via Phantom
                const signed = await window.solana.signTransaction(tx);
                const signature = await connection.sendRawTransaction(signed.serialize());
                
                // Wait for confirmation
                await connection.confirmTransaction(signature, 'confirmed');
                
                showToast('✓ Payment sent! TX: ' + signature.slice(0,8) + '...');
                
                // Mark as paid on server
                markPaidOnServer(prNumber, signature);
                
                // Update UI immediately
                updateRowToPaid(prNumber, signature);
                
            } catch (err) {
                console.error(err);
                btn.innerHTML = originalText;
                btn.disabled = false;
                
                if (err.message.includes('User rejected')) {
                    showToast('Transaction cancelled', true);
                } else {
                    showToast('Error: ' + err.message, true);
                }
            }
        }
        
        // Mark paid on server
        function markPaidOnServer(prNumber, txSig) {
            fetch('/admin/payout/' + prNumber + '/paid?tx=' + encodeURIComponent(txSig))
                .then(() => console.log('Server updated'))
                .catch(err => console.error('Server update failed:', err));
        }
        
        // Update row UI to show paid
        function updateRowToPaid(prNumber, txSig) {
            const statusEl = document.getElementById('status-' + prNumber);
            const actionsEl = document.getElementById('actions-' + prNumber);
            const txLinkEl = document.getElementById('txlink-' + prNumber);
            
            if (statusEl) {
                statusEl.textContent = 'paid';
                statusEl.className = 'px-2 py-1 rounded text-xs bg-green-900/50 text-green-400';
            }
            if (actionsEl) {
                actionsEl.innerHTML = '<span class="text-xs text-gray-500">✓ Complete</span>';
            }
            if (txLinkEl) {
                txLinkEl.innerHTML = '<a href="https://solscan.io/tx/' + txSig + '" target="_blank" ' +
                    'class="text-xs text-green-400 hover:underline ml-2">TX ↗</a>';
            }
        }
        
        // Copy wallet fallback
        function copyWallet(wallet, amount) {
            navigator.clipboard.writeText(wallet).then(() => {
                showToast('✓ Copied! Send ' + amount.toLocaleString() + ' WATT');
            });
        }
        
        // Auto-connect if already authorized
        if (window.solana && window.solana.isPhantom) {
            window.solana.connect({ onlyIfTrusted: true })
                .then(resp => {
                    walletPubkey = resp.publicKey.toString();
                    walletConnected = true;
                    document.getElementById('connectBtn').innerHTML = 
                        '✓ ' + walletPubkey.slice(0,4) + '...' + walletPubkey.slice(-4);
                    document.getElementById('connectBtn').className = 
                        'px-4 py-2 bg-green-600 rounded text-sm font-medium cursor-default';
                })
                .catch(() => {}); // Not pre-authorized, that's fine
        }
    </script>
</body>
</html>
"""

CLAIMS_TEMPLATE = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Bounty Claims - WattCoin Admin</title>
    <script src="https://cdn.tailwindcss.com"></script>
</head>
<body class="bg-gray-900 text-gray-100 min-h-screen">
    <div class="max-w-5xl mx-auto p-6">
        <a href="{{ url_for('admin.dashboard') }}" class="text-gray-500 hover:text-gray-300 text-sm mb-4 inline-block">
            ← Back to Dashboard
        </a>
        
        <h1 class="text-2xl font-bold text-green-400 mb-6">🎯 Bounty Claims</h1>
        
        {% if claims %}
        <div class="bg-gray-800 rounded-lg overflow-hidden">
            <table class="w-full">
                <thead class="bg-gray-700">
                    <tr>
                        <th class="px-4 py-3 text-left text-sm">Issue</th>
                        <th class="px-4 py-3 text-left text-sm">Claimant</th>
                        <th class="px-4 py-3 text-left text-sm">Date</th>
                        <th class="px-4 py-3 text-left text-sm">Stake TX</th>
                        <th class="px-4 py-3 text-left text-sm">Status</th>
                    </tr>
                </thead>
                <tbody>
                    {% for claim in claims %}
                    <tr class="border-t border-gray-700">
                        <td class="px-4 py-3">
                            <a href="https://github.com/{{ repo }}/issues/{{ claim.issue_number }}" 
                               target="_blank" class="text-blue-400 hover:underline">
                                #{{ claim.issue_number }}
                            </a>
                            <div class="text-xs text-gray-500 truncate max-w-[200px]">{{ claim.issue_title }}</div>
                        </td>
                        <td class="px-4 py-3">
                            <a href="https://github.com/{{ claim.claimant }}" target="_blank" class="hover:text-blue-400">
                                {{ claim.claimant }}
                            </a>
                        </td>
                        <td class="px-4 py-3 text-sm text-gray-400">{{ claim.claim_date }}</td>
                        <td class="px-4 py-3">
                            {% if claim.stake_tx %}
                            <a href="https://solscan.io/tx/{{ claim.stake_tx }}" target="_blank" 
                               class="text-xs text-green-400 hover:underline">
                                {{ claim.stake_tx[:8] }}...
                            </a>
                            {% else %}
                            <span class="text-xs text-gray-500">—</span>
                            {% endif %}
                        </td>
                        <td class="px-4 py-3">
                            <span class="px-2 py-1 rounded text-xs 
                                {% if claim.status == 'pending_stake' %}bg-yellow-900/50 text-yellow-400
                                {% elif claim.status == 'staked' %}bg-blue-900/50 text-blue-400
                                {% elif claim.status == 'pr_opened' %}bg-green-900/50 text-green-400
                                {% elif claim.status == 'expired' %}bg-red-900/50 text-red-400
                                {% endif %}">
                                {% if claim.status == 'pending_stake' %}Pending Stake
                                {% elif claim.status == 'staked' %}Staked
                                {% elif claim.status == 'pr_opened' %}PR Opened
                                {% elif claim.status == 'expired' %}Expired
                                {% endif %}
                            </span>
                        </td>
                    </tr>
                    {% endfor %}
                </tbody>
            </table>
        </div>
        {% else %}
        <div class="bg-gray-800 rounded-lg p-8 text-center text-gray-500">
            No bounty claims found
        </div>
        {% endif %}
        
        <div class="mt-6 p-4 bg-gray-800 rounded-lg">
            <p class="text-sm text-gray-500">
                Claims are detected by scanning issue comments for "Claiming" keyword.
                Status updates when stake TX is posted or PR references the issue.
            </p>
        </div>
    </div>
</body>
</html>
"""

API_KEYS_TEMPLATE = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Scraper API Keys - WattCoin Admin</title>
    <script src="https://cdn.tailwindcss.com"></script>
    <style>
        .toast {
            position: fixed; bottom: 20px; right: 20px;
            background: #10b981; color: #000; padding: 12px 20px;
            border-radius: 8px; font-weight: 600; opacity: 0;
            transition: opacity 0.3s; z-index: 1000;
        }
        .toast.show { opacity: 1; }
    </style>
</head>
<body class="bg-gray-900 text-gray-100 min-h-screen">
    <div id="toast" class="toast"></div>
    
    <div class="max-w-6xl mx-auto p-6">
        <!-- Header -->
        <div class="flex justify-between items-center mb-4">
            <div>
                <h1 class="text-2xl font-bold text-green-400">⚡ WattCoin Admin</h1>
                <p class="text-gray-500 text-sm">v2.1.0 | Scraper API Keys - Premium Access (Skip WATT Payment)</p>
            </div>
            <a href="{{ url_for('admin.logout') }}" class="text-gray-400 hover:text-red-400 text-sm">Logout</a>
        </div>
        
        <!-- Nav Tabs -->
        <div class="flex gap-1 mb-6 border-b border-gray-700">
            <a href="{{ url_for('admin.dashboard') }}" 
               class="px-4 py-2 text-sm font-medium border-b-2 border-transparent text-gray-400 hover:text-gray-200">
                🎯 PR Bounties
            </a>
            <a href="{{ url_for('admin.submissions') }}" 
               class="px-4 py-2 text-sm font-medium border-b-2 border-transparent text-gray-400 hover:text-gray-200">
                📋 Agent Tasks
            </a>
            <a href="{{ url_for('admin.api_keys') }}" 
               class="px-4 py-2 text-sm font-medium border-b-2 border-green-400 text-green-400">
                🔑 Scraper Keys
            </a>
            <a href="{{ url_for('admin.clear_data') }}" 
               class="px-4 py-2 text-sm font-medium border-b-2 border-transparent text-gray-400 hover:text-gray-200">
                🗑️ Clear Data
            </a>
        </div>
        
        {% if message %}
        <div class="bg-green-900/50 border border-green-500 text-green-300 px-4 py-2 rounded mb-6">{{ message }}</div>
        {% endif %}
        
        <!-- Stats -->
        <div class="grid grid-cols-3 gap-4 mb-8">
            <div class="bg-gray-800 rounded-lg p-4">
                <div class="text-3xl font-bold text-blue-400">{{ stats.total }}</div>
                <div class="text-gray-500 text-sm">Total Keys</div>
            </div>
            <div class="bg-gray-800 rounded-lg p-4">
                <div class="text-3xl font-bold text-green-400">{{ stats.active }}</div>
                <div class="text-gray-500 text-sm">Active</div>
            </div>
            <div class="bg-gray-800 rounded-lg p-4">
                <div class="text-3xl font-bold text-gray-400">{{ "{:,}".format(stats.total_requests) }}</div>
                <div class="text-gray-500 text-sm">Total Requests</div>
            </div>
        </div>
        
        <!-- Create Key Form -->
        <div class="bg-gray-800 rounded-lg p-6 mb-8">
            <h2 class="text-lg font-semibold mb-4">Create New API Key</h2>
            <form action="{{ url_for('admin.create_api_key') }}" method="POST" class="flex gap-4 items-end">
                <div class="flex-1">
                    <label class="block text-sm text-gray-400 mb-1">Owner Wallet</label>
                    <input type="text" name="owner_wallet" placeholder="Solana wallet address" 
                           class="w-full bg-gray-700 border border-gray-600 rounded px-3 py-2 text-sm focus:border-green-500 focus:outline-none">
                </div>
                <div>
                    <label class="block text-sm text-gray-400 mb-1">Tier</label>
                    <select name="tier" class="bg-gray-700 border border-gray-600 rounded px-3 py-2 text-sm focus:border-green-500 focus:outline-none">
                        <option value="basic">Basic (500/hr)</option>
                        <option value="premium">Premium (2000/hr)</option>
                    </select>
                </div>
                <div>
                    <label class="block text-sm text-gray-400 mb-1">TX Signature</label>
                    <div class="flex gap-2">
                        <input type="text" name="tx_sig" id="tx_sig_input" placeholder="Payment TX (optional)" 
                               class="flex-1 bg-gray-700 border border-gray-600 rounded px-3 py-2 text-sm focus:border-green-500 focus:outline-none">
                        <button type="button" onclick="verifyTx()" 
                                class="px-3 py-2 bg-blue-600 hover:bg-blue-700 rounded text-sm font-medium transition whitespace-nowrap">
                            🔍 Verify
                        </button>
                    </div>
                </div>
                <button type="submit" class="px-4 py-2 bg-green-600 hover:bg-green-700 rounded text-sm font-medium transition">
                    + Create Key
                </button>
            </form>
        </div>
        
        <!-- Keys List -->
        <h2 class="text-lg font-semibold mb-4">Active Keys</h2>
        
        {% if keys %}
        <div class="bg-gray-800 rounded-lg overflow-hidden">
            <table class="w-full">
                <thead class="bg-gray-700">
                    <tr>
                        <th class="px-4 py-3 text-left text-sm">API Key</th>
                        <th class="px-4 py-3 text-left text-sm">Owner</th>
                        <th class="px-4 py-3 text-left text-sm">Tier</th>
                        <th class="px-4 py-3 text-left text-sm">Requests</th>
                        <th class="px-4 py-3 text-left text-sm">Created</th>
                        <th class="px-4 py-3 text-left text-sm">Action</th>
                    </tr>
                </thead>
                <tbody>
                    {% for key in keys %}
                    <tr class="border-t border-gray-700">
                        <td class="px-4 py-3">
                            <code class="text-xs bg-gray-700 px-2 py-1 rounded cursor-pointer" 
                                  onclick="copyKey('{{ key.key }}')" title="Click to copy">
                                {{ key.key[:8] }}...{{ key.key[-4:] }}
                            </code>
                        </td>
                        <td class="px-4 py-3">
                            {% if key.owner_wallet %}
                            <span class="text-xs text-gray-400" title="{{ key.owner_wallet }}">
                                {{ key.owner_wallet[:6] }}...{{ key.owner_wallet[-4:] }}
                            </span>
                            {% else %}
                            <span class="text-xs text-gray-500">—</span>
                            {% endif %}
                        </td>
                        <td class="px-4 py-3">
                            <span class="px-2 py-1 rounded text-xs 
                                {% if key.tier == 'premium' %}bg-purple-900/50 text-purple-400
                                {% else %}bg-blue-900/50 text-blue-400{% endif %}">
                                {{ key.tier }}
                            </span>
                        </td>
                        <td class="px-4 py-3 text-sm text-gray-400">{{ "{:,}".format(key.usage_count) }}</td>
                        <td class="px-4 py-3 text-sm text-gray-500">{{ key.created[:10] }}</td>
                        <td class="px-4 py-3">
                            {% if key.status == 'active' %}
                            <form action="{{ url_for('admin.revoke_api_key', key_id=key.key) }}" method="POST" 
                                  onsubmit="return confirm('Revoke this API key?');" style="display:inline;">
                                <button type="submit" class="text-xs text-red-400 hover:text-red-300">Revoke</button>
                            </form>
                            {% else %}
                            <span class="text-xs text-gray-500">Revoked</span>
                            {% endif %}
                        </td>
                    </tr>
                    {% endfor %}
                </tbody>
            </table>
        </div>
        {% else %}
        <div class="bg-gray-800 rounded-lg p-8 text-center text-gray-500">
            No API keys created yet
        </div>
        {% endif %}
        
        <!-- How It Works -->
        <div class="mt-6 grid md:grid-cols-2 gap-4">
            <div class="p-4 bg-gray-800 rounded-lg">
                <p class="text-sm text-green-400 font-semibold mb-3">📋 How to Issue Keys</p>
                <ol class="text-xs text-gray-400 space-y-2 list-decimal list-inside">
                    <li>User pays <strong>1000 WATT</strong> to bounty wallet</li>
                    <li>User sends you TX proof (X, Discord, etc.)</li>
                    <li>Verify TX on Solscan</li>
                    <li>Create key above → share with user</li>
                </ol>
                <p class="text-xs text-gray-500 mt-3">Bounty wallet: <code class="bg-gray-700 px-1 rounded">7vvNkG3...dXVSF</code></p>
            </div>
            
            <div class="p-4 bg-gray-800 rounded-lg">
                <p class="text-sm text-blue-400 font-semibold mb-3">⚡ Rate Limits</p>
                <table class="text-xs text-gray-400 w-full">
                    <tr><td class="py-1">No key (IP-based)</td><td class="text-right">100/hr</td></tr>
                    <tr><td class="py-1">Basic key</td><td class="text-right text-blue-400">500/hr</td></tr>
                    <tr><td class="py-1">Premium key</td><td class="text-right text-purple-400">2000/hr</td></tr>
                </table>
            </div>
        </div>
        
        <div class="mt-4 p-4 bg-gray-800 rounded-lg">
            <p class="text-sm text-gray-400 mb-2"><strong>User Usage (share with key recipients):</strong></p>
            <code class="text-xs bg-gray-700 px-3 py-2 rounded block overflow-x-auto">
                curl -X POST https://wattcoin-production-81a7.up.railway.app/api/v1/scrape \<br>
                &nbsp;&nbsp;-H "X-API-Key: your-key-here" \<br>
                &nbsp;&nbsp;-H "Content-Type: application/json" \<br>
                &nbsp;&nbsp;-d '{"url": "https://example.com", "format": "text"}'
            </code>
            <p class="text-xs text-gray-500 mt-2">Formats: <code class="bg-gray-700 px-1 rounded">text</code> | <code class="bg-gray-700 px-1 rounded">html</code> | <code class="bg-gray-700 px-1 rounded">json</code></p>
        </div>
    </div>
    
    <script>
        function copyKey(key) {
            navigator.clipboard.writeText(key).then(() => {
                const toast = document.getElementById('toast');
                toast.textContent = '✓ API key copied to clipboard';
                toast.classList.add('show');
                setTimeout(() => toast.classList.remove('show'), 3000);
            });
        }
        
        function verifyTx() {
            const txSig = document.getElementById('tx_sig_input').value.trim();
            if (!txSig) {
                alert('Enter a TX signature first');
                return;
            }
            window.open('https://solscan.io/tx/' + txSig, '_blank');
        }
    </script>
</body>
</html>
"""

# =============================================================================
# ROUTES
# =============================================================================

@admin_bp.route('/login', methods=['GET', 'POST'])
def login():
    """Admin login page."""
    if not ADMIN_PASSWORD:
        return render_template_string(LOGIN_TEMPLATE, error="ADMIN_PASSWORD not configured in env vars")
    
    if request.method == 'POST':
        if request.form.get('password') == ADMIN_PASSWORD:
            session['admin_logged_in'] = True
            return redirect(url_for('admin.dashboard'))
        return render_template_string(LOGIN_TEMPLATE, error="Invalid password")
    
    return render_template_string(LOGIN_TEMPLATE)

@admin_bp.route('/logout')
def logout():
    """Admin logout."""
    session.pop('admin_logged_in', None)
    return redirect(url_for('admin.login'))

@admin_bp.route('/')
@admin_bp.route('/dashboard')
@login_required
def dashboard():
    """Main dashboard - list open PRs."""
    prs = get_open_prs()
    data = load_data()
    reviews = data.get("reviews", {})
    
    # Count stats
    approved_count = len([r for r in reviews.values() if r.get("status") == "approved"])
    rejected_count = len([r for r in reviews.values() if r.get("status") == "rejected"])
    
    stats = {
        "open_prs": len(prs),
        "approved": approved_count,
        "rejected": rejected_count
    }
    
    return render_template_string(DASHBOARD_TEMPLATE, 
        prs=prs, 
        reviews=reviews,
        stats=stats,
        repo=REPO,
        message=request.args.get('message'),
        error=request.args.get('error')
    )

@admin_bp.route('/pr/<int:pr_number>')
@login_required
def pr_detail(pr_number):
    """PR detail page with AI review."""
    pr = get_pr_detail(pr_number)
    if not pr:
        return redirect(url_for('admin.dashboard', error=f"PR #{pr_number} not found"))
    
    data = load_data()
    review = data.get("reviews", {}).get(str(pr_number))
    
    return render_template_string(PR_DETAIL_TEMPLATE,
        pr=pr,
        review=review,
        message=request.args.get('message'),
        error=request.args.get('error')
    )

@admin_bp.route('/pr/<int:pr_number>/review', methods=['POST'])
@login_required
def trigger_review(pr_number):
    """Trigger AI review for a PR."""
    pr = get_pr_detail(pr_number)
    if not pr:
        return redirect(url_for('admin.dashboard', error=f"PR #{pr_number} not found"))
    
    result = call_ai_review(pr)
    
    if result.get("success"):
        data = load_data()
        review_entry = {
            "review": result["review"],
            "timestamp": result["timestamp"],
            "pr_title": pr["title"],
            "author": pr["author"]
        }
        # Store structured fields if available
        for field in ["score", "passed", "feedback", "concerns", "suggested_changes", 
                       "recommendation", "completeness", "suggested_payout"]:
            if field in result:
                review_entry[field] = result[field]
        
        data["reviews"][str(pr_number)] = review_entry
        save_data(data)
        return redirect(url_for('admin.pr_detail', pr_number=pr_number, message="AI review completed"))
    else:
        return redirect(url_for('admin.pr_detail', pr_number=pr_number, error=result.get("error", "Review failed")))

@admin_bp.route('/pr/<int:pr_number>/approve', methods=['POST'])
@login_required
def approve_pr(pr_number):
    """Approve and merge a PR."""
    # Get PR info first for callback
    pr = get_pr_detail(pr_number)
    callback_url = extract_callback_url(pr.get("body", "")) if pr else None
    bounty = extract_bounty_amount(pr.get("title", ""), pr.get("body", ""), pr.get("labels", [])) if pr else 0
    
    # Merge via GitHub API
    url = f"https://api.github.com/repos/{REPO}/pulls/{pr_number}/merge"
    try:
        resp = requests.put(url, headers=github_headers(), json={
            "commit_title": f"Merge PR #{pr_number} - Bounty approved",
            "merge_method": "squash"
        }, timeout=15)
        
        if resp.status_code in [200, 201]:
            # Update data
            data = load_data()
            review_text = ""
            if str(pr_number) in data["reviews"]:
                data["reviews"][str(pr_number)]["status"] = "approved"
                data["reviews"][str(pr_number)]["approved_at"] = datetime.now().isoformat()
                review_text = data["reviews"][str(pr_number)].get("review", "")
            
            # Add to payout queue
            if pr:
                recipient_wallet = extract_wallet(pr.get("body", ""))
                data["payouts"].append({
                    "pr_number": pr_number,
                    "author": pr["author"],
                    "amount": bounty,
                    "wallet": recipient_wallet,
                    "status": "pending",
                    "approved_at": datetime.now().isoformat()
                })
            
            save_data(data)
            
            # Send callback notification
            send_callback(callback_url, {
                "pr_number": pr_number,
                "status": "approved",
                "bounty": bounty,
                "review_summary": review_text[:1000],
                "payout_wallet": BOUNTY_WALLET_ADDRESS,
                "timestamp": datetime.now().isoformat()
            })
            
            return redirect(url_for('admin.dashboard', message=f"PR #{pr_number} merged successfully"))
        else:
            error_msg = resp.json().get("message", "Unknown error")
            return redirect(url_for('admin.pr_detail', pr_number=pr_number, error=f"Merge failed: {error_msg}"))
    except Exception as e:
        return redirect(url_for('admin.pr_detail', pr_number=pr_number, error=f"Merge error: {str(e)}"))

@admin_bp.route('/pr/<int:pr_number>/reject', methods=['POST'])
@login_required
def reject_pr(pr_number):
    """Reject and close a PR."""
    # Get PR info for callback
    pr = get_pr_detail(pr_number)
    callback_url = extract_callback_url(pr.get("body", "")) if pr else None
    bounty = extract_bounty_amount(pr.get("title", ""), pr.get("body", ""), pr.get("labels", [])) if pr else 0
    
    data = load_data()
    review = data.get("reviews", {}).get(str(pr_number), {})
    review_text = review.get('review', 'No detailed review available.')
    
    # Post rejection comment
    comment = f"""## ❌ Bounty Review - Not Approved

This PR has been reviewed but not approved for the bounty at this time.

{review_text}

---
*This is an automated response from the WattCoin bounty system. Please address the issues above and submit a new PR.*
"""
    
    url = f"https://api.github.com/repos/{REPO}/issues/{pr_number}/comments"
    try:
        requests.post(url, headers=github_headers(), json={"body": comment}, timeout=15)
    except:
        pass  # Comment posting is best-effort
    
    # Close the PR on GitHub
    close_pr(pr_number)
    
    # Update status
    if str(pr_number) in data.get("reviews", {}):
        data["reviews"][str(pr_number)]["status"] = "rejected"
        data["reviews"][str(pr_number)]["rejected_at"] = datetime.now().isoformat()
        save_data(data)
    
    # Send callback notification
    send_callback(callback_url, {
        "pr_number": pr_number,
        "status": "rejected",
        "bounty": bounty,
        "review_summary": review_text[:1000],
        "payout_wallet": None,
        "timestamp": datetime.now().isoformat()
    })
    
    return redirect(url_for('admin.dashboard', message=f"PR #{pr_number} rejected and closed"))

@admin_bp.route('/payouts')
@login_required
def payouts():
    """Payout queue page."""
    data = load_data()
    payout_list = data.get("payouts", [])
    
    # Backfill missing wallets and amounts from PR
    updated = False
    for payout in payout_list:
        pr = None
        if not payout.get("wallet") or payout.get("amount", 0) == 0:
            pr = get_pr_detail(payout.get("pr_number"))
        
        if pr:
            if not payout.get("wallet"):
                wallet = extract_wallet(pr.get("body", ""))
                if wallet:
                    payout["wallet"] = wallet
                    updated = True
            
            if payout.get("amount", 0) == 0:
                amount = extract_bounty_amount(pr.get("title", ""), pr.get("body", ""), pr.get("labels", []))
                if amount > 0:
                    payout["amount"] = amount
                    updated = True
    
    # Save if we backfilled anything
    if updated:
        save_data(data)
    
    return render_template_string(PAYOUTS_TEMPLATE,
        payouts=payout_list,
        repo=REPO,
        bounty_wallet=BOUNTY_WALLET_ADDRESS
    )

@admin_bp.route('/claims')
@login_required
def claims():
    """Bounty claims page."""
    claim_list = get_bounty_claims()
    return render_template_string(CLAIMS_TEMPLATE,
        claims=claim_list,
        repo=REPO
    )

@admin_bp.route('/payout/<int:pr_number>/paid')
@login_required
def mark_paid(pr_number):
    """Mark a payout as paid."""
    tx_sig = request.args.get('tx', '').strip()
    
    data = load_data()
    for payout in data.get("payouts", []):
        if payout.get("pr_number") == pr_number:
            payout["status"] = "paid"
            payout["paid_at"] = datetime.now().isoformat()
            if tx_sig:
                payout["tx_sig"] = tx_sig
            break
    
    save_data(data)
    return redirect(url_for('admin.payouts', message=f"PR #{pr_number} marked as paid"))

# =============================================================================
# API KEYS ROUTES
# =============================================================================

@admin_bp.route('/api-keys')
@login_required
def api_keys():
    """API keys management page."""
    data = load_api_keys()
    keys_dict = data.get("keys", {})
    
    # Convert to list for template
    keys_list = []
    total_requests = 0
    active_count = 0
    
    for key_id, key_data in keys_dict.items():
        key_data["key"] = key_id
        keys_list.append(key_data)
        total_requests += key_data.get("usage_count", 0)
        if key_data.get("status") == "active":
            active_count += 1
    
    # Sort by created date (newest first)
    keys_list.sort(key=lambda x: x.get("created", ""), reverse=True)
    
    stats = {
        "total": len(keys_list),
        "active": active_count,
        "total_requests": total_requests
    }
    
    return render_template_string(API_KEYS_TEMPLATE,
        keys=keys_list,
        stats=stats,
        repo=REPO,
        message=request.args.get('message')
    )

@admin_bp.route('/api-keys/create', methods=['POST'])
@login_required
def create_api_key():
    """Create a new API key."""
    owner_wallet = request.form.get('owner_wallet', '').strip()
    tier = request.form.get('tier', 'basic')
    tx_sig = request.form.get('tx_sig', '').strip()
    
    if tier not in ['basic', 'premium']:
        tier = 'basic'
    
    # Generate new key
    new_key = generate_api_key()
    
    # Load and update data
    data = load_api_keys()
    data["keys"][new_key] = {
        "owner_wallet": owner_wallet,
        "tier": tier,
        "tx_sig": tx_sig if tx_sig else None,
        "usage_count": 0,
        "created": datetime.now().isoformat(),
        "status": "active"
    }
    
    save_api_keys(data)
    
    return redirect(url_for('admin.api_keys', message=f"Key created: {new_key[:8]}..."))

@admin_bp.route('/api-keys/revoke/<key_id>', methods=['POST'])
@login_required
def revoke_api_key(key_id):
    """Revoke an API key."""
    data = load_api_keys()
    
    if key_id in data.get("keys", {}):
        data["keys"][key_id]["status"] = "revoked"
        data["keys"][key_id]["revoked_at"] = datetime.now().isoformat()
        save_api_keys(data)
        return redirect(url_for('admin.api_keys', message=f"Key revoked: {key_id[:8]}..."))
    
    return redirect(url_for('admin.api_keys', message="Key not found"))

@admin_bp.route('/clear-data')
@login_required
def clear_data():
    """Show clear data options page."""
    message = request.args.get('message', '')
    error = request.args.get('error', '')
    
    # Get current counts
    bounty_data = load_data()
    submissions_data = load_submissions()
    external_data = load_external_tasks()
    
    counts = {
        "bounty_reviews": len(bounty_data.get("reviews", {})),
        "bounty_payouts": len(bounty_data.get("payouts", [])),
        "task_submissions": len(submissions_data.get("submissions", [])),
        "external_tasks": len(external_data.get("tasks", []))
    }
    
    return render_template_string(CLEAR_DATA_HTML, counts=counts, message=message, error=error)

@admin_bp.route('/clear-data/execute', methods=['POST'])
@login_required
def clear_data_execute():
    """Execute data clearing based on selections."""
    cleared = []
    
    if request.form.get('clear_bounty_reviews'):
        save_data({"reviews": {}, "payouts": [], "history": []})
        cleared.append("Bounty reviews")
    
    if request.form.get('clear_task_submissions'):
        save_submissions({"submissions": []})
        cleared.append("Task submissions")
    
    if request.form.get('clear_external_tasks'):
        # Save empty external tasks
        try:
            os.makedirs(os.path.dirname(EXTERNAL_TASKS_FILE), exist_ok=True)
            with open(EXTERNAL_TASKS_FILE, 'w') as f:
                json.dump({"tasks": []}, f, indent=2)
            cleared.append("External tasks")
        except Exception as e:
            return redirect(url_for('admin.clear_data', error=f"Failed to clear external tasks: {e}"))
    
    if cleared:
        return redirect(url_for('admin.clear_data', message=f"Cleared: {', '.join(cleared)}"))
    else:
        return redirect(url_for('admin.clear_data', error="Nothing selected"))

CLEAR_DATA_HTML = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Clear Data - WattCoin Admin</title>
    <script src="https://cdn.tailwindcss.com"></script>
    <style>body { background: #0a0a0a; color: #e5e5e5; }</style>
</head>
<body class="p-8">
    <div class="max-w-2xl mx-auto">
        <div class="flex justify-between items-center mb-6">
            <div>
                <h1 class="text-2xl font-bold text-green-400">⚡ WattCoin Admin</h1>
                <p class="text-gray-500 text-sm">v2.1.0 | Clear Test Data</p>
            </div>
            <a href="{{ url_for('admin.logout') }}" class="text-gray-400 hover:text-red-400 text-sm">Logout</a>
        </div>
        
        <!-- Nav Tabs -->
        <div class="flex gap-1 mb-6 border-b border-gray-700">
            <a href="{{ url_for('admin.dashboard') }}" 
               class="px-4 py-2 text-sm font-medium border-b-2 border-transparent text-gray-400 hover:text-gray-200">
                🎯 PR Bounties
            </a>
            <a href="{{ url_for('admin.submissions') }}" 
               class="px-4 py-2 text-sm font-medium border-b-2 border-transparent text-gray-400 hover:text-gray-200">
                📋 Agent Tasks
            </a>
            <a href="{{ url_for('admin.api_keys') }}" 
               class="px-4 py-2 text-sm font-medium border-b-2 border-transparent text-gray-400 hover:text-gray-200">
                🔑 Scraper Keys
            </a>
            <a href="{{ url_for('admin.clear_data') }}" 
               class="px-4 py-2 text-sm font-medium border-b-2 border-green-400 text-green-400">
                🗑️ Clear Data
            </a>
        </div>
        
        {% if message %}
        <div class="bg-green-900/50 border border-green-500 text-green-300 px-4 py-2 rounded mb-6">{{ message }}</div>
        {% endif %}
        
        {% if error %}
        <div class="bg-red-900/50 border border-red-500 text-red-300 px-4 py-2 rounded mb-6">{{ error }}</div>
        {% endif %}
        
        <form method="POST" action="{{ url_for('admin.clear_data_execute') }}" class="bg-gray-900 rounded-lg p-6">
            <p class="text-yellow-400 text-sm mb-6">⚠️ This action cannot be undone. Only clear test data, not real usage.</p>
            
            <div class="space-y-4">
                <label class="flex items-center gap-3 p-4 bg-gray-800 rounded-lg cursor-pointer hover:bg-gray-750">
                    <input type="checkbox" name="clear_bounty_reviews" class="w-5 h-5 rounded">
                    <div>
                        <div class="font-medium">Bounty Reviews</div>
                        <div class="text-gray-500 text-sm">{{ counts.bounty_reviews }} reviews, {{ counts.bounty_payouts }} payouts</div>
                    </div>
                </label>
                
                <label class="flex items-center gap-3 p-4 bg-gray-800 rounded-lg cursor-pointer hover:bg-gray-750">
                    <input type="checkbox" name="clear_task_submissions" class="w-5 h-5 rounded">
                    <div>
                        <div class="font-medium">Task Submissions</div>
                        <div class="text-gray-500 text-sm">{{ counts.task_submissions }} submissions</div>
                    </div>
                </label>
                
                <label class="flex items-center gap-3 p-4 bg-gray-800 rounded-lg cursor-pointer hover:bg-gray-750">
                    <input type="checkbox" name="clear_external_tasks" class="w-5 h-5 rounded">
                    <div>
                        <div class="font-medium">External Tasks</div>
                        <div class="text-gray-500 text-sm">{{ counts.external_tasks }} tasks (agent-posted)</div>
                    </div>
                </label>
            </div>
            
            <div class="mt-6 flex gap-3">
                <button type="submit" class="bg-red-600 hover:bg-red-700 text-white font-medium px-6 py-2 rounded-lg">
                    Clear Selected
                </button>
                <a href="{{ url_for('admin.dashboard') }}" class="bg-gray-700 hover:bg-gray-600 text-white font-medium px-6 py-2 rounded-lg">
                    Cancel
                </a>
            </div>
        </form>
    </div>
</body>
</html>
"""

# =============================================================================
# SUBMISSIONS PAGE
# =============================================================================

SUBMISSIONS_FILE = "/app/data/task_submissions.json"

def load_submissions():
    """Load task submissions."""
    try:
        with open(SUBMISSIONS_FILE, 'r') as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {"submissions": []}

def save_submissions(data):
    """Save task submissions."""
    try:
        os.makedirs(os.path.dirname(SUBMISSIONS_FILE), exist_ok=True)
        with open(SUBMISSIONS_FILE, 'w') as f:
            json.dump(data, f, indent=2)
        return True
    except:
        return False

EXTERNAL_TASKS_FILE = "/app/data/external_tasks.json"

def load_external_tasks():
    """Load external tasks from JSON file."""
    try:
        with open(EXTERNAL_TASKS_FILE, 'r') as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {"tasks": []}

SUBMISSIONS_HTML = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Agent Task Submissions - WattCoin Admin</title>
    <script src="https://cdn.tailwindcss.com"></script>
    <style>
        body { background: #0a0a0a; color: #e5e5e5; }
        .truncate-id { max-width: 100px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
    </style>
</head>
<body class="p-8">
    <div class="max-w-6xl mx-auto">
        <!-- Header -->
        <div class="flex justify-between items-center mb-4">
            <div>
                <h1 class="text-2xl font-bold text-green-400">⚡ WattCoin Admin</h1>
                <p class="text-gray-500 text-sm">v2.1.0 | Agent Task Submissions + External Tasks Monitor</p>
            </div>
            <a href="{{ url_for('admin.logout') }}" class="text-gray-400 hover:text-red-400 text-sm">Logout</a>
        </div>
        
        <!-- Nav Tabs -->
        <div class="flex gap-1 mb-6 border-b border-gray-700">
            <a href="{{ url_for('admin.dashboard') }}" 
               class="px-4 py-2 text-sm font-medium border-b-2 border-transparent text-gray-400 hover:text-gray-200">
                🎯 PR Bounties
            </a>
            <a href="{{ url_for('admin.submissions') }}" 
               class="px-4 py-2 text-sm font-medium border-b-2 border-green-400 text-green-400">
                📋 Agent Tasks
            </a>
            <a href="{{ url_for('admin.api_keys') }}" 
               class="px-4 py-2 text-sm font-medium border-b-2 border-transparent text-gray-400 hover:text-gray-200">
                🔑 Scraper Keys
            </a>
            <a href="{{ url_for('admin.clear_data') }}" 
               class="px-4 py-2 text-sm font-medium border-b-2 border-transparent text-gray-400 hover:text-gray-200">
                🗑️ Clear Data
            </a>
        </div>
        
        {% if message %}
        <div class="bg-green-900/50 border border-green-500 text-green-300 px-4 py-2 rounded mb-6">{{ message }}</div>
        {% endif %}
        
        {% if error %}
        <div class="bg-red-900/50 border border-red-500 text-red-300 px-4 py-2 rounded mb-6">{{ error }}</div>
        {% endif %}
        
        <!-- Stats -->
        <div class="grid grid-cols-4 gap-4 mb-8">
            <div class="bg-gray-800 rounded-lg p-4">
                <div class="text-3xl font-bold text-yellow-400">{{ stats.pending }}</div>
                <div class="text-gray-500 text-sm">Pending Review</div>
            </div>
            <div class="bg-gray-800 rounded-lg p-4">
                <div class="text-3xl font-bold text-blue-400">{{ stats.approved }}</div>
                <div class="text-gray-500 text-sm">Approved</div>
            </div>
            <div class="bg-gray-800 rounded-lg p-4">
                <div class="text-3xl font-bold text-green-400">{{ stats.paid }}</div>
                <div class="text-gray-500 text-sm">Paid</div>
            </div>
            <div class="bg-gray-800 rounded-lg p-4">
                <div class="text-3xl font-bold text-red-400">{{ stats.rejected }}</div>
                <div class="text-gray-500 text-sm">Rejected</div>
            </div>
        </div>
        
        <!-- External Tasks Monitor -->
        {% if external_tasks %}
        <div class="bg-gray-900 rounded-lg p-6 mb-6 border border-purple-900">
            <h2 class="text-lg font-bold text-purple-400 mb-4">🌐 External Tasks (Agent Posted) - {{ external_tasks|length }}</h2>
            <div class="grid grid-cols-4 gap-3 mb-4">
                <div class="bg-gray-800 rounded p-3">
                    <div class="text-xl font-bold text-green-400">{{ ext_stats.open }}</div>
                    <div class="text-gray-500 text-xs">Open</div>
                </div>
                <div class="bg-gray-800 rounded p-3">
                    <div class="text-xl font-bold text-blue-400">{{ ext_stats.completed }}</div>
                    <div class="text-gray-500 text-xs">Completed</div>
                </div>
                <div class="bg-gray-800 rounded p-3">
                    <div class="text-xl font-bold text-yellow-400">{{ "{:,}".format(ext_stats.total_posted) }}</div>
                    <div class="text-gray-500 text-xs">Total WATT Posted</div>
                </div>
                <div class="bg-gray-800 rounded p-3">
                    <div class="text-xl font-bold text-green-400">{{ "{:,}".format(ext_stats.total_paid) }}</div>
                    <div class="text-gray-500 text-xs">Total WATT Paid</div>
                </div>
            </div>
            <table class="w-full text-sm">
                <thead>
                    <tr class="text-gray-400 border-b border-gray-700">
                        <th class="text-left pb-2">ID</th>
                        <th class="text-left pb-2">Title</th>
                        <th class="text-right pb-2">WATT</th>
                        <th class="text-left pb-2">Poster</th>
                        <th class="text-left pb-2">Status</th>
                        <th class="text-left pb-2">Created</th>
                    </tr>
                </thead>
                <tbody>
                {% for task in external_tasks[-15:] | reverse %}
                    <tr class="border-b border-gray-800">
                        <td class="py-2 font-mono text-xs text-purple-400">{{ task.id }}</td>
                        <td class="py-2">{{ task.title[:40] }}{% if task.title|length > 40 %}...{% endif %}</td>
                        <td class="py-2 text-right font-mono text-green-400">{{ "{:,}".format(task.amount) }}</td>
                        <td class="py-2 font-mono text-xs">{{ task.poster[:8] }}...</td>
                        <td class="py-2">
                            {% if task.status == 'open' %}
                            <span class="px-2 py-1 bg-green-900 text-green-300 rounded text-xs">open</span>
                            {% elif task.status == 'completed' %}
                            <span class="px-2 py-1 bg-blue-900 text-blue-300 rounded text-xs">completed</span>
                            {% else %}
                            <span class="px-2 py-1 bg-gray-700 text-gray-300 rounded text-xs">{{ task.status }}</span>
                            {% endif %}
                        </td>
                        <td class="py-2 text-gray-500 text-xs">{{ task.created_at[:10] }}</td>
                    </tr>
                {% endfor %}
                </tbody>
            </table>
        </div>
        {% else %}
        <div class="bg-gray-900 rounded-lg p-6 mb-6 border border-purple-900/50">
            <h2 class="text-lg font-bold text-purple-400 mb-2">🌐 External Tasks</h2>
            <p class="text-gray-500">No external tasks posted yet. Agents can post tasks via POST /api/v1/tasks</p>
        </div>
        {% endif %}
        
        <!-- Pending Submissions -->
        {% if pending %}
        <div class="bg-gray-900 rounded-lg p-6 mb-6">
            <h2 class="text-lg font-bold text-yellow-400 mb-4">⏳ Pending Review ({{ pending|length }})</h2>
            <table class="w-full text-sm">
                <thead>
                    <tr class="text-gray-500 border-b border-gray-700">
                        <th class="text-left pb-2">ID</th>
                        <th class="text-left pb-2">Task</th>
                        <th class="text-left pb-2">Wallet</th>
                        <th class="text-right pb-2">Amount</th>
                        <th class="text-left pb-2">AI Review</th>
                        <th class="text-left pb-2">Submitted</th>
                        <th class="text-right pb-2">Actions</th>
                    </tr>
                </thead>
                <tbody>
                {% for sub in pending %}
                    <tr class="border-b border-gray-800">
                        <td class="py-3 font-mono text-xs truncate-id" title="{{ sub.id }}">{{ sub.id }}</td>
                        <td class="py-3">
                            <a href="https://github.com/WattCoin-Org/wattcoin/issues/{{ sub.task_id }}" 
                               target="_blank" class="text-blue-400 hover:underline">
                                #{{ sub.task_id }}
                            </a>
                            <span class="text-gray-500">{{ sub.task_title[:30] }}...</span>
                        </td>
                        <td class="py-3 font-mono text-xs">{{ sub.wallet[:8] }}...</td>
                        <td class="py-3 text-right text-green-400">{{ "{:,}".format(sub.amount) }} WATT</td>
                        <td class="py-3">
                            {% if sub.ai_review %}
                                {% if sub.ai_review.pass %}
                                    <span class="text-green-400">✓ {{ (sub.ai_review.confidence * 100)|int }}%</span>
                                {% else %}
                                    <span class="text-red-400">✗ {{ (sub.ai_review.confidence * 100)|int }}%</span>
                                {% endif %}
                            {% else %}
                                <span class="text-gray-500">-</span>
                            {% endif %}
                        </td>
                        <td class="py-3 text-gray-500 text-xs">{{ sub.submitted_at[:10] }}</td>
                        <td class="py-3 text-right">
                            <form action="{{ url_for('admin.approve_submission', sub_id=sub.id) }}" method="POST" class="inline">
                                <button type="submit" class="px-3 py-1 bg-green-600 hover:bg-green-700 rounded text-xs mr-1">
                                    ✓ Approve
                                </button>
                            </form>
                            <form action="{{ url_for('admin.reject_submission', sub_id=sub.id) }}" method="POST" class="inline">
                                <button type="submit" class="px-3 py-1 bg-red-600 hover:bg-red-700 rounded text-xs">
                                    ✗ Reject
                                </button>
                            </form>
                        </td>
                    </tr>
                    <tr class="border-b border-gray-800 bg-gray-800/30">
                        <td colspan="7" class="py-2 px-4">
                            <details class="text-xs">
                                <summary class="cursor-pointer text-gray-400 hover:text-gray-200">View result</summary>
                                <pre class="mt-2 p-2 bg-black rounded overflow-x-auto text-green-400">{{ sub.result | tojson(indent=2) }}</pre>
                                {% if sub.ai_review and sub.ai_review.reason %}
                                <p class="mt-2 text-gray-400"><strong>AI:</strong> {{ sub.ai_review.reason }}</p>
                                {% endif %}
                            </details>
                        </td>
                    </tr>
                {% endfor %}
                </tbody>
            </table>
        </div>
        {% endif %}
        
        <!-- Payout History -->
        <div class="bg-gray-900 rounded-lg p-6">
            <h2 class="text-lg font-bold text-green-400 mb-4">💰 Payout History ({{ paid|length }})</h2>
            {% if paid %}
            <table class="w-full text-sm">
                <thead>
                    <tr class="text-gray-500 border-b border-gray-700">
                        <th class="text-left pb-2">Task</th>
                        <th class="text-left pb-2">Wallet</th>
                        <th class="text-right pb-2">Amount</th>
                        <th class="text-left pb-2">TX</th>
                        <th class="text-left pb-2">Paid At</th>
                    </tr>
                </thead>
                <tbody>
                {% for sub in paid %}
                    <tr class="border-b border-gray-800">
                        <td class="py-3">
                            <a href="https://github.com/WattCoin-Org/wattcoin/issues/{{ sub.task_id }}" 
                               target="_blank" class="text-blue-400 hover:underline">
                                #{{ sub.task_id }}
                            </a>
                            {{ sub.task_title[:25] }}...
                        </td>
                        <td class="py-3 font-mono text-xs">{{ sub.wallet[:12] }}...</td>
                        <td class="py-3 text-right text-green-400">{{ "{:,}".format(sub.amount) }} WATT</td>
                        <td class="py-3">
                            {% if sub.tx_signature %}
                            <a href="https://solscan.io/tx/{{ sub.tx_signature }}" target="_blank" 
                               class="text-blue-400 hover:underline text-xs font-mono">
                                {{ sub.tx_signature[:12] }}...
                            </a>
                            {% else %}
                            <span class="text-gray-500">-</span>
                            {% endif %}
                        </td>
                        <td class="py-3 text-gray-500 text-xs">{{ sub.paid_at[:16] if sub.paid_at else '-' }}</td>
                    </tr>
                {% endfor %}
                </tbody>
            </table>
            {% else %}
            <p class="text-gray-500">No payouts yet.</p>
            {% endif %}
        </div>
        
        <!-- Rejected -->
        {% if rejected %}
        <div class="bg-gray-900 rounded-lg p-6 mt-6">
            <h2 class="text-lg font-bold text-red-400 mb-4">❌ Rejected ({{ rejected|length }})</h2>
            <table class="w-full text-sm">
                <thead>
                    <tr class="text-gray-500 border-b border-gray-700">
                        <th class="text-left pb-2">Task</th>
                        <th class="text-left pb-2">Wallet</th>
                        <th class="text-left pb-2">Reason</th>
                        <th class="text-left pb-2">Date</th>
                    </tr>
                </thead>
                <tbody>
                {% for sub in rejected[-10:] %}
                    <tr class="border-b border-gray-800">
                        <td class="py-3">
                            <a href="https://github.com/WattCoin-Org/wattcoin/issues/{{ sub.task_id }}" 
                               target="_blank" class="text-blue-400 hover:underline">
                                #{{ sub.task_id }}
                            </a>
                        </td>
                        <td class="py-3 font-mono text-xs">{{ sub.wallet[:8] }}...</td>
                        <td class="py-3 text-gray-400 text-xs">
                            {{ sub.ai_review.reason[:60] if sub.ai_review else sub.get('reject_reason', '-') }}...
                        </td>
                        <td class="py-3 text-gray-500 text-xs">{{ sub.submitted_at[:10] }}</td>
                    </tr>
                {% endfor %}
                </tbody>
            </table>
        </div>
        {% endif %}
        
    </div>
</body>
</html>
"""

@admin_bp.route('/submissions')
@login_required
def submissions():
    """Task submissions management page."""
    message = request.args.get('message', '')
    error = request.args.get('error', '')
    
    data = load_submissions()
    subs = data.get("submissions", [])
    
    # Categorize
    pending = [s for s in subs if s.get("status") in ["pending_review", "approved"]]
    paid = [s for s in subs if s.get("status") == "paid"]
    rejected = [s for s in subs if s.get("status") == "rejected"]
    
    # Sort by date descending
    pending.sort(key=lambda x: x.get("submitted_at", ""), reverse=True)
    paid.sort(key=lambda x: x.get("paid_at", x.get("submitted_at", "")), reverse=True)
    rejected.sort(key=lambda x: x.get("submitted_at", ""), reverse=True)
    
    stats = {
        "pending": len([s for s in subs if s.get("status") == "pending_review"]),
        "approved": len([s for s in subs if s.get("status") == "approved"]),
        "paid": len(paid),
        "rejected": len(rejected)
    }
    
    # Load external tasks
    ext_data = load_external_tasks()
    external_tasks = ext_data.get("tasks", [])
    ext_stats = {
        "open": len([t for t in external_tasks if t.get("status") == "open"]),
        "completed": len([t for t in external_tasks if t.get("status") == "completed"]),
        "total_posted": sum(t.get("amount", 0) for t in external_tasks),
        "total_paid": sum(t.get("amount", 0) for t in external_tasks if t.get("status") == "completed")
    }
    
    return render_template_string(SUBMISSIONS_HTML,
        stats=stats,
        pending=pending,
        paid=paid,
        rejected=rejected,
        external_tasks=external_tasks,
        ext_stats=ext_stats,
        message=message,
        error=error
    )

@admin_bp.route('/submissions/approve/<sub_id>', methods=['POST'])
@login_required
def approve_submission(sub_id):
    """Approve a pending submission and trigger payout."""
    data = load_submissions()
    
    for sub in data.get("submissions", []):
        if sub.get("id") == sub_id:
            if sub.get("status") == "paid":
                return redirect(url_for('admin.submissions', error="Already paid"))
            
            # Try to send payout
            from api_tasks import send_watt_payout
            success, result = send_watt_payout(sub["wallet"], sub["amount"])
            
            if success:
                sub["status"] = "paid"
                sub["tx_signature"] = result
                sub["paid_at"] = datetime.now().isoformat() + "Z"
                sub["approved_by"] = "admin"
                save_submissions(data)
                
                # Post GitHub comment
                try:
                    comment = f"""## ✅ Task Completed - Admin Approved

**Submission ID:** `{sub_id}`
**Agent Wallet:** `{sub['wallet']}`
**Payout:** {sub['amount']:,} WATT
**TX:** [{result[:16]}...](https://solscan.io/tx/{result})

---
*Manually approved by admin*
"""
                    requests.post(
                        f"https://api.github.com/repos/{REPO}/issues/{sub['task_id']}/comments",
                        headers={"Authorization": f"token {GITHUB_TOKEN}", "Accept": "application/vnd.github.v3+json"},
                        json={"body": comment},
                        timeout=10
                    )
                except:
                    pass
                
                return redirect(url_for('admin.submissions', message=f"Paid {sub['amount']:,} WATT! TX: {result[:12]}..."))
            else:
                return redirect(url_for('admin.submissions', error=f"Payout failed: {result}"))
    
    return redirect(url_for('admin.submissions', error="Submission not found"))

@admin_bp.route('/process_payments', methods=['POST'])
def process_payment_queue():
    """Process all pending payments in the queue"""
    import json
    import os
    from datetime import datetime
    
    queue_file = "/app/data/payment_queue.json"
    
    if not os.path.exists(queue_file):
        return jsonify({"success": False, "message": "No payments in queue"}), 404
    
    # Load queue
    with open(queue_file, 'r') as f:
        queue = json.load(f)
    
    results = []
    updated_queue = []
    
    for payment in queue:
        if payment.get("status") != "pending":
            updated_queue.append(payment)
            continue
        
        pr_number = payment["pr_number"]
        wallet = payment["wallet"]
        amount = payment["amount"]
        bounty_issue_id = payment.get("bounty_issue_id")
        review_score = payment.get("review_score")
        
        # Import execute_auto_payment from api_webhooks
        from api_webhooks import execute_auto_payment, post_github_comment
        
        # Execute payment
        tx_signature, error = execute_auto_payment(pr_number, wallet, amount, bounty_issue_id=bounty_issue_id, review_score=review_score)
        
        if tx_signature:
            payment["status"] = "completed"
            payment["tx_signature"] = tx_signature
            payment["processed_at"] = datetime.utcnow().isoformat()
            results.append(f"✅ PR #{pr_number}: {amount:,} WATT → {tx_signature[:16]}...")
            
            # Post TX confirmation comment to PR
            try:
                comment = (
                    f"✅ **Bounty paid!** {amount:,} WATT sent.\n\n"
                    f"**TX:** [View on Solscan](https://solscan.io/tx/{tx_signature})\n\n"
                    f"Thank you for contributing to the WattCoin agent economy! ⚡🤖"
                )
                post_github_comment(pr_number, comment)
            except Exception as comment_err:
                print(f"[QUEUE] Warning: Failed to post PR comment for #{pr_number}: {comment_err}", flush=True)
        else:
            payment["status"] = "failed"
            payment["error"] = error
            payment["failed_at"] = datetime.utcnow().isoformat()
            results.append(f"❌ PR #{pr_number}: {error}")
        
        updated_queue.append(payment)
    
    # Save updated queue
    with open(queue_file, 'w') as f:
        json.dump(updated_queue, f, indent=2)
    
    return jsonify({
        "success": True,
        "processed": len(results),
        "results": results
    })


@admin_bp.route('/queue_manual_payment', methods=['POST'])
@login_required
def queue_manual_payment():
    """Manually queue a payment for a merged PR that missed auto-payment.
    Goes through the same pipeline as automated payments (on-chain memo, PR comment, Discord).
    """
    import json
    import os
    from datetime import datetime
    
    pr_number = request.form.get('pr_number', type=int)
    wallet = request.form.get('wallet', '').strip()
    amount = request.form.get('amount', type=int)
    bounty_issue_id = request.form.get('bounty_issue_id', type=int)
    reason = request.form.get('reason', 'Manual admin payment').strip()
    
    # Validation
    errors = []
    if not pr_number:
        errors.append("PR number required")
    if not wallet or len(wallet) < 32:
        errors.append("Valid Solana wallet address required")
    if not amount or amount < 1:
        errors.append("Amount must be > 0 WATT")
    if amount and amount > 100000:
        errors.append("Amount exceeds 100K WATT safety limit — contact admin for larger payouts")
    
    if errors:
        return redirect(url_for('admin.dashboard', error=" | ".join(errors)))
    
    queue_file = "/app/data/payment_queue.json"
    os.makedirs("/app/data", exist_ok=True)
    
    # Load existing queue
    queue = []
    if os.path.exists(queue_file):
        try:
            with open(queue_file, 'r') as f:
                queue = json.load(f)
        except:
            queue = []
    
    # Add manual payment entry
    payment = {
        "pr_number": pr_number,
        "wallet": wallet,
        "amount": amount,
        "bounty_issue_id": bounty_issue_id,
        "review_score": None,
        "author": "manual_admin_payout",
        "queued_at": datetime.utcnow().isoformat(),
        "status": "pending",
        "manual": True,
        "reason": reason
    }
    
    queue.append(payment)
    
    with open(queue_file, 'w') as f:
        json.dump(queue, f, indent=2)
    
    print(f"[ADMIN] Manual payment queued: PR #{pr_number}, {amount:,} WATT to {wallet[:8]}... Reason: {reason}", flush=True)
    
    return redirect(url_for('admin.dashboard', 
        message=f"✅ Queued: {amount:,} WATT for PR #{pr_number} → {wallet[:8]}... Use Process Queue to send."))


@admin_bp.route('/clear_payment_queue', methods=['POST'])
@login_required
def clear_payment_queue():
    """Clear all pending payments from the queue (keeps completed/failed for history)."""
    import json
    import os
    
    queue_file = "/app/data/payment_queue.json"
    
    if not os.path.exists(queue_file):
        return redirect(url_for('admin.dashboard', message="Queue already empty"))
    
    with open(queue_file, 'r') as f:
        queue = json.load(f)
    
    pending_count = len([p for p in queue if p.get("status") == "pending"])
    
    # Keep completed/failed for history, remove only pending
    queue = [p for p in queue if p.get("status") != "pending"]
    
    with open(queue_file, 'w') as f:
        json.dump(queue, f, indent=2)
    
    print(f"[ADMIN] Cleared {pending_count} pending payments from queue", flush=True)
    
    return redirect(url_for('admin.dashboard', message=f"🗑️ Cleared {pending_count} pending payment(s) from queue"))


def reject_submission(sub_id):
    """Reject a pending submission."""
    data = load_submissions()
    
    for sub in data.get("submissions", []):
        if sub.get("id") == sub_id:
            if sub.get("status") == "paid":
                return redirect(url_for('admin.submissions', error="Cannot reject - already paid"))
            
            sub["status"] = "rejected"
            sub["reject_reason"] = "Rejected by admin"
            sub["rejected_at"] = datetime.now().isoformat() + "Z"
            save_submissions(data)
            
            return redirect(url_for('admin.submissions', message=f"Submission {sub_id[:12]}... rejected"))
    
    return redirect(url_for('admin.submissions', error="Submission not found"))

# =============================================================================
# BAN MANAGEMENT
# =============================================================================

def _load_banned_users():
    """Load banned users from data file."""
    banned_file = os.path.join("/app/data", "banned_users.json")
    try:
        with open(banned_file, 'r') as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {"banned": [], "updated": None}

def _save_banned_users(data):
    """Save banned users to data file."""
    banned_file = os.path.join("/app/data", "banned_users.json")
    os.makedirs("/app/data", exist_ok=True)
    with open(banned_file, 'w') as f:
        json.dump(data, f, indent=2)

@admin_bp.route('/ban/<username>', methods=['POST'])
@login_required
def ban_user(username):
    """Ban a GitHub user from the bounty system."""
    data = _load_banned_users()
    banned_list = [u.lower() for u in data.get("banned", [])]
    
    if username.lower() not in banned_list:
        data.setdefault("banned", []).append(username)
        data["updated"] = datetime.now().isoformat() + "Z"
        _save_banned_users(data)
    
    return redirect(url_for('admin.dashboard', message=f"🚫 Banned: {username}"))

@admin_bp.route('/unban/<username>', methods=['POST'])
@login_required
def unban_user(username):
    """Unban a GitHub user."""
    data = _load_banned_users()
    data["banned"] = [u for u in data.get("banned", []) if u.lower() != username.lower()]
    data["updated"] = datetime.now().isoformat() + "Z"
    _save_banned_users(data)
    
    return redirect(url_for('admin.dashboard', message=f"✅ Unbanned: {username}"))

@admin_bp.route('/api/ban/<username>', methods=['POST'])
@login_required
def api_ban_user(username):
    """API endpoint to ban a user (for programmatic access)."""
    data = _load_banned_users()
    banned_list = [u.lower() for u in data.get("banned", [])]
    
    if username.lower() in banned_list:
        return jsonify({"success": True, "message": f"{username} already banned", "banned": data["banned"]})
    
    data.setdefault("banned", []).append(username)
    data["updated"] = datetime.now().isoformat() + "Z"
    _save_banned_users(data)
    
    return jsonify({"success": True, "message": f"Banned {username}", "banned": data["banned"]})


