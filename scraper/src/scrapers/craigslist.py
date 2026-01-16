"""
Craigslist scraper implementation.
Extracts service leads from Craigslist listings using requests and BeautifulSoup.
"""

from typing import List, Dict, Any, Optional
import time
import math
from bs4 import BeautifulSoup as bs

from .base import BaseScraper
try:
    from ..models import CraigslistLead, ScrapedLead
    from ..logger import ScraperLogger
except ImportError:
    from models import CraigslistLead, ScrapedLead
    from logger import ScraperLogger


class CraigslistScraper(BaseScraper):
    """
    Scraper for Craigslist service listings.
    Uses requests for HTTP retrieval and BeautifulSoup for parsing.
    """
    
    def __init__(self, **kwargs):
        """
        Initialize Craigslist scraper.
        
        Args:
            **kwargs: Additional arguments passed to BaseScraper
        """
        db_manager = kwargs.pop('db_manager', None)
        # Remove headless if present as we don't use it
        kwargs.pop('headless', None)
        super().__init__("craigslist", db_manager=db_manager)
        
        # Craigslist-specific headers
        self.headers = {
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.9',
            'Cache-Control': 'max-age=0',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1',
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        }

    def parse_search_item(self, soup_element) -> Dict[str, Any]:
        """
        Parse a single Craigslist result-node HTML block.
        
        Args:
            soup_element: BeautifulSoup element for a result-node
        
        Returns:
            Dict: Parsed item data
        """
        root = soup_element
        
        # New structure: li.cl-static-search-result > a > div.title + div.details
        link = root.select_one("a")
        if link:
            url = link.get("href")
            title_elem = link.select_one(".title") or link.select_one("div.title")
            title = title_elem.get_text(strip=True) if title_elem else root.get("title")
            
            # Location from details
            location_elem = link.select_one(".location") or link.select_one("div.location")
            location = location_elem.get_text(strip=True) if location_elem else None
            
            # Price
            price_elem = link.select_one(".price") or link.select_one("div.price")
            price = price_elem.get_text(strip=True) if price_elem else None
        else:
            # Fallback for old structure
            title_link = root.select_one("a.posting-title") or root.select_one("a.cl-search-anchor")
            if title_link:
                title = title_link.get_text(strip=True)
                url = title_link.get("href")
            else:
                title = None
                url = None
            
            location_elem = root.select_one(".result-info > div") or root.select_one(".result-hood")
            location = location_elem.get_text(strip=True) if location_elem else None
            price = None
        
        # Date (may not be present in all listings)
        date_span = root.select_one(".meta > span") or root.select_one(".result-date")
        date_short = date_span.get_text(strip=True) if date_span else None
        date_full = date_span.get("title") if date_span else None
        
        # Image
        img = root.select_one("img")
        img_url = img.get("src") if img else None
        img_alt = img.get("alt") if img else None
        
        return {
            "title": title,
            "url": url,
            "location": location,
            "price": price,
            "date_short": date_short,
            "date_full": date_full,
            "image_url": img_url,
            "image_alt": img_alt,
        }
    
    def get_total_count(self, soup: bs) -> int:
        """
        Extract total number of results from the page.
        """
        try:
            # Look for <span class="totalcount">3000</span>
            count_elem = soup.select_one(".totalcount")
            if count_elem:
                return int(count_elem.get_text(strip=True))
            
            # Fallback: look for "1 - 120 of 360" text
            range_elem = soup.select_one(".rangeTo")
            if range_elem:
                 # Usually somewhere nearby
                 parent = range_elem.parent
                 if parent:
                     text = parent.get_text()
                     # simple extraction logic needed if class not present
                     pass
            
            return 0
        except Exception:
            return 0

    def scrape_search_page(
        self,
        search_url: str,
        offset: int = 0,
        category: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        Scrape a single search results page at a specific offset.
        """
        # Construct URL with offset
        if '?' in search_url:
            page_url = f"{search_url}&s={offset}"
        else:
            page_url = f"{search_url}?s={offset}"
            
        self.logger.info("scraping_page", url=page_url, offset=offset)
        
        try:
            response = self.make_request(
                page_url,
                headers=self.headers,
                use_proxy=True
            )
            
            soup = bs(response.text, "html.parser")
            
            # Find all result nodes
            # Craigslist structure changes sometimes, support multiple selectors
            items = soup.select("li.cl-static-search-result, [class*='cl-search-result'] > div.result-node, .result-row")
            
            # If standard selectors fail, try broader ones
            if not items:
                items = soup.select(".cl-search-result")

            parsed_items = []
            for item in items:
                parsed = self.parse_search_item(item)
                if parsed.get('title') and parsed.get('url'):
                    if category:
                        parsed['category'] = category
                    parsed_items.append(parsed)
            
            self.logger.debug(
                "page_scraped",
                url=page_url,
                items_found=len(parsed_items)
            )
            
            return parsed_items, soup
            
        except Exception as e:
            self.logger.error("scraping_page_failed", url=page_url, error=str(e))
            raise

    def parse_item(self, raw_data: Dict[str, Any]) -> Optional[CraigslistLead]:
        """
        Parse raw scraped data into a CraigslistLead model.
        """
        try:
            # Extract posting ID from URL if available
            posting_id = None
            if raw_data.get('url'):
                # URL format: /gbs/aos/d/title/1234567890.html
                parts = raw_data['url'].split('/')
                if parts:
                    clean_part = parts[-1].replace('.html', '')
                    if clean_part.isdigit():
                        posting_id = clean_part
            
            # Create lead model
            lead = CraigslistLead(
                source_url=raw_data.get('url', ''),
                source_id=posting_id,
                posting_id=posting_id,
                title=raw_data.get('title'),
                description=raw_data.get('description'),
                location=raw_data.get('location'),
                category=raw_data.get('category'),
                date_short=raw_data.get('date_short'),
                date_full=raw_data.get('date_full'),
                image_thumbnail=raw_data.get('image_url'),
                images=[raw_data.get('image_url')] if raw_data.get('image_url') else [],
            )
            
            return lead
            
        except Exception as e:
            self.logger.warning("failed_to_parse_item", error=str(e))
            return None

    def get_subcategories(self, location_url: str) -> List[Dict[str, str]]:
        """Get subcategories using requests."""
        try:
            response = self.make_request(location_url, headers=self.headers, use_proxy=True)
            soup = bs(response.text, "html.parser")
            
            services_section = soup.select_one("#bbb")
            if not services_section:
                return []
            
            subcategories = []
            for link in services_section.select("li > a"):
                subcategories.append({
                    "name": link.get_text(strip=True),
                    "url": location_url.rstrip("/") + link.get("href")
                })
            return subcategories
        except Exception as e:
            self.logger.error("failed_to_fetch_subcategories", error=str(e))
            return []

    def scrape(self, target: str, **kwargs) -> List[ScrapedLead]:
        """
        Main scraping method.
        parameter 'max_pages' can be used to limit depth.
        """
        category = kwargs.get('category')
        subcategories = kwargs.get('subcategories', [])
        max_pages = kwargs.get('max_pages', 5)
        
        all_leads = []
        
        try:
            # Setup subcategories
            if not subcategories and target.endswith('.craigslist.org/'):
                subs = self.get_subcategories(target)
                subcategories = [s['url'] for s in subs]
            
            if not subcategories:
                subcategories = [target]
            
            for sub_url in subcategories:
                self.logger.info("scraping_subcategory", url=sub_url)
                
                offset = 0
                items_per_page = 120
                
                for page in range(max_pages):
                    try:
                        raw_items, soup = self.scrape_search_page(sub_url, offset, category)
                        
                        if not raw_items:
                            break
                            
                        for raw in raw_items:
                            lead = self.parse_item(raw)
                            if lead:
                                all_leads.append(lead)
                        
                        # Pagination check
                        total_count = self.get_total_count(soup)
                        curr_count = offset + len(raw_items)
                        
                        if curr_count >= total_count or len(raw_items) == 0:
                            break
                        
                        offset += len(raw_items)
                        time.sleep(2) # Be polite
                        
                    except Exception as e:
                        self.logger.error("page_loop_failed", error=str(e))
                        break
            print(all_leads)
            return all_leads
            
        except Exception as e:
            self.logger.error("scrape_failed", error=str(e))
            raise
