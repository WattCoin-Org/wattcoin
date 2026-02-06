"""
WattNode API - Node registration, job routing, payouts
v2.3.0 - Added /api/v1/stats endpoint
"""

from flask import Blueprint, request, jsonify
import os
import json
import time
import uuid
import requests
import base58
from datetime import datetime, timezone
from api_error_codes import E

nodes_bp = Blueprint('nodes', __name__)

# Track uptime
START_TIME = time.time()

# === Config ===
NODES_FILE = os.environ.get('NODES_FILE', '/app/data/nodes.json')
JOBS_FILE = os.environ.get('JOBS_FILE', '/app/data/node_jobs.json')
WATT_MINT = "Gpmbh4PoQnL1kNgpMYDED3iv4fczcr7d3qNBLf8rpump"
BOUNTY_WALLET = "7vvNkG3JF3JpxLEavqZSkc5T3n9hHR98Uw23fbWdXVSF"
TREASURY_WALLET = os.environ.get('TREASURY_WALLET', 'Atu5phbGGGFogbKhi259czz887dSdTfXwJxwbuE5aF5q')
TREASURY_WALLET_PRIVATE_KEY = os.environ.get('TREASURY_WALLET_PRIVATE_KEY', '')
SOLANA_RPC = "https://solana.publicnode.com"

STAKE_AMOUNT = 10000  # 10,000 WATT required
HEARTBEAT_TIMEOUT = 120  # seconds - node inactive if no heartbeat
JOB_TIMEOUT = 30  # seconds - job expires if not completed

# Payment split (out of 100)
NODE_SHARE = 70
TREASURY_SHARE = 20
BURN_SHARE = 10

# === Storage Helpers ===
def load_nodes():
    if os.path.exists(NODES_FILE):
        with open(NODES_FILE, 'r') as f:
            return json.load(f)
    return {"nodes": {}}

def save_nodes(data):
    os.makedirs(os.path.dirname(NODES_FILE), exist_ok=True)
    with open(NODES_FILE, 'w') as f:
        json.dump(data, f, indent=2)

def load_jobs():
    if os.path.exists(JOBS_FILE):
        with open(JOBS_FILE, 'r') as f:
            return json.load(f)
    return {"jobs": {}, "pending": [], "completed": []}

def save_jobs(data):
    os.makedirs(os.path.dirname(JOBS_FILE), exist_ok=True)
    with open(JOBS_FILE, 'w') as f:
        json.dump(data, f, indent=2)

# === Stake Verification ===
def verify_stake(wallet: str, tx_signature: str) -> dict:
    """Verify WATT stake transaction to treasury wallet"""
    try:
        # Get transaction details
        resp = requests.post(SOLANA_RPC, json={
            "jsonrpc": "2.0",
            "id": 1,
            "method": "getTransaction",
            "params": [tx_signature, {"encoding": "jsonParsed", "maxSupportedTransactionVersion": 0}]
        }, timeout=15)
        
        data = resp.json()
        if "error" in data or not data.get("result"):
            return {"valid": False, "error": "Transaction not found"}
        
        tx = data["result"]
        
        # Check age (must be within last 24 hours for registration)
        block_time = tx.get("blockTime", 0)
        if time.time() - block_time > 86400:
            return {"valid": False, "error": "Transaction too old (>24h)"}
        
        # Check pre/post token balances for WATT transfer
        meta = tx.get("meta", {})
        pre_balances = meta.get("preTokenBalances", [])
        post_balances = meta.get("postTokenBalances", [])
        
        # Find treasury wallet balance change
        treasury_pre = 0
        treasury_post = 0
        sender_wallet = None
        
        for bal in pre_balances:
            if bal.get("mint") == WATT_MINT:
                owner = bal.get("owner", "")
                if owner == TREASURY_WALLET:
                    treasury_pre = int(bal.get("uiTokenAmount", {}).get("amount", 0))
                elif owner == wallet:
                    sender_wallet = owner
        
        for bal in post_balances:
            if bal.get("mint") == WATT_MINT:
                owner = bal.get("owner", "")
                if owner == TREASURY_WALLET:
                    treasury_post = int(bal.get("uiTokenAmount", {}).get("amount", 0))
        
        amount_received = (treasury_post - treasury_pre) / 1_000_000  # 6 decimals
        
        if amount_received < STAKE_AMOUNT:
            return {"valid": False, "error": f"Insufficient stake: {amount_received} < {STAKE_AMOUNT}"}
        
        return {"valid": True, "amount": amount_received}
        
    except Exception as e:
        return {"valid": False, "error": str(e)}

