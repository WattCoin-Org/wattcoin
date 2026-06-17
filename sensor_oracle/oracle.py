#!/usr/bin/env python3
"""
WattCoin Sensor Oracle
Reads sensor data and reports to the WattCoin network.
"""
import os
import sys
import time
import json
import logging
import argparse
import shlex
import subprocess
from datetime import datetime
from typing import Dict, List, Optional

from sensors import SensorFactory
from signer import WalletSigner
from history import HistoryStore
from config import OracleConfig

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler('oracle.log')
    ]
)
logger = logging.getLogger(__name__)


class SensorOracle:
    """Main oracle that reads sensors and reports data."""
    
    def __init__(self, config: OracleConfig):
        self.config = config
        self.signer = WalletSigner(config.private_key)
        self.history = HistoryStore(config.history_file)
        self.sensors = []
        
        for sensor_type in config.sensor_types:
            try:
                sensor = SensorFactory.create(
                    sensor_type,
                    mock_mode=config.mock_mode
                )
                self.sensors.append(sensor)
                logger.info(f"Initialized {sensor_type} sensor (mock={config.mock_mode})")
            except Exception as e:
                logger.error(f"Failed to initialize {sensor_type}: {e}")
    
    def run(self):
        """Main loop: read sensors and report."""
        logger.info(f"Oracle started. Reporting every {self.config.interval}s to {self.config.api_url}")
        
        while True:
            try:
                readings = self._read_all_sensors()
                if readings:
                    self._report_readings(readings)
                else:
                    logger.warning("No readings available")
            except Exception as e:
                logger.error(f"Error in main loop: {e}")
            
            time.sleep(self.config.interval)
    
    def _read_all_sensors(self) -> List[Dict]:
        """Read from all active sensors."""
        readings = []
        for sensor in self.sensors:
            try:
                data = sensor.read()
                if data:
                    readings.append({
                        "sensor_type": sensor.sensor_type,
                        "reading_value": data["value"],
                        "unit": data.get("unit", ""),
                        "timestamp": datetime.utcnow().isoformat() + "Z",
                        "location": self.config.location
                    })
            except Exception as e:
                logger.error(f"Sensor {sensor.sensor_type} read failed: {e}")
        return readings
    
    def _report_readings(self, readings: List[Dict]):
        """Sign and report readings to API."""
        for reading in readings:
            try:
                # Sign the reading
                payload = json.dumps(reading, sort_keys=True)
                signature = self.signer.sign(payload)
                
                report = {
                    **reading,
                    "wallet_address": self.signer.wallet_address,
                    "signature": signature
                }
                
                # Store locally
                self.history.store(report)
                
                # Send to API
                self._send_report(report)
                
            except Exception as e:
                logger.error(f"Failed to report reading: {e}")
    
    def _send_report(self, report: Dict):
        """Send report to API endpoint."""
        import urllib.request
        import urllib.error
        
        headers = {
            'Content-Type': 'application/json',
            'User-Agent': 'WattCoin-SensorOracle/1.0'
        }
        
        data = json.dumps(report).encode('utf-8')
        req = urllib.request.Request(
            self.config.api_url,
            data=data,
            headers=headers,
            method='POST'
        )
        
        try:
            with urllib.request.urlopen(req, timeout=10) as response:
                if response.status == 200:
                    logger.info(f"Reported {report['sensor_type']}={report['reading_value']}")
                else:
                    logger.warning(f"API returned status {response.status}")
        except urllib.error.URLError as e:
            logger.warning(f"API connection failed: {e}. Report queued locally.")
        except Exception as e:
            logger.error(f"Unexpected error sending report: {e}")


def main():
    parser = argparse.ArgumentParser(description='WattCoin Sensor Oracle')
    parser.add_argument('--config', default='config.json', help='Config file path')
    parser.add_argument('--mock', action='store_true', help='Use mock sensors')
    parser.add_argument('--interval', type=int, help='Reporting interval in seconds')
    parser.add_argument('--api-url', help='API endpoint URL')
    parser.add_argument('--wallet-key', help='Wallet private key (or set WATT_WALLET_KEY env)')
    
    args = parser.parse_args()
    
    # Load config
    config = OracleConfig.from_file(args.config)
    
    # Override with CLI args
    if args.mock:
        config.mock_mode = True
    if args.interval:
        config.interval = args.interval
    if args.api_url:
        config.api_url = args.api_url
    if args.wallet_key:
        config.private_key = args.wallet_key
    
    # Validate
    if not config.private_key:
        logger.error("No wallet key provided. Set WATT_WALLET_KEY or use --wallet-key")
        sys.exit(1)
    
    oracle = SensorOracle(config)
    
    try:
        oracle.run()
    except KeyboardInterrupt:
        logger.info("Oracle stopped by user")
        sys.exit(0)


if __name__ == '__main__':
    main()
