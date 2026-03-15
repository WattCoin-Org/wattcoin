# WattCoin PR Bounty System

Automated PR review and payout system for WattCoin bounties.

## Overview

This system enables:
1. **Automated PR Reviews** - Grok AI reviews submitted PRs
2. **Payout Queue** - Merged PRs automatically queue for payment
3. **Security Controls** - Rate limiting, code scanning, emergency pauses
4. **Manual Approval** - All payouts require admin confirmation

## Architecture

```
┌─────────────────┐
│  Contributor    │
│  Submits PR     │
└────────┬────────┘
         │
         ▼
┌─────────────────────────────────┐
│  POST /api/v1/review_pr         │
│  - Validates format             │
│  - Checks rate limits           │
│  - Scans for dangerous code     │
│  - Calls Grok for review        │
│  - Posts review comment         │
└────────┬────────────────────────┘
         │
         ▼
┌─────────────────────────────────┐
│  Maintainer Reviews & Merges    │
└────────┬────────────────────────┘
         │
         ▼
┌─────────────────────────────────┐
│  POST /webhooks/github          │
│  - Triggered on PR merge        │
│  - Extracts wallet & amount     │
│  - Verifies review passed       │
│  - Queues payout                │
│  - Posts status comment         │
└────────┬────────────────────────┘
         │
         ▼
┌─────────────────────────────────┐
│  Admin Dashboard                │
│  - Views pending payouts        │
│  - Approves/rejects             │
│  - Executes Solana transfer     │
└─────────────────────────────────┘
```

## Components

### 1. pr_security.py
Security utilities and validation:
- Wallet validation (Base58, length checks)
- Rate limiting (5 PRs/day, 24h cooldown)
- Code scanning (dangerous patterns)
- Security event logging
- Emergency controls

### 2. api_pr_review.py
PR review endpoint:
- **Endpoint**: `POST /api/v1/review_pr`
- Validates PR format
- Calls Grok API for code review
- Scans diff for security issues
- Posts review as GitHub comment
- Stores review in database

### 3. api_webhooks.py
GitHub webhook handler:
- **Endpoint**: `POST /webhooks/github`
- Listens for PR merge events
- Verifies signature
- Validates review passed
- Extracts wallet & bounty amount
- Queues payout for approval

### 4. Data Files
JSON-based storage:
- `pr_reviews.json` - Review history
- `pr_payouts.json` - Payout queue
- `pr_rate_limits.json` - Rate limiting
- `security_logs.json` - Security events

## Flow for Contributors

### Step 1: Submit PR

Create PR with this format in the body:

```markdown
**Closes**: #123
**Payout Wallet**: 7vvNkG3JF3JpxLEavqZSkc5T3n9hHR98Uw23fbWdXVSF

## Description
[What you changed]

## Changes Made
- [List changes]
```

### Step 2: Request Review

Call the review endpoint (or maintainer calls it):

```bash
curl -X POST https://your-backend-url.example.com/api/v1/review_pr \
  -H "Content-Type: application/json" \
  -d '{
    "pr_url": "https://github.com/WattCoin-Org/wattcoin/pull/123",
    "bounty_issue_id": 45
  }'
```

Grok will post a review comment with score and feedback.

### Step 3: Address Feedback

If score < 8, make improvements and request re-review.

### Step 4: Merge

Maintainer reviews and merges the PR.

### Step 5: Auto-Payout Queue

On merge, webhook:
- Extracts your wallet
- Gets bounty amount from issue
- Queues payout
- Posts confirmation comment

### Step 6: Admin Approval

Admin approves payout → you receive WATT!

## Security Features

### Rate Limiting
- **5 PRs per 24 hours** per wallet
- **24h cooldown** after receiving payout
- Prevents spam and farming

### Code Scanning
Flags dangerous patterns:
- `subprocess`, `os.system`
- `eval`, `exec`
- `private_key`, `SECRET_KEY`
- SQL injection attempts
- File system operations

### Wallet Validation
- Must be valid Solana address
- Base58 encoding check
- Length validation (32-44 chars)
- Required format in PR body

### Emergency Controls

Environment variables:
```bash
PAUSE_PR_REVIEWS=true    # Stop new reviews
PAUSE_PR_PAYOUTS=true    # Stop all payouts
REQUIRE_DOUBLE_APPROVAL=true  # Need 2 admins
```

## API Reference

### POST /api/v1/review_pr

Submit a PR for automated review.

**Request:**
```json
{
  "pr_url": "https://github.com/WattCoin-Org/wattcoin/pull/123",
  "bounty_issue_id": 45
}
```

**Response (Success):**
```json
{
  "success": true,
  "review": {
    "pass": true,
    "score": 9,
    "feedback": "Excellent contribution that improves error handling...",
    "suggested_changes": [
      "Consider adding unit tests",
      "Update documentation"
    ],
    "concerns": []
  },
  "security": {
    "is_safe": true,
    "warnings": []
  },
  "pr_number": 123,
  "wallet": "7vvNkG3JF...",
  "remaining_prs": 4,
  "comment_posted": true
}
```

**Response (Rate Limited):**
```json
{
  "success": false,
  "error": "Rate limit exceeded: 5 PRs per 24h",
  "remaining_prs": 0
}
```

