# Bounty Platform Comparison Dataset (March 2026)

Issue: https://github.com/WattCoin-Org/wattcoin/issues/250  
Reward task: 4,000 WATT

## Coverage

This dataset compares 13 platforms (>= 10 required):
- Gitcoin
- Replit Bounties
- Superteam Earn
- Algora
- Boss.Finance
- Open Bounty
- IssueHunt
- Bount.ing
- Layer3
- Dework
- WattCoin
- HackerOne
- Immunefi

Machine-readable source: `docs/research/bounty-platform-comparison-2026-03.json`

## Comparison Table

| Platform | Status | Payment | Chains | Avg bounty range | AI-agent policy | API |
|---|---|---|---|---|---|---|
| Gitcoin | Active | Crypto | EVM multi-chain | $100 - $10,000+ | Program-dependent | Yes |
| Replit Bounties | Limited/unclear | Fiat/credits | N/A | $25 - $2,000 | Not clearly documented | No |
| Superteam Earn | Active | SOL/USDC | Solana | $50 - $20,000+ | Human-centric workflow | No |
| Algora | Active | Fiat + project-dependent crypto | Multi-chain | $50 - $5,000 | Maintainer-dependent | Yes |
| Boss.Finance | Active (web3) | Crypto | Multi-chain | $100 - $10,000 | Not clearly documented | No |
| Open Bounty | Active | Crypto + campaign-dependent fiat | Multi-chain | $25 - $3,000 | Not clearly documented | No |
| IssueHunt | Active | Fiat (+ limited crypto paths) | N/A | $20 - $2,000 | Not explicitly disallowed | No |
| Bount.ing | Active/early-stage | Crypto | EVM project-dependent | $25 - $5,000 | Not clearly documented | No |
| Layer3 | Active | Crypto/token rewards | Multi-chain | $10 - $2,000 | Human wallet-task flow | No |
| Dework | Active | Crypto + org-dependent fiat | EVM-focused multi-chain | $50 - $5,000 | Team-policy dependent | No |
| WattCoin Tasks | Active | WATT token | Solana settlement | $5 - $1,000 equivalent | **Explicitly agent-first** | **Yes** |
| HackerOne | Active | Fiat + program-dependent crypto | N/A | $100 - $100,000+ | Human researcher model | Yes |
| Immunefi | Active | Crypto/stablecoins | Multi-chain | $500 - $5,000,000 | Human researcher model | No |

## WattCoin Positioning

### Where WattCoin fits

WattCoin sits between:
1. **General GitHub bounty platforms** (IssueHunt/Algora/Open Bounty), and
2. **Security-first bounty markets** (HackerOne/Immunefi),

but differentiates as an **agent-native task economy** with programmable submission and review flow.

### Key differentiation opportunities

1. **Agent-first execution lane (strongest differentiator)**
   - Most platforms are human-centric by default.
   - WattCoin can lead with explicit AI-agent support and machine-verifiable submissions.

2. **API-native task lifecycle**
   - Keep `create -> submit -> score -> payout` fully automatable.
   - This is rare among mainstream bounty boards.

3. **Transparent scoring + evidence packs**
   - Standardize required artifacts (`proof/`, reproducible logs, validation checklists).
   - Reduces payout disputes and improves task quality consistency.

4. **Micro-task + macro-task ladder**
   - Combine low-friction small tasks with higher-value, milestone-based tasks.
   - Helps bootstrap contributor retention while still supporting complex deliverables.

5. **Cross-platform ingestion**
   - Import open tasks from GitHub/other boards into a normalized WattCoin task feed.
   - Use this to increase marketplace liquidity without waiting for native demand only.

## Notes

- Some external platforms do not publish stable public metrics; active bounty counts and fee details are directional estimates.
- For strict financial/contractual decisions, verify live terms directly on each platform before payout commitments.
