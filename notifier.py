"""
Telegram Notifier Module
Handles sending notifications via Telegram Bot
"""

import asyncio
import logging
import aiohttp
from datetime import datetime
from typing import Dict, Any, Optional
from api_config import APIConfig

class TelegramNotifier:
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.logger = logging.getLogger(__name__)
        
        self.bot_token = config['api_keys'].get('telegram_token')
        self.chat_id = config['telegram'].get('chat_id')
        self.session = None
        
        if not self.bot_token:
            self.logger.warning("Telegram bot token not provided - notifications disabled")
        if not self.chat_id:
            self.logger.warning("Telegram chat ID not provided - notifications disabled")
    
    async def _get_session(self) -> aiohttp.ClientSession:
        """Get or create aiohttp session"""
        if self.session is None or self.session.closed:
            self.session = aiohttp.ClientSession()
        return self.session
    
    async def close(self):
        """Close the session"""
        if self.session and not self.session.closed:
            await self.session.close()
    
    async def send_message(self, text: str, parse_mode: str = 'HTML') -> bool:
        """Send a message via Telegram Bot API"""
        try:
            if not self.bot_token or not self.chat_id:
                self.logger.warning("Telegram credentials missing - cannot send message")
                return False
            
            session = await self._get_session()
            
            url = APIConfig.get_full_url('notification', 'telegram', 'send_message')
            
            payload = {
                'chat_id': self.chat_id,
                'text': text,
                'parse_mode': parse_mode,
                'disable_web_page_preview': True
            }
            
            async with session.post(url, json=payload) as response:
                if response.status == 200:
                    self.logger.info("Telegram message sent successfully")
                    return True
                else:
                    error_text = await response.text()
                    self.logger.error(f"Telegram API error {response.status}: {error_text}")
                    return False
                    
        except Exception as e:
            self.logger.error(f"Error sending Telegram message: {e}")
            return False
    
    async def send_signal(self, signal: Dict[str, Any]) -> bool:
        """Send trading signal notification"""
        try:
            from signal_generator import SignalGenerator
            generator = SignalGenerator(self.config)
            
            # Format signal for Telegram
            message = generator.format_signal_telegram(signal)
            
            # Send the message
            success = await self.send_message(message)
            
            if success:
                self.logger.info(f"Signal notification sent for {signal['symbol']} {signal['direction']}")
            
            return success
            
        except Exception as e:
            self.logger.error(f"Error sending signal notification: {e}")
            return False
    
    async def send_startup_message(self) -> bool:
        """Send bot startup notification"""
        try:
            message = f"""
🤖 <b>Crypto Signal Bot Started</b>

📊 <b>Configuration:</b>
• Symbol: {self.config['trading']['symbol']}
• Timeframe: {self.config['trading']['timeframe']}
• Risk per trade: {self.config.get('risk_management', {}).get('risk_per_trade', 2)}%

⏰ Started at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S UTC')}

<i>Bot is now monitoring the markets for signals...</i>
            """.strip()
            
            return await self.send_message(message)
            
        except Exception as e:
            self.logger.error(f"Error sending startup message: {e}")
            return False
    
    async def send_error_message(self, error_msg: str) -> bool:
        """Send error notification"""
        try:
            message = f"""
⚠️ <b>Bot Error Alert</b>

<b>Error:</b> {error_msg}
<b>Time:</b> {datetime.now().strftime('%Y-%m-%d %H:%M:%S UTC')}

<i>Please check the bot logs for more details.</i>
            """.strip()
            
            return await self.send_message(message)
            
        except Exception as e:
            self.logger.error(f"Error sending error message: {e}")
            return False
    
    async def send_status_update(self, status: Dict[str, Any]) -> bool:
        """Send periodic status update"""
        try:
            message = f"""
📊 <b>Bot Status Update</b>

<b>Uptime:</b> {status.get('uptime', 'Unknown')}
<b>Signals Today:</b> {status.get('signals_today', 0)}
<b>Last Signal:</b> {status.get('last_signal_time', 'None')}

<b>Current Market:</b>
• Price: ${status.get('current_price', 'N/A')}
• 24h Change: {status.get('price_change_24h', 'N/A')}%

<i>Bot is running normally</i>
            """.strip()
            
            return await self.send_message(message)
            
        except Exception as e:
            self.logger.error(f"Error sending status update: {e}")
            return False
    
    async def test_connection(self) -> bool:
        """Test Telegram bot connection"""
        try:
            if not self.bot_token:
                self.logger.error("No Telegram bot token provided")
                return False
            
            session = await self._get_session()
            url = f"https://api.telegram.org/bot{self.bot_token}/getMe"
            
            async with session.get(url) as response:
                if response.status == 200:
                    data = await response.json()
                    bot_info = data.get('result', {})
                    bot_name = bot_info.get('first_name', 'Unknown')
                    self.logger.info(f"Telegram bot connection successful: {bot_name}")
                    
                    # Send test message
                    test_msg = f"🔧 Telegram connection test successful!\nBot: @{bot_info.get('username', 'unknown')}"
                    return await self.send_message(test_msg)
                else:
                    self.logger.error(f"Telegram bot connection failed: {response.status}")
                    return False
                    
        except Exception as e:
            self.logger.error(f"Error testing Telegram connection: {e}")
            return False
    
    def format_price(self, price: float) -> str:
        """Format price for display"""
        if price >= 1000:
            return f"{price:,.2f}"
        elif price >= 1:
            return f"{price:.4f}"
        else:
            return f"{price:.6f}"
    
    def format_percentage(self, percentage: float) -> str:
        """Format percentage for display"""
        sign = "+" if percentage >= 0 else ""
        return f"{sign}{percentage:.2f}%"
