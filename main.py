#!/usr/bin/env python3
"""
Crypto Signal Bot - Main Entry Point
Orchestrates data collection, technical analysis, sentiment analysis, and signal generation
"""

import asyncio
import logging
import os
import signal
import sys
from datetime import datetime
from typing import Dict, Any

import yaml
from flask import Flask, render_template_string, jsonify

from data_collector import DataCollector
from strategy import TradingStrategy
from sentiment_analyzer import SentimentAnalyzer
from signal_generator import SignalGenerator
from notifier import TelegramNotifier
from utils import setup_logging

# Flask app for health check and status
app = Flask(__name__)

class CryptoSignalBot:
    def __init__(self, config_path: str = "config.yaml"):
        """Initialize the crypto signal bot"""
        self.config = self._load_config(config_path)
        self.running = False
        self.last_signal = None
        self.signal_count = 0
        
        # Initialize components
        self.data_collector = DataCollector(self.config)
        self.strategy = TradingStrategy(self.config)
        self.sentiment_analyzer = SentimentAnalyzer(self.config)
        self.signal_generator = SignalGenerator(self.config)
        self.notifier = TelegramNotifier(self.config)
        
        # Setup logging
        setup_logging(self.config.get('logging', {}))
        self.logger = logging.getLogger(__name__)
        
    def _load_config(self, config_path: str) -> Dict[str, Any]:
        """Load configuration from YAML file"""
        try:
            with open(config_path, 'r') as f:
                config = yaml.safe_load(f)
            
            # Override with environment variables
            config['api_keys']['binance_key'] = os.getenv('BINANCE_API_KEY', config['api_keys']['binance_key'])
            config['api_keys']['binance_secret'] = os.getenv('BINANCE_API_SECRET', config['api_keys']['binance_secret'])
            config['api_keys']['finnhub_key'] = os.getenv('FINNHUB_API_KEY', config['api_keys']['finnhub_key'])
            config['api_keys']['telegram_token'] = os.getenv('TELEGRAM_BOT_TOKEN', config['api_keys']['telegram_token'])
            config['telegram']['chat_id'] = os.getenv('TELEGRAM_CHAT_ID', config['telegram']['chat_id'])
            
            return config
        except Exception as e:
            self.logger.error(f"Failed to load config: {e}")
            sys.exit(1)
    
    async def run_analysis_cycle(self):
        """Run one complete analysis cycle"""
        try:
            symbol = self.config['trading']['symbol']
            timeframe = self.config['trading']['timeframe']
            
            self.logger.info(f"Starting analysis cycle for {symbol} {timeframe}")
            
            # 1. Collect latest data
            df = await self.data_collector.get_ohlcv_data(symbol, timeframe)
            if df is None or df.empty:
                self.logger.warning("No data collected, skipping cycle")
                return
            
            self.logger.info(f"Collected {len(df)} candles")
            
            # 2. Calculate technical indicators
            df_with_indicators = self.strategy.calculate_indicators(df)
            
            # 3. Get sentiment data
            sentiment_score = await self.sentiment_analyzer.get_sentiment(symbol)
            
            # 4. Generate signal
            signal = self.signal_generator.generate_signal(
                df_with_indicators, 
                sentiment_score
            )
            
            if signal:
                self.logger.info(f"Signal generated: {signal['direction']} at {signal['entry_price']}")
                self.last_signal = signal
                self.signal_count += 1
                
                # 5. Send notification
                await self.notifier.send_signal(signal)
            else:
                self.logger.info("No signal generated")
                
        except Exception as e:
            self.logger.error(f"Error in analysis cycle: {e}")
    
    async def run(self):
        """Main bot loop"""
        self.running = True
        self.logger.info("Crypto Signal Bot started")
        
        # Send startup notification
        await self.notifier.send_startup_message()
        
        while self.running:
            try:
                await self.run_analysis_cycle()
                
                # Wait for next cycle
                interval = self.config['trading'].get('check_interval', 300)  # 5 minutes default
                await asyncio.sleep(interval)
                
            except KeyboardInterrupt:
                self.logger.info("Received shutdown signal")
                break
            except Exception as e:
                self.logger.error(f"Unexpected error: {e}")
                await asyncio.sleep(60)  # Wait before retrying
        
        self.logger.info("Crypto Signal Bot stopped")
    
    def stop(self):
        """Stop the bot"""
        self.running = False

