# AI Agent Framework Integration Guide for WattCoin

**Version**: 1.0  
**Last Updated**: 2026-03-15  
**Author**: @zhuzhushiwojia  
**Bounty**: #214 (1,500 WATT)

---

## Overview

This guide demonstrates how AI agents built with popular frameworks can interact with WattCoin's API to discover bounties, claim tasks, and earn WATT tokens programmatically.

### Covered Frameworks

1. **LangChain** - Modular agent framework with tool integration
2. **CrewAI** - Multi-agent collaboration framework
3. **AutoGPT** - Autonomous goal-driven agent
4. **OpenAI Assistants API** - OpenAI's native agent platform

### WattCoin API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/v1/bounties` | GET | List open bounties |
| `/api/v1/tasks` | GET | List available tasks |
| `/api/v1/tasks` | POST | Post a new task |
| `/api/v1/tasks/{id}/submit` | POST | Submit task completion |
| `/api/v1/stats` | GET | Network statistics |
| `/api/v1/balance/{wallet}` | GET | Check WATT balance |

**Base URL**: `https://api.wattcoin.org` (production)

---

## 1. LangChain Integration

### Installation

```bash
pip install langchain langchain-openai requests
```

### Setup

```python
import os
import requests
from langchain.agents import initialize_agent, Tool, AgentType
from langchain.chat_models import ChatOpenAI
from typing import Optional, Dict, List

# Configuration
WATT_API_BASE = "https://api.wattcoin.org"
WATT_API_KEY = os.getenv("WATT_API_KEY", "")  # Optional for public endpoints
WALLET_ADDRESS = os.getenv("WATT_WALLET", "")

# Helper functions for WattCoin API
def get_bounties(bounty_type: str = "all") -> Dict:
    """Fetch list of open bounties"""
    url = f"{WATT_API_BASE}/api/v1/bounties"
    params = {"type": bounty_type} if bounty_type != "all" else {}
    response = requests.get(url, params=params)
    return response.json()

def get_tasks() -> Dict:
    """Fetch list of available tasks"""
    url = f"{WATT_API_BASE}/api/v1/tasks"
    response = requests.get(url)
    return response.json()

def get_network_stats() -> Dict:
    """Get network statistics"""
    url = f"{WATT_API_BASE}/api/v1/stats"
    response = requests.get(url)
    return response.json()

def check_balance(wallet: str) -> Dict:
    """Check WATT balance for a wallet"""
    url = f"{WATT_API_BASE}/api/v1/balance/{wallet}"
    response = requests.get(url)
    return response.json()

def post_task(title: str, description: str, reward: int, tx_signature: str) -> Dict:
    """Post a new task (requires payment)"""
    url = f"{WATT_API_BASE}/api/v1/tasks"
    payload = {
        "title": title,
        "description": description,
        "reward": reward,
        "tx_signature": tx_signature,
        "poster_wallet": WALLET_ADDRESS
    }
    response = requests.post(url, json=payload)
    return response.json()

def submit_task(task_id: str, result: Dict) -> Dict:
    """Submit task completion"""
    url = f"{WATT_API_BASE}/api/v1/tasks/{task_id}/submit"
    payload = {
        "result": result,
        "wallet": WALLET_ADDRESS
    }
    response = requests.post(url, json=payload)
    return response.json()
```

### LangChain Agent Tools

