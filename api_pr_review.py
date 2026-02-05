"""
WattCoin PR Review API
POST /api/v1/review_pr - Submit a PR for Grok review

Checks:
- Rate limits
- PR format validation
- Calls Grok to review diff
- Scans for dangerous code
- Logs review results
- Posts review comment on GitHub
"""

import os
import json
import time
import requests
from datetime import datetime
from flask import Blueprint, request, jsonify
from openai import OpenAI

from pr_security import (
    check_rate_limit,
    record_pr_submission,
    validate_pr_format,
    extract_wallet_from_pr_body,
    scan_dangerous_code,
    log_security_event,
    check_emergency_pause,
    load_json_data,
    save_json_data,
    DATA_DIR
)

pr_review_bp = Blueprint('pr_review', __name__)

# =============================================================================
# CONFIG
# =============================================================================

GROK_API_KEY = os.getenv("GROK_API_KEY")
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")
REPO = "WattCoin-Org/wattcoin"

PR_REVIEWS_FILE = f"{DATA_DIR}/pr_reviews.json"

# Grok client
grok_client = None
if GROK_API_KEY:
    grok_client = OpenAI(api_key=GROK_API_KEY, base_url="https://api.x.ai/v1")

# =============================================================================
# GITHUB HELPERS
# =============================================================================

def github_headers():
    """Get GitHub API headers."""
    headers = {"Accept": "application/vnd.github.v3+json"}
    if GITHUB_TOKEN:
        headers["Authorization"] = f"token {GITHUB_TOKEN}"
    return headers

def get_pr_details(pr_number):
    """
    Fetch PR details from GitHub.
    Returns: (pr_data, error)
    """
    try:
        # Get PR info
        pr_url = f"https://api.github.com/repos/{REPO}/pulls/{pr_number}"
        resp = requests.get(pr_url, headers=github_headers(), timeout=15)
        
        if resp.status_code != 200:
            return None, f"Failed to fetch PR: {resp.status_code}"
        
        pr_data = resp.json()
        
        # Get PR diff
        diff_url = pr_data.get("diff_url")
        if diff_url:
            diff_resp = requests.get(diff_url, headers=github_headers(), timeout=30)
            if diff_resp.status_code == 200:
                pr_data["diff"] = diff_resp.text
            else:
                pr_data["diff"] = None
        
        # Get referenced issues from body
        pr_data["referenced_issues"] = extract_referenced_issues(pr_data.get("body", ""))
        
        return pr_data, None
        
    except Exception as e:
        return None, f"Error fetching PR: {e}"

def extract_referenced_issues(text):
    """Extract issue numbers referenced in text (e.g., #123, closes #456)."""
    import re
    if not text:
        return []
    
    # Match patterns like #123, closes #456, fixes #789
    pattern = r'(?:closes?|fixes?|resolves?|references?)?\s*#(\d+)'
    matches = re.findall(pattern, text, re.IGNORECASE)
    
    # Also match standalone #123
    standalone = re.findall(r'#(\d+)', text)
    
    all_issues = set(matches + standalone)
    return [int(n) for n in all_issues]

def post_pr_comment(pr_number, comment):
    """Post a comment on a PR."""
    if not GITHUB_TOKEN:
        return False
    
    try:
        url = f"https://api.github.com/repos/{REPO}/issues/{pr_number}/comments"
        resp = requests.post(
            url,
            headers=github_headers(),
            json={"body": comment},
            timeout=15
        )
        return resp.status_code in [200, 201]
    except:
        return False

# =============================================================================
# GROK REVIEW
# =============================================================================

GROK_REVIEW_PROMPT = """You are reviewing a Pull Request for the WattCoin project.

Repository: https://github.com/WattCoin-Org/wattcoin
WattCoin is a Solana utility token for AI/robot automation with distributed compute network.

PR Details:
- Number: {pr_number}
- Title: {title}
- Author: {author}
- Files Changed: {files_changed}
- Additions: +{additions} / Deletions: -{deletions}

PR Description:
{body}

Code Diff:
```diff
{diff}
```

Review Guidelines:
1. **Functionality**: Does it improve features, fix bugs, or add useful capabilities?
2. **Code Quality**: Clean, readable, follows existing patterns?
3. **Security**: No vulnerabilities, no breaking changes without justification?
4. **Scope**: Changes match PR description, no unrelated modifications?
5. **Testing**: Would need testing? Are tests included if applicable?

Dangerous patterns already flagged: {security_warnings}

Rate the PR on a scale of 1-10:
- 10: Excellent, production-ready
- 8-9: Good, minor improvements possible
- 6-7: Acceptable with changes
- 4-5: Needs significant work
- 1-3: Major issues, reject

A score of **8 or higher** passes initial review (subject to human approval).

Respond ONLY with valid JSON in this exact format:
{{
  "pass": true/false,
  "score": 1-10,
  "feedback": "Brief summary of review (2-3 sentences)",
  "suggested_changes": ["specific change 1", "specific change 2"],
  "concerns": ["security concern 1", "quality concern 2"]
}}

Do not include any text before or after the JSON."""

