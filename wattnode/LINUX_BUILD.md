# WattNode Linux Build Guide

## Overview

This guide covers building and installing WattNode on Linux systems. WattNode is a desktop GUI client for the WattCoin distributed computing network, providing node management, job processing, and wallet integration capabilities.

## System Requirements

### Minimum Requirements
- **OS**: Ubuntu 22.04 LTS or compatible distribution
- **Python**: 3.10 or higher
- **Memory**: 4GB RAM minimum, 8GB recommended
- **Storage**: 2GB free disk space
- **Network**: Stable internet connection

### GPU Support (Optional)
- **NVIDIA GPU**: CUDA-capable GPU with driver 470+ recommended
- **nvidia-smi**: Required for GPU detection and monitoring

## Dependencies

### System Packages (Ubuntu/Debian)
```bash
sudo apt update
sudo apt install -y \
    python3 \
    python3-pip \
    python3-venv \
    python3-dev \
    python3-tk \
    git \
    build-essential \
    pkg-config \
    libssl-dev \
    curl \
    wget
```

### Additional Dependencies for AppImage
```bash
sudo apt install -y \
    fuse \
    libfuse2 \
    desktop-file-utils
```

## Build Process

### 1. Clone Repository
```bash
git clone https://github.com/WattCoin-Org/wattcoin.git
cd wattcoin/wattnode
```

### 2. Set Up Virtual Environment
```bash
python3 -m venv venv
source venv/bin/activate
pip install --upgrade pip setuptools wheel
```

### 3. Install Python Dependencies
```bash
pip install -r requirements.txt
pip install pyinstaller
```

### 4. Verify Installation
```bash
python3 wattnode.py --version
```

### 5. Build Executable

#### Option A: PyInstaller (Recommended)
```bash
pyinstaller --onefile \
    --windowed \
    --name=WattNode \
    --icon=assets/icon.png \
    --add-data="assets:assets" \
    --add-data="config:config" \
    wattnode.py
```

#### Option B: AppImage Build
```bash
# Download AppImage tools
wget https://github.com/AppImage/AppImageKit/releases/download/continuous/appimagetool-x86_64.AppImage
chmod +x appimagetool-x86_64.AppImage

# Create AppDir structure
mkdir -p WattNode.AppDir/usr/bin
mkdir -p WattNode.AppDir/usr/share/applications
mkdir -p WattNode.AppDir/usr/share/icons/hicolor/256x256/apps

# Copy built executable
cp dist/WattNode WattNode.AppDir/usr/bin/
cp assets/icon.png WattNode.AppDir/usr/share/icons/hicolor/256x256/apps/wattnode.png

# Create desktop file
cat > WattNode.AppDir/usr/share/applications/wattnode.desktop << EOF
[Desktop Entry]
Type=Application
Name=WattNode
Comment=WattCoin Network Node Manager
Exec=WattNode
Icon=wattnode
Categories=Network;System;
EOF

# Create AppRun
cat > WattNode.AppDir/AppRun << 'EOF'
#!/bin/bash
HERE="$(dirname "$(readlink -f "${0}")")"
exec "${HERE}/usr/bin/WattNode" "$@"
EOF
chmod +x WattNode.AppDir/AppRun

# Build AppImage
./appimagetool-x86_64.AppImage WattNode.AppDir WattNode-x86_64.AppImage
```

### 6. Create Debian Package (Optional)
```bash
mkdir -p debian-build/DEBIAN
mkdir -p debian-build/usr/bin
mkdir -p debian-build/usr/share/applications
mkdir -p debian-build/usr/share/icons/hicolor/256x256/apps

# Copy files
cp dist/WattNode debian-build/usr/bin/
cp assets/icon.png debian-build/usr/share/icons/hicolor/256x256/apps/wattnode.png

# Create desktop file
cp WattNode.AppDir/usr/share/applications/wattnode.desktop debian-build/usr/share/applications/

# Create control file
cat > debian-build/DEBIAN/control << EOF
Package: wattnode
Version: 1.0.0
Section: net
Priority: optional
Architecture: amd64
Depends: python3, python3-tk
Maintainer: WattCoin Team <dev@wattcoin.org>
Description: WattCoin Network Node Manager
 Desktop GUI client for managing WattCoin network nodes,
 processing distributed computing jobs, and wallet integration.
EOF

# Build package
dpkg-deb --build debian-build wattnode_1.0.0_amd64.deb
```

