#!/usr/bin/env python3
"""
Build WattNode Linux Executable
Output: dist/WattNode
"""

import os
import subprocess
import sys
import shutil

# Constants for security and clarity
REQUIRED_PACKAGES = {
    "PyInstaller": "pyinstaller",
    "PIL": "pillow"
}

def check_dependencies():
    """Verify that all required build dependencies are installed."""
    missing = []
    
    # Check PyInstaller
    try:
        import PyInstaller
    except ImportError:
        missing.append(REQUIRED_PACKAGES["PyInstaller"])
        
    # Check Pillow (PIL)
    try:
        from PIL import Image
    except ImportError:
        missing.append(REQUIRED_PACKAGES["PIL"])
        
    if missing:
        print("✗ Missing build dependencies: " + ", ".join(missing))
        print(f"\nPlease install them using:\n\npip install {' '.join(missing)}")
        print("\nOr use the requirements file:\n\npip install -r requirements_gui.txt")
        sys.exit(1)
    
    print("✓ All build dependencies found.")

def main():
    print("=" * 50)
    print("WattNode Linux Build")
    print("=" * 50)
    
    # 1. Platform Check
    if not sys.platform.startswith('linux'):
        print("✗ This script is for Linux builds only.")
        sys.exit(1)

    # 2. Dependency Check (Static, no auto-install for security)
    check_dependencies()
    
    # 3. Environment Preparation
    # Ensure we are in the correct directory
    script_dir = os.path.dirname(os.path.abspath(__file__))
    os.chdir(script_dir)
    
    # Create assets folder if missing (should be tracked in git)
    os.makedirs("assets", exist_ok=True)
    if not os.path.exists("assets/logo.png"):
        print("⚠️ Warning: assets/logo.png not found. The application might lack an icon.")
    
    # Clean previous builds
    for folder in ["build", "dist"]:
        if os.path.exists(folder):
            try:
                shutil.rmtree(folder)
            except Exception as e:
                print(f"⚠️ Could not clean {folder}: {e}")
    
    # 4. PyInstaller Execution
    # We use a list of arguments and shell=False to prevent command injection
    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--onefile",
        "--name=WattNode",
        "--add-data=assets:assets",
        "wattnode_gui.py"
    ]
    
    print("\nRunning PyInstaller...")
    try:
        # shell=False is the default, but we're explicit for security reviews
        subprocess.run(cmd, check=True, shell=False)
        
        print("\n" + "=" * 50)
        print("✓ Build successful!")
        print("=" * 50)
        print("\nOutput: dist/WattNode")
    except subprocess.CalledProcessError as e:
        print(f"\n✗ Build failed with exit code {e.returncode}")
        sys.exit(1)
    except FileNotFoundError:
        print("\n✗ PyInstaller not found in path. Please ensure it is installed.")
        sys.exit(1)

if __name__ == "__main__":
    main()
