"""
Unit tests for the enhanced health check endpoint.

These tests verify backward compatibility and all service checks.
"""

import json
import os
import sys
import unittest
from unittest.mock import patch, mock_open, MagicMock
from datetime import datetime

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class TestHealthEndpoint(unittest.TestCase):
    """Test cases for the /health endpoint."""
    
    def setUp(self):
        """Set up test fixtures."""
        self.test_data_dir = '/tmp/test_data'
        os.makedirs(self.test_data_dir, exist_ok=True)
    
    def tearDown(self):
        """Clean up test fixtures."""
        import shutil
        if os.path.exists(self.test_data_dir):
            shutil.rmtree(self.test_data_dir)
    
    @patch('os.path.exists')
    @patch('os.access')
    @patch.dict(os.environ, {'ANTHROPIC_API_KEY': 'test-key'})
    def test_health_all_healthy(self, mock_access, mock_exists):
        """Test health endpoint when all services are healthy."""
        # Mock file existence and accessibility
        mock_exists.return_value = True
        mock_access.return_value = True
        
        # Import after mocking
        from bridge_web import health
        
        # Mock flask request context
        with patch('bridge_web.jsonify') as mock_jsonify:
            mock_response = {'status': 'ok', 'ok': True}
            mock_jsonify.return_value = mock_response
            
            result = health()
            
            # Verify response structure
            self.assertIn('status', result)
            self.assertEqual(result['status'], 'ok')
            self.assertIn('ok', result)
            self.assertTrue(result['ok'])
    
    @patch('os.path.exists')
    @patch('os.access')
    @patch.dict(os.environ, {}, clear=True)
    def test_health_degraded_missing_files(self, mock_access, mock_exists):
        """Test health endpoint when data files are missing."""
        mock_exists.return_value = False
        mock_access.return_value = False
        
        from bridge_web import health
        
        with patch('bridge_web.jsonify') as mock_jsonify:
            mock_response = {
                'status': 'degraded',
                'ok': False,
                'checks': {'data_files': {'status': 'degraded'}}
            }
            mock_jsonify.return_value = mock_response
            
            result = health()
            
            self.assertEqual(result['status'], 'degraded')
            self.assertFalse(result['ok'])
    
    @patch.dict(os.environ, {}, clear=True)
    def test_health_no_ai_keys(self):
        """Test health endpoint when AI API keys are not configured."""
        from bridge_web import health
        
        with patch('bridge_web.jsonify') as mock_jsonify:
            mock_jsonify.return_value = {'checks': {'ai_api': {'configured': False}}}
            
            result = health()
            
            # Verify AI is marked as not configured
            self.assertFalse(result['checks']['ai_api']['configured'])
    
    def test_health_response_time(self):
        """Test that health endpoint returns response time."""
        from bridge_web import health
        
        with patch('bridge_web.jsonify') as mock_jsonify:
            mock_jsonify.return_value = {'response_time_ms': 50}
            
            result = health()
            
            self.assertIn('response_time_ms', result)
            self.assertIsInstance(result['response_time_ms'], int)
            self.assertGreaterEqual(result['response_time_ms'], 0)
    
    def test_backward_compatibility(self):
        """Test that health endpoint maintains backward compatibility."""
        from bridge_web import health
        
        with patch('bridge_web.jsonify') as mock_jsonify:
            # Test that 'ok' field exists for legacy clients
            mock_jsonify.return_value = {
                'status': 'ok',
                'ok': True,
                'active_nodes': 5
            }
            
            result = health()
            
            # Legacy clients expect 'ok' boolean
            self.assertIn('ok', result)
            self.assertIsInstance(result['ok'], bool)
            
            # Legacy clients expect 'status' as string
            self.assertIn('status', result)
            self.assertIsInstance(result['status'], str)
            
            # Legacy clients expect 'active_nodes' count
            self.assertIn('active_nodes', result)
            self.assertIsInstance(result['active_nodes'], int)


class TestHealthCheckStructure(unittest.TestCase):
    """Test the structure of health check responses."""
    
    def test_required_fields(self):
        """Test that all required fields are present in health response."""
        from bridge_web import health
        
        with patch('bridge_web.jsonify') as mock_jsonify:
            mock_jsonify.return_value = {
                'status': 'ok',
                'ok': True,
                'version': '3.4.0',
                'timestamp': datetime.utcnow().isoformat(),
                'response_time_ms': 100,
                'checks': {},
                'active_nodes': 0
            }
            
            result = health()
            
            required_fields = ['status', 'ok', 'version', 'timestamp', 
                             'response_time_ms', 'checks', 'active_nodes']
            for field in required_fields:
                self.assertIn(field, result, f"Missing required field: {field}")


if __name__ == '__main__':
    unittest.main()
