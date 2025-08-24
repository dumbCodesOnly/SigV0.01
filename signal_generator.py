"""
Signal Generator Module
Combines technical analysis and sentiment to generate trading signals
"""

import logging
import pandas as pd
import numpy as np
from datetime import datetime
from typing import Dict, Any, Optional, List

class SignalGenerator:
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.logger = logging.getLogger(__name__)
        
        # Risk management parameters
        self.risk_percent = config.get('risk_management', {}).get('risk_per_trade', 2.0)
        self.atr_multiplier_sl = config.get('risk_management', {}).get('atr_multiplier_sl', 2.0)
        self.take_profit_ratios = config.get('risk_management', {}).get('take_profit_ratios', [1.0, 1.5, 2.5])
        self.breakeven_after_tp = config.get('risk_management', {}).get('breakeven_after_tp', 1)
        self.trailing_atr_multiplier = config.get('risk_management', {}).get('trailing_atr_multiplier', 2.5)
        
        # Signal validation parameters
        self.min_confidence = config.get('signals', {}).get('min_confidence', 0.6)
        self.sentiment_threshold = config.get('sentiment', {}).get('threshold', 0.2)
    
    def generate_signal(self, df: pd.DataFrame, sentiment_score: float, symbol: str = None, timeframe: str = None) -> Optional[Dict[str, Any]]:
        """
        Generate trading signal based on technical analysis and sentiment
        """
        try:
            if len(df) < 200:  # Need sufficient data for indicators
                self.logger.warning("Insufficient data for signal generation")
                return None
            
            # Get the latest data point
            current = df.iloc[-1]
            
            # Use provided symbol/timeframe or fall back to config
            if symbol is None:
                symbol = self.config['trading'].get('symbol', self.config['trading']['symbols'][0])
            if timeframe is None:
                timeframe = self.config['trading'].get('timeframe', self.config['trading']['timeframes'][0])
            
            # Import strategy here to avoid circular imports
            from strategy import TradingStrategy
            strategy = TradingStrategy(self.config)
            
            # Detect setup
            setup = strategy.detect_pullback_setup(df)
            
            if not setup['valid']:
                self.logger.debug(f"No valid setup detected: {setup.get('reason', 'Unknown')}")
                return None
            
            direction = setup['direction']
            
            # Validate sentiment alignment
            if not self._validate_sentiment_alignment(sentiment_score, direction):
                self.logger.info(f"Sentiment {sentiment_score:.2f} doesn't align with {direction} signal")
                return None
            
            # Calculate signal details
            signal = self._calculate_signal_details(df, setup, sentiment_score, symbol, timeframe)
            
            if signal and signal['confidence'] >= self.min_confidence:
                self.logger.info(f"Generated {direction} signal with {signal['confidence']:.1%} confidence")
                return signal
            else:
                self.logger.debug(f"Signal confidence too low: {signal['confidence']:.1%}" if signal else "Failed to calculate signal")
                return None
                
        except Exception as e:
            self.logger.error(f"Error generating signal: {e}")
            return None
    
    def _validate_sentiment_alignment(self, sentiment_score: float, direction: str) -> bool:
        """Validate sentiment alignment with signal direction"""
        # If sentiment is neutral (0.0), allow signals to pass through
        # This handles cases where sentiment data is unavailable
        if abs(sentiment_score) < 0.01:  # Essentially neutral
            self.logger.debug(f"Neutral sentiment detected, allowing {direction} signal to proceed")
            return True
            
        if direction == 'LONG':
            return sentiment_score >= self.sentiment_threshold
        elif direction == 'SHORT':
            return sentiment_score <= -self.sentiment_threshold
        return False
    
    def _calculate_signal_details(self, df: pd.DataFrame, setup: Dict[str, Any], 
                                 sentiment_score: float, symbol: str, timeframe: str) -> Optional[Dict[str, Any]]:
        """Calculate complete signal details including entry, exit, and risk management"""
        try:
            current = df.iloc[-1]
            direction = setup['direction']
            
            # Entry price (current close)
            entry_price = float(current['close'])
            
            # Calculate stop loss
            atr = float(current['atr'])
            stop_loss = self._calculate_stop_loss(df, direction, entry_price, atr)
            
            # Calculate position size based on risk
            account_balance = self.config.get('risk_management', {}).get('account_balance', 10000)
            position_size = self._calculate_position_size(account_balance, entry_price, stop_loss)
            
            # Calculate take profit levels
            take_profits = self._calculate_take_profits(entry_price, stop_loss, direction)
            
            # Calculate confidence score
            confidence = self._calculate_confidence(setup, sentiment_score, df)
            
            # Collect reasons
            reasons = setup['conditions'].copy()
            reasons.append(self._get_sentiment_description(sentiment_score))
            
            # Create signal dictionary
            signal = {
                'timestamp': datetime.now().isoformat(),
                'symbol': symbol,
                'timeframe': timeframe,
                'direction': direction,
                'entry_price': entry_price,
                'stop_loss': stop_loss,
                'take_profits': take_profits,
                'position_size': position_size,
                'risk_amount': abs(entry_price - stop_loss) * position_size,
                'risk_percent': self.risk_percent,
                'confidence': confidence,
                'sentiment_score': sentiment_score,
                'reasons': reasons,
                'atr': atr,
                'breakeven_after_tp': self.breakeven_after_tp,
                'trailing_stop': {
                    'enabled': True,
                    'atr_multiplier': self.trailing_atr_multiplier,
                    'initial_stop': stop_loss
                },
                'metadata': {
                    'ema_fast': float(current['ema_fast']),
                    'ema_slow': float(current['ema_slow']),
                    'rsi': float(current['rsi']),
                    'bb_width': float(current.get('bb_width', 0)),
                    'volume_ratio': float(current['volume'] / current.get('volume_sma', current['volume']))
                }
            }
            
            return signal
            
        except Exception as e:
            self.logger.error(f"Error calculating signal details: {e}")
            return None
    
    def _calculate_stop_loss(self, df: pd.DataFrame, direction: str, entry_price: float, atr: float) -> float:
        """Calculate stop loss based on ATR and swing levels"""
        try:
            # ATR-based stop loss
            atr_stop = atr * self.atr_multiplier_sl
            
            if direction == 'LONG':
                # For long positions, stop below entry
                atr_sl = entry_price - atr_stop
                
                # Check for recent swing low
                swing_lows = df['swing_low'].dropna().tail(5)
                if not swing_lows.empty:
                    recent_swing_low = swing_lows.min()
                    # Use the lower of ATR stop or swing low (with buffer)
                    swing_sl = recent_swing_low * 0.998  # 0.2% buffer
                    stop_loss = min(atr_sl, swing_sl)
                else:
                    stop_loss = atr_sl
            
            else:  # SHORT
                # For short positions, stop above entry
                atr_sl = entry_price + atr_stop
                
                # Check for recent swing high
                swing_highs = df['swing_high'].dropna().tail(5)
                if not swing_highs.empty:
                    recent_swing_high = swing_highs.max()
                    # Use the higher of ATR stop or swing high (with buffer)
                    swing_sl = recent_swing_high * 1.002  # 0.2% buffer
                    stop_loss = max(atr_sl, swing_sl)
                else:
                    stop_loss = atr_sl
            
            return float(stop_loss)
            
        except Exception as e:
            self.logger.error(f"Error calculating stop loss: {e}")
            # Fallback to simple ATR stop
            if direction == 'LONG':
                return entry_price - (atr * self.atr_multiplier_sl)
            else:
                return entry_price + (atr * self.atr_multiplier_sl)
    
    def _calculate_take_profits(self, entry_price: float, stop_loss: float, direction: str) -> List[float]:
        """Calculate take profit levels based on R multiples"""
        try:
            risk_amount = abs(entry_price - stop_loss)
            take_profits = []
            
            for ratio in self.take_profit_ratios:
                if direction == 'LONG':
                    tp = entry_price + (risk_amount * ratio)
                else:  # SHORT
                    tp = entry_price - (risk_amount * ratio)
                
                take_profits.append(float(tp))
            
            return take_profits
            
        except Exception as e:
            self.logger.error(f"Error calculating take profits: {e}")
            return []
    
    def _calculate_position_size(self, account_balance: float, entry_price: float, stop_loss: float) -> float:
        """Calculate position size based on risk management"""
        try:
            risk_amount = account_balance * (self.risk_percent / 100)
            price_diff = abs(entry_price - stop_loss)
            
            if price_diff == 0:
                return 0
            
            # For crypto, this would be the amount in base currency
            position_size = risk_amount / price_diff
            
            # Limit position size to reasonable bounds
            max_position_value = account_balance * 0.1  # Max 10% of account per trade
            max_position_size = max_position_value / entry_price
            
            return min(position_size, max_position_size)
            
        except Exception as e:
            self.logger.error(f"Error calculating position size: {e}")
            return 0
    
    def _calculate_confidence(self, setup: Dict[str, Any], sentiment_score: float, df: pd.DataFrame) -> float:
        """Calculate overall signal confidence"""
        try:
            # Base confidence from technical setup
            base_confidence = setup.get('confidence', 0.5)
            
            # Sentiment boost/penalty
            sentiment_boost = 0
            if abs(sentiment_score) > 0.5:
                sentiment_boost = 0.2
            elif abs(sentiment_score) > 0.3:
                sentiment_boost = 0.1
            
            # Volume confirmation
            current = df.iloc[-1]
            volume_boost = 0
            if not pd.isna(current.get('volume_sma')):
                if current['volume'] > current['volume_sma'] * 1.5:
                    volume_boost = 0.1
            
            # Trend strength
            trend_boost = 0
            ema_diff = abs(current['ema_fast'] - current['ema_slow']) / current['ema_slow']
            if ema_diff > 0.02:  # 2% difference
                trend_boost = 0.1
            
            # RSI position
            rsi_boost = 0
            rsi = current['rsi']
            if setup['direction'] == 'LONG' and 50 < rsi < 70:
                rsi_boost = 0.05
            elif setup['direction'] == 'SHORT' and 30 < rsi < 50:
                rsi_boost = 0.05
            
            # Combine all factors
            total_confidence = base_confidence + sentiment_boost + volume_boost + trend_boost + rsi_boost
            
            # Cap at 1.0
            return min(1.0, total_confidence)
            
        except Exception as e:
            self.logger.error(f"Error calculating confidence: {e}")
            return 0.5
    
    def _get_sentiment_description(self, sentiment_score: float) -> str:
        """Get human-readable sentiment description"""
        if sentiment_score >= 0.5:
            return "Very Positive Sentiment"
        elif sentiment_score >= 0.2:
            return "Positive Sentiment"
        elif sentiment_score > -0.2:
            return "Neutral Sentiment"
        elif sentiment_score > -0.5:
            return "Negative Sentiment"
        else:
            return "Very Negative Sentiment"
    
    def format_signal_json(self, signal: Dict[str, Any]) -> str:
        """Format signal as JSON for logging/backtesting"""
        try:
            import json
            return json.dumps(signal, indent=2, default=str)
        except Exception as e:
            self.logger.error(f"Error formatting signal JSON: {e}")
            return str(signal)
    
    def format_signal_telegram(self, signal: Dict[str, Any]) -> str:
        """Format signal for Telegram message"""
        try:
            direction_emoji = "🟢" if signal['direction'] == 'LONG' else "🔴"
            confidence_bar = "█" * int(signal['confidence'] * 10)
            
            message = f"""
{direction_emoji} <b>{signal['symbol']} · {signal['direction']} · {signal['timeframe']}</b>

📊 <b>Entry:</b> <code>{signal['entry_price']:,.4f}</code>
🛑 <b>Stop Loss:</b> <code>{signal['stop_loss']:,.4f}</code>
🎯 <b>Take Profits:</b>
   TP1: <code>{signal['take_profits'][0]:,.4f}</code>
   TP2: <code>{signal['take_profits'][1]:,.4f}</code> 
   TP3: <code>{signal['take_profits'][2]:,.4f}</code>

⚙️ <b>Risk Management:</b>
• Position Size: <code>{signal['position_size']:,.2f}</code>
• Risk Amount: <code>${signal['risk_amount']:,.2f}</code> ({signal['risk_percent']}%)
• BE after: TP{signal['breakeven_after_tp']}
• Trail: ATR × {signal['trailing_stop']['atr_multiplier']}

📈 <b>Confidence:</b> {signal['confidence']:.0%} {confidence_bar}
💭 <b>Sentiment:</b> {signal['sentiment_score']:+.2f}

<b>Analysis:</b>
{' • '.join(signal['reasons'][:4])}

<i>Generated at {datetime.fromisoformat(signal['timestamp']).strftime('%H:%M:%S UTC')}</i>
            """.strip()
            
            return message
            
        except Exception as e:
            self.logger.error(f"Error formatting Telegram message: {e}")
            return f"Signal Error: {e}"
