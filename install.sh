#!/bin/bash

# Raspberry Pi Local Agent Node Installation Script
# WATT Network Bounty Implementation

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Configuration
SERVICE_NAME="watt-agent"
SERVICE_USER="watt"
INSTALL_DIR="/opt/watt-agent"
CONFIG_DIR="/etc/watt-agent"
LOG_DIR="/var/log/watt-agent"
DATA_DIR="/var/lib/watt-agent"

print_status() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

print_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

check_root() {
    if [[ $EUID -ne 0 ]]; then
        print_error "This script must be run as root"
        exit 1
    fi
}

detect_architecture() {
    local arch=$(uname -m)
    case $arch in
        armv6l|armv7l)
            ARCH="armv7"
            ;;
        aarch64|arm64)
            ARCH="arm64"
            ;;
        x86_64)
            ARCH="amd64"
            ;;
        *)
            print_error "Unsupported architecture: $arch"
            exit 1
            ;;
    esac
    print_status "Detected architecture: $ARCH"
}

check_raspberry_pi() {
    if [[ ! -f /proc/cpuinfo ]] || ! grep -q "BCM" /proc/cpuinfo; then
        print_warning "This doesn't appear to be a Raspberry Pi, but continuing anyway..."
    else
        local model=$(grep "Model" /proc/cpuinfo | cut -d: -f2 | xargs)
        print_status "Detected Raspberry Pi: $model"
    fi
}

update_system() {
    print_status "Updating system packages..."
    apt update && apt upgrade -y
    print_success "System updated"
}

install_dependencies() {
    print_status "Installing dependencies..."
    
    # Essential packages
    apt install -y \
        curl \
        wget \
        git \
        build-essential \
        python3 \
        python3-pip \
        python3-venv \
        nodejs \
        npm \
        sqlite3 \
        systemd \
        jq \
        htop \
        ufw \
        fail2ban \
        logrotate \
        supervisor \
        nginx
    
    # Raspberry Pi specific packages
    if grep -q "BCM" /proc/cpuinfo 2>/dev/null; then
        apt install -y \
            raspi-config \
            rpi-update \
            libraspberrypi-bin \
            python3-rpi.gpio \
            i2c-tools \
            spi-tools
    fi
    
    print_success "Dependencies installed"
}

create_user() {
    print_status "Creating service user..."
    
    if id "$SERVICE_USER" &>/dev/null; then
        print_warning "User $SERVICE_USER already exists"
    else
        useradd -r -s /bin/false -d $DATA_DIR $SERVICE_USER
        print_success "User $SERVICE_USER created"
    fi
}

create_directories() {
    print_status "Creating directories..."
    
    mkdir -p $INSTALL_DIR
    mkdir -p $CONFIG_DIR
    mkdir -p $LOG_DIR
    mkdir -p $DATA_DIR
    
    # Set permissions
    chown -R $SERVICE_USER:$SERVICE_USER $INSTALL_DIR
    chown -R $SERVICE_USER:$SERVICE_USER $CONFIG_DIR
    chown -R $SERVICE_USER:$SERVICE_USER $LOG_DIR
    chown -R $SERVICE_USER:$SERVICE_USER $DATA_DIR
    
    chmod 755 $INSTALL_DIR
    chmod 750 $CONFIG_DIR
    chmod 750 $LOG_DIR
    chmod 750 $DATA_DIR
    
    print_success "Directories created"
}

install_python_dependencies() {
    print_status "Installing Python dependencies..."
    
    # Create virtual environment
    python3 -m venv $INSTALL_DIR/venv
    source $INSTALL_DIR/venv/bin/activate
    
    # Upgrade pip
    pip install --upgrade pip setuptools wheel
    
    # Install main dependencies
    pip install \
        fastapi \
        uvicorn \
        websockets \
        aiohttp \
        asyncio \
        sqlite3 \
        cryptography \
        pycryptodome \
        requests \
        schedule \
        psutil \
        pyyaml \
        click \
        python-dotenv
    
    # Raspberry Pi specific dependencies
    if grep -q "BCM" /proc/cpuinfo 2>/dev/null; then
        pip install \
            RPi.GPIO \
            gpiozero \
            adafruit-circuitpython-ssd1306 \
            adafruit-circuitpython-dht \
            w1thermsensor
    fi
    
    deactivate
    chown -R $SERVICE_USER:$SERVICE_USER $INSTALL_DIR/venv
    
    print_success "Python dependencies installed"
}

