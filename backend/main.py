from fastapi import FastAPI, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import Dict, List
from datetime import datetime, timedelta
import logging
import asyncio
import os
import sys
import uvicorn

from fastapi.middleware.cors import CORSMiddleware

# Add the project root to Python path when running directly
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

# Now import with absolute paths to ensure it works in all contexts
from backend.core.database import get_db, NewsArticle, SocialMediaPost, FinancialTerm
from backend.services.rag_service import RAGService
from backend.services.stock_service import StockService
from backend.services.stock_analysis_service import StockAnalysisService
from backend.services.chain_service import ChainService
from backend.scrapers.scraper_service import DataCollectionService, ScraperCoordinator
from backend.services.embedding_service import EmbeddingService
from backend.services.stock_impact_service import StockImpactService
from sqlalchemy import func

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

app = FastAPI(title="Finance News AI")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Or restrict to ["http://localhost:5500"] if needed
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Global instance of the scraper coordinator for use in background tasks
scraper_coordinator = None

# @app.on_event("startup")
# async def startup_event():
#     """Initialize services when the FastAPI app starts"""
#     global scraper_coordinator
#     try:
#         # Get a database session
#         db = next(get_db())
        
#         # Initialize the scraper coordinator
#         scraper_coordinator = ScraperCoordinator(db=db)
        
#         # Start the hourly scraping
#         logger.info("Starting hourly data collection service...")
#         scraper_coordinator.start_scheduled_scraping(interval_minutes=60)
#         logger.info("Hourly data collection service started")
        
#     except Exception as e:
#         logger.error(f"Error starting scraping services: {str(e)}")

@app.on_event("startup")
async def startup_event():
    """Initialize services when the FastAPI app starts"""
    global scraper_coordinator
    try:
        # Get a database session
        db = next(get_db())
        
        # Initialize the scraper coordinator
        scraper_coordinator = ScraperCoordinator(db=db)
        
        # Start the hourly scraping with immediate data collection
        # Note: Hourly updates only include news and social media (not financial terms)
        logger.info("Starting hourly data collection service (news and social media only)...")
        scraper_coordinator.start_scheduled_scraping(interval_minutes=60, run_immediately=True)
        logger.info("Hourly data collection service started with immediate data collection")
        
    except Exception as e:
        logger.error(f"Error starting scraping services: {str(e)}")

@app.on_event("shutdown")
async def shutdown_event():
    """Clean up resources when the FastAPI app shuts down"""
    global scraper_coordinator
    if scraper_coordinator and scraper_coordinator.is_scheduled:
        logger.info("Stopping hourly data collection service...")
        scraper_coordinator.stop_scheduled_scraping()
        logger.info("Hourly data collection service stopped")

@app.get("/")
def read_root():
    return {"message": "Welcome to Finance News AI"}

@app.post("/update-data")
async def update_data(include_financial_terms: bool = True, db: Session = Depends(get_db)):
    """
    Update data sources (news, social media, and optionally financial terms)
    
    Args:
        include_financial_terms: Whether to update financial terms (default: True)
    """
    try:
        # Use the dedicated data collection service instead of RAGService
        collector = DataCollectionService(db)
        new_items = await collector.update_all_data(include_financial_terms=include_financial_terms)
        
        sources_updated = "news, social media" + (", and financial terms" if include_financial_terms else "")
        return {
            "message": f"Added {new_items} new items from {sources_updated} and saved to data directory",
            "financial_terms_included": include_financial_terms
        }
    except Exception as e:
        logger.error(f"Error updating data: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/update-embeddings")
async def update_embeddings(db: Session = Depends(get_db)):
    """Update embeddings for all database items that don't have them"""
    try:
        embedding_service = EmbeddingService(db)
        results = embedding_service.update_all_embeddings()
        
        total_updated = sum(results.values())
        return {
            "message": f"Updated embeddings for {total_updated} items",
            "details": results
        }
    except Exception as e:
        logger.error(f"Error updating embeddings: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/scheduler/status")
def get_scheduler_status():
    """Get current status of the scheduler"""
    global scraper_coordinator
    if not scraper_coordinator:
        return {"status": "not_initialized"}
    
    return {
        "status": "running" if scraper_coordinator.is_scheduled else "stopped",
        "interval_minutes": scraper_coordinator.interval_minutes,
    }

@app.post("/scheduler/start")
def start_scheduler(interval_minutes: int = 60, db: Session = Depends(get_db)):
    """Start the scheduler with a given interval"""
    global scraper_coordinator
    
    if not scraper_coordinator:
        scraper_coordinator = ScraperCoordinator(db=db)
    
    if scraper_coordinator.is_scheduled:
        return {"message": "Scheduler is already running"}
    
    scraper_coordinator.start_scheduled_scraping(interval_minutes=interval_minutes)
    return {"message": f"Started scheduler with {interval_minutes} minute interval"}

@app.post("/scheduler/stop")
def stop_scheduler():
    """Stop the scheduler"""
    global scraper_coordinator
    if not scraper_coordinator or not scraper_coordinator.is_scheduled:
        return {"message": "Scheduler is not running"}
    
    scraper_coordinator.stop_scheduled_scraping()
    return {"message": "Stopped scheduler"}

