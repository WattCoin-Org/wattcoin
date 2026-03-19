import asyncio
import json
import logging
import time
from typing import Dict, Any, Optional, List
from datetime import datetime
import aiohttp
import hashlib
import platform
import psutil
from dataclasses import dataclass, asdict

from .scraper import WebScraper
from .validator import DataValidator
from .config import Config

@dataclass
class SystemInfo:
    hostname: str
    platform: str
    cpu_count: int
    memory_total: int
    memory_available: int
    disk_usage: float
    
    @classmethod
    def get_current(cls) -> 'SystemInfo':
        memory = psutil.virtual_memory()
        disk = psutil.disk_usage('/')
        
        return cls(
            hostname=platform.node(),
            platform=f"{platform.system()} {platform.release()}",
            cpu_count=psutil.cpu_count(),
            memory_total=memory.total,
            memory_available=memory.available,
            disk_usage=disk.percent
        )

class PIAgent:
    def __init__(self, config: Config):
        self.config = config
        self.logger = logging.getLogger(__name__)
        self.session: Optional[aiohttp.ClientSession] = None
        self.scraper = WebScraper(config)
        self.validator = DataValidator(config)
        self.agent_id = self._generate_agent_id()
        self.running = False
        self.last_heartbeat = 0
        
    def _generate_agent_id(self) -> str:
        """Generate unique agent ID based on system info"""
        system_info = SystemInfo.get_current()
        unique_string = f"{system_info.hostname}_{system_info.platform}_{time.time()}"
        return hashlib.sha256(unique_string.encode()).hexdigest()[:16]
    
    async def __aenter__(self):
        self.session = aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(total=self.config.request_timeout)
        )
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.session:
            await self.session.close()
    
    async def register(self) -> bool:
        """Register agent with central API"""
        try:
            system_info = SystemInfo.get_current()
            registration_data = {
                "agent_id": self.agent_id,
                "system_info": asdict(system_info),
                "capabilities": ["web_scraping", "data_validation"],
                "version": "1.0.0",
                "timestamp": datetime.utcnow().isoformat()
            }
            
            async with self.session.post(
                f"{self.config.api_base_url}/agents/register",
                json=registration_data,
                headers={"Authorization": f"Bearer {self.config.api_token}"}
            ) as response:
                if response.status == 200:
                    result = await response.json()
                    self.logger.info(f"Agent registered successfully: {result}")
                    return True
                else:
                    error_text = await response.text()
                    self.logger.error(f"Registration failed: {response.status} - {error_text}")
                    return False
                    
        except Exception as e:
            self.logger.error(f"Registration error: {e}")
            return False
    
    async def send_heartbeat(self) -> bool:
        """Send periodic heartbeat to maintain registration"""
        try:
            system_info = SystemInfo.get_current()
            heartbeat_data = {
                "agent_id": self.agent_id,
                "status": "active",
                "system_info": asdict(system_info),
                "timestamp": datetime.utcnow().isoformat()
            }
            
            async with self.session.post(
                f"{self.config.api_base_url}/agents/heartbeat",
                json=heartbeat_data,
                headers={"Authorization": f"Bearer {self.config.api_token}"}
            ) as response:
                if response.status == 200:
                    self.last_heartbeat = time.time()
                    return True
                else:
                    self.logger.error(f"Heartbeat failed: {response.status}")
                    return False
                    
        except Exception as e:
            self.logger.error(f"Heartbeat error: {e}")
            return False
    
    async def poll_tasks(self) -> List[Dict[str, Any]]:
        """Poll for available tasks"""
        try:
            async with self.session.get(
                f"{self.config.api_base_url}/tasks/poll",
                params={"agent_id": self.agent_id},
                headers={"Authorization": f"Bearer {self.config.api_token}"}
            ) as response:
                if response.status == 200:
                    data = await response.json()
                    return data.get("tasks", [])
                elif response.status == 204:
                    return []
                else:
                    self.logger.error(f"Task polling failed: {response.status}")
                    return []
                    
        except Exception as e:
            self.logger.error(f"Task polling error: {e}")
            return []
    
    async def execute_task(self, task: Dict[str, Any]) -> Dict[str, Any]:
        """Execute a single task based on its type"""
        task_id = task.get("task_id")
        task_type = task.get("type")
        parameters = task.get("parameters", {})
        
        self.logger.info(f"Executing task {task_id} of type {task_type}")
        
        try:
            if task_type == "web_scraping":
                result = await self._execute_scraping_task(parameters)
            elif task_type == "data_validation":
                result = await self._execute_validation_task(parameters)
            else:
                raise ValueError(f"Unsupported task type: {task_type}")
            
            return {
                "task_id": task_id,
                "status": "completed",
                "result": result,
                "completed_at": datetime.utcnow().isoformat()
            }
            
        except Exception as e:
            self.logger.error(f"Task {task_id} failed: {e}")
            return {
                "task_id": task_id,
                "status": "failed",
                "error": str(e),
                "completed_at": datetime.utcnow().isoformat()
            }
    
    async def _execute_scraping_task(self, parameters: Dict[str, Any]) -> Dict[str, Any]:
        """Execute web scraping task"""
        url = parameters.get("url")
        selectors = parameters.get("selectors", {})
        options = parameters.get("options", {})
        
        if not url:
            raise ValueError("URL is required for scraping task")
        
        data = await self.scraper.scrape(url, selectors, **options)
        
        return {
            "url": url,
            "data": data,
            "scraped_at": datetime.utcnow().isoformat()
        }
    
    async def _execute_validation_task(self, parameters: Dict[str, Any]) -> Dict[str, Any]:
        """Execute data validation task"""
        data = parameters.get("data")
        schema = parameters.get("schema")
        rules = parameters.get("rules", [])
        
        if not data or not schema:
            raise ValueError("Data and schema are required for validation task")
        
        validation_result = await self.validator.validate(data, schema, rules)
        
        return {
            "validation_result": validation_result,
            "validated_at": datetime.utcnow().isoformat()
        }
    
    async def submit_result(self, result: Dict[str, Any]) -> bool:
        """Submit task result back to API"""
        try:
            async with self.session.post(
                f"{self.config.api_base_url}/tasks/results",
                json=result,
                headers={"Authorization": f"Bearer {self.config.api_token}"}
            ) as response:
                if response.status in [200, 201]:
                    self.logger.info(f"Result submitted for task {result.get('task_id')}")
                    return True
                else:
                    error_text = await response.text()
                    self.logger.error(f"Result submission failed: {response.status} - {error_text}")
                    return False
                    
        except Exception as e:
            self.logger.error(f"Result submission error: {e}")
            return False
    
    async def run(self):
        """Main agent loop"""
        self.running = True
        self.logger.info(f"Starting PI Agent {self.agent_id}")
        
        # Initial registration
        if not await self.register():
            self.logger.error("Failed to register agent, exiting")
            return
        
        while self.running:
            try:
                # Send heartbeat if needed
                current_time = time.time()
                if current_time - self.last_heartbeat > self.config.heartbeat_interval:
                    await self.send_heartbeat()
                
                # Poll for tasks
                tasks = await self.poll_tasks()
                
                if tasks:
                    self.logger.info(f"Received {len(tasks)} task(s)")
                    
                    # Process tasks concurrently
                    task_coroutines = [self.execute_task(task) for task in tasks]
                    results = await asyncio.gather(*task_coroutines, return_exceptions=True)
                    
                    # Submit results
                    for result in results:
                        if isinstance(result, dict):
                            await self.submit_result(result)
                        else:
                            self.logger.error(f"Task execution failed: {result}")
                
                # Wait before next poll
                await asyncio.sleep(self.config.poll_interval)
                
            except KeyboardInterrupt:
                self.logger.info("Received shutdown signal")
                break
            except Exception as e:
                self.logger.error(f"Unexpected error in main loop: {e}")
                await asyncio.sleep(5)  # Brief pause before retry
        
        self.running = False
        self.logger.info("PI Agent stopped")
    
    def stop(self):
        """Stop the agent"""
        self.running = False