#!/usr/bin/env python3
"""
WattNode - Light Node Daemon for WattCoin Network
Earn WATT by completing scrape/inference jobs

Usage:
    python wattnode.py register    # One-time registration
    python wattnode.py run         # Start daemon
    python wattnode.py status      # Check node status
    python wattnode.py earnings    # View earnings
"""

import os
import sys
import time
import json
import argparse
import requests
from datetime import datetime

from node_config import load_config, validate_config
from services.scraper import local_scrape
from services.inference import local_inference

API_BASE = os.environ.get("WATTCOIN_API_URL", "")
HEARTBEAT_INTERVAL = 60  # seconds
POLL_INTERVAL = 5  # seconds

class WattNode:
    def __init__(self, config_path: str = "config.yaml"):
        self.config = load_config(config_path)
        validate_config(self.config)
        
        self.wallet = self.config["wallet"]
        self.capabilities = self.config.get("capabilities", ["scrape"])
        self.node_id = self.config.get("node_id")  # Set after registration
        self.name = self.config.get("name", "unnamed-node")
        
        self.last_heartbeat = 0
        self.jobs_completed = 0
        self.total_earned = 0
        self.running = False
    
    def _api_call(self, method: str, endpoint: str, data: dict = None) -> dict:
        """Make API call to WattCoin backend"""
        url = f"{API_BASE}{endpoint}"
        try:
            if method == "GET":
                resp = requests.get(url, params=data, timeout=30)
            else:
                resp = requests.post(url, json=data, timeout=30)
            return resp.json()
        except requests.RequestException as e:
            return {"success": False, "error": str(e)}
    
    def register(self, stake_tx: str) -> bool:
        """Register node with network (requires stake TX)"""
        print(f"🔗 Registering node '{self.name}' with capabilities: {self.capabilities}")
        
        result = self._api_call("POST", "/api/v1/nodes/register", {
            "wallet": self.wallet,
            "capabilities": self.capabilities,
            "stake_tx": stake_tx,
            "name": self.name,
            "endpoint": None  # Polling mode
        })
        
        if result.get("success"):
            self.node_id = result.get("node_id")
            print(f"✅ Registered! Node ID: {self.node_id}")
            print(f"   Stake verified: {result.get('stake_amount')} WATT")
            print(f"   You will earn 70% of each job payment")
            
            # Save node_id to config for future runs
            self._save_node_id()
            return True
        else:
            print(f"❌ Registration failed: {result.get('error')}")
            return False
    
    def _save_node_id(self):
        """Save node_id to local file for persistence"""
        with open(".wattnode_id", "w") as f:
            json.dump({"node_id": self.node_id, "wallet": self.wallet}, f)
    
    def _load_node_id(self) -> str:
        """Load saved node_id"""
        if os.path.exists(".wattnode_id"):
            with open(".wattnode_id") as f:
                data = json.load(f)
                if data.get("wallet") == self.wallet:
                    return data.get("node_id")
        return None
    
    def heartbeat(self) -> bool:
        """Send heartbeat to keep node active"""
        if not self.node_id:
            return False
        
        result = self._api_call("POST", "/api/v1/nodes/heartbeat", {
            "node_id": self.node_id
        })
        
        if result.get("success"):
            self.last_heartbeat = time.time()
            return True
        else:
            print(f"⚠️  Heartbeat failed: {result.get('error')}")
            return False
    
    def poll_jobs(self) -> list:
        """Poll for available jobs"""
        if not self.node_id:
            return []
        
        result = self._api_call("GET", "/api/v1/nodes/jobs", {
            "node_id": self.node_id
        })
        
        if result.get("success"):
            return result.get("jobs", [])
        return []
    
    def claim_job(self, job_id: str) -> bool:
        """Claim a job to work on"""
        result = self._api_call("POST", f"/api/v1/nodes/jobs/{job_id}/claim", {
            "node_id": self.node_id
        })
        return result.get("success", False)
    
    def execute_job(self, job: dict) -> dict:
        """Execute a job based on type"""
        job_type = job.get("type")
        payload = job.get("payload", {})
        
        try:
            if job_type == "scrape":
                url = payload.get("url")
                fmt = payload.get("format", "text")
                print(f"   📄 Scraping: {url[:50]}...")
                content = local_scrape(url, fmt)
                return {
                    "success": True,
                    "content": content,
                    "status_code": 200
                }
            
            elif job_type == "inference":
                prompt = payload.get("prompt")
                model = payload.get("model", "llama2")
                print(f"   🧠 Running inference: {prompt[:30]}...")
                response = local_inference(prompt, model)
                return {
                    "success": True,
                    "response": response
                }
            
            else:
                return {"success": False, "error": f"Unknown job type: {job_type}"}
        
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    def submit_result(self, job_id: str, result: dict) -> dict:
        """Submit completed job result"""
        response = self._api_call("POST", f"/api/v1/nodes/jobs/{job_id}/complete", {
            "node_id": self.node_id,
            "result": result
        })
        return response
    
    def get_status(self) -> dict:
        """Get node status from network"""
        if not self.node_id:
            # Try to load saved node_id
            self.node_id = self._load_node_id()
            if not self.node_id:
                return {"registered": False}
        
        result = self._api_call("GET", f"/api/v1/nodes/{self.node_id}", {})
        if result.get("success"):
            return {
                "registered": True,
                "node_id": self.node_id,
                "name": result.get("name"),
                "status": result.get("status"),
                "capabilities": result.get("capabilities"),
                "jobs_completed": result.get("jobs_completed"),
                "total_earned": result.get("total_earned"),
                "stake_amount": result.get("stake_amount")
            }
        return {"registered": False, "error": result.get("error")}
    
    def run(self):
        """Main daemon loop"""
        # Load or require node_id
        if not self.node_id:
            self.node_id = self._load_node_id()
        
        if not self.node_id:
            print("❌ Node not registered. Run: python wattnode.py register <stake_tx>")
            return
        
        print(f"⚡ WattNode starting...")
        print(f"   Node ID: {self.node_id}")
        print(f"   Wallet: {self.wallet}")
        print(f"   Capabilities: {', '.join(self.capabilities)}")
        print(f"   Poll interval: {POLL_INTERVAL}s")
        print(f"   Heartbeat interval: {HEARTBEAT_INTERVAL}s")
        print()
        print("🟢 Listening for jobs... (Ctrl+C to stop)")
        print("-" * 50)
        
        self.running = True
        
        try:
            while self.running:
                # Heartbeat if needed
                if time.time() - self.last_heartbeat > HEARTBEAT_INTERVAL:
                    self.heartbeat()
                
                # Poll for jobs
                jobs = self.poll_jobs()
                
                for job in jobs:
                    job_id = job.get("job_id")
                    job_type = job.get("type")
                    reward = job.get("reward", 0)
                    
                    print(f"\n📥 Job received: {job_id}")
                    print(f"   Type: {job_type}")
                    print(f"   Reward: {reward} WATT")
                    
                    # Claim job
                    if not self.claim_job(job_id):
                        print(f"   ⚠️  Could not claim job (already taken?)")
                        continue
                    
                    # Execute
                    result = self.execute_job(job)
                    
                    if result.get("success"):
                        # Submit result
                        submit_resp = self.submit_result(job_id, result)
                        
                        if submit_resp.get("success"):
                            self.jobs_completed += 1
                            self.total_earned += reward
                            print(f"   ✅ Completed! Earned: {reward} WATT")
                            print(f"   📊 Total: {self.jobs_completed} jobs, {self.total_earned} WATT")
                        else:
                            print(f"   ❌ Submit failed: {submit_resp.get('error')}")
                    else:
                        print(f"   ❌ Job failed: {result.get('error')}")
                
                time.sleep(POLL_INTERVAL)
        
        except KeyboardInterrupt:
            print("\n\n🛑 Shutting down...")
            print(f"   Session stats: {self.jobs_completed} jobs, {self.total_earned} WATT earned")
            self.running = False