## Installation

### AppImage Installation
```bash
# Download and make executable
chmod +x WattNode-x86_64.AppImage

# Run directly
./WattNode-x86_64.AppImage

# Optional: Install to system
sudo mv WattNode-x86_64.AppImage /opt/
sudo ln -sf /opt/WattNode-x86_64.AppImage /usr/local/bin/wattnode
```

### Debian Package Installation
```bash
sudo dpkg -i wattnode_1.0.0_amd64.deb
sudo apt-get install -f  # Fix any dependency issues
```

### Manual Installation
```bash
# Copy executable to system path
sudo cp dist/WattNode /usr/local/bin/wattnode
sudo chmod +x /usr/local/bin/wattnode

# Install desktop entry
sudo cp assets/wattnode.desktop /usr/share/applications/
sudo cp assets/icon.png /usr/share/icons/hicolor/256x256/apps/wattnode.png
sudo update-desktop-database
```

## GPU Detection Setup

### NVIDIA GPU Support
```bash
# Install NVIDIA drivers (if not already installed)
sudo apt install nvidia-driver-535  # or latest available

# Verify nvidia-smi works
nvidia-smi

# For headless systems, ensure nvidia-ml-py is available
pip install nvidia-ml-py3
```

## Configuration

### First Run Setup
1. Launch WattNode: `wattnode` or run the AppImage
2. Configure wallet connection in Settings tab
3. Set up node registration details
4. Configure GPU settings if applicable
5. Test connection to WattCoin network

### Configuration Files
- **Config directory**: `~/.config/wattnode/`
- **Logs directory**: `~/.local/share/wattnode/logs/`
- **Cache directory**: `~/.cache/wattnode/`

## Troubleshooting

### Common Issues

#### 1. Tkinter Import Error
```bash
# Install tkinter
sudo apt install python3-tk
```

#### 2. SSL Certificate Errors
```bash
# Update certificates
sudo apt update && sudo apt install ca-certificates
```

#### 3. NVIDIA GPU Not Detected
```bash
# Check driver installation
nvidia-smi
lsmod | grep nvidia

# Reinstall drivers if needed
sudo apt purge nvidia-*
sudo apt autoremove
sudo apt install nvidia-driver-535
sudo reboot
```

#### 4. Permission Errors
```bash
# Fix file permissions
chmod +x WattNode-x86_64.AppImage
# or
sudo chmod +x /usr/local/bin/wattnode
```

#### 5. AppImage FUSE Errors
```bash
# Install FUSE if missing
sudo apt install fuse libfuse2

# Enable user namespaces (if restricted)
echo 'kernel.unprivileged_userns_clone=1' | sudo tee -a /etc/sysctl.conf
sudo sysctl -p
```

#### 6. Desktop Integration Issues
```bash
# Update desktop database
sudo update-desktop-database
sudo gtk-update-icon-cache /usr/share/icons/hicolor/
```

### Debug Mode
```bash
# Run with debug output
wattnode --debug

# Or for AppImage
./WattNode-x86_64.AppImage --debug
```

### Log Files
Check logs for detailed error information:
```bash
tail -f ~/.local/share/wattnode/logs/wattnode.log
```

## Development

### Running from Source
```bash
cd wattnode
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
python3 wattnode.py
```

### Testing Build
```bash
# Test executable
./dist/WattNode --test-connection

# Test AppImage
./WattNode-x86_64.AppImage --test-connection
```

## Support

For additional support:
- **GitHub Issues**: https://github.com/WattCoin-Org/wattcoin/issues
- **Discord**: https://discord.gg/wattcoin
- **Documentation**: https://docs.wattcoin.org/wattnode

## Version Information

This build process is compatible with:
- **Ubuntu**: 22.04 LTS and newer
- **Debian**: 11 (Bullseye) and newer
- **Linux Mint**: 21 and newer
- **Pop!_OS**: 22.04 and newer
