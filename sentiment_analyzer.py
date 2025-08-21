"""
Sentiment Analysis Module
Integrates various sentiment data sources
"""

import asyncio
import logging
import aiohttp
import json
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, List

class SentimentAnalyzer:
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.logger = logging.getLogger(__name__)
        self.finnhub_key = config['api_keys'].get('finnhub_key')
        self.session = None
        
        # Sentiment cache to avoid excessive API calls
        self.sentiment_cache = {}
        self.cache_duration = 300  # 5 minutes
        
    async def _get_session(self) -> aiohttp.ClientSession:
        """Get or create aiohttp session"""
        if self.session is None or self.session.closed:
            self.session = aiohttp.ClientSession()
        return self.session
    
    async def close(self):
        """Close the session"""
        if self.session and not self.session.closed:
            await self.session.close()
    
    def _is_cache_valid(self, symbol: str) -> bool:
        """Check if cached sentiment is still valid"""
        if symbol not in self.sentiment_cache:
            return False
        
        cache_time = self.sentiment_cache[symbol].get('timestamp')
        if not cache_time:
            return False
        
        return (datetime.now() - cache_time).seconds < self.cache_duration
    
    async def get_finnhub_news_sentiment(self, symbol: str) -> Optional[float]:
        """Get news sentiment from Finnhub API"""
        try:
            if not self.finnhub_key:
                self.logger.warning("Finnhub API key not provided")
                return None
            
            session = await self._get_session()
            
            # Convert crypto symbol to Finnhub format
            finnhub_symbol = symbol.replace('USDT', '-USD')
            
            # Get recent news
            params = {
                'symbol': finnhub_symbol,
                'token': self.finnhub_key
            }
            
            url = "https://finnhub.io/api/v1/company-news"
            
            async with session.get(url, params=params) as response:
                if response.status == 200:
                    news_data = await response.json()
                    
                    if not news_data:
                        self.logger.info(f"No news found for {symbol}")
                        return 0.0
                    
                    # Analyze news sentiment
                    sentiment_scores = []
                    
                    for article in news_data[:10]:  # Analyze last 10 articles
                        headline = article.get('headline', '')
                        summary = article.get('summary', '')
                        
                        # Simple sentiment scoring based on keywords
                        sentiment = self._analyze_text_sentiment(headline + ' ' + summary)
                        sentiment_scores.append(sentiment)
                    
                    # Average sentiment
                    if sentiment_scores:
                        avg_sentiment = sum(sentiment_scores) / len(sentiment_scores)
                        self.logger.info(f"Finnhub sentiment for {symbol}: {avg_sentiment:.2f}")
                        return avg_sentiment
                    
                elif response.status == 429:
                    self.logger.warning("Finnhub API rate limit exceeded")
                    return 0.0
                else:
                    self.logger.error(f"Finnhub API error: {response.status}")
                    return None
                    
        except Exception as e:
            self.logger.error(f"Error getting Finnhub sentiment: {e}")
            return None
    
    def _analyze_text_sentiment(self, text: str) -> float:
        """
        Simple rule-based sentiment analysis
        Returns sentiment score between -1 (very negative) and 1 (very positive)
        """
        if not text:
            return 0.0
        
        text_lower = text.lower()
        
        # Positive keywords
        positive_keywords = [
            'bullish', 'bull', 'buy', 'surge', 'pump', 'moon', 'rally', 'breakout',
            'support', 'strong', 'bullrun', 'up', 'rise', 'gain', 'profit',
            'positive', 'good', 'great', 'excellent', 'amazing', 'fantastic',
            'adoption', 'partnership', 'upgrade', 'institutional', 'investment'
        ]
        
        # Negative keywords
        negative_keywords = [
            'bearish', 'bear', 'sell', 'dump', 'crash', 'drop', 'fall', 'decline',
            'resistance', 'weak', 'bearmarket', 'down', 'loss', 'negative',
            'bad', 'terrible', 'awful', 'crash', 'scam', 'hack', 'regulation',
            'ban', 'restriction', 'fear', 'uncertainty', 'doubt'
        ]
        
        positive_count = sum(1 for keyword in positive_keywords if keyword in text_lower)
        negative_count = sum(1 for keyword in negative_keywords if keyword in text_lower)
        
        total_words = len(text_lower.split())
        if total_words == 0:
            return 0.0
        
        # Calculate sentiment score
        sentiment_score = (positive_count - negative_count) / max(total_words * 0.1, 1)
        
        # Normalize to -1 to 1 range
        sentiment_score = max(-1.0, min(1.0, sentiment_score))
        
        return sentiment_score
    
    async def get_social_sentiment(self, symbol: str) -> Optional[float]:
        """
        Get social media sentiment (placeholder for future implementation)
        This could integrate with Twitter API, Reddit API, etc.
        """
        try:
            # Placeholder implementation
            # In a real implementation, you would:
            # 1. Fetch recent tweets/posts about the symbol
            # 2. Analyze sentiment using NLP
            # 3. Return aggregated sentiment score
            
            # For now, return neutral sentiment
            self.logger.info(f"Social sentiment for {symbol}: 0.0 (placeholder)")
            return 0.0
            
        except Exception as e:
            self.logger.error(f"Error getting social sentiment: {e}")
            return None
    
    async def get_market_sentiment(self, symbol: str) -> Optional[float]:
        """
        Get overall market sentiment indicators
        This could include VIX-like indicators, fear & greed index, etc.
        """
        try:
            # Placeholder for market sentiment indicators
            # This could integrate with:
            # - Crypto Fear & Greed Index
            # - Google Trends
            # - Market volatility indicators
            
            # For now, return neutral sentiment
            self.logger.info(f"Market sentiment for {symbol}: 0.0 (placeholder)")
            return 0.0
            
        except Exception as e:
            self.logger.error(f"Error getting market sentiment: {e}")
            return None
    
    async def get_sentiment(self, symbol: str) -> float:
        """
        Get combined sentiment score for a symbol
        Returns score between -1 (very negative) and 1 (very positive)
        """
        try:
            # Check cache first
            if self._is_cache_valid(symbol):
                cached_sentiment = self.sentiment_cache[symbol]['score']
                self.logger.debug(f"Using cached sentiment for {symbol}: {cached_sentiment}")
                return cached_sentiment
            
            sentiment_scores = []
            weights = []
            
            # Get news sentiment
            news_sentiment = await self.get_finnhub_news_sentiment(symbol)
            if news_sentiment is not None:
                sentiment_scores.append(news_sentiment)
                weights.append(0.6)  # 60% weight for news
            
            # Get social sentiment
            social_sentiment = await self.get_social_sentiment(symbol)
            if social_sentiment is not None:
                sentiment_scores.append(social_sentiment)
                weights.append(0.3)  # 30% weight for social
            
            # Get market sentiment
            market_sentiment = await self.get_market_sentiment(symbol)
            if market_sentiment is not None:
                sentiment_scores.append(market_sentiment)
                weights.append(0.1)  # 10% weight for market
            
            # Calculate weighted average
            if sentiment_scores:
                # Normalize weights
                total_weight = sum(weights)
                if total_weight > 0:
                    normalized_weights = [w / total_weight for w in weights]
                    combined_sentiment = sum(score * weight for score, weight 
                                           in zip(sentiment_scores, normalized_weights))
                else:
                    combined_sentiment = sum(sentiment_scores) / len(sentiment_scores)
            else:
                combined_sentiment = 0.0  # Neutral if no data
            
            # Cache the result
            self.sentiment_cache[symbol] = {
                'score': combined_sentiment,
                'timestamp': datetime.now()
            }
            
            self.logger.info(f"Combined sentiment for {symbol}: {combined_sentiment:.2f}")
            return combined_sentiment
            
        except Exception as e:
            self.logger.error(f"Error getting combined sentiment: {e}")
            return 0.0  # Return neutral on error
    
    def validate_sentiment_alignment(self, sentiment_score: float, signal_direction: str) -> bool:
        """
        Validate if sentiment aligns with signal direction
        """
        try:
            sentiment_threshold = self.config.get('sentiment', {}).get('threshold', 0.2)
            
            if signal_direction == 'LONG':
                return sentiment_score >= sentiment_threshold
            elif signal_direction == 'SHORT':
                return sentiment_score <= -sentiment_threshold
            
            return False
            
        except Exception as e:
            self.logger.error(f"Error validating sentiment alignment: {e}")
            return False
    
    def get_sentiment_description(self, sentiment_score: float) -> str:
        """Get human-readable sentiment description"""
        if sentiment_score >= 0.5:
            return "Very Positive"
        elif sentiment_score >= 0.2:
            return "Positive"
        elif sentiment_score > -0.2:
            return "Neutral"
        elif sentiment_score > -0.5:
            return "Negative"
        else:
            return "Very Negative"
