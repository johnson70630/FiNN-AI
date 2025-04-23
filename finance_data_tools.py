#!/usr/bin/env python3
"""
Finance Data Collection and Viewing Tools

This script provides comprehensive tools for collecting, managing, and viewing financial data:
- Collect news articles, social media posts, and financial terms
- Schedule periodic data collection
- View collected data from different databases
- Manage database schema

Usage:
    python finance_data_tools.py collect --all                   # Collect all types of data once
    python finance_data_tools.py collect --news                  # Collect only news once
    python finance_data_tools.py collect --social                # Collect only social media once
    python finance_data_tools.py collect --terms                 # Collect only financial terms once
    python finance_data_tools.py schedule --all --interval 60    # Schedule all data collection every 60 minutes
    python finance_data_tools.py schedule --news --interval 30   # Schedule news collection every 30 minutes
    python finance_data_tools.py view --all                      # View all data
    python finance_data_tools.py view --news                     # View news data
    python finance_data_tools.py view --social                   # View social media data
    python finance_data_tools.py view --terms                    # View financial terms
    python finance_data_tools.py recreate-db                     # Recreate database schema
"""

import asyncio
import os
import sys
import argparse
import time
import signal
import aiohttp
import sqlite3
import schedule
import threading
from pathlib import Path
from datetime import datetime, timezone
from dotenv import load_dotenv
from sqlalchemy.orm import sessionmaker
from app.database import engine, Base, NewsArticle, SocialMediaPost, FinancialTerm
from app.scrapers.news_scraper import NewsScraperService
from app.scrapers.social_media_scraper import SocialMediaScraperService
from app.scrapers.financial_knowledge import FinancialKnowledgeService
from app.data_collection.scraper_service import ScraperCoordinator

# Load environment variables
load_dotenv()

def print_separator():
    """Print a separator line"""
    print("-" * 80)

def recreate_database():
    """Drop and recreate all database tables"""
    print("Dropping all tables...")
    Base.metadata.drop_all(bind=engine)
    print("Recreating all tables...")
    Base.metadata.create_all(bind=engine)
    print("Database tables have been recreated successfully.")

async def collect_news_data(db_session):
    """Collect news articles"""
    print("\n=== Collecting News Articles ===")
    news_service = NewsScraperService(db_session)
    try:
        news_count = await news_service.update_news_database()
        print(f"Added {news_count} new news articles to database")
        return news_count
    except Exception as e:
        print(f"Error collecting news: {e}")
        return 0

async def collect_social_media_data(db_session):
    """Collect social media posts with fixed schema"""
    print("\n=== Collecting Social Media Posts ===")
    
    # Get API credentials
    twitter_bearer_token = os.getenv("TWITTER_BEARER_TOKEN")
    reddit_client_id = os.getenv("REDDIT_CLIENT_ID")
    reddit_client_secret = os.getenv("REDDIT_CLIENT_SECRET")
    reddit_user_agent = os.getenv("REDDIT_USER_AGENT")
    
    print(f"Twitter Bearer Token: {'Found' if twitter_bearer_token else 'Not found'}")
    print(f"Reddit Client ID: {'Found' if reddit_client_id else 'Not found'}")
    print(f"Reddit Client Secret: {'Found' if reddit_client_secret else 'Not found'}")
    print(f"Reddit User Agent: {'Found' if reddit_user_agent else 'Not found'}")
    
    try:
        # Get existing URLs to avoid duplicates
        existing_urls = {post.url for post in db_session.query(SocialMediaPost).all()}
        
        # Common headers
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
        }
        
        # Create session for API calls
        connector = aiohttp.TCPConnector(limit=10)
        async with aiohttp.ClientSession(connector=connector) as session:
            # Fetch Twitter posts
            twitter_posts = await fetch_twitter_posts(session, twitter_bearer_token, headers)
            
            # Fetch Reddit posts
            reddit_token = await get_reddit_token(session, reddit_client_id, reddit_client_secret, reddit_user_agent)
            reddit_posts = await fetch_reddit_posts(session, reddit_token, reddit_user_agent)
            
            # Combine all posts
            all_posts = twitter_posts + reddit_posts
            
            # Add new posts to database
            added_count = 0
            for post in all_posts:
                if post.url not in existing_urls:
                    db_session.add(post)
                    added_count += 1
            
            # Commit if there are new posts
            if added_count > 0:
                db_session.commit()
                
            print(f"Added {added_count} new social media posts to database")
            return added_count
    except Exception as e:
        print(f"Error collecting social media data: {e}")
        return 0

