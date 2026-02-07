import unittest
import json
import os
from bridge_web import app

class TestWattCoinAPI(unittest.TestCase):
    def setUp(self):
        self.app = app.test_client()
        self.app.testing = True

    def test_health_endpoint(self):
        """Test the /api/v1/health endpoint returns correct structure"""
        response = self.app.get('/api/v1/health')
        self.assertIn(response.status_code, [200, 503])
        
        data = json.loads(response.data)
        self.assertIn('status', data)
        self.assertIn('version', data)
        self.assertIn('services', data)
        self.assertIn('database', data['services'])
        self.assertIn('active_nodes', data)
        self.assertIn('open_tasks', data)

    def test_leaderboard_endpoint(self):
        """Test the /api/v1/tasks/leaderboard endpoint"""
        response = self.app.get('/api/v1/tasks/leaderboard')
        self.assertEqual(response.status_code, 200)
        
        data = json.loads(response.data)
        self.assertTrue(data['success'])
        self.assertIsInstance(data['leaderboard'], list)
        
        if len(data['leaderboard']) > 0:
            entry = data['leaderboard'][0]
            self.assertIn('rank', entry)
            self.assertIn('wallet', entry)
            self.assertIn('total_earned', entry)

    def test_leaderboard_sorting(self):
        """Test leaderboard sorting parameters"""
        # Test sort by completed
        response = self.app.get('/api/v1/tasks/leaderboard?sort_by=completed')
        self.assertEqual(response.status_code, 200)
        
        # Test limit
        response = self.app.get('/api/v1/tasks/leaderboard?limit=5')
        data = json.loads(response.data)
        self.assertLessEqual(len(data['leaderboard']), 5)

if __name__ == '__main__':
    unittest.main()