def main():
    parser = argparse.ArgumentParser(description="WattNode - Earn WATT by running a light node")
    parser.add_argument("command", choices=["register", "run", "status", "earnings"],
                       help="Command to execute")
    parser.add_argument("stake_tx", nargs="?", help="Stake transaction signature (for register)")
    parser.add_argument("-c", "--config", default="config.yaml", help="Config file path")
    
    args = parser.parse_args()
    
    node = WattNode(args.config)
    
    if args.command == "register":
        if not args.stake_tx:
            print("❌ Usage: python wattnode.py register <stake_tx>")
            print()
            print("Steps:")
            print("1. Send 10,000 WATT to treasury wallet:")
            print("   Atu5phbGGGFogbKhi259czz887dSdTfXwJxwbuE5aF5q")
            print("2. Copy the transaction signature")
            print("3. Run: python wattnode.py register <tx_signature>")
            sys.exit(1)
        
        node.register(args.stake_tx)
    
    elif args.command == "run":
        node.run()
    
    elif args.command == "status":
        status = node.get_status()
        if status.get("registered"):
            print(f"⚡ WattNode Status")
            print(f"   Node ID: {status.get('node_id')}")
            print(f"   Name: {status.get('name')}")
            print(f"   Status: {status.get('status')}")
            print(f"   Capabilities: {', '.join(status.get('capabilities', []))}")
            print(f"   Jobs completed: {status.get('jobs_completed')}")
            print(f"   Total earned: {status.get('total_earned')} WATT")
            print(f"   Stake: {status.get('stake_amount')} WATT")
        else:
            print("❌ Node not registered")
            if status.get("error"):
                print(f"   Error: {status.get('error')}")
    
    elif args.command == "earnings":
        status = node.get_status()
        if status.get("registered"):
            print(f"💰 WattNode Earnings")
            print(f"   Jobs completed: {status.get('jobs_completed')}")
            print(f"   Total earned: {status.get('total_earned')} WATT")
        else:
            print("❌ Node not registered")


if __name__ == "__main__":
    main()
