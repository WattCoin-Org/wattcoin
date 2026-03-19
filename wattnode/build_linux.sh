#!/bin/bash

# WattNode Linux Build Script
# Creates AppImage package with PyInstaller

set -e

echo "Building WattNode for Linux..."

# Check if we're in a virtual environment
if [[ "$VIRTUAL_ENV" == "" ]]; then
    echo "Warning: Not in a virtual environment. Consider using one."
fi

# Create build directory
BUILD_DIR="build"
DIST_DIR="dist"
APP_NAME="WattNode"
APP_VERSION=$(python -c "import wattnode; print(wattnode.__version__)" 2>/dev/null || echo "1.0.0")

rm -rf $BUILD_DIR $DIST_DIR
mkdir -p $BUILD_DIR

echo "Installing build dependencies..."
pip install pyinstaller requests

# Check for tkinter
python -c "import tkinter" || {
    echo "Error: tkinter not available. Install with:"
    echo "  Ubuntu/Debian: sudo apt-get install python3-tk"
    echo "  CentOS/RHEL: sudo yum install tkinter"
    echo "  Arch: sudo pacman -S tk"
    exit 1
}

# Check for nvidia-smi
NVIDIA_SMI_PATH=$(which nvidia-smi || echo "")
if [[ -n "$NVIDIA_SMI_PATH" ]]; then
    echo "Found nvidia-smi at: $NVIDIA_SMI_PATH"
    NVIDIA_SMI_OPTION="--add-binary $NVIDIA_SMI_PATH:."
else
    echo "nvidia-smi not found - will use fallback detection"
    NVIDIA_SMI_OPTION=""
fi

echo "Creating PyInstaller spec..."
cat > wattnode.spec << EOF
# -*- mode: python ; coding: utf-8 -*-

block_cipher = None

a = Analysis(
    ['wattnode/main.py'],
    pathex=[],
    binaries=[
        $( [[ -n "$NVIDIA_SMI_PATH" ]] && echo "('$NVIDIA_SMI_PATH', '.')," )
    ],
    datas=[
        ('wattnode/assets', 'assets'),
        ('wattnode/config', 'config'),
    ],
    hiddenimports=[
        'tkinter',
        'tkinter.ttk',
        'tkinter.messagebox',
        'tkinter.filedialog',
        'psutil',
        'requests',
        'subprocess',
        'threading',
        'json',
        'os',
        'sys',
        'time',
        'platform',
        'socket',
        'hashlib',
        'base64',
        'urllib.parse',
        'urllib.request',
        'ssl',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='$APP_NAME',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon='wattnode/assets/icon.ico' if os.path.exists('wattnode/assets/icon.ico') else None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='$APP_NAME',
)
EOF

echo "Building with PyInstaller..."
pyinstaller wattnode.spec --clean --noconfirm

# Create AppImage
echo "Creating AppImage..."

APPDIR="$APP_NAME.AppDir"
rm -rf $APPDIR
mkdir -p $APPDIR/usr/bin
mkdir -p $APPDIR/usr/share/applications
mkdir -p $APPDIR/usr/share/icons/hicolor/256x256/apps

# Copy built application
cp -r dist/$APP_NAME/* $APPDIR/usr/bin/

# Create desktop entry
cat > $APPDIR/usr/share/applications/$APP_NAME.desktop << EOF
[Desktop Entry]
Type=Application
Name=WattNode
Comment=Mining Pool Monitor and GPU Manager
Exec=$APP_NAME
Icon=$APP_NAME
Categories=System;Monitor;
Terminal=false
EOF

# Copy icon if available
if [[ -f "wattnode/assets/icon.png" ]]; then
    cp wattnode/assets/icon.png $APPDIR/usr/share/icons/hicolor/256x256/apps/$APP_NAME.png
    cp wattnode/assets/icon.png $APPDIR/$APP_NAME.png
elif [[ -f "wattnode/assets/icon.ico" ]]; then
    # Convert ico to png if available
    if command -v convert >/dev/null 2>&1; then
        convert wattnode/assets/icon.ico $APPDIR/$APP_NAME.png
        cp $APPDIR/$APP_NAME.png $APPDIR/usr/share/icons/hicolor/256x256/apps/$APP_NAME.png
    fi
fi

# Create AppRun script
cat > $APPDIR/AppRun << 'EOF'
#!/bin/bash
HERE="$(dirname "$(readlink -f "${0}")")"
export APPDIR="$HERE"
export PATH="${HERE}/usr/bin:${PATH}"
export LD_LIBRARY_PATH="${HERE}/usr/lib:${LD_LIBRARY_PATH}"

# Check for nvidia-smi in system PATH if not bundled
if [[ ! -x "${HERE}/usr/bin/nvidia-smi" ]]; then
    SYSTEM_NVIDIA_SMI=$(which nvidia-smi 2>/dev/null || echo "")
    if [[ -n "$SYSTEM_NVIDIA_SMI" ]]; then
        export NVIDIA_SMI_PATH="$SYSTEM_NVIDIA_SMI"
    fi
fi

cd "${HERE}/usr/bin"
exec "./WattNode" "$@"
EOF

chmod +x $APPDIR/AppRun
cp $APPDIR/usr/share/applications/$APP_NAME.desktop $APPDIR/

# Download and use appimagetool
APPIMAGETOOL_URL="https://github.com/AppImage/AppImageKit/releases/download/continuous/appimagetool-x86_64.AppImage"
if [[ ! -f "appimagetool" ]]; then
    echo "Downloading appimagetool..."
    wget -O appimagetool "$APPIMAGETOOL_URL"
    chmod +x appimagetool
fi

# Build AppImage
APPIMAGE_NAME="$APP_NAME-$APP_VERSION-x86_64.AppImage"
echo "Building $APPIMAGE_NAME..."
./appimagetool $APPDIR $APPIMAGE_NAME

# Make it executable
chmod +x $APPIMAGE_NAME

echo "Build complete!"
echo "AppImage: $APPIMAGE_NAME"
echo "Portable directory: dist/$APP_NAME"

# Test the build
echo "Testing build..."
if [[ -f "$APPIMAGE_NAME" ]]; then
    echo "✓ AppImage created successfully"
    
    # Quick test run (with timeout)
    timeout 5s ./$APPIMAGE_NAME --version 2>/dev/null && echo "✓ AppImage runs correctly" || echo "⚠ Could not verify AppImage execution"
else
    echo "✗ AppImage creation failed"
    exit 1
fi

echo ""
echo "Installation instructions:"
echo "1. Copy $APPIMAGE_NAME to desired location"
echo "2. Make executable: chmod +x $APPIMAGE_NAME"
echo "3. Run: ./$APPIMAGE_NAME"
echo ""
echo "Or install system-wide:"
echo "sudo mv $APPIMAGE_NAME /usr/local/bin/$APP_NAME"

# Cleanup
rm -f wattnode.spec
rm -rf $BUILD_DIR $APPDIR

echo "Build script completed!"