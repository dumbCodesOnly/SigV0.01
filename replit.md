# Overview

This is a cryptocurrency market analysis and signal generation bot that performs real-time technical analysis, sentiment analysis, and trading signal generation without executing trades. The bot monitors crypto markets using Binance WebSocket feeds, applies technical indicators and sentiment analysis, and generates trading signals with complete risk management parameters including entry points, stop losses, and take profit levels.

# User Preferences

Preferred communication style: Simple, everyday language.

# System Architecture

## Core Architecture Pattern
The system follows a modular event-driven architecture with async/await patterns for handling real-time data streams and API calls. Each component operates independently and communicates through a central orchestrator (main.py) that coordinates data flow between modules.

## Data Processing Pipeline
- **Real-time Data Ingestion**: Uses Binance WebSocket API for live OHLCV data collection with fallback support for CCXT-Pro integration
- **Technical Analysis Engine**: Implements pandas-ta for calculating technical indicators (EMA, RSI, ATR, Bollinger Bands) with configurable parameters
- **Sentiment Analysis**: Multi-source sentiment aggregation from Finnhub API, LunarCrush API, and fallback FinBERT model for news classification
- **Signal Generation**: Combines technical and sentiment analysis to generate qualified trading signals with complete risk management parameters

## Risk Management Framework
- **Position Sizing**: Configurable risk percentage per trade
- **Stop Loss Calculation**: ATR-based or swing point-based stop losses
- **Take Profit Levels**: Multiple profit targets (TP1, TP2, TP3) with risk-reward ratios
- **Breakeven Management**: Automatic stop loss adjustment after first profit target
- **Trailing Stops**: Optional ATR-based trailing stop functionality

## Strategy Implementation
- **Trend Filtering**: EMA crossover system (50/200) for trend direction
- **Entry Conditions**: Pullback and breakout setups with Bollinger Band squeeze detection
- **Sentiment Confirmation**: Requires sentiment alignment (+0.2 for longs, -0.2 for shorts)
- **Confidence Scoring**: Weighted combination of technical and sentiment factors

## Backtesting Engine
- **Historical Testing**: Runs identical strategy logic on historical data
- **Performance Metrics**: Calculates win rate, profit factor, maximum drawdown, average R-multiple
- **Bias Prevention**: Ensures no lookahead bias by using only closed candle data

## Notification System
- **Telegram Integration**: Formatted HTML messages sent to configured chat channels
- **Signal Format**: Structured messages with entry, stop loss, take profit levels
- **Health Monitoring**: Web dashboard for bot status and performance metrics

## Configuration Management
- **YAML Configuration**: Centralized configuration for all parameters including API keys, trading pairs, timeframes, and risk management settings
- **Environment Flexibility**: Supports multiple exchange configurations and indicator parameters

## Asynchronous Architecture
- **Non-blocking Operations**: All API calls and data processing use async/await patterns
- **Session Management**: Proper aiohttp session handling for HTTP requests
- **Resource Cleanup**: Automatic session cleanup and connection management

## Error Handling and Logging
- **Structured Logging**: Configurable logging with file rotation and multiple output formats
- **Graceful Degradation**: Fallback mechanisms for API failures and data source unavailability
- **Health Monitoring**: Built-in Flask endpoint for system status monitoring

# External Dependencies

## Market Data Sources
- **Binance API**: Primary data source for cryptocurrency OHLCV data via WebSocket and REST API
- **CCXT-Pro**: Optional integration for multi-exchange support

## Sentiment Data Providers
- **Finnhub API**: Financial news sentiment analysis and market data
- **LunarCrush API**: Cryptocurrency social sentiment aggregation
- **HuggingFace FinBERT**: Fallback NLP model for financial text classification

## Technical Analysis Libraries
- **pandas-ta**: Primary technical analysis library for indicator calculations
- **TA-Lib**: Alternative technical analysis library (optional)

## Communication Services
- **Telegram Bot API**: Message delivery for trading signals and alerts

## Python Libraries
- **aiohttp**: Asynchronous HTTP client for API communications
- **pandas/numpy**: Data manipulation and numerical computations
- **Flask**: Web interface for monitoring and health checks
- **PyYAML**: Configuration file parsing
- **python-telegram-bot**: Telegram integration library

## Infrastructure Components
- **WebSocket Connections**: Real-time market data streaming
- **HTTP REST APIs**: Various financial data and sentiment APIs
- **File System**: Local logging and configuration storage