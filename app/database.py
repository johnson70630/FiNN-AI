from sqlalchemy import create_engine, Column, Integer, String, DateTime, Text, Float, LargeBinary
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from pathlib import Path
import numpy as np
import json
from datetime import datetime
from typing import List, Dict, Any

# Create data directory if it doesn't exist
data_dir = Path("data")
data_dir.mkdir(exist_ok=True)

# Create database URL
SQLALCHEMY_DATABASE_URL = f"sqlite:///{data_dir}/finance.db"

# Create SQLAlchemy engine
engine = create_engine(
    SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False}
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()

# Database Models
class SocialMediaPost(Base):
    __tablename__ = "social_media_posts"

    id = Column(Integer, primary_key=True, index=True)
    platform = Column(String)
    user = Column(String)
    date = Column(DateTime)
    content = Column(Text)
    url = Column(String, unique=True)
    subreddit = Column(String, nullable=True)  # For Reddit posts
    embedding = Column(LargeBinary, nullable=True)  # For vector search

class NewsArticle(Base):
    __tablename__ = "news_articles"

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String)
    content = Column(Text)
    date = Column(DateTime)
    source = Column(String)
    url = Column(String, unique=True)
    embedding = Column(LargeBinary, nullable=True)  # For vector search

class FinancialTerm(Base):
    __tablename__ = "financial_terms"

    id = Column(Integer, primary_key=True, index=True)
    term = Column(String, unique=True)
    definition = Column(Text)
    url = Column(String)
    embedding = Column(LargeBinary, nullable=True)  # For vector search

# Dependency to get database session
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# Vector search functions
def store_embedding(db, model, item_id: int, embedding: List[float]):
    """Store an embedding for an item"""
    item = db.query(model).filter(model.id == item_id).first()
    if item:
        item.embedding = json.dumps(embedding).encode()
        db.commit()

def search_by_embedding(db, model, query_embedding: List[float], limit: int = 5) -> List[Dict]:
    """Search items using embedding similarity"""
    query_embedding = np.array(query_embedding)
    results = []
    
    # Get all items with embeddings
    items = db.query(model).filter(model.embedding.isnot(None)).all()
    
    # Calculate similarities
    similarities = []
    for item in items:
        item_embedding = np.array(json.loads(item.embedding.decode()))
        similarity = np.dot(query_embedding, item_embedding) / (
            np.linalg.norm(query_embedding) * np.linalg.norm(item_embedding)
        )
        similarities.append((similarity, item))
    
    # Sort by similarity
    sorted_items = sorted(similarities, key=lambda x: x[0], reverse=True)
    
    # Convert to dictionaries
    for similarity, item in sorted_items[:limit]:
        item_dict = {
            "id": item.id,
            "url": item.url,
            "similarity": float(similarity)
        }
        
        if isinstance(item, NewsArticle):
            item_dict.update({
                "title": item.title,
                "content": item.content,
                "source": item.source,
                "date": item.date
            })
        elif isinstance(item, SocialMediaPost):
            item_dict.update({
                "platform": item.platform,
                "content": item.content,
                "date": item.date
            })
        elif isinstance(item, FinancialTerm):
            item_dict.update({
                "term": item.term,
                "definition": item.definition
            })
            
        results.append(item_dict)
    
    return results

# Create all tables
Base.metadata.create_all(bind=engine)
