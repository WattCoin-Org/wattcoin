#!/bin/bash
set -e

echo "=== WattCoin Sensor Oracle Installer ==="

# Check Python
if ! command -v python3 &> /dev/null; then
    echo "Installing Python3..."
    sudo apt-get update
    sudo apt-get install -y python3 python3-pip
fi

# Install dependencies
echo "Installing Python dependencies..."
pip3 install --user -r requirements.txt 2>/dev/null || echo "No requirements.txt (pure Python, no external deps needed)"

# Create config template
if [ ! -f config.json ]; then
    echo "Creating config.json template..."
    cat > config.json << 'CONFIG'
{
  "sensor_types": ["DHT22", "PIR"],
  "mock_mode": true,
  "interval": 60,
  "api_url": "http://localhost:3000/api/v1/oracle/report",
  "private_key": "",
  "location": "pi_node_1",
  "history_file": "oracle_history.db"
}
CONFIG
    echo "Edit config.json and set your wallet private key!"
fi

# Create systemd service (optional)
if command -v systemctl &> /dev/null; then
    echo "Creating systemd service..."
    sudo tee /etc/systemd/system/wattcoin-oracle.service > /dev/null << 'SERVICE'
[Unit]
Description=WattCoin Sensor Oracle
After=network.target

[Service]
Type=simple
User=pi
WorkingDirectory=/home/pi/wattcoin/sensor_oracle
Environment=WATT_WALLET_KEY=your_key_here
ExecStart=/usr/bin/python3 /home/pi/wattcoin/sensor_oracle/oracle.py --config /home/pi/wattcoin/sensor_oracle/config.json
Restart=always

[Install]
WantedBy=multi-user.target
SERVICE
    echo "Systemd service created. Enable with: sudo systemctl enable wattcoin-oracle"
fi

echo ""
echo "=== Installation Complete ==="
echo "1. Edit config.json with your wallet key"
echo "2. Run: python3 oracle.py --mock (to test)"
echo "3. Run: python3 tests.py (to verify)"
echo ""
