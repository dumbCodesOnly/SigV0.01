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
        self.last_signals = {}  # Store signals for each symbol/timeframe
        self.signal_count = 0
        self.market_data = {}  # Store market data for multiple symbols
        
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
            config['api_keys']['newsapi_key'] = os.getenv('NEWSAPI_KEY', config['api_keys']['newsapi_key'])
            config['api_keys']['cryptocompare_key'] = os.getenv('CRYPTOCOMPARE_KEY', config['api_keys']['cryptocompare_key'])
            config['api_keys']['telegram_token'] = os.getenv('TELEGRAM_BOT_TOKEN', config['api_keys']['telegram_token'])
            config['telegram']['chat_id'] = os.getenv('TELEGRAM_CHAT_ID', config['telegram']['chat_id'])
            
            return config
        except Exception as e:
            self.logger.error(f"Failed to load config: {e}")
            sys.exit(1)
    
    async def run_analysis_cycle(self):
        """Run one complete analysis cycle for all symbols and timeframes"""
        try:
            symbols = self.config['trading']['symbols']
            timeframes = self.config['trading']['timeframes']
            
            self.logger.info(f"Starting analysis cycle for {len(symbols)} symbols and {len(timeframes)} timeframes")
            
            for symbol in symbols:
                # Update market data for this symbol
                await self._update_market_data(symbol)
                
                for timeframe in timeframes:
                    try:
                        await self._analyze_symbol_timeframe(symbol, timeframe)
                    except Exception as e:
                        self.logger.error(f"Error analyzing {symbol} {timeframe}: {e}")
                        continue
                        
        except Exception as e:
            self.logger.error(f"Error in analysis cycle: {e}")
    
    async def _update_market_data(self, symbol: str):
        """Update market data for a symbol"""
        try:
            # Get current price and 24h ticker
            current_price = await self.data_collector.get_current_price(symbol)
            ticker_data = await self.data_collector.get_24h_ticker(symbol)
            
            if current_price and ticker_data:
                self.market_data[symbol] = {
                    'price': round(current_price, 2),
                    'change': round(ticker_data['price_change'], 2),
                    'change_percent': round(ticker_data['price_change_percent'], 2),
                    'volume': ticker_data['volume'],
                    'high_24h': ticker_data['high_price'],
                    'low_24h': ticker_data['low_price'],
                    'updated': datetime.now().isoformat()
                }
        except Exception as e:
            self.logger.warning(f"Failed to update market data for {symbol}: {e}")
    
    async def _analyze_symbol_timeframe(self, symbol: str, timeframe: str):
        """Analyze a specific symbol and timeframe combination"""
        try:
            self.logger.debug(f"Analyzing {symbol} {timeframe}")
            
            # 1. Collect latest data
            df = await self.data_collector.get_ohlcv_data(symbol, timeframe)
            if df is None or df.empty:
                self.logger.warning(f"No data collected for {symbol} {timeframe}")
                return
            
            # 2. Calculate technical indicators
            df_with_indicators = self.strategy.calculate_indicators(df)
            
            # 3. Get sentiment data (cached per symbol)
            sentiment_score = await self.sentiment_analyzer.get_sentiment(symbol)
            
            # 4. Generate signal with symbol and timeframe context
            signal = self.signal_generator.generate_signal(
                df_with_indicators, 
                sentiment_score,
                symbol=symbol,
                timeframe=timeframe
            )
            
            # 5. Store and process signal
            key = f"{symbol}_{timeframe}"
            if signal:
                self.logger.info(f"Signal generated for {symbol} {timeframe}: {signal['direction']} at {signal['entry_price']}")
                self.last_signals[key] = signal
                self.signal_count += 1
                
                # Send notification for new signals
                await self.notifier.send_signal(signal)
            else:
                # Keep track that no signal was generated
                if key in self.last_signals:
                    # Clear old signal if no new signal
                    pass  # Keep the last signal for display
                    
        except Exception as e:
            self.logger.error(f"Error analyzing {symbol} {timeframe}: {e}")
    
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
                --primary-gradient: linear-gradient(135deg, #1a1a2e 0%, #16213e 100%);
                --success-gradient: linear-gradient(135deg, #0f3460 0%, #1e3c72 100%);
                --warning-gradient: linear-gradient(135deg, #2d1b69 0%, #1e3c72 100%);
                --danger-gradient: linear-gradient(135deg, #cc2b5e 0%, #753a88 100%);
                --dark-gradient: linear-gradient(135deg, #0c0c0c 0%, #1a1a1a 100%);
                --glass-bg: rgba(30, 30, 30, 0.9);
                --glass-border: rgba(70, 70, 70, 0.3);
                --shadow-color: rgba(0, 0, 0, 0.5);
                --text-primary: #ffffff;
                --text-secondary: #b3b3b3;
                --accent-blue: #4facfe;
                --accent-green: #00d4aa;
                --accent-red: #ff6b6b;
                --background-dark: #0a0a0a;
            }
            
            * { 
                font-family: 'Inter', sans-serif;
                color: var(--text-primary);
            }
            
            body {
                background: linear-gradient(135deg, #0a0a0a 0%, #1a1a1a 50%, #2d2d2d 100%);
                min-height: 100vh;
                position: relative;
                color: var(--text-primary);
            }
            
            body::before {
                content: '';
                position: fixed;
                top: 0;
                left: 0;
                width: 100%;
                height: 100%;
                background-image: 
                    radial-gradient(circle at 20% 20%, rgba(79, 172, 254, 0.1) 0%, transparent 40%),
                    radial-gradient(circle at 80% 80%, rgba(0, 212, 170, 0.1) 0%, transparent 40%),
                    radial-gradient(circle at 40% 60%, rgba(255, 107, 107, 0.05) 0%, transparent 30%);
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
            
            .status-card.running { background: linear-gradient(135deg, #0f3460 0%, #1e3c72 100%); }
            .status-card.signals { background: linear-gradient(135deg, #1a1a2e 0%, #16213e 100%); }
            .status-card.price { background: linear-gradient(135deg, #2d1b69 0%, #1e3c72 100%); }
            .status-card.change { background: linear-gradient(135deg, #cc2b5e 0%, #753a88 100%); }
            
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
                background: linear-gradient(135deg, #4facfe 0%, #00d4aa 100%);
                border: none;
                border-radius: 8px;
                padding: 6px 12px;
                font-weight: 600;
                color: #ffffff;
                transition: all 0.3s ease;
                box-shadow: 0 2px 8px rgba(79, 172, 254, 0.2);
                font-size: 0.875rem;
            }
            
            .btn-modern:hover {
                transform: translateY(-1px);
                box-shadow: 0 4px 12px rgba(79, 172, 254, 0.4);
                background: linear-gradient(135deg, #00d4aa 0%, #4facfe 100%);
                border: none;
                color: #ffffff;
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
                color: #ffffff;
                text-shadow: 0 2px 8px rgba(0, 0, 0, 0.3);
                margin: 0;
                background: linear-gradient(135deg, #4facfe 0%, #00d4aa 100%);
                -webkit-background-clip: text;
                -webkit-text-fill-color: transparent;
                background-clip: text;
            }
            
            .last-update {
                font-size: 0.9rem;
                opacity: 0.8;
            }
            
            .text-white-50 {
                color: var(--text-secondary) !important;
            }
            
            .badge {
                background-color: rgba(255, 255, 255, 0.1) !important;
                color: var(--text-primary) !important;
                border: 1px solid rgba(255, 255, 255, 0.2);
            }
            
            .badge.bg-light {
                background-color: rgba(79, 172, 254, 0.2) !important;
                color: var(--accent-blue) !important;
                border: 1px solid rgba(79, 172, 254, 0.3);
            }
            
            .custom-btn {
                display: inline-block;
                color: var(--text-primary);
                border: 1px solid rgba(255, 255, 255, 0.3);
                background: transparent;
                border-radius: 8px;
                font-size: 0.875rem;
                padding: 6px 12px;
                font-weight: 600;
                line-height: 1.5;
                text-align: center;
                text-decoration: none;
                vertical-align: middle;
                cursor: pointer;
                user-select: none;
                transition: all 0.3s ease;
                font-family: 'Inter', sans-serif;
            }
            
            .custom-btn:hover {
                color: var(--background-dark);
                background-color: rgba(255, 255, 255, 0.9);
                border-color: rgba(255, 255, 255, 0.9);
                transform: translateY(-1px);
                text-decoration: none;
            }
            
            .custom-btn:focus {
                color: var(--background-dark);
                background-color: rgba(255, 255, 255, 0.9);
                border-color: rgba(255, 255, 255, 0.9);
                outline: 0;
                box-shadow: 0 0 0 0.2rem rgba(255, 255, 255, 0.25);
            }
            
            .custom-btn:active {
                color: var(--background-dark);
                background-color: rgba(255, 255, 255, 0.9);
                border-color: rgba(255, 255, 255, 0.9);
                transform: translateY(0);
            }
            
            .table-dark {
                --bs-table-bg: rgba(30, 30, 30, 0.8);
                --bs-table-border-color: rgba(70, 70, 70, 0.3);
                color: var(--text-primary);
            }
            
            .table-hover > tbody > tr:hover > td {
                background-color: rgba(79, 172, 254, 0.1);
            }
            
            #market-overview-content {
                transition: all 0.3s ease-in-out;
                overflow: hidden;
            }
            
            #market-details {
                transition: all 0.3s ease-in-out;
                overflow: hidden;
            }
            
            #status-cards-content {
                transition: all 0.3s ease-in-out;
                overflow: hidden;
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
            
            <!-- Cryptocurrency Market Data -->
            <div class="row g-3 mb-3">
                <div class="col-12">
                    <div class="signal-card p-3">
                        <div class="d-flex justify-content-between align-items-center mb-3">
                            <h4 class="text-white mb-0">
                                <i data-feather="trending-up" class="me-2"></i>
                                Market Overview
                            </h4>
                            <div class="d-flex gap-2">
                                <button class="custom-btn" onclick="toggleMarketOverview()" id="market-toggle-btn">
                                    <i data-feather="chevron-down" class="me-1"></i>
                                    Expand
                                </button>
                                <button class="custom-btn" onclick="refreshData()">
                                    <i data-feather="refresh-cw" class="me-1"></i>
                                    Refresh
                                </button>
                            </div>
                        </div>
                        
                        <!-- Collapsible Market Content -->
                        <div id="market-overview-content" style="display: none;">
                            <div id="crypto-grid" class="row g-3">
                                <!-- Crypto cards will be populated by JavaScript -->
                            </div>
                            
                            <!-- Details toggle button -->
                            <div class="text-center mt-3">
                                <button class="custom-btn" onclick="toggleMarketDetails()" id="details-expand-btn">
                                    <i data-feather="chevron-down" class="me-1"></i>
                                    Show Details
                                </button>
                            </div>
                            
                            <!-- Expanded market details -->
                            <div id="market-details" class="mt-3" style="display: none;">
                                <div class="row g-3">
                                    <div class="col-12">
                                        <div class="table-responsive">
                                            <table class="table table-dark table-hover">
                                                <thead>
                                                    <tr class="text-white-50">
                                                        <th>Symbol</th>
                                                        <th>Price</th>
                                                        <th>24h Change</th>
                                                        <th>24h High</th>
                                                        <th>24h Low</th>
                                                        <th>Volume</th>
                                                    </tr>
                                                </thead>
                                                <tbody id="market-table-body">
                                                    <!-- Table rows will be populated by JavaScript -->
                                                </tbody>
                                            </table>
                                        </div>
                                    </div>
                                </div>
                            </div>
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
            
            <!-- Bot Status (moved to bottom) -->
            <div class="row g-3 mb-3 mt-5">
                <div class="col-12">
                    <div class="signal-card p-3">
                        <div class="d-flex justify-content-between align-items-center mb-3">
                            <h4 class="text-white mb-0">
                                <i data-feather="activity" class="me-2"></i>
                                Bot Status
                            </h4>
                            <div class="d-flex gap-2">
                                <button class="custom-btn" onclick="toggleStatusCards()" id="status-toggle-btn">
                                    <i data-feather="chevron-down" class="me-1"></i>
                                    Expand
                                </button>
                            </div>
                        </div>
                        
                        <!-- Collapsible Status Cards Content -->
                        <div id="status-cards-content" style="display: none;">
                            <div class="row g-3">
                                <div class="col-lg-3 col-md-6">
                                    <div class="status-card running text-white p-3">
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
                                    <div class="status-card signals text-white p-3">
                                        <div class="d-flex justify-content-between align-items-start">
                                            <div class="flex-grow-1">
                                                <div class="metric-label">Total Signals</div>
                                                <div class="metric-value" id="signals">0</div>
                                            </div>
                                            <i data-feather="zap" class="icon-large"></i>
                                        </div>
                                    </div>
                                </div>
                                
                                <div class="col-lg-3 col-md-6">
                                    <div class="status-card price text-white p-3">
                                        <div class="d-flex justify-content-between align-items-start">
                                            <div class="flex-grow-1">
                                                <div class="metric-label">Symbols Tracking</div>
                                                <div class="metric-value" id="symbol-count">5</div>
                                            </div>
                                            <i data-feather="eye" class="icon-large"></i>
                                        </div>
                                    </div>
                                </div>
                                
                                <div class="col-lg-3 col-md-6">
                                    <div class="status-card change text-white p-3">
                                        <div class="d-flex justify-content-between align-items-start">
                                            <div class="flex-grow-1">
                                                <div class="metric-label">Timeframes</div>
                                                <div class="metric-value" id="timeframe-count">4</div>
                                            </div>
                                            <i data-feather="clock" class="icon-large"></i>
                                        </div>
                                    </div>
                                </div>
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
                        
                        // Update crypto grid
                        updateCryptoGrid(data.crypto_data || {});
                        
                        // Update latest signals display
                        updateSignalsDisplay(data.last_signals || {});
                        
                        feather.replace();
                        updateLastUpdated();
                    })
                    .catch(error => {
                        console.error('Error:', error);
                        showErrorState();
                    })
                    .finally(() => {
                        // Reset button
                        refreshBtn.innerHTML = originalContent;
                        refreshBtn.disabled = false;
                        feather.replace();
                    });
            }
            
            function updateCryptoGrid(cryptoData) {
                const grid = document.getElementById('crypto-grid');
                const symbols = ['BTCUSDT', 'ETHUSDT', 'BNBUSDT', 'SOLUSDT', 'XRPUSDT'];
                const symbolNames = {
                    'BTCUSDT': 'Bitcoin',
                    'ETHUSDT': 'Ethereum', 
                    'BNBUSDT': 'BNB',
                    'SOLUSDT': 'Solana',
                    'XRPUSDT': 'XRP'
                };
                
                let gridHTML = '';
                
                symbols.forEach(symbol => {
                    const data = cryptoData[symbol];
                    const name = symbolNames[symbol];
                    const shortSymbol = symbol.replace('USDT', '');
                    
                    if (data) {
                        const changeColor = data.change_percent >= 0 ? '#4facfe' : '#ff6b6b';
                        const changeIcon = data.change_percent >= 0 ? 'trending-up' : 'trending-down';
                        
                        gridHTML += `
                            <div class="col-lg-2 col-md-4 col-sm-6">
                                <div class="glass-card p-3 text-center">
                                    <h6 class="text-white mb-1">${shortSymbol}</h6>
                                    <small class="text-white-50 d-block mb-2">${name}</small>
                                    <div class="h5 text-white mb-1">$${data.price.toFixed(data.price > 1 ? 2 : 6)}</div>
                                    <div class="d-flex align-items-center justify-content-center">
                                        <i data-feather="${changeIcon}" style="width: 14px; height: 14px; color: ${changeColor};" class="me-1"></i>
                                        <small style="color: ${changeColor};">
                                            ${data.change_percent >= 0 ? '+' : ''}${data.change_percent.toFixed(2)}%
                                        </small>
                                    </div>
                                </div>
                            </div>
                        `;
                    } else {
                        gridHTML += `
                            <div class="col-lg-2 col-md-4 col-sm-6">
                                <div class="glass-card p-3 text-center">
                                    <h6 class="text-white mb-1">${shortSymbol}</h6>
                                    <small class="text-white-50 d-block mb-2">${name}</small>
                                    <div class="h5 text-white-50 mb-1">Loading...</div>
                                    <small class="text-white-50">---%</small>
                                </div>
                            </div>
                        `;
                    }
                });
                
                grid.innerHTML = gridHTML;
                
                // Update the detailed table as well
                updateMarketTable(cryptoData);
            }
            
            function updateMarketTable(cryptoData) {
                const tableBody = document.getElementById('market-table-body');
                const symbols = ['BTCUSDT', 'ETHUSDT', 'BNBUSDT', 'SOLUSDT', 'XRPUSDT'];
                const symbolNames = {
                    'BTCUSDT': 'Bitcoin',
                    'ETHUSDT': 'Ethereum', 
                    'BNBUSDT': 'BNB',
                    'SOLUSDT': 'Solana',
                    'XRPUSDT': 'XRP'
                };
                
                let tableHTML = '';
                
                symbols.forEach(symbol => {
                    const data = cryptoData[symbol];
                    const name = symbolNames[symbol];
                    const shortSymbol = symbol.replace('USDT', '');
                    
                    if (data) {
                        const changeColor = data.change_percent >= 0 ? '#4facfe' : '#ff6b6b';
                        const changeIcon = data.change_percent >= 0 ? 'trending-up' : 'trending-down';
                        
                        tableHTML += `
                            <tr>
                                <td>
                                    <div class="d-flex align-items-center">
                                        <strong class="text-white">${shortSymbol}</strong>
                                        <small class="text-white-50 ms-2">${name}</small>
                                    </div>
                                </td>
                                <td class="text-white">$${data.price.toFixed(data.price > 1 ? 2 : 6)}</td>
                                <td>
                                    <span style="color: ${changeColor};">
                                        <i data-feather="${changeIcon}" style="width: 14px; height: 14px;" class="me-1"></i>
                                        ${data.change_percent >= 0 ? '+' : ''}${data.change_percent.toFixed(2)}%
                                    </span>
                                </td>
                                <td class="text-white-50">$${data.high_24h.toFixed(data.high_24h > 1 ? 2 : 6)}</td>
                                <td class="text-white-50">$${data.low_24h.toFixed(data.low_24h > 1 ? 2 : 6)}</td>
                                <td class="text-white-50">${formatVolume(data.volume)}</td>
                            </tr>
                        `;
                    } else {
                        tableHTML += `
                            <tr>
                                <td>
                                    <div class="d-flex align-items-center">
                                        <strong class="text-white">${shortSymbol}</strong>
                                        <small class="text-white-50 ms-2">${name}</small>
                                    </div>
                                </td>
                                <td class="text-white-50">Loading...</td>
                                <td class="text-white-50">---%</td>
                                <td class="text-white-50">---</td>
                                <td class="text-white-50">---</td>
                                <td class="text-white-50">---</td>
                            </tr>
                        `;
                    }
                });
                
                tableBody.innerHTML = tableHTML;
            }
            
            function formatVolume(volume) {
                if (volume >= 1e9) {
                    return (volume / 1e9).toFixed(1) + 'B';
                } else if (volume >= 1e6) {
                    return (volume / 1e6).toFixed(1) + 'M';
                } else if (volume >= 1e3) {
                    return (volume / 1e3).toFixed(1) + 'K';
                } else {
                    return volume.toFixed(0);
                }
            }
            
            function toggleMarketOverview() {
                const contentElement = document.getElementById('market-overview-content');
                const toggleBtn = document.getElementById('market-toggle-btn');
                const isExpanded = contentElement.style.display !== 'none';
                
                if (isExpanded) {
                    contentElement.style.height = contentElement.scrollHeight + 'px';
                    setTimeout(() => {
                        contentElement.style.height = '0px';
                        contentElement.style.opacity = '0';
                    }, 10);
                    setTimeout(() => {
                        contentElement.style.display = 'none';
                    }, 300);
                    toggleBtn.innerHTML = '<i data-feather="chevron-down" class="me-1"></i>Expand';
                } else {
                    contentElement.style.display = 'block';
                    contentElement.style.height = '0px';
                    contentElement.style.opacity = '0';
                    setTimeout(() => {
                        contentElement.style.height = contentElement.scrollHeight + 'px';
                        contentElement.style.opacity = '1';
                    }, 10);
                    setTimeout(() => {
                        contentElement.style.height = 'auto';
                    }, 300);
                    toggleBtn.innerHTML = '<i data-feather="chevron-up" class="me-1"></i>Collapse';
                }
                
                feather.replace();
            }
            
            function toggleMarketDetails() {
                const detailsElement = document.getElementById('market-details');
                const expandBtn = document.getElementById('details-expand-btn');
                const isExpanded = detailsElement.style.display !== 'none';
                
                if (isExpanded) {
                    detailsElement.style.height = detailsElement.scrollHeight + 'px';
                    setTimeout(() => {
                        detailsElement.style.height = '0px';
                        detailsElement.style.opacity = '0';
                    }, 10);
                    setTimeout(() => {
                        detailsElement.style.display = 'none';
                    }, 300);
                    expandBtn.innerHTML = '<i data-feather="chevron-down" class="me-1"></i>Show Details';
                } else {
                    detailsElement.style.display = 'block';
                    detailsElement.style.height = '0px';
                    detailsElement.style.opacity = '0';
                    setTimeout(() => {
                        detailsElement.style.height = detailsElement.scrollHeight + 'px';
                        detailsElement.style.opacity = '1';
                    }, 10);
                    setTimeout(() => {
                        detailsElement.style.height = 'auto';
                    }, 300);
                    expandBtn.innerHTML = '<i data-feather="chevron-up" class="me-1"></i>Hide Details';
                }
                
                feather.replace();
            }
            
            function toggleStatusCards() {
                const contentElement = document.getElementById('status-cards-content');
                const toggleBtn = document.getElementById('status-toggle-btn');
                const isExpanded = contentElement.style.display !== 'none';
                
                if (isExpanded) {
                    contentElement.style.height = contentElement.scrollHeight + 'px';
                    setTimeout(() => {
                        contentElement.style.height = '0px';
                        contentElement.style.opacity = '0';
                    }, 10);
                    setTimeout(() => {
                        contentElement.style.display = 'none';
                    }, 300);
                    toggleBtn.innerHTML = '<i data-feather="chevron-down" class="me-1"></i>Expand';
                } else {
                    contentElement.style.display = 'block';
                    contentElement.style.height = '0px';
                    contentElement.style.opacity = '0';
                    setTimeout(() => {
                        contentElement.style.height = contentElement.scrollHeight + 'px';
                        contentElement.style.opacity = '1';
                    }, 10);
                    setTimeout(() => {
                        contentElement.style.height = 'auto';
                    }, 300);
                    toggleBtn.innerHTML = '<i data-feather="chevron-up" class="me-1"></i>Collapse';
                }
                
                feather.replace();
            }
            
            function updateSignalsDisplay(lastSignals) {
                const signalContainer = document.getElementById('latest-signal');
                const signals = Object.values(lastSignals);
                
                if (signals.length > 0) {
                    // Show the most recent signal
                    const latestSignal = signals.reduce((latest, current) => {
                        return new Date(current.timestamp || 0) > new Date(latest.timestamp || 0) ? current : latest;
                    });
                    
                    const directionColor = latestSignal.direction === 'LONG' ? '#4facfe' : '#ff6b6b';
                    const directionIcon = latestSignal.direction === 'LONG' ? 'trending-up' : 'trending-down';
                    
                    signalContainer.innerHTML = `
                        <div class="row align-items-center">
                            <div class="col-md-8">
                                <div class="d-flex align-items-center mb-3">
                                    <div class="badge px-3 py-2 me-3" style="background: ${directionColor}; font-size: 1rem;">
                                        <i data-feather="${directionIcon}" class="me-2"></i>
                                        ${latestSignal.direction}
                                    </div>
                                    <h5 class="text-white mb-0">${latestSignal.symbol} · ${latestSignal.timeframe}</h5>
                                    <span class="badge bg-light text-dark ms-3">${Math.round(latestSignal.confidence * 100)}% Confidence</span>
                                </div>
                                
                                <div class="row text-white-50">
                                    <div class="col-md-4 mb-2">
                                        <small class="d-block">Entry Price</small>
                                        <strong class="text-white fs-5">$${latestSignal.entry_price}</strong>
                                    </div>
                                    <div class="col-md-4 mb-2">
                                        <small class="d-block">Stop Loss</small>
                                        <strong class="text-white fs-5">$${latestSignal.stop_loss}</strong>
                                    </div>
                                    <div class="col-md-4 mb-2">
                                        <small class="d-block">Take Profits</small>
                                        <strong class="text-white fs-6">${latestSignal.take_profits.map(tp => '$' + tp).join(' / ')}</strong>
                                    </div>
                                </div>
                                
                                <div class="mt-3">
                                    <small class="text-white-50">Active Signals: ${signals.length} across multiple timeframes</small>
                                </div>
                            </div>
                            
                            <div class="col-md-4">
                                <div class="glass-card p-3">
                                    <h6 class="text-white-50 mb-2">Analysis Reasons</h6>
                                    <ul class="list-unstyled text-white small mb-0">
                                        ${latestSignal.reasons.slice(0, 3).map(reason => `<li class="mb-1">• ${reason}</li>`).join('')}
                                    </ul>
                                    <small class="text-white-50 mt-2 d-block">
                                        Generated: ${new Date(latestSignal.timestamp || Date.now()).toLocaleTimeString()}
                                    </small>
                                </div>
                            </div>
                        </div>
                    `;
                } else {
                    signalContainer.innerHTML = `
                        <div class="text-center py-5">
                            <i data-feather="search" class="mb-3" style="width: 64px; height: 64px; opacity: 0.3;"></i>
                            <h5 class="text-white-50">Analyzing Multiple Markets</h5>
                            <p class="text-white-50 mb-0">Monitoring BTC, ETH, BNB, SOL, XRP across 5m, 15m, 1h, 4h timeframes</p>
                        </div>
                    `;
                }
            }
            
            function showErrorState() {
                document.getElementById('crypto-grid').innerHTML = `
                    <div class="col-12 text-center">
                        <div class="text-white-50">
                            <i data-feather="wifi-off" style="width: 48px; height: 48px; opacity: 0.5;"></i>
                            <p class="mt-2">Unable to fetch market data</p>
                        </div>
                    </div>
                `;
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

async def fetch_all_crypto_data():
    """Fetch market data for all supported cryptocurrencies"""
    from data_collector import DataCollector
    
    symbols = ["BTCUSDT", "ETHUSDT", "BNBUSDT", "SOLUSDT", "XRPUSDT"]
    crypto_data = {}
    
    try:
        # Create a temporary data collector for price fetching
        temp_config = {"api_keys": {}}
        collector = DataCollector(temp_config)
        
        for symbol in symbols:
            try:
                # Get current price and 24h ticker data
                current_price = await collector.get_current_price(symbol)
                ticker_data = await collector.get_24h_ticker(symbol)
                
                if current_price and ticker_data:
                    crypto_data[symbol] = {
                        'price': round(current_price, 6),
                        'change': round(ticker_data['price_change'], 6),
                        'change_percent': round(ticker_data['price_change_percent'], 2),
                        'volume': ticker_data['volume'],
                        'high_24h': ticker_data['high_price'],
                        'low_24h': ticker_data['low_price']
                    }
            except Exception as e:
                print(f"Error fetching data for {symbol}: {e}")
                continue
        
        # Close the session
        await collector.close()
        
        return crypto_data
        
    except Exception as e:
        print(f"Error fetching crypto data: {e}")
        return {}

@app.route('/api/status')
def api_status():
    """API endpoint for bot status"""
    global bot
    
    # Get real market data for all cryptocurrencies
    crypto_data = {}
    
    try:
        # Create new event loop for price fetching
        import asyncio
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        try:
            crypto_data = loop.run_until_complete(fetch_all_crypto_data())
        finally:
            loop.close()
            
    except Exception as e:
        print(f"Error in crypto data fetch: {e}")
    
    # Bot status (may be None if running under gunicorn)
    bot_running = False
    signal_count = 0
    last_signals = {}
    market_data = {}
    
    if bot:
        bot_running = bot.running
        signal_count = bot.signal_count
        last_signals = getattr(bot, 'last_signals', {})
        market_data = getattr(bot, 'market_data', {})
    
    return jsonify({
        'running': bot_running,
        'signal_count': signal_count,
        'last_signals': last_signals,
        'crypto_data': crypto_data,
        'market_data': market_data,
        'symbols': ["BTCUSDT", "ETHUSDT", "BNBUSDT", "SOLUSDT", "XRPUSDT"],
        'timeframes': ["5m", "15m", "1h", "4h"]
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
    
    # Only run the bot (web server runs separately via gunicorn)
    try:
        print("Starting Crypto Signal Bot...")
        asyncio.run(run_bot())
    except KeyboardInterrupt:
        print("\nShutdown complete")
