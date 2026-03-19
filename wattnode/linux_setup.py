#!/usr/bin/env python3
"""
WattNode Linux Setup Script
Handles GPU detection, dependency installation, and AppImage creation
"""

import os
import sys
import subprocess
import shutil
import platform
import json
import urllib.request
from pathlib import Path

class WattNodeLinuxSetup:
    def __init__(self):
        self.arch = platform.machine()
        self.distro = self.detect_distro()
        self.gpu_info = self.detect_gpu()
        self.work_dir = Path.cwd()
        self.build_dir = self.work_dir / "build"
        self.appdir = self.build_dir / "WattNode.AppDir"
        
    def detect_distro(self):
        """Detect Linux distribution"""
        try:
            with open('/etc/os-release', 'r') as f:
                lines = f.readlines()
                distro_info = {}
                for line in lines:
                    if '=' in line:
                        key, value = line.strip().split('=', 1)
                        distro_info[key] = value.strip('"')
                return distro_info.get('ID', 'unknown')
        except:
            return 'unknown'
    
    def detect_gpu(self):
        """Detect available GPUs and their capabilities"""
        gpu_info = {
            'nvidia': False,
            'amd': False,
            'intel': False,
            'cuda': False,
            'opencl': False,
            'vulkan': False
        }
        
        # Check for NVIDIA GPU
        try:
            result = subprocess.run(['nvidia-smi'], capture_output=True, text=True)
            if result.returncode == 0:
                gpu_info['nvidia'] = True
                gpu_info['cuda'] = True
        except:
            pass
        
        # Check for AMD GPU
        try:
            result = subprocess.run(['lspci'], capture_output=True, text=True)
            if 'AMD' in result.stdout or 'Radeon' in result.stdout:
                gpu_info['amd'] = True
        except:
            pass
        
        # Check for Intel GPU
        try:
            result = subprocess.run(['lspci'], capture_output=True, text=True)
            if 'Intel' in result.stdout and 'VGA' in result.stdout:
                gpu_info['intel'] = True
        except:
            pass
        
        # Check OpenCL support
        try:
            result = subprocess.run(['clinfo'], capture_output=True, text=True)
            if result.returncode == 0 and 'Platform' in result.stdout:
                gpu_info['opencl'] = True
        except:
            pass
        
        # Check Vulkan support
        try:
            result = subprocess.run(['vulkaninfo'], capture_output=True, text=True)
            if result.returncode == 0:
                gpu_info['vulkan'] = True
        except:
            pass
        
        return gpu_info
    
    def install_system_dependencies(self):
        """Install system-level dependencies based on distribution"""
        print(f"Installing system dependencies for {self.distro}...")
        
        packages = {
            'ubuntu': [
                'build-essential', 'cmake', 'git', 'curl', 'wget',
                'libnvidia-compute-510', 'nvidia-cuda-toolkit',
                'ocl-icd-opencl-dev', 'clinfo',
                'libvulkan1', 'vulkan-utils', 'vulkan-tools',
                'python3-dev', 'python3-pip', 'python3-venv',
                'libssl-dev', 'libffi-dev', 'zlib1g-dev',
                'libjpeg-dev', 'libpng-dev', 'libfreetype6-dev',
                'libfuse2', 'desktop-file-utils'
            ],
            'debian': [
                'build-essential', 'cmake', 'git', 'curl', 'wget',
                'nvidia-cuda-toolkit',
                'ocl-icd-opencl-dev', 'clinfo',
                'libvulkan1', 'vulkan-utils', 'vulkan-tools',
                'python3-dev', 'python3-pip', 'python3-venv',
                'libssl-dev', 'libffi-dev', 'zlib1g-dev',
                'libjpeg-dev', 'libpng-dev', 'libfreetype6-dev',
                'libfuse2', 'desktop-file-utils'
            ],
            'fedora': [
                'gcc', 'gcc-c++', 'cmake', 'git', 'curl', 'wget',
                'cuda', 'nvidia-driver-cuda',
                'opencl-headers', 'ocl-icd', 'clinfo',
                'vulkan', 'vulkan-tools',
                'python3-devel', 'python3-pip',
                'openssl-devel', 'libffi-devel', 'zlib-devel',
                'libjpeg-turbo-devel', 'libpng-devel', 'freetype-devel',
                'fuse', 'desktop-file-utils'
            ],
            'arch': [
                'base-devel', 'cmake', 'git', 'curl', 'wget',
                'cuda', 'nvidia', 'nvidia-utils',
                'opencl-headers', 'ocl-icd', 'clinfo',
                'vulkan-icd-loader', 'vulkan-tools',
                'python', 'python-pip',
                'openssl', 'libffi', 'zlib',
                'libjpeg-turbo', 'libpng', 'freetype2',
                'fuse2', 'desktop-file-utils'
            ]
        }
        
        distro_packages = packages.get(self.distro, packages['ubuntu'])
        
        if self.distro in ['ubuntu', 'debian']:
            subprocess.run(['sudo', 'apt', 'update'], check=True)
            subprocess.run(['sudo', 'apt', 'install', '-y'] + distro_packages)
        elif self.distro == 'fedora':
            subprocess.run(['sudo', 'dnf', 'install', '-y'] + distro_packages)
        elif self.distro == 'arch':
            subprocess.run(['sudo', 'pacman', '-S', '--noconfirm'] + distro_packages)
        else:
            print(f"Unsupported distribution: {self.distro}")
            print("Please install dependencies manually")
    
    def setup_python_environment(self):
        """Setup Python virtual environment and install Python dependencies"""
        print("Setting up Python environment...")
        
        venv_path = self.build_dir / "venv"
        if venv_path.exists():
            shutil.rmtree(venv_path)
        
        subprocess.run([sys.executable, '-m', 'venv', str(venv_path)], check=True)
        
        pip_path = venv_path / "bin" / "pip"
        python_path = venv_path / "bin" / "python"
        
        # Upgrade pip
        subprocess.run([str(pip_path), 'install', '--upgrade', 'pip'], check=True)
        
        # Install base dependencies
        base_deps = [
            'torch', 'torchvision', 'torchaudio',
            'transformers', 'datasets', 'tokenizers',
            'numpy', 'scipy', 'matplotlib', 'pillow',
            'requests', 'aiohttp', 'websockets',
            'cryptography', 'pynacl',
            'psutil', 'GPUtil',
            'PyQt6', 'PyQt6-WebEngine',
            'pyinstaller'
        ]
        
        # Add GPU-specific dependencies
        if self.gpu_info['cuda']:
            base_deps.extend(['cupy-cuda11x', 'nvidia-ml-py'])
        
        if self.gpu_info['opencl']:
            base_deps.extend(['pyopencl'])
        
        subprocess.run([str(pip_path), 'install'] + base_deps, check=True)
        
        return python_path, pip_path
    
    def build_application(self, python_path):
        """Build the WattNode application"""
        print("Building WattNode application...")
        
        # Create build script
        build_script = self.build_dir / "build_wattnode.py"
        with open(build_script, 'w') as f:
            f.write("""
import sys
import os
from pathlib import Path

# Add source directory to path
sys.path.insert(0, str(Path.cwd().parent / "wattnode"))

# Import and run main application
from main import main

if __name__ == "__main__":
    main()
""")
        
        # Use PyInstaller to create executable
        pyinstaller_args = [
            str(python_path), '-m', 'PyInstaller',
            '--onefile',
            '--windowed',
            '--name', 'WattNode',
            '--icon', str(self.work_dir / 'assets' / 'icon.png'),
            '--add-data', f"{self.work_dir / 'wattnode'}:wattnode",
            '--add-data', f"{self.work_dir / 'assets'}:assets",
            '--hidden-import', 'torch',
            '--hidden-import', 'transformers',
            '--hidden-import', 'PyQt6',
            str(build_script)
        ]
        
        subprocess.run(pyinstaller_args, cwd=self.build_dir, check=True)
    
    def create_appimage(self):
        """Create AppImage package"""
        print("Creating AppImage package...")
        
        # Create AppDir structure
        self.appdir.mkdir(parents=True, exist_ok=True)
        
        # Copy executable
        exe_src = self.build_dir / "dist" / "WattNode"
        exe_dst = self.appdir / "WattNode"
        shutil.copy2(exe_src, exe_dst)
        os.chmod(exe_dst, 0o755)
        
        # Create desktop file
        desktop_content = """[Desktop Entry]
Type=Application
Name=WattNode
Comment=Decentralized GPU Computing Network
Exec=WattNode
Icon=wattnode
Categories=Network;Utility;
Terminal=false
"""
        with open(self.appdir / "WattNode.desktop", 'w') as f:
            f.write(desktop_content)
        
        # Copy icon
        icon_src = self.work_dir / "assets" / "icon.png"
        if icon_src.exists():
            shutil.copy2(icon_src, self.appdir / "wattnode.png")
        
        # Create AppRun script
        apprun_content = """#!/bin/bash
cd "$(dirname "$0")"
exec ./WattNode "$@"
"""
        with open(self.appdir / "AppRun", 'w') as f:
            f.write(apprun_content)
        os.chmod(self.appdir / "AppRun", 0o755)
        
        # Download appimagetool
        appimagetool_path = self.download_appimagetool()
        
        # Create AppImage
        appimage_name = f"WattNode-{self.arch}.AppImage"
        subprocess.run([
            str(appimagetool_path),
            str(self.appdir),
            str(self.build_dir / appimage_name)
        ], check=True)
        
        print(f"AppImage created: {self.build_dir / appimage_name}")
    
    def download_appimagetool(self):
        """Download appimagetool for creating AppImages"""
        appimagetool_url = f"https://github.com/AppImage/AppImageKit/releases/download/continuous/appimagetool-{self.arch}.AppImage"
        appimagetool_path = self.build_dir / "appimagetool.AppImage"
        
        if not appimagetool_path.exists():
            print("Downloading appimagetool...")
            urllib.request.urlretrieve(appimagetool_url, appimagetool_path)
            os.chmod(appimagetool_path, 0o755)
        
        return appimagetool_path
    
    def install_desktop_integration(self):
        """Install desktop integration files"""
        print("Installing desktop integration...")
        
        # Install desktop file
        desktop_dir = Path.home() / ".local" / "share" / "applications"
        desktop_dir.mkdir(parents=True, exist_ok=True)
        
        desktop_content = """[Desktop Entry]
Type=Application
Name=WattNode
Comment=Decentralized GPU Computing Network
Exec={exec_path}
Icon=wattnode
Categories=Network;Utility;
Terminal=false
""".format(exec_path=self.build_dir / f"WattNode-{self.arch}.AppImage")
        
        with open(desktop_dir / "wattnode.desktop", 'w') as f:
            f.write(desktop_content)
        
        # Install icon
        icon_dir = Path.home() / ".local" / "share" / "icons"
        icon_dir.mkdir(parents=True, exist_ok=True)
        
        icon_src = self.work_dir / "assets" / "icon.png"
        if icon_src.exists():
            shutil.copy2(icon_src, icon_dir / "wattnode.png")
        
        # Update desktop database
        try:
            subprocess.run(['update-desktop-database', str(desktop_dir)], check=True)
        except:
            pass
    
    def create_installation_script(self):
        """Create installation script for end users"""
        install_script = self.build_dir / "install.sh"
        
        script_content = f"""#!/bin/bash
set -e

echo "Installing WattNode for Linux..."

# Check architecture
ARCH=$(uname -m)
if [ "$ARCH" != "{self.arch}" ]; then
    echo "Error: This package is for {self.arch}, but you have $ARCH"
    exit 1
fi

# Install to /opt/wattnode
sudo mkdir -p /opt/wattnode
sudo cp WattNode-{self.arch}.AppImage /opt/wattnode/
sudo chmod +x /opt/wattnode/WattNode-{self.arch}.AppImage

# Create symlink
sudo ln -sf /opt/wattnode/WattNode-{self.arch}.AppImage /usr/local/bin/wattnode

# Install desktop file
mkdir -p ~/.local/share/applications
cat > ~/.local/share/applications/wattnode.desktop << EOF
[Desktop Entry]
Type=Application
Name=WattNode
Comment=Decentralized GPU Computing Network
Exec=/opt/wattnode/WattNode-{self.arch}.AppImage
Icon=wattnode
Categories=Network;Utility;
Terminal=false
EOF

# Install icon if available
if [ -f assets/icon.png ]; then
    mkdir -p ~/.local/share/icons
    cp assets/icon.png ~/.local/share/icons/wattnode.png
fi

# Update desktop database
if command -v update-desktop-database >/dev/null 2>&1; then
    update-desktop-database ~/.local/share/applications
fi

echo "WattNode installed successfully!"
echo "You can run it from the applications menu or by typing 'wattnode' in terminal"
"""
        
        with open(install_script, 'w') as f:
            f.write(script_content)
        os.chmod(install_script, 0o755)
    
    def run_tests(self, python_path):
        """Run basic functionality tests"""
        print("Running tests...")
        
        test_script = self.build_dir / "test_wattnode.py"
        with open(test_script, 'w') as f:
            f.write("""
import sys
import torch
import subprocess

def test_torch():
    print("Testing PyTorch...")
    x = torch.randn(2, 3)
    print(f"PyTorch tensor: {x}")
    print(f"CUDA available: {torch.cuda.is_available()}")
    if torch.cuda.is_available():
        print(f"CUDA devices: {torch.cuda.device_count()}")

def test_gpu():
    print("Testing GPU detection...")
    try:
        import GPUtil
        gpus = GPUtil.getGPUs()
        print(f"Found {len(gpus)} GPU(s)")
        for gpu in gpus:
            print(f"  {gpu.name} - {gpu.memoryTotal}MB")
    except:
        print("GPUtil not available")

def test_networking():
    print("Testing networking...")
    import requests
    try:
        response = requests.get("https://httpbin.org/ip", timeout=5)
        print(f"Network test successful: {response.status_code}")
    except Exception as e:
        print(f"Network test failed: {e}")

if __name__ == "__main__":
    test_torch()
    test_gpu()
    test_networking()
    print("All tests completed!")
""")
        
        subprocess.run([str(python_path), str(test_script)], check=True)
    
    def cleanup(self):
        """Clean up build artifacts"""
        print("Cleaning up...")
        
        cleanup_dirs = [
            self.build_dir / "venv",
            self.build_dir / "__pycache__",
            self.build_dir / "build",
            self.build_dir / "dist",
            self.appdir
        ]
        
        for dir_path in cleanup_dirs:
            if dir_path.exists():
                shutil.rmtree(dir_path)
    
    def run_setup(self, skip_system_deps=False):
        """Run the complete setup process"""
        print("WattNode Linux Setup Starting...")
        print(f"Architecture: {self.arch}")
        print(f"Distribution: {self.distro}")
        print(f"GPU Info: {self.gpu_info}")
        
        try:
            # Create build directory
            self.build_dir.mkdir(exist_ok=True)
            
            # Install system dependencies
            if not skip_system_deps:
                self.install_system_dependencies()
            
            # Setup Python environment
            python_path, pip_path = self.setup_python_environment()
            
            # Build application
            self.build_application(python_path)
            
            # Create AppImage
            self.create_appimage()
            
            # Run tests
            self.run_tests(python_path)
            
            # Install desktop integration
            self.install_desktop_integration()
            
            # Create installation script
            self.create_installation_script()
            
            print("\nSetup completed successfully!")
            print(f"AppImage: {self.build_dir / f'WattNode-{self.arch}.AppImage'}")
            print(f"Installation script: {self.build_dir / 'install.sh'}")
            
        except Exception as e:
            print(f"Setup failed: {e}")
            raise

def main():
    import argparse
    
    parser = argparse.ArgumentParser(description="WattNode Linux Setup")
    parser.add_argument("--skip-system-deps", action="store_true",
                       help="Skip system dependency installation")
    parser.add_argument("--cleanup", action="store_true",
                       help="Clean up build artifacts")
    
    args = parser.parse_args()
    
    setup = WattNodeLinuxSetup()
    
    if args.cleanup:
        setup.cleanup()
        return
    
    setup.run_setup(skip_system_deps=args.skip_system_deps)

if __name__ == "__main__":
    main()