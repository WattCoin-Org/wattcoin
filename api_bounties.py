"""
WattCoin Bounties API - Public endpoint for AI agents
GET /api/v1/bounties - List available bounties and agent tasks

Query params:
  - type: all (default), bounty, agent
  - tier: low, medium, high
  - status: open, claimed
  - min_amount: minimum WATT reward

No auth required. Cached for 5 minutes.
"""

import os
import re
import json
import time
import requests
from datetime import datetime, timedelta, timezone
from flask import Blueprint, jsonify, request
from collections import defaultdict

bounties_bp = Blueprint('bounties', __name__)

# Config
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN", "")
REPO = "WattCoin-Org/wattcoin"
STAKE_WALLET = os.getenv("BOUNTY_WALLET_ADDRESS", "7vvNkG3JF3JpxLEavqZSkc5T3n9hHR98Uw23fbWdXVSF")
DOCS_URL = "https://github.com/WattCoin-Org/wattcoin/blob/main/CONTRIBUTING.md"
CACHE_TTL = 300  # 5 minutes

# Cache
_bounties_cache = {"data": None, "expires": 0}

def github_headers():
    """Get GitHub API headers."""
    headers = {"Accept": "application/vnd.github.v3+json"}
    if GITHUB_TOKEN:
        headers["Authorization"] = f"token {GITHUB_TOKEN}"
    return headers

def parse_bounty_amount(title):
    """Extract bounty amount from issue title like '[BOUNTY: 100,000 WATT]'"""
    match = re.search(r'(\d{1,3}(?:,?\d{3})*)\s*WATT', title, re.IGNORECASE)
    if match:
        return int(match.group(1).replace(',', ''))
    return 0

def get_tier(amount):
    """Determine tier based on amount."""
    if amount >= 100000:
        return "high"
    elif amount >= 20000:
        return "medium"
    return "low"

def parse_claimed_info(comments):
    """Parse claiming info from issue comments."""
    for comment in comments:
        body = (comment.get("body") or "").lower()
        if "claiming" in body or "i claim" in body:
            user = comment.get("user", {}).get("login", "")
            created_at = comment.get("created_at", "")
            
            # Look for wallet in comment
            wallet = None
            wallet_match = re.search(r'[1-9A-HJ-NP-Za-km-z]{32,44}', comment.get("body", ""))
            if wallet_match:
                wallet = wallet_match.group(0)
            
            return {
                "claimed_by": wallet,
                "claimed_by_github": user,
                "claimed_at": created_at
            }
    return None

