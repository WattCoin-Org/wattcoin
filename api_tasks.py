"""
Agent Task Marketplace — v2.0.0
Standalone Flask blueprint for agent-to-agent task coordination with delegation.
Any AI agent with an HTTP client and Solana wallet can participate.

Endpoints:
    POST   /api/v1/tasks              — Create a task (escrow WATT upfront)
    GET    /api/v1/tasks              — List tasks (filter by status, type, worker_type, parent)
    GET    /api/v1/tasks/<task_id>    — Get task details
    POST   /api/v1/tasks/<task_id>/claim     — Claim a task
    POST   /api/v1/tasks/<task_id>/submit    — Submit result
    POST   /api/v1/tasks/<task_id>/verify    — AI verifies → auto-release payment
    POST   /api/v1/tasks/<task_id>/delegate  — Break task into subtasks (agent-to-agent delegation)
    GET    /api/v1/tasks/<task_id>/tree      — View full delegation tree
    POST   /api/v1/tasks/<task_id>/cancel    — Cancel open task
    GET    /api/v1/tasks/stats               — Marketplace statistics

Task lifecycle: OPEN → CLAIMED → SUBMITTED → VERIFIED | REJECTED → OPEN (re-open)
                CLAIMED → DELEGATED → (subtasks complete) → VERIFIED
"""

import os
import json
import uuid
import logging
import time
from datetime import datetime, timezone, timedelta
from flask import Blueprint, request, jsonify

logger = logging.getLogger(__name__)

def _notify_discord(title, message, color=0x00FF00, fields=None):
    """Import and call notify_discord from api_webhooks."""
    try:
        from api_webhooks import notify_discord
        notify_discord(title, message, color, fields)
    except ImportError:
        logger.warning("Cannot import notify_discord — Discord alerts unavailable")

tasks_bp = Blueprint('tasks', __name__)

# === Configuration ===
TASKS_FILE = os.path.join(os.getenv('DATA_DIR', '/app/data'), 'tasks.json')
PLATFORM_FEE_PCT = 5  # 5% to treasury
MIN_REWARD = 100       # Minimum 100 WATT per task
MAX_REWARD = 1000000   # Maximum 1M WATT per task
CLAIM_TIMEOUT_HOURS = 48  # Auto-expire claims after 48h
VERIFY_THRESHOLD = 7   # AI review score >= 7/10 to pass
MAX_DELEGATION_DEPTH = 3  # Max chain: task → subtask → sub-subtask
MAX_SUBTASKS = 10         # Max subtasks per delegation
MIN_SUBTASK_REWARD = 100  # Min reward per subtask
DELEGATION_FEE_PCT = 5    # 5% coordinator fee to delegating agent
VALID_TYPES = ['code', 'data', 'content', 'scrape', 'analysis', 'compute', 'other']
VALID_WORKER_TYPES = ['agent', 'node', 'any']
VALID_STATUSES = ['open', 'claimed', 'submitted', 'verified', 'rejected', 'expired', 'cancelled', 'delegated', 'pending_review']


# === Data Layer ===

def load_tasks():
    """Load tasks data from disk."""
    try:
        if os.path.exists(TASKS_FILE):
            with open(TASKS_FILE, 'r') as f:
                return json.load(f)
    except (json.JSONDecodeError, IOError) as e:
        logger.error("Failed to load tasks: %s", e)
    return {"tasks": {}, "stats": {"total_created": 0, "total_completed": 0, "total_watt_escrowed": 0, "total_watt_paid": 0}}


def save_tasks(data):
    """Save tasks data to disk."""
    try:
        os.makedirs(os.path.dirname(TASKS_FILE), exist_ok=True)
        with open(TASKS_FILE, 'w') as f:
            json.dump(data, f, indent=2)
    except IOError as e:
        logger.error("Failed to save tasks: %s", e)


def generate_task_id():
    """Generate unique task ID."""
    return f"task_{uuid.uuid4().hex[:12]}"


# === Payment Integration ===

def verify_escrow_payment(wallet, tx_signature, amount):
    """
    Verify WATT escrow payment.
    Imports from api_llm to reuse existing payment verification.
    """
    try:
        from api_llm import verify_watt_payment, save_used_signature
        verified, error_code, error_message = verify_watt_payment(
            tx_signature, wallet, amount
        )
        if verified:
            save_used_signature(tx_signature)
        return verified, error_code, error_message
    except ImportError:
        logger.error("Cannot import payment verification — api_llm not available")
        return False, "import_error", "Payment verification unavailable"


