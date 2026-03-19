#!/usr/bin/env python3
"""
Raspberry Pi Energy Monitor
Monitors energy usage from various smart devices and reports to WATT bounty system
Supports Kasa, Shelly devices and mock mode for testing
"""

import asyncio
import json
import logging
import time
import os
import sys
from datetime import datetime, timezone
from typing import Dict, List, Optional, Union
import aiohttp
import hashlib
import hmac
from dataclasses import dataclass
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ed25519

# Device imports
try:
    from kasa import SmartPlug, Discover
except ImportError:
    SmartPlug = None
    Discover = None

try:
    import requests
except ImportError:
    requests = None

@dataclass
class EnergyReading:
    device_id: str
    device_type: str
    timestamp: datetime
    power_watts: float
    energy_kwh: float
    voltage: Optional[float] = None
    current: Optional[float] = None
    temperature: Optional[float] = None

class MockDevice:
    """Mock device for testing without real hardware"""
    
    def __init__(self, device_id: str):
        self.device_id = device_id
        self.alias = f"Mock Device {device_id}"
        self._power = 50.0  # Mock 50W device
        self._energy = 0.0
        self._last_update = time.time()
    
    async def get_emeter_realtime(self):
        current_time = time.time()
        time_diff = current_time - self._last_update
        self._energy += (self._power / 1000) * (time_diff / 3600)  # Convert to kWh
        self._last_update = current_time
        
        # Add some variance to make it realistic
        import random
        power_variance = random.uniform(0.9, 1.1)
        
        return {
            'power_mw': int(self._power * power_variance * 1000),
            'total_wh': int(self._energy * 1000),
            'voltage_mv': 120000 + random.randint(-1000, 1000),
            'current_ma': int((self._power * power_variance / 120) * 1000)
        }

class KasaDevice:
    """Wrapper for Kasa smart plugs"""
    
    def __init__(self, device: SmartPlug):
        self.device = device
        self.device_id = device.mac
        self.alias = device.alias
    
    async def get_reading(self) -> EnergyReading:
        emeter_data = await self.device.get_emeter_realtime()
        
        return EnergyReading(
            device_id=self.device_id,
            device_type="kasa",
            timestamp=datetime.now(timezone.utc),
            power_watts=emeter_data.get('power_mw', 0) / 1000.0,
            energy_kwh=emeter_data.get('total_wh', 0) / 1000.0,
            voltage=emeter_data.get('voltage_mv', 0) / 1000.0,
            current=emeter_data.get('current_ma', 0) / 1000.0
        )

class ShellyDevice:
    """Wrapper for Shelly devices via HTTP API"""
    
    def __init__(self, ip_address: str, device_id: str):
        self.ip_address = ip_address
        self.device_id = device_id
        self.alias = f"Shelly {device_id}"
        self.base_url = f"http://{ip_address}"
    
    async def get_reading(self) -> EnergyReading:
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(f"{self.base_url}/meter/0") as response:
                    data = await response.json()
                    
                    return EnergyReading(
                        device_id=self.device_id,
                        device_type="shelly",
                        timestamp=datetime.now(timezone.utc),
                        power_watts=data.get('power', 0),
                        energy_kwh=data.get('total', 0) / 60000.0,  # Convert Wmin to kWh
                        voltage=data.get('voltage', 0),
                        current=data.get('current', 0)
                    )
        except Exception as e:
            logging.error(f"Error reading from Shelly device {self.device_id}: {e}")
            raise

class WalletSigner:
    """Handles cryptographic signing of energy data"""
    
    def __init__(self, private_key_path: str):
        self.private_key_path = private_key_path
        self.private_key = self._load_or_generate_key()
        self.public_key = self.private_key.public_key()
        
    def _load_or_generate_key(self) -> ed25519.Ed25519PrivateKey:
        """Load existing key or generate new one"""
        if os.path.exists(self.private_key_path):
            with open(self.private_key_path, 'rb') as f:
                key_data = f.read()
                return serialization.load_pem_private_key(key_data, password=None)
        else:
            # Generate new key
            private_key = ed25519.Ed25519PrivateKey.generate()
            
            # Save key
            os.makedirs(os.path.dirname(self.private_key_path), exist_ok=True)
            with open(self.private_key_path, 'wb') as f:
                f.write(private_key.private_bytes(
                    encoding=serialization.Encoding.PEM,
                    format=serialization.PrivateFormat.PKCS8,
                    encryption_algorithm=serialization.NoEncryption()
                ))
            
            logging.info(f"Generated new private key: {self.private_key_path}")
            return private_key
    
    def get_public_key_hex(self) -> str:
        """Get public key as hex string"""
        public_bytes = self.public_key.public_bytes(
            encoding=serialization.Encoding.Raw,
            format=serialization.PublicFormat.Raw
        )
        return public_bytes.hex()
    
    def sign_data(self, data: dict) -> str:
        """Sign data and return signature as hex string"""
        message = json.dumps(data, sort_keys=True).encode('utf-8')
        signature = self.private_key.sign(message)
        return signature.hex()