def fetch_bounties():
    """Fetch bounties and agent tasks from GitHub API."""
    now = time.time()
    
    # Check cache
    if _bounties_cache["data"] and now < _bounties_cache["expires"]:
        return _bounties_cache["data"]
    
    bounties = []
    seen_ids = set()
    
    try:
        # Fetch issues with bounty OR agent-task labels (two calls, merge)
        labels_to_fetch = ["bounty", "agent-task"]
        all_issues = []
        
        for label in labels_to_fetch:
            url = f"https://api.github.com/repos/{REPO}/issues?labels={label}&state=open&per_page=100"
            resp = requests.get(url, headers=github_headers(), timeout=15)
            
            if resp.status_code == 200:
                all_issues.extend(resp.json())
        
        for issue in all_issues:
            # Skip PRs (they show up in issues endpoint)
            if issue.get("pull_request"):
                continue
            
            issue_number = issue.get("number")
            
            # Dedupe (in case issue has both labels)
            if issue_number in seen_ids:
                continue
            seen_ids.add(issue_number)
            title = issue.get("title", "")
            amount = parse_bounty_amount(title)
            
            if amount == 0:
                continue
            
            # Determine type from labels (agent-task takes priority)
            label_names = [l.get("name", "").lower() for l in issue.get("labels", [])]
            if "agent-task" in label_names:
                item_type = "agent"
            else:
                item_type = "bounty"
            
            # Clean title (remove bounty/agent-task tag)
            clean_title = re.sub(r'\[(BOUNTY|AGENT TASK)[:\s]*[\d,]+\s*WATT\]\s*', '', title, flags=re.IGNORECASE).strip()
            
            # Get issue body for description
            body = issue.get("body") or ""
            # Extract first paragraph as description
            description = ""
            if "## Description" in body:
                desc_match = re.search(r'## Description\s*\n+([^\n#]+)', body)
                if desc_match:
                    description = desc_match.group(1).strip()[:200]
            elif body:
                description = body.split('\n')[0][:200]
            
            # Check for claims in comments
            claimed_info = None
            status = "open"
            deadline = None
            
            # Fetch comments to check for claims
            comments_url = f"https://api.github.com/repos/{REPO}/issues/{issue_number}/comments"
            comments_resp = requests.get(comments_url, headers=github_headers(), timeout=10)
            if comments_resp.status_code == 200:
                comments = comments_resp.json()
                claimed_info = parse_claimed_info(comments)
                if claimed_info:
                    status = "claimed"
                    # Calculate deadline (7 days from claim)
                    if claimed_info.get("claimed_at"):
                        try:
                            claimed_dt = datetime.fromisoformat(claimed_info["claimed_at"].replace("Z", "+00:00"))
                            deadline_dt = claimed_dt + timedelta(days=7)
                            deadline = deadline_dt.isoformat().replace("+00:00", "Z")
                        except:
                            pass
            
            bounty = {
                "id": issue_number,
                "type": item_type,
                "title": clean_title,
                "amount": amount,
                "stake_required": int(amount * 0.1) if item_type == "bounty" else 0,
                "tier": get_tier(amount),
                "status": status,
                "url": issue.get("html_url"),
                "created_at": issue.get("created_at"),
                "description": description,
                "claimed_by": claimed_info.get("claimed_by") if claimed_info else None,
                "claimed_by_github": claimed_info.get("claimed_by_github") if claimed_info else None,
                "claimed_at": claimed_info.get("claimed_at") if claimed_info else None,
                "deadline": deadline
            }
            
            bounties.append(bounty)
        
        # Sort by amount descending
        bounties.sort(key=lambda x: x["amount"], reverse=True)
        
        # Update cache
        _bounties_cache["data"] = bounties
        _bounties_cache["expires"] = now + CACHE_TTL
        
    except Exception as e:
        print(f"Error fetching bounties: {e}")
    
    return bounties

@bounties_bp.route('/api/v1/bounties', methods=['GET'])
def list_bounties():
    """Public endpoint to list all bounties and agent tasks."""
    bounties = fetch_bounties()
    
    # Apply filters
    type_filter = request.args.get('type', 'all').lower()
    tier_filter = request.args.get('tier')
    status_filter = request.args.get('status')
    min_amount = request.args.get('min_amount', type=int)
    
    filtered = bounties
    
    # Type filter
    if type_filter == 'bounty':
        filtered = [b for b in filtered if b["type"] == "bounty"]
    elif type_filter == 'agent':
        filtered = [b for b in filtered if b["type"] == "agent"]
    # 'all' returns everything
    
    if tier_filter:
        filtered = [b for b in filtered if b["tier"] == tier_filter]
    
    if status_filter:
        filtered = [b for b in filtered if b["status"] == status_filter]
    
    if min_amount:
        filtered = [b for b in filtered if b["amount"] >= min_amount]
    
    # Calculate summary stats
    total_bounties = len([b for b in filtered if b["type"] == "bounty"])
    total_agent_tasks = len([b for b in filtered if b["type"] == "agent"])
    total_watt = sum(b["amount"] for b in filtered)
    
    return jsonify({
        "total": len(filtered),
        "total_bounties": total_bounties,
        "total_agent_tasks": total_agent_tasks,
        "total_watt": total_watt,
        "items": filtered,
        "stake_wallet": STAKE_WALLET,
        "docs": DOCS_URL,
        "cached_until": datetime.fromtimestamp(_bounties_cache["expires"]).isoformat() + "Z" if _bounties_cache["expires"] else None
    })


# ============================================================
# AUTONOMOUS BOUNTY PROPOSAL SYSTEM v1.0
# Agents propose improvements → AI evaluates/prices → auto-creates bounty
# ============================================================

