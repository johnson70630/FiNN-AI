from backend.services.rag_service import RAGService
from backend.services.stock_analysis_service import StockAnalysisService
from sqlalchemy.orm import Session
import re
import logging

logger = logging.getLogger(__name__)

class ChainService:
    """Chain-based service for processing financial queries with structured reasoning"""
    
    def __init__(self, db: Session):
        """Initialize with database session"""
        self.db = db
        self.rag_service = RAGService(db)
        self.stock_analyzer = StockAnalysisService(db)
        
    async def process_query(self, question: str) -> dict:
        """
        Process a user query through a chain of reasoning steps
        
        Args:
            question: The user's question
            
        Returns:
            Dict containing the answer and chain of thought
        """
        # Step 1: Determine the type of query
        query_type = self._classify_query(question)
        logger.info(f"Classified query as {query_type}: {question}")
        
        # Step 2: Execute appropriate chain based on query type
        if query_type == "stock_analysis":
            answer, chain = await self._stock_analysis_chain(question)
        elif query_type == "market_overview":
            answer, chain = await self._market_overview_chain(question)
        elif query_type == "investment_advice":
            answer, chain = await self._investment_advice_chain(question)
        else:
            # Default to RAG for general questions
            answer = await self.rag_service.process_question(question)
            chain = [
                {"step": "Query Classification", "output": "General financial question (using RAG)"},
                {"step": "Answer Generation", "output": "Used Retrieval Augmented Generation to find relevant information"}
            ]
        
        return {
            "answer": answer,
            "chain_of_thought": chain
        }
    
    def _classify_query(self, question: str) -> str:
        """Classify the type of financial query"""
        question_lower = question.lower()
        
        # Check for stock analysis patterns
        stock_patterns = [
            r"what (?:do you think|is your opinion) (?:about|of) (\w+)(?:\s+stock)?",
            r"(?:should|would you) (?:i|we) (?:buy|sell) (\w+)(?:\s+stock)?",
            r"analyze (\w+)(?:\s+stock)?",
            r"(?:what is the|what's the) (?:bull|bear) case for (\w+)",
            r"is (\w+) a good (?:buy|investment)",
            r"what do you think will happen (?:to|with) (\w+)"
        ]
        
        for pattern in stock_patterns:
            if re.search(pattern, question_lower):
                return "stock_analysis"
        
        # Check for market overview patterns
        market_patterns = [
            r"market overview",
            r"how is the market",
            r"market (?:today|performance|outlook)",
            r"stock market",
            r"s&p 500"
        ]
        
        if any(re.search(pattern, question_lower) for pattern in market_patterns):
            return "market_overview"
            
        # Check for investment advice patterns
        advice_patterns = [
            r"portfolio",
            r"invest(?:ing|ment)",
            r"retirement",
            r"asset allocation",
            r"diversif(?:y|ication)",
            r"financial advice"
        ]
        
        if any(re.search(pattern, question_lower) for pattern in advice_patterns):
            return "investment_advice"
            
        return "general"
        
    async def _stock_analysis_chain(self, question: str) -> tuple:
        """Chain for stock analysis queries"""
        chain = []
        
        # Step 1: Extract the stock symbol from the question
        chain.append({"step": "Query Classification", "output": "Stock Analysis Query"})
        
        symbol = self._extract_stock_symbol(question)
        chain.append({"step": "Symbol Extraction", "output": f"Extracted stock symbol: {symbol if symbol else 'None'}"})
        
        if not symbol:
            return "I couldn't identify a stock symbol in your question. Please specify which stock you'd like me to analyze.", chain
        
        # Step 2: Get stock data and perform analysis
        chain.append({"step": "Data Collection", "output": f"Retrieving data for {symbol}"})
        analysis = await self.stock_analyzer.analyze_stock(symbol)
        
        # Step 3: Check if analysis was successful
        if "error" in analysis:
            chain.append({"step": "Analysis", "output": f"Error: {analysis['error']}"})
            return f"I encountered an error analyzing {symbol}: {analysis['error']}", chain
        
        chain.append({"step": "Analysis", "output": f"Successfully analyzed {symbol} ({analysis.get('company_name', 'Unknown Company')})"})
        
        # Step 4: Format the response with chain-of-thought reasoning
        response = []
        response.append(f"# Analysis for {analysis['company_name']} ({symbol})\n")
        
        # Step 4.1: Price analysis
        if "price_analysis" in analysis and "error" not in analysis["price_analysis"]:
            price = analysis["price_analysis"]
            chain.append({"step": "Price Analysis", "output": f"{price['trend']} trend, {price['total_change_pct']}% change"})
            
            response.append(f"## Price Analysis\n")
            response.append(f"* {price['summary']}")
            response.append(f"* Price change: {price['total_change_pct']}% ({price['trend']} trend)")
            response.append(f"* Volatility: {price['volatility_pct']}%\n")
        
        # Step 4.2: News sentiment
        if "news_analysis" in analysis and "error" not in analysis["news_analysis"]:
            news = analysis["news_analysis"]
            chain.append({"step": "News Sentiment", "output": f"{news['sentiment']} sentiment, {news['articles_found']} articles"})
            
            response.append(f"## News Sentiment\n")
            response.append(f"* {news['summary']}")
            response.append(f"* Found {news['articles_found']} relevant articles")
            if news['articles_found'] > 0 and 'recent_articles' in news and news['recent_articles']:
                response.append("* Key headlines:")
                for article in news['recent_articles'][:3]:  # Top 3 articles
                    response.append(f"  - {article['title']}\n")
        
        # Step 4.3: Social media sentiment
        if "social_analysis" in analysis and "error" not in analysis["social_analysis"]:
            social = analysis["social_analysis"]
            chain.append({"step": "Social Sentiment", "output": f"{social['sentiment']} sentiment, {social['posts_found']} posts"})
            
            response.append(f"## Social Media Sentiment\n")
            response.append(f"* {social['summary']}")
            if social['posts_found'] > 0 and 'platforms' in social and social['platforms']:
                response.append(f"* Found {social['posts_found']} relevant posts across {', '.join(social['platforms'])}\n")
        
        # Step 4.4: Final recommendation
        if "combined_analysis" in analysis and "recommendation" in analysis["combined_analysis"]:
            combined = analysis["combined_analysis"]
            recommendation = combined.get('recommendation', 'No clear recommendation')
            chain.append({"step": "Final Recommendation", "output": recommendation})
            
            response.append(f"## Recommendation\n")
            response.append(f"* {recommendation}")
            if "reasoning" in combined and combined["reasoning"]:
                response.append("* Reasoning:")
                for reason in combined["reasoning"]:
                    response.append(f"  - {reason}")
        
        # Join all parts with proper formatting
        final_response = "\n".join(response)
        return final_response, chain
    
    async def _market_overview_chain(self, question: str) -> tuple:
        """Chain for market overview queries"""
        chain = [
            {"step": "Query Classification", "output": "Market Overview Query"},
            {"step": "Processing", "output": "Using RAG to provide market overview"}
        ]
        
        # For now, use RAG to answer market overview questions
        answer = await self.rag_service.process_question(
            f"Give a brief overview of the current stock market conditions. {question}"
        )
        
        chain.append({"step": "Response Generation", "output": "Generated market overview"})
        return answer, chain
    
    async def _investment_advice_chain(self, question: str) -> tuple:
        """Chain for investment advice queries"""
        chain = [
            {"step": "Query Classification", "output": "Investment Advice Query"},
            {"step": "Processing", "output": "Using RAG to provide investment advice"}
        ]
        
        # For now, use RAG to answer investment advice questions
        answer = await self.rag_service.process_question(
            f"Provide investment advice for the following question: {question}"
        )
        
        chain.append({"step": "Response Generation", "output": "Generated investment advice"})
        return answer, chain
    
    def _extract_stock_symbol(self, question: str) -> str:
        """Extract a stock symbol from the question"""
        # Simple pattern matching for stock symbols
        common_symbols = ["AAPL", "MSFT", "GOOGL", "AMZN", "META", "TSLA", "NVDA"]
        
        # Check for common symbols directly
        for symbol in common_symbols:
            if symbol in question.upper():
                return symbol
                
        # Try to match using regex patterns
        patterns = [
            r"(?:symbol|ticker)\s+(\w+)",
            r"(\w+)(?:\s+stock)",
            r"(?:buy|sell)\s+(\w+)"
        ]
        
        for pattern in patterns:
            match = re.search(pattern, question, re.IGNORECASE)
            if match:
                potential_symbol = match.group(1).upper()
                # Only return if it looks like a valid symbol (1-5 uppercase letters)
                if re.match(r"^[A-Z]{1,5}$", potential_symbol):
                    return potential_symbol
                    
        return None 