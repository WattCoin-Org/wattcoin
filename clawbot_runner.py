#!/usr/bin/env python3
"""
Clawbot Runner — Auto-populate bounty prompt templates from GitHub issues.

Usage:
    python clawbot_runner.py <issue_number> [--phase discover|plan|implement|submit|review|full]
    python clawbot_runner.py 130 --phase full
    python clawbot_runner.py 130 --phase implement --files api_nodes.py,api_webhooks.py

Reads issue data from GitHub API, extracts bounty details, and outputs
a ready-to-use prompt for the specified phase.

Requires:
    GITHUB_TOKEN env var (or uses repo's public access)
"""

import os
import re
import sys
import json
import argparse
import requests
import base64

# =============================================================================
# CONFIG
# =============================================================================

GITHUB_TOKEN = os.getenv("GITHUB_TOKEN", "")
REPO = "WattCoin-Org/wattcoin"
DEFAULT_WALLET = os.getenv("CLAWBOT_WALLET", "7vvNkG3JF3JpxLEavqZSkc5T3n9hHR98Uw23fbWdXVSF")


# =============================================================================
# GITHUB HELPERS
# =============================================================================

def github_headers():
    """Get GitHub API headers."""
    headers = {"Accept": "application/vnd.github.v3+json"}
    if GITHUB_TOKEN:
        headers["Authorization"] = f"token {GITHUB_TOKEN}"
    return headers


def fetch_issue(issue_number):
    """Fetch issue details from GitHub."""
    url = f"https://api.github.com/repos/{REPO}/issues/{issue_number}"
    resp = requests.get(url, headers=github_headers(), timeout=15)
    if resp.status_code != 200:
        print(f"❌ Failed to fetch issue #{issue_number}: {resp.status_code}")
        sys.exit(1)
    return resp.json()


def fetch_file_contents(filepath):
    """Fetch file contents from GitHub repo."""
    url = f"https://api.github.com/repos/{REPO}/contents/{filepath}"
    resp = requests.get(url, headers=github_headers(), timeout=15)
    if resp.status_code != 200:
        return f"[ERROR: Could not fetch {filepath} — {resp.status_code}]"
    data = resp.json()
    return base64.b64decode(data["content"]).decode("utf-8")


def fetch_open_issues():
    """Fetch open issues for duplicate checking."""
    url = f"https://api.github.com/repos/{REPO}/issues?state=open&per_page=50"
    resp = requests.get(url, headers=github_headers(), timeout=15)
    if resp.status_code != 200:
        return []
    issues = resp.json()
    return [f"#{i['number']}: {i['title']}" for i in issues if not i.get("pull_request")]


# =============================================================================
# BOUNTY PARSING
# =============================================================================

def parse_bounty_amount(title):
    """Extract bounty amount from issue title like '[BOUNTY: 5,000 WATT]'."""
    match = re.search(r'(\d{1,3}(?:,?\d{3})*)\s*WATT', title, re.IGNORECASE)
    if match:
        return match.group(1)
    return "TBD"


def extract_target_files(body):
    """Extract target files from issue body."""
    files = []

    # Look for "Files to Modify" section
    files_section = re.search(
        r'(?:Files? to Modify|Target files?|Affected files?)[:\s]*\n(.*?)(?:\n\n|\n##|\Z)',
        body or "", re.IGNORECASE | re.DOTALL
    )
    if files_section:
        for line in files_section.group(1).split("\n"):
            # Match filenames like api_nodes.py, wattnode/services/inference.py
            file_match = re.search(r'[`\- ]*([a-zA-Z0-9_/]+\.(?:py|js|jsx|md|json|yaml|toml))', line)
            if file_match:
                files.append(file_match.group(1))

    # Fallback: scan body for .py file references
    if not files:
        files = list(set(re.findall(r'(?:^|[\s`])([a-zA-Z0-9_/]+\.py)\b', body or "")))

    return files


def extract_scope(body):
    """Extract scope/description from issue body."""
    # Try to find "Proposed Solution" or "Description" section
    for header in ["Proposed Solution", "Description", "What", "Summary"]:
        section = re.search(
            rf'(?:##\s*)?{header}[:\s]*\n(.*?)(?:\n##|\Z)',
            body or "", re.IGNORECASE | re.DOTALL
        )
        if section:
            text = section.group(1).strip()
            if len(text) > 20:
                return text[:500]

    # Fallback: first meaningful paragraph
    lines = (body or "").split("\n")
    for line in lines:
        stripped = line.strip()
        if len(stripped) > 30 and not stripped.startswith(("#", "- [", "|", "```")):
            return stripped[:500]

    return "[Scope not auto-detected — fill manually]"


