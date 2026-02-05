"""
Grok-Claude Bridge - Web Interface v2.1.0
Human-in-the-loop AI collaboration for WattCoin project
+ Proxy endpoint for external API calls (Moltbook, etc.)
+ Admin dashboard for bounty management
+ Paid scraper API (100 WATT per scrape)
+ WattNode routing for distributed compute

CHANGELOG v2.1.0:
- WattNode network support - route scrape jobs to registered nodes
- Nodes earn 70% of payment, 20% treasury, 10% burn
- Fallback to centralized if no active nodes

CHANGELOG v1.9.0:
- Scraper now requires WATT payment (100 WATT) or API key
- Same payment verification as LLM proxy
- API keys still work for premium users (skip payment)

CHANGELOG v1.3.0:
- Added API key authentication for /api/v1/scrape endpoint
- API keys have higher rate limits (500/hr basic, 2000/hr premium)
- Usage tracking per API key
- Keys managed via admin dashboard

CHANGELOG v1.2.0:
- Added admin blueprint for bounty dashboard
- Added /admin/* routes
- Requires ADMIN_PASSWORD env var for dashboard access
"""

import os
import json
import time
import random
import logging
import ipaddress
import socket
from urllib.parse import urlparse
from collections import defaultdict, deque

import requests
from bs4 import BeautifulSoup
from datetime import datetime
from flask import Flask, render_template_string, request, session, jsonify
from flask_cors import CORS
from anthropic import Anthropic
from openai import OpenAI

from scraper_errors import (
    ScraperError,
    ScraperErrorCode,
    validate_url,
    validate_format,
    validate_payment_params,
    validate_response_size,
    validate_http_status,
    validate_encoding,
    validate_content_not_empty,
    network_error_to_scraper_error,
    content_parsing_error,
    handle_redirect_error,
    handle_too_many_redirects
)

app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY", "wattcoin-dev-key-change-in-prod")

# =============================================================================
# LOGGING
# =============================================================================
logger = logging.getLogger("wattcoin.scraper")
logger.setLevel(logging.DEBUG)
if not logger.handlers:
    _handler = logging.StreamHandler()
    _handler.setLevel(logging.DEBUG)
    _handler.setFormatter(logging.Formatter(
        "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S"
    ))
    logger.addHandler(_handler)

# CORS - allow wattcoin.org and local dev
CORS(app, origins=[
    "https://wattcoin.org",
    "https://www.wattcoin.org",
    "http://localhost:5173",
    "http://localhost:3000"
])

# =============================================================================
# REGISTER ADMIN BLUEPRINT
# =============================================================================
from admin_blueprint import admin_bp
from api_bounties import bounties_bp
from api_llm import llm_bp, verify_watt_payment, save_used_signature
from api_reputation import reputation_bp
from api_tasks import tasks_bp
from api_nodes import nodes_bp, create_job, wait_for_job_result, cancel_job, get_active_nodes
from api_pr_review import pr_review_bp
from api_webhooks import webhooks_bp
from api_wsi import wsi_bp
app.register_blueprint(admin_bp)
app.register_blueprint(bounties_bp)
app.register_blueprint(llm_bp)
app.register_blueprint(reputation_bp)
app.register_blueprint(tasks_bp)
app.register_blueprint(nodes_bp)
app.register_blueprint(pr_review_bp)
app.register_blueprint(webhooks_bp)
app.register_blueprint(wsi_bp)

# =============================================================================
# API CLIENTS
# =============================================================================
GROK_API_KEY = os.getenv("GROK_API_KEY")
CLAUDE_API_KEY = os.getenv("CLAUDE_API_KEY")
PROXY_SECRET = os.getenv("PROXY_SECRET", "wattcoin-proxy-secret-change-me")

if not GROK_API_KEY or not CLAUDE_API_KEY:
    print("WARNING: Set GROK_API_KEY and CLAUDE_API_KEY environment variables")

grok_client = None
claude_client = None

def init_clients():
    global grok_client, claude_client
    if GROK_API_KEY:
        grok_client = OpenAI(api_key=GROK_API_KEY, base_url="https://api.x.ai/v1")
    if CLAUDE_API_KEY:
        claude_client = Anthropic(api_key=CLAUDE_API_KEY)

init_clients()

# =============================================================================
# SCRAPER CONFIG (v0.1)
# =============================================================================

SCRAPE_TIMEOUT_SECONDS = 30
MAX_CONTENT_BYTES = 2 * 1024 * 1024  # 2MB
MAX_REDIRECTS = 3
TRUST_PROXY_HEADERS = os.getenv("SCRAPE_TRUST_PROXY", "false").lower() == "true"
RATE_LIMIT_WINDOW_SECONDS = 60 * 60  # 1 hour
MAX_REQUESTS_PER_IP = 100
MAX_REQUESTS_PER_URL = 10

# API Key config
API_KEYS_FILE = "/app/data/api_keys.json"
API_KEY_RATE_LIMITS = {
    "basic": {"requests_per_hour": 500, "requests_per_url": 50},
    "premium": {"requests_per_hour": 2000, "requests_per_url": 200}
}

SCRAPE_USER_AGENTS = [
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.2 Safari/605.1.15",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_2 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.2 Mobile/15E148 Safari/604.1",
    "Mozilla/5.0 (iPad; CPU OS 17_2 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.2 Mobile/15E148 Safari/604.1",
]

