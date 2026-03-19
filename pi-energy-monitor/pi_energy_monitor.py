#!/usr/bin/env python3
"""
Pi Energy Monitor - Raspberry Pi Power Consumption Reporter
Monitors power usage and reports to WattCoin API

Usage:
    python pi_energy_monitor.py --config config.yaml
    python pi_energy_monitor.py --mock  # Run with mock hardware
    python pi_energy_monitor.py --status  # Check status
"""

import os
import sys
import json
import time
import argparse
import logging
import sqlite3
import hashlib
import hmac
from datetime import datetime
from pathlib import Path

# Try to import required packages, handle gracefully if missing
try:
    import requests
except ImportError:
    print("ERROR: 'requests' package not installed. Install with: pip install requests")
    sys.exit(1)

try:
    import serial
except ImportError:
    serial = None

# Import local modules
from hardware import create_hardware_driver
from config import load_config, validate_config
from api_client import EnergyAPIClient
from logger import EnergyLogger

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class PiEnergyMonitor:
    """Main energy monitoring application"""
    
    def __init__(self, config_path: str = "config.yaml", mock_mode: bool = False):
        """Initialize the energy monitor"""
        self.config_path = config_path
        self.mock_mode = mock_mode
        
        # Load configuration
        if mock_mode:
            # Create minimal config for mock mode
            self.config = {
                "wallet_address": "MockWallet12345678901234567890123456789012",
                "hardware": {"device_type": "mock"},
                "polling": {"interval_seconds": 60},
                "api": {
                    "base_url": "http://localhost:8000",
                    "endpoint": "/api/v1/energy/report",
                    "timeout": 30,
                    "max_retries": 3
                },
                "logging": {
                    "database_path": "energy_data.db",
                    "json_log": True,
                    "json_log_path": "energy_readings.json"
                }
            }
        else:
            self.config = load_config(config_path)
            validate_config(self.config)
        
        # Initialize components
        self.wallet_address = self.config["wallet_address"]
        
        # Hardware driver
        device_type = "mock" if mock_mode else self.config["hardware"]["device_type"]
        hw_config = self.config["hardware"].get(device_type, {})
        self.hardware = create_hardware_driver(device_type, hw_config)
        
        # API client
        api_config = self.config["api"]
        self.api_client = EnergyAPIClient(
            base_url=api_config["base_url"],
            endpoint=api_config["endpoint"],
            wallet_address=self.wallet_address,
            timeout=api_config.get("timeout", 30),
            max_retries=api_config.get("max_retries", 3)
        )
        
        # Local logger
        log_config = self.config["logging"]
        self.logger = EnergyLogger(
            database_path=log_config.get("database_path", "energy_data.db"),
            json_log=log_config.get("json_log", True),
            json_log_path=log_config.get("json_log_path", "energy_readings.json")
        )
        
        # Polling settings
        polling_config = self.config["polling"]
        self.poll_interval = polling_config.get("interval_seconds", 60)
        self.samples = polling_config.get("samples_per_reading", 5)
        self.sample_delay = polling_config.get("sample_delay", 0.5)
        
        self.running = False
        self.total_reports = 0
        self.failed_reports = 0
    
    def _sign_data(self, data: dict) -> str:
        """Sign report data with wallet address (HMAC-style)"""
        # Create a signature using wallet address as key
        # In production, this would use actual wallet private key
        message = json.dumps(data, sort_keys=True)
        signature = hmac.new(
            self.wallet_address.encode(),
            message.encode(),
            hashlib.sha256
        ).hexdigest()
        return signature
    
    def _read_power(self) -> float:
        """Read power consumption from hardware"""
        readings = []
        
        for _ in range(self.samples):
            try:
                watts = self.hardware.read_power()
                readings.append(watts)
            except Exception as e:
                logger.warning(f"Failed to read power: {e}")
            
            if self.samples > 1:
                time.sleep(self.sample_delay)
        
        if not readings:
            raise RuntimeError("No successful power readings")
        
        # Return average
        return sum(readings) / len(readings)
    
    def _create_report(self, watts: float) -> dict:
        """Create an energy report"""
        timestamp = datetime.utcnow().isoformat() + "Z"
        
        report = {
            "timestamp": timestamp,
            "wallet": self.wallet_address,
            "watts": round(watts, 2),
            "device_type": self.hardware.name,
            "client_version": "1.0.0"
        }
        
        # Add signature
        report["signature"] = self._sign_data(report)
        
        return report
    
    def _process_reading(self) -> bool:
        """Process a single power reading"""
        try:
            # Read power consumption
            watts = self._read_power()
            logger.info(f"Power reading: {watts:.2f} W")
            
            # Create report
            report = self._create_report(watts)
            
            # Log locally
            self.logger.log_reading(report)
            
            # Send to API
            success = self.api_client.send_report(report)
            
            if success:
                self.total_reports += 1
                logger.info(f"Report sent successfully (total: {self.total_reports})")
            else:
                self.failed_reports += 1
                logger.warning(f"Report failed (failed: {self.failed_reports})")
            
            return success
            
        except Exception as e:
            logger.error(f"Error processing reading: {e}")
            self.failed_reports += 1
            return False
    
    def run(self):
        """Main monitoring loop"""
        logger.info("=" * 50)
        logger.info("Pi Energy Monitor Starting")
        logger.info(f"Wallet: {self.wallet_address[:10]}...")
        logger.info(f"Hardware: {self.hardware.name}")
        logger.info(f"Poll interval: {self.poll_interval}s")
        logger.info("=" * 50)
        
        self.running = True
        
        try:
            while self.running:
                self._process_reading()
                
                # Sleep until next reading
                for _ in range(int(self.poll_interval)):
                    if not self.running:
                        break
                    time.sleep(1)
                    
        except KeyboardInterrupt:
            logger.info("Received interrupt, shutting down...")
        finally:
            self.running = False
            self._print_stats()
    
    def _print_stats(self):
        """Print final statistics"""
        logger.info("=" * 50)
        logger.info("Session Statistics")
        logger.info(f"Total reports: {self.total_reports}")
        logger.info(f"Failed reports: {self.failed_reports}")
        if self.total_reports > 0:
            success_rate = (self.total_reports / (self.total_reports + self.failed_reports)) * 100
            logger.info(f"Success rate: {success_rate:.1f}%")
        logger.info("=" * 50)
    
    def get_status(self) -> dict:
        """Get monitor status"""
        return {
            "wallet": self.wallet_address[:10] + "...",
            "hardware": self.hardware.name,
            "poll_interval": self.poll_interval,
            "total_reports": self.total_reports,
            "failed_reports": self.failed_reports,
            "running": self.running
        }


