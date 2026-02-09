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
        result = subprocess.run([sys.executable, "-m", "py_compile", "wattnode/wattnode_gui.py"], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, f"GUI script has syntax/import errors: {result.stderr}")

    def test_build_script_confirm_install_logic(self):
        """Verify the input validation in build_linux.py."""
        # This is a bit tricky to test directly as it uses input(), 
        # but we can verify the function existence and logic pattern.
        with open("wattnode/build_linux.py", "r") as f:
            content = f.read()
            self.assertIn("valid_responses = {\"y\": True, \"n\": False, \"yes\": True, \"no\": False}", content)
            self.assertIn("while True:", content)
            self.assertIn("shell=False", content)

if __name__ == "__main__":
    unittest.main()
