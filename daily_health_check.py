#!/usr/bin/env python3
"""
WattCoin Daily API Health Check (Agent Task #21)
Checks all critical endpoints and reports status.
"""

import requests
import json
import time
import sys
from datetime import datetime

API_BASE = "https://wattcoin-production-81a7.up.railway.app"

ENDPOINTS = [
    ("GET", "/health"),
    ("GET", "/api/v1/bounties"),
    ("GET", "/api/v1/reputation"),
    ("GET", "/api/v1/reputation/stats"),
    ("GET", "/api/v1/llm/pricing"),
    # ("POST", "/api/v1/llm"), # Skipping POSTs to avoid cost/auth errors in check
    # ("POST", "/api/v1/scrape"),
]

def check_endpoint(method, endpoint):
    url = f"{API_BASE}{endpoint}"
    start_time = time.time()
    try:
        if method == "GET":
            response = requests.get(url, timeout=10)
        else:
            response = requests.post(url, timeout=10)
        
        latency_ms = (time.time() - start_time) * 1000
        
        return {
            "endpoint": endpoint,
            "method": method,
            "status_code": response.status_code,
            "latency_ms": round(latency_ms, 2),
            "healthy": 200 <= response.status_code < 500
        }
    except Exception as e:
        return {
            "endpoint": endpoint,
            "method": method,
            "status_code": 0,
            "latency_ms": 0,
            "healthy": False,
            "error": str(e)
        }

def run_health_check():
    print(f"[*] Starting Daily Health Check for {API_BASE}...")
    
    results = []
    all_healthy = True
    
    for method, endpoint in ENDPOINTS:
        print(f"    Checking {method} {endpoint}...", end="")
        result = check_endpoint(method, endpoint)
        results.append(result)
        
        if result["healthy"]:
            print(f" ✅ ({result['status_code']} - {result['latency_ms']}ms)")
        else:
            print(f" ❌ ({result['status_code']})")
            all_healthy = False

    report = {
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "api_base": API_BASE,
        "overall_status": "healthy" if all_healthy else "degraded",
        "checks": results
    }
    
    # Save report
    with open("daily_health_report.json", "w") as f:
        json.dump(report, f, indent=2)
        
    print(f"\n[+] Health Check Complete. Report saved to daily_health_report.json")
    return report

if __name__ == "__main__":
    run_health_check()
