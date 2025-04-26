import os
import asyncio
import time
import threading
import schedule
from datetime import datetime, timezone
from sqlalchemy.orm import Session
from ..database import SocialMediaPost
from dotenv import load_dotenv
from playwright.sync_api import sync_playwright
import aiohttp

# Load environment variables
load_dotenv()

class SocialMediaScraperService:
    def __init__(self, db: Session):
        self.db = db
        
        # Twitter login credentials
        self.twitter_username = os.getenv("TWITTER_USERNAME")
        self.twitter_password = os.getenv("TWITTER_PASSWORD")

        if not self.twitter_username or not self.twitter_password:
            raise RuntimeError("Twitter username/password missing in environment variables")

        # Reddit credentials
        self.reddit_client_id = os.getenv("REDDIT_CLIENT_ID")
        self.reddit_client_secret = os.getenv("REDDIT_CLIENT_SECRET")
        self.reddit_user_agent = os.getenv("REDDIT_USER_AGENT")

        if not self.reddit_client_id or not self.reddit_client_secret or not self.reddit_user_agent:
            raise RuntimeError("Reddit credentials missing in environment variables")

        # Other settings
        self.limit = 100
        self.keywords = ["stock", "finance", "market", "nasdaq", "invest", "earnings"]
        self.subreddits = ["investing", "stocks", "wallstreetbets", "finance", "stockmarket"]

        # Scheduling properties
        self.is_scheduled = False
        self.scheduler_thread = None

    def get_existing_urls(self) -> set:
        """Fetch existing URLs from database to avoid duplicates"""
        return {post.url for post in self.db.query(SocialMediaPost).all()}

    def _scrape_twitter_sync(self, per_keyword_limit: int) -> list:
        """Scrape Twitter posts using Playwright synchronously"""
        results = []
        try:
            with sync_playwright() as pw:
                browser = pw.chromium.launch(headless=True)
                page = browser.new_page()

                page.goto("https://x.com/i/flow/login")
                page.fill('input[name="text"]', self.twitter_username)
                page.get_by_role("button", name="Next").click()
                page.wait_for_selector('input[name="password"]', timeout=10000)
                page.fill('input[name="password"]', self.twitter_password)
                page.get_by_role("button", name="Log in").click()
                page.wait_for_url("https://x.com/home", timeout=20000)
                print("Logged in to Twitter")

                for keyword in self.keywords:
                    collected = []
                    url = f"https://x.com/search?q={keyword}&f=live"
                    page.goto(url)
                    start = time.time()

                    while len(collected) < per_keyword_limit and time.time() - start < 60:
                        page.keyboard.press("PageDown")
                        time.sleep(0.5)

                        for handle in page.locator("article[role=article]").element_handles():
                            try:
                                href = handle.query_selector("a time").evaluate("e => e.parentElement.href")
                                tid = href.rsplit("/", 1)[-1]
                                txt = handle.query_selector("div[lang]").inner_text().replace("\n", " ")
                                usr = handle.query_selector("div span span").inner_text()
                                dt = handle.query_selector("time").get_attribute("datetime")

                                collected.append({
                                    "platform": "Twitter",
                                    "user": usr,
                                    "content": txt,
                                    "date": dt,
                                    "url": href
                                })

                                if len(collected) >= per_keyword_limit:
                                    break
                            except:
                                continue

                    print(f"Collected {len(collected)} tweets for keyword '{keyword}'")
                    results.extend(collected)

                browser.close()

        except Exception as e:
            print(f"Error scraping Twitter: {e}")

        return results

    async def fetch_twitter_posts(self) -> list:
        """Async wrapper for Twitter scraping"""
        return await asyncio.to_thread(self._scrape_twitter_sync, self.limit // len(self.keywords))

    async def get_reddit_token(self, session) -> str:
        """Get Reddit OAuth token"""
        auth = aiohttp.BasicAuth(self.reddit_client_id, self.reddit_client_secret)
        data = {"grant_type": "client_credentials"}
        headers = {"User-Agent": self.reddit_user_agent}

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

    async def fetch_reddit_posts(self) -> list:
        """Fetch recent finance-related Reddit posts"""
        posts = []
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=30)) as session:
            token = await self.get_reddit_token(session)
            if not token:
                return posts

            headers = {
                "Authorization": f"Bearer {token}",
                "User-Agent": self.reddit_user_agent
            }

            reddit_api_url = "https://oauth.reddit.com"

            for subreddit in self.subreddits:
                try:
                    url = f"{reddit_api_url}/r/{subreddit}/hot"
                    params = {"limit": self.limit // len(self.subreddits)}

                    async with session.get(url, headers=headers, params=params) as response:
                        if response.status == 200:
                            data = await response.json()

                            for post in data["data"]["children"]:
                                post_data = post["data"]
                                created_at = datetime.fromtimestamp(post_data["created_utc"], tz=timezone.utc)

                                posts.append({
                                    "platform": "Reddit",
                                    "user": post_data.get("author", "unknown"),
                                    "content": f"{post_data['title']}\n\n{post_data['selftext']}",
                                    "url": f"https://reddit.com{post_data['permalink']}",
                                    "date": created_at.isoformat()
                                })
                        else:
                            print(f"Reddit API error for r/{subreddit}: {response.status}")
                except Exception as e:
                    print(f"Error fetching r/{subreddit}: {e}")

        return posts

    async def update_posts_database(self) -> int:
        """Collect new social media posts and save to database"""
        existing_urls = self.get_existing_urls()

        twitter_task = asyncio.create_task(self.fetch_twitter_posts())
        reddit_task = asyncio.create_task(self.fetch_reddit_posts())

        all_posts = []
        for task in [twitter_task, reddit_task]:
            try:
                posts = await task
                all_posts.extend(posts)
            except Exception as e:
                print(f"Error fetching posts: {e}")

        added_count = 0
        for post in all_posts:
            if post["url"] not in existing_urls:
                new_post = SocialMediaPost(
                    platform=post["platform"],
                    user=post.get("user", "unknown"),
                    content=post["content"],
                    url=post["url"],
                    date=datetime.fromisoformat(post["date"])
                )
                self.db.add(new_post)
                added_count += 1

        if added_count > 0:
            self.db.commit()

        print(f"Added {added_count} new social media posts to database")
        return added_count

    def hourly_update_job(self):
        """Schedule job to update posts"""
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            result = loop.run_until_complete(self.update_posts_database())
            print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] Scheduled social media job completed. Added {result} new posts.")
        except Exception as e:
            print(f"Error in scheduled social media job: {e}")
        finally:
            loop.close()

    def start_hourly_scheduling(self):
        """Start scraping every hour"""
        if self.is_scheduled:
            print("Hourly social media scheduling is already running")
            return

        def run_scheduler():
            schedule.every(1).hour.do(self.hourly_update_job)
            self.hourly_update_job()

            while self.is_scheduled:
                schedule.run_pending()
                time.sleep(60)

        self.is_scheduled = True
        self.scheduler_thread = threading.Thread(target=run_scheduler)
        self.scheduler_thread.daemon = True
        self.scheduler_thread.start()
        print("Started hourly scheduling of social media updates")

    def stop_hourly_scheduling(self):
        """Stop hourly scraping"""
        if not self.is_scheduled:
            print("Hourly social media scheduling is not running")
            return

        self.is_scheduled = False
        if self.scheduler_thread:
            self.scheduler_thread.join(timeout=2)
            self.scheduler_thread = None
        print("Stopped hourly scheduling of social media updates")
