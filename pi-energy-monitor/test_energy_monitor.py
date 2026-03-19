"""
Unit tests for Pi Energy Monitor
"""

import os
import sys
import json
import time
import tempfile
import unittest
from datetime import datetime, timezone, timedelta
from unittest.mock import Mock, patch, MagicMock

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from hardware import (
    MockPowerMeter,
    KasaPowerMeter,
    ShellyPowerMeter,
    create_hardware_driver
)
from config import load_config, validate_config, create_default_config
from api_client import EnergyAPIClient
from logger import EnergyLogger


class TestMockPowerMeter(unittest.TestCase):
    """Tests for MockPowerMeter"""
    
    def test_name(self):
        """Test device name"""
        meter = MockPowerMeter()
        self.assertEqual(meter.name, "mock")
    
    def test_read_power(self):
        """Test power reading"""
        meter = MockPowerMeter({"base_watts": 100.0, "variance": 5.0})
        watts = meter.read_power()
        self.assertIsInstance(watts, float)
        self.assertGreater(watts, 0)
    
    def test_read_power_range(self):
        """Test power reading is within expected range"""
        meter = MockPowerMeter({"base_watts": 100.0, "variance": 10.0})
        readings = [meter.read_power() for _ in range(100)]
        # Most readings should be within variance
        in_range = sum(1 for r in readings if 90 <= r <= 110)
        self.assertGreater(in_range, 80)


class TestHardwareFactory(unittest.TestCase):
    """Tests for hardware driver factory"""
    
    def test_create_mock(self):
        """Test creating mock driver"""
        driver = create_hardware_driver("mock")
        self.assertIsInstance(driver, MockPowerMeter)
    
    def test_create_kasa(self):
        """Test creating Kasa driver"""
        driver = create_hardware_driver("kasa", {"host": "192.168.1.100"})
        self.assertIsInstance(driver, KasaPowerMeter)
        self.assertEqual(driver.host, "192.168.1.100")
    
    def test_create_shelly(self):
        """Test creating Shelly driver"""
        driver = create_hardware_driver("shelly", {"host": "192.168.1.101"})
        self.assertIsInstance(driver, ShellyPowerMeter)
        self.assertEqual(driver.host, "192.168.1.101")
    
    def test_invalid_device(self):
        """Test invalid device type raises error"""
        with self.assertRaises(ValueError):
            create_hardware_driver("invalid_device")


class TestConfig(unittest.TestCase):
    """Tests for configuration"""
    
    def setUp(self):
        """Create temp config file"""
        self.temp_dir = tempfile.mkdtemp()
        self.config_path = os.path.join(self.temp_dir, "config.yaml")
    
    def tearDown(self):
        """Clean up temp files"""
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)
    
    def test_create_default_config(self):
        """Test creating default config"""
        create_default_config(self.config_path)
        self.assertTrue(os.path.exists(self.config_path))
        
        config = load_config(self.config_path)
        self.assertIn("wallet_address", config)
        self.assertIn("hardware", config)
        self.assertIn("polling", config)
    
    def test_validate_config_valid(self):
        """Test validating valid config"""
        config = {
            "wallet_address": "MockWallet12345678901234567890123456789012",
            "hardware": {"device_type": "mock"},
            "polling": {"interval_seconds": 60},
            "api": {"base_url": "http://localhost:8000"},
            "logging": {"database_path": "test.db"}
        }
        self.assertTrue(validate_config(config))
    
    def test_validate_config_missing_field(self):
        """Test validation fails with missing field"""
        config = {
            "wallet_address": "MockWallet12345678901234567890123456789012",
            # Missing hardware
            "polling": {"interval_seconds": 60},
            "api": {"base_url": "http://localhost:8000"},
            "logging": {"database_path": "test.db"}
        }
        with self.assertRaises(ValueError):
            validate_config(config)
    
    def test_validate_config_invalid_wallet(self):
        """Test validation fails with invalid wallet"""
        config = {
            "wallet_address": "short",
            "hardware": {"device_type": "mock"},
            "polling": {"interval_seconds": 60},
            "api": {"base_url": "http://localhost:8000"},
            "logging": {"database_path": "test.db"}
        }
        with self.assertRaises(ValueError):
            validate_config(config)
    
    def test_validate_config_invalid_device(self):
        """Test validation fails with invalid device"""
        config = {
            "wallet_address": "MockWallet12345678901234567890123456789012",
            "hardware": {"device_type": "invalid"},
            "polling": {"interval_seconds": 60},
            "api": {"base_url": "http://localhost:8000"},
            "logging": {"database_path": "test.db"}
        }
        with self.assertRaises(ValueError):
            validate_config(config)


