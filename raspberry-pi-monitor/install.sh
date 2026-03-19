#!/bin/bash

# Raspberry Pi Energy Monitor Installation Script
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
INSTALL_DIR="/opt/raspberry-pi-monitor"
SERVICE_USER="pi-monitor"
SERVICE_NAME="raspberry-pi-monitor"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

log() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

error() {
    echo -e "${RED}[ERROR]${NC} $1"
    exit 1
}

# Check if running as root
if [[ $EUID -ne 0 ]]; then
    error "This script must be run as root (use sudo)"
fi

log "Starting Raspberry Pi Energy Monitor installation..."

# Update package list
log "Updating package list..."
apt-get update

# Install required system packages
log "Installing system dependencies..."
apt-get install -y \
    python3 \
    python3-pip \
    python3-venv \
    git \
    curl \
    sqlite3 \
    nginx \
    supervisor \
    i2c-tools \
    python3-smbus \
    python3-dev \
    build-essential \
    libffi-dev \
    libssl-dev

# Enable I2C and SPI
log "Enabling I2C and SPI interfaces..."
raspi-config nonint do_i2c 0
raspi-config nonint do_spi 0

# Create service user
log "Creating service user: $SERVICE_USER"
if ! id "$SERVICE_USER" &>/dev/null; then
    useradd -r -s /bin/false -d "$INSTALL_DIR" "$SERVICE_USER"
else
    log "User $SERVICE_USER already exists"
fi

# Create installation directory
log "Creating installation directory: $INSTALL_DIR"
mkdir -p "$INSTALL_DIR"
mkdir -p "$INSTALL_DIR/logs"
mkdir -p "$INSTALL_DIR/data"
mkdir -p "/var/log/$SERVICE_NAME"