_rate_limit_ip = defaultdict(deque)
_rate_limit_url = defaultdict(deque)
_rate_limit_api_key = defaultdict(deque)
_rate_limit_api_key_url = defaultdict(deque)

# =============================================================================
# API KEY VALIDATION
# =============================================================================

def _load_api_keys():
    """Load API keys from JSON file."""
    try:
        with open(API_KEYS_FILE, 'r') as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {"keys": {}}

def _save_api_keys(data):
    """Save API keys to JSON file."""
    try:
        os.makedirs(os.path.dirname(API_KEYS_FILE), exist_ok=True)
        with open(API_KEYS_FILE, 'w') as f:
            json.dump(data, f, indent=2)
    except Exception as e:
        print(f"Error saving API keys: {e}")

def _validate_api_key(api_key):
    """Validate API key and return key data if valid."""
    if not api_key:
        return None
    data = _load_api_keys()
    key_data = data.get("keys", {}).get(api_key)
    if key_data and key_data.get("status") == "active":
        return key_data
    return None

def _increment_api_key_usage(api_key):
    """Increment usage count for an API key."""
    data = _load_api_keys()
    if api_key in data.get("keys", {}):
        data["keys"][api_key]["usage_count"] = data["keys"][api_key].get("usage_count", 0) + 1
        data["keys"][api_key]["last_used"] = datetime.utcnow().isoformat() + "Z"
        _save_api_keys(data)

def _check_api_key_rate_limit(api_key, url, tier):
    """Check rate limit for API key. Returns (allowed, retry_after)."""
    now = time.time()
    limits = API_KEY_RATE_LIMITS.get(tier, API_KEY_RATE_LIMITS["basic"])
    
    # Check per-key rate limit
    key_queue = _rate_limit_api_key[api_key]
    _prune_rate_limit(key_queue, now)
    if len(key_queue) >= limits["requests_per_hour"]:
        retry_after = int(RATE_LIMIT_WINDOW_SECONDS - (now - key_queue[0]))
        return False, retry_after
    
    # Check per-key per-URL rate limit
    key_url = f"{api_key}:{url}"
    url_queue = _rate_limit_api_key_url[key_url]
    _prune_rate_limit(url_queue, now)
    if len(url_queue) >= limits["requests_per_url"]:
        retry_after = int(RATE_LIMIT_WINDOW_SECONDS - (now - url_queue[0]))
        return False, retry_after
    
    key_queue.append(now)
    url_queue.append(now)
    return True, None


def _prune_rate_limit(queue, now):
    while queue and now - queue[0] > RATE_LIMIT_WINDOW_SECONDS:
        queue.popleft()


def _check_rate_limit(ip_address, url):
    now = time.time()

    ip_queue = _rate_limit_ip[ip_address]
    _prune_rate_limit(ip_queue, now)
    if len(ip_queue) >= MAX_REQUESTS_PER_IP:
        retry_after = int(RATE_LIMIT_WINDOW_SECONDS - (now - ip_queue[0]))
        return False, retry_after

    url_queue = _rate_limit_url[url]
    _prune_rate_limit(url_queue, now)
    if len(url_queue) >= MAX_REQUESTS_PER_URL:
        retry_after = int(RATE_LIMIT_WINDOW_SECONDS - (now - url_queue[0]))
        return False, retry_after

    ip_queue.append(now)
    url_queue.append(now)
    return True, None


def _get_client_ip():
    if TRUST_PROXY_HEADERS:
        forwarded_for = request.headers.get("X-Forwarded-For", "")
        if forwarded_for:
            return forwarded_for.split(",")[0].strip()
    return request.remote_addr or "unknown"


def _is_disallowed_host(hostname):
    if not hostname:
        return True
    lowered = hostname.lower()
    if lowered in {"localhost", "127.0.0.1", "0.0.0.0", "::1"}:
        return True
    try:
        ip = ipaddress.ip_address(hostname)
        return not ip.is_global
    except ValueError:
        return False


def _resolves_to_public_ip(hostname):
    try:
        infos = socket.getaddrinfo(hostname, None)
    except socket.gaierror:
        return False
    for info in infos:
        ip_str = info[4][0]
        try:
            ip = ipaddress.ip_address(ip_str)
        except ValueError:
            return False
        if not ip.is_global:
            return False
    return True


def _validate_scrape_url(target_url):
    parsed = urlparse(target_url)
    if parsed.scheme not in {"http", "https"}:
        return False
    if parsed.username or parsed.password:
        return False
    if _is_disallowed_host(parsed.hostname):
        return False
    if not _resolves_to_public_ip(parsed.hostname):
        return False
    return True


def _read_limited_content(resp):
    content = bytearray()
    for chunk in resp.iter_content(chunk_size=8192):
        if chunk:
            content.extend(chunk)
            if len(content) > MAX_CONTENT_BYTES:
                raise ValueError("Response too large")
    return bytes(content)


