"""
Sensor implementations with mock mode support.
"""
import random
import time
from abc import ABC, abstractmethod
from typing import Dict


class BaseSensor(ABC):
    """Abstract base sensor."""
    
    def __init__(self, sensor_type: str):
        self.sensor_type = sensor_type
    
    @abstractmethod
    def read(self) -> Dict:
        """Read sensor data. Returns dict with 'value' and optional 'unit'."""
        pass


class DHT22Sensor(BaseSensor):
    """DHT22 temperature and humidity sensor."""
    
    def __init__(self, mock_mode: bool = False):
        super().__init__("DHT22")
        self.mock_mode = mock_mode
        self._last_temp = 22.0
        self._last_humidity = 55.0
    
    def read(self) -> Dict:
        if self.mock_mode:
            # Simulate realistic temp/humidity changes
            self._last_temp += random.uniform(-0.5, 0.5)
            self._last_temp = max(15.0, min(35.0, self._last_temp))
            self._last_humidity += random.uniform(-2.0, 2.0)
            self._last_humidity = max(30.0, min(80.0, self._last_humidity))
            
            return {
                "value": {
                    "temperature_c": round(self._last_temp, 1),
                    "humidity_percent": round(self._last_humidity, 1)
                },
                "unit": "°C / %"
            }
        else:
            # Real hardware read using Adafruit_DHT
            try:
                import Adafruit_DHT
                humidity, temperature = Adafruit_DHT.read_retry(Adafruit_DHT.DHT22, 4)
                if humidity is not None and temperature is not None:
                    return {
                        "value": {
                            "temperature_c": round(temperature, 1),
                            "humidity_percent": round(humidity, 1)
                        },
                        "unit": "°C / %"
                    }
                else:
                    raise RuntimeError("Failed to read from DHT22")
            except ImportError:
                raise RuntimeError("Adafruit_DHT library not installed. Use --mock for testing.")


class PIRSensor(BaseSensor):
    """PIR motion sensor."""
    
    def __init__(self, mock_mode: bool = False):
        super().__init__("PIR")
        self.mock_mode = mock_mode
        self._last_motion = False
        self._consecutive_reads = 0
    
    def read(self) -> Dict:
        if self.mock_mode:
            # Simulate motion events (bursts of True, then False)
            if self._consecutive_reads > 0:
                self._consecutive_reads -= 1
                motion = True
            else:
                motion = random.random() < 0.15  # 15% chance of motion
                if motion:
                    self._consecutive_reads = random.randint(2, 5)
            
            self._last_motion = motion
            return {
                "value": "motion_detected" if motion else "no_motion",
                "unit": "boolean"
            }
        else:
            # Real hardware read using GPIO
            try:
                import RPi.GPIO as GPIO
                GPIO.setmode(GPIO.BCM)
                GPIO.setup(17, GPIO.IN)
                motion = GPIO.input(17)
                return {
                    "value": "motion_detected" if motion else "no_motion",
                    "unit": "boolean"
                }
            except ImportError:
                raise RuntimeError("RPi.GPIO library not installed. Use --mock for testing.")


class MockGenericSensor(BaseSensor):
    """Generic mock sensor for testing."""
    
    def __init__(self, sensor_type: str = "MOCK"):
        super().__init__(sensor_type)
        self._counter = 0
    
    def read(self) -> Dict:
        self._counter += 1
        return {
            "value": {
                "sequence_id": self._counter,
                "random_value": round(random.uniform(0, 100), 2)
            },
            "unit": "arbitrary"
        }


class SensorFactory:
    """Factory for creating sensors."""
    
    @staticmethod
    def create(sensor_type: str, mock_mode: bool = False) -> BaseSensor:
        sensor_type = sensor_type.upper()
        
        if sensor_type == "DHT22":
            return DHT22Sensor(mock_mode=mock_mode)
        elif sensor_type == "PIR":
            return PIRSensor(mock_mode=mock_mode)
        elif sensor_type == "MOCK":
            return MockGenericSensor()
        else:
            raise ValueError(f"Unknown sensor type: {sensor_type}")