**Response (Failed Review):**
```json
{
  "success": true,
  "review": {
    "pass": false,
    "score": 5,
    "feedback": "Needs significant improvements...",
    "suggested_changes": ["Fix security issues", "Add tests"],
    "concerns": ["Potential SQL injection", "Missing input validation"]
  }
}
```

### POST /webhooks/github

GitHub webhook receiver (internal, called by GitHub).

**Handled Events:**
- `pull_request` with `action: closed` and `merged: true`

**Actions:**
1. Extract wallet from PR body
2. Find Grok review in database
3. Verify review passed (score ≥ 8)
4. Get bounty amount from issue
5. Queue payout
6. Post status comment

## Database Schema

### pr_reviews.json
```json
{
  "reviews": [
    {
      "pr_number": 123,
      "pr_url": "https://...",
      "wallet": "7vvNkG...",
      "bounty_issue_id": 45,
      "timestamp": "2026-02-04T12:00:00Z",
      "review": {
        "pass": true,
        "score": 9,
        "feedback": "...",
        "suggested_changes": [],
        "concerns": []
      },
      "security": {
        "is_safe": true,
        "warnings": []
      },
      "pr_data": {
        "title": "Fix bug in scraper",
        "author": "contributor123",
        "merged": false,
        "state": "open"
      }
    }
  ]
}
```

### pr_payouts.json
```json
{
  "payouts": [
    {
      "id": 1,
      "pr_number": 123,
      "wallet": "7vvNkG...",
      "amount": 50000,
      "bounty_issue_id": 45,
      "status": "pending",
      "queued_at": "2026-02-04T12:00:00Z",
      "approved_by": null,
      "approved_at": null,
      "tx_signature": null,
      "paid_at": null,
      "review_score": 9,
      "requires_double_approval": false,
      "approval_count": 0
    }
  ]
}
```

### pr_rate_limits.json
```json
{
  "7vvNkG...": {
    "pr_submissions": [1738675200.0, 1738761600.0],
    "last_payout": 1738848000.0
  }
}
```

### security_logs.json
```json
{
  "events": [
    {
      "timestamp": "2026-02-04T12:00:00Z",
      "type": "dangerous_code",
      "details": {
        "pr_number": 123,
        "wallet": "7vvNkG...",
        "warnings": [
          {
            "pattern": "os.system",
            "match": "os.system(",
            "context": "os.system('rm -rf')"
          }
        ]
      }
    }
  ]
}
```

## Admin Operations

### View Pending Payouts

Check `data/pr_payouts.json` for payouts with `status: "pending"`.

### Approve Payout

(Session 2 - Admin Dashboard will provide UI)

Manually:
1. Update payout status to "approved"
2. Add `approved_by` and `approved_at`
3. Execute Solana transfer
4. Update with `tx_signature` and `paid_at`
5. Record payout in rate limits

### View Security Logs

```bash
cat data/security_logs.json | jq '.events | .[-10:]'
```

### Clear Rate Limit

Edit `data/pr_rate_limits.json` and remove wallet entry.

### Emergency Pause

```bash
# In Railway environment variables:
PAUSE_PR_REVIEWS=true
PAUSE_PR_PAYOUTS=true
```

## Grok Review Criteria

Grok evaluates PRs on:

1. **Functionality** (35%)
   - Does it work?
   - Does it solve the issue?
   - Any bugs introduced?

2. **Code Quality** (25%)
   - Readable and maintainable
   - Follows existing patterns
   - Proper error handling

3. **Security** (25%)
   - No vulnerabilities
   - No dangerous patterns
   - Input validation

4. **Scope** (15%)
   - Changes match description
   - No unrelated modifications
   - Focused and atomic

**Scoring:**
- 10: Perfect, production-ready
- 8-9: Good, passes review
- 6-7: Needs minor improvements
- 4-5: Significant issues
- 1-3: Reject

**Pass Threshold**: ≥8/10

## Troubleshooting

### PR Review Fails

**Error: "Missing wallet in PR body"**
- Ensure wallet address in exact format: `**Payout Wallet**: address`

**Error: "Rate limit exceeded"**
- Wait 24 hours or contact admin to reset

**Error: "Invalid wallet address"**
- Verify it's a valid Solana address (32-44 chars, Base58)

### Webhook Not Triggering

1. Check webhook is active in GitHub settings
2. Verify secret matches `GITHUB_WEBHOOK_SECRET`
3. Check `/webhooks/health` endpoint
4. Look for delivery errors in GitHub webhook settings

### Payout Not Queued

1. Verify PR was merged (not just closed)
2. Check review passed (score ≥ 8)
3. Verify bounty issue referenced in PR
4. Check `data/security_logs.json` for blocks

## Testing

### Manual Test Flow

1. Create test bounty issue with title: `[BOUNTY: 10,000 WATT] Test Issue`
2. Create PR with proper wallet format
3. Call review endpoint
4. Verify Grok comment posted
5. Merge PR
6. Check payout queued
7. Verify webhook comment posted

### Unit Tests

(To be added in Session 2)

## Changelog

### v1.0.0 (Session 1 - Feb 4, 2026)
- Initial implementation
- PR review endpoint
- GitHub webhook handler
- Security module
- Rate limiting
- Code scanning
- Data storage
- Emergency controls

## Next: Session 2

Planned for next session:
- Admin dashboard for payout approval
- Payout execution UI
- Review history viewer
- Enhanced code scanning
- Unit tests
- End-to-end testing

---

**Questions?** Check CONTRIBUTING.md or contact maintainers.