# --- Config ---
MAX_AUTO_APPROVE_WATT = 20000       # Auto-create up to this amount
DAILY_CAP_WATT = 100000             # Total WATT auto-created per day
RATE_LIMIT_PER_HOUR = 3             # Max proposals per agent per hour
RATE_LIMIT_PER_DAY = 10             # Max proposals per agent per day
PROPOSALS_FILE = "/app/data/bounty_proposals.json"
API_KEYS_FILE = "/app/data/api_keys.json"
BORDERLINE_SCORE_MIN = 7            # Score 7-8 → manual review queue
BORDERLINE_SCORE_MAX = 8
AUTO_APPROVE_MIN_SCORE = 8          # Score ≥ 8 → auto-approve (if within caps)

# Blacklist: reject proposals mentioning these off-mission topics
BLACKLIST_KEYWORDS = [
    "marketing", "social media", "twitter campaign", "influencer",
    "logo redesign", "color scheme", "font change", "favicon",
    "tiktok", "instagram", "youtube video", "meme",
    "airdrop campaign", "pump", "listing fee", "exchange listing"
]

# In-memory rate tracking (resets on container restart - acceptable for v1)
_rate_tracker = defaultdict(list)    # key -> [timestamps]
_daily_watt_tracker = {"date": None, "total": 0}


def load_api_keys():
    """Load API keys from JSON file."""
    try:
        with open(API_KEYS_FILE, 'r') as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {"keys": {}}


def validate_api_key(api_key):
    """Validate API key and return key data or None."""
    if not api_key:
        return None
    # Check env var key first (for agents/testing without admin dashboard)
    env_key = os.getenv("PROPOSAL_API_KEY", "")
    if env_key and api_key == env_key:
        return {"owner_wallet": "env_proposal_key", "tier": "basic", "status": "active"}
    # Then check stored keys
    data = load_api_keys()
    key_data = data.get("keys", {}).get(api_key)
    if key_data and key_data.get("status") == "active":
        return key_data
    return None


def check_rate_limit(api_key):
    """
    Check rate limits: 3/hour + 10/day per agent.
    Returns (allowed, error_message).
    """
    now = time.time()
    hour_ago = now - 3600
    day_ago = now - 86400

    # Clean old entries
    _rate_tracker[api_key] = [t for t in _rate_tracker[api_key] if t > day_ago]

    # Count recent
    hour_count = sum(1 for t in _rate_tracker[api_key] if t > hour_ago)
    day_count = len(_rate_tracker[api_key])

    if hour_count >= RATE_LIMIT_PER_HOUR:
        return False, f"Rate limit exceeded: {RATE_LIMIT_PER_HOUR} proposals/hour. Try again later."
    if day_count >= RATE_LIMIT_PER_DAY:
        return False, f"Daily limit exceeded: {RATE_LIMIT_PER_DAY} proposals/day. Try again tomorrow."

    return True, None


def record_rate_limit(api_key):
    """Record a proposal attempt for rate limiting."""
    _rate_tracker[api_key].append(time.time())


def check_daily_cap(amount):
    """
    Check if auto-approving this amount would exceed daily cap.
    Returns (allowed, remaining).
    """
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    if _daily_watt_tracker["date"] != today:
        _daily_watt_tracker["date"] = today
        _daily_watt_tracker["total"] = 0

    remaining = DAILY_CAP_WATT - _daily_watt_tracker["total"]
    if amount > remaining:
        return False, remaining

    return True, remaining


def record_daily_cap(amount):
    """Record approved WATT against daily cap."""
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    if _daily_watt_tracker["date"] != today:
        _daily_watt_tracker["date"] = today
        _daily_watt_tracker["total"] = 0
    _daily_watt_tracker["total"] += amount


def check_blacklist(title, description):
    """Check for off-mission blacklisted topics. Returns matched keyword or None."""
    combined = f"{title} {description}".lower()
    for kw in BLACKLIST_KEYWORDS:
        if kw in combined:
            return kw
    return None


