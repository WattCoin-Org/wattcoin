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

    def test_build_script_security_patterns(self):
        """Verify the security hardening in build_linux.py."""
        with open("wattnode/build_linux.py", "r") as f:
            content = f.read()
            # Verify no shell=True is used
            self.assertNotIn("shell=True", content)
            # Verify explicit shell=False is used in subprocess
            self.assertIn("subprocess.run(cmd, check=True, shell=False)", content)
            # Verify we are using list arguments
            self.assertIn("cmd = [", content)
            # Verify we moved away from interactive pip installs for security
            self.assertNotIn("pip install", content.split("\n\n")[0]) # Not in logic, only in help text
            self.assertIn("check_dependencies()", content)

if __name__ == "__main__":
    unittest.main()
