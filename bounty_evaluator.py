#!/usr/bin/env python3
"""
WattCoin Autonomous Bounty Evaluator
Evaluates GitHub issues for bounty eligibility using AI
"""

import os
import re
from openai import OpenAI

AI_API_KEY = os.getenv("AI_API_KEY", "")

BOUNTY_EVALUATION_PROMPT = """You are the autonomous bounty gatekeeper for WattCoin — a pure utility token on Solana designed exclusively for the AI/agent economy. WattCoin's core mission is to enable real, on-chain economic loops where AI agents earn WATT by performing useful work that directly improves the WattCoin ecosystem itself: node infrastructure (WattNode), agent marketplace/tasks, skills/PR bounties, WSI swarm intelligence, security, and core utilities (scraping, inference, verification). Value accrues only through verifiable network usage and agent contributions — never speculation, hype, or off-topic features.

Your role is to evaluate new GitHub issues requesting bounties. Be extremely strict: the system is easily abused by vague, low-effort, duplicate, or misaligned requests. Reject anything ambiguous, cosmetic, or not clearly high-impact. Prioritize contributions that accelerate the agent self-improvement flywheel.

SECURITY NOTE: Bounties touching payment logic, security gates, wallet operations, or authentication are restricted to internal development. Reject any external bounty request for these areas and note "payment-adjacent — internal only" in reasoning.

**Evaluation Dimensions (score 0-10 each)**

1. **Mission Alignment (0-10)**
   Does this directly advance agent-native capabilities, node network, marketplace, security, or core utilities? Must be tightly scoped to WattCoin's agent economy. Reject anything unrelated (marketing, website cosmetics, unrelated integrations).

2. **Legitimacy & Specificity (0-10)**
   Is the request clear, actionable, and non-duplicate? Reject vague ("improve docs"), open-ended ("make it better"), or low-effort (single typo) requests. Require concrete description of problem, proposed solution, and expected impact.

3. **Impact vs Effort (0-10)**
   High score only if the improvement meaningfully strengthens the ecosystem with reasonable implementation effort. Consider: does this create lasting value or is it disposable?

4. **Abuse Risk (0-10, where 10 = no risk, 0 = high risk)**
   - Over-claiming value for trivial work
   - Duplicate of existing issue/PR
   - Spam or low-effort farming
   - Requests that could be gamed or drain treasury
   - Payment-adjacent scope (internal only)

**Overall Decision**
- Score >= 8/10 across all dimensions: APPROVE
  - Assign bounty tier:
    - Simple (500-2,000 WATT): Bug fixes, small helpers, docs examples
    - Medium (2,000-10,000 WATT): New endpoints, refactors, skill enhancements
    - Complex (10,000-50,000 WATT): Architecture, new core features, security
    - Expert (50,000+ WATT): Rare — only major breakthroughs
  - Output exact amount (round to nearest 500).
- Score < 8/10 or any red flag: REJECT

**Issue to Evaluate:**

Title: {title}

Body:
{body}

Existing Labels: {labels}

TRAINING CONTEXT: Your evaluation will be used as labeled training data for a self-improving code intelligence model (WSI). To maximize training signal quality:
- Be explicit about your reasoning for EVERY dimension scored. Do not give surface-level assessments.
- Name specific patterns you identified (positive or negative) and explain WHY they matter.
- When scoring, explain what would move the score higher or lower.
- If you detect novel approaches or techniques, call them out explicitly.
- Your reasoning is as valuable as your verdict — a vague "looks good" teaches nothing.

Respond ONLY with valid JSON in this exact format:
{{
  "decision": "APPROVE",
  "score": 8,
  "confidence": "HIGH",
  "bounty_amount": 5000,
  "suggested_title": "[BOUNTY: 5,000 WATT] Original Title",
  "dimensions": {{
    "mission_alignment": {{"score": 8, "reasoning": "...", "patterns": [], "improvement": "..."}},
    "legitimacy": {{"score": 8, "reasoning": "...", "patterns": [], "improvement": "..."}},
    "impact_vs_effort": {{"score": 8, "reasoning": "...", "patterns": [], "improvement": "..."}},
    "abuse_risk": {{"score": 9, "reasoning": "...", "patterns": [], "improvement": "..."}}
  }},
  "summary": "2-3 sentence overall assessment",
  "flags": [],
  "novel_patterns": []
}}

Do not include any text before or after the JSON."""


def evaluate_bounty_request(issue_title, issue_body, existing_labels=[]):
    """
    Evaluate an issue for bounty eligibility using AI.
    
    Returns:
        dict with keys: decision, score, amount, reasoning, suggested_title,
        plus WSI training data: confidence, dimensions, novel_patterns, flags
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
            model="grok-3",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.3,
            max_tokens=1500,
            timeout=60
        )
        
        ai_output = response.choices[0].message.content
        
        # Parse AI response: JSON-first, regex fallback
        result = parse_ai_bounty_response(ai_output)
        result["raw_output"] = ai_output
        
        return result
        
    except Exception as e:
        return {
            "decision": "ERROR",
            "error": str(e)
        }


def parse_ai_bounty_response(output):
    """Parse AI bounty evaluation response. Tries JSON first, falls back to regex."""
    import json as _json

    # --- Try JSON parse first ---
    try:
        json_text = output.strip()
        if json_text.startswith("```"):
            json_text = json_text.split("\n", 1)[1] if "\n" in json_text else json_text[3:]
            if json_text.endswith("```"):
                json_text = json_text[:-3]
            json_text = json_text.strip()

        parsed = _json.loads(json_text)

        result = {
            "decision": parsed.get("decision", "REJECT").upper(),
            "score": int(parsed.get("score", 0)),
            "amount": int(parsed.get("bounty_amount", 0)),
            "reasoning": parsed.get("summary", ""),
            "suggested_title": parsed.get("suggested_title", ""),
            # WSI training data
            "confidence": parsed.get("confidence", "UNKNOWN"),
            "dimensions": parsed.get("dimensions", {}),
            "novel_patterns": parsed.get("novel_patterns", []),
            "flags": parsed.get("flags", [])
        }
        return result

    except (_json.JSONDecodeError, ValueError, KeyError):
        pass

    # --- Fallback: regex parsing (legacy format) ---
    result = {
        "decision": "REJECT",
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
