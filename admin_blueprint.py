"""
WattCoin Bounty Admin Dashboard - Blueprint v1.1.0
Admin routes for managing bounty PR reviews.

Requires env vars:
    ADMIN_PASSWORD - Dashboard login password
    GROK_API_KEY - For PR reviews
    GITHUB_TOKEN - For GitHub API calls

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

def extract_bounty_amount(labels):
    """Extract bounty amount from PR labels."""
    for label in labels:
        if "bounty" in label.lower():
            # Try to extract number from label like "bounty:50000" or "bounty-50k"
            import re
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
        <div class="flex justify-between items-center mb-8">
            <div>
                <h1 class="text-2xl font-bold text-green-400">⚡ Bounty Admin Dashboard</h1>
                <p class="text-gray-500 text-sm">v1.1.0 | {{ repo }}</p>
            </div>
            <a href="{{ url_for('admin.logout') }}" class="text-gray-400 hover:text-red-400 text-sm">Logout</a>
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
        
        <!-- Payout Queue Link -->
        <div class="mt-8 pt-6 border-t border-gray-700">
            <a href="{{ url_for('admin.payouts') }}" class="text-green-400 hover:text-green-300">
                View Payout Queue →
            </a>
        </div>
    </div>
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
    </style>
</head>
<body class="bg-gray-900 text-gray-100 min-h-screen">
    <div id="toast" class="toast"></div>
    
    <div class="max-w-5xl mx-auto p-6">
        <a href="{{ url_for('admin.dashboard') }}" class="text-gray-500 hover:text-gray-300 text-sm mb-4 inline-block">
            ← Back to Dashboard
        </a>
        
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
                    <tr class="border-t border-gray-700">
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
                            <span class="px-2 py-1 rounded text-xs 
                                {% if payout.status == 'pending' %}bg-yellow-900/50 text-yellow-400
                                {% elif payout.status == 'paid' %}bg-green-900/50 text-green-400
                                {% endif %}">
                                {{ payout.status }}
                            </span>
                        </td>
                        <td class="px-4 py-3">
                            {% if payout.status == 'pending' and payout.wallet %}
                            <button onclick="copyWallet('{{ payout.wallet }}', {{ payout.amount }})"
                               class="px-3 py-1.5 bg-purple-600 hover:bg-purple-700 rounded text-sm font-medium transition inline-flex items-center gap-1">
                                📋 Copy Wallet
                            </button>
                            {% elif payout.status == 'pending' and not payout.wallet %}
                            <span class="text-xs text-red-400">No wallet</span>
                            {% else %}
                            <span class="text-xs text-gray-500">—</span>
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
            <p class="text-sm text-gray-500 mt-2">
                Copy contributor wallet, open Phantom, paste and send WATT.
            </p>
        </div>
        {% else %}
        <div class="bg-gray-800 rounded-lg p-8 text-center text-gray-500">
            No pending payouts
        </div>
        {% endif %}
    </div>
    
    <script>
        function copyWallet(wallet, amount) {
            navigator.clipboard.writeText(wallet).then(() => {
                const toast = document.getElementById('toast');
                toast.textContent = '✓ Copied! Send ' + amount.toLocaleString() + ' WATT to contributor';
                toast.classList.add('show');
                setTimeout(() => toast.classList.remove('show'), 3000);
            });
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
    bounty = extract_bounty_amount(pr.get("labels", [])) if pr else 0
    
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
    bounty = extract_bounty_amount(pr.get("labels", [])) if pr else 0
    
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
    
    # Backfill missing wallets from PR body
    updated = False
    for payout in payout_list:
        if not payout.get("wallet"):
            pr = get_pr_detail(payout.get("pr_number"))
            if pr:
                wallet = extract_wallet(pr.get("body", ""))
                if wallet:
                    payout["wallet"] = wallet
                    updated = True
    
    # Save if we backfilled any wallets
    if updated:
        save_data(data)
    
    return render_template_string(PAYOUTS_TEMPLATE,
        payouts=payout_list,
        repo=REPO
    )
