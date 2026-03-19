"""
Configuration loader for Pi Energy Monitor
"""

import os
import yaml
import logging

logger = logging.getLogger(__name__)


def load_config(config_path: str) -> dict:
    """Load configuration from YAML file"""
    
    # Check if file exists
    if not os.path.exists(config_path):
        # Try with .yaml extension
        yaml_path = config_path.replace(".yaml", "") + ".yaml"
        if os.path.exists(yaml_path):
            config_path = yaml_path
        else:
            raise FileNotFoundError(f"Config file not found: {config_path}")
    
    # Load YAML
    with open(config_path, 'r') as f:
        config = yaml.safe_load(f)
    
    # Apply environment variable overrides
    _apply_env_overrides(config)
    
    return config


def _apply_env_overrides(config: dict):
    """Apply environment variable overrides to config"""
    
    # Wallet address
    if os.environ.get("WATT_WALLET"):
        config["wallet_address"] = os.environ["WATT_WALLET"]
    
    # API URL
    if os.environ.get("WATTCOIN_API_URL"):
        if "api" not in config:
            config["api"] = {}
        config["api"]["base_url"] = os.environ["WATTCOIN_API_URL"]
    
    # Hardware device type
    if os.environ.get("WATT_HARDWARE"):
        if "hardware" not in config:
            config["hardware"] = {}
        config["hardware"]["device_type"] = os.environ["WATT_HARDWARE"]
    
    # Kasa host
    if os.environ.get("KASA_HOST"):
        if "hardware" not in config:
            config["hardware"] = {"device_type": "kasa"}
        if "kasa" not in config["hardware"]:
            config["hardware"]["kasa"] = {}
        config["hardware"]["kasa"]["host"] = os.environ["KASA_HOST"]
    
    # Shelly host
    if os.environ.get("SHELLY_HOST"):
        if "hardware" not in config:
            config["hardware"] = {"device_type": "shelly"}
        if "shelly" not in config["hardware"]:
            config["hardware"]["shelly"] = {}
        config["hardware"]["shelly"]["host"] = os.environ["SHELLY_HOST"]


def validate_config(config: dict) -> bool:
    """Validate configuration"""
    
    required_fields = ["wallet_address", "hardware", "polling", "api", "logging"]
    
    for field in required_fields:
        if field not in config:
            raise ValueError(f"Missing required config field: {field}")
    
    # Validate wallet address
    wallet = config["wallet_address"]
    if not wallet or len(wallet) < 32:
        raise ValueError(f"Invalid wallet address: {wallet}")
    
    # Validate hardware
    device_type = config["hardware"].get("device_type")
    if device_type not in ["mock", "kasa", "shelly", "usb_power_meter"]:
        raise ValueError(f"Invalid device_type: {device_type}")
    
    # Validate polling
    interval = config["polling"].get("interval_seconds", 0)
    if interval < 1:
        raise ValueError("polling.interval_seconds must be at least 1")
    
    # Validate API
    if not config["api"].get("base_url"):
        raise ValueError("api.base_url is required")
    
    logger.info("Configuration validated successfully")
    return True


def create_default_config(output_path: str = "config.yaml"):
    """Create a default configuration file"""
    
    default_config = {
        "wallet_address": "YourSolanaWalletAddress...",
        "hardware": {
            "device_type": "mock",
            "mock": {
                "base_watts": 150.0,
                "variance": 10.0
            }
        },
        "polling": {
            "interval_seconds": 60,
            "samples_per_reading": 5,
            "sample_delay": 0.5
        },
        "api": {
            "base_url": "https://your-backend-url.example.com",
            "endpoint": "/api/v1/energy/report",
            "timeout": 30,
            "max_retries": 3,
            "retry_delay": 5
        },
        "logging": {
            "database_path": "energy_data.db",
            "json_log": True,
            "json_log_path": "energy_readings.json",
            "retention_days": 90
        }
    }
    
    with open(output_path, 'w') as f:
        yaml.dump(default_config, f, default_flow_style=False)
    
    logger.info(f"Created default config at {output_path}")
    return default_config
