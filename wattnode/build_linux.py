#!/usr/bin/env python3
"""
WattNode GUI - Linux Build Script

Creates AppImage for Linux distribution (Ubuntu 22.04+)

Requirements:
- Python 3.9+
- pip install pyinstaller python-appimage

Usage:
    python build_linux.py

Output:
    dist/WattNode-1.0.0-x86_64.AppImage
"""

import os
import sys
import subprocess
import shutil
from pathlib import Path

# === CONFIG ===
APP_NAME = "WattNode"
VERSION = "3.0.0"
ARCH = "x86_64"
ENTRY_POINT = "wattnode_gui.py"
ICON_PATH = "assets/logo.png"

# === DIRECTORIES ===
ROOT_DIR = Path(__file__).parent
DIST_DIR = ROOT_DIR / "dist"
BUILD_DIR = ROOT_DIR / "build"
APPIMAGE_DIR = DIST_DIR / f"{APP_NAME}.AppDir"

def clean_build():
    """Clean previous build artifacts"""
    print("🧹 Cleaning previous build...")
    for dir_path in [DIST_DIR, BUILD_DIR]:
        if dir_path.exists():
            shutil.rmtree(dir_path)
    print("✓ Clean complete")

def install_dependencies():
    """Install required Python packages"""
    print("📦 Installing dependencies...")
    deps = [
        "pyinstaller>=6.0",
        "python-appimage>=1.4",
        "tkinter-tooltip",
    ]
    for dep in deps:
        print(f"  Installing {dep}...")
        subprocess.check_call([sys.executable, "-m", "pip", "install", dep])
    print("✓ Dependencies installed")

def build_executable():
    """Build standalone executable with PyInstaller"""
    print("🔨 Building executable with PyInstaller...")
    
    pyinstaller_cmd = [
        sys.executable, "-m", "PyInstaller",
        "--name", APP_NAME,
        "--onedir",
        "--windowed",
        "--icon", str(ROOT_DIR / ICON_PATH) if Path(ROOT_DIR / ICON_PATH).exists() else "",
        "--add-data", f"{ROOT_DIR}/assets:assets",
        "--hidden-import", "tkinter",
        "--hidden-import", "matplotlib",
        f"--workpath={BUILD_DIR}",
        f"--distpath={DIST_DIR}",
        f"--specpath={BUILD_DIR}",
        ENTRY_POINT,
    ]
    
    # Filter empty strings
    pyinstaller_cmd = [arg for arg in pyinstaller_cmd if arg]
    
    print(f"  Running: {' '.join(pyinstaller_cmd)}")
    subprocess.check_call(pyinstaller_cmd, cwd=str(ROOT_DIR))
    print("✓ Executable built")

def create_appdir():
    """Create AppDir structure for AppImage"""
    print("📁 Creating AppDir structure...")
    
    # Create AppDir
    APPIMAGE_DIR.mkdir(parents=True, exist_ok=True)
    
    # Copy executable
    exe_src = DIST_DIR / APP_NAME / APP_NAME
    exe_dst = APPIMAGE_DIR / APP_NAME
    if exe_src.exists():
        shutil.copy2(exe_src, exe_dst)
        os.chmod(exe_dst, 0o755)
    
    # Copy icon
    icon_src = ROOT_DIR / ICON_PATH
    icon_dst = APPIMAGE_DIR / f"{APP_NAME}.png"
    if icon_src.exists():
        shutil.copy2(icon_src, icon_dst)
    
    # Create desktop file
    desktop_content = f"""[Desktop Entry]
Type=Application
Name={APP_NAME}
Comment=WattNode - Earn WATT by running a light node
Exec={APP_NAME}
Icon={APP_NAME}
Categories=Network;Utility;
Keywords=blockchain;crypto;wattcoin;
"""
    (APPIMAGE_DIR / f"{APP_NAME}.desktop").write_text(desktop_content)
    
    # Create AppRun script
    apprun_content = f"""#!/bin/bash
HERE="$(dirname "$(readlink -f "$0")")"
exec "$HERE/{APP_NAME}" "$@"
"""
    apprun_path = APPIMAGE_DIR / "AppRun"
    apprun_path.write_text(apprun_content)
    os.chmod(apprun_path, 0o755)
    
    print("✓ AppDir created")