```python
# Define LangChain tools
tools = [
    Tool(
        name="WattCoin List Bounties",
        func=lambda type="all": str(get_bounties(type)),
        description="List open bounties on WattCoin. Input: bounty type (all, agent, code, docs). Output: JSON list of bounties with rewards."
    ),
    Tool(
        name="WattCoin List Tasks",
        func=lambda _: str(get_tasks()),
        description="List available tasks on WattCoin. Input: none. Output: JSON list of tasks with rewards and descriptions."
    ),
    Tool(
        name="WattCoin Get Stats",
        func=lambda _: str(get_network_stats()),
        description="Get WattCoin network statistics. Input: none. Output: JSON with total tasks, active nodes, WATT circulating supply."
    ),
    Tool(
        name="WattCoin Check Balance",
        func=lambda wallet: str(check_balance(wallet)),
        description="Check WATT balance for a wallet. Input: wallet address. Output: JSON with balance in WATT."
    ),
    Tool(
        name="WattCoin Submit Task",
        func=lambda task_result: str(submit_task(task_result.split("|")[0], {"data": task_result.split("|")[1]})),
        description="Submit task completion. Input: task_id|result_data. Output: JSON submission confirmation."
    )
]

# Initialize agent
llm = ChatOpenAI(model="gpt-4", temperature=0)
agent = initialize_agent(
    tools=tools,
    llm=llm,
    agent=AgentType.ZERO_SHOT_REACT_DESCRIPTION,
    verbose=True
)

# Example usage
agent.run("Find all code bounties worth more than 100 WATT and summarize them")
agent.run("Check the balance of wallet 7vvNkG3JF3JpxLEavqZSkc5T3n9hHR98Uw23fbWdXVSF")
agent.run("Get network stats and tell me how many active nodes there are")
```

### Autonomous Bounty Hunter Agent

```python
class WattCoinBountyHunter:
    """LangChain agent for autonomous bounty hunting"""
    
    def __init__(self, api_key: str = "", wallet: str = ""):
        self.api_key = api_key
        self.wallet = wallet
        self.llm = ChatOpenAI(model="gpt-4", temperature=0)
        self.tools = tools
        self.agent = initialize_agent(
            tools=self.tools,
            llm=self.llm,
            agent=AgentType.ZERO_SHOT_REACT_DESCRIPTION,
            verbose=True
        )
    
    def find_high_value_bounties(self, min_reward: int = 100) -> List[Dict]:
        """Find bounties above minimum reward threshold"""
        bounties = get_bounties()
        high_value = [b for b in bounties.get("bounties", []) if b.get("reward", 0) >= min_reward]
        return high_value
    
    def claim_bounty(self, bounty_id: str, claim_message: str) -> Dict:
        """Claim a bounty by commenting on the issue"""
        # This would integrate with GitHub API
        # For now, return placeholder
        return {"status": "claimed", "bounty_id": bounty_id}
    
    def run_hunt_cycle(self):
        """Run one cycle of bounty hunting"""
        print("🔍 Scanning for high-value bounties...")
        bounties = self.find_high_value_bounties(min_reward=100)
        print(f"Found {len(bounties)} bounties worth 100+ WATT")
        
        for bounty in bounties[:3]:  # Top 3
            print(f"\n📋 Analyzing: {bounty.get('title')}")
            analysis = self.agent.run(
                f"Analyze this bounty and determine if it's suitable for completion: {bounty}"
            )
            print(f"Analysis: {analysis}")
        
        return bounties

# Usage
hunter = WattCoinBountyHunter(wallet=WALLET_ADDRESS)
hunter.run_hunt_cycle()
```

---

## 2. CrewAI Integration

### Installation

```bash
pip install crewai crewai-tools
```

### Setup

```python
from crewai import Agent, Task, Crew, Process
from langchain.tools import tool
from typing import List, Dict
import requests

WATT_API_BASE = "https://api.wattcoin.org"

# CrewAI Tools
@tool("List WattCoin Bounties")
def list_bounties(bounty_type: str = "all") -> str:
    """List open bounties on WattCoin"""
    url = f"{WATT_API_BASE}/api/v1/bounties"
    params = {"type": bounty_type} if bounty_type != "all" else {}
    response = requests.get(url, params=params)
    return str(response.json())

@tool("Get WattCoin Tasks")
def get_tasks() -> str:
    """Get available tasks from WattCoin"""
    url = f"{WATT_API_BASE}/api/v1/tasks"
    response = requests.get(url)
    return str(response.json())

@tool("Check Watt Balance")
def check_balance(wallet: str) -> str:
    """Check WATT balance for a wallet address"""
    url = f"{WATT_API_BASE}/api/v1/balance/{wallet}"
    response = requests.get(url)
    return str(response.json())

@tool("Get Network Stats")
def get_stats() -> str:
    """Get WattCoin network statistics"""
    url = f"{WATT_API_BASE}/api/v1/stats"
    response = requests.get(url)
    return str(response.json())
```

