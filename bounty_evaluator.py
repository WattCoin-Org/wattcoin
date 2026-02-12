#!/usr/bin/env python3
"""
WattCoin Autonomous Bounty Evaluator
Evaluates GitHub issues for bounty eligibility using AI
"""

import os
import re

AI_API_KEY = os.getenv("AI_API_KEY", "")

# Escrow wallet for staking
ESCROW_WALLET = os.getenv("ESCROW_WALLET_ADDRESS", "5nZhxQksaj7pVWgET7UFSPjN7BDBYWWw3ZdL9AmADvkZ")
STAKE_PERCENTAGE = int(os.getenv("BOUNTY_STAKE_PERCENTAGE", "10"))

BOUNTY_EVALUATION_PROMPT = """You are the autonomous bounty gatekeeper for WattCoin — a pure utility token on Solana designed exclusively for the AI/agent economy. WattCoin's core mission is to enable real, on-chain economic loops where AI agents earn WATT by performing useful work that directly improves the WattCoin ecosystem itself: node infrastructure (WattNode), agent marketplace/tasks, skills/PR bounties, distributed inference, security, and core utilities (scraping, inference, verification). Value accrues only through verifiable network usage and agent contributions — never speculation, hype, or off-topic features.

Your role is to evaluate new GitHub issues requesting bounties. Be extremely strict: the system is easily abused by vague, low-effort, duplicate, or misaligned requests. Reject anything ambiguous, cosmetic, or not clearly high-impact. Prioritize contributions that strengthen the agent ecosystem.

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
  - Assign bounty tier (STRICT — do not exceed tier caps):
    - Simple (500-2,000 WATT): Bug fixes, small helpers, docs examples, typo fixes
    - Medium (2,000-10,000 WATT): New endpoints, refactors, skill enhancements, test suites
    - Complex (10,000-50,000 WATT): Architecture, new core features, multi-file security improvements
    - Expert (50,000-500,000 WATT): Rare — only major system-level breakthroughs with clear ecosystem impact
  - Output exact amount (round to nearest 500). MAXIMUM bounty is 500,000 WATT. Never exceed this.
- Score < 8/10 or any red flag: REJECT

**IMPORTANT — Bounty Body Requirements:**
When you output the `suggested_body`, you MUST include ALL of the following sections:

1. **Description** — clear task description
2. **Requirements** — numbered list of specific deliverables
3. **API Endpoints Note** (if applicable) — if the bounty references any API endpoints that may not exist yet, include:
   > **Note:** Some referenced API endpoints may not be built yet. Use configurable URLs (env vars or config file), implement graceful error handling for unavailable endpoints, and document any new endpoints you create.
4. **Security Requirements** — include "No `shell=True` in subprocess calls" and any other relevant security notes
5. **Payout Wallet section** — always end with:
   ```
   ---
   **Payout Wallet**: <your_solana_address>
   **Stake TX**: <your_stake_tx_signature>

   ℹ️ Before claiming this bounty, you must stake {stake_pct}% ({stake_amount} WATT) to the escrow wallet:
   `{escrow_wallet}`
   Include memo: `stake:<issue_number>`
   Your stake is returned when your PR is merged OR if all reviews are exhausted.
   ```

**Issue to Evaluate:**

Title: {title}

Body:
{body}

Existing Labels: {labels}

Respond ONLY with valid JSON in this exact format:
{{
  "decision": "APPROVE",
  "score": 8,
  "confidence": "HIGH",
  "bounty_amount": 5000,
  "suggested_title": "[BOUNTY: 5,000 WATT] Original Title",
  "suggested_body": "Full issue body with all required sections including wallet hint and staking instructions",
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
        dict with keys: decision, score, amount, reasoning, suggested_title, suggested_body
    """
    if not AI_API_KEY:
        return {
            "decision": "ERROR",
            "error": "AI_API_KEY not configured"
        }
    
    # Calculate stake info for prompt
    # We don't know the bounty amount yet, so AI will fill in the template
    prompt = BOUNTY_EVALUATION_PROMPT.format(
        title=issue_title,
        body=issue_body,
        labels=", ".join(existing_labels) if existing_labels else "None",
        stake_pct=STAKE_PERCENTAGE,
        stake_amount="{calculated_at_creation}",
        escrow_wallet=ESCROW_WALLET,
        issue_number="{issue_number}"
    )
    
    try:
        # Call AI API (vendor-neutral via ai_provider)
        from ai_provider import call_ai
        ai_output, ai_error = call_ai(prompt, temperature=0.3, max_tokens=2500, timeout=60)
        
        if ai_error or not ai_output:
            return {
                "decision": "ERROR",
                "error": f"AI API error: {ai_error}"
            }
        
        # Parse AI response: JSON-first, regex fallback
        result = parse_ai_bounty_response(ai_output)
        result["raw_output"] = ai_output
        
        # Enforce 500K cap
        if result.get("amount", 0) > 500000:
            result["amount"] = 500000
            result["flags"] = result.get("flags", []) + ["Amount capped at 500,000 WATT maximum"]
        
        # Save training data (non-blocking)
        try:
            from eval_logger import save_evaluation
            save_evaluation("bounty_evaluation", ai_output, {
                "title": issue_title,
            })
        except Exception:
            pass
        
        return result
        
    except Exception as e:
        return {
            "decision": "ERROR",
            "error": str(e)
        }


