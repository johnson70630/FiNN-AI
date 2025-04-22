import asyncio
import os
import json
from datetime import datetime
from sqlalchemy.orm import Session
from ..database import get_db
from ..scrapers.news_scraper import NewsScraperService
from ..scrapers.social_media_scraper import SocialMediaScraperService
from ..scrapers.financial_knowledge import FinancialKnowledgeService

class DataCollectionService:
    def __init__(self, db: Session = None):
        self.db = db or next(get_db())
        self.news_service = NewsScraperService(self.db)
        self.social_service = SocialMediaScraperService(self.db) if hasattr(SocialMediaScraperService, "__call__") else None
        self.knowledge_service = FinancialKnowledgeService(self.db) if hasattr(FinancialKnowledgeService, "__call__") else None
        self.data_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "data")
        os.makedirs(self.data_dir, exist_ok=True)
    
    async def update_news_data(self):
        """Update news articles and save to data directory"""
        news_count = await self.news_service.update_news_database()
        
        # Export news data to data directory
        news_data = []
        try:
            # Use only the columns we need, ignoring 'embedding' if it doesn't exist
            for article in self.db.query(
                self.news_service.model_class.id,
                self.news_service.model_class.title,
                self.news_service.model_class.content,
                self.news_service.model_class.source,
                self.news_service.model_class.url,
                self.news_service.model_class.date
            ).order_by(self.news_service.model_class.date.desc()).all():
                news_data.append({
                    "id": article.id,
                    "title": article.title,
                    "content": article.content,
                    "source": article.source,
                    "url": article.url,
                    "date": article.date.isoformat() if hasattr(article.date, 'isoformat') else str(article.date)
                })
        except Exception as e:
            print(f"Error querying news articles: {e}")
            # Fallback to a simpler query that doesn't specify columns
            # This approach avoids issues with missing columns
            for article in self.db.query(self.news_service.model_class).all():
                try:
                    news_data.append({
                        "id": article.id,
                        "title": article.title,
                        "content": article.content,
                        "source": article.source,
                        "url": article.url,
                        "date": article.date.isoformat() if hasattr(article.date, 'isoformat') else str(article.date)
                    })
                except Exception as attr_err:
                    print(f"Error processing article {article.id if hasattr(article, 'id') else 'unknown'}: {attr_err}")
        
        # Save to JSON file
        news_file = os.path.join(self.data_dir, "news_articles.json")
        with open(news_file, "w") as f:
            json.dump(news_data, f, indent=2)
            
        return news_count
    
    async def update_social_data(self):
        """Update social media posts and save to data directory"""
        if not self.social_service:
            return 0
            
        social_count = await self.social_service.update_posts_database()
        
        # Export social data to data directory
        social_data = []
        for post in self.db.query(self.social_service.model_class).order_by(
            self.social_service.model_class.date.desc()).all():
            social_data.append({
                "id": post.id,
                "platform": post.platform,
                "content": post.content,
                "url": post.url,
                "date": post.date.isoformat() if hasattr(post.date, 'isoformat') else str(post.date)
            })
        
        # Save to JSON file
        social_file = os.path.join(self.data_dir, "social_posts.json")
        with open(social_file, "w") as f:
            json.dump(social_data, f, indent=2)
            
        return social_count
    
    async def update_terms_data(self):
        """Update financial terms and save to data directory"""
        if not self.knowledge_service:
            return 0
            
        terms_count = await self.knowledge_service.update_terms_database()
        
        # Export terms data to data directory
        terms_data = []
        for term in self.db.query(self.knowledge_service.model_class).all():
            terms_data.append({
                "id": term.id,
                "term": term.term,
                "definition": term.definition,
                "url": term.url
            })
        
        # Save to JSON file
        terms_file = os.path.join(self.data_dir, "financial_terms.json")
        with open(terms_file, "w") as f:
            json.dump(terms_data, f, indent=2)
            
        return terms_count
    
    async def update_all_data(self):
        """Update all data sources and save to data directory"""
        news_count = await self.update_news_data()
        social_count = await self.update_social_data()
        terms_count = await self.update_terms_data()
        
        # Create a metadata file with update timestamp
        metadata = {
            "last_updated": datetime.now().isoformat(),
            "news_count": news_count,
            "social_count": social_count,
            "terms_count": terms_count
        }
        
        metadata_file = os.path.join(self.data_dir, "metadata.json")
        with open(metadata_file, "w") as f:
            json.dump(metadata, f, indent=2)
        
        return news_count + social_count + terms_count

# CLI entry point
async def main():
    collector = DataCollectionService()
    count = await collector.update_all_data()
    print(f"Added {count} new items and saved to data directory")

if __name__ == "__main__":
    asyncio.run(main())