#!/bin/bash

# Raspberry Pi Energy Monitor Installation Script
set -e

echo "Installing Raspberry Pi Energy Monitor..."

# Update system
echo "Updating system packages..."
sudo apt update && sudo apt upgrade -y

# Install dependencies
echo "Installing dependencies..."
sudo apt install -y python3 python3-pip python3-venv git i2c-tools

# Enable I2C interface
echo "Enabling I2C interface..."
sudo raspi-config nonint do_i2c 0

# Create application directory
APP_DIR="/opt/energy-monitor"
echo "Creating application directory: $APP_DIR"
sudo mkdir -p $APP_DIR
sudo chown $USER:$USER $APP_DIR

# Copy application files
echo "Copying application files..."
cp -r ./* $APP_DIR/

# Create virtual environment
echo "Creating Python virtual environment..."
cd $APP_DIR
python3 -m venv venv
source venv/bin/activate

# Install Python packages
echo "Installing Python dependencies..."
pip install --upgrade pip
pip install -r requirements.txt

# Create systemd service
echo "Creating systemd service..."
sudo tee /etc/systemd/system/energy-monitor.service > /dev/null << EOF
[Unit]
Description=Energy Monitor Service
After=network.target
StartLimitIntervalSec=0

[Service]
Type=simple
Restart=always
RestartSec=1
User=$USER
WorkingDirectory=$APP_DIR
ExecStart=$APP_DIR/venv/bin/python main.py
Environment=PYTHONPATH=$APP_DIR

[Install]
WantedBy=multi-user.target
EOF

# Enable and start service
echo "Enabling and starting service..."
sudo systemctl daemon-reload
sudo systemctl enable energy-monitor.service
sudo systemctl start energy-monitor.service

# Create log directory
sudo mkdir -p /var/log/energy-monitor
sudo chown $USER:$USER /var/log/energy-monitor

# Configure log rotation
sudo tee /etc/logrotate.d/energy-monitor > /dev/null << EOF
/var/log/energy-monitor/*.log {
    daily
    rotate 7
    compress
    delaycompress
    missingok
    notifempty
    create 644 $USER $USER
}
EOF

# Set up GPIO permissions
echo "Setting up GPIO permissions..."
sudo usermod -a -G gpio $USER

# Configure I2C permissions
sudo usermod -a -G i2c $USER

echo "Installation complete!"
echo ""
echo "Configuration:"
echo "- Application installed in: $APP_DIR"
echo "- Service: energy-monitor.service"
echo "- Logs: /var/log/energy-monitor/"
echo ""
echo "Commands:"
echo "- Check status: sudo systemctl status energy-monitor"
echo "- View logs: journalctl -u energy-monitor -f"
echo "- Restart service: sudo systemctl restart energy-monitor"
echo ""
echo "Please reboot your Raspberry Pi to complete the setup:"
echo "sudo reboot"