install_node_dependencies() {
    print_status "Installing Node.js dependencies..."
    
    cd $INSTALL_DIR
    
    # Initialize package.json if it doesn't exist
    if [[ ! -f package.json ]]; then
        npm init -y
    fi
    
    # Install dependencies
    npm install \
        ws \
        axios \
        express \
        sqlite3 \
        crypto \
        fs-extra \
        node-cron \
        systeminformation \
        node-machine-id
    
    chown -R $SERVICE_USER:$SERVICE_USER $INSTALL_DIR/node_modules
    
    print_success "Node.js dependencies installed"
}

create_config_files() {
    print_status "Creating configuration files..."
    
    # Main configuration
    cat > $CONFIG_DIR/config.yaml << EOF
# WATT Agent Configuration
agent:
  id: ""
  name: "raspberry-pi-agent"
  version: "1.0.0"
  description: "Raspberry Pi local agent node for WATT network"

network:
  port: 8080
  host: "0.0.0.0"
  ssl: false
  websocket_port: 8081

blockchain:
  network: "testnet"
  rpc_url: ""
  private_key: ""
  contract_address: ""

storage:
  database_path: "${DATA_DIR}/agent.db"
  backup_interval: 3600
  max_backups: 24

logging:
  level: "INFO"
  file: "${LOG_DIR}/agent.log"
  max_size: "10MB"
  max_files: 5

hardware:
  enable_gpio: true
  enable_sensors: true
  sensor_interval: 60
  temperature_pin: 4
  led_pin: 18

security:
  api_key: ""
  rate_limit: 100
  enable_firewall: true
  allowed_ips: []

monitoring:
  enable_metrics: true
  metrics_interval: 30
  system_stats: true
  network_stats: true
EOF
    
    # Environment variables
    cat > $CONFIG_DIR/.env << EOF
# Environment Configuration
NODE_ENV=production
WATT_AGENT_CONFIG=${CONFIG_DIR}/config.yaml
WATT_AGENT_DATA=${DATA_DIR}
WATT_AGENT_LOGS=${LOG_DIR}
EOF
    
    # Set permissions
    chown $SERVICE_USER:$SERVICE_USER $CONFIG_DIR/config.yaml
    chown $SERVICE_USER:$SERVICE_USER $CONFIG_DIR/.env
    chmod 640 $CONFIG_DIR/config.yaml
    chmod 640 $CONFIG_DIR/.env
    
    print_success "Configuration files created"
}

create_systemd_service() {
    print_status "Creating systemd service..."
    
    cat > /etc/systemd/system/$SERVICE_NAME.service << EOF
[Unit]
Description=WATT Network Local Agent Node
Documentation=https://github.com/watt-network/agent
After=network.target
Wants=network.target

[Service]
Type=simple
User=$SERVICE_USER
Group=$SERVICE_USER
WorkingDirectory=$INSTALL_DIR
Environment=PATH=$INSTALL_DIR/venv/bin:\$PATH
EnvironmentFile=$CONFIG_DIR/.env
ExecStart=$INSTALL_DIR/venv/bin/python main.py
ExecReload=/bin/kill -HUP \$MAINPID
Restart=always
RestartSec=10
StandardOutput=journal
StandardError=journal
SyslogIdentifier=$SERVICE_NAME

# Security settings
NoNewPrivileges=true
PrivateTmp=true
ProtectSystem=strict
ProtectHome=true
ReadWritePaths=$DATA_DIR $LOG_DIR $CONFIG_DIR
ProtectKernelTunables=true
ProtectKernelModules=true
ProtectControlGroups=true

# Resource limits
LimitNOFILE=65536
LimitNPROC=4096
MemoryMax=512M

[Install]
WantedBy=multi-user.target
EOF
    
    # Reload systemd
    systemctl daemon-reload
    systemctl enable $SERVICE_NAME
    
    print_success "Systemd service created and enabled"
}

