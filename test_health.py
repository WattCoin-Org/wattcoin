import requests
import sys
import json

BASE_URL = "http://localhost:5003"

def test_health():
    print(f"Testing {BASE_URL}/health ...")
    try:
        resp = requests.get(f"{BASE_URL}/health", timeout=5)
        print(f"Status: {resp.status_code}")
        data = resp.json()
        print(json.dumps(data, indent=2))
        
        # Validation
        assert resp.status_code in [200, 503]
        assert "uptime_seconds" in data
        assert "services" in data
        assert "database" in data["services"]
        assert "active_nodes" in data
        assert "open_tasks" in data
        
        print("✅ Health check schema verified!")
        
    except Exception as e:
        print(f"❌ Test failed: {e}")
        sys.exit(1)

if __name__ == "__main__":
    test_health()
