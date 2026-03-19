#!/usr/bin/env python3
"""
Raspberry Pi Energy Monitor
Supports Kasa, Shelly, and mock devices with local logging, API reporting, and wallet signing
"""

import asyncio
import json
import logging
import time
from datetime import datetime, timezone
from typing import Dict, List, Optional, Any
import sqlite3
import requests
import os
from dataclasses import dataclass, asdict
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives.asymmetric.rsa import RSAPrivateKey
import base64
import hashlib
import hmac

# Device drivers
try:
    from kasa import SmartPlug, Discover
    KASA_AVAILABLE = True
except ImportError:
    KASA_AVAILABLE = False

try:
    import aiohttp
    SHELLY_AVAILABLE = True
except ImportError:
    SHELLY_AVAILABLE = False

@dataclass
class EnergyReading:
    device_id: str
    device_type: str
    timestamp: datetime
    power_w: float
    voltage_v: Optional[float] = None
    current_a: Optional[float] = None
    energy_kwh: Optional[float] = None
    temperature_c: Optional[float] = None

class DatabaseManager:
    def __init__(self, db_path: str = "energy_data.db"):
        self.db_path = db_path
        self.init_database()

    def init_database(self):
        """Initialize SQLite database"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS energy_readings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                device_id TEXT NOT NULL,
                device_type TEXT NOT NULL,
                timestamp TEXT NOT NULL,
                power_w REAL NOT NULL,
                voltage_v REAL,
                current_a REAL,
                energy_kwh REAL,
                temperature_c REAL,
                uploaded INTEGER DEFAULT 0
            )
        """)
        
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_timestamp ON energy_readings(timestamp)
        """)
        
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_device ON energy_readings(device_id)
        """)
        
        conn.commit()
        conn.close()

    def store_reading(self, reading: EnergyReading):
        """Store energy reading to database"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute("""
            INSERT INTO energy_readings 
            (device_id, device_type, timestamp, power_w, voltage_v, current_a, energy_kwh, temperature_c)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            reading.device_id,
            reading.device_type,
            reading.timestamp.isoformat(),
            reading.power_w,
            reading.voltage_v,
            reading.current_a,
            reading.energy_kwh,
            reading.temperature_c
        ))
        
        conn.commit()
        conn.close()

    def get_unuploaded_readings(self, limit: int = 100) -> List[Dict]:
        """Get readings that haven't been uploaded"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT * FROM energy_readings 
            WHERE uploaded = 0 
            ORDER BY timestamp ASC 
            LIMIT ?
        """, (limit,))
        
        columns = [description[0] for description in cursor.description]
        readings = [dict(zip(columns, row)) for row in cursor.fetchall()]
        
        conn.close()
        return readings

    def mark_uploaded(self, reading_ids: List[int]):
        """Mark readings as uploaded"""
        if not reading_ids:
            return
            
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        placeholders = ','.join('?' * len(reading_ids))
        cursor.execute(f"""
            UPDATE energy_readings 
            SET uploaded = 1 
            WHERE id IN ({placeholders})
        """, reading_ids)
        
        conn.commit()
        conn.close()

class MockDevice:
    """Mock device for testing"""
    def __init__(self, device_id: str):
        self.device_id = device_id
        self._power_base = 100.0
        self._start_time = time.time()

    async def get_reading(self) -> EnergyReading:
        """Generate mock reading with some variation"""
        elapsed = time.time() - self._start_time
        power_variation = 20 * (0.5 - (elapsed % 10) / 10)  # Vary ±20W over 10s cycle
        power = self._power_base + power_variation
        
        return EnergyReading(
            device_id=self.device_id,
            device_type="mock",
            timestamp=datetime.now(timezone.utc),
            power_w=power,
            voltage_v=240.0,
            current_a=power / 240.0,
            energy_kwh=power * elapsed / 3600 / 1000,
            temperature_c=25.0
        )

class KasaDevice:
    """Kasa smart plug wrapper"""
    def __init__(self, device_id: str, host: str):
        self.device_id = device_id
        self.host = host
        self.plug = None

    async def connect(self):
        """Connect to Kasa device"""
        if not KASA_AVAILABLE:
            raise RuntimeError("Kasa library not available")
        
        self.plug = SmartPlug(self.host)
        await self.plug.update()

    async def get_reading(self) -> EnergyReading:
        """Get reading from Kasa device"""
        if not self.plug:
            await self.connect()
        
        await self.plug.update()
        emeter = self.plug.emeter_realtime
        
        return EnergyReading(
            device_id=self.device_id,
            device_type="kasa",
            timestamp=datetime.now(timezone.utc),
            power_w=emeter.get("power", 0.0),
            voltage_v=emeter.get("voltage", None),
            current_a=emeter.get("current", None),
            energy_kwh=emeter.get("total", None)
        )