# === Node Payout ===
def send_node_payout(to_wallet: str, amount: int) -> tuple:
    """
    Send WATT tokens from treasury wallet to node.
    Returns: (success, tx_signature or error_message)
    """
    if not TREASURY_WALLET_PRIVATE_KEY:
        return False, "TREASURY_WALLET_PRIVATE_KEY not configured"
    
    try:
        from solders.keypair import Keypair
        from solders.pubkey import Pubkey
        from solders.instruction import Instruction, AccountMeta
        from solders.transaction import Transaction
        from solders.message import Message
        from solders.hash import Hash
        import struct
        
        # Token-2022 program ID (WATT uses Token-2022)
        TOKEN_2022_PROGRAM_ID = Pubkey.from_string("TokenzQdBNbLqP5VEhdkAS6EPFLC1PHnBqCXEpPxuEb")
        
        # Load treasury wallet from private key
        key_bytes = base58.b58decode(TREASURY_WALLET_PRIVATE_KEY)
        wallet = Keypair.from_bytes(key_bytes)
        
        mint = Pubkey.from_string(WATT_MINT)
        from_pubkey = wallet.pubkey()
        to_pubkey = Pubkey.from_string(to_wallet)
        
        # Get ATAs via RPC
        def get_ata_for_owner(owner_str):
            resp = requests.post(SOLANA_RPC, json={
                "jsonrpc": "2.0",
                "id": 1,
                "method": "getTokenAccountsByOwner",
                "params": [owner_str, {"mint": WATT_MINT}, {"encoding": "jsonParsed"}]
            }, timeout=15)
            data = resp.json()
            accounts = data.get("result", {}).get("value", [])
            if accounts:
                return Pubkey.from_string(accounts[0]["pubkey"])
            return None
        
        from_ata = get_ata_for_owner(str(from_pubkey))
        to_ata = get_ata_for_owner(to_wallet)
        
        if not from_ata:
            return False, "Treasury wallet has no WATT token account"
        if not to_ata:
            return False, f"Node wallet {to_wallet[:8]}... has no WATT token account"
        
        # Build transfer instruction (opcode 3 for SPL token transfer)
        amount_raw = amount * (10 ** 6)  # 6 decimals
        instruction_data = struct.pack('<BQ', 3, amount_raw)
        
        # Account metas for transfer: [source, dest, owner]
        accounts = [
            AccountMeta(from_ata, is_signer=False, is_writable=True),
            AccountMeta(to_ata, is_signer=False, is_writable=True),
            AccountMeta(from_pubkey, is_signer=True, is_writable=False),
        ]
        
        transfer_ix = Instruction(TOKEN_2022_PROGRAM_ID, instruction_data, accounts)
        
        # Get recent blockhash
        rpc_resp = requests.post(SOLANA_RPC, json={
            "jsonrpc": "2.0",
            "id": 1,
            "method": "getLatestBlockhash",
            "params": [{"commitment": "finalized"}]
        }, timeout=15)
        blockhash_data = rpc_resp.json()
        blockhash = Hash.from_string(blockhash_data["result"]["value"]["blockhash"])
        
        # Build and sign transaction
        msg = Message.new_with_blockhash([transfer_ix], from_pubkey, blockhash)
        tx = Transaction.new_unsigned(msg)
        tx.sign([wallet], blockhash)
        
        # Serialize and send
        tx_bytes = bytes(tx)
        tx_base64 = base58.b58encode(tx_bytes).decode('utf-8')
        
        send_resp = requests.post(SOLANA_RPC, json={
            "jsonrpc": "2.0",
            "id": 1,
            "method": "sendTransaction",
            "params": [tx_base64, {"encoding": "base58", "skipPreflight": False}]
        }, timeout=30)
        
        send_result = send_resp.json()
        
        if "result" in send_result:
            return True, send_result["result"]
        elif "error" in send_result:
            return False, f"RPC error: {send_result['error'].get('message', str(send_result['error']))}"
        else:
            return False, "Unknown RPC response"
            
    except ImportError as e:
        return False, f"Solana libraries not installed: {e}"
    except Exception as e:
        return False, f"Payout error: {e}"

