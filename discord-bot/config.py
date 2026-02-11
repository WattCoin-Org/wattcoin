"""Configuration management for WattCoin Discord Bot."""
import os
from dotenv import load_dotenv

load_dotenv()


class Config:
    """Bot configuration."""
    
    # Discord
    DISCORD_TOKEN = os.getenv('DISCORD_TOKEN')
    DISCORD_GUILD_ID = os.getenv('DISCORD_GUILD_ID')
    COMMAND_PREFIX = os.getenv('COMMAND_PREFIX', '!')
    
    # WattCoin API
    WATTCOIN_API_URL = os.getenv('WATTCOIN_API_URL', 'https://wattcoin.org/api/v1')
    WATTCOIN_API_KEY = os.getenv('WATTCOIN_API_KEY', '')
    
    # Solana
    SOLANA_RPC_URL = os.getenv('SOLANA_RPC_URL', 'https://api.mainnet-beta.solana.com')
    WATT_MINT = os.getenv('WATT_MINT', '')
    
    # Alerts
    ALERT_CHECK_INTERVAL = int(os.getenv('ALERT_CHECK_INTERVAL', '60'))
    MAX_ALERTS_PER_USER = int(os.getenv('MAX_ALERTS_PER_USER', '5'))
    
    # Database
    DATABASE_URL = os.getenv('DATABASE_URL', 'sqlite:///wattcoin_bot.db')


def validate_config():
    """Validate required configuration."""
    required = [
        ('DISCORD_TOKEN', Config.DISCORD_TOKEN),
        ('WATTCOIN_API_URL', Config.WATTCOIN_API_URL),
    ]
    
    missing = [name for name, value in required if not value]
    if missing:
        raise ValueError(f"Missing required environment variables: {', '.join(missing)}")
