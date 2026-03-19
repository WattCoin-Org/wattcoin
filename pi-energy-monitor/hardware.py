"""
Hardware abstraction layer for Pi Energy Monitor
Supports multiple power monitoring devices
"""

import random
import logging
from abc import ABC, abstractmethod

logger = logging.getLogger(__name__)


class PowerMeterBase(ABC):
    """Base class for power meter drivers"""
    
    @property
    @abstractmethod
    def name(self) -> str:
        """Return device name"""
        pass
    
    @abstractmethod
    def read_power(self) -> float:
        """Read power consumption in watts"""
        pass
    
    def close(self):
        """Close connection (optional)"""
        pass


class MockPowerMeter(PowerMeterBase):
    """Mock power meter for testing without hardware"""
    
    def __init__(self, config: dict = None):
        self.config = config or {}
        self.base_watts = self.config.get("base_watts", 150.0)
        self.variance = self.config.get("variance", 10.0)
        self._readings = 0
    
    @property
    def name(self) -> str:
        return "mock"
    
    def read_power(self) -> float:
        """Generate simulated power reading"""
        self._readings += 1
        # Add some realistic variation
        noise = random.uniform(-self.variance, self.variance)
        watts = self.base_watts + noise
        # Occasionally spike (like turning on a device)
        if random.random() < 0.05:
            watts += random.uniform(50, 200)
        return max(0, watts)


class KasaPowerMeter(PowerMeterBase):
    """TP-Link Kasa Smart Plug power meter"""
    
    def __init__(self, config: dict):
        self.host = config.get("host", "192.168.1.100")
        self.port = config.get("port", 9999)
        self._socket = None
        
        # Kasa protocol commands
        self._cmd_system_info = self._encode_cmd({"system": {"get_sysinfo": {}}})
    
    @property
    def name(self) -> str:
        return f"kasa:{self.host}"
    
    def _encode_cmd(self, cmd: dict) -> bytes:
        """Encode command for Kasa device"""
        import json
        import struct
        
        data = json.dumps(cmd).encode()
        # Kasa uses a simple protocol: 4-byte length + JSON data
        # With encryption for some commands
        packet = struct.pack(">I", len(data)) + data
        return packet
    
    def _decode_response(self, data: bytes) -> dict:
        """Decode response from Kasa device"""
        import json
        
        # Skip length prefix
        if len(data) > 4:
            try:
                return json.loads(data[4:])
            except json.JSONDecodeError:
                pass
        return {}
    
    def _send_command(self, cmd: bytes) -> dict:
        """Send command to Kasa device and get response"""
        import socket
        import json
        
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(5)
            sock.connect((self.host, self.port))
            sock.send(cmd)
            
            # Receive response
            response = b""
            while True:
                chunk = sock.recv(4096)
                if not chunk:
                    break
                response += chunk
                # Try to parse length
                if len(response) >= 4:
                    import struct
                    length = struct.unpack(">I", response[:4])[0]
                    if len(response) >= 4 + length:
                        break
            
            sock.close()
            return self._decode_response(response)
            
        except Exception as e:
            logger.error(f"Kasa communication error: {e}")
            raise
    
    def read_power(self) -> float:
        """Read power from Kasa plug"""
        try:
            response = self._send_command(self._cmd_system_info)
            
            # Extract power reading
            sys_info = response.get("system", {}).get("get_sysinfo", {})
            
            # Try different possible fields
            power = sys_info.get("current_power") or \
                    sys_info.get("power") or \
                    sys_info.get("real_time_power") or \
                    0.0
            
            return float(power)
            
        except Exception as e:
            logger.error(f"Failed to read Kasa power: {e}")
            # Try alternative: use emeter endpoint
            return self._read_emeter()
    
    def _read_emeter(self) -> float:
        """Try reading via emeter endpoint"""
        import socket
        import json
        import struct
        
        try:
            # Emeter command
            cmd = {"emeter": {"get_realtime": {}}}
            data = json.dumps(cmd).encode()
            packet = struct.pack(">I", len(data)) + data
            
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(5)
            sock.connect((self.host, self.port))
            sock.send(packet)
            
            response = b""
            while True:
                chunk = sock.recv(4096)
                if not chunk:
                    break
                response += chunk
                if len(response) >= 4:
                    length = struct.unpack(">I", response[:4])[0]
                    if len(response) >= 4 + length:
                        break
            
            sock.close()
            
            # Parse response
            if len(response) > 4:
                result = json.loads(response[4:])
                emeter = result.get("emeter", {}).get("get_realtime", {})
                power = emeter.get("power", 0.0)
                return float(power) if power else 0.0
                
        except Exception as e:
            logger.error(f"Kasa emeter read failed: {e}")
            
        raise RuntimeError(f"Could not read power from Kasa at {self.host}")


