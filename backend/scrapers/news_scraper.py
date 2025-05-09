import asyncio
import aiohttp
from bs4 import BeautifulSoup
from datetime import datetime
import re
from urllib.parse import urlparse
from playwright.async_api import async_playwright
from sqlalchemy.orm import Session
from backend.core.database import NewsArticle
from email.utils import parsedate_to_datetime
import time
import schedule
import threading

class NewsScraperService:
    def __init__(self, db: Session):
        self.db = db
        
        # URLs
        self.yahoo_rss_urls = [
            "https://feeds.finance.yahoo.com/rss/2.0/headline?s=^GSPC",  # S&P 500
            "https://feeds.finance.yahoo.com/rss/2.0/headline?s=^IXIC",  # NASDAQ
            "https://feeds.finance.yahoo.com/rss/2.0/headline?s=MSFT,AAPL,GOOGL,AMZN,META"  # Tech stocks
        ]
        self.cnbc_rss_url = "https://www.cnbc.com/id/10000664/device/rss/rss.html"
        self.finviz_url = "https://finviz.com/news.ashx"
        self.investing_com_url = "https://www.investing.com/news/stock-market-news"
        
        # Settings
        self.limit = 100
        self.blocked_domains = [
            "wsj.com", "barrons.com", "bloomberg.com", "nytimes.com",
            "reuters.com", "seekingalpha.com", "marketwatch.com"
        ]
        
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
        }
        self.timeout = aiohttp.ClientTimeout(total=30)
        
        # Scheduling properties
        self.is_scheduled = False
        self.scheduler_thread = None

    def should_skip_url(self, url: str) -> bool:
        """Check if URL should be skipped"""
        try:
            domain = urlparse(url).netloc.lower()
            return any(blocked in domain for blocked in self.blocked_domains)
        except:
            return True

    def clean_text(self, text: str) -> str:
        """Clean text content"""
        if not text:
            return ""
        text = re.sub(r'\s+', ' ', text)
        return text.strip()

    async def fetch_yahoo_finance(self, session) -> list:
        """Fetch news from Yahoo Finance RSS feeds"""
        articles = []
        
        for rss_url in self.yahoo_rss_urls:
            try:
                async with session.get(rss_url, ssl=False) as response:
                    if response.status != 200:
                        print(f"Failed to fetch RSS feed {rss_url}: {response.status}")
                        continue
                        
                    content = await response.text()
                    articles.extend(self.parse_rss_items(content, "Yahoo Finance"))
                    
            except Exception as e:
                print(f"Error fetching Yahoo Finance RSS {rss_url}: {e}")
                
        return articles

    async def fetch_cnbc_news(self, session) -> list:
        """Fetch news from CNBC RSS feed"""
        try:
            async with session.get(self.cnbc_rss_url) as response:
                if response.status == 200:
                    content = await response.text()
                    return self.parse_rss_items(content, "CNBC")
        except Exception as e:
            print(f"CNBC error: {e}")
        return []

    async def fetch_finviz_news(self, session) -> list:
        """Fetch news from Finviz"""
        try:
            async with session.get(self.finviz_url) as response:
                if response.status == 200:
                    content = await response.text()
                    return self.parse_finviz_items(content)
        except Exception as e:
            print(f"Finviz error: {e}")
        return []

    async def fetch_investing_com(self, session) -> list:
        """Fetch news from Investing.com"""
        try:
            async with session.get(self.investing_com_url) as response:
                if response.status == 200:
                    content = await response.text()
                    return self.parse_investing_com_items(content)
        except Exception as e:
            print(f"Investing.com error: {e}")
        return []

    def parse_rss_items(self, content: str, source: str) -> list:
        """Parse RSS feed items"""
        try:
            # First try parsing as XML
            soup = BeautifulSoup(content, 'xml')
            items = soup.find_all('item')
            
            # If no items found, try parsing as HTML
            if not items:
                soup = BeautifulSoup(content, 'html.parser')
                items = soup.find_all('item')
            
            # Limit to the maximum number of items
            items = items[:self.limit]
            results = []
            
            for item in items:
                title_tag = item.find('title')
                link_tag = item.find('link')
                date_tag = item.find('pubDate')
                desc_tag = item.find('description')
                
                if not all([title_tag, link_tag]):
                    continue
                    
                title = self.clean_text(title_tag.get_text())
                link = link_tag.get_text().strip()
                
                if self.should_skip_url(link):
                    continue
                    
                pub_date = None
                if date_tag:
                    date_text = date_tag.get_text().strip()
                    try:
                        pub_date = parsedate_to_datetime(date_text)
                    except Exception:
                        pub_date = datetime.now()
                else:
                    pub_date = datetime.now()
                
                summary = ""
                if desc_tag:
                    desc_text = desc_tag.get_text()
                    # Don't parse HTML here directly, just clean the text
                    summary = self.clean_text(desc_text)

                results.append(NewsArticle(
                    title=title,
                    url=link,
                    date=pub_date,
                    content=summary,
                    source=source
                ))
                
            return results
        except Exception as e:
            print(f"Error parsing RSS from {source}: {e}")
            return []

    def parse_finviz_items(self, content: str) -> list:
        """Parse Finviz news items"""
        soup = BeautifulSoup(content, 'html.parser')
        items = []
        
        for a in soup.find_all('a', href=True):
            if len(items) >= self.limit:
                break
                
            href = a['href']
            if not (href.startswith('http') and 'finviz' not in href):
                continue
                
            if self.should_skip_url(href):
                continue
                
            title = self.clean_text(a.get_text())
            if not title:
                continue
                
            pub_time = datetime.now()
            if a.previous_sibling:
                time_text = str(a.previous_sibling).strip()
                if time_text:
                    if time_text.endswith("AM") or time_text.endswith("PM"):
                        try:
                            today = datetime.now()
                            pub_time = datetime.strptime(f"{today.strftime('%Y-%m-%d')} {time_text}", "%Y-%m-%d %I:%M %p")
                        except:
                            pass
                    else:
                        try:
                            year = datetime.now().year
                            pub_time = datetime.strptime(f"{time_text} {year}", "%b-%d %Y")
                        except:
                            pass

            items.append(NewsArticle(
                title=title,
                url=href,
                date=pub_time,
                content="",  # Will be updated with full content
                source="Finviz"
            ))
            
        return items

    def parse_investing_com_items(self, content: str) -> list:
        """Parse Investing.com news items"""
        soup = BeautifulSoup(content, 'html.parser')
        items = []
        
        for article in soup.find_all('article', class_='js-article-item'):
            if len(items) >= self.limit:
                break
                
            title_tag = article.find('a', class_='title')
            if not title_tag:
                continue
                
            title = self.clean_text(title_tag.get_text())
            url = f"https://www.investing.com{title_tag['href']}"
            
            time_tag = article.find('span', class_='date')
            pub_time = datetime.now()
            if time_tag:
                try:
                    time_text = time_tag.get_text().strip()
                    if "ago" in time_text.lower():
                        # Handle relative time (e.g., "5 hours ago")
                        pass  # Use current time
                    else:
                        # Handle absolute time
                        pub_time = datetime.strptime(time_text, "%b %d, %Y")
                except:
                    pass

            items.append(NewsArticle(
                title=title,
                url=url,
                date=pub_time,
                content="",  # Will be updated with full content
                source="Investing.com"
            ))
            
        return items

    async def fetch_full_content(self, playwright, url: str) -> str:
        """Fetch full article content using Playwright"""
        if self.should_skip_url(url):
            return "[Content blocked or requires subscription]"
            
        try:
            browser = await playwright.chromium.launch(args=['--disable-gpu', '--no-sandbox', '--disable-dev-shm-usage'])
            context = await browser.new_context(
                viewport={'width': 1280, 'height': 720},
                user_agent=self.headers['User-Agent']
            )
            page = await context.new_page()
            
            # Reduce timeout and add navigation timeout
            try:
                await page.goto(url, timeout=20000, wait_until="domcontentloaded")
            except Exception as e:
                print(f"Timeout loading {url}: {e}")
                await browser.close()
                return ""
                
            content = await page.content()
            soup = BeautifulSoup(content, 'html.parser')
            
            # Memory optimization: Clear page content after parsing
            await page.evaluate("document.body.innerHTML = ''")
            await context.close()
            await browser.close()
            
            article = soup.find('article')
            if article:
                text = article.get_text()
            else:
                paragraphs = soup.find_all('p')
                text = '\n'.join(p.get_text() for p in paragraphs)
            
            # Clear beautiful soup objects
            soup.decompose()
            return self.clean_text(text)
            
        except Exception as e:
            print(f"Error loading {url}: {e}")
            return ""

    async def fetch_all_news(self) -> list:
        """Fetch news from all sources"""
        connector = aiohttp.TCPConnector(limit=5)  # Reduced connection limit
        async with aiohttp.ClientSession(headers=self.headers, timeout=self.timeout, connector=connector) as session:
            # Fetch from all sources
            yahoo_task = asyncio.create_task(self.fetch_yahoo_finance(session))
            cnbc_task = asyncio.create_task(self.fetch_cnbc_news(session))
            finviz_task = asyncio.create_task(self.fetch_finviz_news(session))
            investing_task = asyncio.create_task(self.fetch_investing_com(session))
            
            all_news = []
            for task in [yahoo_task, cnbc_task, finviz_task, investing_task]:
                try:
                    articles = await task
                    all_news.extend(articles)
                except Exception as e:
                    print(f"Error in news task: {e}")

        # Process articles in smaller batches
        batch_size = 5  # Process 5 articles at a time
        processed_news = []
        
        async with async_playwright() as p:
            for i in range(0, len(all_news), batch_size):
                batch = all_news[i:i + batch_size]
                tasks = []
                for article in batch:
                    task = asyncio.create_task(self.fetch_full_content(p, article.url))
                    tasks.append((article, task))

                for article, task in tasks:
                    try:
                        content = await task
                        if content:
                            article.content = content
                            processed_news.append(article)
                    except Exception as e:
                        print(f"Error processing article {article.url}: {e}")
                        continue
                
                # Add a small delay between batches to prevent overload
                await asyncio.sleep(1)

        return processed_news

    def get_existing_urls(self) -> set:
        """Get URLs of existing articles"""
        try:
            # Only select the URL column to avoid issues with missing columns
            return {article.url for article in self.db.query(NewsArticle.url).all()}
        except Exception as e:
            print(f"Error getting existing URLs: {e}")
            # Fallback method if there's an issue with the query
            try:
                # Try a more robust approach that explicitly gets just the urls
                from sqlalchemy import select
                stmt = select(NewsArticle.url)
                result = self.db.execute(stmt)
                return {row[0] for row in result if row[0]}
            except Exception as e2:
                print(f"Second error getting URLs: {e2}")
                # Last resort fallback - return empty set if we can't query the database
                return set()

    async def update_news_database(self) -> int:
        """Update the news database by scraping all sources"""
        # Get existing URLs
        existing_urls = self.get_existing_urls()
        
        # Scrape new articles
        new_articles = await self.fetch_all_news()
        
        # Filter out duplicates and add new articles
        added_count = 0
        for article in new_articles:
            if article.url not in existing_urls:
                self.db.add(article)
                added_count += 1
        
        # Commit changes
        if added_count > 0:
            self.db.commit()
            
        return added_count

    def hourly_update_job(self):
        """Run the update_news_database function in the event loop"""
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            result = loop.run_until_complete(self.update_news_database())
            print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] Scheduled news job completed. Added {result} new articles.")
        except Exception as e:
            print(f"Error in scheduled news job: {e}")
        finally:
            loop.close()
    
    def start_hourly_scheduling(self):
        """Start hourly scheduling of news scraping"""
        if self.is_scheduled:
            print("Hourly news scheduling is already running")
            return
        
        def run_scheduler():
            schedule.every(1).hour.do(self.hourly_update_job)
            # Run the job immediately when starting
            self.hourly_update_job()
            
            while self.is_scheduled:
                schedule.run_pending()
                time.sleep(60)  # Check every minute
        
        self.is_scheduled = True
        self.scheduler_thread = threading.Thread(target=run_scheduler)
        self.scheduler_thread.daemon = True
        self.scheduler_thread.start()
        print("Started hourly scheduling of news updates")
    
    def stop_hourly_scheduling(self):
        """Stop the hourly scheduling"""
        if not self.is_scheduled:
            print("Hourly news scheduling is not running")
            return
        
        self.is_scheduled = False
        if self.scheduler_thread:
            self.scheduler_thread.join(timeout=2)
            self.scheduler_thread = None
        print("Stopped hourly scheduling of news updates")
