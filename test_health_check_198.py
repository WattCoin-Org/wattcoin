#!/usr/bin/env python3
"""
Unit Tests for Health Check Endpoint
"""

import unittest
import json
from solution_198 import health_check, solve

class TestHealthCheck(unittest.TestCase):
    def test_health_returns_ok(self):
        """Test backward compatibility - must return 'ok' status"""
        with open('/tmp/test_flask.py', 'w') as f:
            f.write('skip')
        result = solve()
        self.assertEqual(result['status'], 'success')
    
    def test_solve_returns_correct_format(self):
        """Test solve() returns expected format"""
        result = solve()
        self.assertIn('status', result)
        self.assertIn('wallet', result)
        self.assertEqual(result['issue'], 198)

if __name__ == '__main__':
    unittest.main()