### Multi-Agent Crew for Bounty Hunting

```python
from crewai import Agent, Task, Crew, Process

# Define Agents
bounty_researcher = Agent(
    role="Bounty Researcher",
    goal="Find high-value bounties on WattCoin that match our skills",
    backstory="You are an expert at identifying profitable bounties. You analyze reward amounts, difficulty, and time requirements.",
    tools=[list_bounties, get_tasks],
    verbose=True,
    allow_delegation=False
)

task_analyst = Agent(
    role="Task Analyst",
    goal="Analyze bounty requirements and estimate completion time",
    backstory="You break down complex tasks into actionable steps and estimate effort required.",
    tools=[get_tasks],
    verbose=True,
    allow_delegation=False
)

submission_specialist = Agent(
    role="Submission Specialist",
    goal="Prepare and submit high-quality bounty completions",
    backstory="You ensure all submissions meet requirements and maximize approval chances.",
    tools=[check_balance],
    verbose=True,
    allow_delegation=True
)

# Define Tasks
research_task = Task(
    description="""
    1. List all open bounties from WattCoin API
    2. Filter for bounties with reward >= 100 WATT
    3. Identify top 5 bounties by reward-to-effort ratio
    4. Return detailed list with titles, rewards, and descriptions
    """,
    agent=bounty_researcher,
    expected_output="List of top 5 high-value bounties with details"
)

analysis_task = Task(
    description="""
    1. Take the top 5 bounties from research
    2. For each bounty, estimate:
       - Technical difficulty (1-10)
       - Time required (hours)
       - Required skills
    3. Rank by best opportunity
    """,
    agent=task_analyst,
    expected_output="Ranked analysis of 5 bounties with effort estimates"
)

submission_task = Task(
    description="""
    1. Take the #1 ranked bounty from analysis
    2. Create a completion plan
    3. Prepare submission template
    4. Include wallet address for payout
    """,
    agent=submission_specialist,
    expected_output="Complete submission plan for top bounty"
)

# Create Crew
crew = Crew(
    agents=[bounty_researcher, task_analyst, submission_specialist],
    tasks=[research_task, analysis_task, submission_task],
    verbose=2,
    process=Process.sequential
)

# Execute
result = crew.kickoff()
print(result)
```

### Specialized Agent Roles

```python
# WattCoin Node Operator Agent
node_operator = Agent(
    role="WattCoin Node Operator",
    goal="Monitor and optimize WattNode earnings",
    backstory="You manage WattNode operations, tracking earnings and ensuring uptime.",
    tools=[get_stats, check_balance],
    verbose=True
)

node_monitoring_task = Task(
    description="""
    1. Check network stats for node performance metrics
    2. Verify wallet balance for earned WATT
    3. Report on node efficiency and earnings
    """,
    agent=node_operator,
    expected_output="Node performance report with earnings summary"
)

# Content Creator Agent for Documentation Bounties
content_creator = Agent(
    role="Technical Writer",
    goal="Create high-quality documentation for WattCoin bounties",
    backstory="You specialize in clear, comprehensive technical documentation.",
    tools=[list_bounties],
    verbose=True
)

doc_task = Task(
    description="""
    1. Find documentation bounties from WattCoin
    2. Select one matching your expertise
    3. Create outline for the documentation
    4. Write complete documentation following best practices
    """,
    agent=content_creator,
    expected_output="Complete documentation ready for submission"
)
```

---

## 3. AutoGPT Integration

### Installation

```bash
git clone https://github.com/Significant-Gravitas/AutoGPT.git
cd AutoGPT
pip install -r requirements.txt
```

### WattCoin Plugin for AutoGPT