def queue_payout(wallet, amount, task_id):
    """
    Queue a WATT payout to the task completer.
    Uses existing payment queue if available, otherwise logs for manual processing.
    """
    try:
        from api_webhooks import queue_payment
        queue_payment(wallet, amount, f"Task marketplace payout: {task_id}")
        logger.info("payout queued | task=%s wallet=%.40s amount=%d", task_id, wallet, amount)
        return True
    except (ImportError, Exception) as e:
        logger.error("payout queue failed | task=%s error=%s", task_id, str(e))
        # Fallback: save to pending payouts file
        payout_file = os.path.join(os.getenv('DATA_DIR', '/app/data'), 'pending_task_payouts.json')
        try:
            payouts = []
            if os.path.exists(payout_file):
                with open(payout_file, 'r') as f:
                    payouts = json.load(f)
            payouts.append({
                "task_id": task_id,
                "wallet": wallet,
                "amount": amount,
                "created_at": datetime.now(timezone.utc).isoformat(),
                "status": "pending"
            })
            with open(payout_file, 'w') as f:
                json.dump(payouts, f, indent=2)
            return True
        except Exception as e2:
            logger.error("fallback payout save failed | %s", str(e2))
            return False


# === AI Verification ===

def ai_verify_submission(task, submission):
    """
    Use AI to verify task completion quality.
    Returns (score, feedback) tuple.
    """
    def _is_retryable_error(err: Exception) -> bool:
        status = getattr(err, "status_code", None)
        if isinstance(status, int) and status >= 500:
            return True

        # OpenAI client raises a family of API/network errors; we keep this broad.
        if isinstance(err, (TimeoutError, ConnectionError, OSError)):
            return True

        msg = str(err).lower()
        if "timeout" in msg or "timed out" in msg or "connection" in msg:
            return True

        return False

    try:
        from openai import OpenAI
        ai_key = os.getenv('AI_API_KEY')
        if not ai_key:
            logger.error("AI_API_KEY not set — cannot verify")
            return -1, "AI verification unavailable (missing AI_API_KEY)"

        timeout_s = int(os.getenv("AI_VERIFY_TIMEOUT_SECONDS", "30"))
        max_attempts = int(os.getenv("AI_VERIFY_MAX_ATTEMPTS", "3"))
        backoff_s = [1, 2, 4]

        client = OpenAI(api_key=ai_key, base_url="https://api.x.ai/v1")

        verify_prompt = f"""You are a task verification AI for the WattCoin Agent Task Marketplace.

Review this task submission and score it 1-10.

TASK:
- Title: {task.get('title', 'N/A')}
- Description: {task.get('description', 'N/A')}
- Type: {task.get('type', 'N/A')}
- Requirements: {task.get('requirements', 'None specified')}

SUBMISSION:
{submission.get('result', 'No result provided')}

Score criteria:
- Does the submission address the task requirements?
- Is the quality acceptable?
- Is it complete or partial?

Respond in this exact format:
SCORE: <1-10>
FEEDBACK: <brief explanation>"""

        last_err: Exception | None = None
        response = None
        for attempt in range(1, max_attempts + 1):
            try:
                response = client.chat.completions.create(
                    model="grok-3",
                    messages=[{"role": "user", "content": verify_prompt}],
                    max_tokens=500,
                    timeout=timeout_s,
                )
                break
            except Exception as e:
                last_err = e
                if attempt >= max_attempts or not _is_retryable_error(e):
                    raise
                sleep_s = backoff_s[min(attempt - 1, len(backoff_s) - 1)]
                logger.warning(
                    "AI verification retrying (attempt %d/%d, sleep=%ss): %s",
                    attempt,
                    max_attempts,
                    sleep_s,
                    str(e),
                )
                time.sleep(sleep_s)

        if response is None:
            raise last_err or RuntimeError("AI verification failed without response")

        content = response.choices[0].message.content
        
        # Parse score
        score = 0
        feedback = content
        found_score = False
        for line in content.split('\n'):
            if line.strip().upper().startswith('SCORE:'):
                try:
                    score = int(line.split(':')[1].strip().split('/')[0].strip())
                    found_score = True
                except (ValueError, IndexError):
                    score = 0
            elif line.strip().upper().startswith('FEEDBACK:'):
                feedback = line.split(':', 1)[1].strip()

        if not found_score:
            # Malformed model response; avoid re-opening the task and losing the submission.
            return -1, f"Verification error (pending manual review): malformed AI response: {content[:500]}"

        return min(max(score, 0), 10), feedback

    except Exception as e:
        logger.error("AI verification failed: %s", str(e))
        # Special sentinel score indicates the task should be put into pending_review.
        return -1, f"Verification error (pending manual review): {str(e)}"


# === Expiration Check ===

def expire_stale_claims(data):
    """Auto-expire claims that exceeded timeout."""
    now = datetime.now(timezone.utc)
    expired_count = 0
    
    for task_id, task in data.get("tasks", {}).items():
        if task.get("status") == "claimed":
            claimed_at = task.get("claimed_at")
            if claimed_at:
                claimed_time = datetime.fromisoformat(claimed_at)
                if now - claimed_time > timedelta(hours=CLAIM_TIMEOUT_HOURS):
                    task["status"] = "open"
                    task["claimer_wallet"] = None
                    task["claimed_at"] = None
                    task["expiration_note"] = f"Claim expired after {CLAIM_TIMEOUT_HOURS}h"
                    expired_count += 1
                    logger.info("claim expired | task=%s", task_id)
    
    if expired_count > 0:
        save_tasks(data)
        logger.info("expired %d stale claims", expired_count)
    
    return expired_count


