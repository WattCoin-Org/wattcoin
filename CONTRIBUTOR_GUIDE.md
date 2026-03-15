# WattCoin Contributor Guide: Bounties → PR → Payout

Welcome 👋 This guide walks you through the full WattCoin bounty flow, from finding tasks to getting paid.

---

## Quick Start Checklist

- [ ] Find an open bounty issue in the repo
- [ ] Fork the repo and create a focused branch
- [ ] Complete the requested change with minimal scope
- [ ] Open a PR that references the issue
- [ ] Add payout wallet in PR body:

```md
**Payout Wallet**: <your-solana-wallet-address>
```

- [ ] Wait for AI review + score decision
- [ ] If approved (>= 9/10), PR can be merged and paid

---

## 1) Browse Open Bounties on GitHub

Go to the WattCoin issue list and filter for open bounty tasks.

Suggested filters:
- label: `bounty`
- state: `open`
- optionally `agent-task` for automation-focused work

Tips:
- Prefer tasks with clear acceptance criteria
- Check comments/PRs first to avoid duplicate work
- Start with small or docs-focused issues if you're new

---

## 2) Fork the Repo and Create a Branch

1. Fork `WattCoin-Org/wattcoin` to your GitHub account.
2. Clone your fork locally.
3. Create a branch named after the issue (example):

```bash
git checkout -b feat/bounty-216-contributor-guide
```

Branch naming suggestions:
- `feat/bounty-<issue-number>-<short-slug>`
- `fix/bounty-<issue-number>-<short-slug>`
- `docs/bounty-<issue-number>-<short-slug>`

Keep each branch focused on one bounty.

---

## 3) Include Payout Wallet in PR Body

Your PR should include your Solana payout address exactly in this format:

```md
**Payout Wallet**: <address>
```

Example:

```md
**Payout Wallet**: 9xQeWvG816bUx9EPf2vE9M9x5VfQ4G9fN9uY7x2m3kAb
```

Why this matters:
- The payout parser expects this format
- Missing/invalid wallet can delay or block payment

---

## 4) Submit PR and Reference the Bounty Issue

Open a PR against `WattCoin-Org/wattcoin:main` and reference the issue in the PR body.

Use one of these lines:
- `Closes #216`
- `Fixes #216`
- `Resolves #216`

Recommended PR structure:
- **Summary**: what changed and why
- **Scope**: what is intentionally not changed
- **Validation**: tests/commands run
- **Payout Wallet** line

Keep PRs minimal and easy to review.

---

## 5) AI Review Process (What It Checks)

WattCoin bounties use automated review/scoring. The AI review typically checks:

- Requirement coverage (did you satisfy issue acceptance criteria?)
- Correctness and safety
- Scope discipline (no unrelated refactors)
- Code/documentation quality and clarity
- Validation evidence (tests, lint, or compile checks)

### Scoring rubric (typical)

- **9/10 or above**: passes threshold for merge/payment flow
- **Below 9/10**: usually needs revisions before payout eligibility

Tip: explicitly map each issue requirement to a change in your PR description.

---

## 6) Auto-merge and Payment Flow

Typical flow after submission:

1. AI reviewer scores your PR.
2. If score meets threshold and checks pass, PR is approved for merge.
3. Merge happens (automatic or maintainer-triggered, depending on repo settings).
4. Payment job reads bounty + payout wallet info.
5. WATT payout is sent to your listed Solana wallet.

Keep your wallet line unchanged after review to avoid payout mismatches.

---

## 7) Merit System and Tier Bonuses

WattCoin may apply contributor reputation/merit over time.

Common patterns:
- Consistent high-quality submissions improve trust score
- Faster review/approval for proven contributors
- Tiered bonuses or better access to higher-value bounties
- Penalties for spam, low-effort PRs, or abusive behavior

Best way to build merit: small, correct, reliable PRs.

---

## Common Rejection Reasons (and How to Avoid Them)

1. **Missing payout wallet format**
   - Problem: wallet not included or wrong field name
   - Fix: include exact line `**Payout Wallet**: <address>`

2. **Issue not actually addressed**
   - Problem: PR changes are adjacent but don't satisfy acceptance criteria
   - Fix: checklist every requirement in PR body

3. **Scope creep / unrelated edits**
   - Problem: large refactors mixed with bounty fix
   - Fix: keep diffs minimal and issue-focused

4. **No validation evidence**
   - Problem: no test/lint/compile output or verification steps
   - Fix: include commands run and outcomes

5. **Broken references**
   - Problem: PR doesn't link issue correctly
   - Fix: include `Closes #<issue>` in PR body

6. **Quality issues**
   - Problem: unclear docs, poor naming, missing edge cases
   - Fix: tighten wording, add tests/examples where needed

---

## FAQ

### Q1) Are there rate limits for submissions?
Yes, anti-spam/rate controls may apply to PR frequency or review attempts. If your PR is rejected, revise and resubmit instead of opening many duplicate PRs.

### Q2) What wallet formats are accepted?
Use a valid **Solana wallet address**. Keep it plain text in the exact PR-body format shown above.

### Q3) Can I submit multiple bounties at once?
Yes, but one focused PR per bounty is strongly recommended. Avoid mixing multiple bounty scopes in one PR.

### Q4) What happens if multiple people submit for the same issue?
Maintainers/review system decide based on quality, correctness, and policy. First submitted is not always first paid.

### Q5) Can accounts be banned?
Yes. Spam, plagiarism, malicious code, or repeated low-quality abuse can lead to disqualification/bans.

### Q6) I forgot to include wallet in my first PR description. What now?
Edit the PR body and add:

```md
**Payout Wallet**: <address>
```

Then leave a comment noting the update.

---

## Suggested PR Template Snippet

```md
## Summary
- <what changed>

## Validation
- <command/test 1>
- <command/test 2>

Closes #<issue-number>

**Payout Wallet**: <your-solana-wallet-address>
```

Good luck, and thanks for contributing to WattCoin 🚀
