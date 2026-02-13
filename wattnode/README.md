# WattNode

**Earn WATT by running a light node on your Raspberry Pi or desktop.**

WattNode connects to the WattCoin network and fulfills jobs (web scraping, AI inference) for requesters. You earn **70%** of each job's payment in WATT.

## 🖥️ Windows GUI (Recommended for Desktop)

For a point-and-click experience, use the Windows GUI app:

**[Download WattNode-Setup.exe](https://github.com/WattCoin-Org/wattcoin/releases)** or run from source:

```powershell
cd wattnode
pip install -r requirements_gui.txt
python wattnode_gui.py
```

See [README_GUI.md](README_GUI.md) for full GUI documentation.

---

## 🐧 Command Line (Linux/Raspberry Pi)

## Quick Start

```bash
# 1. Clone repo
git clone https://github.com/WattCoin-Org/wattcoin.git
cd wattcoin/wattnode

# 2. Install dependencies
pip install -r requirements.txt

# 3. Configure
cp config.example.yaml config.yaml
# Edit config.yaml with your wallet address

# 4. Stake 10,000 WATT to treasury
# Send to: Atu5phbGGGFogbKhi259czz887dSdTfXwJxwbuE5aF5q
# Copy the transaction signature

# 5. Register your node
python wattnode.py register <your_stake_tx_signature>

# 6. Start earning
python wattnode.py run
```

## Requirements

- Python 3.9+
- Solana wallet with **10,000 WATT** stake
- Small SOL for transaction fees (~0.01 SOL)
- (Optional) [Ollama](https://ollama.ai) for inference jobs

## Commands

| Command | Description |
|---------|-------------|
| `python wattnode.py register <stake_tx>` | Register node with network |
| `python wattnode.py run` | Start the daemon |
| `python wattnode.py status` | Check node status |
| `python wattnode.py earnings` | View earnings summary |

## How It Works

```
┌─────────────────┐         ┌──────────────────┐         ┌─────────────────┐
│   Requester     │ ──────> │  WattCoin API    │ ──────> │   Your Node     │
│ (pays 100 WATT) │         │  (routes jobs)   │         │  (earns 70 WATT)│
└─────────────────┘         └──────────────────┘         └─────────────────┘
```

1. Requester pays WATT to use the scraper/LLM API
2. WattCoin backend creates a job and routes to active nodes
3. Your node picks up the job, executes it locally
4. Submit result → earn 70% of the payment

## Earnings

| Job Type | Requester Pays | You Earn |
|----------|----------------|----------|
| Scrape   | 100 WATT       | 70 WATT  |
| Inference| 500 WATT       | 350 WATT |

**Payment split:**
- 70% → Node operator (you)
- 20% → Treasury (network sustainability)
- 10% → Burned (deflationary)

## Capabilities

### Web Scraping (default)

Fetch web pages for requesters. No extra setup needed.

```yaml
capabilities:
  - scrape
```

### AI Inference (optional)

Run local LLM inference using Ollama.

```bash
# Install Ollama
curl -fsSL https://ollama.ai/install.sh | sh

# Pull a model
ollama pull llama2

# Enable in config
capabilities:
  - scrape
  - inference
```

## Staking

Stake ensures **skin in the game** and protects against malicious nodes.

- **Amount:** 10,000 WATT
- **Wallet:** `Atu5phbGGGFogbKhi259czz887dSdTfXwJxwbuE5aF5q` (Treasury)
- **Slashing:** Stake may be slashed for repeated failures or malicious behavior

## Configuration

See [config.example.yaml](config.example.yaml) for all options.

Key settings:
```yaml
wallet: "YourSolanaWallet..."
name: "my-node"
capabilities:
  - scrape
```

**Security:** Never store private keys in config files. Use environment variables:
```bash
export WATT_PRIVATE_KEY="your_base58_key"
```

## Monitoring

Check your node status:
```bash
python wattnode.py status
```

View live network nodes:
```bash
curl https://your-backend-url.example.com/api/v1/nodes
```

## Troubleshooting

**"Node not registered"**
- Run `python wattnode.py register <stake_tx>` first

**"Stake verification failed"**
- Ensure you sent exactly 10,000 WATT to treasury
- Transaction must be < 24 hours old

**"Cannot connect to Ollama"**
- Install Ollama: https://ollama.ai
- Run: `ollama serve`
- Check URL in config.yaml

## Links

- [WattCoin Website](https://wattcoin.org)
- [API Documentation](https://wattcoin.org/docs)
- [GitHub](https://github.com/WattCoin-Org/wattcoin)
- [Twitter](https://twitter.com/WattCoin2026)

## License

MIT License - See [LICENSE](../LICENSE)
