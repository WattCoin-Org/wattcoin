# WattNode Linux Installation Guide

Install and run WattNode on Linux (Ubuntu 22.04+, Debian, Fedora, Arch).

## Quick Start

### Option 1: AppImage (Recommended - No Installation)

```bash
# Download
wget https://github.com/WattCoin-Org/wattcoin/releases/latest/download/WattNode-3.0.0-x86_64.AppImage

# Make executable
chmod +x WattNode-*.AppImage

# Run
./WattNode-*.AppImage
```

### Option 2: .deb Package (Ubuntu/Debian)

```bash
# Download
wget https://github.com/WattCoin-Org/wattcoin/releases/latest/download/wattnode_3.0.0_amd64.deb

# Install
sudo dpkg -i wattnode_*.deb

# Run from applications menu or terminal
wattnode
```

### Option 3: Build from Source

```bash
# Clone repository
git clone https://github.com/WattCoin-Org/wattcoin.git
cd wattcoin/wattnode

# Install dependencies
sudo apt update
sudo apt install python3 python3-pip python3-tk python3-venv -y

# Create virtual environment
python3 -m venv venv
source venv/bin/activate

# Install Python dependencies
pip install -r requirements_gui.txt

# Run GUI
python wattnode_gui.py
```

## System Requirements

### Minimum Requirements
- **OS**: Ubuntu 22.04+ / Debian 11+ / Fedora 36+ / Arch Linux
- **Python**: 3.9 or higher
- **RAM**: 4GB
- **Storage**: 500MB free space
- **Display**: X11 or Wayland

### Recommended for Inference (WSI)
- **GPU**: NVIDIA with 6GB+ VRAM (RTX 3060 or better)
- **RAM**: 16GB+
- **Storage**: 20GB+ free (for model weights)
- **Driver**: NVIDIA driver 525+ with CUDA support

## Building from Source

### Build AppImage

```bash
cd wattnode

# Install build dependencies
pip install pyinstaller python-appimage

# Build
python build_linux.py

# Output: dist/WattNode-3.0.0-x86_64.AppImage
```

### Build .deb Package

```bash
cd wattnode

# Run build script
python build_linux.py

# Build .deb
cd dist/deb
fakeroot dpkg-deb --build . ../wattnode-3.0.0_amd64.deb
```

## Configuration

### First Run

1. Launch WattNode GUI
2. Enter your Solana wallet address
3. Click "Register Node" (requires 10,000 WATT stake)
4. Or "Link Existing Node" if already registered

### Configuration File

Create `config.yaml` in the same directory:

```yaml
wallet: "YourSolanaWalletAddress"
name: "my-linux-node"
capabilities:
  - scrape
  - inference
api_url: "https://api.wattcoin.org"
```

### Environment Variables

```bash
export WATT_WALLET="YourSolanaWalletAddress"
export WATTCOIN_API_URL="https://api.wattcoin.org"
```

## GPU Detection (Linux)

WattNode automatically detects NVIDIA GPUs on Linux:

```bash
# Check GPU detection
python services/gpu_detector_linux.py

# Manual check
nvidia-smi
```

### Installing NVIDIA Drivers (Ubuntu)

```bash
# Add graphics drivers PPA
sudo add-apt-repository ppa:graphics-drivers/ppa
sudo apt update

# Install driver (adjust version as needed)
sudo apt install nvidia-driver-535 -y

# Reboot
sudo reboot

# Verify
nvidia-smi
```

## Running as a Service

### systemd Service

Create `/etc/systemd/system/wattnode.service`:

```ini
[Unit]
Description=WattNode GUI Daemon
After=network.target

[Service]
Type=simple
User=your_username
WorkingDirectory=/home/your_username/wattcoin/wattnode
ExecStart=/home/your_username/wattcoin/wattnode/venv/bin/python wattnode_gui.py
Restart=always
RestartSec=10
Environment=DISPLAY=:0
Environment=XAUTHORITY=/home/your_username/.Xauthority

[Install]
WantedBy=multi-user.target
```

Enable and start:

```bash
sudo systemctl daemon-reload
sudo systemctl enable wattnode
sudo systemctl start wattnode
sudo systemctl status wattnode
```

### View Logs

```bash
journalctl -u wattnode -f
```

## Troubleshooting

### "No module named 'tkinter'"

```bash
# Ubuntu/Debian
sudo apt install python3-tk -y

# Fedora
sudo dnf install python3-tkinter -y

# Arch
sudo pacman -S tk
```

### "No NVIDIA GPU detected"

1. Check if NVIDIA driver is installed:
   ```bash
   nvidia-smi
   ```

2. If not installed, install drivers (see above)

3. If using laptop with hybrid graphics, ensure NVIDIA is active:
   ```bash
   prime-select query  # Should show "nvidia"
   sudo prime-select nvidia
   sudo reboot
   ```

### AppImage won't start

```bash
# Install FUSE (required for AppImage)
sudo apt install libfuse2 -y

# Or extract and run
./WattNode-*.AppImage --appimage-extract
cd squashfs-root
./AppRun
```

### GUI appears but shows black screen

This is a common issue with Wayland. Try:

```bash
# Force X11 backend
export GDK_BACKEND=x11
./WattNode-*.AppImage

# Or disable Wayland (Ubuntu)
sudo nano /etc/gdm3/custom.conf
# Uncomment: WaylandEnable=false
sudo reboot
```

### No jobs received

1. Check internet connection:
   ```bash
   ping api.wattcoin.org
   ```

2. Verify node is registered:
   ```bash
   python wattnode.py status
   ```

3. Check firewall (WattNode uses outbound connections only):
   ```bash
   sudo ufw status
   ```

## Performance Tuning

### CPU Allocation

In the GUI Settings tab, adjust CPU allocation:
- **25%**: Light usage, good for daily drivers
- **50%**: Balanced (recommended)
- **75-100%**: Dedicated node, maximum earnings

### GPU Inference

For WSI distributed inference:
1. Ensure NVIDIA GPU is detected
2. Install inference dependencies:
   ```bash
   pip install -r requirements_inference.txt
   ```
3. In GUI → Inference tab, click "Install Dependencies"
4. Toggle "Serve Inference" to start earning

## Security Notes

- **Never share your private key** - WattNode only needs your public wallet address
- **Use a dedicated wallet** - Don't use your main wallet for node operations
- **Keep software updated** - Regularly pull latest changes from GitHub
- **Firewall** - WattNode only makes outbound connections (no ports need to be opened)

## Uninstall

### AppImage
```bash
rm WattNode-*.AppImage
rm -rf ~/.config/wattnode  # Config files
```

### .deb Package
```bash
sudo apt remove wattnode
sudo apt autoremove
```

### Source Installation
```bash
rm -rf wattcoin/wattnode/venv
rm -rf ~/.config/wattnode
```

## Getting Help

- **Documentation**: https://github.com/WattCoin-Org/wattcoin/tree/main/wattnode
- **Issues**: https://github.com/WattCoin-Org/wattcoin/issues
- **Discord**: [Join WattCoin Discord]
- **Twitter**: [@WattCoinOrg]

## Changelog

See [CHANGELOG_GUI.md](CHANGELOG_GUI.md) for version history.

---

**Version**: 3.0.0  
**Last Updated**: 2026-03-15  
**Supported Platforms**: Ubuntu 22.04+, Debian 11+, Fedora 36+, Arch Linux
