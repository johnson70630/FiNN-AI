import aiohttp
from bs4 import BeautifulSoup
import asyncio
from sqlalchemy.orm import Session
from ..database import FinancialTerm
import time
import schedule
import threading
import random

class FinancialKnowledgeService:
    def __init__(self, db: Session):
        self.db = db
        self.base_url = "https://www.investopedia.com"
        self.dictionary_url = f"{self.base_url}/financial-term-dictionary-4769738"
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.5",
            "Connection": "keep-alive",
            "Upgrade-Insecure-Requests": "1",
            "Cache-Control": "max-age=0"
        }
        self.timeout = aiohttp.ClientTimeout(total=30)
        self.is_scheduled = False
        self.scheduler_thread = None
        self.model_class = FinancialTerm  # Add reference to the model class
        # List of alphabet pages to scrape
        self.alphabet_urls = []

    async def fetch_alphabet_pages(self) -> list:
        """Fetch all alphabet pages from the dictionary"""
        try:
            print(f"Fetching alphabet pages from {self.dictionary_url}")
            async with aiohttp.ClientSession(headers=self.headers) as session:
                async with session.get(self.dictionary_url) as response:
                    if response.status == 200:
                        content = await response.text()
                        soup = BeautifulSoup(content, 'html.parser')
                        
                        # Find all alphabet links (a-z and numbers)
                        alphabet_links = []
                        for link in soup.find_all('a', href=True):
                            href = link['href']
                            if 'terms-beginning-with-' in href:
                                alphabet_links.append(href)
                        
                        # Remove duplicates and create full URLs
                        alphabet_urls = []
                        for href in set(alphabet_links):
                            # Make sure we don't double the domain
                            if href.startswith('http'):
                                alphabet_urls.append(href)
                            else:
                                alphabet_urls.append(f"{self.base_url}{href}")
                        print(f"Found {len(alphabet_urls)} alphabet pages")
                        return alphabet_urls
                    else:
                        print(f"Failed to fetch dictionary page: {response.status}")
                        return []
        except Exception as e:
            print(f"Error fetching alphabet pages: {e}")
            return []

    async def fetch_term_links(self) -> list:
        """Fetch all financial term links from Investopedia dictionary"""
        term_links = []
        
        # First get all alphabet pages
        alphabet_urls = await self.fetch_alphabet_pages()
        if not alphabet_urls:
            print("No alphabet pages found, cannot fetch terms")
            return []
            
        try:
            async with aiohttp.ClientSession(headers=self.headers) as session:
                # Process each alphabet page to get term links
                for alphabet_url in alphabet_urls:
                    # Add a random delay to avoid rate limiting
                    await asyncio.sleep(random.uniform(1, 3))
                    
                    print(f"Fetching terms from {alphabet_url}")
                    async with session.get(alphabet_url) as response:
                        if response.status == 200:
                            content = await response.text()
                            soup = BeautifulSoup(content, 'html.parser')
                            
                            # Find all term links on this alphabet page
                            page_links = []
                            for link in soup.find_all('a', href=True):
                                href = link['href']
                                if '/terms/' in href and '.asp' in href:
                                    page_links.append(href)
                            
                            # Add unique links to our list
                            for href in set(page_links):
                                if href.startswith('http'):
                                    term_links.append(href)
                                else:
                                    term_links.append(f"{self.base_url}{href}")
                            
                            print(f"Found {len(page_links)} terms on {alphabet_url}")
                        else:
                            print(f"Failed to fetch alphabet page {alphabet_url}: {response.status}")
                
                print(f"Total unique term links found: {len(set(term_links))}")
                return list(set(term_links))
                        
        except Exception as e:
            print(f"Error fetching term links: {e}")
            
        return term_links

    async def fetch_term_definition(self, session, url: str) -> dict:
        """Fetch definition for a single financial term"""
        try:
            # Add a small random delay to avoid rate limiting
            await asyncio.sleep(random.uniform(0.5, 1.5))
            
            async with session.get(url) as response:
                if response.status == 200:
                    content = await response.text()
                    soup = BeautifulSoup(content, 'html.parser')
                    
                    # Get term title - updated selector for current Investopedia structure
                    title = soup.find('h1')
                    if not title:
                        print(f"No title found for {url}")
                        return None
                    
                    # Clean up the title (remove "What Is" and other common prefixes)
                    title_text = title.get_text().strip()
                    for prefix in ["What Is ", "What Is a ", "What Is an ", "What Are "]:
                        if title_text.startswith(prefix):
                            title_text = title_text.replace(prefix, "", 1)
                    
                    # Remove "? Definition..." and similar suffixes
                    if "?" in title_text:
                        title_text = title_text.split("?")[0].strip()
                    elif ":" in title_text:
                        title_text = title_text.split(":")[0].strip()
                    
                    # Get term definition - updated selector for current Investopedia structure
                    # First try to find the main content section
                    definition_section = None
                    
                    # Try different selectors that might contain the definition
                    for selector in [
                        'div[data-component="ArticleBody"]',
                        'div.article-body_content',
                        'div[data-journey-hook="client-content"]',
                        'section.article-body',
                        'div.content-body'
                    ]:
                        definition_section = soup.select_one(selector)
                        if definition_section:
                            break
                    
                    if not definition_section:
                        # Fallback: look for paragraphs after the first h2
                        h2_tags = soup.find_all('h2')
                        if h2_tags and len(h2_tags) > 0:
                            definition_paragraphs = []
                            current = h2_tags[0].find_next_sibling()
                            while current and current.name != 'h2':
                                if current.name == 'p':
                                    definition_paragraphs.append(current.get_text().strip())
                                current = current.find_next_sibling()
                            
                            if definition_paragraphs:
                                definition_text = " ".join(definition_paragraphs)
                            else:
                                print(f"No definition found for {url}")
                                return None
                        else:
                            print(f"No definition structure found for {url}")
                            return None
                    else:
                        # Extract text from the definition section
                        # Remove any nested elements that aren't part of the definition
                        for tag in definition_section.select('.compensation-link, .tooltip, .mntl-sc-block-adslot'):
                            if tag:
                                tag.decompose()
                                
                        definition_text = definition_section.get_text().strip()
                    
                    # Limit definition length if it's too long
                    if len(definition_text) > 5000:
                        definition_text = definition_text[:5000] + "..."
                    
                    print(f"Successfully parsed term: {title_text}")
                    return FinancialTerm(
                        term=title_text,
                        definition=definition_text,
                        url=url
                    )
                else:
                    print(f"Failed to fetch term {url}: HTTP {response.status}")
                        
        except Exception as e:
            print(f"Error fetching term {url}: {e}")
            
        return None

    def get_existing_terms(self) -> set:
        """Get existing terms from database"""
        try:
            # Only select the term column to avoid issues with missing columns
            return {term.term for term in self.db.query(FinancialTerm.term).all()}
        except Exception as e:
            print(f"Error getting existing terms: {e}")
            # Fallback method for older database schemas
            try:
                # Try a more robust approach using SQL directly
                from sqlalchemy import text
                result = self.db.execute(text("SELECT term FROM financial_terms"))
                return {row[0] for row in result if row[0]}
            except Exception as e2:
                print(f"Second error getting terms: {e2}")
                return set()

    async def update_terms_database(self) -> int:
        """Update financial terms database"""
        print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] Starting financial terms update...")
        
        # Get existing terms
        existing_terms = self.get_existing_terms()
        print(f"Found {len(existing_terms)} existing terms in database")
        
        # Fetch all term links
        term_links = await self.fetch_term_links()
        if not term_links:
            print("No term links found. Aborting update.")
            return 0
            
        print(f"Found {len(term_links)} total term links")
        
        # Increase batch size to collect more terms
        # but still keep it reasonable to avoid overwhelming the site
        batch_size = 50
        sample_links = random.sample(term_links, min(batch_size, len(term_links)))
        print(f"Processing a batch of {len(sample_links)} random terms")
        
        # Fetch definitions for new terms
        new_terms = []
        async with aiohttp.ClientSession(headers=self.headers) as session:
            for url in sample_links:
                try:
                    term = await self.fetch_term_definition(session, url)
                    if term and term.term not in existing_terms:
                        new_terms.append(term)
                        print(f"Added new term: {term.term}")
                    elif term:
                        print(f"Term already exists: {term.term}")
                    # Add a delay between requests
                    await asyncio.sleep(random.uniform(1, 2))
                except Exception as e:
                    print(f"Error processing term {url}: {e}")
        
        # Add new terms to database
        added_count = 0
        for term in new_terms:
            try:
                self.db.add(term)
                added_count += 1
            except Exception as e:
                print(f"Error adding term to database: {e}")
        
        # Commit if there are new terms
        if new_terms:
            try:
                self.db.commit()
                print(f"Successfully committed {added_count} new terms to database")
            except Exception as e:
                print(f"Error committing to database: {e}")
                self.db.rollback()
                added_count = 0
            
        print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] Added {added_count} new financial terms to database")
        return added_count
    
    def hourly_update_job(self):
        """Run the update_terms_database function in the event loop"""
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            result = loop.run_until_complete(self.update_terms_database())
            print(f"Scheduled job completed. Added {result} new terms.")
        except Exception as e:
            print(f"Error in scheduled job: {e}")
        finally:
            loop.close()
    
    def start_hourly_scheduling(self):
        """Start hourly scheduling of data scraping"""
        if self.is_scheduled:
            print("Hourly scheduling is already running")
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
        print("Started hourly scheduling of financial terms updates")
    
    def stop_hourly_scheduling(self):
        """Stop the hourly scheduling"""
        if not self.is_scheduled:
            print("Hourly scheduling is not running")
            return
        
        self.is_scheduled = False
        if self.scheduler_thread:
            self.scheduler_thread.join(timeout=2)
            self.scheduler_thread = None
        print("Stopped hourly scheduling of financial terms updates")
