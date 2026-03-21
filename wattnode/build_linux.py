# SPDX-License-Identifier: MIT

import os
import sys
import subprocess
import shutil
import logging
from pathlib import Path

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class LinuxBuilder:
    def __init__(self):
        self.project_root = Path(__file__).parent
        self.build_dir = self.project_root / "build"
        self.dist_dir = self.project_root / "dist"
        self.temp_dir = self.project_root / "temp_appimage"
        self.app_name = "WattNode"
        self.version = self._get_version()

    def _get_version(self):
        """Extract version from wattnode/__init__.py or use default"""
        try:
            init_file = self.project_root / "wattnode" / "__init__.py"
            with open(init_file, 'r') as f:
                for line in f:
                    if line.startswith('__version__'):
                        return line.split('=')[1].strip().strip('"\'')
        except FileNotFoundError:
            pass
        return "1.0.0"

    def check_dependencies(self):
        """Check if required build tools are installed"""
        logger.info("Checking build dependencies...")

        required_tools = {
            'pyinstaller': 'pip install pyinstaller',
            'wget': 'sudo apt-get install wget',
            'fuse': 'sudo apt-get install fuse'
        }

        missing = []
        for tool, install_cmd in required_tools.items():
            if shutil.which(tool) is None:
                logger.error(f"Missing {tool}. Install with: {install_cmd}")
                missing.append(tool)

        if missing:
            logger.error(f"Missing dependencies: {', '.join(missing)}")
            return False

        # Check for AppImageTool
        appimage_tool = self.project_root / "appimagetool-x86_64.AppImage"
        if not appimage_tool.exists():
            logger.info("Downloading AppImageTool...")
            self._download_appimage_tool()

        return True

    def _download_appimage_tool(self):
        """Download AppImageTool if not present"""
        url = "https://github.com/AppImage/AppImageKit/releases/download/continuous/appimagetool-x86_64.AppImage"
        tool_path = self.project_root / "appimagetool-x86_64.AppImage"

        try:
            subprocess.run(['wget', '-O', str(tool_path), url], check=True)
            os.chmod(tool_path, 0o755)
            logger.info("AppImageTool downloaded successfully")
        except subprocess.CalledProcessError as e:
            logger.error(f"Failed to download AppImageTool: {e}")
            sys.exit(1)

    def setup_nvidia_detection(self):
        """Setup NVIDIA GPU detection capabilities"""
        logger.info("Setting up NVIDIA GPU detection...")

        # Check if nvidia-smi is available
        nvidia_available = shutil.which('nvidia-smi') is not None

        if nvidia_available:
            logger.info("NVIDIA drivers detected - GPU detection will be enabled")
            return True
        else:
            logger.warning("NVIDIA drivers not found - GPU detection will be limited")
            return False

    def create_pyinstaller_spec(self):
        """Generate PyInstaller spec file for Linux"""
        logger.info("Creating PyInstaller spec file...")

        spec_content = f'''# -*- mode: python ; coding: utf-8 -*-

block_cipher = None

a = Analysis(
    ['wattnode/main.py'],
    pathex=['{self.project_root}'],
    binaries=[],
    datas=[
        ('wattnode/assets/*', 'assets'),
        ('wattnode/config/*', 'config'),
        ('wattnode/templates/*', 'templates'),
    ],
    hiddenimports=[
        'tkinter',
        'tkinter.ttk',
        'PIL',
        'PIL.Image',
        'PIL.ImageTk',
        'requests',
        'psutil',
        'GPUtil',
        'subprocess',
        'threading',
        'queue',
        'json',
        'configparser',
        'logging',
        'pathlib',
        'sqlite3',
        'hashlib',
        'base64',
        'datetime',
        'wattnode.core',
        'wattnode.gui',
        'wattnode.utils',
        'wattnode.wallet',
        'wattnode.network',
    ],
    hookspath=[],
    hooksconfig={{}},
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
    name='{self.app_name}',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='{self.app_name}',
)
'''

        spec_path = self.project_root / f"{self.app_name}.spec"
        with open(spec_path, 'w') as f:
            f.write(spec_content)

        logger.info(f"Spec file created: {spec_path}")
        return spec_path

    def build_with_pyinstaller(self, spec_path):
        """Run PyInstaller build"""
        logger.info("Building application with PyInstaller...")

        cmd = [
            'pyinstaller',
            '--clean',
            '--noconfirm',
            str(spec_path)
        ]

        try:
            result = subprocess.run(cmd, cwd=self.project_root, check=True,
                                  capture_output=True, text=True)
            logger.info("PyInstaller build completed successfully")
            return True
        except subprocess.CalledProcessError as e:
            logger.error(f"PyInstaller build failed: {e}")
            logger.error(f"STDOUT: {e.stdout}")
            logger.error(f"STDERR: {e.stderr}")
            return False

    def create_desktop_file(self):
        """Create .desktop file for AppImage"""
        desktop_content = f"""[Desktop Entry]
Type=Application
Name={self.app_name}
Comment=WattCoin distributed compute node client
Exec={self.app_name}
Icon=wattnode
Categories=Network;System;
Terminal=false
StartupWMClass={self.app_name}
"""

        desktop_path = self.temp_dir / f"{self.app_name}.desktop"
        with open(desktop_path, 'w') as f:
            f.write(desktop_content)

        os.chmod(desktop_path, 0o755)
        return desktop_path

    def prepare_appimage_structure(self):
        """Prepare directory structure for AppImage creation"""
        logger.info("Preparing AppImage directory structure...")

        # Clean and create temp directory
        if self.temp_dir.exists():
            shutil.rmtree(self.temp_dir)
        self.temp_dir.mkdir(parents=True)

        # Copy PyInstaller output
        pyinstaller_output = self.dist_dir / self.app_name
        if not pyinstaller_output.exists():
            logger.error(f"PyInstaller output not found: {pyinstaller_output}")
            return False

        app_dir = self.temp_dir / "usr" / "bin"
        app_dir.mkdir(parents=True)

        # Copy all files from PyInstaller output
        for item in pyinstaller_output.iterdir():
            if item.is_dir():
                shutil.copytree(item, app_dir / item.name)
            else:
                shutil.copy2(item, app_dir)

        # Create AppRun script
        apprun_content = f'''#!/bin/bash
HERE="$(dirname "$(readlink -f "${{0}}")")"
export PATH="${{HERE}}/usr/bin:${{PATH}}"
export LD_LIBRARY_PATH="${{HERE}}/usr/lib:${{LD_LIBRARY_PATH}}"
cd "${{HERE}}/usr/bin"
exec "./{self.app_name}" "$@"
'''

        apprun_path = self.temp_dir / "AppRun"
        with open(apprun_path, 'w') as f:
            f.write(apprun_content)
        os.chmod(apprun_path, 0o755)

        # Create desktop file
        self.create_desktop_file()

        # Copy icon if exists
        icon_sources = [
            self.project_root / "wattnode" / "assets" / "icon.png",
            self.project_root / "assets" / "icon.png",
            self.project_root / "icon.png"
        ]

        for icon_src in icon_sources:
            if icon_src.exists():
                shutil.copy2(icon_src, self.temp_dir / "wattnode.png")
                break
        else:
            logger.warning("No icon found, AppImage will use default")

        return True

    def create_appimage(self):
        """Build the final AppImage"""
        logger.info("Creating AppImage...")

        appimage_tool = self.project_root / "appimagetool-x86_64.AppImage"
        output_name = f"{self.app_name}-{self.version}-x86_64.AppImage"
        output_path = self.dist_dir / output_name

        # Ensure dist directory exists
        self.dist_dir.mkdir(exist_ok=True)

        cmd = [
            str(appimage_tool),
            str(self.temp_dir),
            str(output_path)
        ]

        try:
            env = os.environ.copy()
            env['ARCH'] = 'x86_64'

            result = subprocess.run(cmd, check=True, capture_output=True,
                                  text=True, env=env)

            if output_path.exists():
                os.chmod(output_path, 0o755)
                logger.info(f"AppImage created successfully: {output_path}")
                logger.info(f"Size: {output_path.stat().st_size / 1024 / 1024:.1f} MB")
                return output_path
            else:
                logger.error("AppImage creation failed - output file not found")
                return None

        except subprocess.CalledProcessError as e:
            logger.error(f"AppImage creation failed: {e}")
            logger.error(f"STDOUT: {e.stdout}")
            logger.error(f"STDERR: {e.stderr}")
            return None

    def cleanup(self):
        """Clean up temporary files"""
        logger.info("Cleaning up temporary files...")

        cleanup_paths = [
            self.temp_dir,
            self.project_root / f"{self.app_name}.spec",
            self.build_dir
        ]

        for path in cleanup_paths:
            if path.exists():
                if path.is_dir():
                    shutil.rmtree(path)
                else:
                    path.unlink()

    def verify_build(self, appimage_path):
        """Verify the built AppImage"""
        logger.info("Verifying AppImage build...")

        if not appimage_path or not appimage_path.exists():
            logger.error("AppImage file not found")
            return False

        # Check file permissions
        stat = appimage_path.stat()
        if not (stat.st_mode & 0o111):
            logger.error("AppImage is not executable")
            return False

        # Basic file size check (should be reasonable size)
        size_mb = stat.st_size / 1024 / 1024
        if size_mb < 10:
            logger.warning(f"AppImage seems small ({size_mb:.1f} MB)")
        elif size_mb > 500:
            logger.warning(f"AppImage seems large ({size_mb:.1f} MB)")

        logger.info("AppImage verification passed")
        return True

    def build(self):
        """Main build process"""
        logger.info(f"Starting Linux build for {self.app_name} v{self.version}")

        try:
            # Check dependencies
            if not self.check_dependencies():
                return False

            # Setup NVIDIA detection
            self.setup_nvidia_detection()

            # Create PyInstaller spec
            spec_path = self.create_pyinstaller_spec()

            # Build with PyInstaller
            if not self.build_with_pyinstaller(spec_path):
                return False

            # Prepare AppImage structure
            if not self.prepare_appimage_structure():
                return False

            # Create AppImage
            appimage_path = self.create_appimage()
            if not appimage_path:
                return False

            # Verify build
            if not self.verify_build(appimage_path):
                return False

            logger.info("=" * 60)
            logger.info("BUILD COMPLETED SUCCESSFULLY!")
            logger.info(f"AppImage: {appimage_path}")
            logger.info(f"Size: {appimage_path.stat().st_size / 1024 / 1024:.1f} MB")
            logger.info("=" * 60)

            return True

        except Exception as e:
            logger.error(f"Build failed with error: {e}")
            return False

        finally:
            # Always cleanup temporary files
            self.cleanup()

def main():
    """Main entry point"""
    if len(sys.argv) > 1 and sys.argv[1] == '--help':
        print("WattNode Linux Build Script")
        print("Usage: python build_linux.py [--no-cleanup]")
        print("\nBuilds WattNode AppImage for Linux distribution")
        return

    builder = LinuxBuilder()
    success = builder.build()

    if not success:
        logger.error("Build failed!")
        sys.exit(1)
    else:
        logger.info("Build completed successfully!")

if __name__ == "__main__":
    main()