class TestAPIClient(unittest.TestCase):
    """Tests for API client"""
    
    def setUp(self):
        """Set up test client"""
        self.client = EnergyAPIClient(
            base_url="http://localhost:8000",
            endpoint="/api/v1/energy/report",
            wallet_address="MockWallet12345678901234567890123456789012",
            timeout=30,
            max_retries=3
        )
    
    def tearDown(self):
        """Clean up"""
        self.client.close()
    
    def test_api_url(self):
        """Test API URL construction"""
        self.assertEqual(
            self.client.api_url,
            "http://localhost:8000/api/v1/energy/report"
        )
    
    @patch('requests.Session.post')
    def test_send_report_success(self, mock_post):
        """Test successful report sending"""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"success": True}
        mock_post.return_value = mock_response
        
        report = {
            "timestamp": "2024-01-15T10:00:00Z",
            "wallet": "MockWallet12345678901234567890123456789012",
            "watts": 100.0,
            "device_type": "mock",
            "signature": "test_signature"
        }
        
        result = self.client.send_report(report)
        self.assertTrue(result)
    
    @patch('requests.Session.post')
    def test_send_report_server_error(self, mock_post):
        """Test report sending with server error (should retry)"""
        mock_response = Mock()
        mock_response.status_code = 500
        mock_response.text = "Internal Server Error"
        mock_post.return_value = mock_response
        
        report = {
            "timestamp": "2024-01-15T10:00:00Z",
            "wallet": "MockWallet12345678901234567890123456789012",
            "watts": 100.0,
            "device_type": "mock",
            "signature": "test_signature"
        }
        
        result = self.client.send_report(report)
        self.assertFalse(result)
    
    @patch('requests.Session.post')
    def test_send_report_client_error(self, mock_post):
        """Test report sending with client error (should not retry)"""
        mock_response = Mock()
        mock_response.status_code = 400
        mock_response.text = "Bad Request"
        mock_post.return_value = mock_response
        
        report = {
            "timestamp": "2024-01-15T10:00:00Z",
            "wallet": "MockWallet12345678901234567890123456789012",
            "watts": 100.0,
            "device_type": "mock",
            "signature": "test_signature"
        }
        
        result = self.client.send_report(report)
        self.assertFalse(result)
    
    @patch('requests.Session.post')
    def test_send_report_timeout(self, mock_post):
        """Test report sending with timeout"""
        import requests
        mock_post.side_effect = requests.Timeout()
        
        report = {
            "timestamp": "2024-01-15T10:00:00Z",
            "wallet": "MockWallet12345678901234567890123456789012",
            "watts": 100.0,
            "device_type": "mock",
            "signature": "test_signature"
        }
        
        result = self.client.send_report(report)
        self.assertFalse(result)


