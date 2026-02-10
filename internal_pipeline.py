"""
Internal Pipeline Admin UI
Manage PRs from WattCoin-Org/wattcoin-internal
"""

import os
import json
import requests
import functools
from datetime import datetime
from flask import Blueprint, render_template_string, request, session, redirect, url_for, jsonify

# Create Blueprint
internal_bp = Blueprint('internal', __name__)

# Environment variables
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN", "")
INTERNAL_REPO = "WattCoin-Org/wattcoin-internal"
PUBLIC_REPO = "WattCoin-Org/wattcoin"
DATA_DIR = "data"
PR_REVIEWS_FILE = f"{DATA_DIR}/pr_reviews.json"

# =============================================================================
# AUTH DECORATOR
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
# GITHUB API HELPERS
# =============================================================================

def github_headers():
    """Get GitHub API headers with auth."""
    headers = {"Accept": "application/vnd.github.v3+json"}
    if GITHUB_TOKEN:
        headers["Authorization"] = f"token {GITHUB_TOKEN}"
    return headers


def get_internal_prs():
    """Fetch open PRs from internal repo."""
    try:
        url = f"https://api.github.com/repos/{INTERNAL_REPO}/pulls?state=open&per_page=50"
        resp = requests.get(url, headers=github_headers(), timeout=10)
        
        if resp.status_code == 200:
            prs = resp.json()
            return prs, None
        else:
            return [], f"GitHub API error: {resp.status_code}"
    except Exception as e:
        return [], f"Error fetching PRs: {str(e)}"


def get_pr_reviews():
    """Load PR reviews from data file, filter for internal repo."""
    try:
        if not os.path.exists(PR_REVIEWS_FILE):
            return []
        
        with open(PR_REVIEWS_FILE, 'r') as f:
            data = json.load(f)
            reviews = data.get("reviews", [])
            
            # Filter for internal repo only
            internal_reviews = [r for r in reviews if r.get("repo") == INTERNAL_REPO]
            return internal_reviews
    except Exception as e:
        print(f"[INTERNAL] Error loading reviews: {e}", flush=True)
        return []


def get_pr_files(pr_number):
    """Get files changed in a PR."""
    try:
        url = f"https://api.github.com/repos/{INTERNAL_REPO}/pulls/{pr_number}/files"
        resp = requests.get(url, headers=github_headers(), timeout=10)
        
        if resp.status_code == 200:
            return resp.json(), None
        else:
            return [], f"Error fetching files: {resp.status_code}"
    except Exception as e:
        return [], str(e)

# =============================================================================
# MAIN PAGE
# =============================================================================

@internal_bp.route('/admin/internal')
@login_required
def internal_page():
    """Internal pipeline admin page."""
    
    # Fetch PRs
    prs, pr_error = get_internal_prs()
    
    # Load review data
    reviews = get_pr_reviews()
    review_map = {r["pr_number"]: r for r in reviews}
    
    # Stats
    stats = {
        "open_prs": len(prs),
        "reviewed": len([p for p in prs if p["number"] in review_map]),
        "pending": len([p for p in prs if p["number"] not in review_map]),
    }
    
    return render_template_string(
        INTERNAL_TEMPLATE,
        prs=prs,
        review_map=review_map,
        stats=stats,
        error=pr_error
    )

# =============================================================================
# API ENDPOINTS
# =============================================================================

@internal_bp.route('/admin/api/internal/trigger-review', methods=['POST'])
@login_required
def trigger_review():
    """Trigger AI review for an internal PR."""
    data = request.get_json()
    pr_number = data.get('pr_number')
    
    if not pr_number:
        return jsonify({"error": "pr_number required"}), 400
    
    try:
        # Import and call trigger function from api_webhooks
        from api_webhooks import trigger_ai_review_internal
        
        review_result, error = trigger_ai_review_internal(pr_number)
        
        if error:
            return jsonify({"error": error}), 400
        
        return jsonify({
            "success": True,
            "pr_number": pr_number,
            "review": review_result
        })
        
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@internal_bp.route('/admin/api/internal/pr/<int:pr_number>/files')
@login_required
def pr_files(pr_number):
    """Get files changed in a PR."""
    files, error = get_pr_files(pr_number)
    
    if error:
        return jsonify({"error": error}), 400
    
    return jsonify({"files": files})

