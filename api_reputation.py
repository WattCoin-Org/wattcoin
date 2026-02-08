"""
WattCoin Reputation API - Contributor merit system and leaderboard
GET /api/v1/reputation - List all contributors with merit scores
GET /api/v1/reputation/<github_username> - Single contributor details
GET /api/v1/reputation/stats - Overall reputation system stats

v3.0.0: Merit System V1 — tier-gated auto-merge, scoring from merge/reject/revert history
"""

import os
import json
from flask import Blueprint, jsonify
from datetime import datetime

reputation_bp = Blueprint('reputation', __name__)

# Config
REPUTATION_FILE = "/app/data/contributor_reputation.json"

# Historical contributors (paid before automated system, preserved for reference)
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
        ]
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
        ]
    },
    "SudarshanSuryaprakash": {
        "github": "SudarshanSuryaprakash",
        "wallet": "7vvNkG3JF3JpxLEavqZSkc5T3n9hHR98Uw23fbWdXVSF",
        "bounties_completed": 3,
        "total_watt_earned": 225000,
        "first_contribution": "2026-02-04",
        "bounties": [
            {
                "pr_number": 1,
                "title": "WattNode error handling improvements",
                "amount": 75000,
                "completed_at": "2026-02-04",
                "tx_signature": "5xYz..."
            },
            {
                "pr_number": 2,
                "title": "API rate limiting enhancements",
                "amount": 75000,
                "completed_at": "2026-02-04",
                "tx_signature": "4wXy..."
            },
            {
                "pr_number": 3,
                "title": "Dashboard UI improvements",
                "amount": 75000,
                "completed_at": "2026-02-04",
                "tx_signature": "3vWx..."
            }
        ]
    }
}

# =============================================================================
# DATA LOADING
# =============================================================================

# Import canonical load function from webhooks (has auto-seed + cleanup + recalculation)
from api_webhooks import load_reputation_data

def build_contributor_list():
    """Build combined list: merit system contributors + historical data."""
    rep_data = load_reputation_data()
    merit_contributors = rep_data.get("contributors", {})
    
    # System/org accounts excluded from leaderboard
    SYSTEM_ACCOUNTS = {"wattcoin-org"}
    
    # Load banned users for tier override
    from api_webhooks import load_banned_users
    banned_users = load_banned_users()
    
    result = []
    
    # Merit system contributors (primary)
    for username, data in merit_contributors.items():
        if username.lower() in SYSTEM_ACCOUNTS:
            continue
        
        tier = data.get("tier", "new")
        if username.lower() in banned_users:
            tier = "banned"
        
        entry = {
            "github": username,
            "score": data.get("score", 0),
            "tier": tier,
            "merged_prs": data.get("merged_prs", []),
            "rejected_prs": data.get("rejected_prs", []),
            "reverted_prs": data.get("reverted_prs", []),
            "total_watt_earned": data.get("total_watt_earned", 0),
            "last_updated": data.get("last_updated"),
            "source": "merit_system"
        }
        
        # Reference historical data separately (don't add to total_watt_earned — score is merit-only)
        if username in HISTORICAL_DATA:
            hist = HISTORICAL_DATA[username]
            entry["historical_watt"] = hist.get("total_watt_earned", 0)
            entry["historical_bounties"] = hist.get("bounties", [])
        
        result.append(entry)
    
    # Add historical-only contributors (not yet in merit system)
    for username, hist in HISTORICAL_DATA.items():
        if username.lower() not in {k.lower() for k in merit_contributors}:
            result.append({
                "github": username,
                "score": 0,
                "tier": "bronze",  # Historical contributors get bronze by default
                "merged_prs": [b["pr_number"] for b in hist.get("bounties", [])],
                "rejected_prs": [],
                "reverted_prs": [],
                "total_watt_earned": hist.get("total_watt_earned", 0),
                "last_updated": hist.get("first_contribution"),
                "historical_bounties": hist.get("bounties", []),
                "source": "historical"
            })
    
    # Sort by score descending, then by WATT earned
    result.sort(key=lambda x: (x["score"], x["total_watt_earned"]), reverse=True)
    
    return result

# =============================================================================
# TIER INFO
# =============================================================================

TIER_INFO = {
    "gold":    {"emoji": "🥇", "min_score": 90,  "auto_merge_min": 9, "payout_bonus": "+20%"},
    "silver":  {"emoji": "🥈", "min_score": 50,  "auto_merge_min": 9, "payout_bonus": "+10%"},
    "bronze":  {"emoji": "🥉", "min_score": 1,   "auto_merge_min": 9, "payout_bonus": "standard"},
    "new":     {"emoji": "🆕", "min_score": 0,   "auto_merge_min": None, "payout_bonus": "standard"},
    "flagged": {"emoji": "🚫", "min_score": None, "auto_merge_min": None, "payout_bonus": "blocked"},
    "banned":  {"emoji": "⛔", "min_score": None, "auto_merge_min": None, "payout_bonus": "blocked", "reason": "Banned for bounty farming"}
}

# =============================================================================
# ENDPOINTS
# =============================================================================

@reputation_bp.route('/api/v1/reputation', methods=['GET'])
def list_reputation():
    """List all contributors and their merit reputation."""
    all_contributors = build_contributor_list()
    
    # Separate banned/flagged users — show counts only, not individual entries
    banned = [c for c in all_contributors if c.get("tier") == "banned"]
    flagged = [c for c in all_contributors if c.get("tier") == "flagged"]
    contributors = [c for c in all_contributors if c.get("tier") not in ("banned", "flagged")]
    
    total_watt = sum(c["total_watt_earned"] for c in contributors)
    total_merged = sum(len(c["merged_prs"]) for c in contributors)
    
    return jsonify({
        "success": True,
        "total": len(contributors),
        "contributors": contributors,
        "banned_count": len(banned),
        "flagged_count": len(flagged),
        "stats": {
            "total_contributors": len(contributors),
            "total_merged_prs": total_merged,
            "total_watt_distributed": total_watt,
            "banned_users": len(banned),
            "flagged_users": len(flagged),
            "last_updated": datetime.utcnow().isoformat() + "Z"
        },
        "tiers": TIER_INFO,
        "scoring": {
            "merged_pr": "+10 points",
            "per_1000_watt": "+1 point",
            "rejected_pr": "-25 points",
            "reverted_pr": "-25 points"
        }
    })

@reputation_bp.route('/api/v1/reputation/<github_username>', methods=['GET'])
def get_contributor(github_username):
    """Get single contributor's merit reputation."""
    contributors = build_contributor_list()
    
    # Case-insensitive lookup
    contributor = None
    for c in contributors:
        if c["github"].lower() == github_username.lower():
            contributor = c
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
    """Get overall merit system stats."""
    all_contributors = build_contributor_list()
    
    banned = [c for c in all_contributors if c.get("tier") == "banned"]
    flagged = [c for c in all_contributors if c.get("tier") == "flagged"]
    active = [c for c in all_contributors if c.get("tier") not in ("banned", "flagged")]
    
    tier_counts = {}
    for c in active:
        tier = c.get("tier", "new")
        tier_counts[tier] = tier_counts.get(tier, 0) + 1
    
    return jsonify({
        "success": True,
        "stats": {
            "total_contributors": len(active),
            "total_watt_distributed": sum(c["total_watt_earned"] for c in active),
            "total_merged_prs": sum(len(c["merged_prs"]) for c in active),
            "tier_breakdown": tier_counts,
            "banned_users": len(banned),
            "flagged_users": len(flagged),            "last_updated": datetime.utcnow().isoformat() + "Z"
        }
    })
