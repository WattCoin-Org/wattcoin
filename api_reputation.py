"""
WattCoin Reputation API - Contributor reputation and leaderboard
GET /api/v1/reputation - List all contributors
GET /api/v1/reputation/<github_username> - Single contributor
"""

import os
import json
from flask import Blueprint, jsonify

reputation_bp = Blueprint('reputation', __name__)

# Config
REPUTATION_FILE = "/app/data/reputation.json"

# =============================================================================
# DATA STORAGE
# =============================================================================

def load_reputation():
    """Load reputation data from JSON file."""
    try:
        with open(REPUTATION_FILE, 'r') as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {"contributors": {}, "tiers": {}, "stats": {}}

def save_reputation(data):
    """Save reputation data to JSON file."""
    try:
        os.makedirs(os.path.dirname(REPUTATION_FILE), exist_ok=True)
        with open(REPUTATION_FILE, 'w') as f:
            json.dump(data, f, indent=2)
        return True
    except Exception as e:
        print(f"Error saving reputation: {e}")
        return False

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

def update_contributor_tier(contributor):
    """Update a contributor's tier based on current stats."""
    contributor["tier"] = get_tier(
        contributor.get("bounties_completed", 0),
        contributor.get("total_watt_earned", 0)
    )
    return contributor

# =============================================================================
# ENDPOINTS
# =============================================================================

@reputation_bp.route('/api/v1/reputation', methods=['GET'])
def list_reputation():
    """List all contributors and their reputation."""
    data = load_reputation()
    contributors = data.get("contributors", {})
    
    # Build list sorted by total_watt_earned (descending)
    contributor_list = []
    for username, info in contributors.items():
        # Ensure tier is up to date
        info = update_contributor_tier(info)
        contributor_list.append(info)
    
    contributor_list.sort(key=lambda x: x.get("total_watt_earned", 0), reverse=True)
    
    return jsonify({
        "success": True,
        "total": len(contributor_list),
        "contributors": contributor_list,
        "stats": data.get("stats", {}),
        "tiers": {
            "gold": {"emoji": "🥇", "min_bounties": 5, "min_watt": 250000},
            "silver": {"emoji": "🥈", "min_bounties": 3, "min_watt": 100000},
            "bronze": {"emoji": "🥉", "min_bounties": 1, "min_watt": 0}
        }
    })

@reputation_bp.route('/api/v1/reputation/<github_username>', methods=['GET'])
def get_contributor(github_username):
    """Get single contributor's reputation."""
    data = load_reputation()
    contributors = data.get("contributors", {})
    
    # Case-insensitive lookup
    contributor = None
    for username, info in contributors.items():
        if username.lower() == github_username.lower():
            contributor = update_contributor_tier(info)
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
    data = load_reputation()
    contributors = data.get("contributors", {})
    
    # Calculate live stats
    total_contributors = len(contributors)
    total_bounties = sum(c.get("bounties_completed", 0) for c in contributors.values())
    total_watt = sum(c.get("total_watt_earned", 0) for c in contributors.values())
    
    # Count by tier
    tier_counts = {"gold": 0, "silver": 0, "bronze": 0, "none": 0}
    for c in contributors.values():
        tier = get_tier(c.get("bounties_completed", 0), c.get("total_watt_earned", 0))
        tier_counts[tier] = tier_counts.get(tier, 0) + 1
    
    return jsonify({
        "success": True,
        "stats": {
            "total_contributors": total_contributors,
            "total_bounties_paid": total_bounties,
            "total_watt_distributed": total_watt,
            "tier_breakdown": tier_counts
        }
    })
