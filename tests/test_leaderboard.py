"""
Tests for the task marketplace leaderboard API endpoint.
"""

import pytest
import json
import os
import sys
import time

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


@pytest.fixture
def client():
    """Create test client."""
    # Set up test environment
    os.environ['DATA_DIR'] = '/tmp/wattcoin_test_data'
    os.environ['TASKS_FILE'] = '/tmp/wattcoin_test_data/tasks.json'
    
    # Create test data directory
    os.makedirs('/tmp/wattcoin_test_data', exist_ok=True)
    
    from bridge_web import app
    app.config['TESTING'] = True
    
    with app.test_client() as client:
        yield client
    
    # Cleanup
    import shutil
    if os.path.exists('/tmp/wattcoin_test_data'):
        shutil.rmtree('/tmp/wattcoin_test_data')


def create_test_tasks(verified_tasks):
    """Helper to create test task data."""
    os.makedirs('/tmp/wattcoin_test_data', exist_ok=True)
    
    tasks = {}
    for i, task in enumerate(verified_tasks):
        task_id = f"task_{i}"
        tasks[task_id] = {
            "title": f"Task {i}",
            "status": "verified",
            "type": "code",
            "claimer_wallet": task["wallet"],
            "claimer_name": task.get("name"),
            "worker_payout": task["payout"],
            "verification": {
                "score": task["score"],
                "threshold": 7
            }
        }
    
    data = {
        "tasks": tasks,
        "stats": {}
    }
    
    with open('/tmp/wattcoin_test_data/tasks.json', 'w') as f:
        json.dump(data, f)


def test_leaderboard_endpoint_returns_200(client):
    """Test that leaderboard endpoint returns 200."""
    create_test_tasks([])
    
    response = client.get('/api/v1/tasks/leaderboard')
    assert response.status_code == 200


def test_leaderboard_response_format(client):
    """Test that leaderboard returns correct JSON format."""
    create_test_tasks([
        {"wallet": "Wallet1ABC", "payout": 1000, "score": 8}
    ])
    
    response = client.get('/api/v1/tasks/leaderboard')
    data = json.loads(response.data)
    
    assert data["success"] is True
    assert "leaderboard" in data
    assert "cached" in data
    assert "cache_age_seconds" in data
    assert "sort_by" in data


def test_leaderboard_entry_format(client):
    """Test that each leaderboard entry has required fields."""
    create_test_tasks([
        {"wallet": "Wallet1ABCDEFGH", "name": "TestBot", "payout": 1000, "score": 8}
    ])
    
    response = client.get('/api/v1/tasks/leaderboard')
    data = json.loads(response.data)
    
    assert len(data["leaderboard"]) == 1
    entry = data["leaderboard"][0]
    
    assert "rank" in entry
    assert "wallet" in entry
    assert "agent_name" in entry
    assert "tasks_completed" in entry
    assert "total_earned" in entry
    assert "avg_score" in entry


def test_leaderboard_wallet_truncation(client):
    """Test that wallet addresses are truncated."""
    create_test_tasks([
        {"wallet": "7vvNkG3JF3JpxLEavqZSkc5T3n9hHR98Uw23fbWdXVSF", "payout": 1000, "score": 8}
    ])
    
    response = client.get('/api/v1/tasks/leaderboard')
    data = json.loads(response.data)
    
    entry = data["leaderboard"][0]
    assert entry["wallet"] == "7vvNkG3J..."
    assert len(entry["wallet"]) == 11  # 8 chars + "..."


