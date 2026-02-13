"""
WattNode Configuration Handler
Loads and validates config from YAML file or environment variables
"""

import os
import yaml
from typing import Dict, Any

REQUIRED_FIELDS = ["wallet"]
VALID_CAPABILITIES = ["scrape", "inference"]

def load_config(config_path: str = "config.yaml") -> Dict[str, Any]:
    """
    Load configuration from YAML file.
    Falls back to environment variables if file not found.
    """
    config = {}
    
    # Try loading from YAML file
    if os.path.exists(config_path):
        with open(config_path, 'r') as f:
            config = yaml.safe_load(f) or {}
    
    # Override/supplement with environment variables
    if os.environ.get("WATT_WALLET"):
        config["wallet"] = os.environ["WATT_WALLET"]
    
    if os.environ.get("WATT_PRIVATE_KEY"):
        config["private_key"] = os.environ["WATT_PRIVATE_KEY"]
    
    if os.environ.get("WATT_NODE_NAME"):
        config["name"] = os.environ["WATT_NODE_NAME"]
    
    if os.environ.get("WATT_CAPABILITIES"):
        config["capabilities"] = os.environ["WATT_CAPABILITIES"].split(",")
    
    if os.environ.get("WATT_NODE_ID"):
        config["node_id"] = os.environ["WATT_NODE_ID"]
    
    # Defaults
    if "capabilities" not in config:
        config["capabilities"] = ["scrape"]
    
    if "name" not in config:
        config["name"] = f"wattnode-{os.uname().nodename}"
    
    if "ollama" not in config:
        config["ollama"] = {
            "url": "http://localhost:11434",
            "model": "llama2"
        }
    
    if "heartbeat_interval" not in config:
        config["heartbeat_interval"] = 60
    
    if "poll_interval" not in config:
        config["poll_interval"] = 5
    
    return config


def validate_config(config: Dict[str, Any]) -> bool:
    """
    Validate configuration. Raises ValueError if invalid.
    """
    # Check required fields
    for field in REQUIRED_FIELDS:
        if not config.get(field):
            raise ValueError(f"Missing required config field: {field}")
    
    # Validate wallet format (basic check - 32-44 chars base58)
    wallet = config["wallet"]
    if len(wallet) < 32 or len(wallet) > 44:
        raise ValueError(f"Invalid wallet address format: {wallet}")
    
    # Validate capabilities
    capabilities = config.get("capabilities", [])
    if not capabilities:
        raise ValueError("At least one capability required (scrape, inference)")
    
    for cap in capabilities:
        if cap not in VALID_CAPABILITIES:
            raise ValueError(f"Invalid capability: {cap}. Valid: {VALID_CAPABILITIES}")
    
    # Warn if inference enabled but no Ollama config
    if "inference" in capabilities:
        ollama = config.get("ollama", {})
        print(f"⚠️  Inference capability enabled. Ensure Ollama is running at {ollama.get('url', 'http://localhost:11434')}")
    
    return True


def create_example_config(output_path: str = "config.example.yaml"):
    """Generate example config file"""
    example = """# WattNode Configuration
# Copy to config.yaml and fill in your details

# Your Solana wallet address (required)
wallet: "YourWalletAddress..."

# Private key is NOT stored here for security
# Use environment variable WATT_PRIVATE_KEY or prompt at runtime

# Node name (optional, shown in network)
name: "my-wattnode"

# Capabilities - what jobs this node can handle
capabilities:
  - scrape        # Web scraping jobs
  # - inference   # LLM inference (requires Ollama)

# Ollama settings (if inference enabled)
ollama:
  url: "http://localhost:11434"
  model: "llama2"

# Timing (seconds)
heartbeat_interval: 60
poll_interval: 5
"""
    with open(output_path, 'w') as f:
        f.write(example)
    print(f"Created {output_path}")


if __name__ == "__main__":
    create_example_config()
