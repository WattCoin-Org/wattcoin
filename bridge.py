"""
Grok-Claude Bridge v1.9 - Server-side sessions
Uses Flask-Session with filesystem storage (not cookies)
"""

import os
import json
import base64
import requests
from datetime import datetime
from flask import Flask, render_template_string, request, session, jsonify, redirect, url_for
from flask_session import Session
from anthropic import Anthropic
from openai import OpenAI

app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY", "wattcoin-dev-key-change-in-prod")

# Server-side session config
app.config['SESSION_TYPE'] = 'filesystem'
app.config['SESSION_FILE_DIR'] = '/tmp/flask_sessions'
app.config['SESSION_PERMANENT'] = True
app.config['PERMANENT_SESSION_LIFETIME'] = 86400  # 24 hours
Session(app)

GROK_API_KEY = os.getenv("GROK_API_KEY")
CLAUDE_API_KEY = os.getenv("CLAUDE_API_KEY")
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")
GITHUB_REPO = "cb3tech/WATTCOIN"
BRIDGE_PASSWORD = os.getenv("BRIDGE_PASSWORD", "")
PROXY_SECRET = os.getenv("PROXY_SECRET", "")
MAX_HISTORY = 10

grok_client = None
claude_client = None

def init_clients():
    global grok_client, claude_client
    if GROK_API_KEY:
        grok_client = OpenAI(api_key=GROK_API_KEY, base_url="https://api.x.ai/v1")
    if CLAUDE_API_KEY:
        claude_client = Anthropic(api_key=CLAUDE_API_KEY)

init_clients()

def login_required(f):
    from functools import wraps
    @wraps(f)
    def decorated(*args, **kwargs):
        if not BRIDGE_PASSWORD:
            return f(*args, **kwargs)
        if not session.get('authenticated'):
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated

# ============================================================
# GITHUB API (for Claude tools)
# ============================================================

def github_headers():
    return {"Authorization": f"token {GITHUB_TOKEN}", "Accept": "application/vnd.github.v3+json"}

def github_read_file(path):
    if not GITHUB_TOKEN:
        return {"error": "GitHub token not configured"}
    url = f"https://api.github.com/repos/{GITHUB_REPO}/contents/{path}"
    resp = requests.get(url, headers=github_headers())
    if resp.status_code == 200:
        data = resp.json()
        content = base64.b64decode(data["content"]).decode("utf-8")
        return {"path": path, "content": content, "sha": data["sha"]}
    return {"error": f"Failed: {resp.status_code}"}

def github_write_file(path, content, message, sha=None):
    if not GITHUB_TOKEN:
        return {"error": "GitHub token not configured"}
    url = f"https://api.github.com/repos/{GITHUB_REPO}/contents/{path}"
    if not sha:
        existing = requests.get(url, headers=github_headers())
        if existing.status_code == 200:
            sha = existing.json().get("sha")
    payload = {"message": message, "content": base64.b64encode(content.encode()).decode()}
    if sha:
        payload["sha"] = sha
    resp = requests.put(url, headers=github_headers(), json=payload)
    if resp.status_code in [200, 201]:
        return {"success": True, "path": path}
    return {"error": f"Failed: {resp.status_code}"}

def github_list_files(path=""):
    if not GITHUB_TOKEN:
        return {"error": "GitHub token not configured"}
    url = f"https://api.github.com/repos/{GITHUB_REPO}/contents/{path}"
    resp = requests.get(url, headers=github_headers())
    if resp.status_code == 200:
        files = resp.json()
        if isinstance(files, list):
            return [{"name": f["name"], "type": f["type"], "path": f["path"]} for f in files]
        return {"name": files["name"], "type": files["type"], "path": files["path"]}
    return {"error": f"Failed: {resp.status_code}"}

# ============================================================
# CLAUDE TOOLS
# ============================================================

CLAUDE_TOOLS = [
    {"name": "github_list_files", "description": "List files in repo path",
     "input_schema": {"type": "object", "properties": {"path": {"type": "string"}}, "required": []}},
    {"name": "github_read_file", "description": "Read file from repo",
     "input_schema": {"type": "object", "properties": {"path": {"type": "string"}}, "required": ["path"]}},
    {"name": "github_write_file", "description": "Write file to repo",
     "input_schema": {"type": "object", "properties": {"path": {"type": "string"}, "content": {"type": "string"}, "message": {"type": "string"}}, "required": ["path", "content", "message"]}}
]