class ShellyDevice:
    """Shelly device wrapper"""
    def __init__(self, device_id: str, host: str):
        self.device_id = device_id
        self.host = host
        self.session = None

    async def connect(self):
        """Connect to Shelly device"""
        if not SHELLY_AVAILABLE:
            raise RuntimeError("aiohttp library not available for Shelly")
        
        self.session = aiohttp.ClientSession()

    async def get_reading(self) -> EnergyReading:
        """Get reading from Shelly device"""
        if not self.session:
            await self.connect()
        
        url = f"http://{self.host}/status"
        async with self.session.get(url) as response:
            data = await response.json()
        
        # Parse Shelly response (example for Shelly Plug S)
        meters = data.get("meters", [{}])
        meter = meters[0] if meters else {}
        
        return EnergyReading(
            device_id=self.device_id,
            device_type="shelly",
            timestamp=datetime.now(timezone.utc),
            power_w=meter.get("power", 0.0),
            voltage_v=None,
            current_a=None,
            energy_kwh=meter.get("total", 0.0) / 60000,  # Wh to kWh
            temperature_c=data.get("tmp", {}).get("tC", None)
        )

    async def close(self):
        """Close Shelly connection"""
        if self.session:
            await self.session.close()

class WalletSigner:
    """Handle wallet signing for energy data"""
    def __init__(self, private_key_path: str = "wallet_private_key.pem"):
        self.private_key_path = private_key_path
        self.private_key = self._load_or_create_key()

    def _load_or_create_key(self) -> RSAPrivateKey:
        """Load existing key or create new one"""
        if os.path.exists(self.private_key_path):
            with open(self.private_key_path, 'rb') as f:
                return serialization.load_pem_private_key(
                    f.read(),
                    password=None
                )
        else:
            # Generate new key
            private_key = rsa.generate_private_key(
                public_exponent=65537,
                key_size=2048
            )
            
            # Save private key
            pem = private_key.private_bytes(
                encoding=serialization.Encoding.PEM,
                format=serialization.PrivateFormat.PKCS8,
                encryption_algorithm=serialization.NoEncryption()
            )
            
            with open(self.private_key_path, 'wb') as f:
                f.write(pem)
            
            return private_key

    def get_wallet_address(self) -> str:
        """Get wallet address from public key"""
        public_key = self.private_key.public_key()
        public_bytes = public_key.public_bytes(
            encoding=serialization.Encoding.DER,
            format=serialization.PublicFormat.SubjectPublicKeyInfo
        )
        
        # Simple hash-based address generation
        hash_digest = hashlib.sha256(public_bytes).digest()
        return base64.b58encode(hash_digest[:20]).decode()

    def sign_data(self, data: dict) -> str:
        """Sign data with private key"""
        # Create canonical JSON string
        json_str = json.dumps(data, sort_keys=True, separators=(',', ':'))
        data_bytes = json_str.encode('utf-8')
        
        # Create signature
        signature = self.private_key.sign(
            data_bytes,
            hashes.SHA256()
        )
        
        return base64.b64encode(signature).decode()

