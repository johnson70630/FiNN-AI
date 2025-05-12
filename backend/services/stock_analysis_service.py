import yfinance as yf
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
import logging
from sqlalchemy.orm import Session
from collections import Counter
import re
import asyncio

from backend.core.database import NewsArticle, SocialMediaPost, get_db
from backend.services.stock_service import StockService

logger = logging.getLogger(__name__)

class StockAnalysisService:
    """Service for analyzing stock data combined with news and social media sentiment"""
    
    def __init__(self, db: Session):
        """Initialize with a database session"""
        self.db = db
    
    async def analyze_stock(self, symbol: str, days_lookback: int = 30) -> Dict:
        """
        Perform comprehensive analysis on a stock, including:
        - Price trend analysis
        - News sentiment analysis
        - Social media sentiment analysis
        - Volume analysis
        - Correlation with relevant factors
        
        Args:
            symbol: Stock ticker symbol
            days_lookback: Number of days to look back for analysis
            
        Returns:
            Dict containing analysis results
        """
        logger.info(f"Starting comprehensive analysis for {symbol} with {days_lookback} days lookback")
        
        # Get stock data
        stock_data = await StockService.get_stock_data(symbol, period=f"{days_lookback}d", interval="1d")
        if "error" in stock_data:
            return {"error": f"Failed to retrieve stock data: {stock_data['error']}"}
        
        # Convert to pandas DataFrame for analysis
        if not stock_data.get("data"):
            return {"error": "No stock data available for analysis"}
            
        price_df = pd.DataFrame(stock_data["data"])
        price_df["timestamp"] = pd.to_datetime(price_df["timestamp"])
        price_df.set_index("timestamp", inplace=True)
        price_df.sort_index(inplace=True)
        
        # Get company name
        company_name = stock_data.get("company_name", symbol)
        
        # Collect all analyses
        results = {
            "symbol": symbol,
            "company_name": company_name,
            "analysis_date": datetime.now().isoformat(),
            "days_analyzed": days_lookback,
            "current_price": stock_data.get("current_price"),
            "currency": stock_data.get("currency", "USD"),
        }
        
        # Run all analyses in parallel
        price_analysis, news_analysis, social_analysis, combined_analysis = await asyncio.gather(
            self._analyze_price_trends(price_df, symbol),
            self._analyze_news_sentiment(symbol, company_name, days_lookback),
            self._analyze_social_sentiment(symbol, company_name, days_lookback),
            self._calculate_combined_signal(price_df, symbol, company_name, days_lookback)
        )
        
        # Combine all analyses
        results.update(price_analysis)
        results.update(news_analysis)
        results.update(social_analysis)
        results.update(combined_analysis)
        
        logger.info(f"Completed analysis for {symbol}")
        return results
    
    async def _analyze_price_trends(self, price_df: pd.DataFrame, symbol: str) -> Dict:
        """Analyze price trends from historical data"""
        logger.info(f"Analyzing price trends for {symbol}")
        
        if len(price_df) < 2:
            return {"price_analysis": {"error": "Not enough price data for analysis"}}
            
        try:
            # Calculate basic metrics
            price_change = price_df["close"].pct_change().dropna()
            
            # Calculate moving averages
            ma_short = price_df["close"].rolling(window=5).mean().iloc[-1] if len(price_df) >= 5 else None
            ma_long = price_df["close"].rolling(window=20).mean().iloc[-1] if len(price_df) >= 20 else None
            
            # Determine trend
            latest_price = price_df["close"].iloc[-1]
            earliest_price = price_df["close"].iloc[0]
            total_change_pct = ((latest_price - earliest_price) / earliest_price) * 100
            
            # Calculate volatility
            volatility = price_change.std() * 100  # Convert to percentage
            
            # Determine if price is above or below moving averages
            above_ma_short = bool(latest_price > ma_short) if ma_short is not None else None
            above_ma_long = bool(latest_price > ma_long) if ma_long is not None else None
            
            # Recent momentum (last 5 days)
            recent_momentum = price_df["close"].pct_change(5).iloc[-1] * 100 if len(price_df) >= 6 else None
            
            # Determine trend strength
            if abs(total_change_pct) < 3:
                trend_strength = "sideways"
            elif abs(total_change_pct) < 8:
                trend_strength = "weak"
            elif abs(total_change_pct) < 15:
                trend_strength = "moderate"
            else:
                trend_strength = "strong"
                
            trend_direction = "upward" if total_change_pct > 0 else "downward"
            
            # Price analysis summary
            if total_change_pct > 0:
                if above_ma_short and above_ma_long:
                    summary = f"{symbol} is in a {trend_strength} uptrend, trading above both short and long-term moving averages"
                elif above_ma_short:
                    summary = f"{symbol} is in a {trend_strength} uptrend, but only above short-term moving average"
                else:
                    summary = f"{symbol} has been rising but may be facing resistance as it's below moving averages"
            else:
                if not above_ma_short and not above_ma_long:
                    summary = f"{symbol} is in a {trend_strength} downtrend, trading below both short and long-term moving averages"
                elif not above_ma_short:
                    summary = f"{symbol} is in a {trend_strength} downtrend, recently breaking below short-term moving average"
                else:
                    summary = f"{symbol} has been falling but may find support at the long-term moving average"
                    
            return {
                "price_analysis": {
                    "total_change_pct": round(total_change_pct, 2),
                    "trend": trend_direction,
                    "trend_strength": trend_strength,
                    "volatility_pct": round(volatility, 2),
                    "above_short_ma": above_ma_short,
                    "above_long_ma": above_ma_long,
                    "recent_momentum": round(recent_momentum, 2) if recent_momentum is not None else None,
                    "summary": summary
                }
            }
        except Exception as e:
            logger.error(f"Error in price trend analysis for {symbol}: {str(e)}")
            return {"price_analysis": {"error": f"Error in price analysis: {str(e)}"}}
    
    async def _analyze_news_sentiment(self, symbol: str, company_name: str, days_lookback: int) -> Dict:
        """Analyze news sentiment for a stock"""
        logger.info(f"Analyzing news sentiment for {symbol} ({company_name})")
        
        try:
            # Calculate date range
            end_date = datetime.now()
            start_date = end_date - timedelta(days=days_lookback)
            
            # Query relevant news articles
            search_terms = [symbol, company_name]
            
            # For companies with simple names, avoid too many false positives
            if len(company_name.split()) == 1 and company_name.lower() not in ["apple", "amazon", "google", "microsoft", "meta"]:
                search_terms = [symbol]  # Just use the ticker symbol
                
            news_query = self.db.query(NewsArticle).filter(
                NewsArticle.date.between(start_date, end_date)
            ).order_by(NewsArticle.date.desc()).all()
            
            relevant_news = []
            for article in news_query:
                if any(term.lower() in article.title.lower() or term.lower() in article.content.lower() 
                       for term in search_terms):
                    relevant_news.append(article)
            
            if not relevant_news:
                return {"news_analysis": {"articles_found": 0, "summary": "No relevant news found for analysis"}}
                
            # Simple sentiment analysis
            positive_words = ["bullish", "growth", "profit", "gain", "positive", "buy", "upward", "outperform", 
                             "beat", "strong", "success", "opportunity", "upgrade", "innovation", "partnership"]
            negative_words = ["bearish", "loss", "decline", "drop", "negative", "sell", "downward", "underperform", 
                             "miss", "weak", "failure", "risk", "downgrade", "layoff", "lawsuit"]
            
            pos_count = 0
            neg_count = 0
            article_sentiments = []
            article_summaries = []
            
            for article in relevant_news[:10]:  # Analyze up to 10 most recent articles
                title_and_content = f"{article.title} {article.content}".lower()
                
                # Count sentiment words
                article_pos = sum(1 for word in positive_words if word in title_and_content)
                article_neg = sum(1 for word in negative_words if word in title_and_content)
                
                pos_count += article_pos
                neg_count += article_neg
                
                # Determine article sentiment
                sentiment = "neutral"
                if article_pos > article_neg * 1.5:
                    sentiment = "positive"
                elif article_neg > article_pos * 1.5:
                    sentiment = "negative"
                    
                article_sentiments.append(sentiment)
                
                # Create article summary
                article_summaries.append({
                    "title": article.title,
                    "date": article.date.isoformat(),
                    "source": article.source,
                    "sentiment": sentiment,
                    "url": article.url
                })
            
            # Overall sentiment analysis
            sentiment_counts = Counter(article_sentiments)
            if sentiment_counts["positive"] > sentiment_counts["negative"] * 1.5:
                overall_sentiment = "positive"
                sentiment_strength = "strong" if sentiment_counts["positive"] > 2 * sentiment_counts["neutral"] else "moderate"
            elif sentiment_counts["negative"] > sentiment_counts["positive"] * 1.5:
                overall_sentiment = "negative"
                sentiment_strength = "strong" if sentiment_counts["negative"] > 2 * sentiment_counts["neutral"] else "moderate"
            else:
                overall_sentiment = "neutral"
                sentiment_strength = "balanced"
                
            # Generate summary
            if overall_sentiment == "positive":
                sentiment_summary = f"News sentiment for {symbol} is {sentiment_strength} positive. Recent articles highlight potential upside."
            elif overall_sentiment == "negative":
                sentiment_summary = f"News sentiment for {symbol} is {sentiment_strength} negative. Recent articles indicate caution is warranted."
            else:
                sentiment_summary = f"News sentiment for {symbol} is mixed or neutral. No clear positive or negative bias in recent coverage."
            
            return {
                "news_analysis": {
                    "articles_found": len(relevant_news),
                    "articles_analyzed": len(article_sentiments),
                    "sentiment": overall_sentiment,
                    "sentiment_strength": sentiment_strength,
                    "positive_count": sentiment_counts["positive"],
                    "neutral_count": sentiment_counts["neutral"],
                    "negative_count": sentiment_counts["negative"],
                    "recent_articles": article_summaries,
                    "summary": sentiment_summary
                }
            }
            
        except Exception as e:
            logger.error(f"Error in news sentiment analysis for {symbol}: {str(e)}")
            return {"news_analysis": {"error": f"Error in news analysis: {str(e)}"}}
    
    async def _analyze_social_sentiment(self, symbol: str, company_name: str, days_lookback: int) -> Dict:
        """Analyze social media sentiment for a stock"""
        logger.info(f"Analyzing social media sentiment for {symbol} ({company_name})")
        
        try:
            # Calculate date range
            end_date = datetime.now()
            start_date = end_date - timedelta(days=days_lookback)
            
            # Query relevant social media posts
            search_terms = [symbol, company_name]
            
            # For companies with simple names, avoid too many false positives
            if len(company_name.split()) == 1 and company_name.lower() not in ["apple", "amazon", "google", "microsoft", "meta"]:
                search_terms = [symbol]  # Just use the ticker symbol
                
            posts_query = self.db.query(SocialMediaPost).filter(
                SocialMediaPost.date.between(start_date, end_date)
            ).order_by(SocialMediaPost.date.desc()).all()
            
            relevant_posts = []
            for post in posts_query:
                if any(term.lower() in post.content.lower() for term in search_terms):
                    relevant_posts.append(post)
            
            if not relevant_posts:
                return {"social_analysis": {"posts_found": 0, "summary": "No relevant social media posts found for analysis"}}
                
            # Simple sentiment analysis
            positive_words = ["bullish", "growth", "profit", "gain", "positive", "buy", "upward", "moon", "rich", 
                             "beat", "strong", "success", "opportunity", "upgrade", "innovation", "partnership", "rocket", "🚀", "💪", "🔥"]
            negative_words = ["bearish", "loss", "decline", "drop", "negative", "sell", "downward", "crash", "poor", 
                             "miss", "weak", "failure", "risk", "downgrade", "layoff", "lawsuit", "scam", "💩", "📉", "🔻"]
            
            pos_count = 0
            neg_count = 0
            post_sentiments = []
            post_summaries = []
            
            for post in relevant_posts[:20]:  # Analyze up to 20 most recent posts
                content = post.content.lower()
                
                # Count sentiment words
                post_pos = sum(1 for word in positive_words if word in content)
                post_neg = sum(1 for word in negative_words if word in content)
                
                pos_count += post_pos
                neg_count += post_neg
                
                # Determine post sentiment
                sentiment = "neutral"
                if post_pos > post_neg * 1.5:
                    sentiment = "positive"
                elif post_neg > post_pos * 1.5:
                    sentiment = "negative"
                    
                post_sentiments.append(sentiment)
                
                # Create post summary
                post_summaries.append({
                    "platform": post.platform,
                    "date": post.date.isoformat(),
                    "sentiment": sentiment,
                    "url": post.url
                })
            
            # Overall sentiment analysis
            sentiment_counts = Counter(post_sentiments)
            if sentiment_counts["positive"] > sentiment_counts["negative"] * 1.5:
                overall_sentiment = "positive"
                sentiment_strength = "strong" if sentiment_counts["positive"] > 2 * sentiment_counts["neutral"] else "moderate"
            elif sentiment_counts["negative"] > sentiment_counts["positive"] * 1.5:
                overall_sentiment = "negative"
                sentiment_strength = "strong" if sentiment_counts["negative"] > 2 * sentiment_counts["neutral"] else "moderate"
            else:
                overall_sentiment = "neutral"
                sentiment_strength = "balanced"
                
            # Generate summary
            if overall_sentiment == "positive":
                sentiment_summary = f"Social media sentiment for {symbol} is {sentiment_strength} positive. Retail investors appear bullish."
            elif overall_sentiment == "negative":
                sentiment_summary = f"Social media sentiment for {symbol} is {sentiment_strength} negative. Retail investors express concerns."
            else:
                sentiment_summary = f"Social media sentiment for {symbol} is mixed or neutral. No clear consensus among retail investors."
            
            return {
                "social_analysis": {
                    "posts_found": len(relevant_posts),
                    "posts_analyzed": len(post_sentiments),
                    "sentiment": overall_sentiment,
                    "sentiment_strength": sentiment_strength,
                    "positive_count": sentiment_counts["positive"],
                    "neutral_count": sentiment_counts["neutral"],
                    "negative_count": sentiment_counts["negative"],
                    "platforms": list(set(post.platform for post in relevant_posts)),
                    "recent_posts": post_summaries[:5],  # Only include a few examples
                    "summary": sentiment_summary
                }
            }
            
        except Exception as e:
            logger.error(f"Error in social media sentiment analysis for {symbol}: {str(e)}")
            return {"social_analysis": {"error": f"Error in social media analysis: {str(e)}"}}
    
    async def _calculate_combined_signal(self, price_df: pd.DataFrame, symbol: str, company_name: str, days_lookback: int) -> Dict:
        """Calculate a combined signal based on all analysis factors"""
        logger.info(f"Calculating combined signal for {symbol}")
        
        try:
            # Get price trend from the dataframe
            if len(price_df) >= 2:
                latest_price = price_df["close"].iloc[-1]
                earliest_price = price_df["close"].iloc[0]
                price_trend = ((latest_price - earliest_price) / earliest_price) * 100
            else:
                price_trend = 0
                
            # Get volume trend if available
            volume_trend = 0
            if "volume" in price_df.columns and len(price_df) >= 10:
                recent_volume_avg = price_df["volume"].iloc[-5:].mean()
                earlier_volume_avg = price_df["volume"].iloc[-10:-5].mean()
                if earlier_volume_avg > 0:
                    volume_trend = ((recent_volume_avg - earlier_volume_avg) / earlier_volume_avg) * 100
            
            # Prepare combined analysis
            combined = {
                "combined_analysis": {
                    "signal_factors": [],
                    "overall_signal": "neutral",
                    "confidence": "low",
                    "reasoning": []
                }
            }
            
            # Add price trend as a factor
            if abs(price_trend) >= 5:
                direction = "bullish" if price_trend > 0 else "bearish"
                strength = "strong" if abs(price_trend) > 10 else "moderate"
                combined["combined_analysis"]["signal_factors"].append({
                    "factor": "price_trend",
                    "signal": direction,
                    "strength": strength,
                    "description": f"Price trend is {round(price_trend, 2)}% over analyzed period" 
                })
                combined["combined_analysis"]["reasoning"].append(
                    f"{'Positive' if price_trend > 0 else 'Negative'} price trend of {round(price_trend, 2)}%"
                )
            
            # Add volume trend as a factor if significant
            if abs(volume_trend) >= 20:
                direction = "bullish" if volume_trend > 0 and price_trend > 0 else "bearish"
                combined["combined_analysis"]["signal_factors"].append({
                    "factor": "volume_trend",
                    "signal": direction,
                    "strength": "moderate",
                    "description": f"Volume has {'increased' if volume_trend > 0 else 'decreased'} by {round(volume_trend, 2)}%"
                })
                combined["combined_analysis"]["reasoning"].append(
                    f"{'Increasing' if volume_trend > 0 else 'Decreasing'} trading volume"
                )
            
            # Determine overall signal based on factors
            bullish_factors = sum(1 for factor in combined["combined_analysis"]["signal_factors"] 
                                  if factor["signal"] == "bullish")
            bearish_factors = sum(1 for factor in combined["combined_analysis"]["signal_factors"] 
                                 if factor["signal"] == "bearish")
            
            # Set default values
            combined["combined_analysis"]["overall_signal"] = "neutral"
            combined["combined_analysis"]["confidence"] = "low"
            
            # Calculate overall signal and confidence
            total_factors = bullish_factors + bearish_factors
            if total_factors > 0:
                if bullish_factors > bearish_factors:
                    combined["combined_analysis"]["overall_signal"] = "bullish"
                    combined["combined_analysis"]["reasoning"].insert(0, f"More bullish factors ({bullish_factors}) than bearish factors ({bearish_factors})")
                elif bearish_factors > bullish_factors:
                    combined["combined_analysis"]["overall_signal"] = "bearish"
                    combined["combined_analysis"]["reasoning"].insert(0, f"More bearish factors ({bearish_factors}) than bullish factors ({bullish_factors})")
                    
                # Set confidence based on factor agreement
                if total_factors == 1:
                    combined["combined_analysis"]["confidence"] = "low"
                elif total_factors == 2:
                    combined["combined_analysis"]["confidence"] = "moderate"
                else:
                    combined["combined_analysis"]["confidence"] = "high"
            
            # Generate final recommendation based on signal and confidence
            signal = combined["combined_analysis"]["overall_signal"]
            confidence = combined["combined_analysis"]["confidence"]
            
            if signal == "bullish" and confidence == "high":
                recommendation = f"Strong Buy - Multiple indicators suggest {symbol} has significant upside potential"
            elif signal == "bullish" and confidence == "moderate":
                recommendation = f"Buy - Several indicators point to {symbol} having positive momentum"
            elif signal == "bullish" and confidence == "low":
                recommendation = f"Weak Buy - Some indicators suggest {symbol} may perform positively"
            elif signal == "bearish" and confidence == "high":
                recommendation = f"Strong Sell - Multiple indicators suggest {symbol} may face significant downward pressure"
            elif signal == "bearish" and confidence == "moderate":
                recommendation = f"Sell - Several indicators point to {symbol} having negative momentum"
            elif signal == "bearish" and confidence == "low":
                recommendation = f"Weak Sell - Some indicators suggest {symbol} may underperform"
            else:
                recommendation = f"Hold/Neutral - No clear directional signal for {symbol} at this time"
                
            combined["combined_analysis"]["recommendation"] = recommendation
            
            return combined
            
        except Exception as e:
            logger.error(f"Error in combined signal calculation for {symbol}: {str(e)}")
            return {"combined_analysis": {"error": f"Error in combined analysis: {str(e)}"}} 