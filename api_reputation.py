"""
WattCoin Reputation API - Contributor reputation and leaderboard
GET /api/v1/reputation - List all contributors
GET /api/v1/reputation/<github_username> - Single contributor
"""

import os
import json
import shutil
from flask import Blueprint, jsonify

reputation_bp = Blueprint('reputation', __name__)

# Config - check volume first, then repo seed
REPUTATION_FILE = "/app/data/reputation.json"

# Seed data - used when volume file is empty/missing
SEED_DATA = {
    "contributors": {
        "aybanda": {
            "github": "aybanda",
            "wallet": None,
            "bounties_completed": 1,
            "total_watt_earned": 100000,
            "first_contribution": "2026-01-31",
            "bounties": [
                {
                    "issue": 6,
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
                    "issue": 4,
                    "title": "Improve CONTRIBUTING.md with examples",
                    "amount": 20000,
                    "completed_at": "2026-02-02",
                    "tx_signature": "3pYqoFejGx1fL3muvtYUUg2VJ79DFrfyWs92wqydFKeSSzFqrZM72dLVdVVfdZ6vvmY4q5zSN1a2PwXKKwz3UjMT"
                },
                {
                    "issue": 5,
                    "title": "Add unit tests for tip_transfer.py",
                    "amount": 50000,
                    "completed_at": "2026-02-02",
                    "tx_signature": "2ZeejLNFLvpbE3gazwTsASmBWXutqvzYtceBX1np1N8hHruhxnnjzRLokEm1vpQareLmPtrUHhF4KZSq9L1jpuqa"
                }
            ],
            "tier": "bronze"
        }
    },
    "tiers": {
        "bronze": {"min_bounties": 1, "min_watt": 0},
        "silver": {"min_bounties": 3, "min_watt": 100000},
        "gold": {"min_bounties": 5, "min_watt": 250000}
    },
    "stats": {
        "total_contributors": 2,
        "total_bounties_paid": 3,
        "total_watt_distributed": 170000,
        "last_updated": "2026-02-02T05:30:00Z"
    }
}

# =============================================================================
# DATA STORAGE
# =============================================================================

def load_reputation():
    """Load reputation data from JSON file. Falls back to seed data if volume empty."""
    # Try loading from volume first
    try:
        with open(REPUTATION_FILE, 'r') as f:
            data = json.load(f)
            # Check if it has actual data
            if data.get("contributors"):
                return data
    except (FileNotFoundError, json.JSONDecodeError):
        pass
    
    # Use seed data and save to volume for future updates
    try:
        os.makedirs(os.path.dirname(REPUTATION_FILE), exist_ok=True)
        with open(REPUTATION_FILE, 'w') as f:
            json.dump(SEED_DATA, f, indent=2)
    except Exception as e:
        print(f"Could not write seed data: {e}")
    
    return SEED_DATA

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
