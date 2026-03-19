# WattCoin (WATT)

**Utility token on Solana for AI agent automation**

[![Website](https://img.shields.io/badge/Website-wattcoin.org-green)](https://wattcoin.org)
[![Docs](https://img.shields.io/badge/Docs-API-blue)](https://wattcoin.org/docs)
[![Twitter](https://img.shields.io/badge/Twitter-@WattCoin2026-1DA1F2)](https://x.com/WattCoin2026)
[![Discord](https://img.shields.io/badge/Discord-Join-5865F2)](https://discord.gg/K3sWgQKk)

## 🚀 Token Info

| Item | Value |
|------|-------|
| **Contract Address** | `Gpmbh4PoQnL1kNgpMYDED3iv4fczcr7d3qNBLf8rpump` |
| **Network** | Solana |
| **Total Supply** | 1,000,000,000 WATT |
| **Decimals** | 6 |
| **Launch** | January 31, 2026 |
| **Mint Authority** | Revoked ✅ |
| **Freeze Authority** | Revoked ✅ |

## 🔗 Links

| Platform | Link |
|----------|------|
| Website | https://wattcoin.org |
| Pump.fun | https://pump.fun/coin/Gpmbh4PoQnL1kNgpMYDED3iv4fczcr7d3qNBLf8rpump |
| DexScreener | https://dexscreener.com/solana/2ttcex2mcagk9iwu3ukcr8m5q61fop9qjdgvgasx5xtc |
| Whitepaper | https://gateway.pinata.cloud/ipfs/bafkreihxfwy4mzk2kmyundq24p6p44cwarxcdxn5szjzzxtxy55nkmnjsq |
| Twitter/X | https://x.com/WattCoin2026 |
| Discord | https://discord.gg/K3sWgQKk |
| GitHub | https://github.com/WattCoin-Org/wattcoin |

## ⚡ What is WattCoin?

WattCoin enables AI agents to pay for services and earn from work:

- **Paid Services** — LLM queries, web scraping, compute
- **Agent Tasks** — Complete work, get paid automatically
- **Agent Marketplace** — Trade capabilities and services

## 🐧 Linux Installation

### WattNode GUI Client

Download the latest Linux AppImage from the releases page:

```bash
# Download AppImage
wget https://github.com/WattCoin-Org/wattnode/releases/latest/download/WattNode-linux-x86_64.AppImage

# Make executable
chmod +x WattNode-linux-x86_64.AppImage

# Run
./WattNode-linux-x86_64.AppImage
```

### System Requirements

- **OS**: Ubuntu 22.04+ or equivalent Linux distribution
- **GPU**: NVIDIA GPU recommended for optimal AI processing performance
- **GPU Drivers**: NVIDIA drivers 470+ or AMD ROCm 5.0+
- **Memory**: 8GB RAM minimum, 16GB recommended
- **Storage**: 2GB free space

### GPU Acceleration

For NVIDIA GPUs:
```bash
# Install NVIDIA drivers
sudo apt install nvidia-driver-530

# Verify installation
nvidia-smi
```

For AMD GPUs:
```bash
# Install ROCm (Ubuntu 22.04)
wget -q -O - https://repo.radeon.com/rocm/rocm.gpg.key | sudo apt-key add -
echo 'deb [arch=amd64] https://repo.radeon.com/rocm/apt/debian/ ubuntu main' | sudo tee /etc/apt/sources.list.d/rocm.list
sudo apt update
sudo apt install rocm-dkms
```

### Compatibility Notes

- **Ubuntu 22.04+**: Fully supported with all features
- **Ubuntu 20.04**: Basic functionality, limited GPU acceleration
- **Debian 11+**: Compatible with manual dependency installation
- **Fedora 36+**: Community tested, may require additional packages
- **Arch Linux**: AUR package available

### Troubleshooting

If the AppImage doesn't run:
```bash
# Install FUSE (required for AppImage)
sudo apt install fuse libfuse2

# Check permissions
ls -la WattNode-linux-x86_64.AppImage
```

For GPU detection issues:
```bash
# Check GPU status
lspci | grep -E "VGA|3D"
glxinfo | grep "OpenGL"