def build_appimage():
    """Build AppImage from AppDir"""
    print("🖼️  Building AppImage...")
    
    try:
        from python_appimage import app
        from python_appimage.app.image import create_appimage
        
        # Create AppImage
        output_path = create_appimage(
            appdir=APPIMAGE_DIR,
            name=APP_NAME,
            version=VERSION,
            icon=str(APPIMAGE_DIR / f"{APP_NAME}.png"),
            executable=APP_NAME,
        )
        
        # Move to dist directory
        final_path = DIST_DIR / f"{APP_NAME}-{VERSION}-{ARCH}.AppImage"
        shutil.move(output_path, final_path)
        os.chmod(final_path, 0o755)
        
        print(f"✓ AppImage created: {final_path}")
        
    except ImportError:
        print("⚠️  python-appimage not available, creating manual AppImage...")
        # Fallback: create tarball instead
        tarball_path = DIST_DIR / f"{APP_NAME}-{VERSION}-linux-{ARCH}.tar.gz"
        subprocess.check_call([
            "tar", "-czf", str(tarball_path),
            "-C", str(DIST_DIR),
            APP_NAME,
        ])
        print(f"✓ Tarball created: {tarball_path}")

def create_deb_package():
    """Create .deb package (alternative distribution)"""
    print("📦 Creating .deb package...")
    
    deb_dir = DIST_DIR / "deb"
    deb_dir.mkdir(parents=True, exist_ok=True)
    
    # DEBIAN control file
    debian_dir = deb_dir / "DEBIAN"
    debian_dir.mkdir()
    
    control_content = f"""Package: wattnode
Version: {VERSION}
Section: utils
Priority: optional
Architecture: amd64
Depends: python3 (>= 3.9), python3-tk, python3-pip
Maintainer: WattCoin Team <dev@wattcoin.org>
Description: WattNode Desktop Client
 Earn WATT by running a light node and serving AI inference
"""
    (debian_dir / "control").write_text(control_content)
    
    # Create usr directory structure
    usr_dir = deb_dir / "usr"
    bin_dir = usr_dir / "bin"
    share_dir = usr_dir / "share" / "wattnode"
    
    bin_dir.mkdir(parents=True)
    share_dir.mkdir(parents=True)
    
    # Copy files
    exe_src = DIST_DIR / APP_NAME / APP_NAME
    shutil.copy2(exe_src, share_dir / APP_NAME)
    
    # Create wrapper script
    wrapper_content = f"""#!/bin/bash
exec /usr/share/wattnode/{APP_NAME} "$@"
"""
    wrapper_path = bin_dir / "wattnode"
    wrapper_path.write_text(wrapper_content)
    os.chmod(wrapper_path, 0o755)
    
    print("✓ .deb package structure created")
    print(f"  To build: cd {deb_dir} && fakeroot dpkg-deb --build . ../{APP_NAME}-{VERSION}.deb")

def main():
    print("=" * 60)
    print(f"  {APP_NAME} v{VERSION} - Linux Build")
    print("=" * 60)
    print()
    
    # Check system
    if sys.platform != "linux":
        print("⚠️  Warning: Building on non-Linux system")
        print("   AppImage may not work correctly")
        print()
    
    # Build steps
    clean_build()
    install_dependencies()
    build_executable()
    create_appdir()
    build_appimage()
    create_deb_package()
    
    print()
    print("=" * 60)
    print("  ✅ Build Complete!")
    print("=" * 60)
    print()
    print(f"Output files in: {DIST_DIR}")
    print()
    print("Installation:")
    print("  AppImage: chmod +x WattNode-*.AppImage && ./WattNode-*.AppImage")
    print("  .deb:     sudo dpkg -i WattNode-*.deb")
    print("  Tarball:  tar -xzf WattNode-*.tar.gz && ./WattNode/WattNode")
    print()

if __name__ == "__main__":
    main()