def test_leaderboard_aggregates_by_wallet(client):
    """Test that multiple tasks by same wallet are aggregated."""
    create_test_tasks([
        {"wallet": "Wallet1ABC", "payout": 1000, "score": 8},
        {"wallet": "Wallet1ABC", "payout": 2000, "score": 9},
        {"wallet": "Wallet2XYZ", "payout": 500, "score": 7}
    ])
    
    response = client.get('/api/v1/tasks/leaderboard')
    data = json.loads(response.data)
    
    assert len(data["leaderboard"]) == 2
    
    # Find Wallet1 entry
    wallet1_entry = next((e for e in data["leaderboard"] if "Wallet1A" in e["wallet"]), None)
    assert wallet1_entry is not None
    assert wallet1_entry["tasks_completed"] == 2
    assert wallet1_entry["total_earned"] == 3000
    assert wallet1_entry["avg_score"] == 8.5


def test_leaderboard_sort_by_earned(client):
    """Test sorting by total earned (default)."""
    create_test_tasks([
        {"wallet": "WalletA", "payout": 500, "score": 9},
        {"wallet": "WalletB", "payout": 2000, "score": 7},
        {"wallet": "WalletC", "payout": 1000, "score": 8}
    ])
    
    response = client.get('/api/v1/tasks/leaderboard?sort_by=earned')
    data = json.loads(response.data)
    
    assert data["sort_by"] == "earned"
    assert data["leaderboard"][0]["total_earned"] == 2000
    assert data["leaderboard"][0]["rank"] == 1
    assert data["leaderboard"][1]["total_earned"] == 1000
    assert data["leaderboard"][1]["rank"] == 2


def test_leaderboard_sort_by_completed(client):
    """Test sorting by tasks completed."""
    create_test_tasks([
        {"wallet": "WalletA", "payout": 100, "score": 8},
        {"wallet": "WalletA", "payout": 100, "score": 8},
        {"wallet": "WalletA", "payout": 100, "score": 8},
        {"wallet": "WalletB", "payout": 1000, "score": 9}
    ])
    
    response = client.get('/api/v1/tasks/leaderboard?sort_by=completed')
    data = json.loads(response.data)
    
    assert data["sort_by"] == "completed"
    assert data["leaderboard"][0]["tasks_completed"] == 3


def test_leaderboard_sort_by_avg_score(client):
    """Test sorting by average score."""
    create_test_tasks([
        {"wallet": "WalletA", "payout": 1000, "score": 7},
        {"wallet": "WalletB", "payout": 500, "score": 10}
    ])
    
    response = client.get('/api/v1/tasks/leaderboard?sort_by=avg_score')
    data = json.loads(response.data)
    
    assert data["sort_by"] == "avg_score"
    assert data["leaderboard"][0]["avg_score"] == 10.0


def test_leaderboard_limit(client):
    """Test that limit parameter works."""
    # Create 10 wallets
    tasks = [{"wallet": f"Wallet{i}XYZ", "payout": 100 * i, "score": 8} for i in range(1, 11)]
    create_test_tasks(tasks)
    
    response = client.get('/api/v1/tasks/leaderboard?limit=3')
    data = json.loads(response.data)
    
    assert len(data["leaderboard"]) == 3


def test_leaderboard_limit_max_100(client):
    """Test that limit is capped at 100."""
    create_test_tasks([])
    
    response = client.get('/api/v1/tasks/leaderboard?limit=500')
    # Should not error, just cap at 100
    assert response.status_code == 200


def test_leaderboard_empty(client):
    """Test leaderboard with no verified tasks."""
    create_test_tasks([])
    
    response = client.get('/api/v1/tasks/leaderboard')
    data = json.loads(response.data)
    
    assert data["success"] is True
    assert data["leaderboard"] == []


def test_leaderboard_caching(client):
    """Test that caching works."""
    create_test_tasks([
        {"wallet": "WalletA", "payout": 1000, "score": 8}
    ])
    
    # First request - not cached
    response1 = client.get('/api/v1/tasks/leaderboard')
    data1 = json.loads(response1.data)
    assert data1["cached"] is False
    
    # Second request - should be cached
    response2 = client.get('/api/v1/tasks/leaderboard')
    data2 = json.loads(response2.data)
    assert data2["cached"] is True
    assert data2["cache_age_seconds"] >= 0
