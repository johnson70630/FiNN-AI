"""
Stock Impact Service - Analyzes news articles to determine which stocks might be impacted.

This service uses NLP techniques to extract company mentions, analyze sentiment,
and predict potential impact on stocks based on news content.
"""

import os
import re
import logging
import openai
from typing import List, Dict, Any, Optional, Tuple
from dotenv import load_dotenv
from sqlalchemy.orm import Session
from datetime import datetime

from backend.core.database import NewsArticle

# Major US stock tickers and their company names
MAJOR_STOCKS = {
    "AAPL": "Apple",
    "MSFT": "Microsoft",
    "AMZN": "Amazon",
    "GOOGL": "Google",
    "GOOG": "Google",
    "META": "Meta",
    "NVDA": "NVIDIA",
    "TSLA": "Tesla",
    "BRK.A": "Berkshire Hathaway",
    "BRK.B": "Berkshire Hathaway",
    "JPM": "JPMorgan Chase",
    "V": "Visa",
    "PG": "Procter & Gamble",
    "UNH": "UnitedHealth",
    "HD": "Home Depot",
    "MA": "Mastercard",
    "JNJ": "Johnson & Johnson",
    "DIS": "Disney",
    "BAC": "Bank of America",
    "XOM": "Exxon Mobil",
    "PFE": "Pfizer",
    "WMT": "Walmart",
    "INTC": "Intel",
    "VZ": "Verizon",
    "CSCO": "Cisco",
    "ADBE": "Adobe",
    "CRM": "Salesforce",
    "NFLX": "Netflix",
    "PYPL": "PayPal",
    "CMCSA": "Comcast",
    "KO": "Coca-Cola",
    "COST": "Costco",
    "NKE": "Nike",
    "T": "AT&T",
    "PEP": "PepsiCo",
    "AMD": "AMD",
    "ABBV": "AbbVie",
    "MRK": "Merck",
    "TMO": "Thermo Fisher Scientific",
    "AVGO": "Broadcom",
    "ACN": "Accenture",
    "ORCL": "Oracle",
    "MCD": "McDonald's",
    "IBM": "IBM",
    "TXN": "Texas Instruments",
    "QCOM": "Qualcomm"
}

# Configure logging
logger = logging.getLogger(__name__)
load_dotenv()

class StockImpactService:
    def __init__(self, db: Session):
        """Initialize the stock impact service"""
        self.db = db
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise ValueError("OPENAI_API_KEY is required for stock impact analysis")
        
        # For caching analyzed articles to avoid re-analysis
        self.analyzed_articles = {}
        
    def _extract_companies_regex(self, text: str) -> List[str]:
        """Extract company names and tickers using regex patterns"""
        companies = []
        
        # Look for stock tickers (capitalized 1-5 letter words)
        ticker_pattern = r'\b[A-Z]{1,5}\b'
        potential_tickers = re.findall(ticker_pattern, text)
        
        # Filter to only known major tickers
        for ticker in potential_tickers:
            if ticker in MAJOR_STOCKS:
                companies.append(ticker)
        
        # Look for company names
        for ticker, company in MAJOR_STOCKS.items():
            if company.lower() in text.lower():
                if ticker not in companies:
                    companies.append(ticker)
        
        return companies

    async def analyze_article_impact(self, article: NewsArticle) -> Dict[str, Any]:
        """Analyze which stocks might be impacted by a specific news article"""
        # Check if we've already analyzed this article
        if article.id in self.analyzed_articles:
            return self.analyzed_articles[article.id]
        
        # Combine title and content for analysis
        text = f"{article.title} {article.content}"
        
        # Step 1: Extract companies mentioned in the article using regex
        companies = self._extract_companies_regex(text)
        
        # Step 2: If no companies found with regex or the article seems complex,
        # use the OpenAI API for more advanced analysis
        if not companies or len(article.content) > 500:
            try:
                companies, impact_analysis = await self._analyze_with_openai(article)
            except Exception as e:
                logger.warning(f"OpenAI analysis failed: {str(e)}. Falling back to regex results.")
                # Use regex results if OpenAI fails
                impact_analysis = "Unable to perform detailed impact analysis."
        else:
            # For shorter articles with clear mentions, create a basic impact analysis
            impact_analysis = f"This news may impact {', '.join(companies)} based on direct mentions."
        
        # Assemble the result
        result = {
            "article_id": article.id,
            "title": article.title,
            "date": article.date,
            "source": article.source,
            "impacted_stocks": companies,
            "impact_analysis": impact_analysis
        }
        
        # Cache the result
        self.analyzed_articles[article.id] = result
        return result
    
    async def _analyze_with_openai(self, article: NewsArticle) -> Tuple[List[str], str]:
        """Use OpenAI to analyze an article for stock impacts"""
        try:
            client = openai.OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
            combined_text = f"Title: {article.title}\nContent: {article.content}\nSource: {article.source}\nDate: {article.date}"
            
            response = client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": """
                    You are a financial analyst specializing in identifying stock market impacts from news.
                    Analyze the provided news article to:
                    1. Identify which specific stock tickers might be impacted
                    2. Provide a brief analysis of the potential impact
                    Focus on major US stocks. If the news is unrelated to any specific stock, say so.
                    """},
                    {"role": "user", "content": f"""
                    Analyze this financial news article to determine which stocks may be impacted.
                    Return your response in the following format:
                    
                    Impacted Stocks: [comma-separated list of stock tickers, or "None" if none]
                    Impact Analysis: [brief 1-2 sentence analysis explaining why these stocks may be impacted]
                    
                    Here's the article:
                    {combined_text}
                    """}
                ],
                temperature=0.5,
                max_tokens=300
            )
            
            analysis = response.choices[0].message.content.strip()
            
            # Parse the response
            stocks_match = re.search(r'Impacted Stocks:\s*(.+)', analysis)
            analysis_match = re.search(r'Impact Analysis:\s*(.+)', analysis, re.DOTALL)
            
            stocks_text = stocks_match.group(1) if stocks_match else "None"
            impact_text = analysis_match.group(1).strip() if analysis_match else "No specific impact analysis available."
            
            # Parse the stocks into a list
            if stocks_text.lower() == "none":
                stocks = []
            else:
                # Extract tickers (all caps sequences)
                potential_tickers = re.findall(r'\b[A-Z]{1,5}\b', stocks_text)
                stocks = [ticker for ticker in potential_tickers if ticker in MAJOR_STOCKS]
            
            return stocks, impact_text
            
        except Exception as e:
            logger.error(f"Error analyzing with OpenAI: {str(e)}")
            # Return default values if OpenAI analysis fails
            return self._extract_companies_regex(f"{article.title} {article.content}"), "Unable to perform detailed impact analysis."
    
    async def analyze_recent_articles(self, limit: int = 10) -> List[Dict[str, Any]]:
        """Analyze the most recent news articles for stock impacts"""
        # Get recent articles
        articles = self.db.query(NewsArticle).order_by(NewsArticle.date.desc()).limit(limit).all()
        
        results = []
        for article in articles:
            try:
                impact = await self.analyze_article_impact(article)
                # Only include articles with identified stock impacts
                if impact["impacted_stocks"]:
                    results.append(impact)
            except Exception as e:
                logger.error(f"Error analyzing article {article.id}: {str(e)}")
        
        return results 