# === Node Helpers ===
def generate_node_id():
    return f"node_{uuid.uuid4().hex[:12]}"

def is_node_active(node: dict) -> bool:
    """Check if node has recent heartbeat"""
    last_hb = node.get("last_heartbeat")
    if not last_hb:
        return False
    try:
        hb_time = datetime.fromisoformat(last_hb.replace('Z', '+00:00'))
        age = (datetime.now(timezone.utc) - hb_time).total_seconds()
        return age < HEARTBEAT_TIMEOUT
    except:
        return False

def get_active_nodes(capability: str = None) -> list:
    """Get list of active nodes, optionally filtered by capability"""
    data = load_nodes()
    active = []
    for node_id, node in data.get("nodes", {}).items():
        if node.get("status") != "active":
            continue
        if not is_node_active(node):
            continue
        if capability and capability not in node.get("capabilities", []):
            continue
        active.append({"node_id": node_id, **node})
    return active

# === API Endpoints ===

@nodes_bp.route('/api/v1/nodes/register', methods=['POST'])
def register_node():
    """Register a new WattNode"""
    body = request.get_json() or {}
    
    wallet = body.get('wallet')
    capabilities = body.get('capabilities', [])
    stake_tx = body.get('stake_tx')
    endpoint = body.get('endpoint')  # null for polling mode
    name = body.get('name', 'unnamed-node')
    
    # Validation
    if not wallet:
        return jsonify({"success": False, "error": "wallet required", "error_code": E.MISSING_WALLET}), 400
    if not stake_tx:
        return jsonify({"success": False, "error": "stake_tx required", "error_code": E.MISSING_TX_SIGNATURE}), 400
    if not capabilities:
        return jsonify({"success": False, "error": "capabilities required (scrape, inference)", "error_code": E.MISSING_FIELD}), 400
    
    valid_caps = ['scrape', 'inference']
    for cap in capabilities:
        if cap not in valid_caps:
            return jsonify({"success": False, "error": f"invalid capability: {cap}", "error_code": E.CAPABILITY_INVALID}), 400
    
    # Check if already registered
    data = load_nodes()
    for node_id, node in data.get("nodes", {}).items():
        if node.get("wallet") == wallet:
            return jsonify({
                "success": False, 
                "error": "wallet already registered",
                "node_id": node_id
            }), 409
        if node.get("stake_tx") == stake_tx:
            return jsonify({"success": False, "error": "stake_tx already used", "error_code": E.STAKE_ALREADY_USED}), 409
    
    # Verify stake
    stake_result = verify_stake(wallet, stake_tx)
    if not stake_result.get("valid"):
        return jsonify({
            "success": False, 
            "error": f"stake verification failed: {stake_result.get('error')}"
        }), 400
    
    # Register node
    node_id = generate_node_id()
    now = datetime.now(timezone.utc).isoformat()
    
    data["nodes"][node_id] = {
        "wallet": wallet,
        "name": name,
        "capabilities": capabilities,
        "endpoint": endpoint,
        "stake_amount": stake_result.get("amount", STAKE_AMOUNT),
        "stake_tx": stake_tx,
        "registered_at": now,
        "last_heartbeat": now,
        "jobs_completed": 0,
        "jobs_failed": 0,
        "total_earned": 0,
        "status": "active"
    }
    
    save_nodes(data)
    
    return jsonify({
        "success": True,
        "node_id": node_id,
        "status": "active",
        "stake_verified": True,
        "stake_amount": stake_result.get("amount"),
        "message": f"Node registered! You will receive {NODE_SHARE}% of job payments."
    })