async def collect_financial_terms(db_session):
    """Collect financial terms"""
    print("\n=== Collecting Financial Terms ===")
    financial_knowledge_service = FinancialKnowledgeService(db_session)
    try:
        terms_count = await financial_knowledge_service.update_terms_database()
        print(f"Added {terms_count} new financial terms to database")
        return terms_count
    except Exception as e:
        print(f"Error collecting financial terms: {e}")
        return 0

async def fetch_twitter_posts(session, bearer_token, headers, limit=100):
    """Fetch recent finance-related tweets"""
    if not bearer_token:
        print("Twitter bearer token not found")
        return []
        
    twitter_api_url = "https://api.twitter.com/2/tweets/search/recent"
    twitter_query = "(stock market OR investing OR finance) -is:retweet lang:en"
    
    headers = {
        "Authorization": f"Bearer {bearer_token}",
        **headers
    }
    
    params = {
        "query": twitter_query,
        "max_results": limit,
        "tweet.fields": "created_at,public_metrics,author_id"
    }
    
    try:
        async with session.get(twitter_api_url, headers=headers, params=params) as response:
            if response.status == 200:
                data = await response.json()
                
                posts = []
                for tweet in data.get("data", []):
                    tweet_id = tweet["id"]
                    tweet_url = f"https://twitter.com/i/web/status/{tweet_id}"
                    created_at = datetime.strptime(tweet["created_at"], "%Y-%m-%dT%H:%M:%S.%fZ")
                    
                    # Create SocialMediaPost without the engagement field
                    posts.append(SocialMediaPost(
                        platform="Twitter",
                        user=tweet.get("author_id", "unknown"),
                        content=tweet["text"],
                        url=tweet_url,
                        date=created_at
                    ))
                    
                return posts
            else:
                print(f"Twitter API error: {response.status}")
                
    except Exception as e:
        print(f"Error fetching tweets: {e}")
        
    return []

async def get_reddit_token(session, client_id, client_secret, user_agent):
    """Get Reddit OAuth token"""
    if not all([client_id, client_secret]):
        print("Reddit credentials not found")
        return None
        
    auth = aiohttp.BasicAuth(client_id, client_secret)
    data = {"grant_type": "client_credentials"}
    headers = {"User-Agent": user_agent}
    
    try:
        reddit_auth_url = "https://www.reddit.com/api/v1/access_token"
        async with session.post(reddit_auth_url, auth=auth, data=data, headers=headers) as response:
            if response.status == 200:
                token_data = await response.json()
                return token_data["access_token"]
            else:
                print(f"Reddit auth error: {response.status}")
                
    except Exception as e:
        print(f"Error getting Reddit token: {e}")
        
    return None

