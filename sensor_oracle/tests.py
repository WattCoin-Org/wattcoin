"""
Tests for the sensor oracle.
"""
import os
import sys
import json
import tempfile
import unittest
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from sensors import DHT22Sensor, PIRSensor, MockGenericSensor, SensorFactory
from signer import WalletSigner
from history import HistoryStore
from config import OracleConfig


class TestSensors(unittest.TestCase):
    """Test sensor implementations."""
    
    def test_dht22_mock(self):
        sensor = DHT22Sensor(mock_mode=True)
        data = sensor.read()
        self.assertEqual(data["unit"], "°C / %")
        self.assertIn("temperature_c", data["value"])
        self.assertIn("humidity_percent", data["value"])
        self.assertTrue(15 <= data["value"]["temperature_c"] <= 35)
        self.assertTrue(30 <= data["value"]["humidity_percent"] <= 80)
    
    def test_pir_mock(self):
        sensor = PIRSensor(mock_mode=True)
        data = sensor.read()
        self.assertIn(data["value"], ["motion_detected", "no_motion"])
        self.assertEqual(data["unit"], "boolean")
    
    def test_mock_generic(self):
        sensor = MockGenericSensor()
        data1 = sensor.read()
        data2 = sensor.read()
        self.assertEqual(data2["value"]["sequence_id"], data1["value"]["sequence_id"] + 1)
    
    def test_sensor_factory(self):
        dht22 = SensorFactory.create("DHT22", mock_mode=True)
        self.assertEqual(dht22.sensor_type, "DHT22")
        
        pir = SensorFactory.create("PIR", mock_mode=True)
        self.assertEqual(pir.sensor_type, "PIR")
        
        with self.assertRaises(ValueError):
            SensorFactory.create("UNKNOWN")


class TestSigner(unittest.TestCase):
    """Test wallet signing."""
    
    def test_sign_and_verify(self):
        signer = WalletSigner("test_key_12345")
        self.assertTrue(signer.wallet_address.startswith("WATT_"))
        
        payload = '{"sensor_type":"DHT22","value":25.5}'
        sig1 = signer.sign(payload)
        sig2 = signer.sign(payload)
        
        # Same payload, same key = same signature
        self.assertEqual(sig1, sig2)
        
        # Different payload = different signature
        sig3 = signer.sign('{"sensor_type":"PIR","value":true}')
        self.assertNotEqual(sig1, sig3)


class TestHistory(unittest.TestCase):
    """Test history store."""
    
    def setUp(self):
        self.temp_db = tempfile.mktemp(suffix='.db')
    
    def tearDown(self):
        if os.path.exists(self.temp_db):
            os.remove(self.temp_db)
    
    def test_store_and_retrieve(self):
        store = HistoryStore(self.temp_db)
        
        report = {
            "sensor_type": "DHT22",
            "reading_value": {"temperature_c": 25.0},
            "unit": "°C",
            "timestamp": "2026-06-02T12:00:00Z",
            "location": "test_lab",
            "wallet_address": "WATT_abc123",
            "signature": "sig_xyz"
        }
        
        store.store(report)
        recent = store.get_recent(limit=10)
        self.assertEqual(len(recent), 1)
        self.assertEqual(recent[0]["sensor_type"], "DHT22")
        
        stats = store.get_stats()
        self.assertEqual(stats["total_readings"], 1)


class TestConfig(unittest.TestCase):
    """Test configuration."""
    
    def test_from_file(self):
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump({
                "sensor_types": ["MOCK"],
                "mock_mode": True,
                "interval": 30,
                "api_url": "http://test.local/api",
                "private_key": "test_key",
                "location": "lab1"
            }, f)
            temp_path = f.name
        
        try:
            config = OracleConfig.from_file(temp_path)
            self.assertEqual(config.sensor_types, ["MOCK"])
            self.assertTrue(config.mock_mode)
            self.assertEqual(config.interval, 30)
            self.assertEqual(config.location, "lab1")
        finally:
            os.remove(temp_path)


if __name__ == '__main__':
    unittest.main()
