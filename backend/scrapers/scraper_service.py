import asyncio
import os
import json
from datetime import datetime
import threading
import time
import schedule
from sqlalchemy.orm import Session
from backend.core.database import get_db
from backend.scrapers.news_scraper import NewsScraperService
from backend.scrapers.social_media_scraper import SocialMediaScraperService
from backend.scrapers.financial_knowledge import FinancialKnowledgeService
from backend.services.embedding_service import EmbeddingService

class ScraperCoordinator:
    def __init__(self, news_service=None, social_media_service=None, financial_knowledge_service=None, db=None):
        """Initialize the coordinator with all scraper services"""
        self.db = db or next(get_db())
        self.news_service = news_service or NewsScraperService(self.db)
        self.social_media_service = social_media_service or SocialMediaScraperService(self.db)
        self.financial_knowledge_service = financial_knowledge_service or FinancialKnowledgeService(self.db)
        
        # Scheduling properties
        self.is_scheduled = False
        self.scheduler_thread = None
        self.interval_minutes = 60  # Default to hourly
    
    async def run_all_scrapers(self, include_financial_terms=False):
        """Run news and social media scrapers (and optionally financial terms) and return the results"""
        # By default, only run news and social media scrapers for hourly updates
        tasks = [
            self.news_service.update_news_database(),
            self.social_media_service.update_posts_database()
        ]
        
        # Only include financial terms if specifically requested
        if include_financial_terms:
            tasks.append(self.financial_knowledge_service.update_terms_database())
        
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Build result dictionary
        result_dict = {
            "news": results[0] if not isinstance(results[0], Exception) else 0,
            "social": results[1] if not isinstance(results[1], Exception) else 0
        }
        
        # Add knowledge results if included
        if include_financial_terms:
            result_dict["knowledge"] = results[2] if not isinstance(results[2], Exception) else 0
        else:
            result_dict["knowledge"] = 0
        
        return result_dict
    
    def hourly_update_job(self):
        """Run news and social media scrapers in a new event loop (skip financial terms)"""
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            # Pass False to skip financial terms (Investopedia) in hourly updates
            results = loop.run_until_complete(self.run_all_scrapers(include_financial_terms=False))
            total = sum(results.values())
            print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] Scheduled job completed. Added {total} new items:")
            print(f"  - News: {results['news']}")
            print(f"  - Social: {results['social']}")
            # Knowledge will be 0 since we excluded it
        except Exception as e:
            print(f"Error in scheduled job: {e}")
        finally:
            loop.close()
    
    def start_scheduled_scraping(self, interval_minutes=60, run_immediately=True):
        """Start scheduled scraping with the specified interval"""
        if self.is_scheduled:
            print("Scheduled scraping is already running")
            return
        
        self.interval_minutes = interval_minutes
        
        def run_scheduler():
            # Schedule the job based on the specified interval
            schedule.every(interval_minutes).minutes.do(self.hourly_update_job)
            
            # Run the job immediately if requested
            if run_immediately:
                print(f"Running initial data collection...")
                self.hourly_update_job()
            else:
                print(f"Initial data collection skipped. First collection will occur in {interval_minutes} minutes.")
            
            while self.is_scheduled:
                schedule.run_pending()
                time.sleep(60)  # Check every minute for pending jobs
        
        self.is_scheduled = True
        self.scheduler_thread = threading.Thread(target=run_scheduler)
        self.scheduler_thread.daemon = True
        self.scheduler_thread.start()
        print(f"Started scheduled scraping every {interval_minutes} minutes")
    
    def stop_scheduled_scraping(self):
        """Stop the scheduled scraping"""
        if not self.is_scheduled:
            print("No scheduled scraping is running")
            return
        
        self.is_scheduled = False
        if self.scheduler_thread:
            self.scheduler_thread.join(timeout=2)
            schedule.clear()
            self.scheduler_thread = None
        print("Stopped scheduled scraping")

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
        try:
            # Use only specific columns to avoid issues with missing columns
            for term in self.db.query(
                self.knowledge_service.model_class.id,
                self.knowledge_service.model_class.term,
                self.knowledge_service.model_class.definition,
                self.knowledge_service.model_class.url
            ).all():
                terms_data.append({
                    "id": term.id,
                    "term": term.term,
                    "definition": term.definition,
                    "url": term.url
                })
        except Exception as e:
            print(f"Error querying financial terms: {e}")
            # Fallback to direct SQL query
            try:
                from sqlalchemy import text
                result = self.db.execute(text("SELECT id, term, definition, url FROM financial_terms"))
                for row in result:
                    terms_data.append({
                        "id": row[0],
                        "term": row[1],
                        "definition": row[2],
                        "url": row[3]
                    })
            except Exception as e2:
                print(f"Second error querying terms: {e2}")
        
        # Save to JSON file
        terms_file = os.path.join(self.data_dir, "financial_terms.json")
        with open(terms_file, "w") as f:
            json.dump(terms_data, f, indent=2)
            
        return terms_count
    
    async def update_all_data(self, include_financial_terms=True):
        """
        Update data sources and save to data directory
        
        Args:
            include_financial_terms: Whether to update financial terms (default: True)
        """
        # Scrape data from sources
        news_count = await self.update_news_data()
        social_count = await self.update_social_data()
        
        # Only update financial terms if requested
        terms_count = 0
        if include_financial_terms:
            print("Updating financial terms (Investopedia data)...")
            terms_count = await self.update_terms_data()
        else:
            print("Skipping financial terms update as requested")
        
        # Generate embeddings for new content
        total_items = news_count + social_count + terms_count
        if total_items > 0:
            print(f"Generating embeddings for {total_items} new items...")
            embedding_service = EmbeddingService(self.db)
            
            # First update new news articles
            if news_count > 0:
                # Get the most recent news_count articles as they're likely the newly added ones
                recent_news = self.db.query(self.news_service.model_class).order_by(
                    self.news_service.model_class.date.desc()
                ).limit(news_count).all()
                
                for article in recent_news:
                    embedding_service.update_new_item_embedding(article)
            
            # Update new social media posts
            if social_count > 0 and hasattr(self, 'social_service') and self.social_service:
                recent_posts = self.db.query(self.social_service.model_class).order_by(
                    self.social_service.model_class.date.desc()
                ).limit(social_count).all()
                
                for post in recent_posts:
                    embedding_service.update_new_item_embedding(post)
            
            # Update new financial terms if they were updated
            if terms_count > 0 and hasattr(self, 'knowledge_service') and self.knowledge_service:
                # Since terms might not have a date field, we can't easily identify just the new ones
                # Just update all terms that don't have embeddings
                embedding_service.update_model_embeddings(self.knowledge_service.model_class)
        
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