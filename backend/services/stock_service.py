import yfinance as yf
from datetime import datetime, timedelta
from typing import Dict, List, Optional
import logging
import random
import traceback
import time
import threading
import functools

logger = logging.getLogger(__name__)

# Cache for stock data to reduce API calls
STOCK_CACHE = {}
CACHE_DURATION = 300  # Cache duration in seconds (5 minutes)
CACHE_LOCK = threading.RLock()  # Lock for thread-safe cache access

def timed_cache(seconds=CACHE_DURATION):
    """Decorator to cache function results for a specified duration"""
    def decorator(func):
        @functools.wraps(func)
        async def wrapper(*args, **kwargs):
            key = str(args) + str(kwargs)
            
            with CACHE_LOCK:
                # Check if result is in cache and still valid
                if key in STOCK_CACHE:
                    timestamp, result = STOCK_CACHE[key]
                    if datetime.now().timestamp() - timestamp < seconds:
                        logger.info(f"Using cached result for {key}")
                        return result
            
            # Get fresh result
            result = await func(*args, **kwargs)
            
            # Store in cache
            with CACHE_LOCK:
                STOCK_CACHE[key] = (datetime.now().timestamp(), result)
            
            return result
        return wrapper
    return decorator

class StockService:
    """Service for retrieving stock price data using yfinance"""
    
    @staticmethod
    @timed_cache(seconds=300)
    async def get_stock_data(symbol: str, period: str = "1d", interval: str = "15m") -> Dict:
        """
        Get stock data for a specific symbol
        
        Args:
            symbol: Stock ticker symbol (e.g., 'AAPL')
            period: Time period (e.g., '1d', '5d', '1mo')
            interval: Time interval (e.g., '15m', '1h', '1d')
            
        Returns:
            Dict containing stock data
        """
        logger.info(f"Fetching stock data for {symbol} with period={period}, interval={interval}")
        start_time = time.time()
        
        try:
            # Use a timeout for yfinance operations
            ticker = yf.Ticker(symbol)
            logger.info(f"Successfully created yfinance ticker for {symbol}")
            
            # Limit the amount of data we get based on period
            max_points = 30
            if '1d' in period:
                max_points = 20
            elif '5d' in period:
                max_points = 30
            elif 'mo' in period:
                max_points = 40
            
            hist = ticker.history(period=period, interval=interval)
            logger.info(f"Got history for {symbol} with {len(hist)} data points")
            
            # Check if we got valid data
            if hist.empty:
                logger.warning(f"No data returned for {symbol}, falling back to mock data")
                return StockService._generate_mock_data(symbol, period, interval)
            
            # Format the data - limit the number of points for performance
            data_points = []
            try:
                # Only take the most recent points up to max_points
                recent_hist = hist.tail(max_points)
                for index, row in recent_hist.iterrows():
                    data_points.append({
                        "timestamp": index.isoformat(),
                        "open": float(row["Open"]),
                        "high": float(row["High"]),
                        "low": float(row["Low"]),
                        "close": float(row["Close"]),
                        "volume": int(row["Volume"])
                    })
                logger.info(f"Formatted {len(data_points)} data points for {symbol}")
            except Exception as format_err:
                logger.error(f"Error formatting data for {symbol}: {str(format_err)}")
                logger.error(traceback.format_exc())
                return StockService._generate_mock_data(symbol, period, interval)
            
            # Get basic company info - minimal info to improve performance
            try:
                company_name = ticker.info.get("shortName", symbol)
                current_price = data_points[-1]["close"] if data_points else None
                currency = ticker.info.get("currency", "USD")
                logger.info(f"Got company info for {symbol}: {company_name}")
            except Exception as info_err:
                logger.error(f"Error getting company info for {symbol}: {str(info_err)}")
                logger.error(traceback.format_exc())
                # Use fallback values
                company_name = symbol
                current_price = data_points[-1]["close"] if data_points else None
                currency = "USD"
            
            elapsed = time.time() - start_time
            logger.info(f"Stock data fetched for {symbol} in {elapsed:.2f} seconds")
            
            return {
                "symbol": symbol,
                "company_name": company_name,
                "current_price": current_price,
                "currency": currency,
                "data": data_points
            }
        except Exception as e:
            elapsed = time.time() - start_time
            logger.error(f"Failed to get ticker '{symbol}' in {elapsed:.2f}s, reason: {str(e)}")
            logger.error(traceback.format_exc())
            # If API fails, return mock data for demo purposes
            return StockService._generate_mock_data(symbol, period, interval)
    
    @staticmethod
    @timed_cache(seconds=300)
    async def get_multiple_stocks(symbols: List[str]) -> List[Dict]:
        """
        Get stock data for multiple symbols
        
        Args:
            symbols: List of stock ticker symbols
            
        Returns:
            List of dictionaries containing stock data
        """
        logger.info(f"Fetching data for multiple stocks: {symbols}")
        start_time = time.time()
        results = []
        
        # Limit to 5 stocks maximum for performance
        symbols = symbols[:5]
        
        # Batch processing to improve performance
        try:
            # Create a simple batch request using yfinance Tickers
            tickers = yf.Tickers(' '.join(symbols))
            logger.info(f"Created Tickers object for {symbols}")
            
            # Process each symbol
            for symbol in symbols:
                try:
                    # First try to get from the batch
                    ticker = tickers.tickers[symbol]
                    hist = ticker.history(period="1d")
                    
                    if hist.empty:
                        # Fall back to individual request if batch fails
                        logger.warning(f"No batch data for {symbol}, falling back to individual request")
                        data = await StockService.get_stock_data(symbol)
                    else:
                        # Extract just what we need from the batch data
                        company_name = ticker.info.get("shortName", symbol)
                        current_price = float(hist["Close"].iloc[-1]) if not hist.empty else None
                        currency = ticker.info.get("currency", "USD")
                        
                        data = {
                            "symbol": symbol,
                            "company_name": company_name,
                            "current_price": current_price,
                            "currency": currency
                        }
                    
                    # Only include key information for multiple stocks
                    if "error" not in data:
                        results.append({
                            "symbol": data["symbol"],
                            "company_name": data["company_name"],
                            "current_price": data["current_price"],
                            "currency": data.get("currency", "USD")
                        })
                    else:
                        results.append({"symbol": symbol, "error": data["error"]})
                        
                except Exception as e:
                    logger.error(f"Error processing symbol {symbol}: {str(e)}")
                    logger.error(traceback.format_exc())
                    # Include fallback data
                    results.append({
                        "symbol": symbol,
                        "company_name": f"{symbol} Inc.",
                        "current_price": 100.0,  # Placeholder value
                        "currency": "USD",
                        "note": "Error fetching data, using placeholder"
                    })
        except Exception as batch_error:
            logger.error(f"Batch processing failed: {str(batch_error)}")
            # Fall back to individual requests
            for symbol in symbols:
                try:
                    data = await StockService.get_stock_data(symbol)
                    if "error" not in data:
                        results.append({
                            "symbol": data["symbol"],
                            "company_name": data["company_name"],
                            "current_price": data["current_price"],
                            "currency": data.get("currency", "USD")
                        })
                    else:
                        results.append({"symbol": symbol, "error": data["error"]})
                except Exception as e:
                    logger.error(f"Error processing symbol {symbol}: {str(e)}")
                    results.append({
                        "symbol": symbol,
                        "company_name": f"{symbol} Inc.",
                        "current_price": 100.0,
                        "currency": "USD",
                        "note": "Error fetching data, using placeholder"
                    })
        
        elapsed = time.time() - start_time
        logger.info(f"Returning data for {len(results)} symbols in {elapsed:.2f} seconds")
        return results
    
    @staticmethod
    def _generate_mock_data(symbol: str, period: str, interval: str) -> Dict:
        """Generate mock stock data for demo purposes when API is unavailable"""
        logger.info(f"Generating mock data for {symbol}")
        # Company name mapping for common symbols
        company_names = {
            "AAPL": "Apple Inc.",
            "MSFT": "Microsoft Corporation",
            "GOOGL": "Alphabet Inc.",
            "AMZN": "Amazon.com, Inc.",
            "META": "Meta Platforms, Inc.",
            "TSLA": "Tesla, Inc.",
            "NVDA": "NVIDIA Corporation",
            "NFLX": "Netflix, Inc."
        }
        
        # Generate base price based on symbol hash
        base_price = sum(ord(c) for c in symbol) % 1000
        if base_price < 50:
            base_price += 50
            
        # Generate mock data points
        now = datetime.now()
        data_points = []
        
        # Determine number of points based on period and interval
        num_points = 20  # Default
        if period == "1d" and interval == "15m":
            num_points = 20
        elif period == "5d":
            num_points = 30
        elif "mo" in period:
            num_points = 40
        elif "y" in period:
            num_points = 50
        
        # Generate price movements
        for i in range(num_points):
            point_time = now - timedelta(hours=num_points-i)
            price_change = (random.random() - 0.5) * base_price * 0.02
            price = base_price * (1 + (i - num_points//2) * 0.001) + price_change
            
            data_points.append({
                "timestamp": point_time.isoformat(),
                "open": price - random.random() * 2,
                "high": price + random.random() * 3,
                "low": price - random.random() * 3,
                "close": price,
                "volume": int(random.random() * 1000000)
            })
            
        current_price = data_points[-1]["close"] if data_points else base_price
        
        return {
            "symbol": symbol,
            "company_name": company_names.get(symbol, f"{symbol} Inc."),
            "current_price": current_price,
            "currency": "USD",
            "data": data_points,
            "note": "Demo data (API unavailable)"
        } 