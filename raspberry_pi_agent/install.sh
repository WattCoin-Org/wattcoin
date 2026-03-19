#!/bin/bash

set -e

# Raspberry Pi Agent Installation Script
# This script installs and configures the local agent node

INSTALL_DIR="/opt/raspberry_pi_agent"
SERVICE_NAME="raspberry-pi-agent"
SERVICE_USER="pi-agent"
CONFIG_DIR="/etc/raspberry-pi-agent"
LOG_DIR="/var/log/raspberry-pi-agent"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

log() {
    echo -e "${GREEN}[$(date +'%Y-%m-%d %H:%M:%S')] $1${NC}"
}

warn() {
    echo -e "${YELLOW}[$(date +'%Y-%m-%d %H:%M:%S')] WARNING: $1${NC}"
}

error() {
    echo -e "${RED}[$(date +'%Y-%m-%d %H:%M:%S')] ERROR: $1${NC}"
    exit 1
}

check_root() {
    if [ "$EUID" -ne 0 ]; then
        error "Please run as root (use sudo)"
    fi
}

detect_pi() {
    if ! grep -q "Raspberry Pi" /proc/device-tree/model 2>/dev/null; then
        warn "This doesn't appear to be a Raspberry Pi"
        read -p "Continue anyway? (y/N): " -n 1 -r
        echo
        if [[ ! $REPLY =~ ^[Yy]$ ]]; then
            exit 1
        fi
    fi
}

update_system() {
    log "Updating system packages..."
    apt-get update -qq
    apt-get upgrade -y -qq
}

install_dependencies() {
    log "Installing system dependencies..."
    apt-get install -y \
        python3 \
        python3-pip \
        python3-venv \
        git \
        curl \
        wget \
        build-essential \
        libssl-dev \
        libffi-dev \
        python3-dev \
        supervisor \
        nginx \
        sqlite3 \
        i2c-tools \
        python3-smbus \
        python3-rpi.gpio \
        gpio \
        wiringpi \
        mosquitto \
        mosquitto-clients
}

create_user() {
    log "Creating service user..."
    if ! id "$SERVICE_USER" &>/dev/null; then
        useradd --system --shell /bin/false --home-dir /nonexistent --no-create-home "$SERVICE_USER"
        usermod -a -G gpio,i2c,spi,dialout "$SERVICE_USER"
    fi
}

create_directories() {
    log "Creating directories..."
    mkdir -p "$INSTALL_DIR"
    mkdir -p "$CONFIG_DIR"
    mkdir -p "$LOG_DIR"
    
    chown -R "$SERVICE_USER:$SERVICE_USER" "$INSTALL_DIR"
    chown -R "$SERVICE_USER:$SERVICE_USER" "$LOG_DIR"
    chown -R root:root "$CONFIG_DIR"
    chmod 755 "$CONFIG_DIR"
}

install_python_deps() {
    log "Setting up Python virtual environment..."
    python3 -m venv "$INSTALL_DIR/venv"
    source "$INSTALL_DIR/venv/bin/activate"
    
    log "Installing Python packages..."
    pip install --upgrade pip setuptools wheel
    pip install \
        fastapi \
        uvicorn \
        pydantic \
        aiofiles \
        psutil \
        RPi.GPIO \
        adafruit-circuitpython-dht \
        w1thermsensor \
        paho-mqtt \
        requests \
        websockets \
        cryptography \
        python-multipart \
        jinja2 \
        sqlalchemy \
        aiosqlite
}

