#!/usr/bin/env python3
"""
Build WattNode Windows Executable
Requires: pip install pyinstaller pillow

Run: python build_windows.py
Output: dist/WattNode.exe
"""

import os
import subprocess
import sys

def main():
    print("=" * 50)
    print("WattNode Windows Build")
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
    
    # Convert logo to ICO if needed
    if os.path.exists("assets/logo.png") and not os.path.exists("assets/icon.ico"):
        print("Converting logo to ICO...")
        try:
            from PIL import Image
            img = Image.open("assets/logo.png")
            img = img.resize((256, 256), Image.LANCZOS)
            img.save("assets/icon.ico", format="ICO")
            print("✓ Created assets/icon.ico")
        except Exception as e:
            print(f"Warning: Could not create ICO: {e}")
    
    # PyInstaller command
    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--onefile",
        "--windowed",  # No console window
        "--name=WattNode",
        "--add-data=assets;assets",  # Include assets folder
    ]
    
    # Add icon if exists
    if os.path.exists("assets/icon.ico"):
        cmd.append("--icon=assets/icon.ico")
    
    cmd.append("wattnode_gui.py")
    
    print("\nRunning PyInstaller...")
    print(" ".join(cmd))
    print()
    
    result = subprocess.run(cmd)
    
    if result.returncode == 0:
        print("\n" + "=" * 50)
        print("✓ Build successful!")
        print("=" * 50)
        print("\nOutput: dist/WattNode.exe")
        print("\nNext steps:")
        print("1. Test: dist\\WattNode.exe")
        print("2. Build installer: Run Inno Setup with installer.iss")
    else:
        print("\n✗ Build failed")
        sys.exit(1)


if __name__ == "__main__":
    main()
