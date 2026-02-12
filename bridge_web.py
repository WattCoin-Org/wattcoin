"""
AI-Claude Bridge - Web Interface v2.2.0
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

# App start time for uptime calculation (placed outside docstring)
APP_START_TIME = time.time()
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
app.secret_key = os.getenv("SECRET_KEY", "")

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

# CORS - allow wattcoin.org
CORS(app, origins=[
    "https://wattcoin.org",
    "https://www.wattcoin.org"
])

# =============================================================================
# RATE LIMITING (Flask-Limiter)
# =============================================================================
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

# Initialize Flask-Limiter with Redis storage (fallback to memory if Redis unavailable)
limiter = Limiter(
    app=app,
    key_func=get_remote_address,
    default_limits=["1000 per hour", "100 per minute"],  # Global defaults
    storage_uri=os.getenv("REDIS_URL", "memory://"),  # Use Redis if available, else in-memory
    storage_options={"socket_connect_timeout": 30},
    strategy="fixed-window",
    headers_enabled=True,  # Add X-RateLimit-* headers to responses
)

# Custom rate limit error handler
@app.errorhandler(429)
def ratelimit_handler(e):
    logger.warning(f"Rate limit exceeded: {request.remote_addr} - {request.path}")
    return jsonify({
        "error": "Rate limit exceeded",
        "message": "Too many requests. Please slow down and try again later.",
        "retry_after": e.description if hasattr(e, "description") else "60 seconds"
    }), 429

logger.info("Flask-Limiter initialized with default limits: 1000/hour, 100/minute")

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
from api_webhooks import webhooks_bp, process_payment_queue, load_reputation_data
from api_wsi import wsi_bp, process_wsi_payout_queue
from api_swarmsolve import swarmsolve_bp
from data_backup import backup_bp
from internal_pipeline import internal_bp
from eval_replay import eval_replay_bp
app.register_blueprint(admin_bp)
app.register_blueprint(bounties_bp)
app.register_blueprint(llm_bp)
app.register_blueprint(reputation_bp)
app.register_blueprint(tasks_bp)
app.register_blueprint(nodes_bp)
app.register_blueprint(pr_review_bp)
app.register_blueprint(webhooks_bp)
app.register_blueprint(wsi_bp)
app.register_blueprint(swarmsolve_bp)
app.register_blueprint(backup_bp)
app.register_blueprint(internal_bp)
app.register_blueprint(eval_replay_bp)

# Apply endpoint-specific rate limits after blueprint registration
limiter.limit("10 per minute")(llm_bp)  # LLM queries are expensive - strict limit
limiter.limit("100 per minute")(bounties_bp)  # Stats/queries - moderate limit
limiter.limit("100 per minute")(reputation_bp)  # Stats/queries - moderate limit
limiter.limit("50 per minute")(webhooks_bp)  # Webhooks - moderate limit
limiter.limit("100 per minute")(tasks_bp)  # Task queries - moderate limit
limiter.limit("100 per minute")(nodes_bp)  # Node queries - moderate limit
limiter.limit("100 per minute")(pr_review_bp)  # PR review queries - moderate limit
limiter.limit("200 per minute")(wsi_bp)  # WSI interface - higher limit for UI
limiter.limit("20 per minute")(swarmsolve_bp)  # SwarmSolve - moderate (on-chain verification is slow)
# Admin blueprint - no additional limit (inherits global defaults)

logger.info("Blueprint-specific rate limits applied successfully")

# =============================================================================
# API CLIENTS
# =============================================================================
AI_API_KEY = os.getenv("AI_API_KEY")
CLAUDE_API_KEY = os.getenv("CLAUDE_API_KEY")
PROXY_SECRET = os.getenv("PROXY_SECRET", "")

if not AI_API_KEY or not CLAUDE_API_KEY:
    print("WARNING: Set AI_API_KEY and CLAUDE_API_KEY environment variables")

ai_client = None
claude_client = None

def init_clients():
    global ai_client, claude_client
    if AI_API_KEY:
        ai_client = OpenAI(api_key=AI_API_KEY, base_url=os.getenv("AI_API_BASE_URL", ""))
    if CLAUDE_API_KEY:
        claude_client = Anthropic(api_key=CLAUDE_API_KEY)

init_clients()

# Process any pending payments from queue (e.g., interrupted by deploy restart)
import threading
def _startup_payment_check():
    """Process pending payments 15 seconds after startup to let app fully initialize."""
    import time
    time.sleep(15)
    try:
        # Seed reputation data if missing (auto-creates contributor_reputation.json)
        load_reputation_data()
        process_payment_queue()
    except Exception as e:
        print(f"[STARTUP] Payment queue processing error: {e}", flush=True)
    try:
        process_wsi_payout_queue()
    except Exception as e:
        print(f"[STARTUP] WSI payout queue processing error: {e}", flush=True)

threading.Thread(target=_startup_payment_check, daemon=True).start()
print("[STARTUP] Payment queue check scheduled (15s delay)", flush=True)

# Periodic WSI payout processing — runs every 5 minutes
# (Bounty payouts trigger on deploy; WSI queries don't cause deploys)
WSI_PAYOUT_INTERVAL = int(os.environ.get('WSI_PAYOUT_INTERVAL', '300'))  # seconds, default 5 min

def _periodic_wsi_payout():
    """Process WSI payout queue on a recurring interval."""
    import time
    time.sleep(60)  # Initial delay — let startup processing finish first
    while True:
        try:
            process_wsi_payout_queue()
        except Exception as e:
            print(f"[WSI-TIMER] Payout processing error: {e}", flush=True)
        time.sleep(WSI_PAYOUT_INTERVAL)

threading.Thread(target=_periodic_wsi_payout, daemon=True).start()
print(f"[STARTUP] WSI payout timer scheduled (every {WSI_PAYOUT_INTERVAL}s)", flush=True)

# Periodic security scan — runs once daily at configured hour (UTC)
SECURITY_SCAN_HOUR = int(os.environ.get('SECURITY_SCAN_HOUR', '3'))  # UTC hour, default 3 AM

def _periodic_security_scan():
    """Run full repo security scan daily at scheduled hour."""
    import time
    from datetime import datetime, timezone, timedelta
    time.sleep(120)  # Initial delay — let startup finish
    while True:
        try:
            now = datetime.now(timezone.utc)
            # Calculate next run time
            target = now.replace(hour=SECURITY_SCAN_HOUR, minute=0, second=0, microsecond=0)
            if target <= now:
                target += timedelta(days=1)
            wait_seconds = (target - now).total_seconds()
            print(f"[SECURITY-SCAN] Next scheduled scan in {wait_seconds/3600:.1f}h at {target.strftime('%H:%M UTC')}", flush=True)
            time.sleep(wait_seconds)
            # Run scan
            from security_scanner import scheduled_scan
            scheduled_scan()
        except Exception as e:
            print(f"[SECURITY-SCAN] Cron error: {e}", flush=True)
            time.sleep(3600)  # Wait 1hr on error before retrying

threading.Thread(target=_periodic_security_scan, daemon=True).start()
print(f"[STARTUP] Security scan cron scheduled (daily at {SECURITY_SCAN_HOUR}:00 UTC)", flush=True)

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
DATA_FILE = "/app/data/bounty_reviews.json"
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


# =============================================================================
# BOUNTY DATA HANDLING
# =============================================================================

def load_bounty_data():
    """Load payout data for stats endpoint."""
    try:
        payout_file = "/app/data/pr_payouts.json"
        with open(payout_file, 'r') as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        logger.warning("Failed to load payout data, returning empty")
        return {"payouts": []}


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

AI_SYSTEM = f"""You are the Strategy Consultant for the WattCoin project.
Your role: High-level strategy, market analysis, tokenomics advice, launch planning.
Project context: {WATTCOIN_CONTEXT}
Keep responses focused and actionable. You're collaborating with Claude (implementation/coder)."""

