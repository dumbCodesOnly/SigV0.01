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
from api_config import APIConfig

class SentimentAnalyzer:
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.logger = logging.getLogger(__name__)
        self.finnhub_key = config['api_keys'].get('finnhub_key')
        self.newsapi_key = config['api_keys'].get('newsapi_key')
        self.cryptocompare_key = config['api_keys'].get('cryptocompare_key')
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
            finnhub_symbol = APIConfig.get_symbol_mapping(symbol, 'finnhub')
            if not finnhub_symbol:
                return None
            
            # Get recent news with auth params
            params = {'symbol': finnhub_symbol}
            params.update(APIConfig.get_auth_params('finnhub'))
            
            url = APIConfig.get_full_url('sentiment', 'finnhub', 'company_news')
            
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
    
    async def get_coingecko_sentiment(self, symbol: str) -> Optional[float]:
        """
        Get sentiment from CoinGecko API (free tier available)
        """
        try:
            session = await self._get_session()
            
            # Convert symbol to CoinGecko format
            coin_id = self._symbol_to_coingecko_id(symbol)
            if not coin_id:
                return None
            
            url = APIConfig.get_full_url('sentiment', 'coingecko', 'coin_data', id=coin_id)
            params = {'localization': 'false', 'tickers': 'false', 'market_data': 'true', 'community_data': 'true'}
            
            async with session.get(url, params=params) as response:
                if response.status == 200:
                    data = await response.json()
                    
                    # Extract sentiment indicators
                    sentiment_score = 0.0
                    
                    # Market data sentiment
                    market_data = data.get('market_data', {})
                    if market_data:
                        # Price change indicates sentiment
                        price_change_24h = market_data.get('price_change_percentage_24h', 0)
                        price_change_7d = market_data.get('price_change_percentage_7d', 0)
                        
                        # Convert price changes to sentiment (-1 to 1)
                        price_sentiment = (price_change_24h * 0.7 + price_change_7d * 0.3) / 100
                        sentiment_score += min(max(price_sentiment, -0.5), 0.5)
                    
                    # Community sentiment
                    community_data = data.get('community_data', {})
                    if community_data:
                        reddit_posts_48h = community_data.get('reddit_posts_48h', 0)
                        reddit_comments_48h = community_data.get('reddit_comments_48h', 0)
                        
                        # High activity can indicate positive sentiment
                        if reddit_posts_48h > 10 or reddit_comments_48h > 50:
                            sentiment_score += 0.1
                    
                    # Normalize to -1 to 1 range
                    sentiment_score = max(-1.0, min(1.0, sentiment_score))
                    
                    self.logger.info(f"CoinGecko sentiment for {symbol}: {sentiment_score:.2f}")
                    return sentiment_score
                    
                elif response.status == 429:
                    self.logger.warning("CoinGecko API rate limit exceeded")
                    return None
                else:
                    self.logger.warning(f"CoinGecko API error: {response.status}")
                    return None
                    
        except Exception as e:
            self.logger.error(f"Error getting CoinGecko sentiment: {e}")
            return None
    
    def _symbol_to_coingecko_id(self, symbol: str) -> Optional[str]:
        """Convert trading symbol to CoinGecko coin ID"""
        return APIConfig.get_symbol_mapping(symbol, 'coingecko')
    
    async def get_newsapi_sentiment(self, symbol: str) -> Optional[float]:
        """
        Get news sentiment from NewsAPI
        """
        try:
            if not self.newsapi_key:
                return None
            
            session = await self._get_session()
            
            # Convert symbol to search terms
            coin_name = self._symbol_to_coin_name(symbol)
            if not coin_name:
                return None
            
            url = APIConfig.get_full_url('sentiment', 'newsapi', 'everything')
            params = {
                'q': f"{coin_name} cryptocurrency OR {coin_name} crypto",
                'language': 'en',
                'sortBy': 'publishedAt',
                'pageSize': 20
            }
            params.update(APIConfig.get_auth_params('newsapi'))
            
            async with session.get(url, params=params) as response:
                if response.status == 200:
                    data = await response.json()
                    articles = data.get('articles', [])
                    
                    if not articles:
                        return 0.0
                    
                    sentiment_scores = []
                    for article in articles[:10]:  # Analyze first 10 articles
                        title = article.get('title', '')
                        description = article.get('description', '')
                        text = f"{title} {description}"
                        
                        sentiment = self._analyze_text_sentiment(text)
                        sentiment_scores.append(sentiment)
                    
                    if sentiment_scores:
                        avg_sentiment = sum(sentiment_scores) / len(sentiment_scores)
                        self.logger.info(f"NewsAPI sentiment for {symbol}: {avg_sentiment:.2f}")
                        return avg_sentiment
                    
                else:
                    self.logger.warning(f"NewsAPI error: {response.status}")
                    return None
                    
        except Exception as e:
            self.logger.error(f"Error getting NewsAPI sentiment: {e}")
            return None
    
    def _symbol_to_coin_name(self, symbol: str) -> Optional[str]:
        """Convert trading symbol to coin name for news searches"""
        return APIConfig.get_symbol_mapping(symbol, 'coin_names')
    
    async def get_fear_greed_index(self) -> Optional[float]:
        """
        Get Crypto Fear & Greed Index
        """
        try:
            session = await self._get_session()
            
            url = APIConfig.get_full_url('sentiment', 'fear_greed', 'fng')
            
            async with session.get(url) as response:
                if response.status == 200:
                    data = await response.json()
                    
                    if data.get('data') and len(data['data']) > 0:
                        index_value = int(data['data'][0]['value'])
                        
                        # Convert 0-100 scale to -1 to 1 sentiment scale
                        # 0-25: Extreme Fear (-0.8 to -0.4)
                        # 25-45: Fear (-0.4 to -0.1)
                        # 45-55: Neutral (-0.1 to 0.1)
                        # 55-75: Greed (0.1 to 0.4)
                        # 75-100: Extreme Greed (0.4 to 0.8)
                        
                        if index_value <= 25:
                            sentiment = -0.8 + (index_value / 25) * 0.4
                        elif index_value <= 45:
                            sentiment = -0.4 + ((index_value - 25) / 20) * 0.3
                        elif index_value <= 55:
                            sentiment = -0.1 + ((index_value - 45) / 10) * 0.2
                        elif index_value <= 75:
                            sentiment = 0.1 + ((index_value - 55) / 20) * 0.3
                        else:
                            sentiment = 0.4 + ((index_value - 75) / 25) * 0.4
                        
                        self.logger.info(f"Fear & Greed Index: {index_value} -> sentiment: {sentiment:.2f}")
                        return sentiment
                        
                else:
                    self.logger.warning(f"Fear & Greed API error: {response.status}")
                    return None
                    
        except Exception as e:
            self.logger.error(f"Error getting Fear & Greed Index: {e}")
            return None
    
    async def get_social_sentiment(self, symbol: str) -> Optional[float]:
        """
        Get aggregated social sentiment from multiple sources
        """
        try:
            sentiment_sources = []
            
            # Try CoinGecko sentiment
            coingecko_sentiment = await self.get_coingecko_sentiment(symbol)
            if coingecko_sentiment is not None:
                sentiment_sources.append(coingecko_sentiment)
            
            # Try NewsAPI sentiment
            news_sentiment = await self.get_newsapi_sentiment(symbol)
            if news_sentiment is not None:
                sentiment_sources.append(news_sentiment)
            
            if sentiment_sources:
                avg_sentiment = sum(sentiment_sources) / len(sentiment_sources)
                self.logger.info(f"Social sentiment for {symbol}: {avg_sentiment:.2f} (from {len(sentiment_sources)} sources)")
                return avg_sentiment
            else:
                self.logger.info(f"Social sentiment for {symbol}: 0.0 (no data available)")
                return 0.0
            
        except Exception as e:
            self.logger.error(f"Error getting social sentiment: {e}")
            return None
    
    async def get_market_sentiment(self, symbol: str) -> Optional[float]:
        """
        Get overall market sentiment indicators
        """
        try:
            # Use Fear & Greed Index as market sentiment
            fear_greed = await self.get_fear_greed_index()
            if fear_greed is not None:
                self.logger.info(f"Market sentiment for {symbol}: {fear_greed:.2f} (Fear & Greed Index)")
                return fear_greed
            else:
                self.logger.info(f"Market sentiment for {symbol}: 0.0 (no data available)")
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
            
            # Get news sentiment (try multiple sources)
            news_sentiment = await self.get_finnhub_news_sentiment(symbol)
            if news_sentiment is None:
                # Fallback to NewsAPI if Finnhub fails
                news_sentiment = await self.get_newsapi_sentiment(symbol)
            
            if news_sentiment is not None:
                sentiment_scores.append(news_sentiment)
                weights.append(0.5)  # 50% weight for news
            
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
    
    def _analyze_text_sentiment(self, text: str) -> float:
        """
        Simple text sentiment analysis using keyword matching
        Returns sentiment score between -1 and 1
        """
        if not text:
            return 0.0
        
        text = text.lower()
        
        positive_words = [
            'bullish', 'bull', 'rally', 'moon', 'pump', 'surge', 'breakout', 
            'strong', 'support', 'uptrend', 'gain', 'profit', 'buy', 'long',
            'positive', 'good', 'great', 'excellent', 'amazing', 'rising',
            'growth', 'increase', 'higher', 'up', 'green', 'win'
        ]
        
        negative_words = [
            'bearish', 'bear', 'crash', 'dump', 'drop', 'fall', 'breakdown',
            'weak', 'resistance', 'downtrend', 'loss', 'sell', 'short',
            'negative', 'bad', 'terrible', 'awful', 'falling', 'decline',
            'decrease', 'lower', 'down', 'red', 'lose', 'correction'
        ]
        
        positive_count = sum(1 for word in positive_words if word in text)
        negative_count = sum(1 for word in negative_words if word in text)
        
        total_words = positive_count + negative_count
        if total_words == 0:
            return 0.0
        
        # Calculate sentiment score
        sentiment = (positive_count - negative_count) / total_words
        
        # Normalize to reasonable range (-0.5 to 0.5 for keyword analysis)
        return max(-0.5, min(0.5, sentiment))
