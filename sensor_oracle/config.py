"""
Configuration management for the oracle.
"""
import os
import json
from typing import List


class OracleConfig:
    """Oracle configuration."""
    
    def __init__(self):
        self.sensor_types = ["DHT22", "PIR"]
        self.mock_mode = False
        self.interval = 60  # seconds
        self.api_url = "http://localhost:3000/api/v1/oracle/report"
        self.private_key = os.getenv("WATT_WALLET_KEY", "")
        self.location = "default"
        self.history_file = "oracle_history.db"
    
    @classmethod
    def from_file(cls, path: str) -> 'OracleConfig':
        """Load config from JSON file."""
        config = cls()
        
        if os.path.exists(path):
            with open(path, 'r') as f:
                data = json.load(f)
                config.sensor_types = data.get("sensor_types", config.sensor_types)
                config.mock_mode = data.get("mock_mode", config.mock_mode)
                config.interval = data.get("interval", config.interval)
                config.api_url = data.get("api_url", config.api_url)
                config.private_key = data.get("private_key", config.private_key)
                config.location = data.get("location", config.location)
                config.history_file = data.get("history_file", config.history_file)
        
        # Override with env vars
        config.private_key = os.getenv("WATT_WALLET_KEY", config.private_key)
        config.mock_mode = os.getenv("WATT_MOCK_MODE", "false").lower() == "true"
        
        return config
    
    def to_file(self, path: str):
        """Save config to JSON file."""
        data = {
            "sensor_types": self.sensor_types,
            "mock_mode": self.mock_mode,
            "interval": self.interval,
            "api_url": self.api_url,
            "private_key": self.private_key,  # In production, don't store in plain text
            "location": self.location,
            "history_file": self.history_file
        }
        with open(path, 'w') as f:
            json.dump(data, f, indent=2)
