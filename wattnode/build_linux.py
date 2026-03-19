#!/usr/bin/env python3
"""
Linux build script for WattNode using PyInstaller
Handles GPU detection and tkinter support
"""

import os
import sys
import subprocess
import shutil
import platform
from pathlib import Path

def check_dependencies():
    """Check if required dependencies are installed"""
    required_packages = [
        'PyInstaller',
        'tkinter',
        'psutil',
        'GPUtil',
        'nvidia-ml-py3'
    ]
    
    missing = []
    for package in required_packages:
        try:
            if package == 'tkinter':
                import tkinter
            elif package == 'PyInstaller':
                import PyInstaller
            elif package == 'psutil':
                import psutil
            elif package == 'GPUtil':
                import GPUtil
            elif package == 'nvidia-ml-py3':
                import pynvml
        except ImportError:
            missing.append(package)
    
    if missing:
        print(f"Missing dependencies: {', '.join(missing)}")
        print("Install them with: pip install " + " ".join(missing))
        return False
    
    return True

def detect_gpu_libraries():
    """Detect available GPU libraries and return appropriate hidden imports"""
    hidden_imports = []
    
    # NVIDIA GPU support
    try:
        import pynvml
        hidden_imports.extend([
            'pynvml',
            'nvidia-ml-py3',
            'GPUtil'
        ])
        print("✓ NVIDIA GPU support detected")
    except ImportError:
        print("⚠ NVIDIA GPU support not available")
    
    # AMD GPU support
    try:
        subprocess.run(['rocm-smi'], capture_output=True, check=True)
        hidden_imports.append('subprocess')
        print("✓ AMD ROCm support detected")
    except (subprocess.CalledProcessError, FileNotFoundError):
        print("⚠ AMD ROCm support not available")
    
    # Intel GPU support
    try:
        subprocess.run(['intel_gpu_top', '--help'], capture_output=True, check=True)
        print("✓ Intel GPU support detected")
    except (subprocess.CalledProcessError, FileNotFoundError):
        print("⚠ Intel GPU support not available")
    
    return hidden_imports

def get_data_files():
    """Get list of data files to include in the build"""
    data_files = []
    
    # Include tkinter theme files
    try:
        import tkinter.ttk
        tkinter_path = Path(tkinter.__file__).parent
        ttk_theme_path = tkinter_path / 'ttk'
        if ttk_theme_path.exists():
            data_files.append((str(ttk_theme_path), 'tkinter/ttk'))
    except ImportError:
        pass
    
    # Include any config files
    config_files = [
        'config.json',
        'settings.ini',
        'wattnode.conf'
    ]
    
    for config_file in config_files:
        if Path(config_file).exists():
            data_files.append((config_file, '.'))
    
    return data_files

def build_wattnode():
    """Build WattNode using PyInstaller"""
    
    print("WattNode Linux Build Script")
    print("=" * 40)
    
    # Check platform
    if platform.system() != 'Linux':
        print("Error: This script is designed for Linux systems only")
        return False
    
    # Check dependencies
    print("Checking dependencies...")
    if not check_dependencies():
        return False
    
    print("✓ All dependencies satisfied")
    
    # Detect GPU libraries
    print("\nDetecting GPU support...")
    hidden_imports = detect_gpu_libraries()
    
    # Get data files
    print("\nPreparing data files...")
    data_files = get_data_files()
    
    # Build command
    build_cmd = [
        'pyinstaller',
        '--onefile',
        '--windowed',
        '--name=wattnode',
        '--distpath=dist/linux',
        '--workpath=build/linux',
        '--specpath=build/linux',
        '--clean',
        '--noconfirm'
    ]
    
    # Add hidden imports
    base_hidden_imports = [
        'tkinter',
        'tkinter.ttk',
        'tkinter.messagebox',
        'tkinter.filedialog',
        'psutil',
        'threading',
        'queue',
        'json',
        'configparser',
        'logging',
        'datetime',
        'subprocess',
        'os',
        'sys',
        'pathlib'
    ]
    
    all_hidden_imports = base_hidden_imports + hidden_imports
    
    for imp in all_hidden_imports:
        build_cmd.extend(['--hidden-import', imp])
    
    # Add data files
    for src, dst in data_files:
        build_cmd.extend(['--add-data', f'{src}:{dst}'])
    
    # Add icon if available
    icon_files = ['icon.png', 'wattnode.png', 'app.png']
    for icon_file in icon_files:
        if Path(icon_file).exists():
            build_cmd.extend(['--icon', icon_file])
            break
    
    # Main script
    main_script = 'main.py'
    if not Path(main_script).exists():
        # Try alternative names
        alternatives = ['wattnode.py', 'app.py', 'gui.py', 'client.py']
        for alt in alternatives:
            if Path(alt).exists():
                main_script = alt
                break
        else:
            print("Error: Could not find main script file")
            return False
    
    build_cmd.append(main_script)
    
    # Create directories
    Path('dist/linux').mkdir(parents=True, exist_ok=True)
    Path('build/linux').mkdir(parents=True, exist_ok=True)
    
    print(f"\nBuilding with command:")
    print(' '.join(build_cmd))
    
    # Run PyInstaller
    try:
        result = subprocess.run(build_cmd, check=True, capture_output=True, text=True)
        print("✓ Build completed successfully")
        
        # Make executable
        executable_path = Path('dist/linux/wattnode')
        if executable_path.exists():
            executable_path.chmod(0o755)
            print(f"✓ Executable created: {executable_path}")
            
            # Get file size
            size_mb = executable_path.stat().st_size / (1024 * 1024)
            print(f"✓ Executable size: {size_mb:.1f} MB")
            
            # Create launcher script
            create_launcher_script()
            
            # Create AppImage if possible
            create_appimage()
            
            return True
        else:
            print("Error: Executable not found after build")
            return False
            
    except subprocess.CalledProcessError as e:
        print(f"Build failed: {e}")
        if e.stdout:
            print("STDOUT:", e.stdout)
        if e.stderr:
            print("STDERR:", e.stderr)
        return False

