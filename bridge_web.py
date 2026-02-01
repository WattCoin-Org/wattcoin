"""
Grok-Claude Bridge - Web Interface v1.2.0
Human-in-the-loop AI collaboration for WattCoin project
+ Proxy endpoint for external API calls (Moltbook, etc.)
+ Admin dashboard for bounty management

CHANGELOG v1.2.0:
- Added admin blueprint for bounty dashboard
- Added /admin/* routes
- Requires ADMIN_PASSWORD env var for dashboard access
"""

import os
import json
import time
import random
import ipaddress
import socket
from urllib.parse import urlparse
from collections import defaultdict, deque

import requests
from bs4 import BeautifulSoup
from datetime import datetime
from flask import Flask, render_template_string, request, session, jsonify
from anthropic import Anthropic
from openai import OpenAI

app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY", "wattcoin-dev-key-change-in-prod")

# =============================================================================
# REGISTER ADMIN BLUEPRINT
# =============================================================================
from admin_blueprint import admin_bp
app.register_blueprint(admin_bp)

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

SCRAPE_USER_AGENTS = [
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.2 Safari/605.1.15",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_2 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.2 Mobile/15E148 Safari/604.1",
    "Mozilla/5.0 (iPad; CPU OS 17_2 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.2 Mobile/15E148 Safari/604.1",
]

_rate_limit_ip = defaultdict(deque)
_rate_limit_url = defaultdict(deque)


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
    data = request.get_json(silent=True) or {}
    target_url = data.get('url', '').strip()
    output_format = (data.get('format') or 'text').strip().lower()

    if not target_url:
        return jsonify({'success': False, 'error': 'URL required'}), 400
    if output_format not in {'text', 'html', 'json'}:
        return jsonify({'success': False, 'error': 'Invalid format'}), 400
    if not _validate_scrape_url(target_url):
        return jsonify({'success': False, 'error': 'Invalid or blocked URL'}), 400

    client_ip = _get_client_ip()
    allowed, retry_after = _check_rate_limit(client_ip, target_url)
    if not allowed:
        return jsonify({
            'success': False,
            'error': 'Rate limit exceeded',
            'retry_after_seconds': retry_after
        }), 429

    headers = {
        'User-Agent': random.choice(SCRAPE_USER_AGENTS),
        'Accept': 'text/html,application/json;q=0.9,*/*;q=0.8',
        'Accept-Language': 'en-US,en;q=0.9'
    }

    try:
        resp = _fetch_with_redirects(target_url, headers)
    except requests.Timeout:
        return jsonify({'success': False, 'error': 'Request timeout'}), 504
    except ValueError as e:
        return jsonify({'success': False, 'error': str(e)}), 400
    except requests.RequestException as e:
        return jsonify({'success': False, 'error': f'Request failed: {str(e)}'}), 502

    if resp.status_code in {401, 403, 429}:
        return jsonify({
            'success': False,
            'error': 'Request blocked',
            'status_code': resp.status_code
        }), 403

    try:
        raw_bytes = _read_limited_content(resp)
        encoding = resp.encoding or 'utf-8'
        if output_format == 'html':
            content = raw_bytes.decode(encoding, errors='replace')
        elif output_format == 'json':
            content = json.loads(raw_bytes.decode(encoding, errors='replace'))
        else:
            html_text = raw_bytes.decode(encoding, errors='replace')
            soup = BeautifulSoup(html_text, 'html.parser')
            content = soup.get_text(separator=' ', strip=True)
    except ValueError as e:
        if str(e) == 'Response too large':
            return jsonify({'success': False, 'error': 'Response too large'}), 413
        return jsonify({'success': False, 'error': 'Invalid JSON response'}), 502
    except Exception as e:
        return jsonify({'success': False, 'error': f'Parsing error: {str(e)}'}), 500

    return jsonify({
        'success': True,
        'url': target_url,
        'content': content,
        'format': output_format,
        'status_code': resp.status_code,
        'timestamp': datetime.utcnow().isoformat() + 'Z'
    }), 200


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
    return jsonify({
        'status': 'ok', 
        'version': '1.2.0',
        'grok': bool(grok_client), 
        'claude': bool(claude_client),
        'proxy': True,
        'admin': True
    })


if __name__ == '__main__':
    port = int(os.getenv('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
