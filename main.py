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
        <title>Crypto Signal Bot - Dashboard</title>
        <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
        <link href="https://cdn.jsdelivr.net/npm/feather-icons@4.29.0/dist/feather.min.css" rel="stylesheet">
        <link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap" rel="stylesheet">
        <script src="https://cdn.jsdelivr.net/npm/feather-icons/dist/feather.min.js"></script>
        <style>
            :root {
                --primary-gradient: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                --success-gradient: linear-gradient(135deg, #4facfe 0%, #00f2fe 100%);
                --warning-gradient: linear-gradient(135deg, #fa709a 0%, #fee140 100%);
                --danger-gradient: linear-gradient(135deg, #ff6b6b 0%, #ffa726 100%);
                --dark-gradient: linear-gradient(135deg, #2c3e50 0%, #34495e 100%);
                --glass-bg: rgba(255, 255, 255, 0.25);
                --glass-border: rgba(255, 255, 255, 0.18);
                --shadow-color: rgba(31, 38, 135, 0.2);
            }
            
            * { font-family: 'Inter', sans-serif; }
            
            body {
                background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                min-height: 100vh;
                position: relative;
            }
            
            body::before {
                content: '';
                position: fixed;
                top: 0;
                left: 0;
                width: 100%;
                height: 100%;
                background-image: 
                    radial-gradient(circle at 25% 25%, rgba(255, 255, 255, 0.1) 0%, transparent 50%),
                    radial-gradient(circle at 75% 75%, rgba(255, 255, 255, 0.1) 0%, transparent 50%);
                pointer-events: none;
                z-index: -1;
            }
            
            .glass-card {
                background: var(--glass-bg);
                backdrop-filter: blur(20px);
                border: 1px solid var(--glass-border);
                border-radius: 20px;
                box-shadow: 0 8px 32px var(--shadow-color);
                transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
            }
            
            .glass-card:hover {
                transform: translateY(-5px);
                box-shadow: 0 20px 40px var(--shadow-color);
            }
            
            .status-card {
                border: none;
                border-radius: 16px;
                backdrop-filter: blur(20px);
                transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
                position: relative;
                overflow: hidden;
            }
            
            .status-card::before {
                content: '';
                position: absolute;
                top: 0;
                left: 0;
                right: 0;
                bottom: 0;
                background: inherit;
                opacity: 0.9;
                z-index: -1;
            }
            
            .status-card:hover {
                transform: translateY(-8px) scale(1.02);
                box-shadow: 0 25px 50px rgba(0, 0, 0, 0.2);
            }
            
            .status-card.running { background: var(--success-gradient); }
            .status-card.signals { background: var(--primary-gradient); }
            .status-card.price { background: var(--warning-gradient); }
            .status-card.change { background: var(--danger-gradient); }
            
            .metric-value {
                font-size: 2.5rem;
                font-weight: 700;
                text-shadow: 0 2px 4px rgba(0, 0, 0, 0.1);
                margin: 0;
                line-height: 1;
            }
            
            .metric-label {
                font-size: 0.9rem;
                font-weight: 500;
                opacity: 0.9;
                margin-bottom: 8px;
            }
            
            .icon-large {
                width: 48px;
                height: 48px;
                opacity: 0.3;
            }
            
            .signal-card {
                background: var(--glass-bg);
                backdrop-filter: blur(20px);
                border: 1px solid var(--glass-border);
                border-radius: 20px;
                position: relative;
                overflow: hidden;
            }
            
            .signal-card::before {
                content: '';
                position: absolute;
                top: 0;
                left: 0;
                width: 4px;
                height: 100%;
                background: var(--primary-gradient);
            }
            
            .btn-modern {
                background: var(--primary-gradient);
                border: none;
                border-radius: 12px;
                padding: 12px 24px;
                font-weight: 600;
                transition: all 0.3s ease;
                box-shadow: 0 4px 15px rgba(102, 126, 234, 0.4);
            }
            
            .btn-modern:hover {
                transform: translateY(-2px);
                box-shadow: 0 8px 25px rgba(102, 126, 234, 0.6);
                background: var(--primary-gradient);
                border: none;
            }
            
            .loading-pulse {
                display: inline-block;
                width: 8px;
                height: 8px;
                border-radius: 50%;
                background: currentColor;
                animation: pulse 1.5s ease-in-out infinite;
            }
            
            @keyframes pulse {
                0%, 100% { opacity: 1; }
                50% { opacity: 0.3; }
            }
            
            .header-title {
                font-size: 2.5rem;
                font-weight: 700;
                color: white;
                text-shadow: 0 2px 4px rgba(0, 0, 0, 0.1);
                margin: 0;
            }
            
            .last-update {
                font-size: 0.9rem;
                opacity: 0.8;
            }
            
            @media (max-width: 768px) {
                .metric-value { font-size: 2rem; }
                .header-title { font-size: 2rem; }
                .status-card { margin-bottom: 1rem; }
            }
        </style>
    </head>
    <body>
        <div class="container-fluid py-4">
            <!-- Header -->
            <div class="text-center mb-5">
                <h1 class="header-title mb-2">
                    <i data-feather="trending-up" class="me-3"></i>
                    Crypto Signal Bot
                </h1>
                <p class="text-white-50 last-update" id="last-update">
                    <i data-feather="clock" class="me-2"></i>
                    Last updated: <span class="loading-pulse"></span>
                </p>
            </div>
            
            <!-- Status Cards -->
            <div class="row g-4 mb-5">
                <div class="col-lg-3 col-md-6">
                    <div class="status-card running text-white p-4">
                        <div class="d-flex justify-content-between align-items-start">
                            <div class="flex-grow-1">
                                <div class="metric-label">Bot Status</div>
                                <div class="metric-value" id="status">Loading...</div>
                            </div>
                            <i data-feather="activity" class="icon-large"></i>
                        </div>
                    </div>
                </div>
                
                <div class="col-lg-3 col-md-6">
                    <div class="status-card signals text-white p-4">
                        <div class="d-flex justify-content-between align-items-start">
                            <div class="flex-grow-1">
                                <div class="metric-label">Signals Today</div>
                                <div class="metric-value" id="signals">0</div>
                            </div>
                            <i data-feather="zap" class="icon-large"></i>
                        </div>
                    </div>
                </div>
                
                <div class="col-lg-3 col-md-6">
                    <div class="status-card price text-white p-4">
                        <div class="d-flex justify-content-between align-items-start">
                            <div class="flex-grow-1">
                                <div class="metric-label">BTC Price</div>
                                <div class="metric-value" id="btc-price">$--,---</div>
                            </div>
                            <i data-feather="dollar-sign" class="icon-large"></i>
                        </div>
                    </div>
                </div>
                
                <div class="col-lg-3 col-md-6">
                    <div class="status-card change text-white p-4">
                        <div class="d-flex justify-content-between align-items-start">
                            <div class="flex-grow-1">
                                <div class="metric-label">24h Change</div>
                                <div class="metric-value" id="price-change">+0.00%</div>
                            </div>
                            <i data-feather="trending-up" class="icon-large"></i>
                        </div>
                    </div>
                </div>
            </div>
            
            <!-- Latest Signal -->
            <div class="row justify-content-center">
                <div class="col-xl-10">
                    <div class="signal-card p-4">
                        <div class="d-flex justify-content-between align-items-center mb-3">
                            <h4 class="text-white mb-0">
                                <i data-feather="target" class="me-2"></i>
                                Latest Signal
                            </h4>
                            <button class="btn btn-modern" onclick="refreshData()">
                                <i data-feather="refresh-cw" class="me-2"></i>
                                Refresh
                            </button>
                        </div>
                        
                        <div id="latest-signal" class="text-white">
                            <div class="text-center py-5">
                                <i data-feather="clock" class="mb-3" style="width: 64px; height: 64px; opacity: 0.3;"></i>
                                <h5 class="text-white-50">No signals generated yet</h5>
                                <p class="text-white-50 mb-0">The bot is analyzing market conditions...</p>
                            </div>
                        </div>
                    </div>
                </div>
            </div>
        </div>
        
        <script>
            feather.replace();
            
            // Update last updated time
            function updateLastUpdated() {
                document.getElementById('last-update').innerHTML = `
                    <i data-feather="clock" class="me-2"></i>
                    Last updated: ${new Date().toLocaleTimeString()}
                `;
                feather.replace();
            }
            
            function refreshData() {
                // Add loading state
                const refreshBtn = document.querySelector('.btn-modern');
                const originalContent = refreshBtn.innerHTML;
                refreshBtn.innerHTML = '<i data-feather="loader" class="me-2"></i>Loading...';
                refreshBtn.disabled = true;
                feather.replace();
                
                fetch('/api/status')
                    .then(response => response.json())
                    .then(data => {
                        // Update status
                        const statusEl = document.getElementById('status');
                        statusEl.textContent = data.running ? 'Running' : 'Stopped';
                        
                        // Update signals count
                        document.getElementById('signals').textContent = data.signal_count || 0;
                        
                        // Update real BTC price data
                        if (data.btc_price) {
                            document.getElementById('btc-price').textContent = 
                                '$' + data.btc_price.toFixed(0).replace(/\B(?=(\d{3})+(?!\d))/g, ',');
                        } else {
                            document.getElementById('btc-price').textContent = '$--,---';
                        }
                        
                        if (data.price_change_percent !== null) {
                            const change = data.price_change_percent;
                            document.getElementById('price-change').textContent = 
                                (change >= 0 ? '+' : '') + change.toFixed(2) + '%';
                            
                            // Update icon based on price direction
                            const changeIcon = document.querySelector('#price-change').parentElement.parentElement.querySelector('.icon-large');
                            changeIcon.setAttribute('data-feather', change >= 0 ? 'trending-up' : 'trending-down');
                        } else {
                            document.getElementById('price-change').textContent = '+0.00%';
                        }
                        
                        // Update signal display
                        const signalContainer = document.getElementById('latest-signal');
                        if (data.last_signal) {
                            const signal = data.last_signal;
                            const directionColor = signal.direction === 'LONG' ? '#4facfe' : '#ff6b6b';
                            const directionIcon = signal.direction === 'LONG' ? 'trending-up' : 'trending-down';
                            
                            signalContainer.innerHTML = `
                                <div class="row align-items-center">
                                    <div class="col-md-8">
                                        <div class="d-flex align-items-center mb-3">
                                            <div class="badge px-3 py-2 me-3" style="background: ${directionColor}; font-size: 1rem;">
                                                <i data-feather="${directionIcon}" class="me-2"></i>
                                                ${signal.direction}
                                            </div>
                                            <h5 class="text-white mb-0">${signal.symbol} · ${signal.timeframe}</h5>
                                            <span class="badge bg-light text-dark ms-3">${Math.round(signal.confidence * 100)}% Confidence</span>
                                        </div>
                                        
                                        <div class="row text-white-50">
                                            <div class="col-md-4 mb-2">
                                                <small class="d-block">Entry Price</small>
                                                <strong class="text-white fs-5">$${signal.entry_price}</strong>
                                            </div>
                                            <div class="col-md-4 mb-2">
                                                <small class="d-block">Stop Loss</small>
                                                <strong class="text-white fs-5">$${signal.stop_loss}</strong>
                                            </div>
                                            <div class="col-md-4 mb-2">
                                                <small class="d-block">Take Profits</small>
                                                <strong class="text-white fs-6">${signal.take_profits.map(tp => '$' + tp).join(' / ')}</strong>
                                            </div>
                                        </div>
                                    </div>
                                    
                                    <div class="col-md-4">
                                        <div class="glass-card p-3">
                                            <h6 class="text-white-50 mb-2">Analysis Reasons</h6>
                                            <ul class="list-unstyled text-white small mb-0">
                                                ${signal.reasons.slice(0, 3).map(reason => `<li class="mb-1">• ${reason}</li>`).join('')}
                                            </ul>
                                            <small class="text-white-50 mt-2 d-block">
                                                Generated: ${new Date(signal.timestamp || Date.now()).toLocaleTimeString()}
                                            </small>
                                        </div>
                                    </div>
                                </div>
                            `;
                        } else {
                            signalContainer.innerHTML = `
                                <div class="text-center py-5">
                                    <i data-feather="clock" class="mb-3" style="width: 64px; height: 64px; opacity: 0.3;"></i>
                                    <h5 class="text-white-50">No signals generated yet</h5>
                                    <p class="text-white-50 mb-0">The bot is analyzing market conditions...</p>
                                </div>
                            `;
                        }
                        
                        feather.replace();
                        updateLastUpdated();
                    })
                    .catch(error => {
                        console.error('Error:', error);
                        // Show error state
                    })
                    .finally(() => {
                        // Reset button
                        refreshBtn.innerHTML = originalContent;
                        refreshBtn.disabled = false;
                        feather.replace();
                    });
            }
            
            // Auto refresh every 30 seconds
            setInterval(refreshData, 30000);
            refreshData(); // Initial load
            
            // Add some interactive animations
            document.addEventListener('DOMContentLoaded', function() {
                // Animate cards on load
                const cards = document.querySelectorAll('.status-card, .signal-card');
                cards.forEach((card, index) => {
                    card.style.opacity = '0';
                    card.style.transform = 'translateY(20px)';
                    setTimeout(() => {
                        card.style.transition = 'all 0.6s cubic-bezier(0.4, 0, 0.2, 1)';
                        card.style.opacity = '1';
                        card.style.transform = 'translateY(0)';
                    }, index * 100);
                });
            });
        </script>
        
        <script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/js/bootstrap.bundle.min.js"></script>
    </body>
    </html>
    """
    return render_template_string(html_template)

@app.route('/api/status')
def api_status():
    """API endpoint for bot status"""
    global bot
    
    # Get real BTC price data
    btc_price = None
    price_change = None
    price_change_percent = None
    
    if bot and hasattr(bot, 'data_collector'):
        try:
            # Get current price
            current_price = asyncio.run(bot.data_collector.get_current_price('BTCUSDT'))
            if current_price:
                btc_price = round(current_price, 2)
            
            # Get 24h ticker data for price change
            ticker_data = asyncio.run(bot.data_collector.get_24h_ticker('BTCUSDT'))
            if ticker_data:
                price_change = round(ticker_data['price_change'], 2)
                price_change_percent = round(ticker_data['price_change_percent'], 2)
        except Exception as e:
            print(f"Error fetching BTC price: {e}")
    
    if bot:
        return jsonify({
            'running': bot.running,
            'signal_count': bot.signal_count,
            'last_signal': bot.last_signal,
            'btc_price': btc_price,
            'price_change': price_change,
            'price_change_percent': price_change_percent
        })
    else:
        return jsonify({
            'running': False, 
            'signal_count': 0, 
            'last_signal': None,
            'btc_price': None,
            'price_change': None,
            'price_change_percent': None
        })

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
    # Always use port 5000 for Replit compatibility
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
