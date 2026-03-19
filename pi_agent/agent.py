import asyncio
import aiohttp
import json
import logging
from datetime import datetime
from typing import Dict, Any, List, Optional
import hashlib
import uuid
from dataclasses import dataclass, asdict
import time

from .config import AgentConfig
from .execution_engine import ExecutionEngine
from .wattcoin_api import WattCoinAPI
from .utils import setup_logging

@dataclass
class TaskResult:
    task_id: str
    agent_id: str
    status: str
    result: Any
    execution_time: float
    timestamp: datetime
    error: Optional[str] = None

class PIAgent:
    def __init__(self, config: AgentConfig):
        self.config = config
        self.agent_id = self._generate_agent_id()
        self.logger = setup_logging("pi_agent")
        self.wattcoin_api = WattCoinAPI(config.wattcoin_api_url, config.api_key)
        self.execution_engine = ExecutionEngine(config)
        self.is_running = False
        self.current_tasks = {}
        
    def _generate_agent_id(self) -> str:
        """Generate unique agent ID based on device info"""
        device_info = f"{self.config.device_id}-{time.time()}"
        return hashlib.sha256(device_info.encode()).hexdigest()[:16]
    
    async def register_agent(self) -> bool:
        """Register this agent with WattCoin network"""
        try:
            registration_data = {
                "agent_id": self.agent_id,
                "device_id": self.config.device_id,
                "capabilities": self.config.capabilities,
                "location": self.config.location,
                "max_concurrent_tasks": self.config.max_concurrent_tasks,
                "timestamp": datetime.utcnow().isoformat()
            }
            
            response = await self.wattcoin_api.register_agent(registration_data)
            if response.get("status") == "success":
                self.logger.info(f"Agent {self.agent_id} successfully registered")
                return True
            else:
                self.logger.error(f"Registration failed: {response.get('message', 'Unknown error')}")
                return False
                
        except Exception as e:
            self.logger.error(f"Registration error: {str(e)}")
            return False
    
    async def poll_tasks(self) -> List[Dict[str, Any]]:
        """Poll for available tasks from WattCoin network"""
        try:
            available_slots = self.config.max_concurrent_tasks - len(self.current_tasks)
            if available_slots <= 0:
                return []
            
            task_request = {
                "agent_id": self.agent_id,
                "capabilities": self.config.capabilities,
                "max_tasks": available_slots
            }
            
            response = await self.wattcoin_api.get_tasks(task_request)
            return response.get("tasks", [])
            
        except Exception as e:
            self.logger.error(f"Task polling error: {str(e)}")
            return []
    
    async def execute_task(self, task: Dict[str, Any]) -> TaskResult:
        """Execute a single task"""
        task_id = task.get("task_id", str(uuid.uuid4()))
        start_time = time.time()
        
        try:
            self.logger.info(f"Starting task {task_id}: {task.get('type', 'unknown')}")
            
            # Execute task based on type
            if task.get("type") == "web_scraping":
                result = await self.execution_engine.execute_web_scraping(task)
            elif task.get("type") == "data_validation":
                result = await self.execution_engine.execute_data_validation(task)
            elif task.get("type") == "api_monitoring":
                result = await self.execution_engine.execute_api_monitoring(task)
            else:
                raise ValueError(f"Unsupported task type: {task.get('type')}")
            
            execution_time = time.time() - start_time
            
            task_result = TaskResult(
                task_id=task_id,
                agent_id=self.agent_id,
                status="completed",
                result=result,
                execution_time=execution_time,
                timestamp=datetime.utcnow()
            )
            
            self.logger.info(f"Task {task_id} completed in {execution_time:.2f}s")
            return task_result
            
        except Exception as e:
            execution_time = time.time() - start_time
            error_msg = str(e)
            self.logger.error(f"Task {task_id} failed: {error_msg}")
            
            return TaskResult(
                task_id=task_id,
                agent_id=self.agent_id,
                status="failed",
                result=None,
                execution_time=execution_time,
                timestamp=datetime.utcnow(),
                error=error_msg
            )
    
    async def submit_result(self, task_result: TaskResult) -> bool:
        """Submit task result to WattCoin network"""
        try:
            result_data = asdict(task_result)
            result_data["timestamp"] = task_result.timestamp.isoformat()
            
            response = await self.wattcoin_api.submit_result(result_data)
            
            if response.get("status") == "success":
                watt_earned = response.get("watt_earned", 0)
                self.logger.info(f"Result submitted for task {task_result.task_id}, earned {watt_earned} WATT")
                return True
            else:
                self.logger.error(f"Result submission failed: {response.get('message', 'Unknown error')}")
                return False
                
        except Exception as e:
            self.logger.error(f"Result submission error: {str(e)}")
            return False
    
    async def heartbeat(self):
        """Send periodic heartbeat to maintain connection"""
        try:
            heartbeat_data = {
                "agent_id": self.agent_id,
                "status": "active" if self.is_running else "inactive",
                "current_tasks": len(self.current_tasks),
                "timestamp": datetime.utcnow().isoformat()
            }
            
            await self.wattcoin_api.send_heartbeat(heartbeat_data)
            
        except Exception as e:
            self.logger.error(f"Heartbeat error: {str(e)}")
    
    async def process_task_batch(self):
        """Process a batch of tasks concurrently"""
        try:
            # Get available tasks
            available_tasks = await self.poll_tasks()
            
            if not available_tasks:
                return
            
            # Create tasks for execution
            task_coroutines = []
            for task in available_tasks:
                task_id = task.get("task_id")
                self.current_tasks[task_id] = task
                task_coroutines.append(self.execute_and_submit_task(task))
            
            # Execute tasks concurrently
            if task_coroutines:
                await asyncio.gather(*task_coroutines, return_exceptions=True)
                
        except Exception as e:
            self.logger.error(f"Batch processing error: {str(e)}")
    
    async def execute_and_submit_task(self, task: Dict[str, Any]):
        """Execute a task and submit its result"""
        task_id = task.get("task_id")
        try:
            # Execute task
            result = await self.execute_task(task)
            
            # Submit result
            await self.submit_result(result)
            
        finally:
            # Clean up
            if task_id in self.current_tasks:
                del self.current_tasks[task_id]
    
    async def start(self):
        """Start the agent main loop"""
        self.logger.info(f"Starting PI Agent {self.agent_id}")
        
        # Register with WattCoin network
        if not await self.register_agent():
            self.logger.error("Failed to register agent, exiting")
            return
        
        self.is_running = True
        heartbeat_interval = self.config.heartbeat_interval
        task_poll_interval = self.config.task_poll_interval
        
        # Schedule periodic tasks
        heartbeat_task = asyncio.create_task(self._periodic_heartbeat(heartbeat_interval))
        main_loop_task = asyncio.create_task(self._main_loop(task_poll_interval))
        
        try:
            await asyncio.gather(heartbeat_task, main_loop_task)
        except asyncio.CancelledError:
            self.logger.info("Agent tasks cancelled")
        except Exception as e:
            self.logger.error(f"Agent error: {str(e)}")
        finally:
            self.is_running = False
            heartbeat_task.cancel()
            main_loop_task.cancel()
    
    async def _periodic_heartbeat(self, interval: int):
        """Send periodic heartbeats"""
        while self.is_running:
            try:
                await self.heartbeat()
                await asyncio.sleep(interval)
            except asyncio.CancelledError:
                break
            except Exception as e:
                self.logger.error(f"Heartbeat loop error: {str(e)}")
                await asyncio.sleep(interval)
    
    async def _main_loop(self, interval: int):
        """Main task processing loop"""
        while self.is_running:
            try:
                await self.process_task_batch()
                await asyncio.sleep(interval)
            except asyncio.CancelledError:
                break
            except Exception as e:
                self.logger.error(f"Main loop error: {str(e)}")
                await asyncio.sleep(interval)
    
    async def stop(self):
        """Stop the agent gracefully"""
        self.logger.info("Stopping PI Agent")
        self.is_running = False
        
        # Wait for current tasks to complete
        while self.current_tasks:
            self.logger.info(f"Waiting for {len(self.current_tasks)} tasks to complete")
            await asyncio.sleep(1)
        
        # Unregister from network
        try:
            await self.wattcoin_api.unregister_agent(self.agent_id)
        except Exception as e:
            self.logger.error(f"Unregister error: {str(e)}")
        
        self.logger.info("PI Agent stopped")