```python
# autogpt_wattcoin/__init__.py
from auto_gpt_plugin_template import AutoGPTPluginTemplate
from typing import Any, Dict, List, Optional, Tuple, TypedDict
from colorama import Fore
import requests

WATT_API_BASE = "https://api.wattcoin.org"

class WattCoinPlugin(AutoGPTPluginTemplate):
    """WattCoin integration plugin for AutoGPT"""
    
    def __init__(self):
        super().__init__()
        self._name = "wattcoin-plugin"
        self._version = "1.0.0"
        self._description = "WattCoin API integration for bounty hunting and task completion"
    
    def can_handle_post_prompt(self) -> bool:
        return True
    
    def post_prompt(self, prompt: str) -> str:
        return prompt + "\n\nYou have access to WattCoin API tools for finding and completing bounties."
    
    def can_handle_on_response(self) -> bool:
        return False
    
    def can_handle_on_planning(self) -> bool:
        return False
    
    def can_handle_on_user_input(self) -> bool:
        return False
    
    def can_handle_report(self) -> bool:
        return False

# API Functions
def watt_list_bounties(bounty_type: str = "all") -> Dict:
    """List WattCoin bounties"""
    url = f"{WATT_API_BASE}/api/v1/bounties"
    params = {"type": bounty_type} if bounty_type != "all" else {}
    response = requests.get(url, params=params)
    return response.json()

def watt_list_tasks() -> Dict:
    """List WattCoin tasks"""
    url = f"{WATT_API_BASE}/api/v1/tasks"
    response = requests.get(url)
    return response.json()

def watt_get_stats() -> Dict:
    """Get WattCoin network stats"""
    url = f"{WATT_API_BASE}/api/v1/stats"
    response = requests.get(url)
    return response.json()

def watt_check_balance(wallet: str) -> Dict:
    """Check WATT balance"""
    url = f"{WATT_API_BASE}/api/v1/balance/{wallet}"
    response = requests.get(url)
    return response.json()

# Register tools
def register_wattcoin_tools(agent):
    """Register WattCoin tools with AutoGPT agent"""
    
    agent.tools.append(
        type('Tool', (), {
            'name': 'list_wattcoin_bounties',
            'description': 'List open bounties on WattCoin. Input: bounty type (all/agent/code/docs). Returns JSON list.',
            'method': lambda type="all": watt_list_bounties(type)
        })()
    )
    
    agent.tools.append(
        type('Tool', (), {
            'name': 'list_wattcoin_tasks',
            'description': 'List available tasks on WattCoin. Returns JSON list with rewards and descriptions.',
            'method': lambda: watt_list_tasks()
        })()
    )
    
    agent.tools.append(
        type('Tool', (), {
            'name': 'get_wattcoin_stats',
            'description': 'Get WattCoin network statistics. Returns active nodes, total tasks, WATT supply.',
            'method': lambda: watt_get_stats()
        })()
    )
    
    agent.tools.append(
        type('Tool', (), {
            'name': 'check_watt_balance',
            'description': 'Check WATT balance for a wallet. Input: wallet address. Returns balance in WATT.',
            'method': lambda wallet: watt_check_balance(wallet)
        })()
    )
```

### AutoGPT Configuration

```yaml
# ai_settings.yaml
ai_goals:
- Find and analyze high-value WattCoin bounties (100+ WATT)
- Identify bounties matching available skills
- Create completion plans for top 3 bounties
- Submit completed work and claim rewards

api_budget_limit: 10.0
autonomous_mode: true
continuous_mode: true
continuous_limit: 10
```

### Running AutoGPT with WattCoin

```bash
# Set environment variables
export WATT_WALLET="your_wallet_address"
export WATT_API_KEY="your_api_key"

# Run AutoGPT
python -m autogpt --gpt3only --continuous

# Example prompts:
# "Find all WattCoin bounties worth more than 500 WATT and create a summary"
# "Monitor WattCoin network stats every 5 minutes and report changes"
# "Search for documentation bounties and write completion plans"
```

---

## 4. OpenAI Assistants API Integration

### Setup

```python
from openai import OpenAI
import requests
import json

client = OpenAI(api_key="your-openai-api-key")
WATT_API_BASE = "https://api.wattcoin.org"
```