def call_grok_review(pr_data, security_warnings):
    """
    Call Grok API to review PR.
    Returns: (review_result, error)
    """
    if not grok_client:
        return None, "Grok API not configured"
    
    try:
        # Prepare prompt
        diff_text = pr_data.get("diff", "")[:8000]  # Limit diff size
        
        # Security warnings summary
        warnings_text = "None"
        if security_warnings:
            warnings_text = "\n".join([
                f"- {w['pattern']}: {w['context'][:60]}..."
                for w in security_warnings[:5]
            ])
        
        prompt = GROK_REVIEW_PROMPT.format(
            pr_number=pr_data.get("number"),
            title=pr_data.get("title", ""),
            author=pr_data.get("user", {}).get("login", "unknown"),
            files_changed=pr_data.get("changed_files", 0),
            additions=pr_data.get("additions", 0),
            deletions=pr_data.get("deletions", 0),
            body=pr_data.get("body", "")[:500],
            diff=diff_text,
            security_warnings=warnings_text
        )
        
        # Call Grok
        response = grok_client.chat.completions.create(
            model="grok-code-fast-1",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.3,
            max_tokens=1000
        )
        
        result_text = response.choices[0].message.content.strip()
        
        # Parse JSON response
        # Remove markdown code blocks if present
        if result_text.startswith("```"):
            result_text = result_text.split("```")[1]
            if result_text.startswith("json"):
                result_text = result_text[4:]
        
        review = json.loads(result_text)
        
        # Validate required fields
        required = ["pass", "score", "feedback"]
        if not all(k in review for k in required):
            return None, f"Invalid Grok response format: missing fields"
        
        # Ensure score is int
        review["score"] = int(review["score"])
        
        # Ensure pass is bool (score >= 8)
        review["pass"] = review["score"] >= 8
        
        return review, None
        
    except json.JSONDecodeError as e:
        return None, f"Failed to parse Grok response as JSON: {e}"
    except Exception as e:
        return None, f"Grok API error: {e}"

# =============================================================================
# REVIEW ENDPOINT
# =============================================================================

