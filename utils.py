"""
Utility Functions
Common helper functions used across modules
"""

import logging
import logging.handlers
import os
import sys
from datetime import datetime, timezone
from typing import Dict, Any, Optional

def setup_logging(config: Dict[str, Any]) -> None:
    """Setup logging configuration"""
    try:
        # Get logging configuration
        log_level = config.get('level', 'INFO')
        log_format = config.get('format', '%(asctime)s - %(name)s - %(levelname)s - %(message)s')
        log_file = config.get('file', 'crypto_bot.log')
        max_bytes = config.get('max_bytes', 10485760)  # 10MB
        backup_count = config.get('backup_count', 5)
        
        # Create formatter
        formatter = logging.Formatter(log_format)
        
        # Setup root logger
        root_logger = logging.getLogger()
        root_logger.setLevel(getattr(logging, log_level.upper()))
        
        # Clear existing handlers
        for handler in root_logger.handlers[:]:
            root_logger.removeHandler(handler)
        
        # Console handler
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setFormatter(formatter)
        root_logger.addHandler(console_handler)
        
        # File handler with rotation
        if log_file:
            file_handler = logging.handlers.RotatingFileHandler(
                log_file, maxBytes=max_bytes, backupCount=backup_count
            )
            file_handler.setFormatter(formatter)
            root_logger.addHandler(file_handler)
        
        # Reduce noise from external libraries
        logging.getLogger('aiohttp').setLevel(logging.WARNING)
        logging.getLogger('urllib3').setLevel(logging.WARNING)
        
        logging.info(f"Logging configured - Level: {log_level}, File: {log_file}")
        
    except Exception as e:
        print(f"Error setting up logging: {e}")

def validate_config(config: Dict[str, Any]) -> bool:
    """Validate configuration parameters"""
    try:
        required_keys = [
            'trading.symbol',
            'trading.timeframe',
            'api_keys.telegram_token',
            'telegram.chat_id'
        ]
        
        for key_path in required_keys:
            if not get_nested_value(config, key_path):
                logging.error(f"Missing required configuration: {key_path}")
                return False
        
        # Validate trading parameters
        symbol = config['trading']['symbol']
        if not symbol or not isinstance(symbol, str):
            logging.error("Invalid trading symbol")
            return False
        
        timeframe = config['trading']['timeframe']
        valid_timeframes = ['1m', '5m', '15m', '30m', '1h', '4h', '1d']
        if timeframe not in valid_timeframes:
            logging.error(f"Invalid timeframe: {timeframe}")
            return False
        
        # Validate risk management
        risk_pct = config.get('risk_management', {}).get('risk_per_trade', 2.0)
        if not (0.1 <= risk_pct <= 10.0):
            logging.error(f"Risk per trade should be between 0.1% and 10%: {risk_pct}%")
            return False
        
        logging.info("Configuration validation passed")
        return True
        
    except Exception as e:
        logging.error(f"Error validating configuration: {e}")
        return False

def get_nested_value(config: Dict[str, Any], key_path: str) -> Any:
    """Get nested dictionary value using dot notation"""
    try:
        keys = key_path.split('.')
        value = config
        for key in keys:
            value = value.get(key)
            if value is None:
                return None
        return value
    except Exception:
        return None

def format_number(number: float, decimals: int = 2) -> str:
    """Format number with proper decimals and thousand separators"""
    try:
        if abs(number) >= 1000000:
            return f"{number / 1000000:.{decimals}f}M"
        elif abs(number) >= 1000:
            return f"{number / 1000:.{decimals}f}K"
        else:
            return f"{number:,.{decimals}f}"
    except Exception:
        return str(number)

def calculate_percentage_change(old_value: float, new_value: float) -> float:
    """Calculate percentage change between two values"""
    try:
        if old_value == 0:
            return 0.0
        return ((new_value - old_value) / old_value) * 100
    except Exception:
        return 0.0

def utc_timestamp() -> str:
    """Get current UTC timestamp as ISO string"""
    return datetime.now(timezone.utc).isoformat()

def safe_float(value: Any, default: float = 0.0) -> float:
    """Safely convert value to float"""
    try:
        return float(value)
    except (ValueError, TypeError):
        return default

def safe_int(value: Any, default: int = 0) -> int:
    """Safely convert value to int"""
    try:
        return int(value)
    except (ValueError, TypeError):
        return default

