#!/usr/bin/env python3
"""
WattCoin Autonomous Bounty Evaluator
Evaluates GitHub issues for bounty eligibility using AI
"""

import os
import re
from openai import OpenAI

AI_API_KEY = os.getenv("AI_API_KEY", "")

BOUNTY_EVALUATION_PROMPT = """**AI Bounty Evaluation Prompt (v1.0)**
You are the autonomous bounty gatekeeper for WattCoin — a pure utility token on Solana designed exclusively for the AI/agent economy. WattCoin's core mission is to enable real, on-chain economic loops where AI agents earn WATT by performing useful work that directly improves the WattCoin ecosystem itself: node infrastructure (WattNode), agent marketplace/tasks, skills/PR bounties, WSI swarm intelligence, security, and core utilities (scraping, inference, verification). Value accrues only through verifiable network usage and agent contributions — never speculation, hype, or off-topic features.

Your role is to evaluate new GitHub issues requesting bounties. Be extremely strict: the system is easily abused by vague, low-effort, duplicate, or misaligned requests. Reject anything ambiguous, cosmetic, or not clearly high-impact. Prioritize contributions that accelerate the agent self-improvement flywheel.

**Evaluation Rubric (score 0-10 on each dimension, then overall)**

1. **Mission Alignment (0-10)**  
   Does this directly advance agent-native capabilities, node network, marketplace, security, or core utilities? Must be tightly scoped to WattCoin's agent economy — reject anything unrelated (e.g., marketing, website cosmetics, unrelated integrations).

2. **Legitimacy & Specificity (0-10)**  
   Is the request clear, actionable, and non-duplicate? Reject vague ("improve docs"), open-ended ("make it better"), or low-effort (single typo) requests. Require concrete description of problem, proposed solution, and expected impact.

3. **Impact vs Effort (0-10)**  
   High score only if the improvement meaningfully strengthens the meta loop (agents earning by building agents) with reasonable implementation effort.

4. **Abuse Risk (reject if any red flags)**  
   - Over-claiming value for trivial work  
   - Duplicate of existing issue/PR  
   - Spam or low-effort farming  
   - Requests that could be gamed or drained treasury

**Overall Decision**
- **Score ≥ 8/10 across all dimensions**: APPROVE  
  - Assign bounty tier based on complexity:  
    - Simple (500-2,000 WATT): Bug fixes, small helpers, docs examples  
    - Medium (2,000-10,000 WATT): New endpoints, refactors, skill enhancements  
    - Complex (10,000-50,000 WATT): Architecture, new core features, security  
    - Expert (50,000+ WATT): Rare — only major breakthroughs  
  - Output exact amount (round to nearest 500).  
- **Score < 8/10 or any red flag**: REJECT

**Response Format (strict)**
```
DECISION: APPROVE or REJECT
SCORE: X/10 (brief overall justification)
BOUNTY AMOUNT: XXXXX WATT (only if APPROVE)
REASONING:
- Alignment: ...
- Legitimacy: ...
- Impact: ...
- Risks: ...
SUGGESTED TITLE: [BOUNTY: XXXXX WATT] Original Title
```

Be conservative — when in doubt, reject. Treasury protection and quality are paramount. The swarm thrives on real contributions only. ⚡🤖

---

**Issue to Evaluate:**

Title: {title}

Body:
{body}

Existing Labels: {labels}

Evaluate this issue strictly according to the rubric above."""


def evaluate_bounty_request(issue_title, issue_body, existing_labels=[]):
    """
    Evaluate an issue for bounty eligibility using AI.
    
    Returns:
        dict with keys: decision, score, amount, reasoning, suggested_title
    """
    if not AI_API_KEY:
        return {
            "decision": "ERROR",
            "error": "AI_API_KEY not configured"
        }
    
    # Format prompt with issue details
    prompt = BOUNTY_EVALUATION_PROMPT.format(
        title=issue_title,
        body=issue_body,
        labels=", ".join(existing_labels) if existing_labels else "None"
    )
    
    try:
        # Call AI API
        client = OpenAI(
            api_key=AI_API_KEY,
            base_url="https://api.x.ai/v1"
        )
        
        response = client.chat.completions.create(
            model="grok-code-fast-1",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.3,
            max_tokens=1000
        )
        
        ai_output = response.choices[0].message.content
        
        # Parse AI structured output
        result = parse_ai_bounty_response(ai_output)
        result["raw_output"] = ai_output
        
        return result
        
    except Exception as e:
        return {
            "decision": "ERROR",
            "error": str(e)
        }


def parse_ai_bounty_response(output):
    """Parse AI structured bounty evaluation response"""
    result = {
        "decision": "REJECT",  # Default to reject
        "score": 0,
        "amount": 0,
        "reasoning": "",
        "suggested_title": ""
    }
    
    # Extract DECISION
    decision_match = re.search(r'DECISION:\s*(APPROVE|REJECT)', output, re.IGNORECASE)
    if decision_match:
        result["decision"] = decision_match.group(1).upper()
    
    # Extract SCORE
    score_match = re.search(r'SCORE:\s*(\d+)/10', output)
    if score_match:
        result["score"] = int(score_match.group(1))
    
    # Extract BOUNTY AMOUNT (only if approved)
    amount_match = re.search(r'BOUNTY AMOUNT:\s*([\d,]+)\s*WATT', output)
    if amount_match:
        amount_str = amount_match.group(1).replace(',', '')
        result["amount"] = int(amount_str)
    
    # Extract REASONING section
    reasoning_match = re.search(r'REASONING:(.*?)(?:SUGGESTED TITLE:|$)', output, re.DOTALL)
    if reasoning_match:
        result["reasoning"] = reasoning_match.group(1).strip()
    
    # Extract SUGGESTED TITLE
    title_match = re.search(r'SUGGESTED TITLE:\s*(.+?)$', output, re.MULTILINE)
    if title_match:
        result["suggested_title"] = title_match.group(1).strip()
    
    return result