# =============================================================================
# TEMPLATE
# =============================================================================

INTERNAL_TEMPLATE = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Internal Pipeline - WattCoin Admin</title>
    <script src="https://cdn.tailwindcss.com"></script>
</head>
<body class="bg-gray-900 text-gray-100 min-h-screen">
    <div class="max-w-6xl mx-auto p-6">
        <!-- Header -->
        <div class="flex justify-between items-center mb-4">
            <div>
                <h1 class="text-2xl font-bold text-green-400">⚡ WattCoin Admin</h1>
                <p class="text-gray-500 text-sm">Internal Pipeline | Private Development</p>
            </div>
            <div class="flex items-center gap-3">
                <a href="{{ url_for('admin.logout') }}" class="text-gray-400 hover:text-red-400 text-sm">Logout</a>
            </div>
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
            <a href="{{ url_for('internal.internal_page') }}" 
               class="px-4 py-2 text-sm font-medium border-b-2 border-green-400 text-green-400">
                🔧 Internal Pipeline
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
        
        {% if error %}
        <div class="bg-red-900/50 border border-red-500 text-red-300 px-4 py-2 rounded mb-6">
            ⚠️ {{ error }}
        </div>
        {% endif %}
        
        <!-- Stats -->
        <div class="grid grid-cols-3 gap-4 mb-8">
            <div class="bg-gray-800 rounded-lg p-4">
                <div class="text-3xl font-bold text-blue-400">{{ stats.open_prs }}</div>
                <div class="text-gray-500 text-sm">Open PRs</div>
            </div>
            <div class="bg-gray-800 rounded-lg p-4">
                <div class="text-3xl font-bold text-green-400">{{ stats.reviewed }}</div>
                <div class="text-gray-500 text-sm">Reviewed</div>
            </div>
            <div class="bg-gray-800 rounded-lg p-4">
                <div class="text-3xl font-bold text-yellow-400">{{ stats.pending }}</div>
                <div class="text-gray-500 text-sm">Pending Review</div>
            </div>
        </div>
        
        <!-- Internal PRs -->
        <div class="mb-8">
            <h2 class="text-xl font-bold mb-4 text-gray-300">Internal Repository PRs</h2>
            
            {% if prs|length == 0 %}
            <div class="bg-gray-800 rounded-lg p-8 text-center">
                <div class="text-gray-500">No open PRs in internal repository</div>
            </div>
            {% else %}
            
            <div class="space-y-4">
                {% for pr in prs %}
                <div class="bg-gray-800 rounded-lg p-4 border border-gray-700">
                    <div class="flex justify-between items-start mb-2">
                        <div class="flex-1">
                            <div class="flex items-center gap-2 mb-1">
                                <a href="https://github.com/WattCoin-Org/wattcoin-internal/pull/{{ pr.number }}" 
                                   target="_blank"
                                   class="text-blue-400 hover:text-blue-300 font-medium">
                                    #{{ pr.number }}: {{ pr.title }}
                                </a>
                                {% set review = review_map.get(pr.number) %}
                                {% if review %}
                                    {% set score = review.review.get('score', 0) %}
                                    {% if score >= 9 %}
                                    <span class="px-2 py-1 bg-green-900/50 text-green-400 text-xs rounded">✅ {{ score }}/10 PASS</span>
                                    {% elif score >= 7 %}
                                    <span class="px-2 py-1 bg-yellow-900/50 text-yellow-400 text-xs rounded">⚠️ {{ score }}/10</span>
                                    {% else %}
                                    <span class="px-2 py-1 bg-red-900/50 text-red-400 text-xs rounded">❌ {{ score }}/10 FAIL</span>
                                    {% endif %}
                                {% else %}
                                <span class="px-2 py-1 bg-gray-700 text-gray-400 text-xs rounded">Pending Review</span>
                                {% endif %}
                            </div>
                            <div class="text-sm text-gray-500">
                                by {{ pr.user.login }} | 
                                +{{ pr.additions }} -{{ pr.deletions }} | 
                                {{ pr.changed_files }} file(s)
                            </div>
                        </div>
                        
                        <div class="flex gap-2">
                            <button onclick="triggerReview({{ pr.number }})" 
                                    id="btn-{{ pr.number }}"
                                    class="px-3 py-1 bg-blue-600 hover:bg-blue-700 text-white text-sm rounded">
                                Trigger Review
                            </button>
                            <button onclick="toggleFiles({{ pr.number }})" 
                                    class="px-3 py-1 bg-gray-700 hover:bg-gray-600 text-white text-sm rounded">
                                Files
                            </button>
                        </div>
                    </div>
                    
                    <!-- Review Details -->
                    {% if review %}
                    <div class="mt-3 p-3 bg-gray-900/50 rounded text-sm">
                        <div class="text-gray-400 mb-1">
                            <strong>AI Review:</strong> {{ review.review.get('feedback', 'No summary available') }}
                        </div>
                        {% if review.review.get('concerns') %}
                        <div class="text-yellow-400 mt-2">
                            <strong>Concerns:</strong>
                            <ul class="list-disc list-inside ml-2">
                                {% for concern in review.review.get('concerns', []) %}
                                <li>{{ concern }}</li>
                                {% endfor %}
                            </ul>
                        </div>
                        {% endif %}
                    </div>
                    {% endif %}
                    
                    <!-- Files Accordion -->
                    <div id="files-{{ pr.number }}" class="mt-3 hidden">
                        <div class="p-3 bg-gray-900/50 rounded text-sm">
                            <div class="text-gray-500 animate-pulse">Loading files...</div>
                        </div>
                    </div>
                </div>
                {% endfor %}
            </div>
            {% endif %}
        </div>
        
        <!-- Promotion Panel -->
        <div class="bg-gray-800 rounded-lg p-6 border border-gray-700">
            <h3 class="text-lg font-bold mb-2 text-gray-300">Code Promotion</h3>
            <p class="text-gray-500 text-sm mb-4">
                Push merged internal code to public repository (with security scan)
            </p>
            <button class="px-4 py-2 bg-green-600 hover:bg-green-700 text-white rounded" disabled>
                Promote to Public Repo (Coming Soon)
            </button>
        </div>
    </div>
    
    <script>
        async function triggerReview(prNumber) {
            const btn = document.getElementById(`btn-${prNumber}`);
            const originalText = btn.textContent;
            btn.textContent = 'Reviewing...';
            btn.disabled = true;
            
            try {
                const resp = await fetch('/admin/api/internal/trigger-review', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({pr_number: prNumber})
                });
                
                const data = await resp.json();
                
                if (resp.ok) {
                    btn.textContent = '✅ Reviewed';
                    setTimeout(() => location.reload(), 1500);
                } else {
                    alert('Error: ' + (data.error || 'Unknown error'));
                    btn.textContent = originalText;
                    btn.disabled = false;
                }
            } catch (err) {
                alert('Error: ' + err.message);
                btn.textContent = originalText;
                btn.disabled = false;
            }
        }
        
        async function toggleFiles(prNumber) {
            const container = document.getElementById(`files-${prNumber}`);
            
            if (container.classList.contains('hidden')) {
                // Load files
                container.classList.remove('hidden');
                
                try {
                    const resp = await fetch(`/admin/api/internal/pr/${prNumber}/files`);
                    const data = await resp.json();
                    
                    if (resp.ok && data.files) {
                        let html = '<div class="p-3 bg-gray-900/50 rounded text-sm space-y-2">';
                        data.files.forEach(f => {
                            const color = f.status === 'added' ? 'text-green-400' : 
                                         f.status === 'removed' ? 'text-red-400' : 'text-yellow-400';
                            html += `<div class="${color}">${f.filename} (+${f.additions} -${f.deletions})</div>`;
                        });
                        html += '</div>';
                        container.innerHTML = html;
                    } else {
                        container.innerHTML = '<div class="p-3 bg-gray-900/50 rounded text-sm text-red-400">Error loading files</div>';
                    }
                } catch (err) {
                    container.innerHTML = '<div class="p-3 bg-gray-900/50 rounded text-sm text-red-400">Error: ' + err.message + '</div>';
                }
            } else {
                container.classList.add('hidden');
            }
        }
    </script>
</body>
</html>
"""