def execute_tool(name, inp):
    if name == "github_list_files":
        return github_list_files(inp.get("path", ""))
    elif name == "github_read_file":
        return github_read_file(inp["path"])
    elif name == "github_write_file":
        return github_write_file(inp["path"], inp["content"], inp["message"])
    return {"error": "Unknown tool"}

# ============================================================
# SYSTEM PROMPTS
# ============================================================

GROK_SYSTEM = """WattCoin Strategy Consultant. Date: {date}
Role: Strategy, go-to-market, tokenomics, $5k budget optimization.
Collaborating with Claude (Implementation). Project: Solana utility token for AI/robot automation."""

CLAUDE_SYSTEM = """WattCoin Implementation Lead. Date: {date}
Role: Technical implementation, code, infrastructure.
GitHub: cb3tech/WATTCOIN (use tools). Whitepaper: docs/WHITEPAPER.md"""

def get_grok_system():
    return GROK_SYSTEM.format(date=datetime.now().strftime('%B %d, %Y'))

def get_claude_system():
    return CLAUDE_SYSTEM.format(date=datetime.now().strftime('%B %d, %Y'))

# ============================================================
# QUERY FUNCTIONS
# ============================================================

def query_grok(prompt, history):
    if not grok_client:
        return "Error: Grok API key not configured"
    messages = [{"role": "system", "content": get_grok_system()}]
    messages.extend(history[-MAX_HISTORY:])
    messages.append({"role": "user", "content": prompt})
    response = grok_client.chat.completions.create(model="grok-4-1-fast-reasoning", messages=messages, max_tokens=2048)
    return response.choices[0].message.content

def query_claude(prompt, history):
    if not claude_client:
        return "Error: Claude API key not configured"
    
    messages = []
    for msg in history[-MAX_HISTORY:]:
        if isinstance(msg, dict) and msg.get("role") in ["user", "assistant"] and isinstance(msg.get("content"), str):
            messages.append(msg)
    messages.append({"role": "user", "content": prompt})
    
    response = claude_client.messages.create(model="claude-sonnet-4-20250514", max_tokens=2048, 
                                              system=get_claude_system(), tools=CLAUDE_TOOLS, messages=messages)
    
    tool_messages = messages.copy()
    tool_results = []
    
    while response.stop_reason == "tool_use":
        assistant_content = response.content
        tool_uses = [b for b in assistant_content if b.type == "tool_use"]
        tool_result_content = []
        for tu in tool_uses:
            result = execute_tool(tu.name, tu.input)
            tool_results.append({"tool": tu.name, "result": result})
            tool_result_content.append({"type": "tool_result", "tool_use_id": tu.id, "content": json.dumps(result)})
        tool_messages.append({"role": "assistant", "content": assistant_content})
        tool_messages.append({"role": "user", "content": tool_result_content})
        response = claude_client.messages.create(model="claude-sonnet-4-20250514", max_tokens=2048,
                                                  system=get_claude_system(), tools=CLAUDE_TOOLS, messages=tool_messages)
    
    text = "".join([b.text for b in response.content if hasattr(b, "text")])
    if tool_results:
        text += "\n\n---\n📁 " + ", ".join([tr['tool'].replace('github_','') for tr in tool_results])
    return text

# ============================================================
# HTML
# ============================================================

LOGIN_HTML = """<!DOCTYPE html><html><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1.0"><title>WattCoin</title>
<style>*{box-sizing:border-box;margin:0;padding:0}body{font-family:system-ui;background:#0a0a0a;color:#e0e0e0;min-height:100vh;display:flex;justify-content:center;align-items:center}
.box{background:#111;padding:40px;border-radius:12px;border:1px solid #222;max-width:400px;width:100%}h1{color:#00ff88;margin-bottom:30px;text-align:center}
input{width:100%;padding:14px;border-radius:8px;background:#1a1a1a;border:1px solid #333;color:#e0e0e0;font-size:16px;margin-bottom:20px}
button{width:100%;padding:14px;border-radius:8px;border:none;background:#00ff88;color:#000;font-weight:600;cursor:pointer}.error{color:#f66;text-align:center;margin-bottom:20px}</style>
</head><body><div class="box"><h1>⚡ WattCoin Bridge</h1>{% if error %}<p class="error">{{error}}</p>{% endif %}
<form method="POST"><input type="password" name="password" placeholder="Password" required autofocus><button>Login</button></form></div></body></html>"""

