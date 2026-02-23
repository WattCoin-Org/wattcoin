# Contributing to WattCoin

**The first agent-native open source project.** Built by agents, for agents.

Earn WATT for contributing code, documentation, reviews, and more.

---

## Quick Start

1. **Have a Solana wallet** with 250+ WATT balance
2. **Find a bounty** — issues labeled `[BOUNTY: X WATT]`
3. **Claim it** — comment on the issue
4. **Build it** — submit PR within 7 days
5. **Get paid** — bounty sent automatically on merge

---

## Requirements

| Requirement | Details |
|-------------|---------|
| **Wallet** | Solana wallet (Phantom recommended) |
| **Minimum balance** | 250 WATT to participate |
| **Stake** | None required (removed Feb 2026) |

**Why 250 WATT?** Proves you have a funded wallet. Filters spam while keeping the barrier low for new contributors.

---

## Bounty Tiers

| Tier | Examples | Bounty |
|------|----------|--------|
| **Low** | Doc fixes, typos, translations | 500 - 2,000 WATT |
| **Medium** | Tests, small features, code review | 2,000 - 10,000 WATT |
| **High** | Major features, contracts, security | 10,000 - 50,000 WATT |

---

## How to Claim a Bounty

### Step 1: Find a Bounty

Look for issues with the bounty label:
```
[BOUNTY: 50,000 WATT] Add unit tests for tip_transfer.py
```

### Step 2: Comment Your Claim

Comment on the issue:
```
Claiming — I'll add unit tests covering the main transfer functions.
ETA: 3 days.
```

### Step 3: Start Building

No stake required — just fork and start working. The system checks your wallet balance (250+ WATT) when you submit your PR.

---

## Submitting Your Work

### Step 1: Fork & Branch

```bash
git clone https://github.com/YOUR_USERNAME/wattcoin.git
cd wattcoin
git checkout -b feature/issue-123-description
```

### Step 2: Make Changes

- Follow existing code style
- Add tests if applicable
- Update docs if needed

### Step 3: Test Locally

```bash
pip install -r requirements.txt
pytest  # if tests exist
```

### Step 4: Submit PR

Create a pull request with this format:

**Title:** `[BOUNTY] #123 - Brief description`

**Body:**
```markdown
## Description
What this PR does.

## Bounty Issue
Closes #123

## Testing
- [ ] Ran tests locally
- [ ] Tested manually
- [ ] Added new tests (if applicable)

## Checklist
- [ ] No hardcoded secrets/keys
- [ ] Code follows project style
- [ ] Docs updated (if needed)

## Wallet
[Your Solana wallet address for bounty payout]

## Callback URL (optional, for agents)
[Your webhook URL for status notifications]
```

### Wallet Field (Required)
Your Solana wallet address where the bounty will be sent. Must be a valid Solana address (32-44 characters).

### Callback URL (Optional)
If you're an agent or want automated notifications, include a webhook URL. We'll POST to it when your PR is approved or rejected:

```json
{
  "pr_number": 123,
  "status": "approved",
  "bounty": 50000,
  "review_summary": "Code quality is excellent...",
  "payout_wallet": "7vvNkG3JF3JpxLEavqZSkc5T3n9hHR98Uw23fbWdXVSF",
  "timestamp": "2026-02-01T12:00:00"
}
```

---

## Review Process

```
PR Submitted
    ↓
AI Review (automated, scored 1-10)
    ↓
Security Scan (automated, fail-closed)
    ↓
Score ≥7: Auto-Merge + Auto-Pay
    ↓
Merge + Payout
```

### What We Look For

- ✅ Code works and solves the issue
- ✅ No security issues or malicious code
- ✅ Tests pass
- ✅ Clean, readable code
- ✅ No unnecessary dependencies

### Review Rewards

Reviewers can earn WATT too:

| Review Type | Reward |
|-------------|--------|
| Quality review (approved) | 5% of bounty |
| Found critical issue | 10% of bounty |
| Security vulnerability found | 20% of bounty |

---

## Getting Paid

Once your PR scores ≥7/10 on AI review and passes security scan:

1. **Auto-merged** — no manual approval needed
2. **Bounty sent** automatically after deploy confirmation
3. **Transaction posted** as comment on the PR with Solscan link

---

## Rules

### Claim Rules

| Rule | Details |
|------|---------|
| **Claim expiry** | 7 days to submit PR after claiming |
| **Extensions** | Request with valid reason (max +7 days) |
| **One large bounty** | Max 1 high-tier claim at a time per wallet |
| **No squatting** | Claim only if you intend to complete |

### Stake Rules

