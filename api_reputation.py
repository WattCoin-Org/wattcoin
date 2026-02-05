"""
WattCoin Reputation API - Contributor reputation and leaderboard
GET /api/v1/reputation - List all contributors
GET /api/v1/reputation/<github_username> - Single contributor

v2.0.0: Now pulls from actual dashboard bounty payouts instead of static seed data
"""

import os
import json
from flask import Blueprint, jsonify
from datetime import datetime

reputation_bp = Blueprint('reputation', __name__)

# Config - use actual dashboard data
BOUNTY_DATA_FILE = "/app/data/bounty_reviews.json"
HISTORICAL_CONTRIBUTORS_FILE = "/app/data/reputation_historical.json"

# Historical contributors (paid before dashboard system)
HISTORICAL_DATA = {
    "aybanda": {
        "github": "aybanda",
        "wallet": None,
        "bounties_completed": 1,
        "total_watt_earned": 100000,
        "first_contribution": "2026-01-31",
        "bounties": [
            {
                "pr_number": 6,
                "title": "Add /api/v1/scrape endpoint",
                "amount": 100000,
                "completed_at": "2026-01-31",
                "tx_signature": None
            }
        ],
        "tier": "silver"
    },
    "njg7194": {
        "github": "njg7194",
        "wallet": "3bLMHWe3jNKMuKiTu1LK5a7MPBE7WN5qDwKx2s7thEkr",
        "bounties_completed": 2,
        "total_watt_earned": 70000,
        "first_contribution": "2026-02-02",
        "bounties": [
            {
                "pr_number": 4,
                "title": "Improve CONTRIBUTING.md with examples",
                "amount": 20000,
                "completed_at": "2026-02-02",
                "tx_signature": "3pYqoFejGx1fL3muvtYUUg2VJ79DFrfyWs92wqydFKeSSzFqrZM72dLVdVVfdZ6vvmY4q5zSN1a2PwXKKwz3UjMT"
            },
            {
                "pr_number": 5,
                "title": "Add unit tests for tip_transfer.py",
                "amount": 50000,
                "completed_at": "2026-02-02",
                "tx_signature": "2ZeejLNFLvpbE3gazwTsASmBWXutqvzYtceBX1np1N8hHruhxnnjzRLokEm1vpQareLmPtrUHhF4KZSq9L1jpuqa"
            }
        ],
        "tier": "bronze"
    }
}

# =============================================================================
# DATA LOADING
# =============================================================================

def load_bounty_data():
    """Load actual bounty payout data from dashboard."""
    try:
        with open(BOUNTY_DATA_FILE, 'r') as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {"reviews": {}, "payouts": [], "history": []}

def build_contributor_stats():
    """Build contributor reputation from historical data + actual paid bounties."""
    # Start with historical contributors
    contributors = {}
    for username, data in HISTORICAL_DATA.items():
        contributors[username] = dict(data)  # Copy historical data
    
    # Load and merge dashboard data
    data = load_bounty_data()
    payouts = data.get("payouts", [])
    
    # Only count paid bounties
    paid_bounties = [p for p in payouts if p.get("status") == "paid"]
    
    # Merge dashboard payouts with historical data
    for payout in paid_bounties:
        author = payout.get("author")
        if not author:
            continue
        
        if author not in contributors:
            # New contributor (not in historical data)
            contributors[author] = {
                "github": author,
                "wallet": payout.get("wallet"),
                "bounties_completed": 0,
                "total_watt_earned": 0,
                "first_contribution": payout.get("paid_at"),
                "bounties": [],
                "tier": "none"
            }
        
        # Add bounty to contributor
        contributors[author]["bounties_completed"] += 1
        contributors[author]["total_watt_earned"] += payout.get("amount", 0)
        contributors[author]["bounties"].append({
            "pr_number": payout.get("pr_number"),
            "amount": payout.get("amount", 0),
            "completed_at": payout.get("paid_at"),
            "tx_signature": payout.get("tx_sig")
        })
        
        # Update wallet if we didn't have it
        if not contributors[author].get("wallet") and payout.get("wallet"):
            contributors[author]["wallet"] = payout.get("wallet")
        
        # Update first contribution if earlier
        if payout.get("paid_at"):
            if not contributors[author]["first_contribution"] or \
               payout.get("paid_at") < contributors[author]["first_contribution"]:
                contributors[author]["first_contribution"] = payout.get("paid_at")
    
    # Calculate tiers for each contributor
    for contributor in contributors.values():
        contributor["tier"] = get_tier(
            contributor["bounties_completed"],
            contributor["total_watt_earned"]
        )
    
    # Calculate overall stats (including historical)
    total_bounties = sum(c["bounties_completed"] for c in contributors.values())
    total_watt = sum(c["total_watt_earned"] for c in contributors.values())
    
    stats = {
        "total_contributors": len(contributors),
        "total_bounties_paid": total_bounties,
        "total_watt_distributed": total_watt,
        "last_updated": datetime.now().isoformat() + "Z"
    }
    
    return contributors, stats

# =============================================================================
# TIER LOGIC
# =============================================================================

def get_tier(bounties_completed, total_watt):
    """Calculate contributor tier based on activity."""
    if bounties_completed >= 5 and total_watt >= 250000:
        return "gold"
    elif bounties_completed >= 3 or total_watt >= 100000:
        return "silver"
    elif bounties_completed >= 1:
        return "bronze"
    return "none"

# =============================================================================
# ENDPOINTS
# =============================================================================

@reputation_bp.route('/api/v1/reputation', methods=['GET'])
def list_reputation():
    """List all contributors and their reputation."""
    contributors, stats = build_contributor_stats()
    
    # Build list sorted by total_watt_earned (descending)
    contributor_list = list(contributors.values())
    contributor_list.sort(key=lambda x: x.get("total_watt_earned", 0), reverse=True)
    
    return jsonify({
        "success": True,
        "total": len(contributor_list),
        "contributors": contributor_list,
        "stats": stats,
        "tiers": {
            "gold": {"emoji": "🥇", "min_bounties": 5, "min_watt": 250000},
            "silver": {"emoji": "🥈", "min_bounties": 3, "min_watt": 100000},
            "bronze": {"emoji": "🥉", "min_bounties": 1, "min_watt": 0}
        }
    })

@reputation_bp.route('/api/v1/reputation/<github_username>', methods=['GET'])
def get_contributor(github_username):
    """Get single contributor's reputation."""
    contributors, _ = build_contributor_stats()
    
    # Case-insensitive lookup
    contributor = None
    for username, info in contributors.items():
        if username.lower() == github_username.lower():
            contributor = info
            break
    
    if not contributor:
        return jsonify({
            "success": False,
            "error": "contributor_not_found",
            "message": f"No reputation data for {github_username}"
        }), 404
    
    return jsonify({
        "success": True,
        "contributor": contributor
    })

@reputation_bp.route('/api/v1/reputation/stats', methods=['GET'])
def get_stats():
    """Get overall reputation system stats."""
    _, stats = build_contributor_stats()
    
    return jsonify({
        "success": True,
        "stats": stats
    })
