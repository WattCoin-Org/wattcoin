# WattNode Installation Guide

Detailed installation instructions for different platforms.

## Raspberry Pi (Recommended)

### Prerequisites

```bash
# Update system
sudo apt update && sudo apt upgrade -y

# Install Python 3.9+
sudo apt install python3 python3-pip python3-venv -y
```

### Installation

```bash
# Clone repository
git clone https://github.com/WattCoin-Org/wattcoin.git
cd wattcoin/wattnode

# Create virtual environment
python3 -m venv venv
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Configure
cp config.example.yaml config.yaml
nano config.yaml  # Edit with your wallet
```

### Run as Service (systemd)

Create `/etc/systemd/system/wattnode.service`:

```ini
[Unit]
Description=WattNode Daemon
After=network.target

[Service]
Type=simple
User=pi
WorkingDirectory=/home/pi/wattcoin/wattnode
ExecStart=/home/pi/wattcoin/wattnode/venv/bin/python wattnode.py run
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

Enable and start:
```bash
sudo systemctl enable wattnode
sudo systemctl start wattnode
sudo systemctl status wattnode
```

View logs:
```bash
journalctl -u wattnode -f
```

## Desktop (macOS/Linux)

### Prerequisites

```bash
# macOS
brew install python@3.11

# Ubuntu/Debian
sudo apt install python3 python3-pip python3-venv
```

### Installation

```bash
git clone https://github.com/WattCoin-Org/wattcoin.git
cd wattcoin/wattnode

python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

cp config.example.yaml config.yaml
# Edit config.yaml
```

### Run

```bash
# Activate venv
source venv/bin/activate

# Register (one time)
python wattnode.py register <stake_tx>

# Run daemon
python wattnode.py run
```

## Windows

### Prerequisites

1. Install [Python 3.11+](https://www.python.org/downloads/)
2. Enable "Add Python to PATH" during install

### Installation

```powershell
# Clone repository
git clone https://github.com/WattCoin-Org/wattcoin.git
cd wattcoin\wattnode

# Create virtual environment
python -m venv venv
.\venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Configure
copy config.example.yaml config.yaml
# Edit config.yaml with notepad
```

### Run

```powershell
.\venv\Scripts\activate
python wattnode.py register <stake_tx>
python wattnode.py run
```

## Docker (Coming Soon)

```bash
# Pull image
docker pull wattcoin/wattnode:latest

# Run
docker run -d \
  -e WATT_WALLET=YourWallet \
  -e WATT_NODE_ID=YourNodeId \
  wattcoin/wattnode
```

## Adding Inference Capability

To earn from inference jobs, install Ollama:

### Raspberry Pi / Linux

```bash
curl -fsSL https://ollama.ai/install.sh | sh
ollama pull llama2  # or smaller: phi, tinyllama
ollama serve &
```

### macOS

```bash
brew install ollama
ollama pull llama2
ollama serve &
```

Then enable in config:
```yaml
capabilities:
  - scrape
  - inference

ollama:
  url: "http://localhost:11434"
  model: "llama2"
```

## Firewall Notes

WattNode uses **polling mode** by default - it calls out to the API, so no incoming ports needed.

If you enable webhook mode (future), you'll need to open port 8765.

## Verify Installation

```bash
# Check status
python wattnode.py status

# Should show:
# ⚡ WattNode Status
#    Node ID: node_abc123
#    Status: active
#    ...
```

## Troubleshooting

### "ModuleNotFoundError: No module named 'yaml'"
```bash
pip install PyYAML
```

### "Permission denied"
```bash
chmod +x wattnode.py
```

### "Connection refused" on Raspberry Pi
Ensure you have internet:
```bash
ping your-backend-url.example.com
```