# Flask routes for web interface
@app.route('/')
def index():
    """Main dashboard"""
    html_template = """
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Crypto Signal Bot</title>
        <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.1.3/dist/css/bootstrap.min.css" rel="stylesheet">
        <link href="https://cdn.jsdelivr.net/npm/feather-icons@4.28.0/dist/feather.min.css" rel="stylesheet">
        <script src="https://cdn.jsdelivr.net/npm/feather-icons/dist/feather.min.js"></script>
    </head>
    <body class="bg-light">
        <div class="container py-5">
            <div class="row">
                <div class="col-md-8 mx-auto">
                    <div class="card shadow">
                        <div class="card-header bg-primary text-white">
                            <h1 class="card-title mb-0">
                                <i data-feather="trending-up" class="me-2"></i>
                                Crypto Signal Bot
                            </h1>
                        </div>
                        <div class="card-body">
                            <div class="row mb-4">
                                <div class="col-md-6">
                                    <div class="card bg-success text-white">
                                        <div class="card-body">
                                            <h5><i data-feather="activity" class="me-2"></i>Status</h5>
                                            <p id="status" class="mb-0">Loading...</p>
                                        </div>
                                    </div>
                                </div>
                                <div class="col-md-6">
                                    <div class="card bg-info text-white">
                                        <div class="card-body">
                                            <h5><i data-feather="bar-chart-2" class="me-2"></i>Signals Today</h5>
                                            <p id="signals" class="mb-0">0</p>
                                        </div>
                                    </div>
                                </div>
                            </div>
                            
                            <div class="card">
                                <div class="card-header">
                                    <h5><i data-feather="target" class="me-2"></i>Latest Signal</h5>
                                </div>
                                <div class="card-body">
                                    <div id="latest-signal">
                                        <p class="text-muted">No signals generated yet</p>
                                    </div>
                                </div>
                            </div>
                            
                            <div class="mt-4">
                                <button class="btn btn-primary" onclick="refreshData()">
                                    <i data-feather="refresh-cw" class="me-2"></i>Refresh
                                </button>
                            </div>
                        </div>
                    </div>
                </div>
            </div>
        </div>
        
        <script>
            feather.replace();
            
            function refreshData() {
                fetch('/api/status')
                    .then(response => response.json())
                    .then(data => {
                        document.getElementById('status').textContent = data.running ? 'Running' : 'Stopped';
                        document.getElementById('signals').textContent = data.signal_count || 0;
                        
                        if (data.last_signal) {
                            const signal = data.last_signal;
                            document.getElementById('latest-signal').innerHTML = `
                                <div class="alert alert-${signal.direction === 'LONG' ? 'success' : 'danger'}">
                                    <h6>${signal.symbol} · ${signal.direction} · ${signal.timeframe}</h6>
                                    <p class="mb-1"><strong>Entry:</strong> ${signal.entry_price}</p>
                                    <p class="mb-1"><strong>Stop Loss:</strong> ${signal.stop_loss}</p>
                                    <p class="mb-1"><strong>Take Profits:</strong> ${signal.take_profits.join(' / ')}</p>
                                    <p class="mb-1"><strong>Confidence:</strong> ${Math.round(signal.confidence * 100)}%</p>
                                    <p class="mb-0"><strong>Reason:</strong> ${signal.reasons.join(', ')}</p>
                                </div>
                            `;
                        }
                    })
                    .catch(error => console.error('Error:', error));
            }
            
            // Auto refresh every 30 seconds
            setInterval(refreshData, 30000);
            refreshData(); // Initial load
        </script>
    </body>
    </html>
    """
    return render_template_string(html_template)

@app.route('/api/status')
def api_status():
    """API endpoint for bot status"""
    global bot
    if bot:
        return jsonify({
            'running': bot.running,
            'signal_count': bot.signal_count,
            'last_signal': bot.last_signal
        })
    else:
        return jsonify({'running': False, 'signal_count': 0, 'last_signal': None})

# Global bot instance
bot = None

def signal_handler(sig, frame):
    """Handle shutdown signals"""
    global bot
    if bot:
        bot.stop()
    sys.exit(0)

async def run_bot():
    """Run the bot in background"""
    global bot
    bot = CryptoSignalBot()
    await bot.run()

def run_flask():
    """Run Flask app"""
    app.run(host='0.0.0.0', port=5000, debug=False)

if __name__ == "__main__":
    # Setup signal handlers
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    # Run both Flask and bot concurrently
    import threading
    
    # Start Flask in a separate thread
    flask_thread = threading.Thread(target=run_flask, daemon=True)
    flask_thread.start()
    
    # Run bot in main thread
    try:
        asyncio.run(run_bot())
    except KeyboardInterrupt:
        print("\nShutdown complete")