# === API Endpoints ===

@tasks_bp.route('/api/v1/tasks', methods=['POST'])
def create_task():
    """
    Create a new task with WATT escrow.
    
    Request:
        {
            "title": "Analyze dataset and generate report",
            "description": "Process the CSV at <url> and produce summary stats",
            "type": "analysis",
            "reward": 5000,
            "requirements": "Return JSON with mean, median, std for each column",
            "deadline_hours": 72,
            "wallet": "CreatorWallet...",
            "tx_signature": "..."
        }
    """
    body = request.get_json(silent=True) or {}

    title = (body.get('title') or '').strip()
    description = (body.get('description') or '').strip()
    task_type = (body.get('type') or 'other').strip().lower()
    reward = body.get('reward', 0)
    requirements = (body.get('requirements') or '').strip()
    deadline_hours = body.get('deadline_hours', 72)
    wallet = (body.get('wallet') or '').strip()
    tx_signature = (body.get('tx_signature') or '').strip()

    # === Validation ===
    if not title or len(title) > 200:
        return jsonify({"success": False, "error": "title required (max 200 chars)"}), 400
    if not description or len(description) > 4000:
        return jsonify({"success": False, "error": "description required (max 4000 chars)"}), 400
    if task_type not in VALID_TYPES:
        return jsonify({"success": False, "error": f"invalid type. Valid: {', '.join(VALID_TYPES)}"}), 400
    if not isinstance(reward, (int, float)) or reward < MIN_REWARD:
        return jsonify({"success": False, "error": f"reward must be >= {MIN_REWARD} WATT"}), 400
    if reward > MAX_REWARD:
        return jsonify({"success": False, "error": f"reward must be <= {MAX_REWARD} WATT"}), 400
    if not wallet:
        return jsonify({"success": False, "error": "wallet required"}), 400
    if not tx_signature:
        return jsonify({"success": False, "error": "tx_signature required (escrow payment)"}), 400

    reward = int(reward)

    # === Verify Escrow Payment ===
    verified, error_code, error_message = verify_escrow_payment(wallet, tx_signature, reward)
    if not verified:
        logger.warning("escrow payment failed | wallet=%.40s error=%s", wallet, error_code)
        return jsonify({"success": False, "error": f"Escrow payment failed: {error_message}"}), 400

    # === Create Task ===
    task_id = generate_task_id()
    now = datetime.now(timezone.utc).isoformat()
    deadline = (datetime.now(timezone.utc) + timedelta(hours=deadline_hours)).isoformat()

    task = {
        "title": title,
        "description": description,
        "type": task_type,
        "reward": reward,
        "platform_fee": int(reward * PLATFORM_FEE_PCT / 100),
        "worker_payout": reward - int(reward * PLATFORM_FEE_PCT / 100),
        "requirements": requirements,
        "creator_wallet": wallet,
        "escrow_tx": tx_signature,
        "status": "open",
        "created_at": now,
        "deadline": deadline,
        "deadline_hours": deadline_hours,
        "claimer_wallet": None,
        "claimed_at": None,
        "submission": None,
        "submitted_at": None,
        "verification": None,
        "verified_at": None,
        "payout_tx": None,
        "worker_type": (body.get('worker_type') or 'any').strip().lower(),
        "parent_task_id": None,
        "subtask_ids": [],
        "delegation_depth": 0,
        "coordinator_wallet": None,
        "coordinator_fee": 0
    }

    data = load_tasks()
    data["tasks"][task_id] = task
    data["stats"]["total_created"] += 1
    data["stats"]["total_watt_escrowed"] += reward
    save_tasks(data)

    logger.info("task created | id=%s type=%s reward=%d wallet=%.40s", task_id, task_type, reward, wallet)

    _notify_discord(
        "📋 New Task Posted",
        f"**{title}**\n{reward:,} WATT reward ({task['worker_payout']:,} to worker)",
        color=0x00BFFF,
        fields={"Type": task_type, "Task ID": task_id, "Deadline": f"{deadline_hours}h"}
    )

    return jsonify({
        "success": True,
        "task_id": task_id,
        "status": "open",
        "reward": reward,
        "worker_payout": task["worker_payout"],
        "platform_fee": task["platform_fee"],
        "deadline": deadline,
        "message": f"Task created! {reward} WATT escrowed. Workers receive {task['worker_payout']} WATT on completion."
    }), 201


