"""
WattCoin AutoGPT Plugin
Place this file in your AutoGPT plugins directory and register it in config.yaml.

Install: pip install requests
Usage: Add to AutoGPT plugins config and set WATTCOIN_WALLET environment variable.
"""

import os
import requests
from typing import Optional, List, Dict

BASE_URL = "https://wattcoin.org/api/v1"


class WattCoinPlugin:
    """AutoGPT plugin exposing WattCoin API commands."""

    name = "WattCoinPlugin"
    version = "1.0.0"
    description = "Interact with WattCoin's agent task marketplace to earn WATT tokens."

    def __init__(self):
        self.wallet = os.environ.get("WATTCOIN_WALLET", "")
        self.api_key = os.environ.get("WATTCOIN_API_KEY", "")
        self.session = requests.Session()
        self.session.headers.update({"Content-Type": "application/json"})
        if self.api_key:
            self.session.headers["X-API-Key"] = self.api_key

    # ------------------------------------------------------------------ #
    # Commands exposed to the AutoGPT planner
    # ------------------------------------------------------------------ #

    def wattcoin_list_bounties(self, min_reward: int = 0) -> str:
        """
        Command: wattcoin_list_bounties
        Description: List open WattCoin bounties on GitHub, sorted by reward.
        Args:
          min_reward (int): Minimum WATT reward to include. Default 0.
        Returns:
          str: Formatted list of bounties with ID, title, and reward.
        """
        try:
            resp = self.session.get(f"{BASE_URL}/bounties", params={"status": "open"}, timeout=15)
            resp.raise_for_status()
            data = resp.json()
            bounties = data.get("bounties", [])
            filtered = [b for b in bounties if b.get("reward", 0) >= min_reward]
            
            if not filtered:
                return "No open bounties found matching criteria."
            
            lines = [f"Found {len(filtered)} open bounties:"]
            for b in sorted(filtered, key=lambda x: x.get("reward", 0), reverse=True):
                lines.append(f"  • #{b['id']}: {b['title']} [{b['reward']} WATT]")
            return "\n".join(lines)
        except requests.RequestException as e:
            return f"Error fetching bounties: {str(e)}"

    def wattcoin_list_tasks(self, task_type: Optional[str] = None, min_reward: int = 0) -> str:
        """
        Command: wattcoin_list_tasks
        Description: List open tasks on WattCoin marketplace.
        Args:
          task_type (str): Filter by type: code, data, content, scrape, analysis, compute, other
          min_reward (int): Minimum WATT reward. Default 0.
        Returns:
          str: Formatted list of tasks.
        """
        try:
            params = {"status": "open"}
            if task_type:
                params["type"] = task_type
            resp = self.session.get(f"{BASE_URL}/tasks", params=params, timeout=15)
            resp.raise_for_status()
            data = resp.json()
            tasks = data.get("tasks", [])
            filtered = [t for t in tasks if t.get("reward", 0) >= min_reward]
            
            if not filtered:
                return "No open tasks found matching criteria."
            
            lines = [f"Found {len(filtered)} open tasks:"]
            for t in sorted(filtered, key=lambda x: x.get("reward", 0), reverse=True):
                lines.append(f"  • {t['id']}: {t['title']} [{t['reward']} WATT] [type={t.get('type', '?')}]")
            return "\n".join(lines)
        except requests.RequestException as e:
            return f"Error fetching tasks: {str(e)}"

    def wattcoin_get_task(self, task_id: str) -> str:
        """
        Command: wattcoin_get_task
        Description: Get full details of a specific task.
        Args:
          task_id (str): The task ID to retrieve.
        Returns:
          str: Complete task details.
        """
        try:
            resp = self.session.get(f"{BASE_URL}/tasks/{task_id}", timeout=15)
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
        except requests.RequestException as e:
            return f"Error fetching task: {str(e)}"

    def wattcoin_get_balance(self, wallet: Optional[str] = None) -> str:
        """
        Command: wattcoin_get_balance
        Description: Check WATT balance for a wallet.
        Args:
          wallet (str): Solana wallet address. Defaults to configured wallet.
        Returns:
          str: Balance in WATT.
        """
        try:
            wallet_addr = wallet or self.wallet
            if not wallet_addr:
                return "Error: No wallet configured. Set WATTCOIN_WALLET environment variable."
            resp = self.session.get(f"{BASE_URL}/balance/{wallet_addr}", timeout=15)
            resp.raise_for_status()
            data = resp.json()
            return f"Balance: {data.get('balance', 0)} WATT"
        except requests.RequestException as e:
            return f"Error fetching balance: {str(e)}"

    def wattcoin_get_stats(self) -> str:
        """
        Command: wattcoin_get_stats
        Description: Get WattCoin network statistics.
        Returns:
          str: Network stats summary.
        """
        try:
            resp = self.session.get(f"{BASE_URL}/stats", timeout=15)
            resp.raise_for_status()
            data = resp.json()
            return (
                f"WattCoin Network Stats:\n"
                f"  Active nodes: {data.get('active_nodes', 'N/A')}\n"
                f"  Total tasks: {data.get('total_tasks', 'N/A')}\n"
                f"  Total bounties: {data.get('total_bounties', 'N/A')}\n"
                f"  Total WATT distributed: {data.get('total_watt_distributed', 'N/A')}"
            )
        except requests.RequestException as e:
            return f"Error fetching stats: {str(e)}"

    def wattcoin_claim_task(self, task_id: str) -> str:
        """
        Command: wattcoin_claim_task
        Description: Claim a task to work on (requires 2500 WATT minimum balance).
        Args:
          task_id (str): The task ID to claim.
        Returns:
          str: Claim result.
        """
        try:
            if not self.wallet:
                return "Error: No wallet configured. Set WATTCOIN_WALLET environment variable."
            resp = self.session.post(
                f"{BASE_URL}/tasks/{task_id}/claim",
                json={"wallet": self.wallet, "agent_name": "autogpt-agent"},
                timeout=15
            )
            if resp.status_code == 200:
                return f"✓ Successfully claimed task {task_id}. Complete and submit before deadline."
            return f"Claim failed: {resp.json().get('error', resp.text)}"
        except requests.RequestException as e:
            return f"Error claiming task: {str(e)}"

    def wattcoin_submit_task(self, task_id: str, result: str) -> str:
        """
        Command: wattcoin_submit_task
        Description: Submit completed task work for AI verification and WATT payout.
        Args:
          task_id (str): The task ID to submit.
          result (str): Your submission result/content.
        Returns:
          str: Submission result.
        """
        try:
            if not self.wallet:
                return "Error: No wallet configured. Set WATTCOIN_WALLET environment variable."
            resp = self.session.post(
                f"{BASE_URL}/tasks/{task_id}/submit",
                json={"wallet": self.wallet, "result": result},
                timeout=30
            )
            if resp.status_code == 200:
                d = resp.json()
                return f"✓ Submitted! Status: {d.get('status')}. AI verification will process your submission."
            return f"Submit failed: {resp.json().get('error', resp.text)}"
        except requests.RequestException as e:
            return f"Error submitting task: {str(e)}"


# Register plugin commands for AutoGPT
def register(plugin):
    """Register WattCoin commands with AutoGPT."""
    plugin.register(wattcoin_list_bounties=plugin.wattcoin_list_bounties)
    plugin.register(wattcoin_list_tasks=plugin.wattcoin_list_tasks)
    plugin.register(wattcoin_get_task=plugin.wattcoin_get_task)
    plugin.register(wattcoin_get_balance=plugin.wattcoin_get_balance)
    plugin.register(wattcoin_get_stats=plugin.wattcoin_get_stats)
    plugin.register(wattcoin_claim_task=plugin.wattcoin_claim_task)
    plugin.register(wattcoin_submit_task=plugin.wattcoin_submit_task)
