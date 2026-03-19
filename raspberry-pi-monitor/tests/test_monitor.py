import unittest
from unittest.mock import patch, MagicMock, mock_open
import json
import tempfile
import os
from datetime import datetime, timezone

from src.monitor import EnergyMonitor
from src.drivers.mock_driver import MockDriver
from src.drivers.usb_driver import USBDriver
from src.config import Config


class TestEnergyMonitor(unittest.TestCase):
    
    def setUp(self):
        """Set up test fixtures before each test method."""
        self.config_data = {
            "device": {
                "type": "mock",
                "port": "/dev/ttyUSB0",
                "baud_rate": 9600
            },
            "api": {
                "url": "http://localhost:8080",
                "token": "test_token"
            },
            "logging": {
                "level": "INFO",
                "file": "test.log"
            },
            "mock": {
                "voltage_range": [220, 240],
                "current_range": [5, 15],
                "power_range": [1000, 3500]
            }
        }
        
        with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.json') as f:
            json.dump(self.config_data, f)
            self.config_file = f.name
        
        self.config = Config(self.config_file)
        self.monitor = EnergyMonitor(self.config)
    
    def tearDown(self):
        """Clean up after each test method."""
        os.unlink(self.config_file)
    
    def test_monitor_initialization(self):
        """Test monitor initialization with different configurations."""
        self.assertIsInstance(self.monitor.driver, MockDriver)
        self.assertEqual(self.monitor.config.device_type, "mock")
    
    def test_mock_driver_data_generation(self):
        """Test mock driver generates realistic data."""
        driver = MockDriver(self.config)
        data = driver.read_data()
        
        self.assertIsInstance(data, dict)
        self.assertIn('voltage', data)
        self.assertIn('current', data)
        self.assertIn('power', data)
        self.assertIn('timestamp', data)
        
        # Check data ranges
        self.assertGreaterEqual(data['voltage'], 220)
        self.assertLessEqual(data['voltage'], 240)
        self.assertGreaterEqual(data['current'], 5)
        self.assertLessEqual(data['current'], 15)
        self.assertGreaterEqual(data['power'], 1000)
        self.assertLessEqual(data['power'], 3500)
    
    @patch('serial.Serial')
    def test_usb_driver_initialization(self):
        """Test USB driver initialization."""
        mock_serial = MagicMock()
        
        # Update config to use USB driver
        config_data = self.config_data.copy()
        config_data['device']['type'] = 'usb'
        
        with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.json') as f:
            json.dump(config_data, f)
            config_file = f.name
        
        try:
            config = Config(config_file)
            driver = USBDriver(config)
            self.assertIsNotNone(driver)
        finally:
            os.unlink(config_file)
    
    @patch('serial.Serial')
    def test_usb_driver_data_parsing(self):
        """Test USB driver data parsing."""
        mock_serial = MagicMock()
        mock_serial.readline.return_value = b'V:230.5,I:12.3,P:2835.15\n'
        
        config_data = self.config_data.copy()
        config_data['device']['type'] = 'usb'
        
        with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.json') as f:
            json.dump(config_data, f)
            config_file = f.name
        
        try:
            config = Config(config_file)
            driver = USBDriver(config)
            driver.connection = mock_serial
            
            data = driver.read_data()
            
            self.assertEqual(data['voltage'], 230.5)
            self.assertEqual(data['current'], 12.3)
            self.assertEqual(data['power'], 2835.15)
            self.assertIn('timestamp', data)
        finally:
            os.unlink(config_file)
    
    @patch('requests.post')
    def test_api_data_transmission(self):
        """Test API data transmission."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"status": "success"}
        
        mock_post = MagicMock(return_value=mock_response)
        
        test_data = {
            'voltage': 230.5,
            'current': 12.3,
            'power': 2835.15,
            'timestamp': datetime.now(timezone.utc).isoformat()
        }
        
        with patch('requests.post', mock_post):
            result = self.monitor.send_data(test_data)
            self.assertTrue(result)
            mock_post.assert_called_once()
            
            # Verify API call parameters
            call_args = mock_post.call_args
            self.assertEqual(call_args[0][0], self.config.api_url)
            self.assertIn('Authorization', call_args[1]['headers'])
            self.assertEqual(call_args[1]['json'], test_data)
    
    @patch('requests.post')
    def test_api_error_handling(self):
        """Test API error handling."""
        mock_response = MagicMock()
        mock_response.status_code = 500
        mock_response.raise_for_status.side_effect = Exception("Server Error")
        
        mock_post = MagicMock(return_value=mock_response)
        
        test_data = {
            'voltage': 230.5,
            'current': 12.3,
            'power': 2835.15,
            'timestamp': datetime.now(timezone.utc).isoformat()
        }
        
        with patch('requests.post', mock_post):
            result = self.monitor.send_data(test_data)
            self.assertFalse(result)
    
    def test_data_logging(self):
        """Test data logging functionality."""
        with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.log') as f:
            log_file = f.name
        
        try:
            # Update config to use test log file
            config_data = self.config_data.copy()
            config_data['logging']['file'] = log_file
            
            with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.json') as f:
                json.dump(config_data, f)
                config_file = f.name
            
            config = Config(config_file)
            monitor = EnergyMonitor(config)
            
            test_data = {
                'voltage': 230.5,
                'current': 12.3,
                'power': 2835.15,
                'timestamp': datetime.now(timezone.utc).isoformat()
            }
            
            monitor.log_data(test_data)
            
            # Verify log file contains data
            with open(log_file, 'r') as f:
                log_content = f.read()
                self.assertIn('230.5', log_content)
                self.assertIn('12.3', log_content)
                self.assertIn('2835.15', log_content)
            
            os.unlink(config_file)
        finally:
            os.unlink(log_file)
    
    def test_monitor_run_cycle(self):
        """Test complete monitoring cycle."""
        with patch.object(self.monitor, 'send_data', return_value=True) as mock_send:
            with patch.object(self.monitor, 'log_data') as mock_log:
                # Run one monitoring cycle
                data = self.monitor.driver.read_data()
                self.monitor.log_data(data)
                result = self.monitor.send_data(data)
                
                self.assertTrue(result)
                mock_log.assert_called_once_with(data)
                mock_send.assert_called_once_with(data)
    
    def test_config_validation(self):
        """Test configuration validation."""
        # Test invalid config
        invalid_config = {}
        
        with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.json') as f:
            json.dump(invalid_config, f)
            invalid_config_file = f.name
        
        try:
            with self.assertRaises((KeyError, ValueError)):
                Config(invalid_config_file)
        finally:
            os.unlink(invalid_config_file)
    
    def test_data_validation(self):
        """Test data validation and sanitization."""
        # Test with invalid data
        invalid_data = {
            'voltage': 'invalid',
            'current': None,
            'power': -100,
            'timestamp': 'not_a_timestamp'
        }
        
        # Mock driver should not generate invalid data
        valid_data = self.monitor.driver.read_data()
        
        self.assertIsInstance(valid_data['voltage'], (int, float))
        self.assertIsInstance(valid_data['current'], (int, float))
        self.assertIsInstance(valid_data['power'], (int, float))
        self.assertIsInstance(valid_data['timestamp'], str)
        
        # Voltage should be positive
        self.assertGreater(valid_data['voltage'], 0)
        self.assertGreater(valid_data['current'], 0)
        self.assertGreater(valid_data['power'], 0)
    
    def test_mock_mode_configuration(self):
        """Test mock mode specific configuration."""
        # Test custom mock ranges
        custom_config = self.config_data.copy()
        custom_config['mock'] = {
            'voltage_range': [110, 120],
            'current_range': [1, 5],
            'power_range': [100, 600]
        }
        
        with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.json') as f:
            json.dump(custom_config, f)
            config_file = f.name
        
        try:
            config = Config(config_file)
            driver = MockDriver(config)
            
            # Generate multiple readings to test ranges
            for _ in range(10):
                data = driver.read_data()
                self.assertGreaterEqual(data['voltage'], 110)
                self.assertLessEqual(data['voltage'], 120)
                self.assertGreaterEqual(data['current'], 1)
                self.assertLessEqual(data['current'], 5)
                self.assertGreaterEqual(data['power'], 100)
                self.assertLessEqual(data['power'], 600)
        finally:
            os.unlink(config_file)
    
    def test_error_recovery(self):
        """Test error recovery mechanisms."""
        # Test driver failure recovery
        with patch.object(self.monitor.driver, 'read_data', side_effect=Exception("Driver error")):
            try:
                data = self.monitor.driver.read_data()
                self.fail("Expected exception was not raised")
            except Exception as e:
                self.assertEqual(str(e), "Driver error")
        
        # Test API failure recovery (should not crash the monitor)
        with patch('requests.post', side_effect=Exception("Network error")):
            test_data = {'voltage': 230, 'current': 10, 'power': 2300, 'timestamp': '2023-01-01T00:00:00Z'}
            result = self.monitor.send_data(test_data)
            self.assertFalse(result)


if __name__ == '__main__':
    unittest.main()