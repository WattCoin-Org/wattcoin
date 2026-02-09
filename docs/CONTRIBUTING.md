# WattCoin Contributor Onboarding Guide ⚡

Welcome to the **WattCoin Developer Community**! This guide will walk you through your first contribution and help you earn your first WATT.

## 🚀 Prerequisites

1.  **GitHub Account:** 30+ days old with at least 1 public repository.
2.  **Solana Wallet:** To receive your WATT payouts. (We recommend Phantom or Solflare).
3.  **Python 3.10+:** Most of our ecosystem is built on Python.

---

## 🛠 Step 1: Find a Bounty

1.  Navigate to our [Issues](https://github.com/WattCoin-Org/wattcoin/issues) page.
2.  Look for labels:
    *   `bounty`: Tasks with a WATT reward.
    *   `good first issue`: Ideal for new contributors.
    *   `SwarmSolve`: High-value solution requests.

## 🔗 Step 2: Claim Your Task

Before you start coding, you must claim the task to prevent duplicate work.

*   **For Standard Bounties:** Comment on the issue: `/claim <your-solana-wallet>`.
*   **For SwarmSolve Solutions:** Call the API:
    ```bash
    curl -X POST https://api.wattcoin.org/api/v1/solutions/{id}/claim \
         -d '{"github_user": "your_username", "wallet": "your_solana_address"}'
    ```

## 💻 Step 3: Develop & Test

1.  **Fork** the repository.
2.  **Clone** your fork locally.
3.  Create a new branch: `git checkout -b feature/bounty-title`.
4.  **Write your code.** Ensure you follow the project's coding standards (PEP 8 for Python).
5.  **Test your changes.** If you are working on the API, run the test suite: `pytest tests/`.

## 📦 Step 4: Submit Your Pull Request

1.  Push your changes to your fork.
2.  Open a **Pull Request (PR)** to the `main` branch of the official repo.
3.  **Crucial:** Include your Solana wallet in the PR description using this EXACT format:
    `**Payout Wallet**: your_solana_address_here`
4.  Reference the issue number (e.g., `Closes #141`).

## 💰 Step 5: Review & Payout

1.  **AI Review:** Our automated bot will check your code for security and quality.
2.  **Admin Approval:** A human admin will perform a final check.
3.  **Payout:** Once merged, the WATT reward is automatically sent to your wallet.

---

## 🆘 Need Help?
- Join our [Discord](https://discord.gg/K3sWgQKk)
- Tag a maintainer in the issue comments.

Let's build the agentic economy together! 🥧⚡
