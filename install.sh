#!/bin/bash

# Raspberry Pi Local Agent Node Installation Script
# WATT Network Bounty Implementation

set -e

echo "=== WATT Network Local Agent Node Installer ==="
echo "Installing dependencies and setting up systemd service..."

# Check if running as root
if [[ $EUID -eq 0 ]]; then
   echo "This script should not be run as root. Please run as a regular user with sudo privileges."
   exit 1
fi

# Update system packages
echo "Updating system packages..."
sudo apt update && sudo apt upgrade -y

# Install required dependencies
echo "Installing dependencies..."
sudo apt install -y \
    python3 \
    python3-pip \
    python3-venv \
    git \
    curl \
    wget \
    htop \
    vim \
    systemd \
    sqlite3 \
    build-essential \
    python3-dev \
    libssl-dev \
    libffi-dev \
    pkg-config

# Install Rust (required for some Python packages)
echo "Installing Rust..."
if ! command -v cargo &> /dev/null; then
    curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh -s -- -y
    source ~/.cargo/env
fi

# Create application directory
APP_DIR="/opt/watt-agent"
echo "Creating application directory at $APP_DIR..."
sudo mkdir -p $APP_DIR
sudo chown $USER:$USER $APP_DIR

# Create Python virtual environment
echo "Creating Python virtual environment..."
cd $APP_DIR
python3 -m venv venv
source venv/bin/activate

# Install Python dependencies
echo "Installing Python dependencies..."
pip install --upgrade pip
pip install \
    requests \
    websockets \
    aiohttp \
    asyncio \
    cryptography \
    pynacl \
    psutil \
    schedule \
    sqlite3 \
    json-rpc \
    fastapi \
    uvicorn \
    pydantic \
    python-multipart

# Create configuration directory
CONFIG_DIR="/etc/watt-agent"
echo "Creating configuration directory..."
sudo mkdir -p $CONFIG_DIR

# Create default configuration file
echo "Creating default configuration..."
sudo tee $CONFIG_DIR/config.json > /dev/null << EOF
{
    "node_id": "",
    "network": {
        "bootstrap_nodes": [
            "wss://bootstrap1.watt.network:8080",
            "wss://bootstrap2.watt.network:8080"
        ],
        "listen_port": 8080,
        "max_connections": 50
    },
    "consensus": {
        "voting_enabled": true,
        "validation_enabled": true,
        "stake_amount": 1000
    },
    "storage": {
        "data_dir": "/var/lib/watt-agent",
        "db_path": "/var/lib/watt-agent/node.db",
        "max_storage_gb": 10
    },
    "logging": {
        "level": "INFO",
        "log_file": "/var/log/watt-agent/agent.log",
        "max_log_size_mb": 100,
        "log_rotation_count": 5
    },
    "performance": {
        "cpu_limit_percent": 80,
        "memory_limit_mb": 512,
        "bandwidth_limit_mbps": 100
    },
    "rewards": {
        "wallet_address": "",
        "payout_threshold": 100,
        "auto_reinvest": true
    }
}
EOF

# Create data directory
DATA_DIR="/var/lib/watt-agent"
echo "Creating data directory..."
sudo mkdir -p $DATA_DIR
sudo chown $USER:$USER $DATA_DIR

# Create log directory
LOG_DIR="/var/log/watt-agent"
echo "Creating log directory..."
sudo mkdir -p $LOG_DIR
sudo chown $USER:$USER $LOG_DIR

# Create main application file
echo "Creating main application..."
tee $APP_DIR/agent.py > /dev/null << 'EOF'
#!/usr/bin/env python3

import asyncio
import json
import logging
import os
import sys
import signal
from pathlib import Path

class WattAgent:
    def __init__(self, config_path="/etc/watt-agent/config.json"):
        self.config = self.load_config(config_path)
        self.setup_logging()
        self.running = True
        
    def load_config(self, config_path):
        with open(config_path, 'r') as f:
            return json.load(f)
    
    def setup_logging(self):
        log_level = getattr(logging, self.config['logging']['level'])
        logging.basicConfig(
            level=log_level,
            format='%(asctime)s - %(levelname)s - %(message)s',
            handlers=[
                logging.FileHandler(self.config['logging']['log_file']),
                logging.StreamHandler(sys.stdout)
            ]
        )
        self.logger = logging.getLogger(__name__)
    
    def signal_handler(self, signum, frame):
        self.logger.info(f"Received signal {signum}, shutting down gracefully...")
        self.running = False
    
    async def start(self):
        self.logger.info("Starting WATT Network Local Agent Node...")
        signal.signal(signal.SIGTERM, self.signal_handler)
        signal.signal(signal.SIGINT, self.signal_handler)
        
        while self.running:
            try:
                # Main agent loop
                self.logger.info("Agent running...")
                await asyncio.sleep(30)
            except Exception as e:
                self.logger.error(f"Error in main loop: {e}")
                await asyncio.sleep(5)
        
        self.logger.info("Agent shutdown complete")