def format_bounty_body(suggested_body, bounty_amount, issue_number):
    """
    Post-process the AI-generated bounty body to fill in dynamic values.
    Ensures staking instructions have correct amounts.
    """
    stake_amount = int(bounty_amount * STAKE_PERCENTAGE / 100)
    
    # Replace placeholder values
    body = suggested_body
    body = body.replace("{calculated_at_creation}", f"{stake_amount:,}")
    body = body.replace("{stake_amount}", f"{stake_amount:,}")
    body = body.replace("{stake_pct}", str(STAKE_PERCENTAGE))
    body = body.replace("{escrow_wallet}", ESCROW_WALLET)
    body = body.replace("{issue_number}", str(issue_number))
    
    # If AI didn't include the staking section, append it
    if "Stake TX" not in body and "stake" not in body.lower():
        body += f"""

---
**Payout Wallet**: <your_solana_address>
**Stake TX**: <your_stake_tx_signature>

ℹ️ Before claiming this bounty, you must stake {STAKE_PERCENTAGE}% ({stake_amount:,} WATT) to the escrow wallet:
`{ESCROW_WALLET}`
Include memo: `stake:{issue_number}`
Your stake is returned when your PR is merged OR if all reviews are exhausted."""

    # If AI didn't include the wallet hint, append it
    if "**Payout Wallet**" not in body:
        body += "\n\n---\n**Payout Wallet**: <your_solana_address>"
    
    return body


def check_duplicate_issues(title, existing_issues):
    """
    Check if a proposed bounty title is too similar to existing open issues.
    
    Args:
        title: proposed issue title
        existing_issues: list of dicts with 'title' and 'number' keys
    
    Returns:
        (is_duplicate, matching_issue_number, reason)
    """
    if not existing_issues:
        return False, None, None
    
    # Normalize title for comparison
    clean_title = re.sub(r'\[BOUNTY:.*?\]\s*', '', title, flags=re.IGNORECASE).strip().lower()
    clean_title = re.sub(r'[^a-z0-9\s]', '', clean_title)
    title_words = set(clean_title.split())
    
    for issue in existing_issues:
        existing_title = issue.get("title", "")
        existing_clean = re.sub(r'\[BOUNTY:.*?\]\s*', '', existing_title, flags=re.IGNORECASE).strip().lower()
        existing_clean = re.sub(r'[^a-z0-9\s]', '', existing_clean)
        existing_words = set(existing_clean.split())
        
        # Skip very short titles (< 3 words) — too many false positives
        if len(title_words) < 3 or len(existing_words) < 3:
            # Exact match only for short titles
            if clean_title == existing_clean:
                return True, issue.get("number"), f"Exact duplicate of Issue #{issue.get('number')}: {existing_title}"
            continue
        
        # Calculate word overlap (Jaccard similarity)
        if not title_words or not existing_words:
            continue
        
        intersection = title_words & existing_words
        union = title_words | existing_words
        similarity = len(intersection) / len(union) if union else 0
        
        if similarity >= 0.7:  # 70% word overlap = likely duplicate
            return True, issue.get("number"), f"Very similar to existing Issue #{issue.get('number')}: {existing_title} (similarity: {similarity:.0%})"
    
    return False, None, None


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
            "suggested_body": parsed.get("suggested_body", ""),
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
        "suggested_title": "",
        "suggested_body": ""
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
