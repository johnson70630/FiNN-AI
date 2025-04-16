import aiohttp
from bs4 import BeautifulSoup
import asyncio
from sqlalchemy.orm import Session
from ..database import FinancialTerm

class FinancialKnowledgeService:
    def __init__(self, db: Session):
        self.db = db
        self.base_url = "https://www.investopedia.com"
        self.dictionary_url = f"{self.base_url}/financial-term-dictionary-4769738"
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
        }
        self.timeout = aiohttp.ClientTimeout(total=30)

    async def fetch_term_links(self) -> list:
        """Fetch all financial term links from Investopedia dictionary"""
        term_links = []
        
        try:
            async with aiohttp.ClientSession(headers=self.headers) as session:
                async with session.get(self.dictionary_url) as response:
                    if response.status == 200:
                        content = await response.text()
                        soup = BeautifulSoup(content, 'html.parser')
                        
                        # Find all term links in the dictionary
                        for link in soup.find_all('a', href=True):
                            href = link['href']
                            if '/terms/' in href and href.startswith('/'):
                                term_links.append(f"{self.base_url}{href}")
                    else:
                        print(f"Failed to fetch dictionary page: {response.status}")
                        
        except Exception as e:
            print(f"Error fetching term links: {e}")
            
        return term_links

    async def fetch_term_definition(self, session, url: str) -> dict:
        """Fetch definition for a single financial term"""
        try:
            async with session.get(url) as response:
                if response.status == 200:
                    content = await response.text()
                    soup = BeautifulSoup(content, 'html.parser')
                    
                    # Get term title
                    title = soup.find('h1', class_='article-heading')
                    if not title:
                        return None
                        
                    # Get term definition
                    definition = soup.find('div', class_='article-body')
                    if not definition:
                        return None
                        
                    return FinancialTerm(
                        term=title.get_text().strip(),
                        definition=definition.get_text().strip(),
                        url=url
                    )
                        
        except Exception as e:
            print(f"Error fetching term {url}: {e}")
            
        return None

    def get_existing_terms(self) -> set:
        """Get existing terms from database"""
        return {term.term for term in self.db.query(FinancialTerm).all()}

    async def update_terms_database(self) -> int:
        """Update financial terms database"""
        # Get existing terms
        existing_terms = self.get_existing_terms()
        
        # Fetch all term links
        term_links = await self.fetch_term_links()
        
        # Fetch definitions for new terms
        new_terms = []
        async with aiohttp.ClientSession(headers=self.headers) as session:
            tasks = []
            for url in term_links:
                task = asyncio.create_task(self.fetch_term_definition(session, url))
                tasks.append(task)
                
            results = await asyncio.gather(*tasks)
            for term in results:
                if term and term.term not in existing_terms:
                    new_terms.append(term)
        
        # Add new terms to database
        for term in new_terms:
            self.db.add(term)
            
        # Commit if there are new terms
        if new_terms:
            self.db.commit()
            
        return len(new_terms)
