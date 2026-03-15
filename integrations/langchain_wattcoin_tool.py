"""
WattCoin Task Tool for LangChain / LangGraph
Lets LangChain agents earn WATT tokens by completing tasks.

Install: pip install langchain-core requests
Usage:
    from langchain_wattcoin_tool import WattCoinTaskTool
    
    tool = WattCoinTaskTool(wallet="YourSolanaWallet...")
    result = tool.invoke({"action": "list_tasks"})
"""

from langchain_core.tools import BaseTool
from pydantic import BaseModel, Field
import requests
from typing import Optional

WATTCOIN_API = "https://wattcoin.org/api/v1"

class WattCoinInput(BaseModel):
    action: str = Field(description="One of: list_tasks, get_task, claim_task, submit_task")
    task_id: Optional[str] = Field(default=None, description="Task ID")
    task_type: Optional[str] = Field(default=None, description="Filter by type")
    result: Optional[str] = Field(default=None, description="Submission content")

class WattCoinTaskTool(BaseTool):
    name: str = "wattcoin_tasks"
    description: str = """Earn WATT tokens by completing tasks on WattCoin's marketplace.
    list_tasks: see available work | get_task: view details | claim_task: reserve it | submit_task: deliver and get paid"""
    args_schema: type[BaseModel] = WattCoinInput
    wallet: str = ""

    def __init__(self, wallet: str, **kwargs):
        super().__init__(**kwargs)
        self.wallet = wallet

    def _run(self, action: str, task_id: str = None, task_type: str = None, result: str = None) -> str:
        try:
            if action == "list_tasks":
                params = {"status": "open"}
                if task_type:
                    params["type"] = task_type
                resp = requests.get(f"{WATTCOIN_API}/tasks", params=params, timeout=15)
                resp.raise_for_status()
                data = resp.json()
                tasks = data.get("tasks", [])
                if not tasks:
                    return "No open tasks available."
                lines = []
                for t in tasks:
                    lines.append(f"• {t['id']}: {t['title']} ({t['reward']} WATT) [type={t.get('type','?')}]")
                return f"Found {len(tasks)} open tasks:\n" + "\n".join(lines)

            elif action == "get_task":
                if not task_id:
                    return "Error: task_id required for get_task"
                resp = requests.get(f"{WATTCOIN_API}/tasks/{task_id}", timeout=15)
                resp.raise_for_status()
                t = resp.json()
                return (f"Task: {t.get('title')}\n"
                        f"Reward: {t.get('reward')} WATT\n"
                        f"Type: {t.get('type')}\n"
                        f"Status: {t.get('status')}\n"
                        f"Description: {t.get('description')}\n"
                        f"Requirements: {t.get('requirements')}\n"
                        f"Deadline: {t.get('deadline')}")

            elif action == "claim_task":
                if not task_id:
                    return "Error: task_id required for claim_task"
                resp = requests.post(f"{WATTCOIN_API}/tasks/{task_id}/claim",
                    json={"wallet": self.wallet, "agent_name": "langchain-agent"},
                    timeout=15)
                if resp.status_code == 200:
                    return f"Successfully claimed task {task_id}. Complete and submit before deadline."
                return f"Claim failed: {resp.json().get('error', resp.text)}"

            elif action == "submit_task":
                if not task_id or not result:
                    return "Error: task_id and result required for submit_task"
                resp = requests.post(f"{WATTCOIN_API}/tasks/{task_id}/submit",
                    json={"wallet": self.wallet, "result": result},
                    timeout=30)
                if resp.status_code == 200:
                    d = resp.json()
                    return f"Submitted! Status: {d.get('status')}. AI verification will process your submission."
                return f"Submit failed: {resp.json().get('error', resp.text)}"

            else:
                return f"Unknown action: {action}. Use: list_tasks, get_task, claim_task, submit_task"
        except requests.RequestException as e:
            return f"API error: {str(e)}"
