"""
AI Evaluation Replay System
Replay historical PRs through current AI prompts for quality analysis.
Allows retroactive evaluation capture and manual annotation corrections.
"""

import os
import json
import time
import requests
from datetime import datetime, timezone
from flask import Blueprint, request, jsonify

eval_replay_bp = Blueprint('eval_replay', __name__)

ADMIN_API_KEY = os.getenv("ADMIN_API_KEY", "")
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN", "")
REPO = os.getenv("GITHUB_REPO", "WattCoin-Org/wattcoin")
INTERNAL_REPO = os.getenv("GITHUB_INTERNAL_REPO", "WattCoin-Org/wattcoin-internal")


def check_admin_auth(data):
    """Validate admin API key from request data."""
    admin_key = (data.get("admin_key") or "").strip()
    expected = ADMIN_API_KEY
    if not expected:
        return False, "Admin authentication not configured"
    if not admin_key:
        return False, "admin_key required"
    if admin_key != expected:
        return False, "Invalid admin_key"
    return True, None


def github_headers(accept_type="application/vnd.github.v3+json"):
    """Build GitHub API headers."""
    headers = {"Accept": accept_type}
    if GITHUB_TOKEN:
        headers["Authorization"] = f"token {GITHUB_TOKEN}"
    return headers


def fetch_pr_from_github(pr_number, repo=None):
    """
    Fetch PR details and diff from GitHub.
    
    Returns: (pr_info dict, error) or (None, error_message)
    """
    check_repo = repo or REPO
    
    try:
        # Fetch PR details
        pr_url = f"https://api.github.com/repos/{check_repo}/pulls/{pr_number}"
        pr_resp = requests.get(pr_url, headers=github_headers(), timeout=30)
        
        if pr_resp.status_code == 404:
            return None, f"PR #{pr_number} not found in {check_repo}"
        if pr_resp.status_code != 200:
            return None, f"GitHub API error: HTTP {pr_resp.status_code}"
        
        pr_data = pr_resp.json()
        
        # Fetch PR diff
        diff_resp = requests.get(
            pr_url,
            headers=github_headers("application/vnd.github.v3.diff"),
            timeout=30
        )
        
        if diff_resp.status_code != 200:
            return None, f"Failed to fetch diff: HTTP {diff_resp.status_code}"
        
        # Build pr_info dict matching call_ai_review signature
        pr_info = {
            "number": pr_number,
            "title": pr_data.get("title", ""),
            "body": pr_data.get("body") or "",
            "author": pr_data.get("user", {}).get("login", "unknown"),
            "diff": diff_resp.text,
            "files_changed": pr_data.get("changed_files", 0),
            "additions": pr_data.get("additions", 0),
            "deletions": pr_data.get("deletions", 0),
            "state": pr_data.get("state", ""),
            "merged": pr_data.get("merged", False),
            "created_at": pr_data.get("created_at", ""),
            "updated_at": pr_data.get("updated_at", ""),
        }
        
        return pr_info, None
        
    except requests.exceptions.Timeout:
        return None, "GitHub API timeout"
    except requests.exceptions.RequestException as e:
        return None, f"GitHub API error: {str(e)}"
    except Exception as e:
        return None, f"Unexpected error: {str(e)}"