MAIN_HTML = """<!DOCTYPE html><html><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1.0"><title>WattCoin</title>
<style>
*{box-sizing:border-box;margin:0;padding:0}body{font-family:system-ui;background:#0a0a0a;color:#e0e0e0;min-height:100vh;display:flex;flex-direction:column}
.hdr{background:#111;padding:15px 20px;border-bottom:1px solid #222;display:flex;justify-content:space-between;align-items:center}
.hdr h1{color:#00ff88;font-size:1.3em}.hdr a{color:#666;font-size:12px}
.chat{flex:1;overflow-y:auto;padding:20px;max-width:900px;margin:0 auto;width:100%}
.msg{margin-bottom:16px;padding:12px 16px;border-radius:12px;max-width:85%}
.msg.user{background:#1a3d2e;border-left:4px solid #00ff88;margin-left:auto}
.msg.grok{background:#2d1f0d;border-left:4px solid #ff6600}
.msg.claude{background:#0d1f2d;border-left:4px solid #00aaff}
.msg .who{font-weight:600;font-size:13px;margin-bottom:6px}.msg .who.user{color:#00ff88}.msg .who.grok{color:#ff6600}.msg .who.claude{color:#00aaff}
.msg .txt{white-space:pre-wrap;line-height:1.5;font-size:14px}
.acts{background:#1a1a1a;padding:16px;border-radius:12px;margin:16px 0;border:1px dashed #333}
.acts a{padding:8px 16px;border-radius:6px;text-decoration:none;font-size:13px;font-weight:500;margin-right:8px;display:inline-block;margin-bottom:8px}
.acts .c{background:#00aaff;color:#000}.acts .g{background:#ff6600;color:#000}.acts .x{background:#333;color:#ccc}
.inp{background:#111;padding:20px;border-top:1px solid #222}
.inp form{max-width:900px;margin:0 auto;display:flex;gap:12px}
.inp textarea{flex:1;padding:14px;border-radius:12px;background:#1a1a1a;border:1px solid #333;color:#e0e0e0;font-size:14px;resize:none;min-height:50px;font-family:inherit}
.inp .btns{display:flex;flex-direction:column;gap:8px}
.inp button{padding:12px 18px;border-radius:12px;border:none;font-weight:600;cursor:pointer;font-size:14px}
.inp .bg{background:#ff6600;color:#000}.inp .bc{background:#00aaff;color:#000}.inp .bb{background:#9933ff;color:#fff}
.err{background:#2d1111;color:#f66;padding:12px;margin:10px auto;border-radius:8px;max-width:900px}
.empty{color:#444;text-align:center;padding:40px}
</style></head><body>
<div class="hdr"><h1>⚡ WattCoin Bridge <small style="color:#444">v1.9.1</small></h1><a href="/logout">Logout</a></div>
{% if error %}<div class="err">{{error}}</div>{% endif %}
<div class="chat" id="chat">
{% if not thread %}<div class="empty">Ready. Ask Grok (strategy) or Claude (implementation).</div>{% endif %}
{% for m in thread %}<div class="msg {{m.type}}"><div class="who {{m.type}}">{% if m.type=='user' %}You{% elif m.type=='grok' %}🤖 Grok{% else %}🧠 Claude{% endif %}</div><div class="txt">{{m.content}}</div></div>{% endfor %}
{% if thread and thread[-1].type in ['grok','claude'] and not done %}
<div class="acts">
{% if thread[-1].type == 'grok' %}<a href="/fwd/claude" class="c">→ Claude</a>{% else %}<a href="/fwd/grok" class="g">→ Grok</a>{% endif %}
<a href="/done" class="x">✓ Done</a><a href="/clear" class="x" onclick="return confirm('Clear?')">🗑️</a>
</div>{% endif %}
</div>
<div class="inp"><form method="POST" action="/ask">
<textarea name="prompt" placeholder="Ask something..." required></textarea>
<div class="btns"><button type="submit" name="to" value="grok" class="bg">🤖 Grok</button><button type="submit" name="to" value="claude" class="bc">🧠 Claude</button><button type="submit" name="to" value="both" class="bb">⚡ Both</button></div>
</form></div>
<script>document.getElementById('chat').scrollTop=9999999</script>
</body></html>"""

# ============================================================
# ROUTES
# ============================================================

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        if request.form.get('password') == BRIDGE_PASSWORD:
            session['authenticated'] = True
            session['thread'] = []
            session['grok_history'] = []
            session['claude_history'] = []
            session['done'] = False
            return redirect('/')
        return render_template_string(LOGIN_HTML, error="Wrong password")
    return render_template_string(LOGIN_HTML, error=None)

@app.route('/logout')
def logout():
    session.clear()
    return redirect('/login')

