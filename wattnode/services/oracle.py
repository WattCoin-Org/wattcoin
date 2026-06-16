#!/usr/bin/env python3
"""
WattNode Sensor Oracle — reads real-world sensor data (temperature, humidity, motion)
and reports it to the WattCoin API as verifiable data.

Supports:
- DHT22 (temperature + humidity)
- PIR (motion)
- Mock sensors for development/testing
- Configurable reporting interval
- Local SQLite logging & history
- Ed25519 signature using wallet private key
"""

import argparse
import json
import logging
import os
import sqlite3
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import requests
import yaml

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ed25519
from cryptography.hazmat.backends import default_backend

# Optional GPIO / sensor libraries – silently fall back to mock if unavailable
try:
    import board
    import adafruit_dht
    DHT_AVAILABLE = True
except ImportError:
    DHT_AVAILABLE = False

try:
    import RPi.GPIO as GPIO
    PIR_AVAILABLE = True
except ImportError:
    PIR_AVAILABLE = False

logger = logging.getLogger(__name__)


class SensorOracle:
    def __init__(self, config_path: str = None):
        self.config = self._load_config(config_path or self._default_config_path())
        self.db_path = Path(self.config.get('oracle', {}).get('db_path', 'data/oracle_history.db'))
        self._init_db()
        self._sensor_initialized = False

    # -----------------------------------------------------------------------
    # Configuration
    # -----------------------------------------------------------------------
    def _default_config_path(self):
        return Path(__file__).resolve().parent.parent / 'config.yaml'

    def _load_config(self, path):
        with open(path) as f:
            return yaml.safe_load(f)

    # -----------------------------------------------------------------------
    # Database
    # -----------------------------------------------------------------------
    def _init_db(self):
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(self.db_path))
        conn.execute('''
            CREATE TABLE IF NOT EXISTS readings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                sensor_type TEXT NOT NULL,
                value TEXT NOT NULL,
                timestamp TEXT NOT NULL,
                signature TEXT,
                reported INTEGER DEFAULT 0
            )
        ''')
        conn.commit()
        conn.close()

    def _log_local(self, sensor_type, value, signature):
        conn = sqlite3.connect(str(self.db_path))
        conn.execute(
            'INSERT INTO readings (sensor_type, value, timestamp, signature) VALUES (?, ?, ?, ?)',
            (sensor_type, json.dumps(value), datetime.now(timezone.utc).isoformat(), signature)
        )
        conn.commit()
        conn.close()

    def get_history(self, limit=100):
        conn = sqlite3.connect(str(self.db_path))
        rows = conn.execute(
            'SELECT * FROM readings ORDER BY id DESC LIMIT ?', (limit,)
        ).fetchall()
        conn.close()
        return rows

    # -----------------------------------------------------------------------
    # Sensor Reading
    # -----------------------------------------------------------------------
    def _init_sensors(self):
        oracle_cfg = self.config.get('oracle', {})
        self.mock = oracle_cfg.get('mock', False)
        self.interval = oracle_cfg.get('interval', 60)
        self.sensors = oracle_cfg.get('sensors', [])

        # Initialize DHT22 if configured
        self.dht_device = None
        if not self.mock and DHT_AVAILABLE:
            dht_pin = oracle_cfg.get('dht_pin', 'D4')
            try:
                pin = getattr(board, dht_pin.upper())
                self.dht_device = adafruit_dht.DHT22(pin, use_pulseio=False)
                logger.info('DHT22 sensor initialized on pin %s', dht_pin)
            except Exception as e:
                logger.warning('Failed to init DHT22 on pin %s: %s', dht_pin, e)
                self.dht_device = None

        # Initialize PIR if configured
        self.pir_pin = oracle_cfg.get('pir_pin', 17)
        self.pir_initialized = False
        if not self.mock and PIR_AVAILABLE and 'pir' in self.sensors:
            try:
                GPIO.setmode(GPIO.BCM)
                GPIO.setup(self.pir_pin, GPIO.IN)
                self.pir_initialized = True
                logger.info('PIR sensor initialized on pin %d', self.pir_pin)
            except Exception as e:
                logger.warning('Failed to init PIR: %s', e)

        self._sensor_initialized = True

    def _read_dht22(self):
        if self.mock:
            import random
            return {
                'temperature': round(random.uniform(20.0, 30.0), 1),
                'humidity': round(random.uniform(40.0, 70.0), 1)
            }
        if self.dht_device is None:
            return None
        try:
            temp = self.dht_device.temperature
            humidity = self.dht_device.humidity
            if temp is not None and humidity is not None:
                return {'temperature': round(temp, 1), 'humidity': round(humidity, 1)}
        except RuntimeError as e:
            logger.warning('DHT22 read error: %s', e)
        return None

    def _read_pir(self):
        if self.mock:
            import random
            return {'motion': random.choice([True, False])}
        if not self.pir_initialized:
            return None
        try:
            motion = GPIO.input(self.pir_pin)
            return {'motion': bool(motion)}
        except Exception as e:
            logger.warning('PIR read error: %s', e)
        return None

    def read_all_sensors(self):
        if not self._sensor_initialized:
            self._init_sensors()

        readings = {}
        for sensor in self.sensors:
            if sensor == 'dht22':
                val = self._read_dht22()
                if val:
                    readings['dht22'] = val
            elif sensor == 'pir':
                val = self._read_pir()
                if val:
                    readings['pir'] = val
            else:
                logger.warning('Unknown sensor type: %s', sensor)
        return readings

    # -----------------------------------------------------------------------
    # Signing
    # -----------------------------------------------------------------------
    def _get_private_key(self):
        """Decode Ed25519 private key from config or environment variable."""
        key_hex = self.config.get('wallet_private_key') or os.environ.get('WATT_PRIVATE_KEY')
        if not key_hex:
            logger.warning('No wallet private key configured – signing disabled')
            return None
        try:
            raw = bytes.fromhex(key_hex)
            return ed25519.Ed25519PrivateKey.from_private_bytes(raw)
        except Exception as e:
            logger.error('Failed to load private key: %s', e)
            return None

    def sign_data(self, data: dict) -> str:
        """Sign data dictionary and return base64 signature."""
        private_key = self._get_private_key()
        if private_key is None:
            # Mock signature for development
            import hashlib
            import base64
            payload = json.dumps(data, sort_keys=True).encode()
            mock_sig = hashlib.sha256(payload).hexdigest()
            return base64.b64encode(mock_sig.encode()).decode()

        payload = json.dumps(data, sort_keys=True).encode()
        signature = private_key.sign(payload)
        import base64
        return base64.b64encode(signature).decode()

    # -----------------------------------------------------------------------
    # Reporting
    # -----------------------------------------------------------------------
    def report(self, readings: dict):
        """Report sensor readings to the configured API endpoint."""
        if not readings:
            logger.info('No sensor readings to report.')
            return

        endpoint = self.config.get('oracle', {}).get(
            'api_endpoint',
            'https://your-backend-url.example.com/api/v1/oracle/report'
        )
        wallet = self.config.get('wallet', 'Unknown')

        payload = {
            'wallet': wallet,
            'readings': readings,
            'timestamp': datetime.now(timezone.utc).isoformat(),
        }
        signature = self.sign_data(payload)
        payload['signature'] = signature

        # Log locally first
        for sensor_type, value in readings.items():
            self._log_local(sensor_type, value, signature)

        # Send to API
        try:
            resp = requests.post(endpoint, json=payload, timeout=10)
            resp.raise_for_status()
            logger.info('Reported %d sensor(s) to %s (status %d)', len(readings), endpoint, resp.status_code)
        except requests.RequestException as e:
            logger.error('Failed to report sensor data: %s', e)

    # -----------------------------------------------------------------------
    # Main loop
    # -----------------------------------------------------------------------
    def run(self):
        """Start the sensor oracle main loop."""
        self._init_sensors()
        logger.info('Sensor oracle started (interval=%ds, mock=%s)', self.interval, self.mock)

        while True:
            try:
                readings = self.read_all_sensors()
                if readings:
                    self.report(readings)
                else:
                    logger.debug('No readings available this cycle.')
                time.sleep(self.interval)
            except KeyboardInterrupt:
                logger.info('Sensor oracle stopped by user.')
                break
            except Exception as e:
                logger.error('Unexpected error in sensor loop: %s', e)
                time.sleep(self.interval)

        self.cleanup()

    def cleanup(self):
        """Clean up GPIO resources."""
        if self.pir_initialized:
            try:
                GPIO.cleanup()
            except Exception:
                pass
        if self.dht_device:
            try:
                self.dht_device.exit()
            except Exception:
                pass


# ---------------------------------------------------------------------------
# CLI Entry Point
# ---------------------------------------------------------------------------
def main():
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s [%(levelname)s] %(name)s: %(message)s'
    )

    parser = argparse.ArgumentParser(description='WattNode Sensor Oracle')
    parser.add_argument('--config', default=None, help='Path to config.yaml')
    parser.add_argument('--mock', action='store_true', help='Force mock sensors')
    parser.add_argument('--interval', type=int, default=None, help='Reporting interval in seconds')
    parser.add_argument('--once', action='store_true', help='Read sensors once and exit')
    args = parser.parse_args()

    oracle = SensorOracle(config_path=args.config)
    if args.mock:
        oracle.config.setdefault('oracle', {})['mock'] = True
    if args.interval:
        oracle.config.setdefault('oracle', {})['interval'] = args.interval

    if args.once:
        readings = oracle.read_all_sensors()
        if readings:
            oracle.report(readings)
        else:
            print('No sensor readings.')
    else:
        oracle.run()


if __name__ == '__main__':
    main()