@nodes_bp.route('/api/v1/nodes/heartbeat', methods=['POST'])
def node_heartbeat():
    """Keep node alive"""
    body = request.get_json() or {}
    node_id = body.get('node_id')
    
    if not node_id:
        return jsonify({"success": False, "error": "node_id required", "error_code": E.MISSING_FIELD}), 400
    
    data = load_nodes()
    if node_id not in data.get("nodes", {}):
        return jsonify({"success": False, "error": "node not found", "error_code": E.NODE_NOT_FOUND}), 404
    
    data["nodes"][node_id]["last_heartbeat"] = datetime.now(timezone.utc).isoformat()
    # Allow name update via heartbeat
    new_name = body.get('name')
    if new_name and isinstance(new_name, str) and len(new_name) <= 64:
        data["nodes"][node_id]["name"] = new_name.strip()
    save_nodes(data)
    
    return jsonify({
        "success": True,
        "node_id": node_id,
        "status": data["nodes"][node_id]["status"]
    })

@nodes_bp.route('/api/v1/nodes/jobs', methods=['GET'])
def get_node_jobs():
    """Poll for available jobs (for polling mode nodes)"""
    node_id = request.args.get('node_id')
    
    if not node_id:
        return jsonify({"success": False, "error": "node_id required", "error_code": E.MISSING_FIELD}), 400
    
    # Verify node exists and is active
    nodes_data = load_nodes()
    node = nodes_data.get("nodes", {}).get(node_id)
    if not node:
        return jsonify({"success": False, "error": "node not found", "error_code": E.NODE_NOT_FOUND}), 404
    if node.get("status") != "active":
        return jsonify({"success": False, "error": "node not active", "error_code": E.NODE_INACTIVE}), 403
    
    # Get pending jobs for this node's capabilities
    jobs_data = load_jobs()
    available = []
    now = datetime.now(timezone.utc)
    
    for job_id in list(jobs_data.get("pending", [])):
        job = jobs_data.get("jobs", {}).get(job_id)
        if not job:
            continue
        
        # Check if job type matches node capability
        if job.get("type") not in node.get("capabilities", []):
            continue
        
        # Check if job expired
        expires = datetime.fromisoformat(job.get("expires_at", "").replace('Z', '+00:00'))
        if now > expires:
            # Move to failed
            jobs_data["pending"].remove(job_id)
            job["status"] = "expired"
            continue
        
        # Check if already assigned to another node
        if job.get("assigned_to") and job.get("assigned_to") != node_id:
            continue
        
        available.append({
            "job_id": job_id,
            "type": job.get("type"),
            "payload": job.get("payload"),
            "reward": job.get("node_reward"),
            "expires_at": job.get("expires_at")
        })
    
    save_jobs(jobs_data)
    
    # Update heartbeat
    nodes_data["nodes"][node_id]["last_heartbeat"] = now.isoformat()
    save_nodes(nodes_data)
    
    return jsonify({
        "success": True,
        "jobs": available[:5]  # Max 5 jobs at a time
    })