CLAUDE_SYSTEM = f"""You are the Implementation Lead for the WattCoin project.
Your role: Technical implementation, coding, smart contracts, infrastructure.
Project context: {WATTCOIN_CONTEXT}
Keep responses focused and actionable. You're collaborating with AI strategy consultant."""

WATTBOT_SYSTEM = f"""You are WattBot, the official AI assistant for the WattCoin project.
You help users understand WattCoin, its services, and how to participate.

{WATTCOIN_CONTEXT}

Key services:
- LLM Proxy: Pay 500 WATT per AI query (you're it!)
- Web Scraper API: Pay 100 WATT to scrape any URL
- WattNode Network: Run a node, earn 70% of job payments
- Bounty Program: Claim GitHub issues, submit PRs, earn WATT after AI review
- Autonomous Agent Payments: AI agents can earn WATT for code contributions

How to participate:
- Buy WATT on pump.fun (CA: Gpmbh4PoQnL1kNgpMYDED3iv4fczcr7d3qNBLf8rpump)
- Run a WattNode to earn from distributed jobs
- Claim bounties on GitHub (WattCoin-Org/wattcoin)
- Build AI agents that contribute code and earn WATT

Links:
- Website: https://wattcoin.org
- GitHub: https://github.com/WattCoin-Org/wattcoin
- Discord: https://discord.gg/K3sWgQKk
- Twitter: https://x.com/WattCoin2026

Be helpful, concise, and enthusiastic about the project. If you don't know something specific, say so rather than guessing. You are NOT a financial advisor — never give investment advice."""

