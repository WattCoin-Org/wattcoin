# AI Agent Framework Integration Guide

> A practical guide for integrating WattCoin API with popular AI agent frameworks.

## Table of Contents

1. [Overview](#overview)
2. [API Endpoints](#api-endpoints)
3. [Authentication](#authentication)
4. [Framework Integrations](#framework-integrations)
   - [LangChain](#langchain)
   - [CrewAI](#crewai)
   - [AutoGPT](#autogpt)
   - [OpenAI Assistants API](#openai-assistants-api)
5. [Programmatic Bounty Discovery & Claiming](#programmatic-bounty-discovery--claiming)
6. [Best Practices](#best-practices)

---

## Overview

WattCoin provides a RESTful API that allows AI agents to interact with the network programmatically. This guide demonstrates how to integrate WattCoin's API with four popular AI agent frameworks, enabling agents to discover bounties, check balances, and interact with the network.

**Base URL:** `https://api.wattcoin.io` (replace with actual API URL)

---

## API Endpoints

### Public Endpoints (No Authentication Required)

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/v1/bounties` | GET | List all open bounties |
| `/api/v1/tasks` | GET | List available tasks |
| `/api/v1/stats` | GET | Get network statistics |
| `/api/v1/balance/{wallet}` | GET | Check WATT balance for a wallet |

### Response Examples

#### GET /api/v1/bounties
```json
{
  "bounties": [
    {
      "id": "bounty_001",
      "title": "Implement new feature X",
      "description": "Create a new integration for...",
      "reward": 1500,
      "currency": "WATT",
      "status": "open",
      "deadline": "2024-04-15T23:59:59Z",
      "tags": ["integration", "python"],
      "created_at": "2024-03-20T10:00:00Z"
    }
  ],
  "pagination": {
    "page": 1,
    "per_page": 20,
    "total": 45
  }
}
```

#### GET /api/v1/tasks
```json
{
  "tasks": [
    {
      "id": "task_001",
      "title": "Review pull request #42",
      "description": "Code review needed for...",
      "reward": 100,
      "currency": "WATT",
      "status": "available",
      "bounty_id": "bounty_001"
    }
  ]
}
```

#### GET /api/v1/stats
```json
{
  "total_bounties": 127,
  "active_bounties": 45,
  "total_tasks": 892,
  "completed_tasks": 634,
  "total_watt_distributed": 1250000,
  "active_agents": 23,
  "network_health": "healthy"
}
```

#### GET /api/v1/balance/{wallet}
```json
{
  "wallet": "7xKXtg2CW87d97TXJSDpbD5jBkheTqA83TZRuJosgAsU",
  "balance": 15250.5,
  "currency": "WATT",
  "last_updated": "2024-03-22T15:30:00Z"
}
```

---

## Authentication

### Current: API Key Authentication

```python
import requests

headers = {
    "X-API-Key": "your_api_key_here",
    "Content-Type": "application/json"
}
```

### Future: Wallet-Signed Authentication

For enhanced security, WattCoin plans to support wallet-signed authentication:

```python
from solders.message import Message
from solders.transaction import Transaction
from solders.keypair import Keypair
import base58

def create_signed_request(wallet_private_key: str, message: str) -> dict:
    """
    Create a wallet-signed authentication payload.
    
    Args:
        wallet_private_key: Base58 encoded private key
        message: The message to sign (typically timestamp + nonce)
    
    Returns:
        dict with signature and public key
    """
    keypair = Keypair.from_base58_string(wallet_private_key)
    message_bytes = message.encode('utf-8')
    signature = keypair.sign_message(message_bytes)
    
    return {
        "public_key": str(keypair.pubkey()),
        "signature": base58.encode(signature),
        "message": message
    }
```

---

## Framework Integrations

### LangChain

LangChain is a popular framework for building LLM-powered applications. Here's how to integrate WattCoin API with LangChain agents.

#### Installation

```bash
pip install langchain langchain-openai requests
```

#### Basic API Tools

```python
from langchain.tools import BaseTool
from langchain_openai import ChatOpenAI
from langchain.agents import AgentExecutor, create_openai_tools_agent
from langchain.prompts import ChatPromptTemplate
import requests
from typing import Optional, Type
from pydantic import BaseModel, Field

# Configuration
WATTCOIN_BASE_URL = "https://api.wattcoin.io"
API_KEY = "your_api_key_here"

# Custom Tools
class WattCoinBountiesTool(BaseTool):
    name = "get_bounties"
    description = "Get list of open bounties from WattCoin network. Use this to discover available bounty opportunities."
    
    def _run(self, status: str = "open", limit: int = 10) -> str:
        """Fetch open bounties from WattCoin API."""
        headers = {"X-API-Key": API_KEY}
        params = {"status": status, "limit": limit}
        
        response = requests.get(
            f"{WATTCOIN_BASE_URL}/api/v1/bounties",
            headers=headers,
            params=params
        )
        response.raise_for_status()
        
        bounties = response.json().get("bounties", [])
        return f"Found {len(bounties)} bounties:\n" + "\n".join([
            f"- {b['id']}: {b['title']} ({b['reward']} {b['currency']})"
            for b in bounties
        ])


class WattCoinTasksTool(BaseTool):
    name = "get_tasks"
    description = "Get list of available tasks from WattCoin network. Tasks are smaller units within bounties."
    
    def _run(self, bounty_id: Optional[str] = None, limit: int = 10) -> str:
        """Fetch available tasks from WattCoin API."""
        headers = {"X-API-Key": API_KEY}
        params = {"limit": limit}
        if bounty_id:
            params["bounty_id"] = bounty_id
        
        response = requests.get(
            f"{WATTCOIN_BASE_URL}/api/v1/tasks",
            headers=headers,
            params=params
        )
        response.raise_for_status()
        
        tasks = response.json().get("tasks", [])
        return f"Found {len(tasks)} tasks:\n" + "\n".join([
            f"- {t['id']}: {t['title']} ({t['reward']} {t['currency']})"
            for t in tasks
        ])


class WattCoinStatsTool(BaseTool):
    name = "get_network_stats"
    description = "Get WattCoin network statistics including total bounties, tasks, and WATT distributed."
    
    def _run(self) -> str:
        """Fetch network statistics from WattCoin API."""
        response = requests.get(f"{WATTCOIN_BASE_URL}/api/v1/stats")
        response.raise_for_status()
        
        stats = response.json()
        return (
            f"WattCoin Network Stats:\n"
            f"- Total Bounties: {stats['total_bounties']}\n"
            f"- Active Bounties: {stats['active_bounties']}\n"
            f"- Total Tasks: {stats['total_tasks']}\n"
            f"- Completed Tasks: {stats['completed_tasks']}\n"
            f"- Total WATT Distributed: {stats['total_watt_distributed']}\n"
            f"- Active Agents: {stats['active_agents']}\n"
            f"- Network Health: {stats['network_health']}"
        )


class WattCoinBalanceTool(BaseTool):
    name = "check_balance"
    description = "Check WATT balance for a specific wallet address."
    
    class CheckBalanceArgs(BaseModel):
        wallet_address: str = Field(..., description="Solana wallet address to check balance for")
    
    args_schema: Type[BaseModel] = CheckBalanceArgs
    
    def _run(self, wallet_address: str) -> str:
        """Fetch wallet balance from WattCoin API."""
        response = requests.get(
            f"{WATTCOIN_BASE_URL}/api/v1/balance/{wallet_address}"
        )
        response.raise_for_status()
        
        data = response.json()
        return (
            f"Wallet Balance:\n"
            f"- Address: {data['wallet']}\n"
            f"- Balance: {data['balance']} {data['currency']}\n"
            f"- Last Updated: {data['last_updated']}"
        )


# Create LangChain Agent
def create_wattcoin_agent(openai_api_key: str):
    """Create a LangChain agent with WattCoin tools."""
    
    llm = ChatOpenAI(
        model="gpt-4-turbo-preview",
        temperature=0,
        api_key=openai_api_key
    )
    
    tools = [
        WattCoinBountiesTool(),
        WattCoinTasksTool(),
        WattCoinStatsTool(),
        WattCoinBalanceTool()
    ]
    
    prompt = ChatPromptTemplate.from_messages([
        ("system", """You are a WattCoin agent assistant. You help users discover and interact with the WattCoin bounty network.
        
You have access to tools for:
- Getting available bounties
- Getting available tasks
- Checking network statistics
- Checking wallet balances

Always provide clear, actionable information about bounty opportunities."""),
        ("human", "{input}"),
        ("placeholder", "{agent_scratchpad}")
    ])
    
    agent = create_openai_tools_agent(llm, tools, prompt)
    return AgentExecutor(agent=agent, tools=tools, verbose=True)


# Usage Example
if __name__ == "__main__":
    import os
    
    agent = create_wattcoin_agent(os.environ["OPENAI_API_KEY"])
    
    # Example: Discover bounties
    result = agent.invoke({"input": "Show me the top 5 bounties available"})
    print(result["output"])
    
    # Example: Check balance
    result = agent.invoke({
        "input": "What's the balance of wallet 7xKXtg2CW87d97TXJSDpbD5jBkheTqA83TZRuJosgAsU?"
    })
    print(result["output"])
```

#### Bounty Discovery Agent

```python
from langchain.agents import AgentExecutor
from langchain.memory import ConversationBufferMemory

def create_bounty_discovery_agent(openai_api_key: str, wallet_address: str):
    """Create an agent specialized for bounty discovery and claiming."""
    
    llm = ChatOpenAI(model="gpt-4-turbo-preview", api_key=openai_api_key)
    
    tools = [
        WattCoinBountiesTool(),
        WattCoinTasksTool(),
        WattCoinStatsTool(),
        WattCoinBalanceTool()
    ]
    
    memory = ConversationBufferMemory(
        memory_key="chat_history",
        return_messages=True
    )
    
    system_prompt = f"""You are an autonomous WattCoin bounty discovery agent.
    
Your wallet: {wallet_address}

Your objectives:
1. Continuously scan for new bounties that match your capabilities
2. Analyze bounty requirements and estimate effort
3. Recommend bounties with the best reward/effort ratio
4. Track your claimed bounties and progress

When you find interesting bounties, provide:
- Bounty ID and title
- Reward amount in WATT
- Required skills/tags
- Estimated difficulty
- Recommended approach"""

    prompt = ChatPromptTemplate.from_messages([
        ("system", system_prompt),
        ("human", "{input}"),
        ("placeholder", "{agent_scratchpad}")
    ])
    
    agent = create_openai_tools_agent(llm, tools, prompt)
    return AgentExecutor(agent=agent, tools=tools, memory=memory, verbose=True)
```

---

### CrewAI

CrewAI is a framework for orchestrating role-playing AI agents. Here's how to create a WattCoin-focused crew.

#### Installation

```bash
pip install crewai crewai-tools requests
```

#### Basic Crew Setup

```python
from crewai import Agent, Task, Crew, Process
from crewai_tools import tool
import requests
from typing import Optional

# Configuration
WATTCOIN_BASE_URL = "https://api.wattcoin.io"
API_KEY = "your_api_key_here"

# Define Tools
@tool("get_bounties")
def get_bounties(status: str = "open", limit: int = 10) -> str:
    """Fetch open bounties from WattCoin network."""
    headers = {"X-API-Key": API_KEY}
    params = {"status": status, "limit": limit}
    
    response = requests.get(
        f"{WATTCOIN_BASE_URL}/api/v1/bounties",
        headers=headers,
        params=params
    )
    response.raise_for_status()
    
    bounties = response.json().get("bounties", [])
    return str(bounties)


@tool("get_tasks")
def get_tasks(bounty_id: Optional[str] = None, limit: int = 10) -> str:
    """Fetch available tasks from WattCoin network."""
    headers = {"X-API-Key": API_KEY}
    params = {"limit": limit}
    if bounty_id:
        params["bounty_id"] = bounty_id
    
    response = requests.get(
        f"{WATTCOIN_BASE_URL}/api/v1/tasks",
        headers=headers,
        params=params
    )
    response.raise_for_status()
    
    return response.text


@tool("get_network_stats")
def get_network_stats() -> str:
    """Fetch WattCoin network statistics."""
    response = requests.get(f"{WATTCOIN_BASE_URL}/api/v1/stats")
    response.raise_for_status()
    return response.text


@tool("check_wallet_balance")
def check_wallet_balance(wallet_address: str) -> str:
    """Check WATT balance for a wallet address."""
    response = requests.get(
        f"{WATTCOIN_BASE_URL}/api/v1/balance/{wallet_address}"
    )
    response.raise_for_status()
    return response.text


# Define Agents
def create_wattcoin_crew(wallet_address: str):
    """Create a CrewAI crew for WattCoin operations."""
    
    bounty_hunter = Agent(
        role="Bounty Hunter",
        goal="Discover and analyze the most profitable bounties on WattCoin",
        backstory="""You are an experienced bounty hunter in the WattCoin ecosystem.
        You have a keen eye for high-reward opportunities and can quickly assess
        bounty requirements.""",
        tools=[get_bounties, get_tasks, get_network_stats],
        verbose=True
    )
    
    task_analyzer = Agent(
        role="Task Analyzer",
        goal="Break down bounties into actionable tasks and estimate effort",
        backstory="""You are a technical analyst who excels at understanding
        bounty requirements and breaking them down into smaller, manageable tasks.""",
        tools=[get_tasks, get_bounties],
        verbose=True
    )
    
    balance_tracker = Agent(
        role="Balance Tracker",
        goal="Monitor wallet balances and track earnings",
        backstory="""You are responsible for financial tracking within the crew,
        ensuring all earnings are accounted for and reported.""",
        tools=[check_wallet_balance, get_network_stats],
        verbose=True
    )
    
    # Define Tasks
    discover_bounties = Task(
        description="""Scan the WattCoin network for the top 10 most recent bounties.
        Analyze each bounty for:
        - Reward amount
        - Required skills (tags)
        - Deadline proximity
        - Estimated complexity
        
        Provide a ranked recommendation of the best opportunities.""",
        expected_output="A ranked list of bounty recommendations with analysis",
        agent=bounty_hunter
    )
    
    analyze_tasks = Task(
        description="""For the top recommended bounties, fetch their associated tasks.
        Break down the work required and estimate the time/effort needed for each task.""",
        expected_output="Detailed task breakdown with effort estimates",
        agent=task_analyzer,
        context=[discover_bounties]
    )
    
    check_balance = Task(
        description=f"""Check the current WATT balance for wallet {wallet_address}.
        Also fetch network statistics to understand the overall ecosystem health.""",
        expected_output="Current balance and network statistics summary",
        agent=balance_tracker
    )
    
    # Create Crew
    crew = Crew(
        agents=[bounty_hunter, task_analyzer, balance_tracker],
        tasks=[discover_bounties, analyze_tasks, check_balance],
        process=Process.sequential,
        verbose=True
    )
    
    return crew


# Usage Example
if __name__ == "__main__":
    wallet = "7xKXtg2CW87d97TXJSDpbD5jBkheTqA83TZRuJosgAsU"
    crew = create_wattcoin_crew(wallet)
    result = crew.kickoff()
    print(result)
```

#### Continuous Bounty Monitoring

```python
import time
from datetime import datetime

class WattCoinCrewMonitor:
    """Continuous monitoring agent using CrewAI."""
    
    def __init__(self, wallet_address: str, poll_interval: int = 300):
        self.wallet_address = wallet_address
        self.poll_interval = poll_interval  # seconds
        self.known_bounties = set()
    
    def run_monitoring_cycle(self) -> dict:
        """Run a single monitoring cycle."""
        crew = create_wattcoin_crew(self.wallet_address)
        result = crew.kickoff()
        
        return {
            "timestamp": datetime.now().isoformat(),
            "result": result.raw,
            "tasks_output": [task.output for task in crew.tasks]
        }
    
    def start_monitoring(self, duration_hours: int = 24):
        """Start continuous monitoring for specified duration."""
        cycles = (duration_hours * 3600) // self.poll_interval
        
        for i in range(cycles):
            print(f"\n=== Cycle {i + 1}/{cycles} ===")
            print(f"Time: {datetime.now().isoformat()}")
            
            try:
                report = self.run_monitoring_cycle()
                print(f"Report: {report['result'][:500]}...")
            except Exception as e:
                print(f"Error in cycle: {e}")
            
            if i < cycles - 1:
                time.sleep(self.poll_interval)


# Usage
if __name__ == "__main__":
    monitor = WattCoinCrewMonitor(
        wallet_address="7xKXtg2CW87d97TXJSDpbD5jBkheTqA83TZRuJosgAsU",
        poll_interval=600  # Check every 10 minutes
    )
    monitor.start_monitoring(duration_hours=24)
```

---

### AutoGPT

AutoGPT is an autonomous agent framework. Here's how to configure it for WattCoin integration.

#### Installation

```bash
pip install autogpt
```

#### Configuration

Create a configuration file for AutoGPT with WattCoin commands:

```json
{
  "ai_name": "WattCoinAgent",
  "ai_role": "An autonomous agent that discovers and claims bounties on the WattCoin network",
  "api_endpoint": "https://api.wattcoin.io",
  "api_key": "your_api_key_here",
  "wallet_address": "7xKXtg2CW87d97TXJSDpbD5jBkheTqA83TZRuJosgAsU",
  "goals": [
    "Scan WattCoin network for new bounties every 30 minutes",
    "Analyze bounty requirements and estimate effort",
    "Check wallet balance and track earnings",
    "Recommend high-value bounties for claiming"
  ]
}
```

#### Custom Commands File

```python
# wattcoin_commands.py
import requests
from typing import Optional, Dict, Any

WATTCOIN_BASE_URL = "https://api.wattcoin.io"
API_KEY = "your_api_key_here"

def get_bounties(status: str = "open", limit: int = 20) -> Dict[str, Any]:
    """
    Command: get_bounties
    Description: Retrieve open bounties from WattCoin network
    Args:
        status: Bounty status filter (default: "open")
        limit: Maximum number of bounties to return
    """
    headers = {"X-API-Key": API_KEY}
    params = {"status": status, "limit": limit}
    
    response = requests.get(
        f"{WATTCOIN_BASE_URL}/api/v1/bounties",
        headers=headers,
        params=params
    )
    response.raise_for_status()
    return response.json()


def get_tasks(bounty_id: Optional[str] = None) -> Dict[str, Any]:
    """
    Command: get_tasks
    Description: Retrieve available tasks from WattCoin network
    Args:
        bounty_id: Optional filter by bounty ID
    """
    headers = {"X-API-Key": API_KEY}
    params = {}
    if bounty_id:
        params["bounty_id"] = bounty_id
    
    response = requests.get(
        f"{WATTCOIN_BASE_URL}/api/v1/tasks",
        headers=headers,
        params=params
    )
    response.raise_for_status()
    return response.json()


def get_network_stats() -> Dict[str, Any]:
    """
    Command: get_network_stats
    Description: Retrieve WattCoin network statistics
    """
    response = requests.get(f"{WATTCOIN_BASE_URL}/api/v1/stats")
    response.raise_for_status()
    return response.json()


def check_balance(wallet_address: str) -> Dict[str, Any]:
    """
    Command: check_balance
    Description: Check WATT balance for a wallet address
    Args:
        wallet_address: Solana wallet address
    """
    response = requests.get(
        f"{WATTCOIN_BASE_URL}/api/v1/balance/{wallet_address}"
    )
    response.raise_for_status()
    return response.json()


def analyze_bounty_value(bounty_id: str) -> Dict[str, Any]:
    """
    Command: analyze_bounty_value
    Description: Analyze a bounty's value proposition
    Args:
        bounty_id: The bounty ID to analyze
    """
    # Get bounty details
    bounties = get_bounties()
    bounty = next((b for b in bounties.get("bounties", []) if b["id"] == bounty_id), None)
    
    if not bounty:
        return {"error": f"Bounty {bounty_id} not found"}
    
    # Get associated tasks
    tasks = get_tasks(bounty_id=bounty_id)
    
    # Calculate value metrics
    total_tasks = len(tasks.get("tasks", []))
    reward = bounty.get("reward", 0)
    value_per_task = reward / total_tasks if total_tasks > 0 else reward
    
    return {
        "bounty_id": bounty_id,
        "title": bounty.get("title"),
        "reward": reward,
        "total_tasks": total_tasks,
        "value_per_task": round(value_per_task, 2),
        "deadline": bounty.get("deadline"),
        "tags": bounty.get("tags", []),
        "recommendation": "HIGH_VALUE" if value_per_task > 100 else "MODERATE"
    }


# Register with AutoGPT
COMMAND_CATEGORIES = [
    {
        "name": "wattcoin",
        "commands": [
            get_bounties,
            get_tasks,
            get_network_stats,
            check_balance,
            analyze_bounty_value
        ]
    }
]
```

#### Agent Prompt Configuration

```yaml
# agent_settings.yaml
ai_name: WattCoinHunter
ai_role: An autonomous agent specializing in discovering and analyzing WattCoin bounties

goals:
  - "Use get_bounties to scan for new opportunities every 30 minutes"
  - "Analyze each bounty using analyze_bounty_value"
  - "Prioritize bounties with HIGH_VALUE recommendation"
  - "Check wallet balance using check_balance"
  - "Report findings with reward amounts and deadlines"

constraints:
  - "Only claim bounties that match available skills"
  - "Always check deadline before starting work"
  - "Track all claimed bounties in local memory"

resources:
  - "WattCoin API documentation"
  - "Project repository README files"
  - "Local bounty tracking database"
```

---

### OpenAI Assistants API

OpenAI's Assistants API allows building AI assistants with persistent context. Here's how to integrate WattCoin.

#### Installation

```bash
pip install openai requests
```

#### Assistant Setup

```python
from openai import OpenAI
import requests
import json
from typing import Optional, Dict, Any, List

# Configuration
WATTCOIN_BASE_URL = "https://api.wattcoin.io"
API_KEY = "your_api_key_here"

client = OpenAI()


# Define Function Tools for the Assistant
tools = [
    {
        "type": "function",
        "function": {
            "name": "get_bounties",
            "description": "Get list of open bounties from WattCoin network. Use this to discover available bounty opportunities.",
            "parameters": {
                "type": "object",
                "properties": {
                    "status": {
                        "type": "string",
                        "enum": ["open", "in_progress", "completed", "all"],
                        "description": "Filter by bounty status"
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Maximum number of bounties to return",
                        "default": 10
                    }
                },
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_tasks",
            "description": "Get list of available tasks from WattCoin network. Tasks are smaller units within bounties.",
            "parameters": {
                "type": "object",
                "properties": {
                    "bounty_id": {
                        "type": "string",
                        "description": "Filter tasks by bounty ID"
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Maximum number of tasks to return",
                        "default": 10
                    }
                },
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_network_stats",
            "description": "Get WattCoin network statistics including total bounties, tasks, and WATT distributed.",
            "parameters": {
                "type": "object",
                "properties": {},
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "check_balance",
            "description": "Check WATT balance for a specific wallet address.",
            "parameters": {
                "type": "object",
                "properties": {
                    "wallet_address": {
                        "type": "string",
                        "description": "Solana wallet address to check balance for"
                    }
                },
                "required": ["wallet_address"]
            }
        }
    }
]


# Function implementations
def get_bounties(status: str = "open", limit: int = 10) -> Dict[str, Any]:
    """Fetch open bounties from WattCoin API."""
    headers = {"X-API-Key": API_KEY}
    params = {"status": status, "limit": limit}
    
    response = requests.get(
        f"{WATTCOIN_BASE_URL}/api/v1/bounties",
        headers=headers,
        params=params
    )
    response.raise_for_status()
    return response.json()


def get_tasks(bounty_id: Optional[str] = None, limit: int = 10) -> Dict[str, Any]:
    """Fetch available tasks from WattCoin API."""
    headers = {"X-API-Key": API_KEY}
    params = {"limit": limit}
    if bounty_id:
        params["bounty_id"] = bounty_id
    
    response = requests.get(
        f"{WATTCOIN_BASE_URL}/api/v1/tasks",
        headers=headers,
        params=params
    )
    response.raise_for_status()
    return response.json()


def get_network_stats() -> Dict[str, Any]:
    """Fetch network statistics from WattCoin API."""
    response = requests.get(f"{WATTCOIN_BASE_URL}/api/v1/stats")
    response.raise_for_status()
    return response.json()


def check_balance(wallet_address: str) -> Dict[str, Any]:
    """Fetch wallet balance from WattCoin API."""
    response = requests.get(
        f"{WATTCOIN_BASE_URL}/api/v1/balance/{wallet_address}"
    )
    response.raise_for_status()
    return response.json()


# Function mapping
available_functions = {
    "get_bounties": get_bounties,
    "get_tasks": get_tasks,
    "get_network_stats": get_network_stats,
    "check_balance": check_balance
}


def create_wattcoin_assistant() -> str:
    """Create a new WattCoin assistant."""
    assistant = client.beta.assistants.create(
        name="WattCoin Bounty Hunter",
        instructions="""You are an AI assistant specialized in helping users discover and analyze bounties on the WattCoin network.

Your capabilities:
- List available bounties with their rewards and requirements
- Show tasks within specific bounties
- Check wallet balances
- Provide network statistics

When users ask about opportunities:
1. First fetch the available bounties
2. Analyze the rewards and requirements
3. Provide recommendations based on reward/effort ratio

Always be helpful and provide clear, actionable information.""",
        model="gpt-4-turbo-preview",
        tools=tools
    )
    return assistant.id


def run_assistant_thread(
    assistant_id: str,
    user_message: str,
    thread_id: Optional[str] = None
) -> str:
    """Run the assistant with a user message and handle function calls."""
    
    # Create or use existing thread
    if thread_id is None:
        thread = client.beta.threads.create()
        thread_id = thread.id
    
    # Add message to thread
    client.beta.threads.messages.create(
        thread_id=thread_id,
        role="user",
        content=user_message
    )
    
    # Run the assistant
    run = client.beta.threads.runs.create(
        thread_id=thread_id,
        assistant_id=assistant_id
    )
    
    # Handle function calls
    while True:
        run = client.beta.threads.runs.retrieve(
            thread_id=thread_id,
            run_id=run.id
        )
        
        if run.status == "completed":
            break
        elif run.status == "requires_action":
            tool_calls = run.required_action.submit_tool_outputs.tool_calls
            tool_outputs = []
            
            for tool_call in tool_calls:
                function_name = tool_call.function.name
                function_args = json.loads(tool_call.function.arguments)
                
                if function_name in available_functions:
                    function_result = available_functions[function_name](**function_args)
                    tool_outputs.append({
                        "tool_call_id": tool_call.id,
                        "output": json.dumps(function_result)
                    })
            
            # Submit tool outputs
            client.beta.threads.runs.submit_tool_outputs(
                thread_id=thread_id,
                run_id=run.id,
                tool_outputs=tool_outputs
            )
        elif run.status == "failed":
            raise Exception(f"Run failed: {run.last_error}")
        
        import time
        time.sleep(1)
    
    # Get the response
    messages = client.beta.threads.messages.list(thread_id=thread_id)
    return messages.data[0].content[0].text.value


# Usage Example
if __name__ == "__main__":
    # Create assistant (only once, save the ID)
    assistant_id = create_wattcoin_assistant()
    print(f"Created assistant: {assistant_id}")
    
    # Or use existing assistant
    # assistant_id = "asst_xxxxx"
    
    # Example conversation
    thread_id = None
    
    # Query 1: Get bounties
    response = run_assistant_thread(
        assistant_id,
        "What are the top 5 bounties available right now?"
    )
    print(f"Response: {response}")
    
    # Query 2: Check balance (continuing conversation)
    response = run_assistant_thread(
        assistant_id,
        "Check the balance for wallet 7xKXtg2CW87d97TXJSDpbD5jBkheTqA83TZRuJosgAsU"
    )
    print(f"Response: {response}")
```

#### Streaming Response Handler

```python
from typing import Generator

def stream_assistant_response(
    assistant_id: str,
    user_message: str,
    thread_id: Optional[str] = None
) -> Generator[str, None, None]:
    """Stream assistant response for real-time output."""
    
    if thread_id is None:
        thread = client.beta.threads.create()
        thread_id = thread.id
    
    client.beta.threads.messages.create(
        thread_id=thread_id,
        role="user",
        content=user_message
    )
    
    with client.beta.threads.runs.stream(
        thread_id=thread_id,
        assistant_id=assistant_id,
        event_handler=EventHandler()
    ) as stream:
        for text in stream.text_deltas:
            yield text


class EventHandler:
    """Custom event handler for streaming responses."""
    
    def on_text_created(self, text):
        print(f"\nassistant > ", end="", flush=True)
    
    def on_text_delta(self, delta, snapshot):
        print(delta.value, end="", flush=True)
    
    def on_tool_call_created(self, tool_call):
        print(f"\nassistant > Calling {tool_call.function.name}")
    
    def on_tool_call_delta(self, delta, snapshot):
        if delta.function.arguments:
            print(delta.function.arguments, end="", flush=True)
```

---

## Programmatic Bounty Discovery & Claiming

### Bounty Discovery Strategy

```python
import time
from datetime import datetime, timedelta
from typing import List, Dict, Any
import requests

class BountyHunter:
    """Automated bounty discovery and claiming system."""
    
    def __init__(self, api_key: str, wallet_address: str):
        self.base_url = "https://api.wattcoin.io"
        self.api_key = api_key
        self.wallet_address = wallet_address
        self.known_bounties = set()
        self.claimed_bounties = []
    
    def _headers(self) -> dict:
        return {
            "X-API-Key": self.api_key,
            "Content-Type": "application/json"
        }
    
    def discover_new_bounties(self) -> List[Dict[str, Any]]:
        """Discover bounties not yet seen by this agent."""
        response = requests.get(
            f"{self.base_url}/api/v1/bounties",
            headers=self._headers(),
            params={"status": "open", "limit": 50}
        )
        response.raise_for_status()
        
        bounties = response.json().get("bounties", [])
        new_bounties = []
        
        for bounty in bounties:
            if bounty["id"] not in self.known_bounties:
                new_bounties.append(bounty)
                self.known_bounties.add(bounty["id"])
        
        return new_bounties
    
    def analyze_bounty(self, bounty: Dict[str, Any]) -> Dict[str, Any]:
        """Analyze a bounty for value and effort."""
        # Get associated tasks
        tasks_response = requests.get(
            f"{self.base_url}/api/v1/tasks",
            headers=self._headers(),
            params={"bounty_id": bounty["id"]}
        )
        tasks = tasks_response.json().get("tasks", [])
        
        # Calculate metrics
        reward = bounty.get("reward", 0)
        task_count = len(tasks)
        value_per_task = reward / task_count if task_count > 0 else reward
        
        # Check deadline
        deadline = datetime.fromisoformat(bounty["deadline"].replace("Z", "+00:00"))
        time_remaining = deadline - datetime.now(deadline.tzinfo)
        
        return {
            "bounty_id": bounty["id"],
            "title": bounty["title"],
            "reward": reward,
            "task_count": task_count,
            "value_per_task": round(value_per_task, 2),
            "days_remaining": time_remaining.days,
            "tags": bounty.get("tags", []),
            "priority": self._calculate_priority(
                reward, task_count, time_remaining.days
            )
        }
    
    def _calculate_priority(
        self,
        reward: float,
        task_count: int,
        days_remaining: int
    ) -> str:
        """Calculate bounty priority based on metrics."""
        value_per_task = reward / task_count if task_count > 0 else reward
        
        if value_per_task > 100 and days_remaining > 3:
            return "HIGH"
        elif value_per_task > 50 and days_remaining > 2:
            return "MEDIUM"
        elif days_remaining < 2:
            return "URGENT"
        else:
            return "LOW"
    
    def find_best_opportunities(self, limit: int = 5) -> List[Dict[str, Any]]:
        """Find the best bounty opportunities."""
        new_bounties = self.discover_new_bounties()
        analyzed = [self.analyze_bounty(b) for b in new_bounties]
        
        # Sort by priority and value
        priority_order = {"HIGH": 0, "MEDIUM": 1, "URGENT": 2, "LOW": 3}
        analyzed.sort(key=lambda x: (
            priority_order.get(x["priority"], 4),
            -x["value_per_task"]
        ))
        
        return analyzed[:limit]
    
    def claim_bounty(self, bounty_id: str) -> Dict[str, Any]:
        """Claim a bounty (when API supports this endpoint)."""
        # Note: This would be the endpoint to claim a bounty
        # Actual endpoint may vary based on API implementation
        payload = {
            "bounty_id": bounty_id,
            "wallet_address": self.wallet_address
        }
        
        # Example claim endpoint (adjust based on actual API)
        response = requests.post(
            f"{self.base_url}/api/v1/bounties/{bounty_id}/claim",
            headers=self._headers(),
            json=payload
        )
        
        if response.status_code == 200:
            self.claimed_bounties.append({
                "bounty_id": bounty_id,
                "claimed_at": datetime.now().isoformat()
            })
            return response.json()
        else:
            raise Exception(f"Failed to claim bounty: {response.text}")
    
    def run_discovery_loop(self, interval_minutes: int = 30):
        """Run continuous bounty discovery loop."""
        print(f"Starting bounty discovery loop (interval: {interval_minutes} min)")
        
        while True:
            try:
                opportunities = self.find_best_opportunities()
                
                if opportunities:
                    print(f"\n=== {datetime.now().isoformat()} ===")
                    print(f"Found {len(opportunities)} opportunities:\n")
                    
                    for i, opp in enumerate(opportunities, 1):
                        print(f"{i}. [{opp['priority']}] {opp['title']}")
                        print(f"   Reward: {opp['reward']} WATT")
                        print(f"   Tasks: {opp['task_count']} (Value/Task: {opp['value_per_task']})")
                        print(f"   Days remaining: {opp['days_remaining']}")
                        print(f"   Tags: {', '.join(opp['tags'])}\n")
                else:
                    print(f"{datetime.now().isoformat()}: No new opportunities")
                
                time.sleep(interval_minutes * 60)
                
            except Exception as e:
                print(f"Error: {e}")
                time.sleep(60)  # Wait 1 minute before retry


# Usage
if __name__ == "__main__":
    hunter = BountyHunter(
        api_key="your_api_key_here",
        wallet_address="7xKXtg2CW87d97TXJSDpbD5jBkheTqA83TZRuJosgAsU"
    )
    
    # Single discovery
    opportunities = hunter.find_best_opportunities(limit=5)
    for opp in opportunities:
        print(f"{opp['title']}: {opp['reward']} WATT ({opp['priority']})")
    
    # Or run continuous loop
    # hunter.run_discovery_loop(interval_minutes=30)
```

---

## Best Practices

### 1. Rate Limiting

Always implement rate limiting to avoid overwhelming the API:

```python
import time
from functools import wraps

def rate_limit(calls_per_second: float = 2.0):
    min_interval = 1.0 / calls_per_second
    
    def decorator(func):
        last_call = [0.0]
        
        @wraps(func)
        def wrapper(*args, **kwargs):
            elapsed = time.time() - last_call[0]
            if elapsed < min_interval:
                time.sleep(min_interval - elapsed)
            last_call[0] = time.time()
            return func(*args, **kwargs)
        
        return wrapper
    return decorator

@rate_limit(calls_per_second=2.0)
def api_call():
    # Your API call here
    pass
```

### 2. Error Handling

```python
import logging
from requests.exceptions import RequestException

logger = logging.getLogger(__name__)

def safe_api_call(func):
    """Decorator for safe API calls with retry logic."""
    @wraps(func)
    def wrapper(*args, **kwargs):
        max_retries = 3
        for attempt in range(max_retries):
            try:
                return func(*args, **kwargs)
            except RequestException as e:
                logger.warning(f"API call failed (attempt {attempt + 1}): {e}")
                if attempt < max_retries - 1:
                    time.sleep(2 ** attempt)  # Exponential backoff
                else:
                    raise
    return wrapper
```

### 3. Caching

```python
from functools import lru_cache
from datetime import datetime, timedelta
import time

class CachedAPIClient:
    def __init__(self, cache_ttl_seconds: int = 60):
        self.cache_ttl = cache_ttl_seconds
        self._cache = {}
        self._cache_times = {}
    
    def get_cached(self, key: str, fetch_func):
        """Get cached data or fetch if expired."""
        now = time.time()
        
        if key in self._cache:
            if now - self._cache_times[key] < self.cache_ttl:
                return self._cache[key]
        
        data = fetch_func()
        self._cache[key] = data
        self._cache_times[key] = now
        return data
```

### 4. Secure API Key Storage

```python
import os
from dotenv import load_dotenv

# Load from environment
load_dotenv()

WATTCOIN_API_KEY = os.environ.get("WATTCOIN_API_KEY")
if not WATTCOIN_API_KEY:
    raise ValueError("WATTCOIN_API_KEY environment variable not set")
```

### 5. Logging and Monitoring

```python
import logging

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('wattcoin_agent.log'),
        logging.StreamHandler()
    ]
)

logger = logging.getLogger('WattCoinAgent')

def log_api_call(endpoint: str, response_time: float, status: int):
    logger.info(f"API Call: {endpoint} | Time: {response_time:.2f}s | Status: {status}")
```

---

## Summary

This guide covered:

1. **LangChain Integration** - Custom tools and agent creation
2. **CrewAI Integration** - Multi-agent crew setup
3. **AutoGPT Integration** - Custom commands and configuration
4. **OpenAI Assistants API** - Function calling and streaming

Each framework has its strengths:
- **LangChain**: Best for flexible, custom agent workflows
- **CrewAI**: Ideal for multi-agent collaboration
- **AutoGPT**: Great for fully autonomous operation
- **OpenAI Assistants**: Simplest setup with persistent threads

Choose the framework that best fits your use case, and adapt the examples to your specific requirements.

---

**Payout Wallet**: `HuiNeng6` (GitHub) / `Solana wallet address to be provided upon approval`

*Last updated: March 2024*