def replay_pr_evaluation(pr_number, repo=None, store=False):
    """
    Replay a single PR through current AI review + security scan.
    
    Returns: (result dict, error) or (None, error_message)
    """
    try:
        # Import here to avoid circular imports
        from admin_blueprint import call_ai_review
        from pr_security import ai_security_scan_pr
        
        # Fetch PR from GitHub
        pr_info, fetch_error = fetch_pr_from_github(pr_number, repo)
        if fetch_error:
            return None, fetch_error
        
        # Run AI review
        review_result = call_ai_review(pr_info)
        
        # Run security scan
        check_repo = repo or REPO
        scan_passed, scan_report, scan_ran = ai_security_scan_pr(pr_number, repo=check_repo)
        
        security_result = {
            "passed": scan_passed,
            "report": scan_report,
            "scan_ran": scan_ran,
        }
        
        # Store evaluations if requested
        stored_files = []
        if store:
            try:
                from eval_logger import save_evaluation
                
                # Store review
                if not review_result.get("error"):
                    review_text = review_result.get("review", "")
                    filepath, save_error = save_evaluation(
                        "pr_review_public",
                        review_text,
                        {
                            "pr_number": pr_number,
                            "author": pr_info.get("author"),
                            "title": pr_info.get("title"),
                            "replay": True,
                            "replayed_at": datetime.now(timezone.utc).isoformat(),
                        }
                    )
                    if filepath:
                        stored_files.append(filepath)
                
                # Store security scan
                if scan_ran:
                    filepath, save_error = save_evaluation(
                        "security_audit",
                        scan_report,
                        {
                            "pr_number": pr_number,
                            "repo": check_repo,
                            "replay": True,
                            "replayed_at": datetime.now(timezone.utc).isoformat(),
                        }
                    )
                    if filepath:
                        stored_files.append(filepath)
                        
            except ImportError as e:
                print(f"[EVAL-REPLAY] Storage failed (import error): {e}", flush=True)
            except Exception as e:
                print(f"[EVAL-REPLAY] Storage failed: {e}", flush=True)
        
        # Build result
        result = {
            "pr_number": pr_number,
            "pr_info": {
                "title": pr_info.get("title"),
                "author": pr_info.get("author"),
                "state": pr_info.get("state"),
                "merged": pr_info.get("merged"),
            },
            "review": review_result,
            "security": security_result,
            "stored": store and len(stored_files) > 0,
            "stored_files": stored_files if store else None,
        }
        
        return result, None
        
    except ImportError as e:
        return None, f"Import error: {str(e)} - check module dependencies"
    except Exception as e:
        return None, f"Replay error: {str(e)}"


@eval_replay_bp.route('/admin/api/eval/replay', methods=['POST'])
def replay_single():
    """
    Replay a single PR through current AI evaluation.
    
    POST /admin/api/eval/replay
    {
        "admin_key": "...",
        "pr_number": 164,
        "repo": "WattCoin-Org/wattcoin",  // optional
        "store": true
    }
    """
    try:
        data = request.get_json() or {}
        
        # Auth check
        is_admin, auth_error = check_admin_auth(data)
        if not is_admin:
            return jsonify({"error": auth_error}), 403
        
        # Validate input
        pr_number = data.get("pr_number")
        if not pr_number:
            return jsonify({"error": "pr_number required"}), 400
        
        try:
            pr_number = int(pr_number)
        except (ValueError, TypeError):
            return jsonify({"error": "pr_number must be an integer"}), 400
        
        repo = data.get("repo")
        store = data.get("store", False)
        
        # Run replay
        print(f"[EVAL-REPLAY] Replaying PR #{pr_number}...", flush=True)
        result, error = replay_pr_evaluation(pr_number, repo=repo, store=store)
        
        if error:
            return jsonify({"error": error, "pr_number": pr_number}), 400
        
        return jsonify(result), 200
        
    except Exception as e:
        return jsonify({"error": f"Server error: {str(e)}"}), 500