async def fetch_reddit_posts(session, token, user_agent, subreddits=None, limit=100):
    """Fetch recent finance-related Reddit posts"""
    if not token:
        return []
        
    if subreddits is None:
        subreddits = ["investing", "stocks", "wallstreetbets", "finance", "stockmarket"]
        
    headers = {
        "Authorization": f"Bearer {token}",
        "User-Agent": user_agent
    }
    
    posts = []
    reddit_api_url = "https://oauth.reddit.com"
    
    for subreddit in subreddits:
        try:
            url = f"{reddit_api_url}/r/{subreddit}/hot"
            params = {"limit": limit // len(subreddits)}
            
            async with session.get(url, headers=headers, params=params) as response:
                if response.status == 200:
                    data = await response.json()
                    
                    for post in data["data"]["children"]:
                        post_data = post["data"]
                        created_at = datetime.fromtimestamp(post_data["created_utc"], tz=timezone.utc)
                        
                        # Create SocialMediaPost without the engagement field
                        posts.append(SocialMediaPost(
                            platform="Reddit",
                            user=post_data.get("author", "unknown"),
                            content=f"{post_data['title']}\n\n{post_data['selftext']}",
                            url=f"https://reddit.com{post_data['permalink']}",
                            date=created_at,
                            subreddit=subreddit
                        ))
                else:
                    print(f"Reddit API error for r/{subreddit}: {response.status}")
                    
        except Exception as e:
            print(f"Error fetching r/{subreddit}: {e}")
            
    return posts

async def collect_all_data():
    """Collect all types of data"""
    print("Starting data collection with environment variables loaded...")
    
    # Create database session
    Session = sessionmaker(bind=engine)
    db_session = Session()
    
    try:
        # Collect all types of data
        await collect_news_data(db_session)
        await collect_social_media_data(db_session)
        await collect_financial_terms(db_session)
    finally:
        # Close the database session
        db_session.close()
    
    print("\nData collection complete!")

def view_news_data():
    """View news articles from both databases"""
    print("\n=== NEWS ARTICLES ===")
    
    # First check the main database
    Session = sessionmaker(bind=engine)
    session = Session()
    
    try:
        news_articles = session.query(NewsArticle).all()
        print(f"Main database news articles: {len(news_articles)}")
        
        if news_articles:
            for i, article in enumerate(news_articles[:5]):  # Show first 5 articles
                print_separator()
                print(f"Article {i+1}:")
                print(f"Title: {article.title}")
                print(f"Source: {article.source}")
                print(f"Date: {article.date}")
                print(f"URL: {article.url}")
                # Show a snippet of content
                content_preview = article.content[:150] + "..." if len(article.content) > 150 else article.content
                print(f"Content snippet: {content_preview}")
            
            if len(news_articles) > 5:
                print_separator()
                print(f"... and {len(news_articles) - 5} more articles")
    finally:
        session.close()
    
    # Now check the finance_news.db database
    finance_news_db_path = Path("data/finance_news.db")
    if finance_news_db_path.exists():
        print("\n=== FINANCE NEWS DATABASE ===")
        conn = sqlite3.connect(finance_news_db_path)
        cursor = conn.cursor()
        
        try:
            # Get count of articles
            cursor.execute("SELECT COUNT(*) FROM articles")
            count = cursor.fetchone()[0]
            print(f"Finance news database articles: {count}")
            
            if count > 0:
                # Get sample articles
                cursor.execute("SELECT id, title, content, source, url, published_at FROM articles LIMIT 5")
                articles = cursor.fetchall()
                
                for i, article in enumerate(articles):
                    print_separator()
                    print(f"Article {i+1}:")
                    print(f"Title: {article[1]}")
                    print(f"Source: {article[3]}")
                    print(f"Date: {article[5]}")
                    print(f"URL: {article[4]}")
                    # Show a snippet of content
                    content = article[2]
                    content_preview = content[:150] + "..." if len(content) > 150 else content
                    print(f"Content snippet: {content_preview}")
                
                if count > 5:
                    print_separator()
                    print(f"... and {count - 5} more articles")
        finally:
            conn.close()

def view_social_media_data():
    """View social media posts"""
    print("\n=== SOCIAL MEDIA POSTS ===")
    
    # Create a session
    Session = sessionmaker(bind=engine)
    session = Session()
    
    try:
        # Query social media posts
        social_posts = session.query(SocialMediaPost).all()
        print(f"Total social media posts: {len(social_posts)}")
        
        # Group by platform
        platforms = {}
        for post in social_posts:
            platform = post.platform
            if platform not in platforms:
                platforms[platform] = []
            platforms[platform].append(post)
        
        # Print summary by platform
        for platform, posts in platforms.items():
            print(f"\n{platform}: {len(posts)} posts")
        
        # Print sample posts from each platform
        for platform, posts in platforms.items():
            print(f"\n=== {platform.upper()} POSTS ===")
            
            # Sort by date (newest first)
            sorted_posts = sorted(posts, key=lambda x: x.date if x.date else datetime.min, reverse=True)
            
            # Show first 5 posts
            for i, post in enumerate(sorted_posts[:5]):
                print_separator()
                print(f"Post {i+1}:")
                print(f"User: {post.user}")
                print(f"Date: {post.date}")
                if post.subreddit:
                    print(f"Subreddit: {post.subreddit}")
                print(f"URL: {post.url}")
                
                # Show a snippet of content
                content_preview = post.content[:150] + "..." if len(post.content) > 150 else post.content
                print(f"Content snippet: {content_preview}")
            
            if len(sorted_posts) > 5:
                print_separator()
                print(f"... and {len(sorted_posts) - 5} more {platform} posts")
    finally:
        session.close()

def view_financial_terms():
    """View financial terms"""
    print("\n=== FINANCIAL TERMS ===")
    
    # Create a session
    Session = sessionmaker(bind=engine)
    session = Session()
    
    try:
        # Query financial terms
        financial_terms = session.query(FinancialTerm).all()
        print(f"Total financial terms: {len(financial_terms)}")
        
        if financial_terms:
            for i, term in enumerate(financial_terms[:10]):  # Show first 10 terms
                print_separator()
                print(f"Term {i+1}: {term.term}")
                # Show a snippet of definition
                definition_preview = term.definition[:150] + "..." if len(term.definition) > 150 else term.definition
                print(f"Definition: {definition_preview}")
                print(f"URL: {term.url}")
            
            if len(financial_terms) > 10:
                print_separator()
                print(f"... and {len(financial_terms) - 10} more terms")
    finally:
        session.close()

def view_all_data():
    """View all types of data"""
    view_news_data()
    view_social_media_data()
    view_financial_terms()

def signal_handler(sig, frame):
    """Handle Ctrl+C to gracefully exit scheduled data collection"""
    print("\nExiting data collection script...")
    sys.exit(0)

def parse_args():
    """Parse command line arguments"""
    parser = argparse.ArgumentParser(description="Finance Data Collection and Viewing Tools")
    
    subparsers = parser.add_subparsers(dest="command", help="Command to run")
    
    # Collect data command
    collect_parser = subparsers.add_parser("collect", help="Collect financial data once")
    collect_parser.add_argument("--all", action="store_true", help="Collect all types of data")
    collect_parser.add_argument("--news", action="store_true", help="Collect news articles")
    collect_parser.add_argument("--social", action="store_true", help="Collect social media posts")
    collect_parser.add_argument("--terms", action="store_true", help="Collect financial terms")
    
    # Schedule data collection command
    schedule_parser = subparsers.add_parser("schedule", help="Schedule periodic data collection")
    schedule_parser.add_argument("--all", action="store_true", help="Schedule all types of data collection")
    schedule_parser.add_argument("--news", action="store_true", help="Schedule news article collection")
    schedule_parser.add_argument("--social", action="store_true", help="Schedule social media post collection")
    schedule_parser.add_argument("--terms", action="store_true", help="Schedule financial term collection")
    schedule_parser.add_argument(
        "--interval",
        type=int,
        default=60,
        help="Interval in minutes between data collection (default: 60 minutes)"
    )
    
    # View data command
    view_parser = subparsers.add_parser("view", help="View collected data")
    view_parser.add_argument("--all", action="store_true", help="View all types of data")
    view_parser.add_argument("--news", action="store_true", help="View news articles")
    view_parser.add_argument("--social", action="store_true", help="View social media posts")
    view_parser.add_argument("--terms", action="store_true", help="View financial terms")
    
    # Recreate database command
    subparsers.add_parser("recreate-db", help="Recreate database schema")
    
    return parser.parse_args()

def create_services(db_session):
    """Create all scraper services with DB session"""
    news_scraper = NewsScraperService(db_session)
    social_scraper = SocialMediaScraperService(db_session)
    knowledge_scraper = FinancialKnowledgeService(db_session)
    coordinator = ScraperCoordinator(
        news_service=news_scraper,
        social_media_service=social_scraper,
        financial_knowledge_service=knowledge_scraper
    )
    return {
        "news": news_scraper,
        "social": social_scraper, 
        "knowledge": knowledge_scraper,
        "coordinator": coordinator
    }

def start_scheduled_services(services, service_names, interval_minutes):
    """Start scheduled services to run at specified interval"""
    # Convert services to list
    services_to_run = []
    if "news" in service_names or "all" in service_names:
        services_to_run.append(("News Scraper", services["news"]))
    if "social" in service_names or "all" in service_names:
        services_to_run.append(("Social Media Scraper", services["social"]))
    if "knowledge" in service_names or "all" in service_names:
        services_to_run.append(("Financial Knowledge Scraper", services["knowledge"]))
    
    # Start each service with the given interval
    for name, service in services_to_run:
        print(f"Starting {name} to run every {interval_minutes} minutes")
        if interval_minutes == 60:
            # Use the built-in hourly scheduling for 60 minute intervals
            service.start_hourly_scheduling()
        else:
            # For non-hourly intervals, modify the schedule
            # Clear any existing schedules
            schedule.clear()
            # Set the new schedule
            schedule.every(interval_minutes).minutes.do(service.hourly_update_job)
    
    if services_to_run:
        print(f"All services scheduled. Press Ctrl+C to exit.")
        try:
            while True:
                schedule.run_pending()
                time.sleep(1)
        except KeyboardInterrupt:
            print("\nStopping scheduled services...")
            for name, service in services_to_run:
                service.stop_hourly_scheduling()
    else:
        print("No services selected to run")

async def main():
    """Main entry point"""
    # Register signal handler for Ctrl+C
    signal.signal(signal.SIGINT, signal_handler)
    
    # Load environment variables
    load_dotenv()
    
    args = parse_args()
    
    if args.command == "collect":
        # Create database session
        Session = sessionmaker(bind=engine)
        db_session = Session()
        
        try:
            if args.all or (not args.news and not args.social and not args.terms):
                await collect_all_data()
            else:
                if args.news:
                    await collect_news_data(db_session)
                if args.social:
                    await collect_social_media_data(db_session)
                if args.terms:
                    await collect_financial_terms(db_session)
        finally:
            db_session.close()
    
    elif args.command == "schedule":
        # Create database session
        Session = sessionmaker(bind=engine)
        db_session = Session()
        
        try:
            # Create all services
            services = create_services(db_session)
            
            # Parse service names
            service_names = []
            if args.all or (not args.news and not args.social and not args.terms):
                service_names = ["all"]
            else:
                if args.news:
                    service_names.append("news")
                if args.social:
                    service_names.append("social")
                if args.terms:
                    service_names.append("knowledge")
            
            # Start scheduled services
            start_scheduled_services(services, service_names, args.interval)
        finally:
            db_session.close()
    
    elif args.command == "view":
        if args.all or (not args.news and not args.social and not args.terms):
            view_all_data()
        else:
            if args.news:
                view_news_data()
            if args.social:
                view_social_media_data()
            if args.terms:
                view_financial_terms()
    
    elif args.command == "recreate-db":
        recreate_database()
    
    else:
        print("Please specify a command. Use --help for more information.")
        print(__doc__)

if __name__ == "__main__":
    asyncio.run(main())