class EnergyMonitor:
    """Main energy monitoring class"""
    def __init__(self, config_path: str = "config.json"):
        self.config = self._load_config(config_path)
        self.db = DatabaseManager()
        self.signer = WalletSigner()
        self.devices = []
        self.running = False
        
        # Setup logging
        logging.basicConfig(
            level=getattr(logging, self.config.get('log_level', 'INFO')),
            format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
            handlers=[
                logging.FileHandler('energy_monitor.log'),
                logging.StreamHandler()
            ]
        )
        self.logger = logging.getLogger(__name__)

    def _load_config(self, config_path: str) -> dict:
        """Load configuration from JSON file"""
        default_config = {
            "devices": [
                {
                    "id": "mock_device_1",
                    "type": "mock"
                }
            ],
            "reading_interval": 30,
            "upload_interval": 300,
            "api_endpoint": "https://api.wattcoin.org/energy",
            "log_level": "INFO"
        }
        
        if os.path.exists(config_path):
            with open(config_path, 'r') as f:
                config = json.load(f)
            # Merge with defaults
            for key, value in default_config.items():
                if key not in config:
                    config[key] = value
            return config
        else:
            # Create default config
            with open(config_path, 'w') as f:
                json.dump(default_config, f, indent=2)
            return default_config

    async def _init_devices(self):
        """Initialize all configured devices"""
        for device_config in self.config['devices']:
            device_id = device_config['id']
            device_type = device_config['type']
            
            try:
                if device_type == 'mock':
                    device = MockDevice(device_id)
                elif device_type == 'kasa':
                    device = KasaDevice(device_id, device_config['host'])
                    await device.connect()
                elif device_type == 'shelly':
                    device = ShellyDevice(device_id, device_config['host'])
                    await device.connect()
                else:
                    self.logger.error(f"Unknown device type: {device_type}")
                    continue
                
                self.devices.append(device)
                self.logger.info(f"Initialized device: {device_id} ({device_type})")
                
            except Exception as e:
                self.logger.error(f"Failed to initialize device {device_id}: {e}")

    async def _read_device(self, device) -> Optional[EnergyReading]:
        """Read energy data from a device"""
        try:
            reading = await device.get_reading()
            self.logger.debug(f"Reading from {reading.device_id}: {reading.power_w}W")
            return reading
        except Exception as e:
            self.logger.error(f"Failed to read from device {device.device_id}: {e}")
            return None

    async def _collect_readings(self):
        """Collect readings from all devices"""
        tasks = [self._read_device(device) for device in self.devices]
        readings = await asyncio.gather(*tasks, return_exceptions=True)
        
        valid_readings = []
        for reading in readings:
            if isinstance(reading, EnergyReading):
                valid_readings.append(reading)
                self.db.store_reading(reading)
        
        return valid_readings

    def _upload_readings(self, readings: List[Dict]) -> bool:
        """Upload readings to API"""
        if not readings:
            return True
        
        try:
            # Prepare payload
            wallet_address = self.signer.get_wallet_address()
            timestamp = datetime.now(timezone.utc).isoformat()
            
            payload = {
                "wallet_address": wallet_address,
                "timestamp": timestamp,
                "readings": readings
            }
            
            # Sign the payload
            signature = self.signer.sign_data(payload)
            payload["signature"] = signature
            
            # Send to API
            response = requests.post(
                self.config['api_endpoint'],
                json=payload,
                timeout=30,
                headers={'Content-Type': 'application/json'}
            )
            
            if response.status_code == 200:
                self.logger.info(f"Successfully uploaded {len(readings)} readings")
                return True
            else:
                self.logger.error(f"Upload failed: {response.status_code} - {response.text}")
                return False
                
        except Exception as e:
            self.logger.error(f"Upload error: {e}")
            return False

    async def _upload_task(self):
        """Background task to upload readings"""
        while self.running:
            try:
                readings = self.db.get_unuploaded_readings()
                if readings:
                    if self._upload_readings(readings):
                        reading_ids = [r['id'] for r in readings]
                        self.db.mark_uploaded(reading_ids)
                
                await asyncio.sleep(self.config['upload_interval'])
                
            except Exception as e:
                self.logger.error(f"Upload task error: {e}")
                await asyncio.sleep(60)  # Wait before retrying

    async def _monitoring_task(self):
        """Main monitoring task"""
        while self.running:
            try:
                readings = await self._collect_readings()
                self.logger.info(f"Collected {len(readings)} readings")
                
                await asyncio.sleep(self.config['reading_interval'])
                
            except Exception as e:
                self.logger.error(f"Monitoring task error: {e}")
                await asyncio.sleep(30)  # Wait before retrying

    async def start(self):
        """Start the energy monitor"""
        self.logger.info("Starting Energy Monitor")
        self.logger.info(f"Wallet Address: {self.signer.get_wallet_address()}")
        
        await self._init_devices()
        
        if not self.devices:
            self.logger.error("No devices initialized. Exiting.")
            return
        
        self.running = True
        
        # Start background tasks
        monitoring_task = asyncio.create_task(self._monitoring_task())
        upload_task = asyncio.create_task(self._upload_task())
        
        try:
            await asyncio.gather(monitoring_task, upload_task)
        except KeyboardInterrupt:
            self.logger.info("Received shutdown signal")
        finally:
            await self.stop()

    async def stop(self):
        """Stop the energy monitor"""
        self.logger.info("Stopping Energy Monitor")
        self.running = False
        
        # Close device connections
        for device in self.devices:
            if hasattr(device, 'close'):
                await device.close()

async def main():
    """Main entry point"""
    monitor = EnergyMonitor()
    await monitor.start()

if __name__ == "__main__":
    asyncio.run(main())