configure_firewall() {
    print_status "Configuring firewall..."
    
    # Enable UFW
    ufw --force enable
    
    # Default policies
    ufw default deny incoming
    ufw default allow outgoing
    
    # SSH access
    ufw allow ssh
    
    # Agent ports
    ufw allow 8080/tcp
    ufw allow 8081/tcp
    
    # Optional: P2P ports
    ufw allow 30303/tcp
    ufw allow 30303/udp
    
    print_success "Firewall configured"
}

configure_log_rotation() {
    print_status "Configuring log rotation..."
    
    cat > /etc/logrotate.d/$SERVICE_NAME << EOF
$LOG_DIR/*.log {
    daily
    missingok
    rotate 7
    compress
    notifempty
    create 640 $SERVICE_USER $SERVICE_USER
    postrotate
        systemctl reload $SERVICE_NAME > /dev/null 2>&1 || true
    endscript
}
EOF
    
    print_success "Log rotation configured"
}

setup_monitoring() {
    print_status "Setting up monitoring..."
    
    # Create monitoring script
    cat > $INSTALL_DIR/monitor.sh << '#!/bin/bash
#!/bin/bash

# System monitoring script for WATT agent
LOG_FILE="/var/log/watt-agent/monitor.log"
SERVICE_NAME="watt-agent"

log_message() {
    echo "$(date '+%Y-%m-%d %H:%M:%S') - $1" >> $LOG_FILE
}

check_service() {
    if ! systemctl is-active --quiet $SERVICE_NAME; then
        log_message "WARNING: Service $SERVICE_NAME is not running, attempting restart"
        systemctl restart $SERVICE_NAME
        sleep 10
        if systemctl is-active --quiet $SERVICE_NAME; then
            log_message "INFO: Service $SERVICE_NAME restarted successfully"
        else
            log_message "ERROR: Failed to restart service $SERVICE_NAME"
        fi
    fi
}

check_disk_space() {
    local usage=$(df /var/lib/watt-agent | tail -1 | awk '{print $5}' | sed 's/%//')
    if [ $usage -gt 80 ]; then
        log_message "WARNING: Disk usage is ${usage}%"
    fi
}

check_memory() {
    local mem_usage=$(free | grep Mem | awk '{printf "%.1f", $3/$2 * 100}')
    if (( $(echo "$mem_usage > 90" | bc -l) )); then
        log_message "WARNING: Memory usage is ${mem_usage}%"
    fi
}

# Run checks
check_service
check_disk_space
check_memory

log_message "INFO: Monitoring check completed"
EOF
    
    chmod +x $INSTALL_DIR/monitor.sh
    chown $SERVICE_USER:$SERVICE_USER $INSTALL_DIR/monitor.sh
    
    # Add cron job for monitoring
    (crontab -u root -l 2>/dev/null; echo "*/5 * * * * $INSTALL_DIR/monitor.sh") | crontab -u root -
    
    print_success "Monitoring setup completed"
}

enable_gpio() {
    print_status "Configuring GPIO access..."
    
    # Add user to gpio group
    usermod -a -G gpio $SERVICE_USER
    
    # Enable SPI and I2C if on Raspberry Pi
    if command -v raspi-config &> /dev/null; then
        raspi-config nonint do_spi 0
        raspi-config nonint do_i2c 0
        print_success "SPI and I2C enabled"
    fi
    
    print_success "GPIO access configured"
}