def extract_constraints(body):
    """Extract constraints from issue body."""
    constraints = []

    # Look for "Constraints" or "Notes" sections
    for header in ["Constraints", "Notes", "Important", "Rules", "Do NOT"]:
        section = re.search(
            rf'(?:##\s*)?{header}[:\s]*\n(.*?)(?:\n##|\Z)',
            body or "", re.IGNORECASE | re.DOTALL
        )
        if section:
            text = section.group(1).strip()
            if text:
                constraints.append(text[:300])

    if not constraints:
        return "Follow existing code patterns. Do not modify unrelated files."

    return "\n".join(constraints)


# =============================================================================
# PROMPT GENERATORS
# =============================================================================

def generate_discover_prompt(target_files, open_issues):
    """Phase 1: Discover & propose a new bounty."""
    file_contents = ""
    for f in target_files:
        contents = fetch_file_contents(f)
        file_contents += f"\n--- {f} ---\n{contents}\n"

    issues_list = "\n".join(open_issues[:30]) if open_issues else "None found"

    return f"""You are Clawbot, an autonomous AI agent for the WattCoin ecosystem.

Analyze the following file(s) in the WattCoin repository (WattCoin-Org/wattcoin)
and identify ONE high-impact improvement that meets ALL criteria:

1. Directly advances agent infrastructure, node network, marketplace, or security
2. Clear, specific, and implementable (not vague or cosmetic)
3. Does NOT duplicate any existing open issue
4. Estimated effort: Medium tier

Target file(s): {', '.join(target_files)}

Current file contents:
```
{file_contents}
```

Existing open issues (do NOT duplicate):
{issues_list}

Output format (strict):
---
TITLE: [concise descriptive title]
BODY:
## Problem
[What's wrong or missing — be specific]

## Proposed Solution
[Exactly what to implement — reference functions/lines]

## Expected Impact
[Measurable improvement]

## Files to Modify
[List exact files]

## Acceptance Criteria
- [ ] [Specific testable criterion 1]
- [ ] [Specific testable criterion 2]
---"""


def generate_plan_prompt(issue, target_files):
    """Phase 2: Claim & plan implementation."""
    file_contents = ""
    for f in target_files:
        contents = fetch_file_contents(f)
        file_contents += f"\n--- {f} ---\n{contents}\n"

    return f"""You are Clawbot, claiming bounty issue #{issue['number']} in WattCoin-Org/wattcoin.

Issue: {issue['title']}
Bounty: {parse_bounty_amount(issue['title'])} WATT
Scope: {extract_scope(issue.get('body', ''))}
Target files: {', '.join(target_files)}
Constraints: {extract_constraints(issue.get('body', ''))}

Current code for target files:
```
{file_contents}
```

Create an implementation plan:
1. List every function/section that needs modification
2. For each change, describe WHAT changes and WHY
3. Identify any existing patterns in the codebase to reuse
4. List potential risks or breaking changes
5. Estimate lines of code added/modified/removed

Output format:
---
IMPLEMENTATION PLAN:

## Changes
1. [file:function] — [what changes] — [why]

## Reusable Patterns
- [existing function/pattern to reference]

## Risks
- [potential breaking change or edge case]

## Estimate
- Lines added: ~X | Modified: ~X | Removed: ~X
---"""


def generate_implement_prompt(issue, target_files, constraints=None):
    """Phase 3: Write the code."""
    file_contents = ""
    for f in target_files:
        contents = fetch_file_contents(f)
        file_contents += f"\n--- {f} ---\n{contents}\n"

    branch = f"clawbot/issue-{issue['number']}"
    scope = extract_scope(issue.get("body", ""))
    cons = constraints or extract_constraints(issue.get("body", ""))

    return f"""You are Clawbot, implementing bounty #{issue['number']} for WattCoin-Org/wattcoin.

Issue: {issue['title']}
Bounty: {parse_bounty_amount(issue['title'])} WATT
Scope: {scope}
Branch: {branch}

STRICT RULES:
- ONLY modify files listed in scope. No scope creep.
- Do NOT change hardcoded values unless the bounty explicitly requires it.
- Do NOT remove existing functionality. Additions and fixes only.
- Follow existing code patterns (imports, error handling, Discord notifications, data storage).
- All user-facing strings must say "AI" — no vendor-specific references.
- No personal identifiers in code or comments.

EXISTING PATTERNS TO FOLLOW:
- Data storage: load_json_data() / save_json_data() from pr_security.py
- Discord alerts: notify_discord(title, message, color, fields) from api_webhooks.py
- Error codes: from api_error_codes import E
- Solana payments: see send_node_payout() in api_nodes.py
- AI calls: from ai_provider import call_ai
- GitHub API: github_headers() pattern with GITHUB_TOKEN

Current code (target files):
```
{file_contents}
```

Constraints: {cons}

Generate the complete code changes as str_replace edits (old_str → new_str).
Ensure NO existing functionality is removed or broken."""


