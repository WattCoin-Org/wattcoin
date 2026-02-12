# WattNode Desktop GUI

A desktop application to run WattNode and earn WATT on Windows and Linux.

![WattNode GUI](assets/screenshot.png)

## Quick Start (Windows)

### Option 1: Download Installer (Recommended)
1. Download `WattNode-Setup.exe` from [Releases](https://github.com/WattCoin-Org/wattcoin/releases)
2. Run installer → Next → Install
3. Launch WattNode from desktop shortcut
4. Enter your wallet address
5. Register or link existing node
6. Click **Start Node** → Start earning!

### Option 2: Run from Source
```powershell
# Clone repo
git clone https://github.com/WattCoin-Org/wattcoin.git
cd wattcoin/wattnode

# Install dependencies
pip install -r requirements_gui.txt

# Run GUI
python wattnode_gui.py
```

## Linux Quick Start

```bash
cd wattnode
pip install -r requirements_gui.txt
python wattnode_gui.py
```

## Building Packages

### Windows (EXE + Inno Setup installer)

Prerequisites:
- Python 3.9+
- [Inno Setup](https://jrsoftware.org/isdl.php)

```powershell
cd wattnode
python build_windows.py
# Then build installer.iss with Inno Setup
```

Output: `installer_output/WattNode-Setup-1.0.0.exe`

### Linux (single-file binary + AppImage)

Prerequisites:
- Python 3.9+
- `pip install pyinstaller`
- Optional: `appimagetool` for AppImage packaging

```bash
cd wattnode
python build_linux.py
```

Outputs:
- `dist/WattNode` (one-file Linux binary)
- `dist/WattNode.AppImage` (if appimagetool is installed)

## Features

- ⚡ **One-click start/stop** - No command line needed
- 📊 **Live stats** - Jobs completed, WATT earned
- 🔔 **Activity log** - See jobs in real-time
- 🎨 **Dark theme** - Matches WattCoin branding
- 💾 **Auto-save config** - Remembers your settings
- 🚀 **Auto-payout** - WATT sent directly to your wallet

## Registration

New nodes require a 10,000 WATT stake:

1. Click **Register Node** in the app
2. Send 10,000 WATT to treasury wallet (shown in app)
3. Paste transaction signature
4. Click **Register**

Your stake ensures network integrity. Nodes earn 70% of each job payment.

## Troubleshooting

**"Node not registered"**
- Complete registration first (10,000 WATT stake required)

**App won't start**
- Install Visual C++ Redistributable if prompted
- Try running as administrator

**No jobs received**
- Check internet connection
- Verify node is "Running" (green status)
- Jobs are distributed based on demand

## Files

| File | Description |
|------|-------------|
| `wattnode_gui.py` | Main GUI application |
| `build_windows.py` | Windows PyInstaller build script |
| `build_linux.py` | Linux one-file + AppImage build script |
| `installer.iss` | Inno Setup installer script |
| `requirements_gui.txt` | Python dependencies |
| `assets/logo.png` | WattCoin logo |
| `assets/icon.ico` | App icon |

## Color Palette

Matches wattcoin.org:
- Background: `#0f0f0f`
- Surface: `#1a1a1a`
- Accent: `#39ff14` (neon green)
- Text: `#ffffff`
