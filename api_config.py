"""
Centralized API configuration for cryptocurrency market analysis bot.
Contains all public API endpoints and configurations.
"""

from typing import Dict, List, Optional
import os


class APIConfig:
    """Centralized configuration for all external APIs"""
    
    # Binance API Configuration
    BINANCE_ENDPOINTS = [
        "https://api.binance.com/api/v3",           # Primary endpoint
        "https://data-api.binance.vision/api/v3",   # Market data only endpoint
        "https://api1.binance.com/api/v3",          # Alternative 1
        "https://api2.binance.com/api/v3",          # Alternative 2
        "https://api3.binance.com/api/v3",          # Alternative 3
        "https://api4.binance.com/api/v3"           # Alternative 4
    ]
    
    BINANCE_PATHS = {
        'klines': '/klines',
        'ticker_price': '/ticker/price',
        'ticker_24hr': '/ticker/24hr',
        'exchange_info': '/exchangeInfo'
    }
    
    # Sentiment Analysis APIs
    SENTIMENT_APIS = {
        'finnhub': {
            'base_url': 'https://finnhub.io/api/v1',
            'endpoints': {
                'company_news': '/company-news',
                'crypto_profile': '/crypto/profile'
            },
            'auth_param': 'token',
            'rate_limit': 60,  # calls per minute
            'free_tier': True
        },
        
        'newsapi': {
            'base_url': 'https://newsapi.org/v2',
            'endpoints': {
                'everything': '/everything',
                'top_headlines': '/top-headlines'
            },
            'auth_param': 'apiKey',
            'rate_limit': 1000,  # calls per day for free tier
            'free_tier': True
        },
        
        'coingecko': {
            'base_url': 'https://api.coingecko.com/api/v3',
            'endpoints': {
                'coin_data': '/coins/{id}',
                'markets': '/coins/markets',
                'trending': '/search/trending',
                'global': '/global'
            },
            'auth_param': None,  # No auth required for free tier
            'rate_limit': 50,  # calls per minute for free tier
            'free_tier': True
        },
        
        'fear_greed': {
            'base_url': 'https://api.alternative.me',
            'endpoints': {
                'fng': '/fng/',
                'fng_history': '/fng/?limit={limit}&date_format=us'
            },
            'auth_param': None,  # No auth required
            'rate_limit': None,  # No specified limit
            'free_tier': True
        },
        
        'cryptocompare': {
            'base_url': 'https://min-api.cryptocompare.com/data',
            'endpoints': {
                'price': '/price',
                'news': '/v2/news/',
                'social_stats': '/social/coin/general'
            },
            'auth_param': 'api_key',
            'rate_limit': 100000,  # calls per month for free tier
            'free_tier': True
        }
    }
    
    # Notification APIs
    NOTIFICATION_APIS = {
        'telegram': {
            'base_url': 'https://api.telegram.org/bot{token}',
            'endpoints': {
                'send_message': '/sendMessage',
                'send_photo': '/sendPhoto',
                'get_updates': '/getUpdates'
            },
            'auth_method': 'token_in_url',
            'rate_limit': 30,  # messages per second
            'free_tier': True
        }
    }
    
    # Symbol mappings for different APIs
    SYMBOL_MAPPINGS = {
        'coingecko': {
            'BTCUSDT': 'bitcoin',
            'ETHUSDT': 'ethereum', 
            'BNBUSDT': 'binancecoin',
            'SOLUSDT': 'solana',
            'XRPUSDT': 'ripple',
            'ADAUSDT': 'cardano',
            'DOGEUSDT': 'dogecoin',
            'MATICUSDT': 'matic-network',
            'DOTUSDT': 'polkadot',
            'LTCUSDT': 'litecoin',
            'AVAXUSDT': 'avalanche-2',
            'LINKUSDT': 'chainlink',
            'ATOMUSDT': 'cosmos'
        },
        
        'finnhub': {
            'BTCUSDT': 'BTC-USD',
            'ETHUSDT': 'ETH-USD',
            'BNBUSDT': 'BNB-USD',
            'SOLUSDT': 'SOL-USD',
            'XRPUSDT': 'XRP-USD',
            'ADAUSDT': 'ADA-USD',
            'DOGEUSDT': 'DOGE-USD',
            'MATICUSDT': 'MATIC-USD',
            'DOTUSDT': 'DOT-USD',
            'LTCUSDT': 'LTC-USD'
        },
        
        'coin_names': {
            'BTCUSDT': 'Bitcoin',
            'ETHUSDT': 'Ethereum',
            'BNBUSDT': 'Binance',
            'SOLUSDT': 'Solana',
            'XRPUSDT': 'Ripple',
            'ADAUSDT': 'Cardano',
            'DOGEUSDT': 'Dogecoin',
            'MATICUSDT': 'Polygon',
            'DOTUSDT': 'Polkadot',
            'LTCUSDT': 'Litecoin'
        }
    }
    
    @classmethod
    def get_api_key(cls, api_name: str) -> Optional[str]:
        """Get API key from environment variables"""
        key_mapping = {
            'finnhub': 'FINNHUB_API_KEY',
            'newsapi': 'NEWSAPI_KEY', 
            'cryptocompare': 'CRYPTOCOMPARE_KEY',
            'binance': 'BINANCE_API_KEY',
            'telegram': 'TELEGRAM_BOT_TOKEN'
        }
        
        env_var = key_mapping.get(api_name)
        if env_var:
            return os.getenv(env_var)
        return None
    
    @classmethod
    def get_full_url(cls, api_category: str, api_name: str, endpoint: str, **kwargs) -> str:
        """Build full URL for API endpoint"""
        if api_category == 'sentiment':
            api_config = cls.SENTIMENT_APIS.get(api_name)
        elif api_category == 'notification':
            api_config = cls.NOTIFICATION_APIS.get(api_name)
        else:
            raise ValueError(f"Unknown API category: {api_category}")
        
        if not api_config:
            raise ValueError(f"Unknown API: {api_name}")
        
        base_url = api_config['base_url']
        endpoint_path = api_config['endpoints'].get(endpoint)
        
        if not endpoint_path:
            raise ValueError(f"Unknown endpoint: {endpoint} for API: {api_name}")
        
        # Handle token replacement in URL (for Telegram)
        if '{token}' in base_url:
            token = cls.get_api_key(api_name)
            if token:
                base_url = base_url.format(token=token)
        
        # Handle parameter replacement in endpoint
        full_url = base_url + endpoint_path.format(**kwargs)
        return full_url
    
    @classmethod
    def get_symbol_mapping(cls, symbol: str, api_name: str) -> Optional[str]:
        """Get symbol mapping for specific API"""
        mappings = cls.SYMBOL_MAPPINGS.get(api_name, {})
        return mappings.get(symbol)
    
    @classmethod
    def get_auth_params(cls, api_name: str) -> Dict[str, str]:
        """Get authentication parameters for API"""
        api_key = cls.get_api_key(api_name)
        if not api_key:
            return {}
        
        # Find API config
        for category in [cls.SENTIMENT_APIS, cls.NOTIFICATION_APIS]:
            if api_name in category:
                auth_param = category[api_name].get('auth_param')
                if auth_param:
                    return {auth_param: api_key}
        
        return {}
    
    @classmethod
    def get_rate_limit(cls, api_name: str) -> Optional[int]:
        """Get rate limit for API"""
        for category in [cls.SENTIMENT_APIS, cls.NOTIFICATION_APIS]:
            if api_name in category:
                return category[api_name].get('rate_limit')
        return None


# Export commonly used configurations
BINANCE_ENDPOINTS = APIConfig.BINANCE_ENDPOINTS
SENTIMENT_APIS = APIConfig.SENTIMENT_APIS
SYMBOL_MAPPINGS = APIConfig.SYMBOL_MAPPINGS