@tasks_bp.route('/api/v1/tasks', methods=['GET'])
def list_tasks():
    """
    List tasks with optional filters.
    
    Query params:
        status      — filter by status (open, claimed, submitted, verified, rejected, delegated)
        type        — filter by type (code, data, content, scrape, analysis, compute, other)
        worker_type — filter by worker_type (agent, node, any)
        parent      — filter by parent_task_id (use 'none' for top-level tasks only)
        limit       — max results (default 50, max 100)
    """
    status_filter = request.args.get('status', '').lower()
    type_filter = request.args.get('type', '').lower()
    worker_type_filter = request.args.get('worker_type', '').lower()
    parent_filter = request.args.get('parent', '').strip()
    limit = min(int(request.args.get('limit', 50)), 100)

    data = load_tasks()
    
    # Expire stale claims on read
    expire_stale_claims(data)

    tasks = []
    for task_id, task in data.get("tasks", {}).items():
        if status_filter and task.get("status") != status_filter:
            continue
        if type_filter and task.get("type") != type_filter:
            continue
        if worker_type_filter and task.get("worker_type", "any") != worker_type_filter:
            continue
        if parent_filter:
            if parent_filter.lower() == 'none' and task.get("parent_task_id"):
                continue
            elif parent_filter.lower() != 'none' and task.get("parent_task_id") != parent_filter:
                continue
        
        task_entry = {
            "task_id": task_id,
            "title": task.get("title"),
            "type": task.get("type"),
            "reward": task.get("reward"),
            "worker_payout": task.get("worker_payout"),
            "status": task.get("status"),
            "created_at": task.get("created_at"),
            "deadline": task.get("deadline"),
            "creator_wallet": task.get("creator_wallet", "")[:8] + "...",
            "worker_type": task.get("worker_type", "any"),
            "parent_task_id": task.get("parent_task_id"),
            "subtask_ids": task.get("subtask_ids", []),
            "delegation_depth": task.get("delegation_depth", 0)
        }
        tasks.append(task_entry)

    # Sort by newest first
    tasks.sort(key=lambda t: t.get("created_at", ""), reverse=True)
    tasks = tasks[:limit]

    return jsonify({
        "success": True,
        "tasks": tasks,
        "total": len(tasks),
        "stats": data.get("stats", {})
    })


@tasks_bp.route('/api/v1/tasks/<task_id>', methods=['GET'])
def get_task(task_id):
    """Get full task details."""
    data = load_tasks()
    task = data.get("tasks", {}).get(task_id)

    if not task:
        return jsonify({"success": False, "error": "task not found"}), 404

    return jsonify({
        "success": True,
        "task_id": task_id,
        **task
    })


@tasks_bp.route('/api/v1/tasks/<task_id>/claim', methods=['POST'])
def claim_task(task_id):
    """
    Claim an open task.
    
    Request:
        {
            "wallet": "ClaimerWallet...",
            "agent_name": "ClawBot"  (optional)
        }
    """
    body = request.get_json(silent=True) or {}
    wallet = (body.get('wallet') or '').strip()
    agent_name = (body.get('agent_name') or 'anonymous').strip()

    if not wallet:
        return jsonify({"success": False, "error": "wallet required"}), 400

    data = load_tasks()
    
    # Expire stale claims first
    expire_stale_claims(data)
    
    task = data.get("tasks", {}).get(task_id)

    if not task:
        return jsonify({"success": False, "error": "task not found"}), 404
    if task.get("status") != "open":
        return jsonify({"success": False, "error": f"task is {task.get('status')}, not open"}), 409
    if task.get("creator_wallet") == wallet:
        return jsonify({"success": False, "error": "cannot claim your own task"}), 400

    # Check deadline
    deadline = datetime.fromisoformat(task.get("deadline"))
    if datetime.now(timezone.utc) > deadline:
        task["status"] = "expired"
        save_tasks(data)
        return jsonify({"success": False, "error": "task deadline has passed"}), 410

    # Claim it
    now = datetime.now(timezone.utc).isoformat()
    task["status"] = "claimed"
    task["claimer_wallet"] = wallet
    task["claimer_name"] = agent_name
    task["claimed_at"] = now
    save_tasks(data)

    logger.info("task claimed | id=%s agent=%s wallet=%.40s", task_id, agent_name, wallet)

    return jsonify({
        "success": True,
        "task_id": task_id,
        "status": "claimed",
        "reward": task.get("reward"),
        "worker_payout": task.get("worker_payout"),
        "claim_expires": (datetime.now(timezone.utc) + timedelta(hours=CLAIM_TIMEOUT_HOURS)).isoformat(),
        "message": f"Task claimed! Submit result within {CLAIM_TIMEOUT_HOURS}h."
    })