@app.get("/news")
def get_news(limit: int = 10, db: Session = Depends(get_db)):
    """Get recent news articles"""
    try:
        logger.info(f"Fetching {limit} recent news articles")
        articles = db.query(NewsArticle).order_by(NewsArticle.date.desc()).limit(limit).all()
        logger.info(f"Found {len(articles)} news articles")
        
        results = []
        for article in articles:
            try:
                # Safely handle date formatting
                date_str = article.date.isoformat() if article.date else datetime.now().isoformat()
                
                results.append({
                    "title": article.title,
                    "content": article.content[:200] + "..." if len(article.content) > 200 else article.content,
                    "source": article.source,
                    "url": article.url,
                    "date": date_str
                })
            except Exception as item_error:
                logger.error(f"Error processing article {article.id}: {str(item_error)}")
                # Skip problematic items
                
        logger.info(f"Returning {len(results)} news articles")
        return results
    except Exception as e:
        logger.error(f"Error fetching news: {str(e)}")
        return []

@app.get("/news/impact")
async def get_news_with_impact(limit: int = 10, db: Session = Depends(get_db)):
    """Get recent news articles with stock impact analysis"""
    try:
        logger.info(f"Fetching {limit} recent news articles with stock impact analysis")
        
        # Initialize the stock impact service
        impact_service = StockImpactService(db)
        
        # Analyze recent articles
        impact_results = await impact_service.analyze_recent_articles(limit=limit)
        
        logger.info(f"Found {len(impact_results)} news articles with stock impacts")
        return impact_results
    except Exception as e:
        logger.error(f"Error fetching news with stock impact: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/social")
def get_social_posts(limit: int = 10, db: Session = Depends(get_db)):
    """Get recent social media posts"""
    try:
        logger.info(f"Fetching {limit} recent social media posts")
        posts = db.query(SocialMediaPost).order_by(SocialMediaPost.date.desc()).limit(limit).all()
        logger.info(f"Found {len(posts)} social media posts")
        
        results = []
        for post in posts:
            try:
                # Safely handle date formatting
                date_str = post.date.isoformat() if post.date else datetime.now().isoformat()
                
                results.append({
                    "platform": post.platform,
                    "content": post.content[:200] + "..." if len(post.content) > 200 else post.content,
                    "url": post.url,
                    "date": date_str
                })
            except Exception as item_error:
                logger.error(f"Error processing post {post.id}: {str(item_error)}")
                # Skip problematic items
                
        logger.info(f"Returning {len(results)} social media posts")
        return results
    except Exception as e:
        logger.error(f"Error fetching social media posts: {str(e)}")
        return []

@app.get("/terms")
def get_financial_terms(db: Session = Depends(get_db)):
    """Get all financial terms"""
    terms = db.query(FinancialTerm).all()
    return [
        {
            "term": term.term,
            "definition": term.definition,
            "url": term.url
        }
        for term in terms
    ]

@app.post("/query")
async def query_data(query: Dict[str, str], db: Session = Depends(get_db)):
    """Query the data using natural language"""
    try:
        if "question" not in query:
            raise HTTPException(status_code=400, detail="Question is required")
        
        # Initialize chain service
        chain_service = ChainService(db)
        logger.info(f"Processing question with chain service: {query['question'][:50]}...")
        
        try:
            # Use the chain service to process the question
            result = await chain_service.process_query(query["question"])
            
            # Check if response is well-structured
            if isinstance(result, dict) and "answer" in result:
                return {
                    "answer": result["answer"],
                    "service": "chain",
                    "chain_of_thought": result.get("chain_of_thought", [])
                }
            else:
                # If chain service returned a simple string
                return {"answer": result, "service": "chain"}
                
        except Exception as chain_error:
            # If chain service fails, fall back to RAG service
            logger.warning(f"Chain service error: {str(chain_error)}. Falling back to RAG service.")
            logger.info(f"Processing question with RAG service: {query['question'][:50]}...")
            rag = RAGService(db)
            response = await rag.process_question(query["question"])
            return {"answer": response, "service": "rag"}
        
    except Exception as e:
        logger.error(f"Error processing query: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/stocks")
async def get_stocks(symbols: str = "AAPL,MSFT,GOOGL,AMZN,META"):
    """Get stock data for the specified symbols"""
    try:
        symbol_list = symbols.split(",")
        # Limit to 5 symbols max to prevent abuse
        symbol_list = symbol_list[:5]
        stock_data = await StockService.get_multiple_stocks(symbol_list)
        return stock_data
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/stock/{symbol}")
async def get_stock(symbol: str, period: str = "1d", interval: str = "15m"):
    """Get detailed stock data for a specific symbol"""
    try:
        stock_data = await StockService.get_stock_data(symbol, period, interval)
        if "error" in stock_data:
            raise HTTPException(status_code=404, detail=stock_data["error"])
        return stock_data
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/stock-analysis/{symbol}")
async def analyze_stock(symbol: str, days: int = 30, db: Session = Depends(get_db)):
    """
    Analyze a stock using price data, news sentiment, and social media trends
    
    Args:
        symbol: Stock ticker symbol
        days: Number of days to look back for analysis (default: 30)
        
    Returns:
        Dict containing comprehensive analysis results
    """
    try:
        logger.info(f"Received request to analyze stock {symbol} with {days} days lookback")
        
        # Validate inputs
        if days < 5 or days > 365:
            raise HTTPException(status_code=400, detail="Days must be between 5 and 365")
            
        # Initialize analysis service with database session
        analyzer = StockAnalysisService(db)
        
        # Perform comprehensive analysis
        analysis = await analyzer.analyze_stock(symbol, days_lookback=days)
        
        # Check for errors
        if "error" in analysis:
            raise HTTPException(status_code=404, detail=analysis["error"])
            
        return analysis
    except HTTPException:
        # Re-raise HTTP exceptions
        raise
    except Exception as e:
        logger.error(f"Error analyzing stock {symbol}: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to analyze stock: {str(e)}")

if __name__ == "__main__":
    # Run the FastAPI app directly with uvicorn
    print("Starting server at http://localhost:8000...")
    uvicorn.run(app, host="0.0.0.0", port=8000)

