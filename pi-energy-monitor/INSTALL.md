# Pi Energy Monitor - Installation Guide

Raspberry Pi application that monitors power consumption and reports data to the WattCoin API.

## Hardware Compatibility

| Device | Status | Notes |
|--------|--------|-------|
| Mock Mode | ✅ Tested | Built-in for development/testing |
| TP-Link Kasa | ⚡ Supported | Requires network access |
| Shelly Plug | ⚡ Supported | Requires network access |
| USB Power Meter | ⚡ Supported | FNIRSI, USB Wattman, etc. |

## Quick Start

### 1. Clone and Install

```bash
# Clone the repository
git clone https://github.com/WattCoin-Org/wattcoin.git
cd wattcoin/pi-energy-monitor

# Create virtual environment (recommended)
python3 -m venv venv
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt
```

### 2. Configure

```bash
# Copy example config
cp config.yaml.example config.yaml

# Edit config with your settings
nano config.yaml
```

Required settings in `config.yaml`:
- `wallet_address`: Your Solana wallet address
- `hardware.device_type`: One of `mock`, `kasa`, `shelly`, `usb_power_meter`

### 3. Test

```bash
# Test with mock hardware (no hardware needed)
python pi_energy_monitor.py --mock

# Or test your hardware configuration
python pi_energy_monitor.py --test-hardware

# Test API connection (will fail gracefully if API not running)
python pi_energy_monitor.py --test-api
```

### 4. Run

```bash
# Run in foreground (for testing)
python pi_energy_monitor.py --config config.yaml

# Or run in background
nohup python pi_energy_monitor.py --config config.yaml &

# Check status
python pi_energy_monitor.py --status
```

## Hardware Setup

### TP-Link Kasa Smart Plug

1. Connect Kasa plug to power
2. Add device to your WiFi network via Kasa app
3. Note the IP address
4. Update config:
   ```yaml
   hardware:
     device_type: "kasa"
     kasa:
       host: "192.168.1.100"  # Your Kasa's IP
       port: 9999
   ```

### Shelly Plug

1. Connect Shelly plug to power
2. Add device to your WiFi network via Shelly app
3. Note the IP address
4. Update config:
   ```yaml
   hardware:
     device_type: "shelly"
     shelly:
       host: "192.168.1.101"  # Your Shelly's IP
   ```

### USB Power Meter (FNIRSI, USB Wattman, etc.)

1. Connect USB power meter to Pi's USB port
2. Note the device path (usually `/dev/ttyUSB0` or `/dev/ttyACM0`)
3. Update config:
   ```yaml
   hardware:
     device_type: "usb_power_meter"
     usb_power_meter:
       device: "/dev/ttyUSB0"
       baudrate: 115200
   ```

## Systemd Service (Recommended)

For auto-start on boot:

```bash
# Copy service file
sudo cp pi-energy-monitor.service /etc/systemd/system/

# Edit service file to verify paths
sudo nano /etc/systemd/system/pi-energy-monitor.service

# Reload systemd
sudo systemctl daemon-reload

# Enable service
sudo systemctl enable pi-energy-monitor

# Start service
sudo systemctl start pi-energy-monitor

# Check status
sudo systemctl status pi-energy-monitor

# View logs
journalctl -u pi-energy-monitor -f
```

## Configuration Options

### Polling

```yaml
polling:
  interval_seconds: 60      # How often to read power (seconds)
  samples_per_reading: 5    # Number of samples to average
  sample_delay: 0.5         # Delay between samples
```

### API

```yaml
api:
  base_url: "https://your-backend-url.example.com"
  endpoint: "/api/v1/energy/report"
  timeout: 30
  max_retries: 3
```

### Local Logging

```yaml
logging:
  database_path: "energy_data.db"      # SQLite database
  json_log: true
  json_log_path: "energy_readings.json"
  retention_days: 90
```

## Environment Variables

Override config with environment variables:

```bash
export WATT_WALLET="YourSolanaWallet..."
export WATTCOIN_API_URL="https://api.example.com"
export WATT_HARDWARE="mock"
export KASA_HOST="192.168.1.100"
export SHELLY_HOST="192.168.1.101"
```

## API Report Format

Reports are sent as JSON:

```json
{
  "timestamp": "2024-01-15T10:30:00Z",
  "wallet": "YourSolanaWallet...",
  "watts": 125.5,
  "device_type": "mock",
  "client_version": "1.0.0",
  "signature": "abc123..."
}
```

The backend should:
- Accept POST requests at `/api/v1/energy/report`
- Return `{"success": true}` on success
- Handle connection errors gracefully (the client will retry)

## Troubleshooting

### "No such device" error with USB meter
```bash
# Check available serial devices
ls -la /dev/ttyUSB*
ls -la /dev/ttyACM*

# Add user to dialout group
sudo usermod -a -G dialout pi
```

### Kasa/Shelly not responding
- Ensure device is on same network as Pi
- Check IP address is correct
- Verify firewall allows local network access

### API connection failures
- Check base_url in config
- Verify network connectivity
- The monitor will retry automatically

## Uninstall

```bash
# If running as service
sudo systemctl stop pi-energy-monitor
sudo systemctl disable pi-energy-monitor
sudo rm /etc/systemd/system/pi-energy-monitor.service

# Remove files
cd ..
rm -rf pi-energy-monitor
```

## Development

### Running Tests

```bash
# Install test dependencies
pip install pytest pytest-cov

# Run tests
pytest test_energy_monitor.py -v

# With coverage
pytest test_energy_monitor.py --cov=. --cov-report=html
```

### Mock Mode

Use mock mode for testing without hardware:

```bash
# Command line
python pi_energy_monitor.py --mock

# Or set in config
hardware:
  device_type: "mock"
  mock:
    base_watts: 150.0
    variance: 10.0
```

---

**Hardware Tested:** Mock mode fully tested. Kasa and Shelly supported but not physically tested (no devices available).

**Note:** The backend API endpoint (`/api/v1/energy/report`) is not yet deployed. The script is designed to work with any compatible API and will gracefully retry on connection failures.
