import os
from pathlib import Path

class Config:
    # Base directory
    BASE_DIR = Path(__file__).parent
    
    # API Configuration
    API_BASE_URL = os.getenv('API_BASE_URL', 'https://api.energymonitor.com')
    API_KEY = os.getenv('API_KEY', '')
    API_TIMEOUT = int(os.getenv('API_TIMEOUT', '30'))
    
    # Polling Configuration
    SENSOR_POLLING_INTERVAL = int(os.getenv('SENSOR_POLLING_INTERVAL', '60'))  # seconds
    DATA_UPLOAD_INTERVAL = int(os.getenv('DATA_UPLOAD_INTERVAL', '300'))  # seconds
    HEARTBEAT_INTERVAL = int(os.getenv('HEARTBEAT_INTERVAL', '120'))  # seconds
    
    # Device Configuration
    DEVICE_ID = os.getenv('DEVICE_ID', '')
    DEVICE_NAME = os.getenv('DEVICE_NAME', 'RaspberryPi-EnergyMonitor')
    DEVICE_LOCATION = os.getenv('DEVICE_LOCATION', 'Unknown')
    
    # Sensor Configuration
    I2C_BUS = int(os.getenv('I2C_BUS', '1'))
    ADC_ADDRESS = os.getenv('ADC_ADDRESS', '0x48')
    CURRENT_SENSOR_PIN = int(os.getenv('CURRENT_SENSOR_PIN', '0'))
    VOLTAGE_SENSOR_PIN = int(os.getenv('VOLTAGE_SENSOR_PIN', '1'))
    
    # Calibration Values
    VOLTAGE_CALIBRATION = float(os.getenv('VOLTAGE_CALIBRATION', '1.0'))
    CURRENT_CALIBRATION = float(os.getenv('CURRENT_CALIBRATION', '1.0'))
    POWER_OFFSET = float(os.getenv('POWER_OFFSET', '0.0'))
    
    # Wallet Configuration
    WALLET_ADDRESS = os.getenv('WALLET_ADDRESS', '')
    WATT_TOKEN_CONTRACT = os.getenv('WATT_TOKEN_CONTRACT', '')
    
    # Data Storage
    DATA_DIR = BASE_DIR / 'data'
    LOG_DIR = BASE_DIR / 'logs'
    CACHE_DIR = BASE_DIR / 'cache'
    
    # Database Configuration
    DB_PATH = DATA_DIR / 'energy_data.db'
    MAX_DB_SIZE_MB = int(os.getenv('MAX_DB_SIZE_MB', '100'))
    DATA_RETENTION_DAYS = int(os.getenv('DATA_RETENTION_DAYS', '30'))
    
    # Logging Configuration
    LOG_LEVEL = os.getenv('LOG_LEVEL', 'INFO')
    LOG_MAX_SIZE_MB = int(os.getenv('LOG_MAX_SIZE_MB', '10'))
    LOG_BACKUP_COUNT = int(os.getenv('LOG_BACKUP_COUNT', '5'))
    
    # Network Configuration
    WIFI_SSID = os.getenv('WIFI_SSID', '')
    WIFI_PASSWORD = os.getenv('WIFI_PASSWORD', '')
    NETWORK_TIMEOUT = int(os.getenv('NETWORK_TIMEOUT', '10'))
    RETRY_ATTEMPTS = int(os.getenv('RETRY_ATTEMPTS', '3'))
    RETRY_DELAY = int(os.getenv('RETRY_DELAY', '5'))
    
    # Security Configuration
    ENCRYPTION_KEY = os.getenv('ENCRYPTION_KEY', '')
    CERTIFICATE_PATH = BASE_DIR / 'certs' / 'device.crt'
    PRIVATE_KEY_PATH = BASE_DIR / 'certs' / 'device.key'
    
    # Performance Configuration
    MAX_MEMORY_USAGE_MB = int(os.getenv('MAX_MEMORY_USAGE_MB', '128'))
    CPU_USAGE_THRESHOLD = int(os.getenv('CPU_USAGE_THRESHOLD', '80'))
    TEMPERATURE_THRESHOLD = int(os.getenv('TEMPERATURE_THRESHOLD', '70'))
    
    # Energy Calculation Configuration
    VOLTAGE_NOMINAL = float(os.getenv('VOLTAGE_NOMINAL', '120.0'))  # V
    FREQUENCY = float(os.getenv('FREQUENCY', '60.0'))  # Hz
    POWER_FACTOR = float(os.getenv('POWER_FACTOR', '0.85'))
    
    # Data Quality Configuration
    MIN_VOLTAGE = float(os.getenv('MIN_VOLTAGE', '100.0'))
    MAX_VOLTAGE = float(os.getenv('MAX_VOLTAGE', '140.0'))
    MIN_CURRENT = float(os.getenv('MIN_CURRENT', '0.0'))
    MAX_CURRENT = float(os.getenv('MAX_CURRENT', '50.0'))
    
    # Notification Configuration
    ALERT_EMAIL = os.getenv('ALERT_EMAIL', '')
    SMTP_SERVER = os.getenv('SMTP_SERVER', '')
    SMTP_PORT = int(os.getenv('SMTP_PORT', '587'))
    SMTP_USERNAME = os.getenv('SMTP_USERNAME', '')
    SMTP_PASSWORD = os.getenv('SMTP_PASSWORD', '')
    
    # Development Configuration
    DEBUG = os.getenv('DEBUG', 'False').lower() == 'true'
    TEST_MODE = os.getenv('TEST_MODE', 'False').lower() == 'true'
    MOCK_SENSORS = os.getenv('MOCK_SENSORS', 'False').lower() == 'true'
    
    @classmethod
    def create_directories(cls):
        """Create necessary directories if they don't exist"""
        cls.DATA_DIR.mkdir(exist_ok=True)
        cls.LOG_DIR.mkdir(exist_ok=True)
        cls.CACHE_DIR.mkdir(exist_ok=True)
        (cls.BASE_DIR / 'certs').mkdir(exist_ok=True)
    
    @classmethod
    def validate_config(cls):
        """Validate configuration values"""
        errors = []
        
        if not cls.API_KEY:
            errors.append("API_KEY is required")
        
        if not cls.DEVICE_ID:
            errors.append("DEVICE_ID is required")
        
        if not cls.WALLET_ADDRESS:
            errors.append("WALLET_ADDRESS is required")
        
        if cls.SENSOR_POLLING_INTERVAL < 1:
            errors.append("SENSOR_POLLING_INTERVAL must be at least 1 second")
        
        if cls.DATA_UPLOAD_INTERVAL < cls.SENSOR_POLLING_INTERVAL:
            errors.append("DATA_UPLOAD_INTERVAL must be >= SENSOR_POLLING_INTERVAL")
        
        return errors
    
    @classmethod
    def get_api_headers(cls):
        """Get API request headers"""
        return {
            'Authorization': f'Bearer {cls.API_KEY}',
            'Content-Type': 'application/json',
            'User-Agent': f'{cls.DEVICE_NAME}/{cls.DEVICE_ID}'
        }
    
    @classmethod
    def get_device_info(cls):
        """Get device information dictionary"""
        return {
            'device_id': cls.DEVICE_ID,
            'device_name': cls.DEVICE_NAME,
            'location': cls.DEVICE_LOCATION,
            'wallet_address': cls.WALLET_ADDRESS
        }