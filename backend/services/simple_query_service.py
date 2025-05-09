"""
Simple Query Service
This provides a simpler alternative to the RAG service that retrieves recent
data from the database and generates responses using OpenAI directly.
"""
import os
import asyncio
from dotenv import load_dotenv
from sqlalchemy.orm import Session
from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser
from backend.core.database import get_db, NewsArticle, SocialMediaPost, FinancialTerm

# Explicitly load environment variables
load_dotenv()

class SimpleQueryService:
    """A simple service for querying financial data without using the complex RAG pipeline"""
    
    def __init__(self, db: Session = None):
        """Initialize the service with a database session"""
        self.db = db or next(get_db())
        
        # Initialize OpenAI client
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise ValueError("OpenAI API key not found in environment variables")
        
        self.api_key = api_key
        self.llm = ChatOpenAI(
            model="gpt-4",
            temperature=0.7,
            api_key=api_key
        )
        
    async def process_question(self, question: str, limit: int = 10) -> str:
        """Process a question about financial data and generate a response"""
        # Get relevant data from database
        news_articles = self.db.query(NewsArticle).order_by(NewsArticle.date.desc()).limit(limit).all()
        terms = self.db.query(FinancialTerm).limit(limit).all()
        social_posts = self.db.query(SocialMediaPost).order_by(SocialMediaPost.date.desc()).limit(limit).all()
        
        # Format data for context
        news_context = "\n\n".join([
            f"Title: {article.title}\nSource: {article.source}\nDate: {article.date}\nContent: {article.content[:300]}..."
            for article in news_articles
        ])
        
        terms_context = "\n\n".join([
            f"Term: {term.term}\nDefinition: {term.definition[:300]}..."
            for term in terms
        ])
        
        social_context = "\n\n".join([
            f"Platform: {post.platform}\nDate: {post.date}\nContent: {post.content[:300]}..."
            for post in social_posts
        ])
        
        # Create simple prompt for answering
        prompt = ChatPromptTemplate.from_template("""
        You are a helpful financial assistant. Answer the following question based on the provided context.
        
        Question: {question}
        
        Recent News Articles:
        {news}
        
        Financial Terms:
        {terms}
        
        Social Media Posts:
        {social}
        
        Provide a comprehensive answer to the question, highlighting any relevant information from 
        the provided context. If you don't know the answer, say so.
        """)
        
        # Create simple chain and run it
        runnable = prompt | self.llm | StrOutputParser()
        
        # Run the prompt
        try:
            response = runnable.invoke({
                "question": question,
                "news": news_context,
                "terms": terms_context,
                "social": social_context
            })
            return response
        except Exception as e:
            return f"Error processing question: {str(e)}"