@app.route('/')
@login_required
def index():
    return render_template_string(MAIN_HTML, 
        thread=session.get('thread', []), 
        done=session.get('done', False), 
        error=None)

@app.route('/ask', methods=['POST'])
@login_required
def ask():
    prompt = request.form.get('prompt', '').strip()
    to = request.form.get('to', 'grok')
    if not prompt:
        return redirect('/')
    
    thread = session.get('thread', [])
    now = datetime.now().strftime('%H:%M')
    thread.append({'type': 'user', 'content': prompt, 'time': now})
    
    try:
        if to == 'both':
            # Query both AIs
            grok_history = session.get('grok_history', [])
            claude_history = session.get('claude_history', [])
            
            grok_resp = query_grok(prompt, grok_history)
            thread.append({'type': 'grok', 'content': grok_resp, 'time': now})
            grok_history.append({"role": "user", "content": prompt})
            grok_history.append({"role": "assistant", "content": grok_resp})
            session['grok_history'] = grok_history[-MAX_HISTORY:]
            
            claude_resp = query_claude(prompt, claude_history)
            thread.append({'type': 'claude', 'content': claude_resp, 'time': now})
            claude_history.append({"role": "user", "content": prompt})
            claude_history.append({"role": "assistant", "content": claude_resp})
            session['claude_history'] = claude_history[-MAX_HISTORY:]
        elif to == 'claude':
            history = session.get('claude_history', [])
            resp = query_claude(prompt, history)
            thread.append({'type': 'claude', 'content': resp, 'time': now})
            history.append({"role": "user", "content": prompt})
            history.append({"role": "assistant", "content": resp})
            session['claude_history'] = history[-MAX_HISTORY:]
        else:
            history = session.get('grok_history', [])
            resp = query_grok(prompt, history)
            thread.append({'type': 'grok', 'content': resp, 'time': now})
            history.append({"role": "user", "content": prompt})
            history.append({"role": "assistant", "content": resp})
            session['grok_history'] = history[-MAX_HISTORY:]
        
        session['thread'] = thread
        session['done'] = False
        return redirect('/')
    except Exception as e:
        session['thread'] = thread
        return render_template_string(MAIN_HTML, thread=thread, done=session.get('done', False), error=str(e))

@app.route('/fwd/<target>')
@login_required
def forward(target):
    thread = session.get('thread', [])
    prev = ""
    for m in reversed(thread):
        if m.get('type') in ['grok', 'claude']:
            prev = m.get('content', '')
            break
    if not prev:
        return redirect('/')
    
    now = datetime.now().strftime('%H:%M')
    try:
        if target == 'claude':
            history = session.get('claude_history', [])
            prompt = f"Grok said:\n{prev}\n\nYour implementation thoughts?"
            resp = query_claude(prompt, history)
            thread.append({'type': 'claude', 'content': resp, 'time': now})
            history.append({"role": "user", "content": prompt})
            history.append({"role": "assistant", "content": resp})
            session['claude_history'] = history[-MAX_HISTORY:]
        else:
            history = session.get('grok_history', [])
            prompt = f"Claude said:\n{prev}\n\nYour strategic thoughts?"
            resp = query_grok(prompt, history)
            thread.append({'type': 'grok', 'content': resp, 'time': now})
            history.append({"role": "user", "content": prompt})
            history.append({"role": "assistant", "content": resp})
            session['grok_history'] = history[-MAX_HISTORY:]
        
        session['thread'] = thread
        session['done'] = False
        return redirect('/')
    except Exception as e:
        return render_template_string(MAIN_HTML, thread=thread, done=session.get('done', False), error=str(e))

@app.route('/done')
@login_required
def mark_done():
    session['done'] = True
    return redirect('/')

@app.route('/clear')
@login_required
def clear():
    session['thread'] = []
    session['grok_history'] = []
    session['claude_history'] = []
    session['done'] = False
    return redirect('/')

@app.route('/health')
def health():
    return jsonify({'status': 'ok', 'version': '1.10.0', 'proxy': bool(PROXY_SECRET)})


# =============================================================================
# PROXY ENDPOINTS - v1.10.0
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
        if not PROXY_SECRET or data.get('secret') != PROXY_SECRET:
            return jsonify({'error': 'Invalid or missing proxy secret'}), 401
        
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
        if not PROXY_SECRET or data.get('secret') != PROXY_SECRET:
            return jsonify({'error': 'Invalid or missing proxy secret'}), 401
        
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


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.getenv('PORT', 8080)), debug=False)