@nodes_bp.route('/api/v1/nodes/jobs/<job_id>/claim', methods=['POST'])
def claim_job(job_id):
    """Node claims a job to work on"""
    body = request.get_json() or {}
    node_id = body.get('node_id')
    
    if not node_id:
        return jsonify({"success": False, "error": "node_id required", "error_code": E.MISSING_FIELD}), 400
    
    jobs_data = load_jobs()
    job = jobs_data.get("jobs", {}).get(job_id)
    
    if not job:
        return jsonify({"success": False, "error": "job not found", "error_code": E.JOB_NOT_FOUND}), 404
    if job.get("status") != "pending":
        return jsonify({"success": False, "error": f"job status: {job.get('status')}", "error_code": E.JOB_ALREADY_CLAIMED}), 409
    if job.get("assigned_to") and job.get("assigned_to") != node_id:
        return jsonify({"success": False, "error": "job assigned to another node", "error_code": E.JOB_WRONG_NODE}), 409
    
    # Assign job
    job["assigned_to"] = node_id
    job["claimed_at"] = datetime.now(timezone.utc).isoformat()
    jobs_data["jobs"][job_id] = job
    save_jobs(jobs_data)
    
    return jsonify({
        "success": True,
        "job_id": job_id,
        "payload": job.get("payload"),
        "reward": job.get("node_reward")
    })

@nodes_bp.route('/api/v1/nodes/jobs/<job_id>/complete', methods=['POST'])
def complete_job(job_id):
    """Node submits completed job result"""
    body = request.get_json() or {}
    node_id = body.get('node_id')
    result = body.get('result')
    
    if not node_id:
        return jsonify({"success": False, "error": "node_id required", "error_code": E.MISSING_FIELD}), 400
    if result is None:
        return jsonify({"success": False, "error": "result required", "error_code": E.MISSING_FIELD}), 400
    
    jobs_data = load_jobs()
    job = jobs_data.get("jobs", {}).get(job_id)
    
    if not job:
        return jsonify({"success": False, "error": "job not found", "error_code": E.JOB_NOT_FOUND}), 404
    if job.get("assigned_to") != node_id:
        return jsonify({"success": False, "error": "job not assigned to this node", "error_code": E.JOB_WRONG_NODE}), 403
    if job.get("status") == "completed":
        return jsonify({"success": False, "error": "job already completed", "error_code": E.JOB_ALREADY_COMPLETED}), 409
    
    # Update job
    now = datetime.now(timezone.utc).isoformat()
    job["status"] = "completed"
    job["completed_at"] = now
    job["result"] = result
    
    # Move from pending to completed
    if job_id in jobs_data.get("pending", []):
        jobs_data["pending"].remove(job_id)
    jobs_data["completed"].append(job_id)
    jobs_data["jobs"][job_id] = job
    save_jobs(jobs_data)
    
    # Update node stats
    nodes_data = load_nodes()
    node = nodes_data.get("nodes", {}).get(node_id)
    node_wallet = None
    if node:
        node["jobs_completed"] = node.get("jobs_completed", 0) + 1
        node["total_earned"] = node.get("total_earned", 0) + job.get("node_reward", 0)
        node["last_heartbeat"] = now
        node_wallet = node.get("wallet")
        save_nodes(nodes_data)
    
    # Auto-payout to node wallet
    payout_status = "pending"
    payout_tx = None
    payout_error = None
    
    if node_wallet and job.get("node_reward", 0) > 0:
        success, result_msg = send_node_payout(node_wallet, job.get("node_reward"))
        if success:
            payout_status = "paid"
            payout_tx = result_msg
            # Update job with payout info
            jobs_data = load_jobs()
            jobs_data["jobs"][job_id]["payout_status"] = "paid"
            jobs_data["jobs"][job_id]["payout_tx"] = payout_tx
            save_jobs(jobs_data)
        else:
            payout_error = result_msg
    
    response = {
        "success": True,
        "job_id": job_id,
        "status": "completed",
        "reward": job.get("node_reward"),
        "payout_status": payout_status
    }
    
    if payout_tx:
        response["payout_tx"] = payout_tx
    if payout_error:
        response["payout_error"] = payout_error
    
    return jsonify(response)

