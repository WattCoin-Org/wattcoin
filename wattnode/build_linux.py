#!/usr/bin/env python3
"""
Build WattNode Linux Executable (AppImage)
Requires: pip install pyinstaller pillow

Run: python build_linux.py
Output: dist/WattNode
"""

import os
import subprocess
import sys

def main():
    print("=" * 50)
    print("WattNode Linux Build")
    print("=" * 50)
    
    # Check dependencies
    try:
        import PyInstaller
        print("✓ PyInstaller found")
    except ImportError:
        print("Installing PyInstaller...")
        subprocess.run([sys.executable, "-m", "pip", "install", "pyinstaller"])
    
    try:
        from PIL import Image
        print("✓ Pillow found")
    except ImportError:
        print("Installing Pillow...")
        subprocess.run([sys.executable, "-m", "pip", "install", "pillow"])
    
    # Create assets folder
    os.makedirs("assets", exist_ok=True)
    
    # Ensure logo exists or create placeholder if needed
    # (Assuming logo.png is present in assets/)
    
    # PyInstaller command
    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--onefile",
        "--name=WattNode",
        "--add-data=assets:assets",  # Include assets folder (colon on Linux)
    ]
    
    # Add icon if exists (.png preferred on Linux)
    if os.path.exists("assets/logo.png"):
        # PyInstaller doesn't use --icon for Linux binaries in the same way,
        # but we include it in assets for the desktop entry.
        pass
    
    cmd.append("wattnode_gui.py")
    
    print("\nRunning PyInstaller...")
    print(" ".join(cmd))
    print()
    
    result = subprocess.run(cmd)
    
    if result.returncode == 0:
        print("\n" + "=" * 50)
        print("✓ Build successful!")
        print("=" * 50)
        print("\nOutput: dist/WattNode")
        print("\nNext steps:")
        print("1. Test: ./dist/WattNode")
        print("2. Packaging: Run appimagetool to create an AppImage")
    else:
        print("\n✗ Build failed")
        sys.exit(1)


if __name__ == "__main__":
    main()
