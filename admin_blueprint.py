"""
WattCoin Bounty Admin Dashboard - Blueprint v1.2.0
Admin routes for managing bounty PR reviews.

Requires env vars:
    ADMIN_PASSWORD - Dashboard login password
    GROK_API_KEY - For PR reviews
    GITHUB_TOKEN - For GitHub API calls

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
GROK_API_KEY = os.getenv("GROK_API_KEY", "")
REPO = "WattCoin-Org/wattcoin"
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
# GROK REVIEW
# =============================================================================

def call_grok_review(pr_info):
    """Send PR to Grok for review."""
    if not GROK_API_KEY:
        return {"error": "GROK_API_KEY not configured"}
    
    prompt = f"""You are a strict bounty reviewer for WattCoin agent-native OSS.
Review this Pull Request for a bounty task.

PR #{pr_info['number']}: {pr_info['title']}
Author: {pr_info['author']}
Description: {pr_info['body'][:1500]}

DIFF:
```
{pr_info['diff']}
```

Check:
1. Does it solve the stated task fully?
2. Code quality (clean, readable, follows existing patterns)?
3. Security (no backdoors, hardcoded secrets, suspicious patterns)?
4. Tests (added/updated if applicable)?
5. Completeness (% done, what's missing)?

Output in this exact format:

**RECOMMENDATION:** Approve / Request changes / Reject
**CONFIDENCE:** High / Medium / Low
**COMPLETENESS:** X%

**Summary:** 2-3 sentence summary of the PR quality and what it does.

**Issues Found:**
- List any problems (or "None" if clean)

**Suggested Payout:** 100% / X% / 0% of bounty
"""

    try:
        resp = requests.post(
            "https://api.x.ai/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {GROK_API_KEY}",
                "Content-Type": "application/json"
            },
            json={
                "model": "grok-4-1-fast-reasoning",
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0.2,
                "max_tokens": 1500
            },
            timeout=60
        )
        
        if resp.status_code == 200:
            content = resp.json()["choices"][0]["message"]["content"]
            return {
                "success": True,
                "review": content,
                "timestamp": datetime.now().isoformat()
            }
        else:
            return {"error": f"Grok API error: {resp.status_code}"}
    except Exception as e:
        return {"error": f"Grok request failed: {str(e)}"}

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
    <title>WattCoin Bounty Dashboard</title>
    <script src="https://cdn.tailwindcss.com"></script>
</head>
<body class="bg-gray-900 text-gray-100 min-h-screen">
    <div class="max-w-6xl mx-auto p-6">
        <!-- Header -->
        <div class="flex justify-between items-center mb-4">
            <div>
                <h1 class="text-2xl font-bold text-green-400">⚡ WattCoin Admin</h1>
                <p class="text-gray-500 text-sm">v1.3.0 | {{ repo }}</p>
            </div>
            <a href="{{ url_for('admin.logout') }}" class="text-gray-400 hover:text-red-400 text-sm">Logout</a>
        </div>
        
        <!-- Nav Tabs -->
        <div class="flex gap-1 mb-6 border-b border-gray-700">
            <a href="{{ url_for('admin.dashboard') }}" 
               class="px-4 py-2 text-sm font-medium border-b-2 border-green-400 text-green-400">
                🎯 Bounties
            </a>
            <a href="{{ url_for('admin.api_keys') }}" 
               class="px-4 py-2 text-sm font-medium border-b-2 border-transparent text-gray-400 hover:text-gray-200">
                🔑 API Keys
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
            <div class="bg-gray-800 rounded-lg p-4 border-l-4 {% if pr.number|string in reviews %}border-green-500{% else %}border-gray-600{% endif %}">
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
                    <div class="flex gap-2">
                        {% if pr.number|string in reviews %}
                        <span class="px-3 py-1 bg-green-900/50 text-green-400 rounded text-sm">Reviewed</span>
                        {% endif %}
                        <a href="{{ url_for('admin.pr_detail', pr_number=pr.number) }}" 
                           class="px-4 py-1 bg-blue-600 hover:bg-blue-700 rounded text-sm transition">
                            View
                        </a>
                    </div>
                </div>
            </div>
            {% endfor %}
        </div>
        {% else %}
        <div class="bg-gray-800 rounded-lg p-8 text-center text-gray-500">
            No open pull requests
        </div>
        {% endif %}
        
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
            <button onclick="confirmClear()" class="text-xs text-gray-500 hover:text-red-400 transition">
                🗑️ Clear All Data
            </button>
        </div>
    </div>
    
    <script>
        function confirmClear() {
            if (confirm('⚠️ This will delete ALL reviews and payouts data. Are you sure?')) {
                if (confirm('This action cannot be undone. Type "DELETE" mentally and click OK to confirm.')) {
                    window.location.href = '{{ url_for("admin.clear_data") }}';
                }
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
        
        <!-- Grok Review Section -->
        <div class="bg-gray-800 rounded-lg p-6 mb-6">
            <h2 class="text-lg font-semibold mb-4 flex items-center gap-2">
                🤖 Grok Review
                {% if review %}
                <span class="text-xs text-gray-500">{{ review.timestamp[:16] }}</span>
                {% endif %}
            </h2>
            
            {% if review %}
            <div class="bg-gray-900 rounded p-4 mb-4">
                <pre class="whitespace-pre-wrap text-sm">{{ review.review }}</pre>
            </div>
            {% else %}
            <p class="text-gray-500 mb-4">No Grok review yet.</p>
            {% endif %}
            
            <form method="POST" action="{{ url_for('admin.trigger_review', pr_number=pr.number) }}">
                <button type="submit" class="px-4 py-2 bg-orange-600 hover:bg-orange-700 rounded transition">
                    {% if review %}🔄 Re-run Grok Review{% else %}🚀 Run Grok Review{% endif %}
                </button>
            </form>
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
                <strong>Source Wallet:</strong> 7vvNkG3JF3JpxLEavqZSkc5T3n9hHR98Uw23fbWdXVSF (bounty fund)
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
        const RPC_URL = 'https://rpc.ankr.com/solana';
        
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
    <title>API Keys - WattCoin Admin</title>
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
                <p class="text-gray-500 text-sm">v1.3.0 | {{ repo }}</p>
            </div>
            <a href="{{ url_for('admin.logout') }}" class="text-gray-400 hover:text-red-400 text-sm">Logout</a>
        </div>
        
        <!-- Nav Tabs -->
        <div class="flex gap-1 mb-6 border-b border-gray-700">
            <a href="{{ url_for('admin.dashboard') }}" 
               class="px-4 py-2 text-sm font-medium border-b-2 border-transparent text-gray-400 hover:text-gray-200">
                🎯 Bounties
            </a>
            <a href="{{ url_for('admin.api_keys') }}" 
               class="px-4 py-2 text-sm font-medium border-b-2 border-green-400 text-green-400">
                🔑 API Keys
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
    """PR detail page with Grok review."""
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
    """Trigger Grok review for a PR."""
    pr = get_pr_detail(pr_number)
    if not pr:
        return redirect(url_for('admin.dashboard', error=f"PR #{pr_number} not found"))
    
    result = call_grok_review(pr)
    
    if result.get("success"):
        data = load_data()
        data["reviews"][str(pr_number)] = {
            "review": result["review"],
            "timestamp": result["timestamp"],
            "pr_title": pr["title"],
            "author": pr["author"]
        }
        save_data(data)
        return redirect(url_for('admin.pr_detail', pr_number=pr_number, message="Grok review completed"))
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
                "payout_wallet": "7vvNkG3JF3JpxLEavqZSkc5T3n9hHR98Uw23fbWdXVSF",
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
        repo=REPO
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
    """Clear all reviews and payouts data."""
    save_data({"reviews": {}, "payouts": []})
    return redirect(url_for('admin.dashboard', message="All data cleared successfully"))