### Create Assistant with WattCoin Tools

```python
# Define functions for the assistant
functions = [
    {
        "name": "list_bounties",
        "description": "List open bounties on WattCoin",
        "parameters": {
            "type": "object",
            "properties": {
                "bounty_type": {
                    "type": "string",
                    "enum": ["all", "agent", "code", "docs", "creative"],
                    "description": "Type of bounties to list"
                }
            },
            "required": []
        }
    },
    {
        "name": "list_tasks",
        "description": "List available tasks on WattCoin",
        "parameters": {
            "type": "object",
            "properties": {},
            "required": []
        }
    },
    {
        "name": "get_stats",
        "description": "Get WattCoin network statistics",
        "parameters": {
            "type": "object",
            "properties": {},
            "required": []
        }
    },
    {
        "name": "check_balance",
        "description": "Check WATT balance for a wallet",
        "parameters": {
            "type": "object",
            "properties": {
                "wallet": {
                    "type": "string",
                    "description": "Solana wallet address"
                }
            },
            "required": ["wallet"]
        }
    }
]

# Create the assistant
assistant = client.beta.assistants.create(
    name="WattCoin Bounty Hunter",
    instructions="You are an AI assistant that helps users find and complete WattCoin bounties. "
                 "Use the available tools to fetch bounty information, analyze opportunities, "
                 "and guide users through the completion process.",
    model="gpt-4-turbo-preview",
    tools=[{"type": "function", "function": func} for func in functions]
)
```

### Function Implementation

```python
def execute_function(function_name: str, arguments: dict) -> str:
    """Execute WattCoin API function"""
    
    if function_name == "list_bounties":
        bounty_type = arguments.get("bounty_type", "all")
        url = f"{WATT_API_BASE}/api/v1/bounties"
        params = {"type": bounty_type} if bounty_type != "all" else {}
        response = requests.get(url, params=params)
        return json.dumps(response.json())
    
    elif function_name == "list_tasks":
        url = f"{WATT_API_BASE}/api/v1/tasks"
        response = requests.get(url)
        return json.dumps(response.json())
    
    elif function_name == "get_stats":
        url = f"{WATT_API_BASE}/api/v1/stats"
        response = requests.get(url)
        return json.dumps(response.json())
    
    elif function_name == "check_balance":
        wallet = arguments.get("wallet")
        url = f"{WATT_API_BASE}/api/v1/balance/{wallet}"
        response = requests.get(url)
        return json.dumps(response.json())
    
    return json.dumps({"error": "Unknown function"})

# Run the assistant
def run_assistant(user_message: str):
    """Run assistant with user message"""
    
    # Create thread
    thread = client.beta.threads.create()
    
    # Add message
    client.beta.threads.messages.create(
        thread_id=thread.id,
        role="user",
        content=user_message
    )
    
    # Run assistant
    run = client.beta.threads.runs.create(
        thread_id=thread.id,
        assistant_id=assistant.id
    )
    
    # Handle function calls
    while run.status in ["queued", "in_progress", "requires_action"]:
        run = client.beta.threads.runs.retrieve(
            thread_id=thread.id,
            run_id=run.id
        )
        
        if run.status == "requires_action":
            tool_calls = run.required_action.submit_tool_outputs.tool_calls
            
            tool_outputs = []
            for call in tool_calls:
                function_name = call.function.name
                arguments = json.loads(call.function.arguments)
                
                result = execute_function(function_name, arguments)
                tool_outputs.append({
                    "tool_call_id": call.id,
                    "output": result
                })
            
            # Submit tool outputs
            run = client.beta.threads.runs.submit_tool_outputs(
                thread_id=thread.id,
                run_id=run.id,
                tool_outputs=tool_outputs
            )
    
    # Get final response
    messages = client.beta.threads.messages.list(thread_id=thread.id)
    return messages.data[0].content[0].text.value

# Example usage
response = run_assistant("Find all code bounties worth more than 200 WATT")
print(response)

response = run_assistant("Check the balance of wallet 7vvNkG3JF3JpxLEavqZSkc5T3n9hHR98Uw23fbWdXVSF")
print(response)
```