def search_duplicate_issues(title, description):
    """
    Search GitHub for potential duplicate open issues.
    Returns list of similar issues or empty list.
    """
    if not GITHUB_TOKEN:
        return []

    # Extract key terms for search (first 3 significant words)
    words = re.findall(r'\b[a-zA-Z]{4,}\b', title)
    search_query = " ".join(words[:4]) if words else title[:50]

    try:
        url = f"https://api.github.com/search/issues?q={search_query}+repo:{REPO}+is:issue+is:open&per_page=5"
        resp = requests.get(url, headers=github_headers(), timeout=10)
        if resp.status_code == 200:
            results = resp.json().get("items", [])
            duplicates = []
            for issue in results:
                duplicates.append({
                    "id": issue["number"],
                    "title": issue["title"],
                    "url": issue["html_url"]
                })
            return duplicates
    except Exception as e:
        print(f"[PROPOSAL] Duplicate search error: {e}", flush=True)

    return []


def create_bounty_issue(title, description, amount, category, proposer_wallet, evaluation):
    """
    Create a GitHub issue with bounty label and formatting.
    Returns (issue_url, issue_number) or (None, error).
    """
    if not GITHUB_TOKEN:
        return None, "GITHUB_TOKEN not configured"

    # Format issue body
    body = f"""## Description
{description}

## Bounty Details
- **Amount**: {amount:,} WATT
- **Category**: {category}
- **Proposed by**: Agent (`{proposer_wallet[:8]}...{proposer_wallet[-4:]}`)
- **AI Evaluation Score**: {evaluation.get('score', 'N/A')}/10

## AI Evaluation
{evaluation.get('reasoning', 'N/A')}

## How to Claim
1. Comment on this issue with your Solana wallet address
2. Fork the repo and implement the solution
3. Submit a PR referencing this issue (e.g., "Fixes #{'{issue_number}'}")
4. AI will auto-review your code
5. On merge → automatic WATT payment

---
*This bounty was autonomously proposed and evaluated by the WattCoin agent system.* ⚡🤖
"""

    # Determine labels
    labels = ["bounty"]
    if category:
        labels.append(category)

    suggested_title = evaluation.get("suggested_title", "")
    issue_title = suggested_title if suggested_title else f"[BOUNTY: {amount:,} WATT] {title}"

    try:
        url = f"https://api.github.com/repos/{REPO}/issues"
        resp = requests.post(url, headers=github_headers(), json={
            "title": issue_title,
            "body": body,
            "labels": labels
        }, timeout=15)

        if resp.status_code == 201:
            issue = resp.json()
            return issue["html_url"], issue["number"]
        else:
            return None, f"GitHub API error: {resp.status_code} - {resp.text[:200]}"

    except Exception as e:
        return None, str(e)


def create_proposed_bounty_issue(title, description, amount, category, proposer_wallet, evaluation):
    """
    Create a GitHub issue with 'proposed-bounty' label for manual review.
    Used for borderline scores or amounts exceeding auto-approve cap.
    """
    if not GITHUB_TOKEN:
        return None, "GITHUB_TOKEN not configured"

    body = f"""## ⚠️ REQUIRES MANUAL REVIEW

**Reason**: {"Amount exceeds auto-approve cap" if amount > MAX_AUTO_APPROVE_WATT else "Borderline evaluation score"}

## Description
{description}

## Proposed Bounty Details
- **Proposed Amount**: {amount:,} WATT
- **Category**: {category}
- **Proposed by**: Agent (`{proposer_wallet[:8]}...{proposer_wallet[-4:]}`)
- **AI Evaluation Score**: {evaluation.get('score', 'N/A')}/10

## AI Evaluation
{evaluation.get('reasoning', 'N/A')}

## Admin Action Required
- Review the proposal and AI evaluation
- If approved: Change label from `proposed-bounty` to `bounty` and update title with `[BOUNTY: X WATT]`
- If rejected: Close issue with explanation

---
*This bounty was autonomously proposed but flagged for human review.* ⚡🤖
"""

    try:
        url = f"https://api.github.com/repos/{REPO}/issues"
        resp = requests.post(url, headers=github_headers(), json={
            "title": f"[PROPOSED BOUNTY: {amount:,} WATT] {title}",
            "body": body,
            "labels": ["proposed-bounty"]
        }, timeout=15)

        if resp.status_code == 201:
            issue = resp.json()
            return issue["html_url"], issue["number"]
        else:
            return None, f"GitHub API error: {resp.status_code} - {resp.text[:200]}"

    except Exception as e:
        return None, str(e)


