"""
Backtesting Module
Tests the trading strategy on historical data
"""

import logging
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional, Tuple
import asyncio

from data_collector import DataCollector
from strategy import TradingStrategy
from sentiment_analyzer import SentimentAnalyzer
from signal_generator import SignalGenerator

class Backtester:
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.logger = logging.getLogger(__name__)
        
        # Initialize components
        self.data_collector = DataCollector(config)
        self.strategy = TradingStrategy(config)
        self.sentiment_analyzer = SentimentAnalyzer(config)
        self.signal_generator = SignalGenerator(config)
        
        # Backtest parameters
        self.initial_balance = config.get('backtesting', {}).get('initial_balance', 10000)
        self.commission_rate = config.get('backtesting', {}).get('commission_rate', 0.001)  # 0.1%
        
        # Results storage
        self.trades = []
        self.equity_curve = []
        self.daily_returns = []
    
    async def run_backtest(self, start_date: str, end_date: str, symbol: str = None, timeframe: str = None) -> Dict[str, Any]:
        """
        Run backtest on historical data
        """
        try:
            symbol = symbol or self.config['trading']['symbol']
            timeframe = timeframe or self.config['trading']['timeframe']
            
            self.logger.info(f"Starting backtest for {symbol} from {start_date} to {end_date}")
            
            # Get historical data
            df = await self._get_historical_data(symbol, timeframe, start_date, end_date)
            
            if df is None or df.empty:
                self.logger.error("No historical data available")
                return {'error': 'No data available'}
            
            self.logger.info(f"Loaded {len(df)} historical candles")
            
            # Run backtest
            results = await self._execute_backtest(df, symbol, timeframe)
            
            return results
            
        except Exception as e:
            self.logger.error(f"Error running backtest: {e}")
            return {'error': str(e)}
    
    async def _get_historical_data(self, symbol: str, timeframe: str, start_date: str, end_date: str) -> Optional[pd.DataFrame]:
        """Get historical OHLCV data for backtesting"""
        try:
            # For simplicity, we'll use the current data collection method
            # In a real implementation, you might want to use a dedicated historical data source
            df = await self.data_collector.get_ohlcv_data(symbol, timeframe, limit=1000)
            
            if df is None:
                return None
            
            # Filter by date range if needed
            start_dt = pd.to_datetime(start_date)
            end_dt = pd.to_datetime(end_date)
            
            df = df[(df.index >= start_dt) & (df.index <= end_dt)]
            
            return df
            
        except Exception as e:
            self.logger.error(f"Error getting historical data: {e}")
            return None
    
    async def _execute_backtest(self, df: pd.DataFrame, symbol: str, timeframe: str) -> Dict[str, Any]:
        """Execute the backtest logic"""
        try:
            # Calculate indicators for entire dataset
            df_with_indicators = self.strategy.calculate_indicators(df)
            
            # Initialize backtest state
            current_balance = self.initial_balance
            current_position = None
            equity = [current_balance]
            dates = [df.index[0]]
            
            # Minimum lookback period for indicators
            lookback = max(self.strategy.ema_slow, 50)
            
            # Simulate trading day by day
            for i in range(lookback, len(df_with_indicators)):
                current_date = df_with_indicators.index[i]
                
                # Get data up to current point (avoid lookahead bias)
                historical_data = df_with_indicators.iloc[:i+1]
                
                # Check for exit conditions first
                if current_position:
                    exit_result = self._check_exit_conditions(
                        current_position, 
                        historical_data.iloc[-1], 
                        current_date
                    )
                    
                    if exit_result:
                        current_balance = self._execute_exit(
                            current_position, 
                            exit_result, 
                            current_balance
                        )
                        current_position = None
                
                # Look for new entry signals if not in position
                if not current_position:
                    # Get sentiment (simplified for backtesting)
                    sentiment_score = 0.0  # Neutral sentiment for backtesting
                    
                    # Generate signal
                    signal = self.signal_generator.generate_signal(historical_data, sentiment_score)
                    
                    if signal:
                        current_position = self._execute_entry(signal, current_balance, current_date)
                
                # Update equity curve
                if current_position:
                    current_price = historical_data.iloc[-1]['close']
                    unrealized_pnl = self._calculate_unrealized_pnl(current_position, current_price)
                    equity.append(current_balance + unrealized_pnl)
                else:
                    equity.append(current_balance)
                
                dates.append(current_date)
            
            # Close any remaining position
            if current_position:
                final_price = df_with_indicators.iloc[-1]['close']
                exit_result = {
                    'price': final_price,
                    'reason': 'End of backtest',
                    'date': df_with_indicators.index[-1]
                }
                current_balance = self._execute_exit(current_position, exit_result, current_balance)
            
            # Calculate results
            results = self._calculate_backtest_results(current_balance, equity, dates)
            
            return results
            
        except Exception as e:
            self.logger.error(f"Error executing backtest: {e}")
            return {'error': str(e)}
    
    def _execute_entry(self, signal: Dict[str, Any], balance: float, date: pd.Timestamp) -> Dict[str, Any]:
        """Execute trade entry"""
        try:
            entry_price = signal['entry_price']
            position_size = min(signal['position_size'], balance * 0.95 / entry_price)  # Max 95% of balance
            
            # Account for commission
            commission = position_size * entry_price * self.commission_rate
            
            position = {
                'symbol': signal['symbol'],
                'direction': signal['direction'],
                'entry_price': entry_price,
                'position_size': position_size,
                'stop_loss': signal['stop_loss'],
                'take_profits': signal['take_profits'],
                'entry_date': date,
                'commission_paid': commission,
                'trailing_stop': signal.get('trailing_stop', {}).get('initial_stop'),
                'breakeven_triggered': False,
                'tp_levels_hit': 0
            }
            
            self.logger.debug(f"Entered {signal['direction']} position at {entry_price}")
            return position
            
        except Exception as e:
            self.logger.error(f"Error executing entry: {e}")
            return None
    
    def _check_exit_conditions(self, position: Dict[str, Any], current_candle: pd.Series, date: pd.Timestamp) -> Optional[Dict[str, Any]]:
        """Check if position should be exited"""
        try:
            current_price = current_candle['close']
            high_price = current_candle['high']
            low_price = current_candle['low']
            
            direction = position['direction']
            
            # Check stop loss
            if direction == 'LONG':
                if low_price <= position['stop_loss']:
                    return {
                        'price': position['stop_loss'],
                        'reason': 'Stop Loss Hit',
                        'date': date
                    }
            else:  # SHORT
                if high_price >= position['stop_loss']:
                    return {
                        'price': position['stop_loss'],
                        'reason': 'Stop Loss Hit',
                        'date': date
                    }
            
            # Check take profit levels
            for i, tp_price in enumerate(position['take_profits']):
                if position['tp_levels_hit'] <= i:
                    if direction == 'LONG':
                        if high_price >= tp_price:
                            return {
                                'price': tp_price,
                                'reason': f'Take Profit {i+1} Hit',
                                'date': date,
                                'tp_level': i+1
                            }
                    else:  # SHORT
                        if low_price <= tp_price:
                            return {
                                'price': tp_price,
                                'reason': f'Take Profit {i+1} Hit',
                                'date': date,
                                'tp_level': i+1
                            }
            
            return None
            
        except Exception as e:
            self.logger.error(f"Error checking exit conditions: {e}")
            return None
    
    def _execute_exit(self, position: Dict[str, Any], exit_result: Dict[str, Any], balance: float) -> float:
        """Execute trade exit and return new balance"""
        try:
            exit_price = exit_result['price']
            position_size = position['position_size']
            entry_price = position['entry_price']
            direction = position['direction']
            
            # Calculate P&L
            if direction == 'LONG':
                pnl = (exit_price - entry_price) * position_size
            else:  # SHORT
                pnl = (entry_price - exit_price) * position_size
            
            # Account for commission
            exit_commission = position_size * exit_price * self.commission_rate
            total_commission = position['commission_paid'] + exit_commission
            
            net_pnl = pnl - total_commission
            new_balance = balance + net_pnl
            
            # Record trade
            trade_result = {
                'symbol': position['symbol'],
                'direction': direction,
                'entry_date': position['entry_date'],
                'exit_date': exit_result['date'],
                'entry_price': entry_price,
                'exit_price': exit_price,
                'position_size': position_size,
                'gross_pnl': pnl,
                'commission': total_commission,
                'net_pnl': net_pnl,
                'return_pct': (net_pnl / (entry_price * position_size)) * 100,
                'exit_reason': exit_result['reason'],
                'duration_hours': (exit_result['date'] - position['entry_date']).total_seconds() / 3600
            }
            
            self.trades.append(trade_result)
            
            self.logger.debug(f"Exited position: {exit_result['reason']}, P&L: ${net_pnl:.2f}")
            
            return new_balance
            
        except Exception as e:
            self.logger.error(f"Error executing exit: {e}")
            return balance
    
    def _calculate_unrealized_pnl(self, position: Dict[str, Any], current_price: float) -> float:
        """Calculate unrealized P&L for open position"""
        try:
            entry_price = position['entry_price']
            position_size = position['position_size']
            direction = position['direction']
            
            if direction == 'LONG':
                return (current_price - entry_price) * position_size
            else:  # SHORT
                return (entry_price - current_price) * position_size
                
        except Exception:
            return 0.0
    
    def _calculate_backtest_results(self, final_balance: float, equity: List[float], dates: List[pd.Timestamp]) -> Dict[str, Any]:
        """Calculate comprehensive backtest results"""
        try:
            # Basic metrics
            total_return = ((final_balance - self.initial_balance) / self.initial_balance) * 100
            total_trades = len(self.trades)
            
            if total_trades == 0:
                return {
                    'summary': {
                        'initial_balance': self.initial_balance,
                        'final_balance': final_balance,
                        'total_return_pct': total_return,
                        'total_trades': 0
                    },
                    'trades': []
                }
            
            # Trade analysis
            winning_trades = [t for t in self.trades if t['net_pnl'] > 0]
            losing_trades = [t for t in self.trades if t['net_pnl'] < 0]
            
            win_rate = len(winning_trades) / total_trades * 100 if total_trades > 0 else 0
            
            avg_win = sum(t['net_pnl'] for t in winning_trades) / len(winning_trades) if winning_trades else 0
            avg_loss = sum(t['net_pnl'] for t in losing_trades) / len(losing_trades) if losing_trades else 0
            
            profit_factor = abs(avg_win * len(winning_trades) / (avg_loss * len(losing_trades))) if losing_trades else float('inf')
            
            # Equity curve analysis
            equity_series = pd.Series(equity, index=dates)
            returns = equity_series.pct_change().dropna()
            
            # Risk metrics
            max_drawdown = self._calculate_max_drawdown(equity_series)
            sharpe_ratio = self._calculate_sharpe_ratio(returns)
            
            # Duration analysis
            avg_trade_duration = sum(t['duration_hours'] for t in self.trades) / total_trades if total_trades > 0 else 0
            
            results = {
                'summary': {
                    'initial_balance': self.initial_balance,
                    'final_balance': final_balance,
                    'total_return_pct': total_return,
                    'total_trades': total_trades,
                    'winning_trades': len(winning_trades),
                    'losing_trades': len(losing_trades),
                    'win_rate_pct': win_rate,
                    'profit_factor': profit_factor,
                    'avg_win': avg_win,
                    'avg_loss': avg_loss,
                    'max_drawdown_pct': max_drawdown,
                    'sharpe_ratio': sharpe_ratio,
                    'avg_trade_duration_hours': avg_trade_duration
                },
                'trades': self.trades,
                'equity_curve': {
                    'dates': [d.isoformat() for d in dates],
                    'values': equity
                }
            }
            
            return results
            
        except Exception as e:
            self.logger.error(f"Error calculating backtest results: {e}")
            return {'error': str(e)}
    
    def _calculate_max_drawdown(self, equity_series: pd.Series) -> float:
        """Calculate maximum drawdown percentage"""
        try:
            running_max = equity_series.expanding().max()
            drawdown = (equity_series - running_max) / running_max * 100
            return abs(drawdown.min())
        except Exception:
            return 0.0
    
    def _calculate_sharpe_ratio(self, returns: pd.Series, risk_free_rate: float = 0.02) -> float:
        """Calculate Sharpe ratio"""
        try:
            if len(returns) == 0 or returns.std() == 0:
                return 0.0
            
            excess_returns = returns.mean() - risk_free_rate / 252  # Daily risk-free rate
            return excess_returns / returns.std() * np.sqrt(252)  # Annualized
        except Exception:
            return 0.0
    
    def generate_report(self, results: Dict[str, Any]) -> str:
        """Generate a formatted backtest report"""
        try:
            if 'error' in results:
                return f"Backtest Error: {results['error']}"
            
            summary = results['summary']
            
            report = f"""
BACKTEST RESULTS REPORT
======================

PERFORMANCE SUMMARY:
Initial Balance: ${summary['initial_balance']:,.2f}
Final Balance: ${summary['final_balance']:,.2f}
Total Return: {summary['total_return_pct']:+.2f}%
Max Drawdown: {summary['max_drawdown_pct']:.2f}%

TRADE STATISTICS:
Total Trades: {summary['total_trades']}
Winning Trades: {summary['winning_trades']}
Losing Trades: {summary['losing_trades']}
Win Rate: {summary['win_rate_pct']:.1f}%
Profit Factor: {summary['profit_factor']:.2f}

AVERAGE PERFORMANCE:
Average Win: ${summary['avg_win']:.2f}
Average Loss: ${summary['avg_loss']:.2f}
Average Trade Duration: {summary['avg_trade_duration_hours']:.1f} hours

RISK METRICS:
Sharpe Ratio: {summary['sharpe_ratio']:.2f}
            """.strip()
            
            return report
            
        except Exception as e:
            return f"Error generating report: {e}"

# CLI interface for standalone backtesting
async def main():
    """Main function for standalone backtesting"""
    import yaml
    import sys
    from datetime import datetime, timedelta
    
    # Load config
    try:
        with open('config.yaml', 'r') as f:
            config = yaml.safe_load(f)
    except FileNotFoundError:
        print("Config file not found. Please ensure config.yaml exists.")
        sys.exit(1)
    
    # Initialize backtester
    backtester = Backtester(config)
    
    # Set backtest parameters
    end_date = datetime.now()
    start_date = end_date - timedelta(days=30)  # Last 30 days
    
    print(f"Running backtest from {start_date.date()} to {end_date.date()}")
    
    # Run backtest
    results = await backtester.run_backtest(
        start_date.isoformat(), 
        end_date.isoformat()
    )
    
    # Generate and print report
    report = backtester.generate_report(results)
    print(report)
    
    # Close resources
    await backtester.data_collector.close()
    await backtester.sentiment_analyzer.close()

if __name__ == "__main__":
    asyncio.run(main())