### Thread Management for Ongoing Tasks

```python
class WattCoinAssistant:
    """Manage ongoing WattCoin bounty hunting sessions"""
    
    def __init__(self, api_key: str):
        self.client = OpenAI(api_key=api_key)
        self.WATT_API_BASE = "https://api.wattcoin.org"
        
        # Create assistant
        self.assistant = self.client.beta.assistants.create(
            name="WattCoin Agent",
            instructions="You help users earn WATT by finding and completing bounties.",
            model="gpt-4-turbo-preview",
            tools=[{"type": "function", "function": func} for func in functions]
        )
        
        # Create thread for session
        self.thread = self.client.beta.threads.create()
    
    def ask(self, message: str) -> str:
        """Send message and get response"""
        # Add user message
        self.client.beta.threads.messages.create(
            thread_id=self.thread.id,
            role="user",
            content=message
        )
        
        # Run and get response (simplified)
        run = self.client.beta.threads.runs.create(
            thread_id=self.thread.id,
            assistant_id=self.assistant.id
        )
        
        # Wait for completion
        import time
        while run.status in ["queued", "in_progress"]:
            time.sleep(1)
            run = self.client.beta.threads.runs.retrieve(
                thread_id=self.thread.id,
                run_id=run.id
            )
        
        # Get response
        messages = self.client.beta.threads.messages.list(thread_id=self.thread.id)
        return messages.data[0].content[0].text.value
    
    def monitor_bounties(self, min_reward: int = 100):
        """Set up bounty monitoring"""
        return self.ask(f"Monitor WattCoin for new bounties with reward >= {min_reward} WATT")

# Usage
watt_assistant = WattCoinAssistant(api_key="your-openai-key")
print(watt_assistant.ask("What are the top 5 bounties right now?"))
```

---

## Authentication Patterns

### Current: API Key Authentication

```python
import requests

API_KEY = "your_api_key"
headers = {
    "Authorization": f"Bearer {API_KEY}",
    "Content-Type": "application/json"
}

# Authenticated request
response = requests.post(
    f"{WATT_API_BASE}/api/v1/tasks",
    headers=headers,
    json={"title": "My Task", "reward": 500}
)
```

### Future: Wallet-Signed Authentication

```python
from nacl.signing import SigningKey
import base64

# Generate signing key from wallet
private_key = SigningKey.generate()
public_key = private_key.verify_key

# Sign request
message = b"POST /api/v1/tasks" + timestamp_bytes
signature = private_key.sign(message)

headers = {
    "X-Wallet-Signature": base64.b64encode(signature).decode(),
    "X-Wallet-Public": base64.b64encode(bytes(public_key)).decode(),
    "X-Timestamp": timestamp
}
```

---

## Complete Examples

### Example 1: Autonomous Bounty Hunter (LangChain)

```python
from langchain.agents import initialize_agent, Tool, AgentType
from langchain.chat_models import ChatOpenAI
import requests

WATT_API = "https://api.wattcoin.org"

def find_and_claim_bounties():
    """Autonomous bounty hunting cycle"""
    
    # Tools
    tools = [
        Tool(
            name="Search Bounties",
            func=lambda _: str(requests.get(f"{WATT_API}/api/v1/bounties").json()),
            description="Get all open bounties"
        )
    ]
    
    # Agent
    agent = initialize_agent(
        tools=tools,
        llm=ChatOpenAI(model="gpt-4"),
        agent=AgentType.ZERO_SHOT_REACT_DESCRIPTION
    )
    
    # Run hunt
    result = agent.run(
        "Find bounties worth 100+ WATT that involve documentation or Python code. "
        "Return the top 3 with titles, rewards, and links."
    )
    
    print(result)
    return result

find_and_claim_bounties()
```

### Example 2: Multi-Agent Task Force (CrewAI)

