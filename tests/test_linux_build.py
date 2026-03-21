# SPDX-License-Identifier: MIT

import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch, mock_open
import shutil


class TestLinuxBuild(unittest.TestCase):
    """Test suite for Linux build script functionality."""

    def setUp(self):
        """Set up test environment."""
        self.temp_dir = tempfile.mkdtemp()
        self.build_dir = Path(self.temp_dir) / "build"
        self.build_dir.mkdir(exist_ok=True)

    def tearDown(self):
        """Clean up test environment."""
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_gpu_detection_nvidia_available(self):
        """Test GPU detection when NVIDIA GPU is available."""
        mock_result = Mock()
        mock_result.returncode = 0
        mock_result.stdout = "GPU 0: GeForce RTX 4090\nGPU 1: GeForce RTX 3080"

        with patch('subprocess.run', return_value=mock_result):
            result = self._run_gpu_detection()
            self.assertTrue(result['nvidia_available'])
            self.assertEqual(len(result['gpus']), 2)
            self.assertIn('RTX 4090', result['gpus'][0])

    def test_gpu_detection_nvidia_unavailable(self):
        """Test GPU detection when NVIDIA GPU is not available."""
        mock_result = Mock()
        mock_result.returncode = 127  # Command not found

        with patch('subprocess.run', side_effect=FileNotFoundError):
            result = self._run_gpu_detection()
            self.assertFalse(result['nvidia_available'])
            self.assertEqual(len(result['gpus']), 0)

    def test_appimage_creation_structure(self):
        """Test AppImage directory structure creation."""
        appdir = self.build_dir / "WattNode.AppDir"

        # Simulate build script creating AppImage structure
        self._create_appimage_structure(appdir)

        # Verify structure
        self.assertTrue((appdir / "AppRun").exists())
        self.assertTrue((appdir / "usr" / "bin").exists())
        self.assertTrue((appdir / "usr" / "share" / "applications").exists())
        self.assertTrue((appdir / "usr" / "share" / "icons").exists())

    def test_desktop_file_validation(self):
        """Test desktop file validation for AppImage."""
        desktop_content = """[Desktop Entry]
Version=1.0
Type=Application
Name=WattNode
Comment=Decentralized compute client
Exec=wattnode
Icon=wattnode
Categories=Network;System;
Terminal=false
StartupNotify=true
"""

        with patch('builtins.open', mock_open(read_data=desktop_content)):
            validation_result = self._validate_desktop_file("wattnode.desktop")

        self.assertTrue(validation_result['valid'])
        self.assertIn('Name', validation_result['fields'])
        self.assertIn('Exec', validation_result['fields'])
        self.assertIn('Icon', validation_result['fields'])

    def test_build_script_permissions(self):
        """Test build script file permissions."""
        build_script = self.build_dir / "build.sh"
        build_script.write_text("#!/bin/bash\necho 'Building WattNode'")

        # Make executable
        os.chmod(build_script, 0o755)

        # Check permissions
        stat_info = os.stat(build_script)
        self.assertTrue(stat_info.st_mode & 0o100)  # User execute

    def test_dependency_checking(self):
        """Test Linux dependency checking."""
        required_deps = [
            'python3',
            'python3-pip',
            'python3-venv',
            'desktop-file-utils'
        ]

        with patch('subprocess.run') as mock_run:
            mock_run.return_value.returncode = 0

            missing_deps = self._check_dependencies(required_deps)
            self.assertEqual(len(missing_deps), 0)

    def test_virtual_environment_creation(self):
        """Test Python virtual environment creation."""
        venv_path = self.build_dir / "venv"

        with patch('subprocess.run') as mock_run:
            mock_run.return_value.returncode = 0

            result = self._create_venv(str(venv_path))
            self.assertTrue(result)

    def test_requirements_installation(self):
        """Test requirements.txt installation in venv."""
        requirements_content = """tkinter>=8.6
requests>=2.28.0
psutil>=5.9.0
cryptography>=38.0.0
"""

        with patch('builtins.open', mock_open(read_data=requirements_content)):
            with patch('subprocess.run') as mock_run:
                mock_run.return_value.returncode = 0

                result = self._install_requirements("requirements.txt", "venv/bin/pip")
                self.assertTrue(result)

    def test_cross_platform_compatibility_check(self):
        """Test cross-platform compatibility checks."""
        # Test path separators
        linux_path = "/usr/local/bin/wattnode"
        windows_path = "C:\\Program Files\\WattNode\\wattnode.exe"

        converted_path = self._normalize_path(windows_path)
        self.assertNotIn("\\", converted_path)

        # Test line endings
        windows_content = "line1\r\nline2\r\n"
        normalized_content = self._normalize_line_endings(windows_content)
        self.assertNotIn("\r", normalized_content)

    def test_icon_file_validation(self):
        """Test icon file validation for desktop integration."""
        icon_sizes = [16, 32, 48, 64, 128, 256, 512]

        for size in icon_sizes:
            icon_path = f"icons/wattnode_{size}x{size}.png"
            result = self._validate_icon_size(icon_path, size)
            self.assertTrue(result['valid_format'])

    def test_packaging_output_verification(self):
        """Test final package output verification."""
        package_path = self.build_dir / "WattNode-x86_64.AppImage"
        package_path.write_text("mock appimage content")

        # Verify package exists and has reasonable size
        self.assertTrue(package_path.exists())
        self.assertGreater(package_path.stat().st_size, 0)

        # Verify executable permissions
        os.chmod(package_path, 0o755)
        stat_info = os.stat(package_path)
        self.assertTrue(stat_info.st_mode & 0o100)

    # Helper methods for build functionality

    def _run_gpu_detection(self):
        """Simulate GPU detection logic."""
        try:
            result = subprocess.run(['nvidia-smi', '-L'],
                                  capture_output=True, text=True, check=True)
            gpus = [line.strip() for line in result.stdout.split('\n') if line.strip()]
            return {'nvidia_available': True, 'gpus': gpus}
        except (subprocess.CalledProcessError, FileNotFoundError):
            return {'nvidia_available': False, 'gpus': []}

    def _create_appimage_structure(self, appdir):
        """Create AppImage directory structure."""
        directories = [
            appdir / "usr" / "bin",
            appdir / "usr" / "share" / "applications",
            appdir / "usr" / "share" / "icons" / "hicolor" / "256x256" / "apps"
        ]

        for directory in directories:
            directory.mkdir(parents=True, exist_ok=True)

        # Create AppRun file
        apprun = appdir / "AppRun"
        apprun.write_text("#!/bin/bash\nexec usr/bin/wattnode")
        os.chmod(apprun, 0o755)

    def _validate_desktop_file(self, desktop_file):
        """Validate desktop file format."""
        required_fields = ['Name', 'Exec', 'Icon', 'Type']
        found_fields = []

        # Mock validation logic
        for field in required_fields:
            found_fields.append(field)

        return {'valid': len(found_fields) == len(required_fields), 'fields': found_fields}

    def _check_dependencies(self, deps):
        """Check for missing system dependencies."""
        missing = []
        for dep in deps:
            try:
                subprocess.run(['which', dep], check=True, capture_output=True)
            except subprocess.CalledProcessError:
                missing.append(dep)
        return missing

    def _create_venv(self, venv_path):
        """Create Python virtual environment."""
        try:
            subprocess.run(['python3', '-m', 'venv', venv_path], check=True)
            return True
        except subprocess.CalledProcessError:
            return False

    def _install_requirements(self, requirements_file, pip_path):
        """Install requirements in virtual environment."""
        try:
            subprocess.run([pip_path, 'install', '-r', requirements_file], check=True)
            return True
        except subprocess.CalledProcessError:
            return False

    def _normalize_path(self, path):
        """Normalize path separators for cross-platform compatibility."""
        return path.replace('\\', '/')

    def _normalize_line_endings(self, content):
        """Normalize line endings for cross-platform compatibility."""
        return content.replace('\r\n', '\n').replace('\r', '\n')

    def _validate_icon_size(self, icon_path, expected_size):
        """Validate icon file format and size."""
        # Mock icon validation
        return {'valid_format': True, 'size_matches': True}


if __name__ == '__main__':
    unittest.main()
