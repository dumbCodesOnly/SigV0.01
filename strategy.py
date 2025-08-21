"""
Trading Strategy Module
Implements technical analysis and trading logic
"""

import logging
import pandas as pd
# Try to import pandas_ta, fall back to manual calculations if not available
try:
    import pandas_ta as ta
    PANDAS_TA_AVAILABLE = True
except ImportError:
    PANDAS_TA_AVAILABLE = False
    ta = None
import numpy as np
from typing import Dict, Any, Optional, Tuple

class TradingStrategy:
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.logger = logging.getLogger(__name__)
        
        # Strategy parameters from config
        self.ema_fast = config.get('indicators', {}).get('ema_fast', 50)
        self.ema_slow = config.get('indicators', {}).get('ema_slow', 200)
        self.rsi_period = config.get('indicators', {}).get('rsi_period', 14)
        self.atr_period = config.get('indicators', {}).get('atr_period', 14)
        self.bb_period = config.get('indicators', {}).get('bb_period', 20)
        self.bb_std = config.get('indicators', {}).get('bb_std', 2.0)
        
        # Signal thresholds
        self.rsi_long_threshold = config.get('signals', {}).get('rsi_long_threshold', 50)
        self.rsi_short_threshold = config.get('signals', {}).get('rsi_short_threshold', 50)
        
    def calculate_indicators(self, df: pd.DataFrame) -> pd.DataFrame:
        """Calculate all technical indicators"""
        try:
            df_copy = df.copy()
            
            # EMAs
            df_copy['ema_fast'] = ta.ema(df_copy['close'], length=self.ema_fast)
            df_copy['ema_slow'] = ta.ema(df_copy['close'], length=self.ema_slow)
            
            # RSI
            df_copy['rsi'] = ta.rsi(df_copy['close'], length=self.rsi_period)
            
            # ATR
            df_copy['atr'] = ta.atr(df_copy['high'], df_copy['low'], df_copy['close'], length=self.atr_period)
            
            # Bollinger Bands
            bb = ta.bbands(df_copy['close'], length=self.bb_period, std=self.bb_std)
            if bb is not None:
                df_copy['bb_upper'] = bb[f'BBU_{self.bb_period}_{self.bb_std}']
                df_copy['bb_middle'] = bb[f'BBM_{self.bb_period}_{self.bb_std}']
                df_copy['bb_lower'] = bb[f'BBL_{self.bb_period}_{self.bb_std}']
                df_copy['bb_width'] = (df_copy['bb_upper'] - df_copy['bb_lower']) / df_copy['bb_middle'] * 100
            
            # Additional indicators
            df_copy['volume_sma'] = ta.sma(df_copy['volume'], length=20)
            df_copy['price_change'] = df_copy['close'].pct_change()
            
            # Trend direction
            df_copy['trend'] = np.where(df_copy['ema_fast'] > df_copy['ema_slow'], 1, -1)
            
            # Support and resistance levels
            df_copy['swing_high'] = self._identify_swing_highs(df_copy['high'])
            df_copy['swing_low'] = self._identify_swing_lows(df_copy['low'])
            
            self.logger.debug(f"Calculated indicators for {len(df_copy)} candles")
            return df_copy
            
        except Exception as e:
            self.logger.error(f"Error calculating indicators: {e}")
            return df
    
    def _identify_swing_highs(self, high_series: pd.Series, window: int = 5) -> pd.Series:
        """Identify swing highs"""
        try:
            swing_highs = pd.Series(index=high_series.index, dtype=float)
            
            for i in range(window, len(high_series) - window):
                if high_series.iloc[i] == high_series.iloc[i-window:i+window+1].max():
                    swing_highs.iloc[i] = high_series.iloc[i]
            
            return swing_highs
        except Exception:
            return pd.Series(index=high_series.index, dtype=float)
    
    def _identify_swing_lows(self, low_series: pd.Series, window: int = 5) -> pd.Series:
        """Identify swing lows"""
        try:
            swing_lows = pd.Series(index=low_series.index, dtype=float)
            
            for i in range(window, len(low_series) - window):
                if low_series.iloc[i] == low_series.iloc[i-window:i+window+1].min():
                    swing_lows.iloc[i] = low_series.iloc[i]
            
            return swing_lows
        except Exception:
            return pd.Series(index=low_series.index, dtype=float)
    
    def detect_bollinger_squeeze(self, df: pd.DataFrame) -> Tuple[bool, Optional[str]]:
        """
        Detect Bollinger Band squeeze and breakout
        Returns (is_squeezed, breakout_direction)
        """
        try:
            if len(df) < 20:
                return False, None
            
            # Current values
            current_bb_width = df['bb_width'].iloc[-1]
            recent_bb_width = df['bb_width'].iloc[-20:].mean()
            
            # Squeeze detection (current width < average width)
            is_squeezed = current_bb_width < (recent_bb_width * 0.8)
            
            if not is_squeezed:
                return False, None
            
            # Breakout detection
            current_close = df['close'].iloc[-1]
            bb_upper = df['bb_upper'].iloc[-1]
            bb_lower = df['bb_lower'].iloc[-1]
            
            # Check for breakout
            if current_close > bb_upper:
                return True, 'up'
            elif current_close < bb_lower:
                return True, 'down'
            
            return True, None
            
        except Exception as e:
            self.logger.error(f"Error detecting BB squeeze: {e}")
            return False, None
    
    def detect_pullback_setup(self, df: pd.DataFrame) -> Dict[str, Any]:
        """
        Detect pullback and breakout setups
        """
        try:
            if len(df) < max(self.ema_slow, 50):
                return {'valid': False, 'reason': 'Insufficient data'}
            
            # Current values
            current = df.iloc[-1]
            previous = df.iloc[-2]
            
            # Check if we have valid indicator values
            if pd.isna([current['ema_fast'], current['ema_slow'], current['rsi'], current['atr']]).any():
                return {'valid': False, 'reason': 'Invalid indicator values'}
            
            setup = {
                'valid': False,
                'direction': None,
                'strength': 0,
                'conditions': []
            }
            
            # Trend filter
            trend_up = current['ema_fast'] > current['ema_slow']
            trend_down = current['ema_fast'] < current['ema_slow']
            
            # RSI conditions
            rsi_bullish = current['rsi'] > self.rsi_long_threshold
            rsi_bearish = current['rsi'] < self.rsi_short_threshold
            
            # Bollinger Band analysis
            bb_squeezed, bb_breakout = self.detect_bollinger_squeeze(df)
            
            # Volume confirmation
            volume_above_average = current['volume'] > current['volume_sma'] if not pd.isna(current['volume_sma']) else True
            
            # Long setup conditions
            if trend_up and rsi_bullish:
                setup['direction'] = 'LONG'
                setup['conditions'].append('EMA50 > EMA200')
                setup['conditions'].append('RSI > 50')
                setup['strength'] += 2
                
                if bb_breakout == 'up':
                    setup['conditions'].append('BB Breakout Up')
                    setup['strength'] += 2
                elif bb_squeezed:
                    setup['conditions'].append('BB Squeeze')
                    setup['strength'] += 1
                
                if volume_above_average:
                    setup['conditions'].append('Volume Above Average')
                    setup['strength'] += 1
                
                # Check for recent pullback
                recent_lows = df['low'].iloc[-10:].min()
                if current['close'] > recent_lows * 1.02:  # 2% above recent low
                    setup['conditions'].append('Above Recent Low')
                    setup['strength'] += 1
            
            # Short setup conditions
            elif trend_down and rsi_bearish:
                setup['direction'] = 'SHORT'
                setup['conditions'].append('EMA50 < EMA200')
                setup['conditions'].append('RSI < 50')
                setup['strength'] += 2
                
                if bb_breakout == 'down':
                    setup['conditions'].append('BB Breakout Down')
                    setup['strength'] += 2
                elif bb_squeezed:
                    setup['conditions'].append('BB Squeeze')
                    setup['strength'] += 1
                
                if volume_above_average:
                    setup['conditions'].append('Volume Above Average')
                    setup['strength'] += 1
                
                # Check for recent rejection
                recent_highs = df['high'].iloc[-10:].max()
                if current['close'] < recent_highs * 0.98:  # 2% below recent high
                    setup['conditions'].append('Below Recent High')
                    setup['strength'] += 1
            
            # Validate setup
            if setup['direction'] and setup['strength'] >= 3:
                setup['valid'] = True
                setup['confidence'] = min(setup['strength'] / 6.0, 1.0)  # Normalize to 0-1
            
            return setup
            
        except Exception as e:
            self.logger.error(f"Error detecting pullback setup: {e}")
            return {'valid': False, 'reason': f'Error: {e}'}
    
    def calculate_position_size(self, account_balance: float, risk_percent: float, 
                               entry_price: float, stop_loss: float) -> float:
        """Calculate position size based on risk management"""
        try:
            risk_amount = account_balance * (risk_percent / 100)
            price_diff = abs(entry_price - stop_loss)
            
            if price_diff == 0:
                return 0
            
            position_size = risk_amount / price_diff
            return position_size
            
        except Exception as e:
            self.logger.error(f"Error calculating position size: {e}")
            return 0
    
    def get_support_resistance_levels(self, df: pd.DataFrame) -> Dict[str, float]:
        """Get key support and resistance levels"""
        try:
            levels = {}
            
            # Recent swing highs and lows
            swing_highs = df['swing_high'].dropna().tail(5)
            swing_lows = df['swing_low'].dropna().tail(5)
            
            if not swing_highs.empty:
                levels['resistance'] = swing_highs.max()
            
            if not swing_lows.empty:
                levels['support'] = swing_lows.min()
            
            # Bollinger Bands as dynamic S/R
            if 'bb_upper' in df.columns and 'bb_lower' in df.columns:
                levels['bb_resistance'] = df['bb_upper'].iloc[-1]
                levels['bb_support'] = df['bb_lower'].iloc[-1]
            
            # EMA levels as dynamic S/R
            levels['ema_fast'] = df['ema_fast'].iloc[-1]
            levels['ema_slow'] = df['ema_slow'].iloc[-1]
            
            return levels
            
        except Exception as e:
            self.logger.error(f"Error getting S/R levels: {e}")
            return {}