class TestEnergyLogger(unittest.TestCase):
    """Tests for EnergyLogger"""
    
    def setUp(self):
        """Set up temp database"""
        self.temp_dir = tempfile.mkdtemp()
        self.db_path = os.path.join(self.temp_dir, "test_energy.db")
        self.json_path = os.path.join(self.temp_dir, "test_readings.json")
        
        self.logger = EnergyLogger(
            database_path=self.db_path,
            json_log=True,
            json_log_path=self.json_path,
            retention_days=90
        )
    
    def tearDown(self):
        """Clean up"""
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)
    
    def test_log_reading(self):
        """Test logging a reading"""
        report = {
            "timestamp": "2024-01-15T10:00:00Z",
            "wallet": "MockWallet12345678901234567890123456789012",
            "watts": 100.5,
            "device_type": "mock",
            "client_version": "1.0.0",
            "signature": "test_sig"
        }
        
        self.logger.log_reading(report)
        
        # Check database
        readings = self.logger.get_readings()
        self.assertEqual(len(readings), 1)
        self.assertEqual(readings[0]["watts"], 100.5)
    
    def test_log_reading_json(self):
        """Test JSON logging"""
        report = {
            "timestamp": "2024-01-15T10:00:00Z",
            "wallet": "MockWallet12345678901234567890123456789012",
            "watts": 100.5,
            "device_type": "mock"
        }
        
        self.logger.log_reading(report)
        
        # Check JSON file
        self.assertTrue(os.path.exists(self.json_path))
        with open(self.json_path) as f:
            data = json.load(f)
            self.assertEqual(len(data), 1)
            self.assertEqual(data[0]["watts"], 100.5)
    
    def test_get_statistics(self):
        """Test getting statistics"""
        from datetime import timezone, timedelta
        now = datetime.now(timezone.utc)
        # Add some readings with current timestamps
        for i in range(5):
            ts = (now - timedelta(minutes=i)).isoformat()
            self.logger.log_reading({
                "timestamp": ts,
                "wallet": "MockWallet12345678901234567890123456789012",
                "watts": 100.0 + i * 10,
                "device_type": "mock",
                "signature": f"sig_{i}"
            })
        
        stats = self.logger.get_statistics(hours=24)
        self.assertEqual(stats["count"], 5)
        self.assertEqual(stats["min_watts"], 100.0)
        self.assertEqual(stats["max_watts"], 140.0)
    
    def test_get_readings_with_limit(self):
        """Test getting readings with limit"""
        # Add 10 readings
        for i in range(10):
            self.logger.log_reading({
                "timestamp": f"2024-01-15T10:{i:02d}:00Z",
                "wallet": "MockWallet12345678901234567890123456789012",
                "watts": 100.0,
                "device_type": "mock",
                "signature": f"sig_{i}"
            })
        
        readings = self.logger.get_readings(limit=5)
        self.assertEqual(len(readings), 5)


class TestKasaPowerMeter(unittest.TestCase):
    """Tests for KasaPowerMeter"""
    
    def test_name(self):
        """Test device name"""
        meter = KasaPowerMeter({"host": "192.168.1.100"})
        self.assertEqual(meter.name, "kasa:192.168.1.100")
    
    def test_default_port(self):
        """Test default port"""
        meter = KasaPowerMeter({"host": "192.168.1.100"})
        self.assertEqual(meter.port, 9999)


class TestShellyPowerMeter(unittest.TestCase):
    """Tests for ShellyPowerMeter"""
    
    def test_name(self):
        """Test device name"""
        meter = ShellyPowerMeter({"host": "192.168.1.101"})
        self.assertEqual(meter.name, "shelly:192.168.1.101")
    
    @patch('requests.get')
    def test_read_power(self, mock_get):
        """Test reading power from Shelly"""
        mock_response = Mock()
        mock_response.json.return_value = {
            "meters": [{"power": 125.5}]
        }
        mock_get.return_value = mock_response
        
        meter = ShellyPowerMeter({"host": "192.168.1.101"})
        watts = meter.read_power()
        
        self.assertEqual(watts, 125.5)
    
    @patch('requests.get')
    def test_read_power_emeter(self, mock_get):
        """Test reading power from Shelly emeter"""
        mock_response = Mock()
        mock_response.json.return_value = {
            "emeters": [{"power": 200.0}]
        }
        mock_get.return_value = mock_response
        
        meter = ShellyPowerMeter({"host": "192.168.1.101"})
        watts = meter.read_power()
        
        self.assertEqual(watts, 200.0)


if __name__ == "__main__":
    unittest.main()