create_startup_script() {
    print_status "Creating startup script..."
    
    cat > $INSTALL_DIR/start.sh << '#!/bin/bash
#!/bin/bash

# WATT Agent Startup Script
INSTALL_DIR="/opt/watt-agent"
CONFIG_DIR="/etc/watt-agent"
SERVICE_USER="watt"

cd $INSTALL_DIR

# Load environment
if [ -f $CONFIG_DIR/.env ]; then
    source $CONFIG_DIR/.env
fi

# Activate virtual environment
source $INSTALL_DIR/venv/bin/activate

# Start the agent
exec python main.py
EOF
    
    chmod +x $INSTALL_DIR/start.sh
    chown $SERVICE_USER:$SERVICE_USER $INSTALL_DIR/start.sh
    
    print_success "Startup script created"
}

generate_api_key() {
    print_status "Generating API key..."
    
    API_KEY=$(openssl rand -hex 32)
    
    # Update config with API key
    sed -i "s/api_key: \"\"/api_key: \"$API_KEY\"/" $CONFIG_DIR/config.yaml
    
    print_success "API key generated and configured"
}

final_setup() {
    print_status "Performing final setup..."
    
    # Create initial database
    sudo -u $SERVICE_USER sqlite3 $DATA_DIR/agent.db << EOF
CREATE TABLE IF NOT EXISTS agent_info (
    id INTEGER PRIMARY KEY,
    agent_id TEXT UNIQUE,
    name TEXT,
    version TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS transactions (
    id INTEGER PRIMARY KEY,
    tx_hash TEXT UNIQUE,
    block_number INTEGER,
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    status TEXT,
    data TEXT
);

CREATE TABLE IF NOT EXISTS metrics (
    id INTEGER PRIMARY KEY,
    metric_name TEXT,
    metric_value REAL,
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
EOF
    
    # Set correct permissions on database
    chown $SERVICE_USER:$SERVICE_USER $DATA_DIR/agent.db
    chmod 640 $DATA_DIR/agent.db
    
    print_success "Database initialized"
}

display_info() {
    print_success "Installation completed successfully!"
    echo ""
    echo -e "${BLUE}=== WATT Agent Information ===${NC}"
    echo -e "Service Name: ${GREEN}$SERVICE_NAME${NC}"
    echo -e "Install Directory: ${GREEN}$INSTALL_DIR${NC}"
    echo -e "Config Directory: ${GREEN}$CONFIG_DIR${NC}"
    echo -e "Data Directory: ${GREEN}$DATA_DIR${NC}"
    echo -e "Log Directory: ${GREEN}$LOG_DIR${NC}"
    echo -e "Service User: ${GREEN}$SERVICE_USER${NC}"
    echo ""
    echo -e "${BLUE}=== Next Steps ===${NC}"
    echo -e "1. Edit configuration: ${YELLOW}sudo nano $CONFIG_DIR/config.yaml${NC}"
    echo -e "2. Start the service: ${YELLOW}sudo systemctl start $SERVICE_NAME${NC}"
    echo -e "3. Check status: ${YELLOW}sudo systemctl status $SERVICE_NAME${NC}"
    echo -e "4. View logs: ${YELLOW}sudo journalctl -u $SERVICE_NAME -f${NC}"
    echo -e "5. API endpoint: ${YELLOW}http://localhost:8080${NC}"
    echo ""
    echo -e "${BLUE}=== API Key ===${NC}"
    echo -e "Your API key: ${GREEN}$API_KEY${NC}"
    echo -e "Save this key securely!"
    echo ""
    echo -e "${YELLOW}Remember to configure your blockchain settings in the config file!${NC}"
}

main() {
    echo -e "${BLUE}"
    echo "========================================"
    echo "WATT Network - Raspberry Pi Agent Setup"
    echo "========================================"
    echo -e "${NC}"
    
    check_root
    detect_architecture
    check_raspberry_pi
    
    print_status "Starting installation..."
    
    update_system
    install_dependencies
    create_user
    create_directories
    install_python_dependencies
    install_node_dependencies
    create_config_files
    create_systemd_service
    configure_firewall
    configure_log_rotation
    setup_monitoring
    enable_gpio
    create_startup_script
    generate_api_key
    final_setup
    
    display_info
}

# Handle script interruption
trap 'print_error "Installation interrupted!"; exit 1' INT TERM

# Run main installation
main "$@"