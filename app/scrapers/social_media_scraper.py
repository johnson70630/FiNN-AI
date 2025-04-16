import aiohttp
import asyncio
import os
from datetime import datetime, timezone
from sqlalchemy.orm import Session
from ..database import SocialMediaPost

class SocialMediaScraperService:
    def __init__(self, db: Session):
        self.db = db
        
        # Twitter settings
        self.twitter_bearer_token = os.getenv("TWITTER_BEARER_TOKEN")
        self.twitter_api_url = "https://api.twitter.com/2/tweets/search/recent"
        self.twitter_query = "(stock market OR investing OR finance) -is:retweet lang:en"
        
        # Reddit settings
        self.reddit_client_id = os.getenv("REDDIT_CLIENT_ID")
        self.reddit_client_secret = os.getenv("REDDIT_CLIENT_SECRET")
        self.reddit_user_agent = os.getenv("REDDIT_USER_AGENT")
        self.reddit_auth_url = "https://www.reddit.com/api/v1/access_token"
        self.reddit_api_url = "https://oauth.reddit.com"
        self.subreddits = ["investing", "stocks", "wallstreetbets", "finance", "stockmarket"]
        
        # Common settings
        self.limit = 100
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
        }
        self.timeout = aiohttp.ClientTimeout(total=30)

    async def fetch_twitter_posts(self, session) -> list:
        """Fetch recent finance-related tweets"""
        if not self.twitter_bearer_token:
            print("Twitter bearer token not found")
            return []
            
        headers = {
            "Authorization": f"Bearer {self.twitter_bearer_token}",
            **self.headers
        }
        
        params = {
            "query": self.twitter_query,
            "max_results": self.limit,
            "tweet.fields": "created_at,public_metrics,author_id"
        }
        
        try:
            async with session.get(self.twitter_api_url, headers=headers, params=params) as response:
                if response.status == 200:
                    data = await response.json()
                    
                    posts = []
                    for tweet in data.get("data", []):
                        tweet_id = tweet["id"]
                        tweet_url = f"https://twitter.com/i/web/status/{tweet_id}"
                        created_at = datetime.strptime(tweet["created_at"], "%Y-%m-%dT%H:%M:%S.%fZ")
                        
                        posts.append(SocialMediaPost(
                            platform="Twitter",
                            content=tweet["text"],
                            url=tweet_url,
                            date=created_at,
                            engagement=tweet["public_metrics"]["like_count"]
                        ))
                        
                    return posts
                else:
                    print(f"Twitter API error: {response.status}")
                    
        except Exception as e:
            print(f"Error fetching tweets: {e}")
            
        return []

    async def get_reddit_token(self, session) -> str:
        """Get Reddit OAuth token"""
        if not all([self.reddit_client_id, self.reddit_client_secret]):
            print("Reddit credentials not found")
            return None
            
        auth = aiohttp.BasicAuth(self.reddit_client_id, self.reddit_client_secret)
        data = {"grant_type": "client_credentials"}
        headers = {"User-Agent": self.reddit_user_agent}
        
        try:
            async with session.post(self.reddit_auth_url, auth=auth, data=data, headers=headers) as response:
                if response.status == 200:
                    token_data = await response.json()
                    return token_data["access_token"]
                else:
                    print(f"Reddit auth error: {response.status}")
                    
        except Exception as e:
            print(f"Error getting Reddit token: {e}")
            
        return None

    async def fetch_reddit_posts(self, session, token: str) -> list:
        """Fetch recent finance-related Reddit posts"""
        if not token:
            return []
            
        headers = {
            "Authorization": f"Bearer {token}",
            "User-Agent": self.reddit_user_agent
        }
        
        posts = []
        for subreddit in self.subreddits:
            try:
                url = f"{self.reddit_api_url}/r/{subreddit}/hot"
                params = {"limit": self.limit // len(self.subreddits)}
                
                async with session.get(url, headers=headers, params=params) as response:
                    if response.status == 200:
                        data = await response.json()
                        
                        for post in data["data"]["children"]:
                            post_data = post["data"]
                            created_at = datetime.fromtimestamp(post_data["created_utc"], tz=timezone.utc)
                            
                            posts.append(SocialMediaPost(
                                platform="Reddit",
                                content=f"{post_data['title']}\n\n{post_data['selftext']}",
                                url=f"https://reddit.com{post_data['permalink']}",
                                date=created_at,
                                engagement=post_data["score"]
                            ))
                    else:
                        print(f"Reddit API error for r/{subreddit}: {response.status}")
                        
            except Exception as e:
                print(f"Error fetching r/{subreddit}: {e}")
                
        return posts

    def get_existing_urls(self) -> set:
        """Get URLs of existing posts"""
        return {post.url for post in self.db.query(SocialMediaPost).all()}

    async def update_posts_database(self) -> int:
        """Update social media posts database"""
        # Get existing URLs
        existing_urls = self.get_existing_urls()
        
        # Create session for API calls
        connector = aiohttp.TCPConnector(limit=10)
        async with aiohttp.ClientSession(connector=connector) as session:
            # Fetch Twitter posts
            twitter_task = asyncio.create_task(self.fetch_twitter_posts(session))
            
            # Fetch Reddit posts
            reddit_token = await self.get_reddit_token(session)
            reddit_task = asyncio.create_task(self.fetch_reddit_posts(session, reddit_token))
            
            # Wait for all tasks
            all_posts = []
            for task in [twitter_task, reddit_task]:
                try:
                    posts = await task
                    all_posts.extend(posts)
                except Exception as e:
                    print(f"Error in social media task: {e}")
        
        # Add new posts to database
        added_count = 0
        for post in all_posts:
            if post.url not in existing_urls:
                self.db.add(post)
                added_count += 1
        
        # Commit if there are new posts
        if added_count > 0:
            self.db.commit()
            
        return added_count