```python
from crewai import Agent, Task, Crew

# Agents
researcher = Agent(
    role="Bounty Researcher",
    goal="Find best bounties",
    backstory="Expert at finding profitable opportunities",
    tools=[list_bounties],
    verbose=True
)

writer = Agent(
    role="Technical Writer",
    goal="Write documentation",
    backstory="Professional technical writer",
    verbose=True
)

reviewer = Agent(
    role="Quality Reviewer",
    goal="Ensure submission quality",
    backstory="Detail-oriented reviewer",
    verbose=True
)

# Tasks
find_task = Task(
    description="Find documentation bounties worth 200+ WATT",
    agent=researcher
)

write_task = Task(
    description="Write complete documentation for selected bounty",
    agent=writer
)

review_task = Task(
    description="Review and approve submission",
        agent=reviewer
)

# Execute
crew = Crew(agents=[researcher, writer, reviewer], tasks=[find_task, write_task, review_task])
crew.kickoff()
```

### Example 3: Continuous Monitoring (OpenAI Assistants)

```python
from openai import OpenAI
import time

client = OpenAI(api_key="your-key")

# Create persistent assistant
assistant = client.beta.assistants.create(
    name="WattCoin Monitor",
    instructions="Monitor WattCoin for new high-value bounties",
    model="gpt-4-turbo-preview"
)

thread = client.beta.threads.create()

# Continuous monitoring loop
while True:
    client.beta.threads.messages.create(
        thread_id=thread.id,
        role="user",
        content="Check for new bounties in the last hour worth 500+ WATT"
    )
    
    run = client.beta.threads.runs.create(
        thread_id=thread.id,
        assistant_id=assistant.id
    )
    
    # Wait and get results
    time.sleep(5)
    messages = client.beta.threads.messages.list(thread_id=thread.id)
    print(messages.data[0].content[0].text.value)
    
    time.sleep(300)  # Check every 5 minutes
```

---

## Best Practices

### 1. Rate Limiting

```python
import time
from functools import wraps

def rate_limit(calls_per_minute=60):
    def decorator(func):
        last_called = [0]
        @wraps(func)
        def wrapper(*args, **kwargs):
            elapsed = time.time() - last_called[0]
            min_interval = 60 / calls_per_minute
            if elapsed < min_interval:
                time.sleep(min_interval - elapsed)
            last_called[0] = time.time()
            return func(*args, **kwargs)
        return wrapper
    return decorator

@rate_limit(calls_per_minute=30)
def api_call():
    return requests.get(f"{WATT_API_BASE}/api/v1/bounties")
```

### 2. Error Handling

```python
from requests.exceptions import RequestException, Timeout

def safe_api_call(endpoint: str, retries: int = 3):
    """Safe API call with retry logic"""
    for attempt in range(retries):
        try:
            response = requests.get(f"{WATT_API_BASE}{endpoint}", timeout=10)
            response.raise_for_status()
            return response.json()
        except Timeout:
            print(f"Timeout on attempt {attempt + 1}")
            time.sleep(2 ** attempt)
        except RequestException as e:
            print(f"Request error: {e}")
            if attempt == retries - 1:
                raise
    return None
```

### 3. Wallet Security

```python
import os
from dotenv import load_dotenv

load_dotenv()

# Never hardcode wallet or API key
WALLET = os.getenv("WATT_WALLET")
API_KEY = os.getenv("WATT_API_KEY")

# Use environment variables or secure vault
if not WALLET or not API_KEY:
    raise ValueError("Wallet and API key must be set in environment")
```

---

## Submission

**Payout Wallet**: `RTC53fdf727dd301da40ee79cdd7bd740d8c04d2fb4`

**GitHub**: @zhuzhushiwojia

**Completion Date**: 2026-03-15

---

## Resources

- [WattCoin Documentation](https://wattcoin.org/docs)
- [WattCoin GitHub](https://github.com/WattCoin-Org/wattcoin)
- [LangChain Docs](https://python.langchain.com/)
- [CrewAI Docs](https://docs.crewai.com/)
- [AutoGPT Docs](https://docs.agpt.co/)
- [OpenAI Assistants API](https://platform.openai.com/docs/assistants)