@pr_review_bp.route('/api/v1/review_pr', methods=['POST'])
def review_pr():
    """
    Review a PR using Grok API.
    
    Body:
    {
      "pr_url": "https://github.com/WattCoin-Org/wattcoin/pull/123",
      "bounty_issue_id": 45  // optional
    }
    
    Returns:
    {
      "success": true,
      "review": {
        "pass": true,
        "score": 9,
        "feedback": "...",
        "suggested_changes": [...],
        "concerns": [...]
      },
      "security": {
        "is_safe": true,
        "warnings": [...]
      },
      "pr_number": 123,
      "comment_posted": true
    }
    """
    # Check emergency pause
    is_paused, pause_type, pause_msg = check_emergency_pause()
    if is_paused and pause_type == "reviews":
        return jsonify({
            "success": False,
            "error": pause_msg
        }), 503
    
    # Parse request
    data = request.get_json()

    # Log incoming request for debugging
    print(f"[REVIEW API] Received request - Content-Type: {request.content_type}", flush=True)
    print(f"[REVIEW API] Data keys: {list(data.keys()) if data else 'None'}", flush=True)
    if data:
        print(f"[REVIEW API] pr_url present: {'pr_url' in data}, value: {data.get('pr_url', 'N/A')[:80]}", flush=True)

    if not data:
        print(f"[REVIEW API] Validation failed: Request body required", flush=True)
        return jsonify({
            "success": False,
            "error": "Request body required"
        }), 400
    
    pr_url = data.get("pr_url", "").strip()
    bounty_issue_id = data.get("bounty_issue_id")
    
    if not pr_url:
        return jsonify({
            "success": False,
            "error": "pr_url is required"
        }), 400
    
    # Extract PR number from URL
    import re
    match = re.search(r'/pull/(\d+)', pr_url)
    if not match:
        return jsonify({
            "success": False,
            "error": "Invalid PR URL format"
        }), 400
    
    pr_number = int(match.group(1))
    
    # Fetch PR details
    pr_data, pr_error = get_pr_details(pr_number)
    if pr_error:
        return jsonify({
            "success": False,
            "error": pr_error
        }), 400
    
    # Validate PR format
    is_valid, format_errors = validate_pr_format(pr_data.get("body", ""))
    if not is_valid:
        log_security_event("blocked_pr", {
            "pr_number": pr_number,
            "reason": "invalid_format",
            "errors": format_errors
        })
        
        return jsonify({
            "success": False,
            "error": "PR format validation failed",
            "format_errors": format_errors
        }), 400
    
    # Extract wallet
    wallet, wallet_error = extract_wallet_from_pr_body(pr_data.get("body", ""))
    if wallet_error:
        return jsonify({
            "success": False,
            "error": wallet_error
        }), 400
    
    # Check rate limit
    is_allowed, rate_error, remaining = check_rate_limit(wallet)
    if not is_allowed:
        log_security_event("rate_limit", {
            "pr_number": pr_number,
            "wallet": wallet,
            "reason": rate_error
        })
        
        return jsonify({
            "success": False,
            "error": rate_error,
            "remaining_prs": 0
        }), 429
    
    # Scan for dangerous code
    diff_text = pr_data.get("diff", "")
    is_safe, security_warnings = scan_dangerous_code(diff_text)
    
    if not is_safe:
        log_security_event("dangerous_code", {
            "pr_number": pr_number,
            "wallet": wallet,
            "warnings": security_warnings
        })
        
        # Don't block entirely, but flag heavily in review
        # (Grok will see the warnings)
    
    # Call Grok for review
    review_result, review_error = call_grok_review(pr_data, security_warnings)
    if review_error:
        return jsonify({
            "success": False,
            "error": review_error
        }), 500
    
    # Record submission
    record_pr_submission(wallet)
    
    # Save review to database
    reviews = load_json_data(PR_REVIEWS_FILE, default={"reviews": []})
    
    review_record = {
        "pr_number": pr_number,
        "pr_url": pr_url,
        "wallet": wallet,
        "bounty_issue_id": bounty_issue_id,
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "review": review_result,
        "security": {
            "is_safe": is_safe,
            "warnings": security_warnings
        },
        "pr_data": {
            "title": pr_data.get("title"),
            "author": pr_data.get("user", {}).get("login"),
            "merged": pr_data.get("merged", False),
            "state": pr_data.get("state")
        }
    }
    
    reviews["reviews"].append(review_record)
    
    # Keep only last 500 reviews
    if len(reviews["reviews"]) > 500:
        reviews["reviews"] = reviews["reviews"][-500:]
    
    save_json_data(PR_REVIEWS_FILE, reviews)
    
    # Post comment on PR
    comment = f"""## 🤖 Grok Review Results

**Score**: {review_result['score']}/10
**Status**: {'✅ PASS' if review_result['pass'] else '❌ FAIL'}

**Feedback**: {review_result['feedback']}

"""
    
    if review_result.get("suggested_changes"):
        comment += "**Suggested Changes**:\n"
        for change in review_result["suggested_changes"]:
            comment += f"- {change}\n"
        comment += "\n"
    
    if review_result.get("concerns"):
        comment += "**Concerns**:\n"
        for concern in review_result["concerns"]:
            comment += f"- ⚠️ {concern}\n"
        comment += "\n"
    
    if not is_safe:
        comment += f"**⚠️ Security Warnings Detected**: {len(security_warnings)} potential issues found in code scan.\n\n"
    
    if review_result["pass"]:
        comment += "*This PR has passed initial automated review. A maintainer will review for final approval and merge.*\n"
    else:
        comment += "*This PR needs improvements before it can be merged. Please address the feedback above.*\n"
    
    comment_posted = post_pr_comment(pr_number, comment)
    
    # Return response
    return jsonify({
        "success": True,
        "review": review_result,
        "security": {
            "is_safe": is_safe,
            "warnings": security_warnings
        },
        "pr_number": pr_number,
        "wallet": wallet,
        "remaining_prs": remaining - 1,
        "comment_posted": comment_posted
    }), 200