class ShellyPowerMeter(PowerMeterBase):
    """Shelly Plug power meter"""
    
    def __init__(self, config: dict):
        self.host = config.get("host", "192.168.1.101")
        self.base_url = f"http://{self.host}"
    
    @property
    def name(self) -> str:
        return f"shelly:{self.host}"
    
    def read_power(self) -> float:
        """Read power from Shelly plug"""
        import requests
        
        try:
            # Shelly API endpoint for power readings
            resp = requests.get(f"{self.base_url}/status", timeout=5)
            resp.raise_for_status()
            
            data = resp.json()
            
            # Get power from the first meter
            meters = data.get("meters", [])
            if meters:
                return float(meters[0].get("power", 0.0))
            
            # Try alternative: emeters
            emeters = data.get("emeters", [])
            if emeters:
                return float(emeters[0].get("power", 0.0))
            
            return 0.0
            
        except requests.RequestException as e:
            logger.error(f"Shelly communication error: {e}")
            raise RuntimeError(f"Could not read power from Shelly at {self.host}")


class USBPowerMeter(PowerMeterBase):
    """USB Power Meter (e.g., USB Wattman, FNIRSI)"""
    
    def __init__(self, config: dict):
        self.device = config.get("device", "/dev/ttyUSB0")
        self.baudrate = config.get("baudrate", 115200)
        self._serial = None
        self._connect()
    
    @property
    def name(self) -> str:
        return f"usb_power_meter:{self.device}"
    
    def _connect(self):
        """Connect to USB power meter"""
        global serial
        
        if serial is None:
            raise RuntimeError("pyserial package not installed. Install with: pip install pyserial")
        
        try:
            self._serial = serial.Serial(
                port=self.device,
                baudrate=self.baudrate,
                timeout=2
            )
            logger.info(f"Connected to USB power meter at {self.device}")
        except Exception as e:
            logger.error(f"Failed to connect to USB power meter: {e}")
            raise
    
    def read_power(self) -> float:
        """Read power from USB meter"""
        if not self._serial or not self._serial.is_open:
            self._connect()
        
        try:
            # Clear buffer
            self._serial.reset_input_buffer()
            
            # Send read command (common for FNIRSI USB meter)
            # Format may vary by device
            self._serial.write(b"READ\r\n")
            
            # Read response
            line = self._serial.readline().decode('utf-8', errors='ignore').strip()
            
            # Parse response - common formats:
            # "12.34V 5.67A" -> watts = 12.34 * 5.67
            # "12.34W" -> direct watts
            
            import re
            
            # Try voltage * current
            match = re.search(r'([\d.]+)\s*V\s+([\d.]+)\s*A', line)
            if match:
                volts = float(match.group(1))
                amps = float(match.group(2))
                return volts * amps
            
            # Try direct watts
            match = re.search(r'([\d.]+)\s*W', line)
            if match:
                return float(match.group(1))
            
            # Try just finding any number (fallback)
            numbers = re.findall(r'[\d.]+', line)
            if len(numbers) >= 2:
                # Assume volts and amps
                return float(numbers[0]) * float(numbers[1])
            
            logger.warning(f"Could not parse USB meter response: {line}")
            return 0.0
            
        except Exception as e:
            logger.error(f"USB meter read error: {e}")
            raise RuntimeError(f"Failed to read from USB meter: {e}")
    
    def close(self):
        """Close serial connection"""
        if self._serial and self._serial.is_open:
            self._serial.close()


def create_hardware_driver(device_type: str, config: dict = None) -> PowerMeterBase:
    """Factory function to create appropriate hardware driver"""
    
    drivers = {
        "mock": MockPowerMeter,
        "kasa": KasaPowerMeter,
        "shelly": ShellyPowerMeter,
        "usb_power_meter": USBPowerMeter,
    }
    
    driver_class = drivers.get(device_type.lower())
    
    if driver_class is None:
        raise ValueError(f"Unknown device type: {device_type}. Available: {list(drivers.keys())}")
    
    return driver_class(config or {})