def _fetch_with_redirects(url, headers):
    current_url = url
    for _ in range(MAX_REDIRECTS + 1):
        resp = requests.get(
            current_url,
            headers=headers,
            timeout=SCRAPE_TIMEOUT_SECONDS,
            allow_redirects=False,
            stream=True
        )
        if resp.status_code in {301, 302, 303, 307, 308}:
            location = resp.headers.get("Location")
            if not location:
                return resp
            next_url = requests.compat.urljoin(current_url, location)
            if not _validate_scrape_url(next_url):
                raise ValueError("Redirect to invalid or blocked URL")
            current_url = next_url
            continue
        return resp
    raise ValueError("Too many redirects")

# Project context
WATTCOIN_CONTEXT = """
WattCoin (WATT) is a pure utility token on Solana for AI/robot automation payments.
- Purpose: Energy, task execution, maintenance, rewards in automation ecosystems
- Platform: Solana (65k TPS, ~$0.00025/tx)
- Supply: 1B WATT fixed cap, 0.15% burn per transaction
- CA: Gpmbh4PoQnL1kNgpMYDED3iv4fczcr7d3qNBLf8rpump
- Use cases: Task marketplace, autonomous sustainment, owner revenue, cross-chain bridges
- Status: LIVE on mainnet (Jan 31, 2026)
"""

GROK_SYSTEM = f"""You are the Strategy Consultant for the WattCoin project.
Your role: High-level strategy, market analysis, tokenomics advice, launch planning.
Project context: {WATTCOIN_CONTEXT}
Keep responses focused and actionable. You're collaborating with Claude (implementation/coder)."""

CLAUDE_SYSTEM = f"""You are the Implementation Lead for the WattCoin project.
Your role: Technical implementation, coding, smart contracts, infrastructure.
Project context: {WATTCOIN_CONTEXT}
Keep responses focused and actionable. You're collaborating with Grok (strategy consultant)."""

def query_grok(prompt, history=[]):
    if not grok_client:
        return "Error: Grok API key not configured"
    messages = [{"role": "system", "content": GROK_SYSTEM}]
    messages.extend(history)
    messages.append({"role": "user", "content": prompt})
    
    response = grok_client.chat.completions.create(
        model="grok-3",
        messages=messages,
        max_tokens=2048
    )
    return response.choices[0].message.content

def query_claude(prompt, history=[]):
    if not claude_client:
        return "Error: Claude API key not configured"
    messages = []
    for msg in history:
        if msg["role"] in ["user", "assistant"]:
            messages.append(msg)
    messages.append({"role": "user", "content": prompt})
    
    response = claude_client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=2048,
        system=CLAUDE_SYSTEM,
        messages=messages
    )
    return response.content[0].text

HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>WattCoin - Grok/Claude Bridge</title>
    <style>
        * { box-sizing: border-box; margin: 0; padding: 0; }
        body { 
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            background: #0a0a0a; color: #e0e0e0; min-height: 100vh;
            padding: 20px; max-width: 1200px; margin: 0 auto;
        }
        h1 { color: #00ff88; margin-bottom: 10px; font-size: 1.8em; }
        .subtitle { color: #888; margin-bottom: 30px; }
        .input-section { margin-bottom: 30px; }
        textarea { 
            width: 100%; padding: 15px; border-radius: 8px; 
            background: #1a1a1a; border: 1px solid #333; color: #e0e0e0;
            font-size: 16px; resize: vertical; min-height: 100px;
        }
        textarea:focus { outline: none; border-color: #00ff88; }
        .btn { 
            padding: 12px 24px; border-radius: 6px; border: none; 
            cursor: pointer; font-size: 14px; font-weight: 600;
            transition: all 0.2s;
        }
        .btn-primary { background: #00ff88; color: #000; }
        .btn-primary:hover { background: #00cc6a; }
        .btn-secondary { background: #333; color: #e0e0e0; }
        .btn-secondary:hover { background: #444; }
        .btn-danger { background: #ff4444; color: #fff; }
        .btn-danger:hover { background: #cc3333; }
        .buttons { display: flex; gap: 10px; margin-top: 15px; flex-wrap: wrap; }
        .response-box { 
            background: #1a1a1a; border-radius: 8px; padding: 20px; 
            margin-bottom: 20px; border-left: 4px solid #333;
        }
        .response-box.grok { border-left-color: #ff6600; }
        .response-box.claude { border-left-color: #00aaff; }
        .response-box h3 { margin-bottom: 15px; display: flex; align-items: center; gap: 10px; }
        .response-box.grok h3 { color: #ff6600; }
        .response-box.claude h3 { color: #00aaff; }
        .response-content { 
            white-space: pre-wrap; line-height: 1.6; 
            background: #0d0d0d; padding: 15px; border-radius: 4px;
        }
        .history { margin-top: 40px; border-top: 1px solid #333; padding-top: 20px; }
        .history h2 { color: #888; margin-bottom: 20px; }
        .exchange { margin-bottom: 30px; padding-bottom: 20px; border-bottom: 1px solid #222; }
        .exchange-prompt { color: #00ff88; margin-bottom: 10px; font-weight: 600; }
        .timestamp { color: #555; font-size: 12px; }
        .loading { display: none; color: #00ff88; padding: 20px; }
        .spinner { display: inline-block; animation: spin 1s linear infinite; }
        @keyframes spin { 100% { transform: rotate(360deg); } }
        .status { padding: 10px; border-radius: 4px; margin-bottom: 20px; }
        .status.error { background: #331111; color: #ff6666; }
        .status.success { background: #113311; color: #66ff66; }
        #editPrompt { display: none; margin-top: 15px; }
        .admin-link { position: fixed; top: 20px; right: 20px; }
        .admin-link a { color: #888; text-decoration: none; font-size: 14px; }
        .admin-link a:hover { color: #00ff88; }
    </style>
</head>
<body>
    <div class="admin-link"><a href="/admin">🔐 Admin Dashboard</a></div>
    
    <h1>⚡ WattCoin Bridge v1.2</h1>
    <p class="subtitle">Grok (Strategy) ↔ Claude (Implementation) | Proxy: Active</p>
    
    {% if status %}
    <div class="status {{ status.type }}">{{ status.message }}</div>
    {% endif %}
    
    <div class="input-section">
        <form method="POST" action="/query" id="mainForm">
            <textarea name="prompt" placeholder="Enter your topic or question for the AI collaboration..." required>{{ prompt or '' }}</textarea>
            <div class="buttons">
                <button type="submit" class="btn btn-primary">🚀 Send to Grok</button>
                <button type="button" class="btn btn-secondary" onclick="clearHistory()">🗑️ Clear History</button>
            </div>
        </form>
    </div>
    
    <div class="loading" id="loading">
        <span class="spinner">⚡</span> Processing...
    </div>
    
    {% if grok_response %}
    <div class="response-box grok">
        <h3>🤖 GROK (Strategy)</h3>
        <div class="response-content">{{ grok_response }}</div>
        <div class="buttons">
            <form method="POST" action="/send-to-claude" style="display:inline;">
                <input type="hidden" name="grok_response" value="{{ grok_response }}">
                <input type="hidden" name="original_prompt" value="{{ prompt }}">
                <button type="submit" class="btn btn-primary">✅ Send to Claude</button>
            </form>
            <button type="button" class="btn btn-secondary" onclick="showEdit()">✏️ Edit Prompt</button>
            <form method="POST" action="/skip-claude" style="display:inline;">
                <input type="hidden" name="grok_response" value="{{ grok_response }}">
                <input type="hidden" name="original_prompt" value="{{ prompt }}">
                <button type="submit" class="btn btn-secondary">⏭️ Skip Claude</button>
            </form>
        </div>
        <div id="editPrompt">
            <form method="POST" action="/send-to-claude">
                <textarea name="custom_prompt" placeholder="Custom prompt for Claude..."></textarea>
                <input type="hidden" name="grok_response" value="{{ grok_response }}">
                <input type="hidden" name="original_prompt" value="{{ prompt }}">
                <button type="submit" class="btn btn-primary" style="margin-top:10px;">Send Custom Prompt</button>
            </form>
        </div>
    </div>
    {% endif %}
    
    {% if claude_response %}
    <div class="response-box claude">
        <h3>🧠 CLAUDE (Implementation)</h3>
        <div class="response-content">{{ claude_response }}</div>
        <div class="buttons">
            <form method="POST" action="/send-to-grok" style="display:inline;">
                <input type="hidden" name="claude_response" value="{{ claude_response }}">
                <button type="submit" class="btn btn-secondary">🔄 Send to Grok</button>
            </form>
        </div>
    </div>
    {% endif %}
    
    {% if history %}
    <div class="history">
        <h2>📜 Conversation History</h2>
        {% for ex in history|reverse %}
        <div class="exchange">
            <div class="timestamp">{{ ex.timestamp }}</div>
            <div class="exchange-prompt">💬 {{ ex.prompt }}</div>
            <div class="response-box grok" style="margin:10px 0;">
                <h3>🤖 Grok</h3>
                <div class="response-content">{{ ex.grok }}</div>
            </div>
            {% if ex.claude != '[skipped]' %}
            <div class="response-box claude">
                <h3>🧠 Claude</h3>
                <div class="response-content">{{ ex.claude }}</div>
            </div>
            {% endif %}
        </div>
        {% endfor %}
    </div>
    {% endif %}
    
    <script>
        function showEdit() {
            document.getElementById('editPrompt').style.display = 'block';
        }
        function clearHistory() {
            if (confirm('Clear all conversation history?')) {
                window.location.href = '/clear';
            }
        }
        document.getElementById('mainForm').onsubmit = function() {
            document.getElementById('loading').style.display = 'block';
        };
    </script>
</body>
</html>
"""

@app.route('/')
def index():
    history = session.get('history', [])
    return render_template_string(HTML_TEMPLATE, history=history)

@app.route('/query', methods=['POST'])
def query():
    prompt = request.form.get('prompt', '')
    history = session.get('history', [])
    grok_history = session.get('grok_history', [])
    
    try:
        grok_response = query_grok(prompt, grok_history)
        session['pending_grok'] = grok_response
        session['grok_history'] = grok_history + [
            {"role": "user", "content": prompt},
            {"role": "assistant", "content": grok_response}
        ]
        return render_template_string(HTML_TEMPLATE, 
            prompt=prompt, grok_response=grok_response, history=history)
    except Exception as e:
        return render_template_string(HTML_TEMPLATE, 
            history=history, status={'type': 'error', 'message': f'Grok error: {str(e)}'})

@app.route('/send-to-claude', methods=['POST'])
def send_to_claude():
    grok_response = request.form.get('grok_response', '')
    original_prompt = request.form.get('original_prompt', '')
    custom_prompt = request.form.get('custom_prompt', '')
    
    history = session.get('history', [])
    claude_history = session.get('claude_history', [])
    
    if custom_prompt:
        claude_prompt = custom_prompt
    else:
        claude_prompt = f"Grok (strategy consultant) said:\n\n{grok_response}\n\nRespond with implementation perspective."
    
    try:
        claude_response = query_claude(claude_prompt, claude_history)
        session['claude_history'] = claude_history + [
            {"role": "user", "content": claude_prompt},
            {"role": "assistant", "content": claude_response}
        ]
        
        # Log exchange
        history.append({
            'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M'),
            'prompt': original_prompt,
            'grok': grok_response,
            'claude': claude_response
        })
        session['history'] = history
        
        return render_template_string(HTML_TEMPLATE,
            prompt=original_prompt, grok_response=grok_response, 
            claude_response=claude_response, history=history)
    except Exception as e:
        return render_template_string(HTML_TEMPLATE,
            history=history, status={'type': 'error', 'message': f'Claude error: {str(e)}'})

@app.route('/skip-claude', methods=['POST'])
def skip_claude():
    grok_response = request.form.get('grok_response', '')
    original_prompt = request.form.get('original_prompt', '')
    history = session.get('history', [])
    
    history.append({
        'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M'),
        'prompt': original_prompt,
        'grok': grok_response,
        'claude': '[skipped]'
    })
    session['history'] = history
    
    return render_template_string(HTML_TEMPLATE, history=history,
        status={'type': 'success', 'message': 'Skipped Claude, logged Grok response.'})

@app.route('/send-to-grok', methods=['POST'])
def send_to_grok():
    claude_response = request.form.get('claude_response', '')
    prompt = f"Claude (implementation) responded:\n\n{claude_response}\n\nYour thoughts?"
    
    history = session.get('history', [])
    grok_history = session.get('grok_history', [])
    
    try:
        grok_response = query_grok(prompt, grok_history)
        session['grok_history'] = grok_history + [
            {"role": "user", "content": prompt},
            {"role": "assistant", "content": grok_response}
        ]
        return render_template_string(HTML_TEMPLATE,
            prompt=prompt, grok_response=grok_response, history=history)
    except Exception as e:
        return render_template_string(HTML_TEMPLATE,
            history=history, status={'type': 'error', 'message': f'Grok error: {str(e)}'})

@app.route('/clear')
def clear():
    session.clear()
    return render_template_string(HTML_TEMPLATE, 
        status={'type': 'success', 'message': 'History cleared.'})


# =============================================================================
# SCRAPER ENDPOINT - v0.1
# =============================================================================

@app.route('/api/v1/scrape', methods=['POST'])
def scrape():
    """
    Web scraper endpoint - requires WATT payment or API key.
    
    Comprehensive error handling with detailed error codes and messages.
    
    Request:
        {
            "url": "https://example.com",
            "format": "text|html|json",
            "wallet": "AgentWallet...",      # Required if no API key
            "tx_signature": "..."             # Required if no API key
        }
    
    Headers:
        X-API-Key: <key>  (optional - skips payment if valid)
    
    Pricing: 100 WATT per scrape
    
    Error Codes:
        - missing_url, invalid_url, url_blocked
        - invalid_format
        - missing_payment, invalid_payment
        - invalid_api_key, rate_limit_exceeded
        - timeout, connection_error, dns_error
        - response_too_large, empty_response
        - invalid_json, invalid_html
        - http_error, redirect_error
        - internal_error
    """
    SCRAPE_PRICE_WATT = 100
    
    try:
        # Parse request
        data = request.get_json(silent=True) or {}
        target_url = data.get('url', '').strip()
        output_format = (data.get('format') or 'text').strip().lower()
        client_ip = _get_client_ip()
        
        logger.info("scrape request received | ip=%s url=%.120s format=%s", client_ip, target_url or '<empty>', output_format)
        
        # === INPUT VALIDATION ===
        
        # Validate URL
        is_valid, url_error = validate_url(target_url)
        if not is_valid:
            logger.warning("url validation failed | ip=%s error=%s", client_ip, url_error.error_code.value)
            response, status = url_error.to_response()
            return jsonify(response), status
        
        # Validate format
        is_valid, format_error = validate_format(output_format)
        if not is_valid:
            logger.warning("format validation failed | ip=%s format=%s", client_ip, output_format)
            response, status = format_error.to_response()
            return jsonify(response), status
        
        # Set default format if needed
        if not output_format:
            output_format = 'text'
        
        # Validate URL with security checks
        if not _validate_scrape_url(target_url):
            logger.warning("url blocked by security check | ip=%s url=%.120s", client_ip, target_url)
            error = ScraperError(
                ScraperErrorCode.URL_BLOCKED,
                "URL is blocked or invalid for security reasons",
                400
            )
            response, status = error.to_response()
            return jsonify(response), status
        
        # === AUTHENTICATION ===
        
        api_key = request.headers.get('X-API-Key', '').strip()
        wallet = data.get('wallet', '').strip()
        tx_signature = data.get('tx_signature', '').strip()
        
        # Validate payment parameters
        is_valid, payment_error = validate_payment_params(api_key, wallet, tx_signature)
        if not is_valid:
            logger.warning("payment validation failed | ip=%s error=%s", client_ip, payment_error.error_code.value)
            response, status = payment_error.to_response()
            return jsonify(response), status
        
        key_data = None
        payment_verified = False
        
        if api_key:
            # API key authentication
            key_data = _validate_api_key(api_key)
            if not key_data:
                logger.warning("invalid api key | ip=%s", client_ip)
                error = ScraperError(
                    ScraperErrorCode.INVALID_API_KEY,
                    "The provided API key is invalid or inactive",
                    401
                )
                response, status = error.to_response()
                return jsonify(response), status
            
            # Check rate limit
            tier = key_data.get('tier', 'basic')
            allowed, retry_after = _check_api_key_rate_limit(api_key, target_url, tier)
            if not allowed:
                logger.warning("api key rate limit exceeded | ip=%s tier=%s retry_after=%s", client_ip, tier, retry_after)
                error = ScraperError(
                    ScraperErrorCode.RATE_LIMIT_EXCEEDED,
                    f"Rate limit exceeded for tier '{tier}'. Try again in {retry_after} seconds.",
                    429,
                    {'retry_after_seconds': retry_after, 'tier': tier}
                )
                response, status = error.to_response()
                return jsonify(response), status
            
            logger.info("api key authenticated | ip=%s tier=%s", client_ip, tier)
            _increment_api_key_usage(api_key)
            payment_verified = True
        else:
            # WATT payment verification
            logger.info("verifying watt payment | ip=%s wallet=%.40s", client_ip, wallet)
            verified, error_code, error_message = verify_watt_payment(
                tx_signature, wallet, SCRAPE_PRICE_WATT
            )
            
            if not verified:
                logger.warning("watt payment failed | ip=%s error_code=%s", client_ip, error_code)
                # Determine error type
                if error_code == 'invalid_signature':
                    scraper_error_code = ScraperErrorCode.INVALID_PAYMENT
                elif error_code == 'insufficient_amount':
                    scraper_error_code = ScraperErrorCode.PAYMENT_FAILED
                elif error_code == 'signature_already_used':
                    scraper_error_code = ScraperErrorCode.PAYMENT_FAILED
                else:
                    scraper_error_code = ScraperErrorCode.PAYMENT_FAILED
                
                error = ScraperError(
                    scraper_error_code,
                    error_message,
                    400
                )
                response, status = error.to_response()
                return jsonify(response), status
            
            logger.info("watt payment verified | ip=%s wallet=%.40s", client_ip, wallet)
            save_used_signature(tx_signature)
            payment_verified = True
        
        # === NODE ROUTING (v2.1.0) ===
        if payment_verified:
            active_nodes = get_active_nodes(capability='scrape')
            if active_nodes:
                try:
                    job_result = create_job(
                        job_type='scrape',
                        payload={'url': target_url, 'format': output_format},
                        total_payment=SCRAPE_PRICE_WATT,
                        requester_wallet=wallet or 'api_key_user'
                    )
                    
                    if job_result.get('routed'):
                        job_id = job_result.get('job_id')
                        node_result = wait_for_job_result(job_id, timeout=30)
                        
                        if node_result.get('success'):
                            result = node_result.get('result', {})
                            response_data = {
                                'success': True,
                                'url': target_url,
                                'content': result.get('content', ''),
                                'format': output_format,
                                'status_code': result.get('status_code', 200),
                                'timestamp': datetime.utcnow().isoformat() + 'Z',
                                'routed_to_node': True,
                                'node_id': node_result.get('node_id')
                            }
                            if tx_signature:
                                response_data['tx_verified'] = True
                                response_data['watt_charged'] = SCRAPE_PRICE_WATT
                            return jsonify(response_data), 200
                        else:
                            # Node timeout - fallback to centralized
                            cancel_job(job_id)
                except Exception:
                    # Node routing error - fall through to centralized
                    pass
        
        # === CENTRALIZED FALLBACK ===
        headers = {
            'User-Agent': random.choice(SCRAPE_USER_AGENTS),
            'Accept': 'text/html,application/json;q=0.9,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.9'
        }
        
        # Fetch with redirect handling
        logger.info("fetching url | ip=%s url=%.120s format=%s", client_ip, target_url, output_format)
        try:
            resp = _fetch_with_redirects(target_url, headers)
        except requests.Timeout as e:
            logger.warning("request timed out | ip=%s url=%.120s elapsed=%ss", client_ip, target_url, SCRAPE_TIMEOUT_SECONDS)
            error = network_error_to_scraper_error(e)
            response, status = error.to_response()
            return jsonify(response), status
        except requests.exceptions.SSLError as e:
            logger.warning("ssl error | ip=%s url=%.120s error=%s", client_ip, target_url, str(e)[:120])
            error = network_error_to_scraper_error(e)
            response, status = error.to_response()
            return jsonify(response), status
        except ValueError as e:
            error_msg = str(e)
            if "Too many redirects" in error_msg:
                logger.warning("too many redirects | ip=%s url=%.120s", client_ip, target_url)
                error = handle_too_many_redirects()
            else:
                logger.warning("redirect error | ip=%s url=%.120s reason=%s", client_ip, target_url, error_msg)
                error = handle_redirect_error(error_msg)
            response, status = error.to_response()
            return jsonify(response), status
        except requests.RequestException as e:
            logger.warning("network error | ip=%s url=%.120s type=%s error=%s", client_ip, target_url, type(e).__name__, str(e)[:120])
            error = network_error_to_scraper_error(e)
            response, status = error.to_response()
            return jsonify(response), status
        except Exception as e:
            logger.error("unexpected fetch error | ip=%s url=%.120s type=%s error=%s", client_ip, target_url, type(e).__name__, str(e)[:120])
            error = ScraperError(
                ScraperErrorCode.INTERNAL_ERROR,
                "An unexpected error occurred while fetching the URL",
                500
            )
            response, status = error.to_response()
            return jsonify(response), status
        
        # Validate HTTP response status
        logger.debug("target responded | ip=%s url=%.120s status=%d", client_ip, target_url, resp.status_code)
        is_valid, http_error = validate_http_status(resp.status_code)
        if not is_valid:
            logger.warning("http error from target | ip=%s url=%.120s status=%d", client_ip, target_url, resp.status_code)
            response, status = http_error.to_response()
            return jsonify(response), status
        
        # Read response content with size validation
        try:
            raw_bytes = _read_limited_content(resp)
        except ValueError as e:
            error_msg = str(e)
            if "Response too large" in error_msg:
                logger.warning("response too large | ip=%s url=%.120s max_bytes=%d", client_ip, target_url, MAX_CONTENT_BYTES)
                error = ScraperError(
                    ScraperErrorCode.RESPONSE_TOO_LARGE,
                    "Response exceeds maximum size (2 MB). Use a more specific URL.",
                    413,
                    {'max_bytes': MAX_CONTENT_BYTES}
                )
            else:
                logger.error("content read error | ip=%s url=%.120s error=%s", client_ip, target_url, error_msg)
                error = ScraperError(
                    ScraperErrorCode.INTERNAL_ERROR,
                    "Error reading response content",
                    500
                )
            response, status = error.to_response()
            return jsonify(response), status
        except Exception as e:
            logger.error("unexpected read error | ip=%s url=%.120s type=%s", client_ip, target_url, type(e).__name__)
            error = ScraperError(
                ScraperErrorCode.INTERNAL_ERROR,
                "An unexpected error occurred while reading the response",
                500
            )
            response, status = error.to_response()
            return jsonify(response), status
        
        # Validate content is not empty
        if len(raw_bytes) == 0:
            logger.warning("empty response | ip=%s url=%.120s", client_ip, target_url)
            error = ScraperError(
                ScraperErrorCode.EMPTY_RESPONSE,
                "The target URL returned empty content",
                502
            )
            response, status = error.to_response()
            return jsonify(response), status
        
        # Parse content based on format
        try:
            # Validate and get encoding
            charset = resp.encoding
            is_valid, encoding = validate_encoding(charset)
            
            if output_format == 'html':
                try:
                    content = raw_bytes.decode(encoding, errors='replace')
                except Exception:
                    content = raw_bytes.decode('utf-8', errors='replace')
            elif output_format == 'json':
                try:
                    text = raw_bytes.decode(encoding, errors='replace')
                    content = json.loads(text)
                except json.JSONDecodeError:
                    error = content_parsing_error('json')
                    response, status = error.to_response()
                    return jsonify(response), status
                except Exception as e:
                    error = content_parsing_error('json', e)
                    response, status = error.to_response()
                    return jsonify(response), status
            else:  # text
                try:
                    html_text = raw_bytes.decode(encoding, errors='replace')
                    soup = BeautifulSoup(html_text, 'html.parser')
                    content = soup.get_text(separator=' ', strip=True)
                except Exception as e:
                    error = content_parsing_error('text', e)
                    response, status = error.to_response()
                    return jsonify(response), status
        except Exception as e:
            error = ScraperError(
                ScraperErrorCode.PARSING_ERROR,
                f"An error occurred while parsing the response",
                500
            )
            response, status = error.to_response()
            return jsonify(response), status
        
        # Validate content is not empty after parsing
        is_valid, empty_error = validate_content_not_empty(content, output_format)
        if not is_valid:
            response, status = empty_error.to_response()
            return jsonify(response), status
        
        # === SUCCESS ===
        content_len = len(content) if isinstance(content, str) else len(json.dumps(content))
        logger.info("scrape success | ip=%s url=%.120s format=%s status=%d content_len=%d", client_ip, target_url, output_format, resp.status_code, content_len)
        
        response_data = {
            'success': True,
            'url': target_url,
            'content': content,
            'format': output_format,
            'status_code': resp.status_code,
            'timestamp': datetime.utcnow().isoformat() + 'Z'
        }
        
        # Add payment info
        if tx_signature:
            response_data['tx_verified'] = True
            response_data['watt_charged'] = SCRAPE_PRICE_WATT
        elif key_data:
            response_data['api_key_used'] = True
            response_data['tier'] = key_data.get('tier', 'basic')
        
        return jsonify(response_data), 200
        
    except ScraperError as e:
        logger.warning("scraper error (caught) | error=%s message=%s", e.error_code.value, e.message)
        response, status = e.to_response()
        return jsonify(response), status
    except Exception as e:
        # Catch any unexpected errors
        logger.error("unhandled scraper exception | type=%s error=%s", type(e).__name__, str(e)[:200], exc_info=True)
        error = ScraperError(
            ScraperErrorCode.INTERNAL_ERROR,
            "An unexpected error occurred while processing your request",
            500
        )
        response, status = error.to_response()
        return jsonify(response), status


# =============================================================================
# PROXY ENDPOINTS - v1.1.0
# =============================================================================

@app.route('/proxy', methods=['POST'])
def proxy_request():
    """
    Generic HTTP proxy endpoint - bypasses Claude's egress restrictions.
    
    Request JSON:
    {
        "secret": "your-proxy-secret",
        "method": "POST",
        "url": "https://www.moltbook.com/api/v1/posts/{id}/comments",
        "headers": {"Authorization": "Bearer xxx", "Content-Type": "application/json"},
        "body": {"content": "your comment"}
    }
    """
    try:
        data = request.get_json()
        
        # Auth check
        if data.get('secret') != PROXY_SECRET:
            return jsonify({'error': 'Invalid secret'}), 401
        
        method = data.get('method', 'GET').upper()
        url = data.get('url')
        headers = data.get('headers', {})
        body = data.get('body')
        
        if not url:
            return jsonify({'error': 'URL required'}), 400
        
        # Make the proxied request
        if method == 'GET':
            resp = requests.get(url, headers=headers, timeout=30)
        elif method == 'POST':
            resp = requests.post(url, headers=headers, json=body, timeout=30)
        elif method == 'PUT':
            resp = requests.put(url, headers=headers, json=body, timeout=30)
        elif method == 'DELETE':
            resp = requests.delete(url, headers=headers, timeout=30)
        else:
            return jsonify({'error': f'Unsupported method: {method}'}), 400
        
        # Return response
        try:
            response_data = resp.json()
        except:
            response_data = resp.text
        
        return jsonify({
            'status_code': resp.status_code,
            'response': response_data
        }), 200
        
    except requests.Timeout:
        return jsonify({'error': 'Request timeout'}), 504
    except requests.RequestException as e:
        return jsonify({'error': f'Request failed: {str(e)}'}), 502
    except Exception as e:
        return jsonify({'error': f'Proxy error: {str(e)}'}), 500


@app.route('/proxy/moltbook', methods=['POST'])
def proxy_moltbook():
    """
    Convenience endpoint specifically for Moltbook API calls.
    
    Request JSON:
    {
        "secret": "your-proxy-secret",
        "endpoint": "/posts/{post_id}/comments",
        "method": "POST",
        "api_key": "moltbook_sk_xxx",
        "body": {"content": "your comment"}
    }
    """
    try:
        data = request.get_json()
        
        # Auth check
        if data.get('secret') != PROXY_SECRET:
            return jsonify({'error': 'Invalid secret'}), 401
        
        endpoint = data.get('endpoint', '')
        method = data.get('method', 'GET').upper()
        api_key = data.get('api_key')
        body = data.get('body')
        
        if not endpoint:
            return jsonify({'error': 'Endpoint required'}), 400
        if not api_key:
            return jsonify({'error': 'Moltbook API key required'}), 400
        
        # Build Moltbook URL (always use www)
        url = f"https://www.moltbook.com/api/v1{endpoint}"
        headers = {
            'Authorization': f'Bearer {api_key}',
            'Content-Type': 'application/json'
        }
        
        # Make request
        if method == 'GET':
            resp = requests.get(url, headers=headers, timeout=30)
        elif method == 'POST':
            resp = requests.post(url, headers=headers, json=body, timeout=30)
        else:
            return jsonify({'error': f'Unsupported method: {method}'}), 400
        
        try:
            response_data = resp.json()
        except:
            response_data = resp.text
        
        return jsonify({
            'status_code': resp.status_code,
            'response': response_data
        }), 200
        
    except Exception as e:
        return jsonify({'error': f'Moltbook proxy error: {str(e)}'}), 500


@app.route('/health')
def health():
    active_nodes = len(get_active_nodes())
    return jsonify({
        'status': 'ok', 
        'version': '2.1.0',
        'grok': bool(grok_client), 
        'claude': bool(claude_client),
        'proxy': True,
        'admin': True,
        'active_nodes': active_nodes
    })


@app.route('/api/v1/pricing', methods=['GET'])
def unified_pricing():
    """
    Unified pricing for all WattCoin paid services.
    """
    return jsonify({
        "services": {
            "llm": {
                "endpoint": "/api/v1/llm",
                "price_watt": 500,
                "description": "Query Grok AI",
                "method": "POST"
            },
            "scrape": {
                "endpoint": "/api/v1/scrape",
                "price_watt": 100,
                "description": "Web scraper",
                "method": "POST",
                "note": "API key holders can skip payment"
            }
        },
        "payment": {
            "wallet": "7vvNkG3JF3JpxLEavqZSkc5T3n9hHR98Uw23fbWdXVSF",
            "token_mint": "Gpmbh4PoQnL1kNgpMYDED3iv4fczcr7d3qNBLf8rpump",
            "tx_max_age_minutes": 10
        },
        "request_format": {
            "required_fields": ["wallet", "tx_signature"],
            "example": {
                "url": "https://example.com",
                "format": "text",
                "wallet": "YourWalletAddress...",
                "tx_signature": "YourTxSignature..."
            }
        }
    })


if __name__ == '__main__':
    port = int(os.getenv('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