copy_files() {
    log "Copying application files..."
    cp -r ./src/* "$INSTALL_DIR/"
    cp -r ./config/* "$CONFIG_DIR/"
    
    chown -R "$SERVICE_USER:$SERVICE_USER" "$INSTALL_DIR"
    chmod +x "$INSTALL_DIR/main.py"
}

configure_gpio() {
    log "Configuring GPIO access..."
    if ! grep -q "^gpio:" /etc/group; then
        groupadd gpio
    fi
    
    # Add udev rules for GPIO access
    cat > /etc/udev/rules.d/99-gpio.rules << EOF
KERNEL=="gpiochip*", GROUP="gpio", MODE="0664"
KERNEL=="gpio*", GROUP="gpio", MODE="0664"
EOF
    
    # Enable I2C and SPI
    if ! grep -q "^dtparam=i2c_arm=on" /boot/config.txt; then
        echo "dtparam=i2c_arm=on" >> /boot/config.txt
    fi
    
    if ! grep -q "^dtparam=spi=on" /boot/config.txt; then
        echo "dtparam=spi=on" >> /boot/config.txt
    fi
    
    # Load I2C module
    if ! grep -q "^i2c-dev" /etc/modules; then
        echo "i2c-dev" >> /etc/modules
    fi
}

create_systemd_service() {
    log "Creating systemd service..."
    cat > /etc/systemd/system/$SERVICE_NAME.service << EOF
[Unit]
Description=Raspberry Pi Agent Node
After=network.target
Wants=network-online.target

[Service]
Type=simple
User=$SERVICE_USER
Group=$SERVICE_USER
WorkingDirectory=$INSTALL_DIR
Environment=PATH=$INSTALL_DIR/venv/bin
ExecStart=$INSTALL_DIR/venv/bin/python main.py
Restart=always
RestartSec=10
StandardOutput=journal
StandardError=journal
SyslogIdentifier=$SERVICE_NAME

# Security settings
NoNewPrivileges=true
ProtectSystem=strict
ProtectHome=true
ReadWritePaths=$LOG_DIR $CONFIG_DIR
PrivateTmp=true
ProtectKernelTunables=true
ProtectControlGroups=true
RestrictRealtime=true
RestrictSUIDSGID=true

[Install]
WantedBy=multi-user.target
EOF

    systemctl daemon-reload
    systemctl enable $SERVICE_NAME
}

configure_nginx() {
    log "Configuring nginx reverse proxy..."
    cat > /etc/nginx/sites-available/raspberry-pi-agent << EOF
server {
    listen 80;
    server_name _;
    
    location / {
        proxy_pass http://127.0.0.1:8080;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
    }
    
    location /ws {
        proxy_pass http://127.0.0.1:8080;
        proxy_http_version 1.1;
        proxy_set_header Upgrade \$http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
    }
}
EOF

    ln -sf /etc/nginx/sites-available/raspberry-pi-agent /etc/nginx/sites-enabled/
    rm -f /etc/nginx/sites-enabled/default
    nginx -t
    systemctl enable nginx
    systemctl restart nginx
}

configure_mosquitto() {
    log "Configuring MQTT broker..."
    cat > /etc/mosquitto/conf.d/raspberry-pi-agent.conf << EOF
# Local MQTT configuration for Raspberry Pi Agent
listener 1883 127.0.0.1
allow_anonymous true
persistence true
persistence_location /var/lib/mosquitto/
log_dest file /var/log/mosquitto/mosquitto.log
EOF

    systemctl enable mosquitto
    systemctl restart mosquitto
}

setup_logrotate() {
    log "Setting up log rotation..."
    cat > /etc/logrotate.d/raspberry-pi-agent << EOF
$LOG_DIR/*.log {
    daily
    rotate 7
    compress
    delaycompress
    missingok
    notifempty
    create 644 $SERVICE_USER $SERVICE_USER
    postrotate
        systemctl reload $SERVICE_NAME
    endscript
}
EOF
}

create_default_config() {
    log "Creating default configuration..."
    if [ ! -f "$CONFIG_DIR/config.json" ]; then
        cat > "$CONFIG_DIR/config.json" << EOF
{
    "server": {
        "host": "0.0.0.0",
        "port": 8080,
        "workers": 1
    },
    "database": {
        "path": "$INSTALL_DIR/data/agent.db"
    },
    "mqtt": {
        "broker": "localhost",
        "port": 1883,
        "username": null,
        "password": null,
        "topics": {
            "telemetry": "agent/telemetry",
            "commands": "agent/commands",
            "status": "agent/status"
        }
    },
    "sensors": {
        "enabled": true,
        "scan_interval": 60,
        "temperature_sensors": [],
        "gpio_sensors": []
    },
    "network": {
        "discovery_enabled": true,
        "discovery_port": 8081,
        "heartbeat_interval": 30
    },
    "security": {
        "api_key_required": false,
        "allowed_ips": [],
        "rate_limit": {
            "enabled": true,
            "requests_per_minute": 100
        }
    },
    "logging": {
        "level": "INFO",
        "file": "$LOG_DIR/agent.log",
        "max_size": "10MB",
        "backup_count": 5
    }
}
EOF
    fi
}

post_install_setup() {
    log "Running post-installation setup..."
    
    # Create data directory
    mkdir -p "$INSTALL_DIR/data"
    chown -R "$SERVICE_USER:$SERVICE_USER" "$INSTALL_DIR/data"
    
    # Generate API key
    API_KEY=$(openssl rand -hex 32)
    echo "Generated API Key: $API_KEY" > "$CONFIG_DIR/api_key.txt"
    chmod 600 "$CONFIG_DIR/api_key.txt"
    
    # Get system info
    PI_MODEL=$(cat /proc/device-tree/model | tr -d '\0' 2>/dev/null || echo "Unknown")
    PI_SERIAL=$(cat /proc/cpuinfo | grep Serial | cut -d ' ' -f 2)
    PI_IP=$(hostname -I | awk '{print $1}')
    
    log "Installation complete!"
    log "Raspberry Pi Model: $PI_MODEL"
    log "Serial Number: $PI_SERIAL"
    log "IP Address: $PI_IP"
    log "API Key: $API_KEY"
    log "Web Interface: http://$PI_IP"
    log "Configuration: $CONFIG_DIR/config.json"
    log "Logs: $LOG_DIR/agent.log"
}

start_services() {
    log "Starting services..."
    systemctl start mosquitto
    systemctl start nginx
    systemctl start $SERVICE_NAME
    
    # Check service status
    sleep 5
    if systemctl is-active --quiet $SERVICE_NAME; then
        log "Service started successfully"
    else
        error "Service failed to start. Check logs: journalctl -u $SERVICE_NAME"
    fi
}

cleanup() {
    log "Cleaning up..."
    apt-get autoremove -y
    apt-get autoclean
}

main() {
    log "Starting Raspberry Pi Agent installation..."
    
    check_root
    detect_pi
    update_system
    install_dependencies
    create_user
    create_directories
    install_python_deps
    copy_files
    configure_gpio
    create_systemd_service
    configure_nginx
    configure_mosquitto
    setup_logrotate
    create_default_config
    post_install_setup
    start_services
    cleanup
    
    log "Installation completed successfully!"
    log "The system may need to be rebooted to enable all GPIO features."
    log "Run 'sudo systemctl status $SERVICE_NAME' to check service status."
}

# Handle script arguments
case "${1:-install}" in
    install)
        main
        ;;
    uninstall)
        log "Uninstalling Raspberry Pi Agent..."
        systemctl stop $SERVICE_NAME 2>/dev/null || true
        systemctl disable $SERVICE_NAME 2>/dev/null || true
        rm -f /etc/systemd/system/$SERVICE_NAME.service
        rm -rf "$INSTALL_DIR"
        rm -rf "$CONFIG_DIR"
        rm -rf "$LOG_DIR"
        rm -f /etc/nginx/sites-available/raspberry-pi-agent
        rm -f /etc/nginx/sites-enabled/raspberry-pi-agent
        rm -f /etc/logrotate.d/raspberry-pi-agent
        userdel "$SERVICE_USER" 2>/dev/null || true
        systemctl daemon-reload
        log "Uninstallation complete"
        ;;
    *)
        echo "Usage: $0 [install|uninstall]"
        exit 1
        ;;
esac