def load_proposals_log():
    """Load proposals audit log."""
    try:
        with open(PROPOSALS_FILE, 'r') as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {"proposals": []}


def save_proposal_log(entry):
    """Append a proposal to the audit log."""
    try:
        data = load_proposals_log()
        data["proposals"].append(entry)
        # Keep last 500 entries
        if len(data["proposals"]) > 500:
            data["proposals"] = data["proposals"][-500:]
        os.makedirs(os.path.dirname(PROPOSALS_FILE), exist_ok=True)
        with open(PROPOSALS_FILE, 'w') as f:
            json.dump(data, f, indent=2)
    except Exception as e:
        print(f"[PROPOSAL] Error saving audit log: {e}", flush=True)


# Valid categories for proposals
VALID_CATEGORIES = [
    "wattnode",         # Node infrastructure
    "marketplace",      # Agent marketplace/tasks
    "skills",           # Skills/PR bounties
    "wsi",              # Swarm intelligence
    "security",         # Security improvements
    "core-api",         # Core utilities (scraping, inference, verification)
    "documentation",    # Docs improvements
    "integration",      # External integrations
    "bug-fix"           # Bug fixes
]


@bounties_bp.route('/api/v1/bounties/propose', methods=['POST'])
def propose_bounty():
    """
    Autonomous Bounty Proposal Endpoint v1.0

    Agents propose improvements → AI evaluates/prices → auto-creates bounty issue.

    Headers:
        X-API-Key: valid agent API key (required)

    Request JSON:
        {
            "title": "Add rate limiting to WattNode API",
            "description": "The /api/v1/nodes endpoint lacks rate limiting...",
            "category": "wattnode",
            "wallet": "AgentWalletAddress"
        }

    Response (approved):
        {
            "success": true,
            "decision": "APPROVED",
            "issue_url": "https://github.com/...",
            "issue_number": 99,
            "amount": 5000,
            "score": 9,
            "reasoning": "..."
        }

    Response (rejected):
        {
            "success": true,
            "decision": "REJECTED",
            "score": 4,
            "reasoning": "..."
        }
    """
    # --- 1. Auth: Validate API key ---
    api_key = request.headers.get('X-API-Key', '').strip()
    key_data = validate_api_key(api_key)
    if not key_data:
        return jsonify({
            "success": False,
            "error": "unauthorized",
            "message": "Valid X-API-Key header required"
        }), 401

    # --- 2. Rate limit check ---
    allowed, rate_error = check_rate_limit(api_key)
    if not allowed:
        return jsonify({
            "success": False,
            "error": "rate_limited",
            "message": rate_error
        }), 429

    # --- 3. Parse and validate request ---
    data = request.get_json()
    if not data:
        return jsonify({"success": False, "error": "invalid_json"}), 400

    title = data.get("title", "").strip()
    description = data.get("description", "").strip()
    category = data.get("category", "").strip().lower()
    wallet = data.get("wallet", "").strip()

    if not title:
        return jsonify({"success": False, "error": "missing_title", "message": "Title is required"}), 400
    if len(title) > 200:
        return jsonify({"success": False, "error": "title_too_long", "message": "Max 200 characters"}), 400
    if not description:
        return jsonify({"success": False, "error": "missing_description", "message": "Description is required (explain the problem and proposed solution)"}), 400
    if len(description) < 50:
        return jsonify({"success": False, "error": "description_too_short", "message": "Min 50 characters — provide enough detail for evaluation"}), 400
    if len(description) > 5000:
        return jsonify({"success": False, "error": "description_too_long", "message": "Max 5000 characters"}), 400
    if not wallet or len(wallet) < 32:
        return jsonify({"success": False, "error": "missing_wallet", "message": "Valid Solana wallet address required"}), 400
    if category and category not in VALID_CATEGORIES:
        return jsonify({
            "success": False,
            "error": "invalid_category",
            "message": f"Valid categories: {', '.join(VALID_CATEGORIES)}"
        }), 400

    # --- 4. Blacklist check ---
    blacklisted = check_blacklist(title, description)
    if blacklisted:
        log_entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "api_key": api_key[:8] + "...",
            "wallet": wallet,
            "title": title,
            "decision": "REJECTED",
            "reason": f"Blacklisted keyword: {blacklisted}",
            "score": 0,
            "amount": 0
        }
        save_proposal_log(log_entry)
        record_rate_limit(api_key)

        return jsonify({
            "success": True,
            "decision": "REJECTED",
            "score": 0,
            "reasoning": f"Proposal rejected: off-mission topic detected ('{blacklisted}'). "
                        f"WattCoin bounties must directly improve the agent economy — "
                        f"not marketing, social media, or cosmetic changes."
        })

    # --- 5. Duplicate check ---
    duplicates = search_duplicate_issues(title, description)
    # Flag if very similar titles found (simple substring check)
    title_lower = title.lower()
    close_matches = [d for d in duplicates if
                     title_lower in d["title"].lower() or
                     d["title"].lower() in title_lower]
    if close_matches:
        log_entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "api_key": api_key[:8] + "...",
            "wallet": wallet,
            "title": title,
            "decision": "REJECTED",
            "reason": "Duplicate detected",
            "duplicates": close_matches,
            "score": 0,
            "amount": 0
        }
        save_proposal_log(log_entry)
        record_rate_limit(api_key)

        return jsonify({
            "success": True,
            "decision": "REJECTED",
            "score": 0,
            "reasoning": "Potential duplicate detected. Similar open issues exist:",
            "duplicates": close_matches
        })

    # --- 6. AI Evaluation via bounty_evaluator ---
    print(f"[PROPOSAL] Evaluating: '{title}' from {wallet[:8]}...", flush=True)
    record_rate_limit(api_key)

    try:
        from bounty_evaluator import evaluate_bounty_request
        evaluation = evaluate_bounty_request(title, description, [category] if category else [])
    except Exception as e:
        print(f"[PROPOSAL] Evaluator error: {e}", flush=True)
        return jsonify({
            "success": False,
            "error": "evaluation_failed",
            "message": "AI evaluation system temporarily unavailable"
        }), 503

    if evaluation.get("decision") == "ERROR":
        return jsonify({
            "success": False,
            "error": "evaluation_error",
            "message": evaluation.get("error", "Unknown evaluation error")
        }), 503

    decision = evaluation.get("decision", "REJECT")
    score = evaluation.get("score", 0)
    amount = evaluation.get("amount", 0)
    reasoning = evaluation.get("reasoning", "")

    # --- 7. Decision routing ---

    # REJECT: score too low
    if decision == "REJECT" or score < BORDERLINE_SCORE_MIN:
        log_entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "api_key": api_key[:8] + "...",
            "wallet": wallet,
            "title": title,
            "category": category,
            "decision": "REJECTED",
            "reason": "AI evaluation: below threshold",
            "score": score,
            "amount": 0,
            "raw_reasoning": reasoning
        }
        save_proposal_log(log_entry)

        return jsonify({
            "success": True,
            "decision": "REJECTED",
            "score": score,
            "reasoning": reasoning
        })

    # BORDERLINE: score 7-8 OR amount > cap → manual review queue
    is_borderline_score = BORDERLINE_SCORE_MIN <= score < AUTO_APPROVE_MIN_SCORE
    is_over_cap = amount > MAX_AUTO_APPROVE_WATT

    if is_borderline_score or is_over_cap:
        # Create proposed-bounty issue for admin review
        issue_url, result = create_proposed_bounty_issue(
            title, description, amount, category, wallet, evaluation
        )

        queue_reason = []
        if is_borderline_score:
            queue_reason.append(f"borderline score ({score}/10)")
        if is_over_cap:
            queue_reason.append(f"amount exceeds auto-approve cap ({amount:,} > {MAX_AUTO_APPROVE_WATT:,} WATT)")

        log_entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "api_key": api_key[:8] + "...",
            "wallet": wallet,
            "title": title,
            "category": category,
            "decision": "QUEUED_FOR_REVIEW",
            "reason": ", ".join(queue_reason),
            "score": score,
            "amount": amount,
            "issue_url": issue_url,
            "issue_number": result if isinstance(result, int) else None,
            "raw_reasoning": reasoning
        }
        save_proposal_log(log_entry)

        return jsonify({
            "success": True,
            "decision": "QUEUED_FOR_REVIEW",
            "score": score,
            "proposed_amount": amount,
            "reasoning": reasoning,
            "queue_reason": ", ".join(queue_reason),
            "issue_url": issue_url,
            "issue_number": result if isinstance(result, int) else None,
            "message": "Proposal scored well but requires manual admin review before activation."
        })

    # APPROVE: score ≥ 8 AND amount ≤ 20K → check daily cap then auto-create
    cap_ok, remaining = check_daily_cap(amount)
    if not cap_ok:
        log_entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "api_key": api_key[:8] + "...",
            "wallet": wallet,
            "title": title,
            "category": category,
            "decision": "REJECTED",
            "reason": f"Daily cap reached ({DAILY_CAP_WATT:,} WATT). Remaining: {remaining:,} WATT",
            "score": score,
            "amount": amount,
            "raw_reasoning": reasoning
        }
        save_proposal_log(log_entry)

        return jsonify({
            "success": True,
            "decision": "REJECTED",
            "score": score,
            "proposed_amount": amount,
            "reasoning": f"Proposal approved by AI (score: {score}/10) but daily auto-creation cap "
                        f"reached ({DAILY_CAP_WATT:,} WATT/day). Remaining today: {remaining:,} WATT. "
                        f"Try again tomorrow or propose a smaller bounty."
        })

    # All checks passed — auto-create the bounty issue!
    issue_url, result = create_bounty_issue(
        title, description, amount, category, wallet, evaluation
    )

    if issue_url:
        record_daily_cap(amount)
        log_entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "api_key": api_key[:8] + "...",
            "wallet": wallet,
            "title": title,
            "category": category,
            "decision": "APPROVED",
            "score": score,
            "amount": amount,
            "issue_url": issue_url,
            "issue_number": result,
            "raw_reasoning": reasoning
        }
        save_proposal_log(log_entry)

        print(f"[PROPOSAL] ✅ Auto-created bounty #{result}: {amount:,} WATT - {title}", flush=True)

        return jsonify({
            "success": True,
            "decision": "APPROVED",
            "score": score,
            "amount": amount,
            "issue_url": issue_url,
            "issue_number": result,
            "reasoning": reasoning,
            "message": f"Bounty created! {amount:,} WATT bounty is now live."
        })
    else:
        # Issue creation failed
        return jsonify({
            "success": False,
            "error": "issue_creation_failed",
            "message": f"AI approved but GitHub issue creation failed: {result}"
        }), 500