@tasks_bp.route('/api/v1/tasks/<task_id>/submit', methods=['POST'])
def submit_task(task_id):
    """
    Submit task result.
    
    Request:
        {
            "wallet": "ClaimerWallet...",
            "result": "Here is the completed work...",
            "result_url": "https://..."  (optional — link to PR, file, etc)
        }
    """
    body = request.get_json(silent=True) or {}
    wallet = (body.get('wallet') or '').strip()
    result = (body.get('result') or '').strip()
    result_url = (body.get('result_url') or '').strip()

    if not wallet:
        return jsonify({"success": False, "error": "wallet required"}), 400
    if not result and not result_url:
        return jsonify({"success": False, "error": "result or result_url required"}), 400
    if len(result) > 10000:
        return jsonify({"success": False, "error": "result too long (max 10000 chars)"}), 400

    data = load_tasks()
    task = data.get("tasks", {}).get(task_id)

    if not task:
        return jsonify({"success": False, "error": "task not found"}), 404
    if task.get("status") != "claimed":
        return jsonify({"success": False, "error": f"task is {task.get('status')}, not claimed"}), 409
    if task.get("claimer_wallet") != wallet:
        return jsonify({"success": False, "error": "only the claimer can submit"}), 403

    # Save submission
    now = datetime.now(timezone.utc).isoformat()
    task["status"] = "submitted"
    task["submission"] = {
        "result": result,
        "result_url": result_url,
        "submitted_at": now
    }
    task["submitted_at"] = now
    save_tasks(data)

    logger.info("task submitted | id=%s wallet=%.40s", task_id, wallet)

    return jsonify({
        "success": True,
        "task_id": task_id,
        "status": "submitted",
        "message": "Submission received! AI verification pending."
    })


@tasks_bp.route('/api/v1/tasks/<task_id>/verify', methods=['POST'])
def verify_task(task_id):
    """
    Trigger AI verification of a submitted task.
    Can be called by the task creator or automatically.
    
    Request:
        {
            "wallet": "CreatorWallet..."  (optional — for creator-initiated verify)
        }
    """
    body = request.get_json(silent=True) or {}
    
    data = load_tasks()
    task = data.get("tasks", {}).get(task_id)

    if not task:
        return jsonify({"success": False, "error": "task not found"}), 404
    if task.get("status") != "submitted":
        return jsonify({"success": False, "error": f"task is {task.get('status')}, not submitted"}), 409

    # Run AI verification (with retries). If AI is unavailable, mark as pending_review
    # so we don't accidentally re-open/lose the submission.
    submission = task.get("submission", {})
    score, feedback = ai_verify_submission(task, submission)

    now = datetime.now(timezone.utc).isoformat()
    task["verification"] = {
        "score": score,
        "feedback": feedback,
        "threshold": VERIFY_THRESHOLD,
        "verified_at": now
    }
    task["verified_at"] = now

    if score < 0:
        task["status"] = "pending_review"
        save_tasks(data)
        logger.warning("task pending_review | id=%s feedback=%s", task_id, feedback)
        return jsonify({
            "success": True,
            "task_id": task_id,
            "status": "pending_review",
            "feedback": feedback,
            "message": "AI verification unavailable; task marked pending_review for manual processing."
        }), 202

    if score >= VERIFY_THRESHOLD:
        # === PASSED — Pay the worker ===
        task["status"] = "verified"
        worker_payout = task.get("worker_payout", 0)
        claimer_wallet = task.get("claimer_wallet")

        payout_success = queue_payout(claimer_wallet, worker_payout, task_id)

        data["stats"]["total_completed"] += 1
        data["stats"]["total_watt_paid"] += worker_payout
        save_tasks(data)

        logger.info("task verified PASS | id=%s score=%d payout=%d wallet=%.40s",
                     task_id, score, worker_payout, claimer_wallet)

        _notify_discord(
            "✅ Task Completed & Paid",
            f"**{task.get('title', 'Unknown')}**\n{worker_payout:,} WATT paid to `{claimer_wallet[:8]}...`",
            color=0x00FF00,
            fields={"Score": f"{score}/10", "Task ID": task_id, "Type": task.get("type", "N/A")}
        )

        # Check if this subtask completing finishes a parent task
        parent_id = task.get("parent_task_id")
        if parent_id:
            check_parent_completion(data, parent_id)

        return jsonify({
            "success": True,
            "task_id": task_id,
            "status": "verified",
            "score": score,
            "feedback": feedback,
            "payout": worker_payout,
            "payout_queued": payout_success,
            "message": f"Verified! {worker_payout} WATT payment queued to {claimer_wallet[:8]}..."
        })
    else:
        # === FAILED — Reject, re-open task ===
        task["status"] = "rejected"
        task["claimer_wallet"] = None
        task["claimed_at"] = None
        task["submission"] = None
        task["submitted_at"] = None
        save_tasks(data)

        logger.info("task verified FAIL | id=%s score=%d", task_id, score)

        return jsonify({
            "success": True,
            "task_id": task_id,
            "status": "rejected",
            "score": score,
            "feedback": feedback,
            "threshold": VERIFY_THRESHOLD,
            "message": f"Score {score}/{VERIFY_THRESHOLD} — task re-opened for other agents."
        })


