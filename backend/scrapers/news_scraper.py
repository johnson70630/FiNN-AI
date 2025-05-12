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
        """Fetch news from Yahoo Finance RSS feeds with retry mechanism"""
        articles = []
        
        for rss_url in self.yahoo_rss_urls:
            max_retries = 3
            retry_count = 0
            retry_delay = 2  # Initial delay in seconds
            
            while retry_count <= max_retries:
                try:
                    # Add delay between requests to avoid rate limiting
                    if retry_count > 0:
                        await asyncio.sleep(retry_delay)
                        print(f"Retrying {rss_url} (attempt {retry_count} of {max_retries})")
                    
                    async with session.get(rss_url, ssl=False) as response:
                        if response.status == 200:
                            content = await response.text()
                            articles.extend(self.parse_rss_items(content, "Yahoo Finance"))
                            break  # Success, exit the retry loop
                        elif response.status == 429:
                            # Too many requests, increase retry delay and try again
                            print(f"Rate limit hit for {rss_url} (429). Retrying after delay.")
                            retry_count += 1
                            retry_delay *= 2  # Exponential backoff
                        else:
                            print(f"Failed to fetch RSS feed {rss_url}: {response.status}")
                            break  # Don't retry for non-429 errors
                        
                except Exception as e:
                    print(f"Error fetching Yahoo Finance RSS {rss_url}: {e}")
                    break  # Don't retry for exceptions
                    
            # Add a delay between different RSS URLs
            await asyncio.sleep(1)
                
        return articles

    async def fetch_cnbc_news(self, session) -> list:
        """Fetch news from CNBC RSS feed with retry mechanism"""
        max_retries = 3
        retry_count = 0
        retry_delay = 2  # Initial delay in seconds
        
        while retry_count <= max_retries:
            try:
                # Add delay between retries
                if retry_count > 0:
                    await asyncio.sleep(retry_delay)
                    print(f"Retrying CNBC (attempt {retry_count} of {max_retries})")
                
                async with session.get(self.cnbc_rss_url, ssl=False) as response:
                    if response.status == 200:
                        content = await response.text()
                        articles = self.parse_rss_items(content, "CNBC")
                        print(f"Successfully fetched {len(articles)} articles from CNBC")
                        return articles
                    elif response.status == 429:
                        # Too many requests, increase retry delay and try again
                        print(f"Rate limit hit for CNBC (429). Retrying after delay.")
                        retry_count += 1
                        retry_delay *= 2  # Exponential backoff
                    else:
                        print(f"Failed to fetch CNBC RSS feed: {response.status}")
                        break  # Don't retry for non-429 errors
                    
            except Exception as e:
                print(f"Error fetching CNBC RSS: {e}")
                break  # Don't retry for exceptions
                
        print("Failed to fetch news from CNBC after all retries")
        return []

    async def fetch_finviz_news(self, session) -> list:
        """Fetch news from Finviz with retry mechanism"""
        max_retries = 3
        retry_count = 0
        retry_delay = 2  # Initial delay in seconds
        
        while retry_count <= max_retries:
            try:
                # Add delay between retries
                if retry_count > 0:
                    await asyncio.sleep(retry_delay)
                    print(f"Retrying Finviz (attempt {retry_count} of {max_retries})")
                
                async with session.get(self.finviz_url, ssl=False) as response:
                    if response.status == 200:
                        content = await response.text()
                        articles = self.parse_finviz_items(content)
                        print(f"Successfully fetched {len(articles)} articles from Finviz")
                        return articles
                    elif response.status == 429:
                        # Too many requests, increase retry delay and try again
                        print(f"Rate limit hit for Finviz (429). Retrying after delay.")
                        retry_count += 1
                        retry_delay *= 2  # Exponential backoff
                    else:
                        print(f"Failed to fetch Finviz news: {response.status}")
                        break  # Don't retry for non-429 errors
                    
            except Exception as e:
                print(f"Error fetching Finviz news: {e}")
                break  # Don't retry for exceptions
                
        print("Failed to fetch news from Finviz after all retries")
        return []

    async def fetch_investing_com(self, session) -> list:
        """Fetch news from Investing.com with retry mechanism"""
        max_retries = 3
        retry_count = 0
        retry_delay = 2  # Initial delay in seconds
        
        while retry_count <= max_retries:
            try:
                # Add delay between retries
                if retry_count > 0:
                    await asyncio.sleep(retry_delay)
                    print(f"Retrying Investing.com (attempt {retry_count} of {max_retries})")
                
                async with session.get(self.investing_com_url, ssl=False) as response:
                    if response.status == 200:
                        content = await response.text()
                        articles = self.parse_investing_com_items(content)
                        print(f"Successfully fetched {len(articles)} articles from Investing.com")
                        return articles
                    elif response.status == 429:
                        # Too many requests, increase retry delay and try again
                        print(f"Rate limit hit for Investing.com (429). Retrying after delay.")
                        retry_count += 1
                        retry_delay *= 2  # Exponential backoff
                    else:
                        print(f"Failed to fetch Investing.com news: {response.status}")
                        break  # Don't retry for non-429 errors
                    
            except Exception as e:
                print(f"Error fetching Investing.com news: {e}")
                break  # Don't retry for exceptions
                
        print("Failed to fetch news from Investing.com after all retries")
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
        connector = aiohttp.TCPConnector(limit=3)  # Reduced connection limit even further
        all_news = []
        source_counts = {"CNBC": 0, "Finviz": 0, "Investing.com": 0}
        
        # First fetch all articles from all sources
        print("Starting news collection from reliable sources...")
        async with aiohttp.ClientSession(headers=self.headers, timeout=self.timeout, connector=connector) as session:
            # Skip Yahoo Finance as it's consistently rate-limiting our requests
            print("Skipping Yahoo Finance due to rate limiting issues")
            
            # Fetch from remaining sources sequentially with delays
            print("Fetching CNBC news...")
            cnbc_articles = await self.fetch_cnbc_news(session)
            source_counts["CNBC"] = len(cnbc_articles)
            all_news.extend(cnbc_articles)
            await asyncio.sleep(3)  # Add delay between sources
            
            print("Fetching Finviz news...")
            finviz_articles = await self.fetch_finviz_news(session)
            source_counts["Finviz"] = len(finviz_articles)
            all_news.extend(finviz_articles)
            await asyncio.sleep(3)  # Add delay between sources
            
            print("Fetching Investing.com news...")
            investing_articles = await self.fetch_investing_com(session)
            source_counts["Investing.com"] = len(investing_articles)
            all_news.extend(investing_articles)
        
        print(f"Initial collection summary:")
        for source, count in source_counts.items():
            print(f"  - {source}: {count} articles")
        print(f"Total articles collected: {len(all_news)}")
        
        # Don't attempt to fetch full content if we don't have any articles
        if not all_news:
            print("No articles collected, skipping content fetching")
            return []

        # Skip full content fetching to improve reliability
        print("Skipping full content fetching to ensure reliable news updates")
        
        # Ensure all articles have some content
        for article in all_news:
            if not article.content or len(article.content.strip()) < 20:
                # Use title as content if no content is available
                article.content = f"[Summary] {article.title}"
                
        print(f"Returning {len(all_news)} news articles with basic content")
        return all_news

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
        try:
            # Get existing URLs
            existing_urls = self.get_existing_urls()
            print(f"Found {len(existing_urls)} existing news articles in database")
            
            # Scrape new articles
            print("Fetching new articles from all sources...")
            new_articles = await self.fetch_all_news()
            print(f"Fetched {len(new_articles)} articles, checking for duplicates...")
            
            # Add articles individually with separate transactions for each
            added_count = 0
            for article in new_articles:
                try:
                    # Skip if article URL already exists
                    if article.url in existing_urls:
                        continue
                        
                    # Add and commit each article individually to avoid losing all on one error
                    self.db.add(article)
                    self.db.commit()
                    
                    # Update tracking
                    existing_urls.add(article.url)
                    added_count += 1
                    print(f"Added new article: {article.title[:50]}...")
                    
                except Exception as item_error:
                    # Roll back if there was an error with this article
                    self.db.rollback()
                    print(f"Error adding article {article.url}: {str(item_error)}")
                    # Continue with next article
            
            print(f"Successfully added {added_count} new news articles to database")
            return added_count
            
        except Exception as e:
            print(f"Error in news database update: {str(e)}")
            self.db.rollback()
            return 0

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
