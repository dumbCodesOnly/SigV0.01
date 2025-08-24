"""
Data Collector Module
Handles data ingestion from Binance API and other sources
"""

import asyncio
import logging
import aiohttp
import pandas as pd
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List

class DataCollector:
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.logger = logging.getLogger(__name__)
        # Multiple Binance API endpoints for fallback
        self.binance_endpoints = [
            "https://api.binance.com/api/v3",           # Primary endpoint
            "https://data-api.binance.vision/api/v3",   # Market data only endpoint
            "https://api1.binance.com/api/v3",          # Alternative 1
            "https://api2.binance.com/api/v3",          # Alternative 2
            "https://api3.binance.com/api/v3",          # Alternative 3
            "https://api4.binance.com/api/v3"           # Alternative 4
        ]
        self.current_endpoint_index = 0
        self.session = None
        
    async def _get_session(self) -> aiohttp.ClientSession:
        """Get or create aiohttp session"""
        if self.session is None or self.session.closed:
            self.session = aiohttp.ClientSession()
        return self.session
    
    async def close(self):
        """Close the session"""
        if self.session and not self.session.closed:
            await self.session.close()
    
    def _timeframe_to_interval(self, timeframe: str) -> str:
        """Convert timeframe to Binance interval format"""
        mapping = {
            '1m': '1m',
            '5m': '5m',
            '15m': '15m',
            '30m': '30m',
            '1h': '1h',
            '4h': '4h',
            '1d': '1d'
        }
        return mapping.get(timeframe, '15m')
    
    def _timeframe_to_minutes(self, timeframe: str) -> int:
        """Convert timeframe to minutes"""
        mapping = {
            '1m': 1,
            '5m': 5,
            '15m': 15,
            '30m': 30,
            '1h': 60,
            '4h': 240,
            '1d': 1440
        }
        return mapping.get(timeframe, 15)
    
    async def get_ohlcv_data(self, symbol: str, timeframe: str, limit: int = 200) -> Optional[pd.DataFrame]:
        """
        Get OHLCV data from Binance API with multiple endpoint fallbacks, then CoinGecko
        Returns DataFrame with columns: timestamp, open, high, low, close, volume
        """
        # Try all Binance endpoints
        binance_data = await self._get_binance_data_with_fallback(symbol, timeframe, limit)
        if binance_data is not None:
            return binance_data
        
        # Final fallback to CoinGecko
        self.logger.info("All Binance endpoints unavailable, using CoinGecko fallback")
        return await self._get_coingecko_data(symbol, timeframe, limit)
    
    async def _get_binance_data_with_fallback(self, symbol: str, timeframe: str, limit: int) -> Optional[pd.DataFrame]:
        """Try all Binance endpoints with fallback"""
        for i, base_url in enumerate(self.binance_endpoints):
            try:
                self.logger.debug(f"Trying Binance endpoint {i+1}/{len(self.binance_endpoints)}: {base_url}")
                data = await self._get_binance_data_from_endpoint(symbol, timeframe, limit, base_url)
                if data is not None:
                    if i != self.current_endpoint_index:
                        self.logger.info(f"Switched to Binance endpoint: {base_url}")
                        self.current_endpoint_index = i
                    return data
            except Exception as e:
                self.logger.warning(f"Binance endpoint {base_url} failed: {e}")
                continue
        
        self.logger.error("All Binance endpoints failed")
        return None

    async def _get_binance_data_from_endpoint(self, symbol: str, timeframe: str, limit: int, base_url: str) -> Optional[pd.DataFrame]:
        """Get data from specific Binance API endpoint"""
        try:
            session = await self._get_session()
            interval = self._timeframe_to_interval(timeframe)
            
            params = {
                'symbol': symbol.upper(),
                'interval': interval,
                'limit': limit
            }
            
            url = f"{base_url}/klines"
            
            async with session.get(url, params=params) as response:
                if response.status == 200:
                    data = await response.json()
                    
                    # Convert to DataFrame
                    df = pd.DataFrame(data, columns=[
                        'timestamp', 'open', 'high', 'low', 'close', 'volume',
                        'close_time', 'quote_asset_volume', 'number_of_trades',
                        'taker_buy_base_asset_volume', 'taker_buy_quote_asset_volume', 'ignore'
                    ])
                    
                    # Keep only required columns and convert types
                    df = df[['timestamp', 'open', 'high', 'low', 'close', 'volume']].copy()
                    
                    # Convert timestamp to datetime
                    df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
                    
                    # Convert price and volume columns to float
                    for col in ['open', 'high', 'low', 'close', 'volume']:
                        df[col] = df[col].astype(float)
                    
                    # Set timestamp as index
                    df.set_index('timestamp', inplace=True)
                    
                    self.logger.info(f"Retrieved {len(df)} candles for {symbol} {timeframe} from Binance")
                    return df
                else:
                    self.logger.warning(f"Binance API error: {response.status}")
                    return None
                    
        except Exception as e:
            self.logger.warning(f"Binance API unavailable: {e}")
            return None
    
    async def _get_coingecko_data(self, symbol: str, timeframe: str, limit: int) -> Optional[pd.DataFrame]:
        """Get data from CoinGecko API as fallback"""
        try:
            session = await self._get_session()
            
            # Convert symbol to CoinGecko format
            coin_id = self._symbol_to_coingecko_id(symbol)
            if not coin_id:
                self.logger.error(f"Unsupported symbol for CoinGecko: {symbol}")
                return None
            
            # Calculate days based on timeframe and limit
            timeframe_minutes = self._timeframe_to_minutes(timeframe)
            days = max(1, min(365, (limit * timeframe_minutes) // (24 * 60)))
            
            url = f"https://api.coingecko.com/api/v3/coins/{coin_id}/ohlc"
            params = {
                'vs_currency': 'usd',
                'days': days
            }
            
            async with session.get(url, params=params) as response:
                if response.status == 200:
                    data = await response.json()
                    
                    if not data:
                        self.logger.error("No data received from CoinGecko")
                        return None
                    
                    # Convert to DataFrame
                    df = pd.DataFrame(data, columns=['timestamp', 'open', 'high', 'low', 'close'])
                    
                    # Convert timestamp to datetime
                    df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
                    
                    # Add volume column (placeholder since CoinGecko OHLC doesn't include volume)
                    df['volume'] = 1000000.0  # Placeholder volume
                    
                    # Convert price columns to float
                    for col in ['open', 'high', 'low', 'close', 'volume']:
                        df[col] = df[col].astype(float)
                    
                    # Set timestamp as index
                    df.set_index('timestamp', inplace=True)
                    
                    # Resample to target timeframe if needed
                    df = self._resample_coingecko_data(df, timeframe, limit)
                    
                    self.logger.info(f"Retrieved {len(df)} candles for {symbol} {timeframe} from CoinGecko")
                    return df
                else:
                    self.logger.error(f"CoinGecko API error: {response.status}")
                    return None
                    
        except Exception as e:
            self.logger.error(f"Error fetching CoinGecko data: {e}")
            return None
    
    def _symbol_to_coingecko_id(self, symbol: str) -> Optional[str]:
        """Convert trading symbol to CoinGecko coin ID"""
        symbol_mapping = {
            'BTCUSDT': 'bitcoin',
            'ETHUSDT': 'ethereum',
            'BNBUSDT': 'binancecoin',
            'ADAUSDT': 'cardano',
            'SOLUSDT': 'solana',
            'XRPUSDT': 'ripple',
            'DOTUSDT': 'polkadot',
            'DOGEUSDT': 'dogecoin',
            'AVAXUSDT': 'avalanche-2',
            'MATICUSDT': 'matic-network'
        }
        return symbol_mapping.get(symbol.upper())
    
    def _resample_coingecko_data(self, df: pd.DataFrame, target_timeframe: str, limit: int) -> pd.DataFrame:
        """Resample CoinGecko data to target timeframe"""
        try:
            timeframe_mapping = {
                '1m': '1T', '5m': '5T', '15m': '15T', '30m': '30T',
                '1h': '1H', '4h': '4H', '1d': '1D'
            }
            
            freq = timeframe_mapping.get(target_timeframe, '15T')
            
            # Resample OHLCV data
            resampled = df.resample(freq).agg({
                'open': 'first',
                'high': 'max',
                'low': 'min',
                'close': 'last',
                'volume': 'sum'
            }).dropna()
            
            # Return latest data up to limit
            return resampled.tail(limit)
            
        except Exception as e:
            self.logger.error(f"Error resampling CoinGecko data: {e}")
            return df.tail(limit)
    
    async def get_current_price(self, symbol: str) -> Optional[float]:
        """Get current price for a symbol with endpoint fallback"""
        for base_url in self.binance_endpoints:
            try:
                session = await self._get_session()
                
                params = {'symbol': symbol.upper()}
                url = f"{base_url}/ticker/price"
                
                async with session.get(url, params=params) as response:
                    if response.status == 200:
                        data = await response.json()
                        return float(data['price'])
                    else:
                        self.logger.warning(f"Price endpoint {base_url} returned: {response.status}")
                        continue
                        
            except Exception as e:
                self.logger.warning(f"Price endpoint {base_url} failed: {e}")
                continue
                
        self.logger.error("All price endpoints failed")
        return None
    
    async def get_24h_ticker(self, symbol: str) -> Optional[Dict[str, Any]]:
        """Get 24h ticker statistics with endpoint fallback"""
        for base_url in self.binance_endpoints:
            try:
                session = await self._get_session()
                
                params = {'symbol': symbol.upper()}
                url = f"{base_url}/ticker/24hr"
                
                async with session.get(url, params=params) as response:
                    if response.status == 200:
                        data = await response.json()
                        return {
                            'symbol': data['symbol'],
                            'price_change': float(data['priceChange']),
                            'price_change_percent': float(data['priceChangePercent']),
                            'weighted_avg_price': float(data['weightedAvgPrice']),
                            'last_price': float(data['lastPrice']),
                            'volume': float(data['volume']),
                            'high_price': float(data['highPrice']),
                            'low_price': float(data['lowPrice'])
                        }
                    else:
                        self.logger.warning(f"Ticker endpoint {base_url} returned: {response.status}")
                        continue
                        
            except Exception as e:
                self.logger.warning(f"Ticker endpoint {base_url} failed: {e}")
                continue
                
        self.logger.error("All ticker endpoints failed")
        return None
    
    def validate_data(self, df: pd.DataFrame) -> bool:
        """Validate OHLCV data quality"""
        if df is None or df.empty:
            return False
        
        # Check for required columns
        required_columns = ['open', 'high', 'low', 'close', 'volume']
        if not all(col in df.columns for col in required_columns):
            self.logger.error("Missing required columns in OHLCV data")
            return False
        
        # Check for null values
        if df[required_columns].isnull().any().any():
            self.logger.warning("Found null values in OHLCV data")
            return False
        
        # Check OHLC relationships
        invalid_ohlc = (
            (df['high'] < df['low']) |
            (df['high'] < df['open']) |
            (df['high'] < df['close']) |
            (df['low'] > df['open']) |
            (df['low'] > df['close'])
        )
        
        if invalid_ohlc.any():
            self.logger.warning("Found invalid OHLC relationships")
            return False
        
        # Check for negative values
        if (df[required_columns] < 0).any().any():
            self.logger.warning("Found negative values in OHLCV data")
            return False
        
        return True
    
    def resample_data(self, df: pd.DataFrame, target_timeframe: str) -> pd.DataFrame:
        """Resample data to different timeframe"""
        try:
            timeframe_mapping = {
                '1m': '1T',
                '5m': '5T',
                '15m': '15T',
                '30m': '30T',
                '1h': '1H',
                '4h': '4H',
                '1d': '1D'
            }
            
            freq = timeframe_mapping.get(target_timeframe)
            if not freq:
                raise ValueError(f"Unsupported timeframe: {target_timeframe}")
            
            # Resample OHLCV data
            resampled = df.resample(freq).agg({
                'open': 'first',
                'high': 'max',
                'low': 'min',
                'close': 'last',
                'volume': 'sum'
            }).dropna()
            
            return resampled
            
        except Exception as e:
            self.logger.error(f"Error resampling data: {e}")
            return df
