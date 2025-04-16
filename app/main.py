from fastapi import FastAPI, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import Dict, List
from datetime import datetime
from .database import get_db, NewsArticle, SocialMediaPost, FinancialTerm
from .services.rag_service import RAGService

app = FastAPI(title="Finance News AI")

@app.get("/")
def read_root():
    return {"message": "Welcome to Finance News AI"}

@app.post("/update-data")
async def update_data(db: Session = Depends(get_db)):
    """Update all data sources (news, social media, financial terms)"""
    try:
        rag = RAGService(db)
        new_items = await rag.update_news_database()
        return {"message": f"Added {new_items} new items"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/news")
def get_news(limit: int = 10, db: Session = Depends(get_db)):
    """Get recent news articles"""
    articles = db.query(NewsArticle).order_by(NewsArticle.date.desc()).limit(limit).all()
    return [
        {
            "title": article.title,
            "content": article.content[:200] + "..." if len(article.content) > 200 else article.content,
            "source": article.source,
            "url": article.url,
            "date": article.date.isoformat()
        }
        for article in articles
    ]

@app.get("/social")
def get_social_posts(limit: int = 10, db: Session = Depends(get_db)):
    """Get recent social media posts"""
    posts = db.query(SocialMediaPost).order_by(SocialMediaPost.date.desc()).limit(limit).all()
    return [
        {
            "platform": post.platform,
            "content": post.content[:200] + "..." if len(post.content) > 200 else post.content,
            "url": post.url,
            "date": post.date.isoformat()
        }
        for post in posts
    ]

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
            
        rag = RAGService(db)
        response = await rag.process_question(query["question"])
        return {"answer": response}
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
