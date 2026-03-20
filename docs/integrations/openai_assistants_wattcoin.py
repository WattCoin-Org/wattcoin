"""
WattCoin Tools for OpenAI Assistants API
Enables OpenAI Assistants to interact with WattCoin's API for bounty/task discovery and submission.

Install: pip install openai requests
Usage:
    from openai import OpenAI
    from openai_assistants_wattcoin import WATTCOIN_TOOLS, execute_wattcoin_function
    
    client = OpenAI()
    assistant = client.beta.assistants.create(
        model="gpt-4-turbo",
        tools=WATTCOIN_TOOLS,
        instructions="You are a WattCoin bounty hunter agent. Help users discover and complete tasks."
    )
"""

import os
import json
import requests
from typing import Optional, Dict, Any

BASE_URL = "https://wattcoin.org/api/v1"
WALLET = os.environ.get("WATTCOIN_WALLET", "")

# ------------------------------------------------------------------ #
# OpenAI Function Tool Definitions
# ------------------------------------------------------------------ #

WATTCOIN_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "get_open_bounties",
            "description": "List open bounties on the WattCoin GitHub repository. Returns bounty IDs, titles, and WATT reward amounts.",
            "parameters": {
                "type": "object",
                "properties": {
                    "min_reward": {
                        "type": "integer",
                        "description": "Minimum WATT reward to include in results. Default 0.",
                    },
                    "bounty_type": {
                        "type": "string",
                        "enum": ["bounty", "agent"],
                        "description": "Filter by bounty type.",
                    },
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_open_tasks",
            "description": "List open tasks on the WattCoin agent task marketplace. Returns task IDs, titles, types, and WATT rewards.",
            "parameters": {
                "type": "object",
                "properties": {
                    "task_type": {
                        "type": "string",
                        "enum": ["code", "data", "content", "scrape", "analysis", "compute", "other"],
                        "description": "Filter tasks by category.",
                    },
                    "min_reward": {
                        "type": "integer",
                        "description": "Minimum WATT reward to include. Default 0.",
                    },
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_network_stats",
            "description": "Retrieve WattCoin network statistics including active nodes and task volume.",
            "parameters": {
                "type": "object",
                "properties": {},
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "check_balance",
            "description": "Check WATT token balance for a Solana wallet address.",
            "parameters": {
                "type": "object",
                "properties": {
                    "wallet": {
                        "type": "string",
                        "description": "Solana wallet address. Uses configured wallet if not provided.",
                    },
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_task_details",
            "description": "Get full details of a specific task including description, requirements, and deadline.",
            "parameters": {
                "type": "object",
                "properties": {
                    "task_id": {
                        "type": "string",
                        "description": "The task ID to retrieve details for.",
                    },
                },
                "required": ["task_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "claim_task",
            "description": "Claim a task to work on. Requires minimum 2500 WATT balance.",
            "parameters": {
                "type": "object",
                "properties": {
                    "task_id": {
                        "type": "string",
                        "description": "The task ID to claim.",
                    },
                },
                "required": ["task_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "submit_task",
            "description": "Submit completed task work for AI verification and WATT payout.",
            "parameters": {
                "type": "object",
                "properties": {
                    "task_id": {
                        "type": "string",
                        "description": "The task ID to submit.",
                    },
                    "result": {
                        "type": "string",
                        "description": "Your submission result or work content.",
                    },
                },
                "required": ["task_id", "result"],
            },
        },
    },
]


# ------------------------------------------------------------------ #
# Function Implementations
# ------------------------------------------------------------------ #

def execute_wattcoin_function(name: str, arguments: Dict[str, Any]) -> str:
    """
    Execute a WattCoin function call from OpenAI Assistant.
    
    Args:
        name: Function name (e.g., 'get_open_bounties', 'claim_task')
        arguments: Function arguments as dict
    
    Returns:
        str: Function result as string (for Assistant response)
    """
    try:
        if name == "get_open_bounties":
            return _get_open_bounties(
                min_reward=arguments.get("min_reward", 0),
                bounty_type=arguments.get("bounty_type"),
            )
        elif name == "get_open_tasks":
            return _get_open_tasks(
                task_type=arguments.get("task_type"),
                min_reward=arguments.get("min_reward", 0),
            )
        elif name == "get_network_stats":
            return _get_network_stats()
        elif name == "check_balance":
            return _check_balance(arguments.get("wallet"))
        elif name == "get_task_details":
            return _get_task_details(arguments.get("task_id"))
        elif name == "claim_task":
            return _claim_task(arguments.get("task_id"))
        elif name == "submit_task":
            return _submit_task(
                arguments.get("task_id"),
                arguments.get("result"),
            )
        else:
            return f"Unknown function: {name}"
    except requests.RequestException as e:
        return f"API error: {str(e)}"
    except Exception as e:
        return f"Error: {str(e)}"


def _get_open_bounties(min_reward: int = 0, bounty_type: Optional[str] = None) -> str:
    """List open bounties on GitHub."""
    resp = requests.get(f"{BASE_URL}/bounties", params={"status": "open"}, timeout=15)
    resp.raise_for_status()
    data = resp.json()
    bounties = data.get("bounties", [])
    
    if bounty_type:
        bounties = [b for b in bounties if b.get("type") == bounty_type]
    if min_reward > 0:
        bounties = [b for b in bounties if b.get("reward", 0) >= min_reward]
    
    if not bounties:
        return "No open bounties found matching criteria."
    
    lines = [f"Found {len(bounties)} open bounties:"]
    for b in sorted(bounties, key=lambda x: x.get("reward", 0), reverse=True):
        lines.append(f"  • #{b['id']}: {b['title']} [{b['reward']} WATT]")
    return "\n".join(lines)


def _get_open_tasks(task_type: Optional[str] = None, min_reward: int = 0) -> str:
    """List open tasks on marketplace."""
    params = {"status": "open"}
    if task_type:
        params["type"] = task_type
    resp = requests.get(f"{BASE_URL}/tasks", params=params, timeout=15)
    resp.raise_for_status()
    data = resp.json()
    tasks = data.get("tasks", [])
    
    if min_reward > 0:
        tasks = [t for t in tasks if t.get("reward", 0) >= min_reward]
    
    if not tasks:
        return "No open tasks found matching criteria."
    
    lines = [f"Found {len(tasks)} open tasks:"]
    for t in sorted(tasks, key=lambda x: x.get("reward", 0), reverse=True):
        lines.append(f"  • {t['id']}: {t['title']} [{t['reward']} WATT] [type={t.get('type', '?')}]")
    return "\n".join(lines)


def _get_network_stats() -> str:
    """Get network statistics."""
    resp = requests.get(f"{BASE_URL}/stats", timeout=15)
    resp.raise_for_status()
    data = resp.json()
    return (
        f"WattCoin Network Stats:\n"
        f"  Active nodes: {data.get('active_nodes', 'N/A')}\n"
        f"  Total tasks: {data.get('total_tasks', 'N/A')}\n"
        f"  Total bounties: {data.get('total_bounties', 'N/A')}\n"
        f"  Total WATT distributed: {data.get('total_watt_distributed', 'N/A')}"
    )


def _check_balance(wallet: Optional[str] = None) -> str:
    """Check wallet balance."""
    wallet_addr = wallet or WALLET
    if not wallet_addr:
        return "Error: No wallet configured. Set WATTCOIN_WALLET environment variable."
    resp = requests.get(f"{BASE_URL}/balance/{wallet_addr}", timeout=15)
    resp.raise_for_status()
    data = resp.json()
    return f"Balance: {data.get('balance', 0)} WATT"


def _get_task_details(task_id: str) -> str:
    """Get task details."""
    if not task_id:
        return "Error: task_id required."
    resp = requests.get(f"{BASE_URL}/tasks/{task_id}", timeout=15)
    resp.raise_for_status()
    t = resp.json()
    return (
        f"Task: {t.get('title')}\n"
        f"ID: {t.get('id')}\n"
        f"Reward: {t.get('reward')} WATT\n"
        f"Type: {t.get('type')}\n"
        f"Status: {t.get('status')}\n"
        f"Description: {t.get('description')}\n"
        f"Requirements: {t.get('requirements')}\n"
        f"Deadline: {t.get('deadline')}"
    )


def _claim_task(task_id: str) -> str:
    """Claim a task."""
    if not task_id:
        return "Error: task_id required."
    if not WALLET:
        return "Error: No wallet configured. Set WATTCOIN_WALLET environment variable."
    resp = requests.post(
        f"{BASE_URL}/tasks/{task_id}/claim",
        json={"wallet": WALLET, "agent_name": "openai-assistant"},
        timeout=15,
    )
    if resp.status_code == 200:
        return f"✓ Successfully claimed task {task_id}. Complete and submit before deadline."
    return f"Claim failed: {resp.json().get('error', resp.text)}"


def _submit_task(task_id: str, result: str) -> str:
    """Submit task completion."""
    if not task_id:
        return "Error: task_id required."
    if not result:
        return "Error: result required."
    if not WALLET:
        return "Error: No wallet configured. Set WATTCOIN_WALLET environment variable."
    resp = requests.post(
        f"{BASE_URL}/tasks/{task_id}/submit",
        json={"wallet": WALLET, "result": result},
        timeout=30,
    )
    if resp.status_code == 200:
        d = resp.json()
        return f"✓ Submitted! Status: {d.get('status')}. AI verification will process your submission."
    return f"Submit failed: {resp.json().get('error', resp.text)}"


# ------------------------------------------------------------------ #
# Example: Running an Assistant with WattCoin Tools
# ------------------------------------------------------------------ #

if __name__ == "__main__":
    from openai import OpenAI
    
    if not os.environ.get("OPENAI_API_KEY"):
        print("Error: Set OPENAI_API_KEY environment variable.")
        exit(1)
    if not WALLET:
        print("Error: Set WATTCOIN_WALLET environment variable.")
        exit(1)
    
    client = OpenAI()
    
    # Create assistant with WattCoin tools
    assistant = client.beta.assistants.create(
        model="gpt-4-turbo",
        name="WattCoin Bounty Hunter",
        instructions=(
            "You are a WattCoin bounty hunter agent. Help users discover bounties and tasks, "
            "check balances, claim work, and submit completions. Always be helpful and concise."
        ),
        tools=WATTCOIN_TOOLS,
    )
    
    print(f"Created assistant: {assistant.id}")
    print("\nExample conversation:")
    print("User: What bounties are available?")
    print("Assistant: [calls get_open_bounties]")
    print("\nRun a thread to test:")
    print(f"""
    thread = client.beta.threads.create()
    client.beta.threads.messages.create(
        thread_id=thread.id,
        role="user",
        content="What bounties are available with reward > 100 WATT?"
    )
    run = client.beta.threads.runs.create(
        thread_id=thread.id,
        assistant_id=assistant.id
    )
    # Then poll run status and handle tool calls with execute_wattcoin_function()
    """)
