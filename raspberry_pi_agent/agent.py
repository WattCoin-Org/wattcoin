import asyncio
import json
import logging
import aiohttp
import hashlib
import time
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, asdict
from pathlib import Path
import psutil
import platform
import requests
from bs4 import BeautifulSoup
import pandas as pd
from datetime import datetime, timedelta

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

@dataclass
class AgentInfo:
    agent_id: str
    hostname: str
    platform: str
    cpu_count: int
    memory_gb: float
    status: str = "idle"
    last_heartbeat: float = 0
    earnings: float = 0.0
    tasks_completed: int = 0

@dataclass
class Task:
    task_id: str
    task_type: str
    payload: Dict[str, Any]
    priority: int = 1
    timeout: int = 300
    reward: float = 0.0
    status: str = "pending"
    created_at: float = 0
    assigned_at: float = 0
    completed_at: float = 0
    result: Optional[Dict[str, Any]] = None
    error: Optional[str] = None

class RaspberryPiAgent:
    def __init__(self, api_base_url: str = "http://localhost:8000"):
        self.api_base_url = api_base_url.rstrip('/')
        self.agent_info = self._get_system_info()
        self.session = None
        self.running = False
        self.current_task = None
        self.poll_interval = 5
        self.heartbeat_interval = 30
        self.last_heartbeat = 0
        
        # Task execution modules
        self.task_handlers = {
            "web_scraping": self._handle_web_scraping,
            "data_validation": self._handle_data_validation,
            "file_processing": self._handle_file_processing,
            "system_info": self._handle_system_info,
            "network_test": self._handle_network_test
        }
        
        # Earnings tracking
        self.earnings_file = Path("earnings.json")
        self._load_earnings()
    
    def _get_system_info(self) -> AgentInfo:
        """Get system information for agent registration."""
        hostname = platform.node()
        agent_id = hashlib.sha256(f"{hostname}_{platform.machine()}".encode()).hexdigest()[:16]
        
        return AgentInfo(
            agent_id=agent_id,
            hostname=hostname,
            platform=f"{platform.system()} {platform.release()}",
            cpu_count=psutil.cpu_count(),
            memory_gb=round(psutil.virtual_memory().total / (1024**3), 2),
            last_heartbeat=time.time()
        )
    
    def _load_earnings(self):
        """Load earnings from local file."""
        if self.earnings_file.exists():
            try:
                with open(self.earnings_file, 'r') as f:
                    data = json.load(f)
                    self.agent_info.earnings = data.get('total_earnings', 0.0)
                    self.agent_info.tasks_completed = data.get('tasks_completed', 0)
            except Exception as e:
                logger.warning(f"Could not load earnings file: {e}")
    
    def _save_earnings(self):
        """Save earnings to local file."""
        try:
            with open(self.earnings_file, 'w') as f:
                json.dump({
                    'total_earnings': self.agent_info.earnings,
                    'tasks_completed': self.agent_info.tasks_completed,
                    'last_updated': time.time()
                }, f)
        except Exception as e:
            logger.error(f"Could not save earnings: {e}")
    
    async def _make_request(self, method: str, endpoint: str, data: Dict = None) -> Optional[Dict]:
        """Make HTTP request to API."""
        url = f"{self.api_base_url}{endpoint}"
        try:
            async with self.session.request(method, url, json=data) as response:
                if response.status == 200:
                    return await response.json()
                else:
                    logger.error(f"API request failed: {response.status} - {await response.text()}")
                    return None
        except Exception as e:
            logger.error(f"Request error: {e}")
            return None
    
    async def register_agent(self) -> bool:
        """Register agent with the API."""
        data = asdict(self.agent_info)
        response = await self._make_request("POST", "/api/agents/register", data)
        
        if response and response.get("status") == "success":
            logger.info(f"Agent {self.agent_info.agent_id} registered successfully")
            return True
        else:
            logger.error("Failed to register agent")
            return False
    
    async def send_heartbeat(self):
        """Send heartbeat to maintain connection."""
        self.agent_info.last_heartbeat = time.time()
        data = {
            "agent_id": self.agent_info.agent_id,
            "status": self.agent_info.status,
            "cpu_usage": psutil.cpu_percent(),
            "memory_usage": psutil.virtual_memory().percent,
            "earnings": self.agent_info.earnings,
            "tasks_completed": self.agent_info.tasks_completed
        }
        
        response = await self._make_request("POST", "/api/agents/heartbeat", data)
        if response:
            logger.debug("Heartbeat sent successfully")
        else:
            logger.warning("Failed to send heartbeat")
    
    async def poll_for_tasks(self) -> Optional[Task]:
        """Poll for available tasks."""
        params = {
            "agent_id": self.agent_info.agent_id,
            "capabilities": list(self.task_handlers.keys())
        }
        
        response = await self._make_request("GET", "/api/tasks/poll", params)
        
        if response and response.get("task"):
            task_data = response["task"]
            return Task(
                task_id=task_data["task_id"],
                task_type=task_data["task_type"],
                payload=task_data["payload"],
                priority=task_data.get("priority", 1),
                timeout=task_data.get("timeout", 300),
                reward=task_data.get("reward", 0.0),
                created_at=task_data.get("created_at", time.time()),
                assigned_at=time.time()
            )
        
        return None
    
    async def submit_task_result(self, task: Task):
        """Submit task result to API."""
        data = {
            "task_id": task.task_id,
            "agent_id": self.agent_info.agent_id,
            "status": task.status,
            "result": task.result,
            "error": task.error,
            "completed_at": task.completed_at,
            "execution_time": task.completed_at - task.assigned_at
        }
        
        response = await self._make_request("POST", "/api/tasks/result", data)
        
        if response and response.get("status") == "success":
            # Update earnings
            if task.status == "completed" and task.reward > 0:
                self.agent_info.earnings += task.reward
                self.agent_info.tasks_completed += 1
                self._save_earnings()
                logger.info(f"Task completed. Earned {task.reward} WATT. Total: {self.agent_info.earnings}")
            
            return True
        else:
            logger.error("Failed to submit task result")
            return False
    
    async def _handle_web_scraping(self, payload: Dict) -> Dict[str, Any]:
        """Handle web scraping tasks."""
        url = payload.get("url")
        if not url:
            raise ValueError("URL is required for web scraping")
        
        selectors = payload.get("selectors", {})
        headers = payload.get("headers", {"User-Agent": "RaspberryPi-Agent/1.0"})
        
        async with self.session.get(url, headers=headers) as response:
            if response.status != 200:
                raise Exception(f"HTTP {response.status}: {await response.text()}")
            
            html = await response.text()
            soup = BeautifulSoup(html, 'html.parser')
            
            result = {
                "url": url,
                "status_code": response.status,
                "scraped_data": {},
                "metadata": {
                    "title": soup.title.string if soup.title else None,
                    "scraped_at": time.time()
                }
            }
            
            for key, selector in selectors.items():
                elements = soup.select(selector)
                if len(elements) == 1:
                    result["scraped_data"][key] = elements[0].get_text().strip()
                else:
                    result["scraped_data"][key] = [el.get_text().strip() for el in elements]
            
            return result
    
    async def _handle_data_validation(self, payload: Dict) -> Dict[str, Any]:
        """Handle data validation tasks."""
        data = payload.get("data")
        rules = payload.get("rules", [])
        
        if not data or not rules:
            raise ValueError("Data and rules are required for validation")
        
        results = {
            "valid": True,
            "errors": [],
            "warnings": [],
            "validated_fields": 0,
            "validation_rules_applied": len(rules)
        }
        
        for rule in rules:
            field = rule.get("field")
            rule_type = rule.get("type")
            rule_params = rule.get("params", {})
            
            if field not in data:
                results["errors"].append(f"Missing required field: {field}")
                results["valid"] = False
                continue
            
            value = data[field]
            results["validated_fields"] += 1
            
            try:
                if rule_type == "required" and not value:
                    results["errors"].append(f"Field {field} is required")
                    results["valid"] = False
                
                elif rule_type == "type":
                    expected_type = rule_params.get("expected")
                    if expected_type == "int" and not isinstance(value, int):
                        results["errors"].append(f"Field {field} must be an integer")
                        results["valid"] = False
                    elif expected_type == "str" and not isinstance(value, str):
                        results["errors"].append(f"Field {field} must be a string")
                        results["valid"] = False
                
                elif rule_type == "range":
                    min_val = rule_params.get("min")
                    max_val = rule_params.get("max")
                    if min_val is not None and value < min_val:
                        results["errors"].append(f"Field {field} below minimum: {min_val}")
                        results["valid"] = False
                    if max_val is not None and value > max_val:
                        results["errors"].append(f"Field {field} above maximum: {max_val}")
                        results["valid"] = False
                
            except Exception as e:
                results["errors"].append(f"Validation error for {field}: {str(e)}")
                results["valid"] = False
        
        return results
    
    async def _handle_file_processing(self, payload: Dict) -> Dict[str, Any]:
        """Handle file processing tasks."""
        file_url = payload.get("file_url")
        operation = payload.get("operation", "analyze")
        
        if not file_url:
            raise ValueError("file_url is required")
        
        # Download file
        async with self.session.get(file_url) as response:
            if response.status != 200:
                raise Exception(f"Failed to download file: HTTP {response.status}")
            
            file_content = await response.read()
            file_size = len(file_content)
        
        result = {
            "file_url": file_url,
            "file_size": file_size,
            "operation": operation,
            "processed_at": time.time()
        }
        
        if operation == "analyze":
            # Basic file analysis
            result["analysis"] = {
                "size_mb": round(file_size / (1024 * 1024), 2),
                "hash_md5": hashlib.md5(file_content).hexdigest(),
                "hash_sha256": hashlib.sha256(file_content).hexdigest()
            }
        
        elif operation == "csv_process":
            # Process CSV file
            try:
                import io
                df = pd.read_csv(io.BytesIO(file_content))
                result["csv_analysis"] = {
                    "rows": len(df),
                    "columns": len(df.columns),
                    "column_names": df.columns.tolist(),
                    "data_types": df.dtypes.to_dict(),
                    "sample_data": df.head().to_dict()
                }
            except Exception as e:
                result["error"] = f"CSV processing failed: {str(e)}"
        
        return result
    
    async def _handle_system_info(self, payload: Dict) -> Dict[str, Any]:
        """Handle system information requests."""
        info_type = payload.get("type", "basic")
        
        result = {
            "agent_id": self.agent_info.agent_id,
            "timestamp": time.time()
        }
        
        if info_type in ["basic", "all"]:
            result["basic_info"] = {
                "hostname": self.agent_info.hostname,
                "platform": self.agent_info.platform,
                "cpu_count": self.agent_info.cpu_count,
                "memory_gb": self.agent_info.memory_gb,
                "cpu_usage": psutil.cpu_percent(),
                "memory_usage": psutil.virtual_memory().percent,
                "disk_usage": psutil.disk_usage('/').percent
            }
        
        if info_type in ["network", "all"]:
            net_io = psutil.net_io_counters()
            result["network_info"] = {
                "bytes_sent": net_io.bytes_sent,
                "bytes_recv": net_io.bytes_recv,
                "packets_sent": net_io.packets_sent,
                "packets_recv": net_io.packets_recv
            }
        
        if info_type in ["performance", "all"]:
            result["performance"] = {
                "boot_time": psutil.boot_time(),
                "load_average": psutil.getloadavg() if hasattr(psutil, 'getloadavg') else None,
                "process_count": len(psutil.pids())
            }
        
        return result
    
    async def _handle_network_test(self, payload: Dict) -> Dict[str, Any]:
        """Handle network connectivity tests."""
        target_url = payload.get("target_url", "https://www.google.com")
        test_type = payload.get("test_type", "ping")
        
        result = {
            "target_url": target_url,
            "test_type": test_type,
            "timestamp": time.time()
        }
        
        if test_type == "http":
            start_time = time.time()
            try:
                async with self.session.get(target_url) as response:
                    end_time = time.time()
                    result["success"] = True
                    result["status_code"] = response.status
                    result["response_time_ms"] = round((end_time - start_time) * 1000, 2)
                    result["headers"] = dict(response.headers)
            except Exception as e:
                result["success"] = False
                result["error"] = str(e)
        
        return result
    
    async def execute_task(self, task: Task) -> Task:
        """Execute a task and return the updated task with results."""
        logger.info(f"Executing task {task.task_id} of type {task.task_type}")
        
        self.agent_info.status = "working"
        self.current_task = task
        
        start_time = time.time()
        
        try:
            if task.task_type not in self.task_handlers:
                raise ValueError(f"Unknown task type: {task.task_type}")
            
            handler = self.task_handlers[task.task_type]
            result = await asyncio.wait_for(
                handler(task.payload),
                timeout=task.timeout
            )
            
            task.status = "completed"
            task.result = result
            task.completed_at = time.time()
            
            logger.info(f"Task {task.task_id} completed in {task.completed_at - start_time:.2f}s")
            
        except asyncio.TimeoutError:
            task.status = "timeout"
            task.error = f"Task timed out after {task.timeout} seconds"
            task.completed_at = time.time()
            logger.error(f"Task {task.task_id} timed out")
            
        except Exception as e:
            task.status = "failed"
            task.error = str(e)
            task.completed_at = time.time()
            logger.error(f"Task {task.task_id} failed: {e}")
        
        finally:
            self.agent_info.status = "idle"
            self.current_task = None
        
        return task
    
    async def run(self):
        """Main agent loop."""
        logger.info("Starting Raspberry Pi Agent...")
        
        self.session = aiohttp.ClientSession()
        self.running = True
        
        try:
            # Register with API
            if not await self.register_agent():
                logger.error("Failed to register agent. Exiting.")
                return
            
            logger.info(f"Agent {self.agent_info.agent_id} started successfully")
            
            while self.running:
                try:
                    # Send heartbeat if needed
                    current_time = time.time()
                    if current_time - self.last_heartbeat > self.heartbeat_interval:
                        await self.send_heartbeat()
                        self.last_heartbeat = current_time
                    
                    # Poll for tasks if not busy
                    if self.agent_info.status == "idle":
                        task = await self.poll_for_tasks()
                        
                        if task:
                            # Execute task
                            completed_task = await self.execute_task(task)
                            
                            # Submit result
                            await self.submit_task_result(completed_task)
                    
                    # Sleep before next iteration
                    await asyncio.sleep(self.poll_interval)
                    
                except KeyboardInterrupt:
                    logger.info("Shutdown requested")
                    break
                    
                except Exception as e:
                    logger.error(f"Error in main loop: {e}")
                    await asyncio.sleep(5)
            
        finally:
            if self.session:
                await self.session.close()
            self.running = False
            logger.info("Agent stopped")
    
    async def stop(self):
        """Stop the agent gracefully."""
        logger.info("Stopping agent...")
        self.running = False
        
        if self.current_task:
            logger.info("Waiting for current task to complete...")
            # Allow current task to finish
            await asyncio.sleep(1)

if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Raspberry Pi Agent Node")
    parser.add_argument("--api-url", default="http://localhost:8000", help="API base URL")
    parser.add_argument("--poll-interval", type=int, default=5, help="Task polling interval in seconds")
    parser.add_argument("--heartbeat-interval", type=int, default=30, help="Heartbeat interval in seconds")
    
    args = parser.parse_args()
    
    agent = RaspberryPiAgent(api_base_url=args.api_url)
    agent.poll_interval = args.poll_interval
    agent.heartbeat_interval = args.heartbeat_interval
    
    try:
        asyncio.run(agent.run())
    except KeyboardInterrupt:
        logger.info("Agent stopped by user")