class EnergyMonitor:
    """Main energy monitoring class"""
    
    def __init__(self, config_path: str = "config.json"):
        self.config = self._load_config(config_path)
        self.devices = []
        self.signer = WalletSigner(self.config.get('private_key_path', './keys/private_key.pem'))
        self.session = None
        
        # Setup logging
        logging.basicConfig(
            level=getattr(logging, self.config.get('log_level', 'INFO')),
            format='%(asctime)s - %(levelname)s - %(message)s',
            handlers=[
                logging.FileHandler(self.config.get('log_file', './logs/energy_monitor.log')),
                logging.StreamHandler()
            ]
        )
        
        # Ensure log directory exists
        os.makedirs(os.path.dirname(self.config.get('log_file', './logs/energy_monitor.log')), exist_ok=True)
        
        logging.info(f"Energy Monitor initialized with public key: {self.signer.get_public_key_hex()}")
    
    def _load_config(self, config_path: str) -> dict:
        """Load configuration from JSON file"""
        default_config = {
            "devices": [],
            "api_endpoint": "https://watt-bounty.example.com/api/energy",
            "monitoring_interval": 60,
            "mock_mode": False,
            "log_level": "INFO",
            "log_file": "./logs/energy_monitor.log",
            "data_file": "./data/energy_readings.jsonl",
            "private_key_path": "./keys/private_key.pem"
        }
        
        if os.path.exists(config_path):
            with open(config_path, 'r') as f:
                user_config = json.load(f)
                default_config.update(user_config)
        else:
            # Create default config file
            os.makedirs(os.path.dirname(config_path) if os.path.dirname(config_path) else '.', exist_ok=True)
            with open(config_path, 'w') as f:
                json.dump(default_config, f, indent=2)
            logging.info(f"Created default config file: {config_path}")
        
        return default_config
    
    async def discover_devices(self):
        """Discover and initialize devices"""
        self.devices = []
        
        if self.config.get('mock_mode', False):
            # Add mock devices
            for i, device_config in enumerate(self.config.get('devices', [])):
                if device_config.get('type') == 'mock':
                    mock_device = MockDevice(device_config.get('device_id', f'mock_{i}'))
                    self.devices.append(mock_device)
            
            # If no devices configured, add a default mock device
            if not self.devices:
                self.devices.append(MockDevice('mock_default'))
                
            logging.info(f"Initialized {len(self.devices)} mock devices")
            return
        
        # Discover Kasa devices
        if SmartPlug and Discover:
            try:
                discovered = await Discover.discover()
                for addr, device in discovered.items():
                    if hasattr(device, 'get_emeter_realtime'):
                        await device.update()
                        kasa_device = KasaDevice(device)
                        self.devices.append(kasa_device)
                        logging.info(f"Found Kasa device: {kasa_device.alias} ({kasa_device.device_id})")
            except Exception as e:
                logging.error(f"Error discovering Kasa devices: {e}")
        
        # Initialize Shelly devices from config
        for device_config in self.config.get('devices', []):
            if device_config.get('type') == 'shelly':
                try:
                    shelly_device = ShellyDevice(
                        device_config['ip_address'],
                        device_config['device_id']
                    )
                    self.devices.append(shelly_device)
                    logging.info(f"Added Shelly device: {device_config['device_id']}")
                except Exception as e:
                    logging.error(f"Error adding Shelly device {device_config['device_id']}: {e}")
        
        logging.info(f"Initialized {len(self.devices)} devices total")
    
    async def read_device(self, device) -> Optional[EnergyReading]:
        """Read energy data from a single device"""
        try:
            if isinstance(device, MockDevice):
                emeter_data = await device.get_emeter_realtime()
                return EnergyReading(
                    device_id=device.device_id,
                    device_type="mock",
                    timestamp=datetime.now(timezone.utc),
                    power_watts=emeter_data['power_mw'] / 1000.0,
                    energy_kwh=emeter_data['total_wh'] / 1000.0,
                    voltage=emeter_data['voltage_mv'] / 1000.0,
                    current=emeter_data['current_ma'] / 1000.0
                )
            elif isinstance(device, (KasaDevice, ShellyDevice)):
                return await device.get_reading()
            else:
                logging.error(f"Unknown device type: {type(device)}")
                return None
        except Exception as e:
            logging.error(f"Error reading from device {getattr(device, 'device_id', 'unknown')}: {e}")
            return None
    
    def save_reading_local(self, reading: EnergyReading):
        """Save reading to local file"""
        data_file = self.config.get('data_file', './data/energy_readings.jsonl')
        os.makedirs(os.path.dirname(data_file), exist_ok=True)
        
        reading_dict = {
            'device_id': reading.device_id,
            'device_type': reading.device_type,
            'timestamp': reading.timestamp.isoformat(),
            'power_watts': reading.power_watts,
            'energy_kwh': reading.energy_kwh,
            'voltage': reading.voltage,
            'current': reading.current,
            'temperature': reading.temperature
        }
        
        with open(data_file, 'a') as f:
            f.write(json.dumps(reading_dict) + '\n')
    
    async def report_to_api(self, readings: List[EnergyReading]):
        """Report readings to WATT bounty API"""
        if not readings:
            return
        
        # Prepare data for API
        readings_data = []
        for reading in readings:
            readings_data.append({
                'device_id': reading.device_id,
                'device_type': reading.device_type,
                'timestamp': reading.timestamp.isoformat(),
                'power_watts': reading.power_watts,
                'energy_kwh': reading.energy_kwh,
                'voltage': reading.voltage,
                'current': reading.current,
                'temperature': reading.temperature
            })
        
        payload = {
            'public_key': self.signer.get_public_key_hex(),
            'readings': readings_data,
            'monitor_info': {
                'version': '1.0.0',
                'device_count': len(self.devices),
                'pi_id': self._get_pi_id()
            }
        }
        
        # Sign the payload
        signature = self.signer.sign_data(payload)
        payload['signature'] = signature
        
        try:
            if not self.session:
                self.session = aiohttp.ClientSession()
            
            async with self.session.post(
                self.config['api_endpoint'],
                json=payload,
                timeout=aiohttp.ClientTimeout(total=30)
            ) as response:
                if response.status == 200:
                    result = await response.json()
                    logging.info(f"Successfully reported {len(readings)} readings to API")
                    return result
                else:
                    error_text = await response.text()
                    logging.error(f"API error {response.status}: {error_text}")
        except Exception as e:
            logging.error(f"Error reporting to API: {e}")
    
    def _get_pi_id(self) -> str:
        """Get unique Pi identifier"""
        try:
            # Try to get serial number
            with open('/proc/cpuinfo', 'r') as f:
                for line in f:
                    if line.startswith('Serial'):
                        return line.split(':')[1].strip()
        except:
            pass
        
        # Fallback to MAC address
        try:
            import uuid
            mac = uuid.getnode()
            return f"mac_{mac:012x}"
        except:
            pass
        
        # Final fallback
        return "unknown_pi"
    
    async def monitoring_loop(self):
        """Main monitoring loop"""
        logging.info("Starting energy monitoring loop")
        
        while True:
            try:
                start_time = time.time()
                readings = []
                
                # Read from all devices
                for device in self.devices:
                    reading = await self.read_device(device)
                    if reading:
                        readings.append(reading)
                        self.save_reading_local(reading)
                
                if readings:
                    logging.info(f"Collected {len(readings)} readings")
                    
                    # Report to API
                    await self.report_to_api(readings)
                else:
                    logging.warning("No readings collected this cycle")
                
                # Sleep until next interval
                elapsed = time.time() - start_time
                sleep_time = max(0, self.config['monitoring_interval'] - elapsed)
                await asyncio.sleep(sleep_time)
                
            except KeyboardInterrupt:
                logging.info("Monitoring stopped by user")
                break
            except Exception as e:
                logging.error(f"Error in monitoring loop: {e}")
                await asyncio.sleep(self.config['monitoring_interval'])
    
    async def close(self):
        """Cleanup resources"""
        if self.session:
            await self.session.close()

async def main():
    """Main entry point"""
    import argparse
    
    parser = argparse.ArgumentParser(description='Raspberry Pi Energy Monitor')
    parser.add_argument('--config', default='config.json', help='Configuration file path')
    parser.add_argument('--mock', action='store_true', help='Enable mock mode for testing')
    parser.add_argument('--discover', action='store_true', help='Discover devices and exit')
    args = parser.parse_args()
    
    monitor = EnergyMonitor(args.config)
    
    # Override mock mode if specified
    if args.mock:
        monitor.config['mock_mode'] = True
    
    try:
        await monitor.discover_devices()
        
        if args.discover:
            print(f"Found {len(monitor.devices)} devices:")
            for device in monitor.devices:
                print(f"  - {getattr(device, 'alias', 'Unknown')} ({getattr(device, 'device_id', 'Unknown ID')})")
            return
        
        if not monitor.devices:
            logging.error("No devices found. Check configuration or try --mock mode")
            sys.exit(1)
        
        await monitor.monitoring_loop()
        
    finally:
        await monitor.close()

if __name__ == "__main__":
    asyncio.run(main())