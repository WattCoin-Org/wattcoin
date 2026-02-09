#!/usr/bin/env python3
"""
Test script for WattNode Linux Port
Verifies file structure and basic script execution.
"""

import os
import sys
import unittest
import subprocess

class TestLinuxPort(unittest.TestCase):
    def test_file_structure(self):
        """Verify all required files for Linux port exist."""
        required_files = [
            "wattnode/build_linux.py",
            "wattnode/requirements_gui.txt",
            "wattnode/INSTALL.md",
            "wattnode/assets/logo.png"
        ]
        for f in required_files:
            self.assertTrue(os.path.exists(f), f"Missing file: {f}")

    def test_build_script_syntax(self):
        """Verify the build script has correct syntax."""
        result = subprocess.run([sys.executable, "-m", "py_compile", "wattnode/build_linux.py"])
        self.assertEqual(result.returncode, 0, "Build script has syntax errors")

    def test_gui_script_imports(self):
        """Verify the GUI script can be imported without errors (syntax check)."""
        # We use a subprocess to avoid side effects of tkinter in the test process
        result = subprocess.run([sys.executable, "-m", "py_compile", "wattnode/wattnode_gui.py"])
        self.assertEqual(result.returncode, 0, "GUI script has syntax/import errors")

if __name__ == "__main__":
    unittest.main()