def main():
    """Main entry point"""
    parser = argparse.ArgumentParser(
        description="Pi Energy Monitor - Report power consumption to WattCoin API"
    )
    parser.add_argument(
        "--config", "-c",
        default="config.yaml",
        help="Path to configuration file"
    )
    parser.add_argument(
        "--mock",
        action="store_true",
        help="Run in mock mode (no hardware required)"
    )
    parser.add_argument(
        "--status", "-s",
        action="store_true",
        help="Show current status"
    )
    parser.add_argument(
        "--test-hardware",
        action="store_true",
        help="Test hardware connection"
    )
    parser.add_argument(
        "--test-api",
        action="store_true",
        help="Test API connection"
    )
    
    args = parser.parse_args()
    
    # Handle status command
    if args.status:
        # Try to load config and show status
        try:
            monitor = PiEnergyMonitor(args.config, args.mock)
            status = monitor.get_status()
            print("\n=== Pi Energy Monitor Status ===")
            for key, value in status.items():
                print(f"  {key}: {value}")
            return
        except Exception as e:
            print(f"Error: {e}")
            return
    
    # Handle test hardware
    if args.test_hardware:
        try:
            monitor = PiEnergyMonitor(args.config, args.mock)
            print(f"Testing {monitor.hardware.name}...")
            watts = monitor._read_power()
            print(f"✓ Read successful: {watts:.2f} W")
            return
        except Exception as e:
            print(f"✗ Hardware test failed: {e}")
            sys.exit(1)
    
    # Handle test API
    if args.test_api:
        try:
            monitor = PiEnergyMonitor(args.config, args.mock)
            print(f"Testing API connection to {monitor.api_client.base_url}...")
            test_report = {
                "timestamp": datetime.utcnow().isoformat() + "Z",
                "wallet": monitor.wallet_address,
                "watts": 100.0,
                "device_type": "test",
                "client_version": "1.0.0"
            }
            test_report["signature"] = monitor._sign_data(test_report)
            success = monitor.api_client.send_report(test_report)
            if success:
                print("✓ API test successful")
            else:
                print("✗ API test failed")
            return
        except Exception as e:
            print(f"✗ API test failed: {e}")
            sys.exit(1)
    
    # Run the monitor
    monitor = PiEnergyMonitor(args.config, args.mock)
    monitor.run()


if __name__ == "__main__":
    main()
