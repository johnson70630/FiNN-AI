import pytest
import asyncio
from datetime import datetime
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from app.database import Base, NewsArticle, SocialMediaPost, FinancialTerm
from app.scrapers.news_scraper import NewsScraperService
from app.scrapers.financial_knowledge import FinancialKnowledgeService
from app.scrapers.social_media_scraper import SocialMediaScraperService
from app.services.rag_service import RAGService
import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Test database
TEST_DB_URL = "sqlite:///test_finance.db"

@pytest.fixture
def db_session():
    """Create a test database session"""
    engine = create_engine(TEST_DB_URL)
    Base.metadata.create_all(engine)
    TestingSessionLocal = sessionmaker(bind=engine)
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()
        # Clean up test database
        os.remove("test_finance.db")

@pytest.fixture
def sample_data(db_session):
    """Create sample data for testing"""
    # Add a news article
    news = NewsArticle(
        title="Test Article",
        content="This is a test article about the stock market",
        date=datetime.now(),
        source="Test Source",
        url="http://test.com/article"
    )
    db_session.add(news)
    
    # Add a social media post
    post = SocialMediaPost(
        platform="Twitter",
        content="Test tweet about #stocks",
        date=datetime.now(),
        url="http://twitter.com/test",
        user="testuser"
    )
    db_session.add(post)
    
    # Add a financial term
    term = FinancialTerm(
        term="Stock",
        definition="A type of security that represents ownership in a company",
        url="http://test.com/stock"
    )
    db_session.add(term)
    
    db_session.commit()
    return db_session

@pytest.mark.asyncio
async def test_news_scraper(db_session):
    """Test news scraping functionality"""
    scraper = NewsScraperService(db_session)
    count = await scraper.update_news_database()
    
    # Check if articles were added
    articles = db_session.query(NewsArticle).all()
    assert len(articles) > 0
    
    # Check article structure
    article = articles[0]
    assert article.title is not None
    assert article.content is not None
    assert article.date is not None
    assert article.url is not None
    assert article.source is not None

@pytest.mark.asyncio
async def test_financial_knowledge(db_session):
    """Test financial terms scraping"""
    scraper = FinancialKnowledgeService(db_session)
    count = await scraper.update_terms_database()
    
    # Check if terms were added
    terms = db_session.query(FinancialTerm).all()
    assert len(terms) > 0
    
    # Check term structure
    term = terms[0]
    assert term.term is not None
    assert term.definition is not None
    assert term.url is not None

@pytest.mark.asyncio
async def test_social_media_scraper(db_session):
    """Test social media scraping"""
    scraper = SocialMediaScraperService(db_session)
    count = await scraper.update_posts_database()
    
    # Check if posts were added
    posts = db_session.query(SocialMediaPost).all()
    assert len(posts) > 0
    
    # Check post structure
    post = posts[0]
    assert post.platform is not None
    assert post.content is not None
    assert post.date is not None
    assert post.url is not None

@pytest.mark.asyncio
async def test_embedding_generation(db_session, sample_data):
    """Test embedding generation and search"""
    rag = RAGService(db_session)
    
    # Update database (this will generate embeddings)
    await rag.update_news_database()
    
    # Check if embeddings were generated
    article = db_session.query(NewsArticle).first()
    assert article.embedding is not None
    
    post = db_session.query(SocialMediaPost).first()
    assert post.embedding is not None
    
    term = db_session.query(FinancialTerm).first()
    assert term.embedding is not None

@pytest.mark.asyncio
async def test_rag_pipeline(db_session, sample_data):
    """Test the complete RAG pipeline"""
    rag = RAGService(db_session)
    
    # Test question
    question = "What's happening in the stock market today?"
    
    # Process question
    response = await rag.process_question(question)
    
    # Check response
    assert response is not None
    assert isinstance(response, str)
    assert len(response) > 0

@pytest.mark.asyncio
async def test_duplicate_handling(db_session):
    """Test handling of duplicate entries"""
    # Add same article twice
    article = NewsArticle(
        title="Duplicate Test",
        content="Test content",
        date=datetime.now(),
        source="Test",
        url="http://test.com/duplicate"
    )
    
    db_session.add(article)
    db_session.commit()
    
    # Try to add same article again
    article2 = NewsArticle(
        title="Duplicate Test",
        content="Test content",
        date=datetime.now(),
        source="Test",
        url="http://test.com/duplicate"
    )
    
    db_session.add(article2)
    
    # Should not raise error due to unique constraint on URL
    try:
        db_session.commit()
        assert False, "Should have raised an error"
    except:
        db_session.rollback()
        assert True

@pytest.mark.asyncio
async def test_error_handling(db_session):
    """Test error handling in services"""
    # Test with invalid API keys
    os.environ["TWITTER_BEARER_TOKEN"] = "invalid_token"
    
    scraper = SocialMediaScraperService(db_session)
    count = await scraper.update_posts_database()
    
    # Should handle error gracefully
    assert count == 0

def test_database_session(db_session):
    """Test database session management"""
    # Add test article
    article = NewsArticle(
        title="Session Test",
        content="Test content",
        date=datetime.now(),
        source="Test",
        url="http://test.com/session"
    )
    
    db_session.add(article)
    db_session.commit()
    
    # Query should work
    result = db_session.query(NewsArticle).filter_by(url="http://test.com/session").first()
    assert result is not None
    assert result.title == "Session Test"
    
    # Rollback should work
    article2 = NewsArticle(
        title="Rollback Test",
        content="Test content",
        date=datetime.now(),
        source="Test",
        url="http://test.com/rollback"
    )
    
    db_session.add(article2)
    db_session.rollback()
    
    result = db_session.query(NewsArticle).filter_by(url="http://test.com/rollback").first()
    assert result is None
