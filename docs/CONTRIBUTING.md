# Contributor Onboarding Guide

Welcome to WattCoin! This guide will walk you through the process of completing your first bounty and earning WATT.

## 1. Prerequisites
- **GitHub Account**: Required to submit Pull Requests and track issues.
- **Solana Wallet**: (e.g., Phantom, Solflare) to receive your WATT payouts.
- **Basic Git Knowledge**: You should be comfortable with cloning, branching, and pushing code.

## 2. Finding a Bounty
Bounties are task-based rewards for improving the WattCoin ecosystem. You can find them in:
- **GitHub Issues**: Browse issues in this repository with the `bounty` label.
- **API**: Query `GET /api/v1/bounties` to see a list of active tasks and rewards.
- **Website**: Visit the live Bounty Board at [wattcoin.org](https://wattcoin.org).

## 3. Claiming a Bounty
To ensure work isn't duplicated, we follow a simple claiming process:
1. **Comment**: Reply to the issue stating "I'd like to work on this."
2. **Stake Requirement**: Some high-value bounties require a 10% "Commitment Stake." If required, follow the issue instructions to send the stake to the Treasury wallet: `Atu5phbGGGFogbKhi259czz887dSdTfXwJxwbuE5aF5q`. Your stake is returned upon successful merge.

## 4. Setting up the Development Environment
1. **Fork and Clone**: Fork the repository to your own account and clone it:
   ```bash
   git clone https://github.com/YOUR_USERNAME/wattcoin.git
   ```
2. **Install Dependencies**:
   ```bash
   pip install -r requirements.txt
   ```
3. **Verify Installation**: Run the test suite to ensure your environment is configured correctly:
   ```bash
   pytest tests/
   ```

## 5. Submitting a PR
When your work is ready for review:
1. **Create a Branch**: `git checkout -b fix/issue-name`
2. **Commit and Push**: `git push origin fix/issue-name`
3. **Open Pull Request**: Submit your PR to the `main` branch of the official repository.
4. **Wallet Address**: You **must** include your Solana wallet address in the PR description to receive payment.

### PR Description Template
```markdown
## Overview
Summary of the changes made.

## Issue Linked
Closes #ISSUE_NUMBER

## Solana Wallet Address
[PASTE_YOUR_SOLANA_WALLET_ADDRESS_HERE]
```

## 6. AI Review Process
Every contribution is reviewed by an autonomous AI evaluator to ensure high standards.
- **Automated Feedback**: The AI checks for logic errors, security flaws, and code style.
- **Merge Threshold**: Contributions must achieve a quality score of **≥9/10**. If your score is lower, the AI will provide a detailed breakdown of what needs to be fixed.

## 7. Getting Paid
- **Merge & Payout**: Once an admin approves and merges your PR, the payout is triggered automatically.
- **Timeline**: WATT is usually sent to your wallet within 4 hours.
- **Verification**: You can check the transaction on [Solscan](https://solscan.io) by searching for your wallet address.

## 8. Building Reputation
Regular contributors earn points that unlock bonuses:
- **Contributor Tier**: (5+ merged PRs) - 10% bonus on all future bounties.
- **Core Tier**: (20+ merged PRs) - 25% bonus + early access to high-value "Maintainer-only" bounties.

Check your current standing: `https://wattcoin-production-81a7.up.railway.app/api/v1/reputation/<your-github-username>`

---

Happy Hacking! ⚡🤖