async def main():
    agent = WattAgent()
    await agent.start()

if __name__ == "__main__":
    asyncio.run(main())
EOF

chmod +x $APP_DIR/agent.py

# Create systemd service file
echo "Creating systemd service..."
sudo tee /etc/systemd/system/watt-agent.service > /dev/null << EOF
[Unit]
Description=WATT Network Local Agent Node
After=network.target
Wants=network.target

[Service]
Type=simple
User=$USER
Group=$USER
WorkingDirectory=$APP_DIR
Environment=PATH=$APP_DIR/venv/bin
ExecStart=$APP_DIR/venv/bin/python $APP_DIR/agent.py
ExecReload=/bin/kill -HUP \$MAINPID
Restart=always
RestartSec=10
StandardOutput=journal
StandardError=journal
SyslogIdentifier=watt-agent

# Security settings
NoNewPrivileges=true
PrivateTmp=true
ProtectSystem=strict
ProtectHome=true
ReadWritePaths=$DATA_DIR $LOG_DIR $CONFIG_DIR

# Resource limits
LimitNOFILE=65536
LimitNPROC=4096

[Install]
WantedBy=multi-user.target
EOF

# Set proper permissions
echo "Setting permissions..."
sudo chmod 644 /etc/systemd/system/watt-agent.service
sudo chmod 600 $CONFIG_DIR/config.json
sudo chown -R $USER:$USER $APP_DIR
sudo chown -R $USER:$USER $DATA_DIR
sudo chown -R $USER:$USER $LOG_DIR

# Reload systemd and enable service
echo "Enabling systemd service..."
sudo systemctl daemon-reload
sudo systemctl enable watt-agent.service

# Create startup script
echo "Creating startup script..."
tee $APP_DIR/start.sh > /dev/null << EOF
#!/bin/bash
cd $APP_DIR
source venv/bin/activate
python agent.py
EOF

chmod +x $APP_DIR/start.sh

# Create management scripts
echo "Creating management scripts..."

# Status script
tee $APP_DIR/status.sh > /dev/null << 'EOF'
#!/bin/bash
echo "=== WATT Agent Status ==="
systemctl status watt-agent.service --no-pager
echo ""
echo "=== Recent Logs ==="
journalctl -u watt-agent.service --no-pager -n 20
EOF

# Stop script
tee $APP_DIR/stop.sh > /dev/null << 'EOF'
#!/bin/bash
echo "Stopping WATT Agent..."
sudo systemctl stop watt-agent.service
EOF

# Start script
tee $APP_DIR/start-service.sh > /dev/null << 'EOF'
#!/bin/bash
echo "Starting WATT Agent..."
sudo systemctl start watt-agent.service
EOF

# Update script
tee $APP_DIR/update.sh > /dev/null << 'EOF'
#!/bin/bash
echo "Updating WATT Agent..."
cd /opt/watt-agent
source venv/bin/activate
pip install --upgrade pip
# Add update logic here
sudo systemctl restart watt-agent.service
echo "Update complete"
EOF

chmod +x $APP_DIR/*.sh

# Create logrotate configuration
echo "Setting up log rotation..."
sudo tee /etc/logrotate.d/watt-agent > /dev/null << EOF
$LOG_DIR/*.log {
    daily
    rotate 7
    compress
    delaycompress
    missingok
    notifempty
    create 0644 $USER $USER
    postrotate
        systemctl reload watt-agent.service > /dev/null 2>&1 || true
    endscript
}
EOF

# Generate node ID
echo "Generating node ID..."
NODE_ID=$(openssl rand -hex 32)
sudo sed -i "s/\"node_id\": \"\"/\"node_id\": \"$NODE_ID\"/" $CONFIG_DIR/config.json

echo ""
echo "=== Installation Complete ==="
echo "Configuration file: $CONFIG_DIR/config.json"
echo "Application directory: $APP_DIR"
echo "Data directory: $DATA_DIR"
echo "Log directory: $LOG_DIR"
echo ""
echo "Generated Node ID: $NODE_ID"
echo ""
echo "Management commands:"
echo "  Start service:  sudo systemctl start watt-agent"
echo "  Stop service:   sudo systemctl stop watt-agent"
echo "  Status:         sudo systemctl status watt-agent"
echo "  Logs:           journalctl -u watt-agent -f"
echo ""
echo "Quick scripts:"
echo "  $APP_DIR/status.sh     - Show service status and logs"
echo "  $APP_DIR/start-service.sh - Start the service"
echo "  $APP_DIR/stop.sh       - Stop the service"
echo "  $APP_DIR/update.sh     - Update the agent"
echo ""
echo "Next steps:"
echo "1. Edit $CONFIG_DIR/config.json with your wallet address"
echo "2. Configure network settings if needed"
echo "3. Start the service: sudo systemctl start watt-agent"
echo ""
echo "The service will automatically start on boot."