# Copy application files
log "Copying application files..."
cp -r "$SCRIPT_DIR"/* "$INSTALL_DIR/"
chmod +x "$INSTALL_DIR/src/main.py"

# Create Python virtual environment
log "Creating Python virtual environment..."
python3 -m venv "$INSTALL_DIR/venv"
source "$INSTALL_DIR/venv/bin/activate"

# Upgrade pip
pip install --upgrade pip

# Install Python dependencies
log "Installing Python dependencies..."
pip install -r "$INSTALL_DIR/requirements.txt"

deactivate

# Set up configuration
log "Setting up configuration..."
if [[ ! -f "$INSTALL_DIR/config/config.yaml" ]]; then
    cp "$INSTALL_DIR/config/config.example.yaml" "$INSTALL_DIR/config/config.yaml"
    log "Created config.yaml from example. Please edit it as needed."
fi

# Set permissions
log "Setting file permissions..."
chown -R "$SERVICE_USER:$SERVICE_USER" "$INSTALL_DIR"
chown -R "$SERVICE_USER:$SERVICE_USER" "/var/log/$SERVICE_NAME"
chmod 755 "$INSTALL_DIR"
chmod 644 "$INSTALL_DIR/config/config.yaml"
chmod +x "$INSTALL_DIR/src/main.py"

# Add service user to required groups
usermod -a -G i2c,spi,gpio "$SERVICE_USER"

# Create systemd service file
log "Creating systemd service..."
cat > "/etc/systemd/system/$SERVICE_NAME.service" << EOF
[Unit]
Description=Raspberry Pi Energy Monitor
After=network.target
Wants=network-online.target

[Service]
Type=simple
User=$SERVICE_USER
Group=$SERVICE_USER
WorkingDirectory=$INSTALL_DIR
Environment=PATH=$INSTALL_DIR/venv/bin
ExecStart=$INSTALL_DIR/venv/bin/python $INSTALL_DIR/src/main.py
Restart=always
RestartSec=10
StandardOutput=journal
StandardError=journal
SyslogIdentifier=$SERVICE_NAME

# Security settings
NoNewPrivileges=true
PrivateTmp=true
ProtectHome=true
ProtectSystem=strict
ReadWritePaths=$INSTALL_DIR/data $INSTALL_DIR/logs /var/log/$SERVICE_NAME

[Install]
WantedBy=multi-user.target
EOF

# Create nginx configuration
log "Setting up nginx configuration..."
cat > "/etc/nginx/sites-available/$SERVICE_NAME" << EOF
server {
    listen 80;
    server_name _;
    
    location / {
        proxy_pass http://localhost:5000;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
    }
    
    location /static {
        alias $INSTALL_DIR/web/static;
        expires 1d;
        add_header Cache-Control "public, immutable";
    }
    
    location /api {
        proxy_pass http://localhost:5000;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
    }
}
EOF

# Enable nginx site
ln -sf "/etc/nginx/sites-available/$SERVICE_NAME" "/etc/nginx/sites-enabled/"
rm -f "/etc/nginx/sites-enabled/default"

# Test nginx configuration
nginx -t

# Create log rotation configuration
log "Setting up log rotation..."
cat > "/etc/logrotate.d/$SERVICE_NAME" << EOF
/var/log/$SERVICE_NAME/*.log {
    daily
    missingok
    rotate 7
    compress
    delaycompress
    notifempty
    create 0644 $SERVICE_USER $SERVICE_USER
    postrotate
        systemctl reload $SERVICE_NAME
    endscript
}
EOF

# Create backup script
log "Creating backup script..."
cat > "$INSTALL_DIR/backup.sh" << 'EOF'
#!/bin/bash
BACKUP_DIR="/home/pi/backups"
DATE=$(date +%Y%m%d_%H%M%S)
mkdir -p "$BACKUP_DIR"

# Backup database
sqlite3 /opt/raspberry-pi-monitor/data/energy.db ".backup '$BACKUP_DIR/energy_$DATE.db'"

# Backup configuration
cp /opt/raspberry-pi-monitor/config/config.yaml "$BACKUP_DIR/config_$DATE.yaml"

# Keep only last 7 backups
find "$BACKUP_DIR" -name "energy_*.db" -type f -mtime +7 -delete
find "$BACKUP_DIR" -name "config_*.yaml" -type f -mtime +7 -delete

echo "Backup completed: $DATE"
EOF

chmod +x "$INSTALL_DIR/backup.sh"

# Create daily backup cron job
log "Setting up daily backup..."
cat > "/etc/cron.d/$SERVICE_NAME-backup" << EOF
0 2 * * * $SERVICE_USER $INSTALL_DIR/backup.sh >> /var/log/$SERVICE_NAME/backup.log 2>&1
EOF

# Initialize database
log "Initializing database..."
sudo -u "$SERVICE_USER" "$INSTALL_DIR/venv/bin/python" -c "
import sys
sys.path.append('$INSTALL_DIR/src')
from database import Database
db = Database('$INSTALL_DIR/data/energy.db')
db.init_database()
print('Database initialized successfully')
"

# Reload systemd and enable services
log "Enabling and starting services..."
systemctl daemon-reload
systemctl enable "$SERVICE_NAME"
systemctl enable nginx

# Start services
systemctl restart nginx
systemctl start "$SERVICE_NAME"

# Wait a moment and check service status
sleep 2
if systemctl is-active --quiet "$SERVICE_NAME"; then
    log "Service started successfully"
else
    warn "Service may have issues starting. Check logs with: journalctl -u $SERVICE_NAME"
fi

# Display installation summary
log "Installation completed successfully!"
echo
echo -e "${BLUE}=== Installation Summary ===${NC}"
echo -e "Service Name: ${GREEN}$SERVICE_NAME${NC}"
echo -e "Installation Directory: ${GREEN}$INSTALL_DIR${NC}"
echo -e "Service User: ${GREEN}$SERVICE_USER${NC}"
echo -e "Web Interface: ${GREEN}http://$(hostname -I | awk '{print $1}')${NC}"
echo -e "Configuration: ${GREEN}$INSTALL_DIR/config/config.yaml${NC}"
echo -e "Logs: ${GREEN}/var/log/$SERVICE_NAME/${NC}"
echo
echo -e "${YELLOW}Next Steps:${NC}"
echo "1. Edit the configuration file: sudo nano $INSTALL_DIR/config/config.yaml"
echo "2. Configure your sensors in the config file"
echo "3. Restart the service: sudo systemctl restart $SERVICE_NAME"
echo "4. Check service status: sudo systemctl status $SERVICE_NAME"
echo "5. View logs: sudo journalctl -u $SERVICE_NAME -f"
echo
echo -e "${GREEN}Installation complete! The energy monitor is ready to use.${NC}"