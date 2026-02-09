#!/usr/bin/env python3
"""
Build WattNode Linux Executable
Requires: pip install pyinstaller pillow

Run: python build_linux.py
Output: dist/WattNode
"""

import os
import subprocess
import sys
import shutil

def main():
    print("=" * 50)
    print("WattNode Linux Build")
    print("=" * 50)
    
    # Check for Linux
    if not sys.platform.startswith('linux'):
        print("✗ This script is for Linux builds only.")
        sys.exit(1)

    # User confirmation for dependency installation
    def confirm_install(pkg_name):
        valid_responses = {"y": True, "n": False, "yes": True, "no": False}
        while True:
            res = input(f"Package '{pkg_name}' missing. Install it? (y/n): ").strip().lower()
            if res in valid_responses:
                return valid_responses[res]
            print("Invalid input. Please enter 'y' or 'n'.")

    # Check dependencies
    try:
        import PyInstaller
        print("✓ PyInstaller found")
    except ImportError:
        if confirm_install("pyinstaller"):
            print("Installing PyInstaller...")
            try:
                subprocess.run([sys.executable, "-m", "pip", "install", "pyinstaller"], check=True, shell=False)
            except subprocess.CalledProcessError as e:
                print(f"✗ Failed to install PyInstaller: {e}")
                sys.exit(1)
        else:
            print("✗ PyInstaller is required to build.")
            sys.exit(1)
    
    try:
        from PIL import Image
        print("✓ Pillow found")
    except ImportError:
        if confirm_install("pillow"):
            print("Installing Pillow...")
            try:
                subprocess.run([sys.executable, "-m", "pip", "install", "pillow"], check=True, shell=False)
            except subprocess.CalledProcessError as e:
                print(f"✗ Failed to install Pillow: {e}")
                sys.exit(1)
        else:
            print("✗ Pillow is required to build.")
            sys.exit(1)
    
    # Create assets folder
    os.makedirs("assets", exist_ok=True)
    
    # Check for logo.png and prepare assets
    if not os.path.exists("assets/logo.png"):
        print("⚠️ Warning: assets/logo.png not found. Using generic icon.")
        # Create a placeholder if needed
    else:
        print("✓ assets/logo.png verified")
    
    # Clean previous builds
    if os.path.exists("build"):
        shutil.rmtree("build")
    if os.path.exists("dist"):
        shutil.rmtree("dist")
    
    # PyInstaller command
    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--onefile",
        "--name=WattNode",
        "--add-data=assets:assets",  # Include assets folder (colon on Linux)
        "wattnode_gui.py"
    ]
    
    print("\nRunning PyInstaller...")
    print(" ".join(cmd))
    print()
    
    try:
        result = subprocess.run(cmd, check=True)
        print("\n" + "=" * 50)
        print("✓ Build successful!")
        print("=" * 50)
        print("\nOutput: dist/WattNode")
        print("\nNext steps:")
        print("1. Test: ./dist/WattNode")
        print("2. Packaging: Run appimagetool to create an AppImage")
    except subprocess.CalledProcessError:
        print("\n✗ Build failed")
        sys.exit(1)


if __name__ == "__main__":
    main()
