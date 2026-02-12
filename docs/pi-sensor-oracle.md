# Raspberry Pi Sensor Oracle (Bounty #19 Scaffold)

This scaffold provides a minimal, mergeable implementation for:
- DHT22-style readings (temperature + humidity)
- PIR motion readings
- signed payload submission to `/api/v1/oracle/report`
- local history logging (`history.jsonl`)
- configurable reporting interval

## Quick start

```bash
cd pi/sensor_oracle
./install.sh
.venv/bin/python oracle.py --once
```

## Configuration

- `WATT_ORACLE_API_URL` (default `http://localhost:5000/api/v1/oracle/report`)
- `WATT_WALLET` (wallet id/address)
- `WATT_WALLET_SECRET` (dev signing secret)
- `WATT_ORACLE_HISTORY` (default `pi/sensor_oracle/history.jsonl`)
- `WATT_ORACLE_INTERVAL_SEC` (default `60`)
- `WATT_ORACLE_MOCK_FILE` (default `pi/sensor_oracle/mock_sensors.json`)

## Wiring diagrams (reference)

### DHT22 → Raspberry Pi (BCM)

- VCC → 3.3V (Pin 1)
- DATA → GPIO4 (Pin 7)
- GND → GND (Pin 6)
- 10k resistor between VCC and DATA

### PIR sensor → Raspberry Pi (BCM)

- VCC → 5V (Pin 2)
- OUT → GPIO17 (Pin 11)
- GND → GND (Pin 14)

## Service install (optional)

```bash
sudo cp pi/sensor_oracle/wattcoin-sensor-oracle.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now wattcoin-sensor-oracle
```

## Notes

- Current implementation uses mock sensor input to keep PR safe/testable.
- Replace `MockSensors` with real GPIO/I2C adapters in production.