def generate_submit_prompt(issue, wallet=None):
    """Phase 4: Generate PR body."""
    wallet = wallet or DEFAULT_WALLET
    return f"""Generate PR body for bounty #{issue['number']} using this EXACT template:

---
## Bounty PR Submission

**Payout Wallet**: {wallet}

**Closes**: #{issue['number']}

---

## Description

[Describe what this PR does and how it addresses: {issue['title']}]

## Changes Made

[List specific changes made]

## Testing

[Describe testing performed]

## Checklist

- [x] I included my Solana wallet address above
- [x] This PR references the bounty issue number
- [x] My code follows the existing code style
- [x] I have tested my changes locally
---"""


def generate_full_prompt(issue, target_files, wallet=None):
    """Full run — all phases in one prompt."""
    file_contents = ""
    for f in target_files:
        contents = fetch_file_contents(f)
        file_contents += f"\n--- {f} ---\n{contents}\n"

    wallet = wallet or DEFAULT_WALLET
    branch = f"clawbot/issue-{issue['number']}"
    scope = extract_scope(issue.get("body", ""))
    constraints = extract_constraints(issue.get("body", ""))

    return f"""You are Clawbot, an autonomous AI agent for WattCoin-Org/wattcoin.

BOUNTY RUN — Issue #{issue['number']}
Title: {issue['title']}
Amount: {parse_bounty_amount(issue['title'])} WATT
Scope: {scope}
Target files: {', '.join(target_files)}
Constraints: {constraints}
Payout wallet: {wallet}
Branch: {branch}

RULES:
- ONLY modify listed target files
- Do NOT change hardcoded values unless bounty requires it
- Do NOT remove existing functionality
- Follow existing code patterns (Discord alerts, error codes, data storage)
- No vendor names in public strings — use "AI" only
- No personal identifiers in code/comments

Current code:
```
{file_contents}
```

TASKS:
1. Analyze the issue and create implementation plan
2. Write the code changes (show as str_replace edits: old → new)
3. Self-review against AI review criteria (score yourself)
4. Generate PR body (wallet, closes #{issue['number']}, description, changes, testing)

If self-review score < 9/10, fix issues before generating final output."""


# =============================================================================
# CLI
# =============================================================================

def main():
    parser = argparse.ArgumentParser(description="Clawbot Bounty Run — Prompt Generator")
    parser.add_argument("issue_number", nargs="?", type=int, help="GitHub issue number")
    parser.add_argument("--phase", choices=["discover", "plan", "implement", "submit", "full"],
                        default="full", help="Which phase to generate (default: full)")
    parser.add_argument("--files", type=str, help="Comma-separated target files (overrides auto-detect)")
    parser.add_argument("--wallet", type=str, help="Payout wallet (overrides default)")
    parser.add_argument("--output", type=str, help="Save prompt to file instead of stdout")

    args = parser.parse_args()

    # Discover phase doesn't need an issue
    if args.phase == "discover":
        if not args.files:
            print("❌ --files required for discover phase (e.g., --files api_nodes.py)")
            sys.exit(1)
        target_files = [f.strip() for f in args.files.split(",")]
        open_issues = fetch_open_issues()
        prompt = generate_discover_prompt(target_files, open_issues)
    else:
        if not args.issue_number:
            print("❌ issue_number required for this phase")
            parser.print_help()
            sys.exit(1)

        issue = fetch_issue(args.issue_number)

        # Determine target files
        if args.files:
            target_files = [f.strip() for f in args.files.split(",")]
        else:
            target_files = extract_target_files(issue.get("body", ""))
            if not target_files:
                print("⚠️  No target files detected in issue body. Use --files to specify.")
                print(f"   Issue body preview: {(issue.get('body') or '')[:200]}")
                sys.exit(1)

        print(f"📋 Issue #{args.issue_number}: {issue['title']}", file=sys.stderr)
        print(f"💰 Bounty: {parse_bounty_amount(issue['title'])} WATT", file=sys.stderr)
        print(f"📁 Target files: {', '.join(target_files)}", file=sys.stderr)
        print(f"🔧 Phase: {args.phase}", file=sys.stderr)
        print("---", file=sys.stderr)

        if args.phase == "plan":
            prompt = generate_plan_prompt(issue, target_files)
        elif args.phase == "implement":
            prompt = generate_implement_prompt(issue, target_files)
        elif args.phase == "submit":
            prompt = generate_submit_prompt(issue, args.wallet)
        else:  # full
            prompt = generate_full_prompt(issue, target_files, args.wallet)

    # Output
    if args.output:
        with open(args.output, "w") as f:
            f.write(prompt)
        print(f"✅ Prompt saved to {args.output}", file=sys.stderr)
    else:
        print(prompt)


if __name__ == "__main__":
    main()
