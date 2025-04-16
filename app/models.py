from pydantic import BaseModel
from typing import List, Optional
from datetime import datetime

class NewsArticle(BaseModel):
    id: str
    title: str
    content: str
    source: str
    url: str
    published_at: datetime
    
class NewsQuery(BaseModel):
    question: str

class NewsSource(BaseModel):
    title: str
    url: str
    relevance_score: float

class SentimentScore(BaseModel):
    label: str
    score: float
    sentiment_scores: dict[str, float]

class FinancialAnalysis(BaseModel):
    title: str
    sentiment: SentimentScore

class NewsResponse(BaseModel):
    answer: str
    tasks: str
    sources: List[NewsSource]
    financial_analysis: List[FinancialAnalysis]