@bounties_bp.route('/api/v1/bounties/proposals', methods=['GET'])
def list_proposals():
    """
    Public audit log of all bounty proposals.
    Shows recent proposals with decisions (no sensitive data).
    """
    data = load_proposals_log()
    proposals = data.get("proposals", [])

    # Return last 50, newest first
    recent = list(reversed(proposals[-50:]))

    # Strip raw_reasoning for public view (keep it concise)
    public = []
    for p in recent:
        public.append({
            "timestamp": p.get("timestamp"),
            "title": p.get("title"),
            "category": p.get("category"),
            "decision": p.get("decision"),
            "score": p.get("score"),
            "amount": p.get("amount"),
            "issue_url": p.get("issue_url"),
            "reason": p.get("reason", "")
        })

    summary = {
        "total_proposals": len(proposals),
        "approved": sum(1 for p in proposals if p.get("decision") == "APPROVED"),
        "rejected": sum(1 for p in proposals if p.get("decision") == "REJECTED"),
        "queued": sum(1 for p in proposals if p.get("decision") == "QUEUED_FOR_REVIEW"),
        "total_watt_approved": sum(p.get("amount", 0) for p in proposals if p.get("decision") == "APPROVED")
    }

    return jsonify({
        "success": True,
        "summary": summary,
        "recent": public,
        "daily_cap": DAILY_CAP_WATT,
        "daily_remaining": max(0, DAILY_CAP_WATT - _daily_watt_tracker.get("total", 0))
            if _daily_watt_tracker.get("date") == datetime.now(timezone.utc).strftime("%Y-%m-%d")
            else DAILY_CAP_WATT
    })