def create_launcher_script():
    """Create a launcher script for easier execution"""
    launcher_content = '''#!/bin/bash
# WattNode Launcher Script

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
EXECUTABLE="$SCRIPT_DIR/wattnode"

# Check if executable exists
if [ ! -f "$EXECUTABLE" ]; then
    echo "Error: WattNode executable not found at $EXECUTABLE"
    exit 1
fi

# Check for GPU support
if command -v nvidia-smi &> /dev/null; then
    echo "NVIDIA GPU detected"
    export GPU_SUPPORT="nvidia"
elif command -v rocm-smi &> /dev/null; then
    echo "AMD GPU detected"
    export GPU_SUPPORT="amd"
elif command -v intel_gpu_top &> /dev/null; then
    echo "Intel GPU detected"
    export GPU_SUPPORT="intel"
else
    echo "No GPU acceleration detected, using CPU monitoring only"
    export GPU_SUPPORT="none"
fi

# Set library paths
export LD_LIBRARY_PATH="/usr/local/lib:/usr/lib/x86_64-linux-gnu:$LD_LIBRARY_PATH"

# Launch WattNode
echo "Starting WattNode..."
"$EXECUTABLE" "$@"
'''
    
    launcher_path = Path('dist/linux/launch_wattnode.sh')
    launcher_path.write_text(launcher_content)
    launcher_path.chmod(0o755)
    print(f"✓ Launcher script created: {launcher_path}")

def create_appimage():
    """Create AppImage if appimagetool is available"""
    try:
        # Check if appimagetool is available
        subprocess.run(['appimagetool', '--version'], 
                      capture_output=True, check=True)
        
        print("Creating AppImage...")
        
        # Create AppDir structure
        appdir = Path('dist/linux/WattNode.AppDir')
        appdir.mkdir(exist_ok=True)
        
        # Copy executable
        shutil.copy2('dist/linux/wattnode', appdir / 'AppRun')
        
        # Create desktop file
        desktop_content = '''[Desktop Entry]
Type=Application
Name=WattNode
Comment=GPU Mining Power Monitor
Exec=AppRun
Icon=wattnode
Categories=System;Monitor;
'''
        
        (appdir / 'wattnode.desktop').write_text(desktop_content)
        
        # Copy icon if available
        icon_files = ['icon.png', 'wattnode.png', 'app.png']
        for icon_file in icon_files:
            if Path(icon_file).exists():
                shutil.copy2(icon_file, appdir / 'wattnode.png')
                break
        else:
            # Create a simple icon
            (appdir / 'wattnode.png').touch()
        
        # Create AppImage
        result = subprocess.run([
            'appimagetool', 
            str(appdir), 
            'dist/linux/WattNode-x86_64.AppImage'
        ], capture_output=True, text=True)
        
        if result.returncode == 0:
            print("✓ AppImage created successfully")
            Path('dist/linux/WattNode-x86_64.AppImage').chmod(0o755)
        else:
            print("⚠ AppImage creation failed")
            
    except (subprocess.CalledProcessError, FileNotFoundError):
        print("⚠ AppImage creation skipped (appimagetool not available)")

def main():
    """Main function"""
    if build_wattnode():
        print("\n" + "=" * 40)
        print("Build completed successfully!")
        print("\nFiles created:")
        print("- dist/linux/wattnode (main executable)")
        print("- dist/linux/launch_wattnode.sh (launcher script)")
        
        if Path('dist/linux/WattNode-x86_64.AppImage').exists():
            print("- dist/linux/WattNode-x86_64.AppImage (portable)")
        
        print("\nTo run WattNode:")
        print("  ./dist/linux/wattnode")
        print("  or")
        print("  ./dist/linux/launch_wattnode.sh")
        
        if Path('dist/linux/WattNode-x86_64.AppImage').exists():
            print("  or")
            print("  ./dist/linux/WattNode-x86_64.AppImage")
        
        return 0
    else:
        print("\nBuild failed!")
        return 1

if __name__ == '__main__':
    sys.exit(main())