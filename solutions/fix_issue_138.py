```python
import os
import subprocess
from tkinter import Tk, Label, Button

def check_nvidia_gpu():
    try:
        result = subprocess.run(['nvidia-smi'], capture_output=True, text=True)
        if result.returncode == 0:
            print("NVIDIA GPU detected.")
            print(result.stdout)
        else:
            print("NVIDIA GPU not detected.")
    except FileNotFoundError:
        print("nvidia-smi command not found. Make sure CUDA toolkit is installed.")

def node_registration():
    print("Node registration logic here.")

def job_claiming():
    print("Job claiming logic here.")

def inference_setup():
    print("Inference setup logic here.")

def wallet_configuration():
    print("Wallet configuration logic here.")

def live_log_display():
    print("Live log display logic here.")

def create_gui():
    root = Tk()
    root.title("WattNode GUI")
    root.geometry("300x200")

    Label(root, text="WattNode").pack()
    Button(root, text="Node Registration", command=node_registration).pack()
    Button(root, text="Job Claiming", command=job_claiming).pack()
    Button(root, text="Inference Setup", command=inference_setup).pack()
    Button(root, text="Wallet Configuration", command=wallet_configuration).pack()
    Button(root, text="Live Log Display", command=live_log_display).pack()

    root.mainloop()

if __name__ == "__main__":
    check_nvidia_gpu()
    create_gui()
```

```bash
#!/bin/bash

set -e

echo "Installing dependencies..."
sudo apt update
sudo apt install -y python3 python3-tk python3-pip nvidia-cuda-toolkit

echo "Creating AppImage..."
pip3 install pyinstaller
pyinstaller --onefile --windowed wattnode_gui.py

echo "Testing the build on Ubuntu 22.04..."
./dist/wattnode_gui

echo "Packaging the application..."
mkdir -p wattnode_appimage
cp dist/wattnode_gui wattnode_appimage/
cd wattnode_appimage
wget -O appimagetool https://github.com/AppImage/AppImageKit/releases/download/continuous/appimagetool-x86_64.AppImage
chmod +x appimagetool
./appimagetool --no-appstream .

echo "Build complete. Check wattnode_appimage directory for output."

echo "Updating README with instructions and system requirements..."
cat <<EOL >> ../README.md

## Installation Instructions

For Linux users, please ensure you have the following minimum system requirements before installation:
- Ubuntu 22.04 or equivalent
- Python 3.x
- tkinter library
- NVIDIA CUDA toolkit for GPU support

To install WattNode, download the latest release from the `releases` page.

After download, you can simply make the AppImage executable and run it:

\`\`\`bash
chmod +x WattNode-xxx.AppImage
./WattNode-xxx.AppImage
\`\`\`

## System Requirements

- Operating System: Linux (Ubuntu 22.04 or equivalent)
- GPU: NVIDIA with CUDA support (for GPU features)
- Other: Internet connection for node registration and job claiming

## Developer Notes

- My Solana wallet address for the reward: <your-solana-wallet-address-here>
EOL

echo "Documentation update complete."

echo "Please review changes and create a pull request to WattCoin-Org/wattcoin repository."
```