def truncate_string(text: str, max_length: int = 100) -> str:
    """Truncate string to maximum length"""
    if len(text) <= max_length:
        return text
    return text[:max_length-3] + "..."

def load_environment_variables() -> Dict[str, str]:
    """Load relevant environment variables"""
    env_vars = {}
    
    # List of environment variables to check
    env_keys = [
        'BINANCE_API_KEY',
        'BINANCE_API_SECRET', 
        'FINNHUB_API_KEY',
        'TELEGRAM_BOT_TOKEN',
        'TELEGRAM_CHAT_ID',
        'LOG_LEVEL'
    ]
    
    for key in env_keys:
        value = os.getenv(key)
        if value:
            env_vars[key] = value
    
    return env_vars

def create_directories() -> None:
    """Create necessary directories if they don't exist"""
    directories = ['logs', 'data', 'static']
    
    for directory in directories:
        if not os.path.exists(directory):
            os.makedirs(directory)
            logging.info(f"Created directory: {directory}")

def health_check() -> Dict[str, Any]:
    """Perform basic health check"""
    try:
        return {
            'status': 'healthy',
            'timestamp': utc_timestamp(),
            'python_version': sys.version.split()[0],
            'working_directory': os.getcwd(),
            'environment_variables': len(load_environment_variables())
        }
    except Exception as e:
        return {
            'status': 'unhealthy',
            'error': str(e),
            'timestamp': utc_timestamp()
        }

class RateLimiter:
    """Simple rate limiter for API calls"""
    
    def __init__(self, max_calls: int = 10, time_window: int = 60):
        self.max_calls = max_calls
        self.time_window = time_window
        self.calls = []
    
    def can_make_call(self) -> bool:
        """Check if a call can be made within rate limits"""
        now = datetime.now()
        
        # Remove calls outside the time window
        self.calls = [call_time for call_time in self.calls 
                     if (now - call_time).seconds < self.time_window]
        
        return len(self.calls) < self.max_calls
    
    def make_call(self) -> bool:
        """Record a call if within rate limits"""
        if self.can_make_call():
            self.calls.append(datetime.now())
            return True
        return False

def retry_async(max_retries: int = 3, delay: float = 1.0):
    """Decorator for retrying async functions"""
    def decorator(func):
        async def wrapper(*args, **kwargs):
            import asyncio
            
            last_exception = None
            for attempt in range(max_retries):
                try:
                    return await func(*args, **kwargs)
                except Exception as e:
                    last_exception = e
                    if attempt < max_retries - 1:
                        logging.warning(f"Attempt {attempt + 1} failed: {e}. Retrying in {delay}s...")
                        await asyncio.sleep(delay)
                    else:
                        logging.error(f"All {max_retries} attempts failed. Last error: {e}")
            
            if last_exception:
                raise last_exception
        
        return wrapper
    return decorator

# Configuration validation schemas
CONFIG_SCHEMA = {
    'trading': {
        'symbol': str,
        'timeframe': str,
        'check_interval': int
    },
    'api_keys': {
        'telegram_token': str,
        'finnhub_key': str
    },
    'telegram': {
        'chat_id': str,
        'enable_notifications': bool
    },
    'risk_management': {
        'account_balance': (int, float),
        'risk_per_trade': (int, float)
    }
}

def validate_config_schema(config: Dict[str, Any], schema: Dict[str, Any] = CONFIG_SCHEMA) -> list[str]:
    """Validate configuration against schema"""
    errors = []
    
    def check_section(config_section: Dict[str, Any], schema_section: Dict[str, Any], path: str = ""):
        for key, expected_type in schema_section.items():
            full_path = f"{path}.{key}" if path else key
            
            if key not in config_section:
                errors.append(f"Missing required key: {full_path}")
                continue
            
            value = config_section[key]
            
            if isinstance(expected_type, dict):
                if not isinstance(value, dict):
                    errors.append(f"Expected dict for {full_path}, got {type(value).__name__}")
                else:
                    check_section(value, expected_type, full_path)
            elif isinstance(expected_type, tuple):
                if not isinstance(value, expected_type):
                    errors.append(f"Expected {expected_type} for {full_path}, got {type(value).__name__}")
            else:
                if not isinstance(value, expected_type):
                    errors.append(f"Expected {expected_type.__name__} for {full_path}, got {type(value).__name__}")
    
    try:
        check_section(config, schema)
    except Exception as e:
        errors.append(f"Schema validation error: {e}")
    
    return errors