@nodes_bp.route('/api/v1/nodes', methods=['GET'])
def list_nodes():
    """Public: List active nodes"""
    data = load_nodes()
    nodes_list = []
    
    for node_id, node in data.get("nodes", {}).items():
        active = is_node_active(node)
        nodes_list.append({
            "node_id": node_id,
            "name": node.get("name"),
            "capabilities": node.get("capabilities"),
            "status": "active" if active else "inactive",
            "jobs_completed": node.get("jobs_completed", 0),
            "total_earned": node.get("total_earned", 0),
            "registered_at": node.get("registered_at")
        })
    
    # Sort by jobs completed
    nodes_list.sort(key=lambda x: x.get("jobs_completed", 0), reverse=True)
    
    return jsonify({
        "success": True,
        "count": len(nodes_list),
        "active": len([n for n in nodes_list if n["status"] == "active"]),
        "nodes": nodes_list
    })

@nodes_bp.route('/api/v1/nodes/<node_id>', methods=['GET'])
def get_node(node_id):
    """Public: Get node details"""
    data = load_nodes()
    node = data.get("nodes", {}).get(node_id)
    
    if not node:
        return jsonify({"success": False, "error": "node not found", "error_code": E.NODE_NOT_FOUND}), 404
    
    return jsonify({
        "success": True,
        "node_id": node_id,
        "name": node.get("name"),
        "capabilities": node.get("capabilities"),
        "status": "active" if is_node_active(node) else "inactive",
        "jobs_completed": node.get("jobs_completed", 0),
        "jobs_failed": node.get("jobs_failed", 0),
        "total_earned": node.get("total_earned", 0),
        "registered_at": node.get("registered_at"),
        "stake_amount": node.get("stake_amount")
    })

@nodes_bp.route('/api/v1/stats', methods=['GET'])
def get_network_stats():
    """Public: Get network-wide statistics for display on /nodes page"""
    nodes_data = load_nodes()
    jobs_data = load_jobs()
    
    nodes = nodes_data.get("nodes", {})
    jobs = jobs_data.get("jobs", {})
    
    # Node stats
    total_nodes = len(nodes)
    active_nodes = sum(1 for n in nodes.values() if is_node_active(n))
    
    # Aggregate from nodes
    total_jobs_from_nodes = sum(n.get("jobs_completed", 0) for n in nodes.values())
    total_watt_earned = sum(n.get("total_earned", 0) for n in nodes.values())
    
    # Jobs stats (as backup/verification)
    completed_jobs = len(jobs_data.get("completed", []))
    paid_jobs = sum(1 for j in jobs.values() if j.get("payout_status") == "paid")
    
    # Try to load task submissions for additional payout stats
    task_payouts = 0
    try:
        submissions_file = "/app/data/task_submissions.json"
        if os.path.exists(submissions_file):
            with open(submissions_file, 'r') as f:
                submissions_data = json.load(f)
                for sub in submissions_data.get("submissions", []):
                    if sub.get("status") == "approved" and sub.get("payout_tx"):
                        task_payouts += sub.get("reward", 0)
    except:
        pass
    
    # Total WATT distributed (nodes + tasks)
    total_watt_paid = total_watt_earned + task_payouts
    
    return jsonify({
        "success": True,
        "nodes": {
            "total_registered": total_nodes,
            "active": active_nodes,
            "inactive": total_nodes - active_nodes
        },
        "jobs": {
            "total_completed": total_jobs_from_nodes,
            "total_paid": paid_jobs
        },
        "payouts": {
            "nodes_watt": total_watt_earned,
            "tasks_watt": task_payouts,
            "total_watt": total_watt_paid
        },
        "updated_at": datetime.now(timezone.utc).isoformat()
    })