@eval_replay_bp.route('/admin/api/eval/replay-batch', methods=['POST'])
def replay_batch():
    """
    Replay multiple PRs through current AI evaluation.
    
    POST /admin/api/eval/replay-batch
    {
        "admin_key": "...",
        "pr_numbers": [130, 131, 150, 164],
        "repo": "WattCoin-Org/wattcoin",  // optional
        "store": true
    }
    """
    try:
        data = request.get_json() or {}
        
        # Auth check
        is_admin, auth_error = check_admin_auth(data)
        if not is_admin:
            return jsonify({"error": auth_error}), 403
        
        # Validate input
        pr_numbers = data.get("pr_numbers", [])
        if not pr_numbers or not isinstance(pr_numbers, list):
            return jsonify({"error": "pr_numbers must be a non-empty list"}), 400
        
        # Cap at 10 PRs
        if len(pr_numbers) > 10:
            return jsonify({"error": "Maximum 10 PRs per batch"}), 400
        
        repo = data.get("repo")
        store = data.get("store", False)
        
        # Process batch
        results = []
        succeeded = 0
        failed = 0
        
        print(f"[EVAL-REPLAY] Batch replay: {len(pr_numbers)} PRs", flush=True)
        
        for idx, pr_number in enumerate(pr_numbers):
            try:
                pr_number = int(pr_number)
            except (ValueError, TypeError):
                results.append({
                    "pr_number": pr_number,
                    "status": "error",
                    "error": "Invalid PR number",
                })
                failed += 1
                continue
            
            # Rate limit: 5 second pause between PRs (except first)
            if idx > 0:
                time.sleep(5)
            
            print(f"[EVAL-REPLAY] Processing PR #{pr_number} ({idx+1}/{len(pr_numbers)})...", flush=True)
            
            # Wrap in try/except to isolate per-PR failures
            try:
                result, error = replay_pr_evaluation(pr_number, repo=repo, store=store)
                
                if error:
                    results.append({
                        "pr_number": pr_number,
                        "status": "error",
                        "error": error,
                    })
                    failed += 1
                else:
                    # Extract summary for batch response
                    review_score = None
                    review_passed = None
                    if result.get("review") and not result["review"].get("error"):
                        review_score = result["review"].get("score")
                        review_passed = result["review"].get("passed")
                    
                    security_verdict = "UNKNOWN"
                    if result.get("security"):
                        if result["security"].get("passed"):
                            security_verdict = "PASS"
                        elif result["security"].get("scan_ran"):
                            security_verdict = "FAIL"
                        else:
                            security_verdict = "UNAVAILABLE"
                    
                    results.append({
                        "pr_number": pr_number,
                        "status": "ok",
                        "review_score": review_score,
                        "review_passed": review_passed,
                        "security_verdict": security_verdict,
                        "stored": result.get("stored", False),
                    })
                    succeeded += 1
                    
            except Exception as e:
                # Catch any unhandled exceptions from replay_pr_evaluation
                print(f"[EVAL-REPLAY] Unhandled exception for PR #{pr_number}: {e}", flush=True)
                results.append({
                    "pr_number": pr_number,
                    "status": "error",
                    "error": f"Unexpected error: {str(e)}",
                })
                failed += 1
        
        print(f"[EVAL-REPLAY] Batch complete: {succeeded} ok, {failed} failed", flush=True)
        
        return jsonify({
            "total": len(pr_numbers),
            "succeeded": succeeded,
            "failed": failed,
            "results": results,
        }), 200
        
    except Exception as e:
        return jsonify({"error": f"Server error: {str(e)}"}), 500


@eval_replay_bp.route('/admin/api/eval/annotate', methods=['POST'])
def annotate_evaluation():
    """
    Store manual evaluation corrections.
    
    POST /admin/api/eval/annotate
    {
        "admin_key": "...",
        "pr_number": 130,
        "corrected_score": 3,
        "corrected_verdict": "FAIL",
        "reason": "Bounty farming — reviewer missed duplicate code patterns"
    }
    """
    try:
        data = request.get_json() or {}
        
        # Auth check
        is_admin, auth_error = check_admin_auth(data)
        if not is_admin:
            return jsonify({"error": auth_error}), 403
        
        # Validate required fields
        pr_number = data.get("pr_number")
        corrected_score = data.get("corrected_score")
        reason = data.get("reason")
        
        if pr_number is None:
            return jsonify({"error": "pr_number required"}), 400
        if corrected_score is None:
            return jsonify({"error": "corrected_score required"}), 400
        if not reason:
            return jsonify({"error": "reason required"}), 400
        
        try:
            pr_number = int(pr_number)
            corrected_score = int(corrected_score)
        except (ValueError, TypeError):
            return jsonify({"error": "pr_number and corrected_score must be integers"}), 400
        
        # Build annotation record
        annotation = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "pr_number": pr_number,
            "corrected_score": corrected_score,
            "corrected_verdict": data.get("corrected_verdict"),
            "reason": reason,
            "annotated_by": "admin",
            "original_review": data.get("original_review"),  # Optional: copy of original AI review
        }
        
        # Save to annotations directory
        eval_log_dir = os.getenv("EVAL_LOG_DIR", "data/eval_log")
        annotations_dir = os.path.join(eval_log_dir, "annotations")
        os.makedirs(annotations_dir, exist_ok=True)
        
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        filename = f"{timestamp}_pr{pr_number}_annotation.json"
        filepath = os.path.join(annotations_dir, filename)
        
        with open(filepath, 'w') as f:
            json.dump(annotation, f, indent=2)
        
        print(f"[EVAL-REPLAY] Annotation saved: PR #{pr_number} → {filepath}", flush=True)
        
        return jsonify({
            "status": "saved",
            "pr_number": pr_number,
            "file": f"annotations/{filename}",
            "filepath": filepath,
        }), 200
        
    except Exception as e:
        return jsonify({"error": f"Server error: {str(e)}"}), 500

