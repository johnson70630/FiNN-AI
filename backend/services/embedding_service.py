"""
Embedding Service - Handles generating and storing embeddings for database items.

This service creates embeddings for news articles, social media posts, and financial terms
using OpenAI's text-embedding-3-small model and stores them in the database.
"""

import os
import logging
from typing import List, Type, Any, Optional
from dotenv import load_dotenv, find_dotenv
from sqlalchemy.orm import Session
from langchain_openai import OpenAIEmbeddings
from tqdm import tqdm

from backend.core.database import (
    NewsArticle, SocialMediaPost, FinancialTerm, 
    InvestopediaDict, InvestingCom, store_embedding
)

# Configure logging
logger = logging.getLogger(__name__)

class EmbeddingService:
    def __init__(self, db: Session):
        """Initialize the embedding service with a database session"""
        self.db = db
        
        # Load OpenAI API key from environment
        load_dotenv(find_dotenv())
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise ValueError("OPENAI_API_KEY is required for embedding generation")
            
        # Initialize the embeddings model
        self.embeddings = OpenAIEmbeddings(model="text-embedding-3-small")
        
        # Mapping of model classes to their text content fields
        self.model_fields = {
            NewsArticle: lambda item: f"{item.title} {item.content}",
            SocialMediaPost: lambda item: item.content,
            FinancialTerm: lambda item: f"{item.term} {item.definition}",
            InvestopediaDict: lambda item: f"{item.title} {item.content}",
            InvestingCom: lambda item: f"{item.title} {item.content}"
        }
    
    def generate_embedding(self, text: str) -> List[float]:
        """Generate an embedding for the given text"""
        return self.embeddings.embed_query(text)
    
    def update_item_embedding(self, item: Any, model_class: Type) -> bool:
        """Generate and store an embedding for a single item"""
        try:
            # Skip if already has embedding
            if item.embedding is not None:
                return False
                
            # Get text to embed based on model type
            if model_class not in self.model_fields:
                logger.warning(f"Unsupported model class: {model_class.__name__}")
                return False
                
            text_getter = self.model_fields[model_class]
            text = text_getter(item)
            
            # Generate embedding
            embedding = self.generate_embedding(text)
            
            # Store embedding
            store_embedding(self.db, model_class, item.id, embedding)
            return True
            
        except Exception as e:
            logger.error(f"Error generating embedding for {model_class.__name__} {item.id}: {e}")
            return False
    
    def update_model_embeddings(self, model_class: Type, batch_size: int = 50) -> int:
        """Update embeddings for all items in a model class that don't have them"""
        try:
            # Get items without embeddings
            items = self.db.query(model_class).filter(model_class.embedding.is_(None)).all()
            
            if not items:
                logger.info(f"No {model_class.__name__} items without embeddings")
                return 0
                
            # Process in batches to avoid rate limits
            updated_count = 0
            total_items = len(items)
            
            logger.info(f"Updating embeddings for {total_items} {model_class.__name__} items")
            
            for i in tqdm(range(0, total_items, batch_size), desc=f"Embedding {model_class.__name__}"):
                batch = items[i:i+batch_size]
                
                for item in batch:
                    success = self.update_item_embedding(item, model_class)
                    if success:
                        updated_count += 1
            
            return updated_count
            
        except Exception as e:
            logger.error(f"Error updating embeddings for {model_class.__name__}: {e}")
            return 0
    
    def update_all_embeddings(self) -> dict:
        """Update embeddings for all supported models"""
        results = {}
        
        for model_class in self.model_fields.keys():
            count = self.update_model_embeddings(model_class)
            results[model_class.__name__] = count
            
        return results
    
    def update_new_item_embedding(self, item: Any) -> bool:
        """Generate and store embedding for a newly added item"""
        for model_class in self.model_fields.keys():
            if isinstance(item, model_class):
                return self.update_item_embedding(item, model_class)
                
        logger.warning(f"Unknown item type: {type(item).__name__}")
        return False 