@nodes_bp.route('/health', methods=['GET'])
def health_check():
    """Health check endpoint for WattNode API monitoring"""
    jobs_data = load_jobs()
    active_jobs = len([j for j in jobs_data.get("jobs", {}).values() if j.get("status") == "pending"])

    return jsonify({
        "status": "ok",
        "uptime_seconds": int(time.time() - START_TIME),
        "active_jobs": active_jobs,
        "version": "3.0.0"
    })

# === Job Creation Helper (called by scraper/inference endpoints) ===
def create_job(job_type: str, payload: dict, total_payment: int, requester_wallet: str) -> dict:
    """
    Create a job for node routing.
    Returns job_id if nodes available, None if should fallback to centralized.
    """
    # Check for active nodes with this capability
    active = get_active_nodes(capability=job_type)
    if not active:
        return {"routed": False, "reason": "no_active_nodes"}
    
    # Calculate splits
    node_reward = int(total_payment * NODE_SHARE / 100)
    treasury_amount = int(total_payment * TREASURY_SHARE / 100)
    burn_amount = int(total_payment * BURN_SHARE / 100)
    
    # Create job
    job_id = f"job_{uuid.uuid4().hex[:12]}"
    now = datetime.now(timezone.utc)
    expires = now.replace(second=now.second + JOB_TIMEOUT)
    
    job = {
        "job_id": job_id,
        "type": job_type,
        "payload": payload,
        "total_payment": total_payment,
        "node_reward": node_reward,
        "treasury_amount": treasury_amount,
        "burn_amount": burn_amount,
        "requester_wallet": requester_wallet,
        "status": "pending",
        "assigned_to": None,
        "created_at": now.isoformat(),
        "expires_at": expires.isoformat(),
        "result": None
    }
    
    jobs_data = load_jobs()
    jobs_data["jobs"][job_id] = job
    jobs_data["pending"].append(job_id)
    save_jobs(jobs_data)
    
    return {
        "routed": True,
        "job_id": job_id,
        "node_reward": node_reward,
        "active_nodes": len(active)
    }

def wait_for_job_result(job_id: str, timeout: int = 30) -> dict:
    """Wait for job to be completed by a node"""
    start = time.time()
    while time.time() - start < timeout:
        jobs_data = load_jobs()
        job = jobs_data.get("jobs", {}).get(job_id)
        if job and job.get("status") == "completed":
            return {
                "success": True,
                "result": job.get("result"),
                "node_id": job.get("assigned_to")
            }
        time.sleep(0.5)
    
    # Timeout - job not completed
    return {"success": False, "error": "timeout"}

def cancel_job(job_id: str):
    """Cancel a pending job (used when falling back to centralized)"""
    jobs_data = load_jobs()
    if job_id in jobs_data.get("pending", []):
        jobs_data["pending"].remove(job_id)
    if job_id in jobs_data.get("jobs", {}):
        jobs_data["jobs"][job_id]["status"] = "cancelled"
    save_jobs(jobs_data)


# === TEST ENDPOINT (Admin only) ===
@nodes_bp.route('/api/v1/nodes/test/create-job', methods=['POST'])
def test_create_job():
    """
    Admin endpoint to create a test job for debugging.
    Requires ADMIN_PASSWORD header.
    """
    admin_pass = os.environ.get('ADMIN_PASSWORD', '')
    auth_header = request.headers.get('Authorization', '')
    
    if not admin_pass or auth_header != f'Bearer {admin_pass}':
        return jsonify({"success": False, "error": "unauthorized", "error_code": E.UNAUTHORIZED}), 401
    
    body = request.get_json() or {}
    job_type = body.get('type', 'scrape')
    url = body.get('url', 'https://example.com')
    payment = body.get('payment', 100)
    
    result = create_job(
        job_type=job_type,
        payload={'url': url, 'format': 'text'},
        total_payment=payment,
        requester_wallet='test_admin'
    )
    
    return jsonify({
        "success": True,
        "job": result
    })