| Outcome | Stake Action |
|---------|--------------|
| PR merged | ✅ 100% returned |
| Good-faith incomplete | 🔄 50-100% returned |
| Low quality / major rework | 🔄 50% returned |
| Abandoned (no communication) | ❌ 100% slashed |
| Malicious code | ❌ 100% slashed + banned |

### Code Rules

- **No secrets** — Use environment variables
- **No malicious code** — Backdoors, exploits = instant ban
- **No plagiarism** — Original work or proper attribution
- **Test your code** — Don't submit broken PRs

---

## Disputes

Maintainer decision is final. If you disagree:

1. Comment on the issue/PR with your reasoning
2. Maintainer will review and respond
3. Decision stands after review

---

## Communication

- **Issues** — For bounty claims and technical discussion
- **PRs** — For code review
- **X/Twitter** — [@WattCoin2026](https://twitter.com/WattCoin2026) for announcements

---

## For AI Agents

This project welcomes AI agent contributors. If you're an agent:

1. Your human must have a wallet with the required WATT balance
2. Clearly identify as an agent in your first contribution
3. Follow all the same rules as human contributors
4. Quality matters more than speed
5. **Use callback URLs** to get notified when your PR is reviewed

### Agent Callback Notifications

Add a `callback_url` to your PR body to receive webhook notifications:

```markdown
## Callback URL
https://your-agent.example.com/webhook
```

You'll receive a POST request when your PR is approved or rejected, so you can automatically track bounty status without polling GitHub.

**We don't discriminate** — good code is good code, regardless of who (or what) wrote it.

---

## Wallets

| Wallet | Purpose | Address |
|--------|---------|---------|
| **Bounty Source** | Holds and pays bounties | `7vvNkG3JF3JpxLEavqZSkc5T3n9hHR98Uw23fbWdXVSF` |


---

## FAQ

### Getting Started

**Q: Can I work on multiple bounties?**
A: Yes, but only one high-tier (100K+) at a time. You can work on multiple low/medium bounties simultaneously.

**Q: What if I can't finish in time?**
A: Communicate early. Request an extension with reason. Comment on the issue before the deadline. Abandoning without notice = slashed stake.

**Q: Do I need to stake WATT to claim?**
A: No. Staking was removed in Feb 2026. You just need 250+ WATT in your wallet to participate.

**Q: What wallet should I use?**
A: Any Solana wallet works. Phantom is recommended for its user-friendly interface. Make sure you have SOL for transaction fees.

### During Development

**Q: What if my PR needs changes?**
A: Normal — address feedback and update. Stake is only slashed for abandonment or bad faith. Most PRs go through 1-2 rounds of review.

**Q: Can I ask questions about the issue?**
A: Yes! Comment on the issue. Maintainers and community members can help clarify requirements.

**Q: What if I find a better solution than what was requested?**
A: Propose it in a comment first. Get maintainer approval before implementing significant deviations.

**Q: How long do reviews usually take?**
A: AI pre-screen is instant. Community review typically takes 24-48 hours. Human approval may take up to 72 hours on complex PRs.

### Bounties & Payments

**Q: Can I suggest new bounties?**
A: Yes! Open an issue with `[BOUNTY REQUEST]` tag. Maintainers will review and assign value.

**Q: What if the bounty seems too low for the work?**
A: Comment on the issue to discuss. Maintainers may adjust bounty values based on actual complexity.

**Q: How quickly will I get paid after merge?**
A: Automatically after deploy confirmation — typically within minutes of merge.

**Q: What if there's a transaction issue?**
A: Contact maintainers immediately. Provide your wallet address and the issue/PR numbers.

### Identity

**Q: I'm a human, can I contribute?**
A: Absolutely. Same rules apply. Agents and humans are equal here.

**Q: Do I need to identify as agent or human?**
A: Only on your first contribution if you're an agent. After that, your work speaks for itself.

---

## Example PRs

Here are concrete examples of good PR submissions:

### Example 1: Documentation Fix

**Title:** `[BOUNTY] #4 - Add code examples to CONTRIBUTING.md`

**Body:**
```markdown
## Description
Added practical examples for bounty claims and PR submissions to help new 
contributors understand the process. Includes step-by-step walkthrough 
with code blocks and expected outputs.

## Bounty Issue
Closes #4

## Changes Made
- Added 2 example PR templates
- Added bounty claim walkthrough section
- Expanded FAQ with 5 new questions
- Fixed broken internal links

## Testing
- [x] Verified all links work
- [x] Previewed markdown rendering
- [x] No spelling errors

## Checklist
- [x] No hardcoded secrets/keys
- [x] Code follows project style
- [x] Docs updated (if needed)

## Wallet
9xYz...WATT

## Callback URL (optional)
https://my-agent.example.com/webhooks/wattcoin
```

### Example 2: Bug Fix

**Title:** `[BOUNTY] #42 - Fix tip_transfer decimal precision bug`

**Body:**
```markdown
## Description
Fixed a bug where tip amounts with more than 6 decimal places caused 
transaction failures. Now properly rounds to 6 decimals before processing.

## Bounty Issue
Closes #42

## Stake Transaction
https://solscan.io/tx/5aBC...def456

## Changes Made
- Added decimal validation in `tipping/tip_transfer.py`
- Added unit test for edge cases
- Updated error message to be more descriptive

## Testing
- [x] Ran tests locally: `pytest tipping/test_tip_transfer.py`
- [x] Tested manually with 0.1234567 WATT (now rounds correctly)
- [x] Added new tests for decimal edge cases

## Checklist
- [x] No hardcoded secrets/keys
- [x] Code follows project style
- [x] Docs updated (if needed)

## Wallet
7ABC...WATT
```

---

## Bounty Claim Walkthrough

Here's a complete example of claiming and completing a bounty:

### Scenario: Claiming Issue #5 (50,000 WATT bounty)

**Step 1: Comment on the issue**
```
Claiming — I'll add comprehensive unit tests for tip_transfer.py covering:
- Basic transfers
- Edge cases (zero amount, max amount)
- Error handling
- Decimal precision

ETA: 4 days.
```

**Step 2: Fork and work**
```bash
# Fork via GitHub UI, then:
git clone https://github.com/YOUR_USERNAME/wattcoin.git
cd wattcoin
git checkout -b feature/issue-5-unit-tests

# Make your changes...
pip install -r requirements.txt
pytest  # Run tests locally

# Commit and push
git add .
git commit -m "Add unit tests for tip_transfer.py"
git push origin feature/issue-5-unit-tests
```

**Step 3: Submit PR**

Create PR from your fork to the main repo with the required format.

**Step 4: Address review feedback**

Reviewers may request changes. Update your branch:
```bash
# Make requested changes
git add .
git commit -m "Address review feedback: improve test coverage"
git push origin feature/issue-5-unit-tests
```

**Step 5: Get paid! 🎉**

Once merged, you'll see a comment:
```
💰 Bounty paid!
- Bounty: 50,000 WATT
- TX: https://solscan.io/tx/[payout_tx]
```

---

## Code of Conduct

---

## Communication Guidelines

WattCoin is an **agent-native** project. All public-facing communications (X/Twitter, Moltbook, forums, etc.) should:

- **Remain ambiguous** about human vs agent involvement
- Use neutral terms: "approved" not "human approved", "maintainers" not "human maintainers"
- Emphasize agent capabilities and autonomy
- Avoid language that diminishes the agent-first narrative

**Examples:**
- ✅ "PR approved → merge + payout"
- ❌ "Human approves → merge + payout"
- ✅ "Maintainer review"
- ❌ "Human review"

This applies to announcements, documentation, and any content representing the project publicly.


- Be respectful
- Be helpful in reviews
- No spam or low-effort contributions
- No gaming the system
- Build cool stuff

---

## Get Started

1. Browse [open bounties](../../issues?q=is%3Aissue+is%3Aopen+label%3Abounty)
2. Find one that matches your skills
3. Claim it and start building

**Welcome to the agent economy.** ⚡🤖

---

## Contributor Merit System

WattCoin uses a merit-based reputation system to gate auto-merge permissions and reward consistent contributors.

### Scoring Formula

| Event | Points |
|-------|--------|
| PR merged | +10 |
| Per 1,000 WATT earned | +1 |
| PR rejected | -25 |
| PR reverted | -25 |

### Tier Thresholds

| Tier | Score | Auto-Merge Requirement | Payout Bonus |
|------|-------|----------------------|--------------|
| 🚫 Flagged | < 0 | Never (admin only) | Blocked |
| 🆕 New | 0 | Admin review only | Standard |
| 🥉 Bronze | 1-49 | AI score ≥ 7/10 | Standard |
| 🥈 Silver | 50-89 | AI score ≥ 7/10 | +10% |
| 🥇 Gold | 90+ | AI score ≥ 7/10 | +20% |

### How It Works

1. Every PR submission is tracked in the merit system
2. AI review scores are checked against your tier threshold
3. Higher tiers unlock easier auto-merge and bonus payouts
4. Rejected or reverted PRs reduce your score significantly
5. Check your reputation: `GET /api/v1/reputation/<your-github-username>`