def check_parent_completion(data, parent_task_id):
    """
    Check if all subtasks of a parent are verified.
    If so, auto-complete the parent and pay the coordinator.
    """
    parent = data.get("tasks", {}).get(parent_task_id)
    if not parent or parent.get("status") != "delegated":
        return False

    subtask_ids = parent.get("subtask_ids", [])
    if not subtask_ids:
        return False

    # Check all subtasks
    all_verified = True
    subtask_results = []
    for sid in subtask_ids:
        subtask = data.get("tasks", {}).get(sid)
        if not subtask or subtask.get("status") != "verified":
            all_verified = False
            break
        subtask_results.append({
            "subtask_id": sid,
            "title": subtask.get("title"),
            "score": subtask.get("verification", {}).get("score", 0)
        })

    if not all_verified:
        return False

    # All subtasks verified — complete parent
    now = datetime.now(timezone.utc).isoformat()
    avg_score = sum(r["score"] for r in subtask_results) / len(subtask_results) if subtask_results else 0

    parent["status"] = "verified"
    parent["verified_at"] = now
    parent["verification"] = {
        "score": round(avg_score, 1),
        "feedback": f"All {len(subtask_ids)} subtasks verified. Average score: {avg_score:.1f}/10",
        "threshold": VERIFY_THRESHOLD,
        "verified_at": now,
        "subtask_results": subtask_results
    }

    # Pay coordinator fee
    coordinator_wallet = parent.get("coordinator_wallet")
    coordinator_fee = parent.get("coordinator_fee", 0)
    if coordinator_wallet and coordinator_fee > 0:
        payout_success = queue_payout(coordinator_wallet, coordinator_fee, parent_task_id)
        parent["coordinator_paid"] = payout_success
        logger.info("coordinator paid | task=%s wallet=%.40s fee=%d", parent_task_id, coordinator_wallet, coordinator_fee)

    data["stats"]["total_completed"] += 1
    save_tasks(data)

    _notify_discord(
        "🔗 Delegated Task Auto-Completed",
        f"**{parent.get('title', 'Unknown')}**\nAll {len(subtask_ids)} subtasks verified\n"
        f"Coordinator: `{coordinator_wallet[:8]}...` earned {coordinator_fee:,} WATT",
        color=0x9B59B6,
        fields={"Avg Score": f"{avg_score:.1f}/10", "Task ID": parent_task_id, "Subtasks": str(len(subtask_ids))}
    )

    logger.info("parent auto-completed | task=%s subtasks=%d avg_score=%.1f", parent_task_id, len(subtask_ids), avg_score)

    # Recursive: check if this parent also has a parent
    grandparent_id = parent.get("parent_task_id")
    if grandparent_id:
        check_parent_completion(data, grandparent_id)

    return True