def query_ai(prompt, history=[]):
    if not ai_client:
        return "Error: AI API key not configured"
    messages = [{"role": "system", "content": AI_SYSTEM}]
    messages.extend(history)
    messages.append({"role": "user", "content": prompt})
    
    response = ai_client.chat.completions.create(
        model=os.getenv("AI_CHAT_MODEL", ""),
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
    <title>WattCoin - AI/Claude Bridge</title>
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
        .response-box.ai { border-left-color: #ff6600; }
        .response-box.claude { border-left-color: #00aaff; }
        .response-box h3 { margin-bottom: 15px; display: flex; align-items: center; gap: 10px; }
        .response-box.ai h3 { color: #ff6600; }
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
    <p class="subtitle">AI (Strategy) ↔ Claude (Implementation) | Proxy: Active</p>
    
    {% if status %}
    <div class="status {{ status.type }}">{{ status.message }}</div>
    {% endif %}
    
    <div class="input-section">
        <form method="POST" action="/query" id="mainForm">
            <textarea name="prompt" placeholder="Enter your topic or question for the AI collaboration..." required>{{ prompt or '' }}</textarea>
            <div class="buttons">
                <button type="submit" class="btn btn-primary">🚀 Send to AI</button>
                <button type="button" class="btn btn-secondary" onclick="clearHistory()">🗑️ Clear History</button>
            </div>
        </form>
    </div>
    
    <div class="loading" id="loading">
        <span class="spinner">⚡</span> Processing...
    </div>
    
    {% if ai_response %}
    <div class="response-box ai">
        <h3>🤖 AI (Strategy)</h3>
        <div class="response-content">{{ ai_response }}</div>
        <div class="buttons">
            <form method="POST" action="/send-to-claude" style="display:inline;">
                <input type="hidden" name="ai_response" value="{{ ai_response }}">
                <input type="hidden" name="original_prompt" value="{{ prompt }}">
                <button type="submit" class="btn btn-primary">✅ Send to Claude</button>
            </form>
            <button type="button" class="btn btn-secondary" onclick="showEdit()">✏️ Edit Prompt</button>
            <form method="POST" action="/skip-claude" style="display:inline;">
                <input type="hidden" name="ai_response" value="{{ ai_response }}">
                <input type="hidden" name="original_prompt" value="{{ prompt }}">
                <button type="submit" class="btn btn-secondary">⏭️ Skip Claude</button>
            </form>
        </div>
        <div id="editPrompt">
            <form method="POST" action="/send-to-claude">
                <textarea name="custom_prompt" placeholder="Custom prompt for Claude..."></textarea>
                <input type="hidden" name="ai_response" value="{{ ai_response }}">
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
            <form method="POST" action="/send-to-ai" style="display:inline;">
                <input type="hidden" name="claude_response" value="{{ claude_response }}">
                <button type="submit" class="btn btn-secondary">🔄 Send to AI</button>
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
            <div class="response-box ai" style="margin:10px 0;">
                <h3>🤖 AI</h3>
                <div class="response-content">{{ ex.ai }}</div>
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
    ai_history = session.get('ai_history', [])
    
    try:
        ai_response = query_ai(prompt, ai_history)
        session['pending_ai'] = ai_response
        session['ai_history'] = ai_history + [
            {"role": "user", "content": prompt},
            {"role": "assistant", "content": ai_response}
        ]
        return render_template_string(HTML_TEMPLATE, 
            prompt=prompt, ai_response=ai_response, history=history)
    except Exception as e:
        return render_template_string(HTML_TEMPLATE, 
            history=history, status={'type': 'error', 'message': f'AI error: {str(e)}'})

@app.route('/send-to-claude', methods=['POST'])
def send_to_claude():
    ai_response = request.form.get('ai_response', '')
    original_prompt = request.form.get('original_prompt', '')
    custom_prompt = request.form.get('custom_prompt', '')
    
    history = session.get('history', [])
    claude_history = session.get('claude_history', [])
    
    if custom_prompt:
        claude_prompt = custom_prompt
    else:
        claude_prompt = f"AI strategy consultant said:\n\n{ai_response}\n\nRespond with implementation perspective."
    
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
            'ai': ai_response,
            'claude': claude_response
        })
        session['history'] = history
        
        return render_template_string(HTML_TEMPLATE,
            prompt=original_prompt, ai_response=ai_response, 
            claude_response=claude_response, history=history)
    except Exception as e:
        return render_template_string(HTML_TEMPLATE,
            history=history, status={'type': 'error', 'message': f'Claude error: {str(e)}'})

@app.route('/skip-claude', methods=['POST'])
def skip_claude():
    ai_response = request.form.get('ai_response', '')
    original_prompt = request.form.get('original_prompt', '')
    history = session.get('history', [])
    
    history.append({
        'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M'),
        'prompt': original_prompt,
        'ai': ai_response,
        'claude': '[skipped]'
    })
    session['history'] = history
    
    return render_template_string(HTML_TEMPLATE, history=history,
        status={'type': 'success', 'message': 'Skipped Claude, logged AI response.'})

@app.route('/send-to-ai', methods=['POST'])
def send_to_ai():
    claude_response = request.form.get('claude_response', '')
    prompt = f"Claude (implementation) responded:\n\n{claude_response}\n\nYour thoughts?"
    
    history = session.get('history', [])
    ai_history = session.get('ai_history', [])
    
    try:
        ai_response = query_ai(prompt, ai_history)
        session['ai_history'] = ai_history + [
            {"role": "user", "content": prompt},
            {"role": "assistant", "content": ai_response}
        ]
        return render_template_string(HTML_TEMPLATE,
            prompt=prompt, ai_response=ai_response, history=history)
    except Exception as e:
        return render_template_string(HTML_TEMPLATE,
            history=history, status={'type': 'error', 'message': f'AI error: {str(e)}'})

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
                        node_result = wait_for_job_result(job_id, timeout=60)
                        
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

@app.route('/api/v1/llm', methods=['POST'])
def llm_query():
    """
    Public LLM endpoint - requires WATT payment.
    
    Request:
        {
            "prompt": "What is WattCoin?",
            "wallet": "AgentWallet...",
            "tx_signature": "..."
        }
    
    Pricing: 500 WATT per query
    """
    LLM_PRICE_WATT = 500
    
    try:
        data = request.get_json(silent=True) or {}
        prompt = (data.get('prompt') or '').strip()
        wallet = (data.get('wallet') or '').strip()
        tx_signature = (data.get('tx_signature') or '').strip()
        client_ip = _get_client_ip()
        
        logger.info("llm request | ip=%s wallet=%.40s prompt_len=%d", client_ip, wallet or '<none>', len(prompt))
        
        # Validate prompt
        if not prompt:
            return jsonify({"success": False, "error": "prompt required"}), 400
        if len(prompt) > 4000:
            return jsonify({"success": False, "error": "prompt too long (max 4000 chars)"}), 400
        
        # Validate payment params
        if not wallet or not tx_signature:
            return jsonify({"success": False, "error": "wallet and tx_signature required"}), 400
        
        # Verify WATT payment
        verified, error_code, error_message = verify_watt_payment(
            tx_signature, wallet, LLM_PRICE_WATT
        )
        
        if not verified:
            logger.warning("llm payment failed | ip=%s error=%s", client_ip, error_code)
            return jsonify({"success": False, "error": error_message}), 400
        
        logger.info("llm payment verified | ip=%s wallet=%.40s", client_ip, wallet)
        save_used_signature(tx_signature)
        
        # Query AI with WattBot persona
        if not ai_client:
            return jsonify({"success": False, "error": "AI service unavailable"}), 503
        
        messages = [
            {"role": "system", "content": WATTBOT_SYSTEM},
            {"role": "user", "content": prompt}
        ]
        
        response = ai_client.chat.completions.create(
            model=os.getenv("AI_CHAT_MODEL", ""),
            messages=messages,
            max_tokens=2048
        )
        
        ai_response = response.choices[0].message.content
        tokens_used = getattr(response.usage, 'total_tokens', 0)
        
        logger.info("llm response | ip=%s tokens=%d", client_ip, tokens_used)
        
        return jsonify({
            "success": True,
            "response": ai_response,
            "tokens_used": tokens_used,
            "watt_charged": LLM_PRICE_WATT
        })
        
    except Exception as e:
        logger.error("llm error | %s", str(e))
        return jsonify({"success": False, "error": "Internal error processing query"}), 500


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
    """Health check endpoint with service status checks.
    
    Returns 200 if healthy, 503 if critical service degraded.
    All checks are lightweight (<500ms total) - no HTTP calls.
    Maintains backward compatibility with existing fields.
    """
    # Initialize services dict with defaults
    services = {
        'database': 'ok',
        'discord': 'ok',
        'ai_api': 'ok'
    }
    critical_degraded = False
    
    # Check 1: Data files readable (lightweight - just check existence)
    try:
        data_files = [
            'data/contributor_reputation.json',
            'data/reputation.json',
            'data/security_logs.json'
        ]
        data_ok = all(os.path.exists(f) for f in data_files)
        services['database'] = 'ok' if data_ok else 'degraded'
        if not data_ok:
            critical_degraded = True
    except Exception:
        services['database'] = 'degraded'
        critical_degraded = True
    
    # Check 2: Discord webhook configured (check env var exists)
    try:
        discord_ok = bool(os.getenv('DISCORD_WEBHOOK_URL', ''))
        services['discord'] = 'ok' if discord_ok else 'degraded'
    except Exception:
        services['discord'] = 'degraded'
    
    # Check 3: AI API key present (check env vars exist)
    try:
        ai_api_ok = bool(os.getenv('AI_API_KEY', '')) and bool(os.getenv('CLAUDE_API_KEY', ''))
        services['ai_api'] = 'ok' if ai_api_ok else 'degraded'
        if not ai_api_ok:
            critical_degraded = True
    except Exception:
        services['ai_api'] = 'degraded'
        critical_degraded = True
    
    # Get active nodes count
    try:
        active_nodes = len(get_active_nodes())
    except Exception:
        active_nodes = 0
    
    # Count open tasks from data files (with error handling)
    open_tasks = 0
    try:
        if os.path.exists('data/tasks.json'):
            with open('data/tasks.json', 'r') as f:
                tasks_data = json.load(f)
                open_tasks = len([t for t in tasks_data if t.get('status') == 'open'])
    except Exception:
        open_tasks = 0
    
    # Calculate uptime
    try:
        uptime_seconds = int(time.time() - APP_START_TIME)
    except Exception:
        uptime_seconds = 0
    
    # Build response maintaining backward compatibility
    response = {
        # Legacy fields (maintain backward compatibility)
        'status': 'healthy' if not critical_degraded else 'degraded',
        'version': '3.4.0',
        'ai': bool(ai_client), 
        'claude': bool(claude_client),
        'proxy': True,
        'admin': True,
        'active_nodes': active_nodes,
        # New fields
        'uptime_seconds': uptime_seconds,
        'services': services,
        'open_tasks': open_tasks,
        'timestamp': datetime.utcnow().isoformat() + 'Z'
    }
    
    status_code = 200 if not critical_degraded else 503
    return jsonify(response), status_code


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
                "description": "Query AI",
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
            "wallet": os.getenv("BOUNTY_WALLET_ADDRESS", ""),
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


@app.route('/api/v1/bounty-stats', methods=['GET'])
def bounty_stats():
    """
    Public bounty statistics for website.
    
    Returns live stats on paid and pending bounties.
    """
    try:
        data = load_bounty_data()
        payouts = data.get("payouts", [])
        
        # Filter paid vs pending
        paid = [p for p in payouts if p.get("status") == "paid"]
        pending = [p for p in payouts if p.get("status") != "paid"]
        
        # Calculate totals
        total_paid_watt = sum(p.get("amount", 0) for p in paid)
        total_pending_watt = sum(p.get("amount", 0) for p in pending)
        
        # Average bounty
        all_amounts = [p.get("amount", 0) for p in payouts if p.get("amount", 0) > 0]
        avg_bounty = sum(all_amounts) // len(all_amounts) if all_amounts else 0
        
        # Recent payouts (last 10, most recent first)
        recent = sorted(
            [p for p in paid if p.get("paid_at")],
            key=lambda x: x.get("paid_at", ""),
            reverse=True
        )[:10]
        
        # Format recent for public display
        recent_formatted = []
        for p in recent:
            recent_formatted.append({
                "pr_number": p.get("pr_number"),
                "author": p.get("author"),
                "amount": p.get("amount", 0),
                "paid_at": p.get("paid_at"),
                "tx_sig": p.get("tx_signature", p.get("tx_sig", ""))
            })
        
        # Contributor leaderboard (aggregate by author)
        contributor_totals = {}
        for p in paid:
            author = p.get("author", "unknown")
            if author not in contributor_totals:
                contributor_totals[author] = {"total_earned": 0, "pr_count": 0}
            contributor_totals[author]["total_earned"] += p.get("amount", 0)
            contributor_totals[author]["pr_count"] += 1
        
        leaderboard = sorted(
            [{"username": k, **v} for k, v in contributor_totals.items()],
            key=lambda x: x["total_earned"],
            reverse=True
        )
        
        return jsonify({
            "success": True,
            "total_paid_count": len(paid),
            "total_paid_watt": total_paid_watt,
            "total_pending_count": len(pending),
            "total_pending_watt": total_pending_watt,
            "avg_bounty": avg_bounty,
            "recent_payouts": recent_formatted,
            "leaderboard": leaderboard,
            "updated_at": datetime.now().isoformat() + "Z"
        })
        
    except Exception as e:
        logger.error(f"Bounty stats error: {e}")
        return jsonify({
            "success": False,
            "error": "Failed to load bounty statistics"
        }), 500


if __name__ == '__main__':
    port = int(os.getenv('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)