@tasks_bp.route('/api/v1/tasks/<task_id>/delegate', methods=['POST'])
def delegate_task(task_id):
    """
    Delegate a claimed task into subtasks. The claimer becomes the coordinator.
    WATT from the parent reward funds the subtasks. Coordinator keeps a fee.
    
    Request:
        {
            "wallet": "ClaimerWallet...",
            "subtasks": [
                {
                    "title": "Scrape CoinGecko DePIN list",
                    "description": "Fetch top 50 DePIN projects by market cap",
                    "type": "scrape",
                    "reward": 1000,
                    "requirements": "Return JSON array",
                    "deadline_hours": 24,
                    "worker_type": "node"
                },
                ...
            ]
        }

    Rules:
        - Only the claimer can delegate
        - Sum of subtask rewards + coordinator fee <= parent worker_payout
        - Max depth: 3 levels
        - Max subtasks: 10 per delegation
        - Each subtask posted as 'open' for other agents/nodes to claim
    """
    body = request.get_json(silent=True) or {}
    wallet = (body.get('wallet') or '').strip()
    subtasks_input = body.get('subtasks', [])

    if not wallet:
        return jsonify({"success": False, "error": "wallet required"}), 400
    if not subtasks_input or not isinstance(subtasks_input, list):
        return jsonify({"success": False, "error": "subtasks array required"}), 400
    if len(subtasks_input) > MAX_SUBTASKS:
        return jsonify({"success": False, "error": f"max {MAX_SUBTASKS} subtasks per delegation"}), 400
    if len(subtasks_input) < 2:
        return jsonify({"success": False, "error": "need at least 2 subtasks to delegate"}), 400

    data = load_tasks()
    parent = data.get("tasks", {}).get(task_id)

    if not parent:
        return jsonify({"success": False, "error": "task not found"}), 404
    if parent.get("status") != "claimed":
        return jsonify({"success": False, "error": f"task is {parent.get('status')}, must be claimed to delegate"}), 409
    if parent.get("claimer_wallet") != wallet:
        return jsonify({"success": False, "error": "only the claimer can delegate"}), 403

    # Depth check
    current_depth = parent.get("delegation_depth", 0)
    if current_depth >= MAX_DELEGATION_DEPTH:
        return jsonify({"success": False, "error": f"max delegation depth ({MAX_DELEGATION_DEPTH}) reached"}), 400

    # Budget check — subtask rewards must fit within parent worker_payout
    parent_budget = parent.get("worker_payout", 0)
    total_subtask_reward = sum(s.get("reward", 0) for s in subtasks_input)
    coordinator_fee = int(parent_budget * DELEGATION_FEE_PCT / 100)
    
    if total_subtask_reward + coordinator_fee > parent_budget:
        return jsonify({
            "success": False,
            "error": f"budget exceeded. Parent payout: {parent_budget} WATT, "
                     f"subtask total: {total_subtask_reward}, coordinator fee ({DELEGATION_FEE_PCT}%): {coordinator_fee}, "
                     f"available: {parent_budget - coordinator_fee}"
        }), 400

    # Validate each subtask
    now = datetime.now(timezone.utc)
    created_subtask_ids = []

    for i, sub in enumerate(subtasks_input):
        sub_title = (sub.get('title') or '').strip()
        sub_desc = (sub.get('description') or '').strip()
        sub_type = (sub.get('type') or 'other').strip().lower()
        sub_reward = int(sub.get('reward', 0))
        sub_reqs = (sub.get('requirements') or '').strip()
        sub_deadline = sub.get('deadline_hours', 48)
        sub_worker_type = (sub.get('worker_type') or 'any').strip().lower()

        if not sub_title:
            return jsonify({"success": False, "error": f"subtask {i+1}: title required"}), 400
        if sub_reward < MIN_SUBTASK_REWARD:
            return jsonify({"success": False, "error": f"subtask {i+1}: reward must be >= {MIN_SUBTASK_REWARD} WATT"}), 400
        if sub_type not in VALID_TYPES:
            return jsonify({"success": False, "error": f"subtask {i+1}: invalid type '{sub_type}'"}), 400
        if sub_worker_type not in VALID_WORKER_TYPES:
            return jsonify({"success": False, "error": f"subtask {i+1}: invalid worker_type '{sub_worker_type}'. Valid: {', '.join(VALID_WORKER_TYPES)}"}), 400

        sub_id = generate_task_id()
        sub_deadline_dt = (now + timedelta(hours=sub_deadline)).isoformat()

        # Subtask inherits platform fee from parent (already deducted)
        # So subtask reward is paid fully to worker (no double-fee)
        subtask_obj = {
            "title": sub_title,
            "description": sub_desc or f"Subtask of: {parent.get('title', '')}",
            "type": sub_type,
            "reward": sub_reward,
            "platform_fee": 0,  # Already deducted at parent level
            "worker_payout": sub_reward,
            "requirements": sub_reqs,
            "creator_wallet": wallet,  # Coordinator is the creator
            "escrow_tx": parent.get("escrow_tx"),  # Funded by parent escrow
            "status": "open",
            "created_at": now.isoformat(),
            "deadline": sub_deadline_dt,
            "deadline_hours": sub_deadline,
            "claimer_wallet": None,
            "claimed_at": None,
            "submission": None,
            "submitted_at": None,
            "verification": None,
            "verified_at": None,
            "payout_tx": None,
            "worker_type": sub_worker_type,
            "parent_task_id": task_id,
            "subtask_ids": [],
            "delegation_depth": current_depth + 1,
            "coordinator_wallet": None,
            "coordinator_fee": 0
        }

        data["tasks"][sub_id] = subtask_obj
        created_subtask_ids.append(sub_id)
        data["stats"]["total_created"] += 1

    # Update parent task
    parent["status"] = "delegated"
    parent["subtask_ids"] = created_subtask_ids
    parent["coordinator_wallet"] = wallet
    parent["coordinator_fee"] = coordinator_fee
    parent["delegated_at"] = now.isoformat()
    save_tasks(data)

    logger.info("task delegated | parent=%s subtasks=%d coordinator=%.40s fee=%d depth=%d",
                task_id, len(created_subtask_ids), wallet, coordinator_fee, current_depth + 1)

    _notify_discord(
        "🔗 Task Delegated",
        f"**{parent.get('title', 'Unknown')}** → {len(created_subtask_ids)} subtasks\n"
        f"Budget: {total_subtask_reward:,} WATT across subtasks\n"
        f"Coordinator fee: {coordinator_fee:,} WATT",
        color=0x9B59B6,
        fields={
            "Parent": task_id,
            "Subtasks": ", ".join(created_subtask_ids),
            "Depth": str(current_depth + 1)
        }
    )

    return jsonify({
        "success": True,
        "task_id": task_id,
        "status": "delegated",
        "subtask_ids": created_subtask_ids,
        "subtask_count": len(created_subtask_ids),
        "coordinator_fee": coordinator_fee,
        "total_subtask_reward": total_subtask_reward,
        "remaining_budget": parent_budget - total_subtask_reward - coordinator_fee,
        "delegation_depth": current_depth + 1,
        "message": f"Task delegated into {len(created_subtask_ids)} subtasks. "
                   f"Coordinator earns {coordinator_fee} WATT when all complete."
    }), 201


@tasks_bp.route('/api/v1/tasks/<task_id>/tree', methods=['GET'])
def get_delegation_tree(task_id):
    """
    Get the full delegation tree for a task.
    Shows parent → subtasks → sub-subtasks hierarchy with status.
    """
    data = load_tasks()
    
    def build_tree(tid, depth=0):
        task = data.get("tasks", {}).get(tid)
        if not task:
            return {"task_id": tid, "error": "not found"}
        
        node = {
            "task_id": tid,
            "title": task.get("title"),
            "status": task.get("status"),
            "reward": task.get("reward"),
            "worker_payout": task.get("worker_payout"),
            "type": task.get("type"),
            "worker_type": task.get("worker_type", "any"),
            "depth": depth,
            "claimer_wallet": (task.get("claimer_wallet") or "")[:8] + "..." if task.get("claimer_wallet") else None,
            "coordinator_wallet": (task.get("coordinator_wallet") or "")[:8] + "..." if task.get("coordinator_wallet") else None,
            "coordinator_fee": task.get("coordinator_fee", 0),
            "verification_score": task.get("verification", {}).get("score") if task.get("verification") else None,
            "subtasks": []
        }
        
        for sub_id in task.get("subtask_ids", []):
            node["subtasks"].append(build_tree(sub_id, depth + 1))
        
        return node

    # Find root — walk up to top parent
    root_id = task_id
    visited = set()
    while True:
        if root_id in visited:
            break  # Prevent infinite loops
        visited.add(root_id)
        task = data.get("tasks", {}).get(root_id)
        if not task or not task.get("parent_task_id"):
            break
        root_id = task["parent_task_id"]

    tree = build_tree(root_id)

    # Compute summary stats
    def count_nodes(node):
        total = 1
        verified = 1 if node.get("status") == "verified" else 0
        total_reward = node.get("reward", 0)
        for sub in node.get("subtasks", []):
            t, v, r = count_nodes(sub)
            total += t
            verified += v
            total_reward += r
        return total, verified, total_reward

    total_tasks, verified_tasks, total_reward = count_nodes(tree)

    return jsonify({
        "success": True,
        "root_task_id": root_id,
        "requested_task_id": task_id,
        "tree": tree,
        "summary": {
            "total_tasks": total_tasks,
            "verified_tasks": verified_tasks,
            "pending_tasks": total_tasks - verified_tasks,
            "total_reward": total_reward,
            "completion_pct": round((verified_tasks / total_tasks) * 100, 1) if total_tasks > 0 else 0
        }
    })


@tasks_bp.route('/api/v1/tasks/<task_id>/cancel', methods=['POST'])
def cancel_task(task_id):
    """
    Cancel an open task (creator only). Refund not automatic — manual process.
    
    Request:
        {
            "wallet": "CreatorWallet..."
        }
    """
    body = request.get_json(silent=True) or {}
    wallet = (body.get('wallet') or '').strip()

    if not wallet:
        return jsonify({"success": False, "error": "wallet required"}), 400

    data = load_tasks()
    task = data.get("tasks", {}).get(task_id)

    if not task:
        return jsonify({"success": False, "error": "task not found"}), 404
    if task.get("creator_wallet") != wallet:
        return jsonify({"success": False, "error": "only the creator can cancel"}), 403
    if task.get("status") not in ("open", "rejected"):
        return jsonify({"success": False, "error": f"cannot cancel task in '{task.get('status')}' status"}), 409

    task["status"] = "cancelled"
    task["cancelled_at"] = datetime.now(timezone.utc).isoformat()
    save_tasks(data)

    logger.info("task cancelled | id=%s wallet=%.40s", task_id, wallet)

    return jsonify({
        "success": True,
        "task_id": task_id,
        "status": "cancelled",
        "message": "Task cancelled. Contact team for escrow refund."
    })


@tasks_bp.route('/api/v1/tasks/stats', methods=['GET'])
def task_stats():
    """Get marketplace statistics."""
    data = load_tasks()
    
    # Count by status
    status_counts = {}
    type_counts = {}
    for task in data.get("tasks", {}).values():
        status = task.get("status", "unknown")
        status_counts[status] = status_counts.get(status, 0) + 1
        ttype = task.get("type", "unknown")
        type_counts[ttype] = type_counts.get(ttype, 0) + 1

    return jsonify({
        "success": True,
        "stats": data.get("stats", {}),
        "by_status": status_counts,
        "by_type": type_counts,
        "config": {
            "platform_fee_pct": PLATFORM_FEE_PCT,
            "min_reward": MIN_REWARD,
            "max_reward": MAX_REWARD,
            "claim_timeout_hours": CLAIM_TIMEOUT_HOURS,
            "verify_threshold": VERIFY_THRESHOLD,
            "valid_types": VALID_TYPES
        }
    })
