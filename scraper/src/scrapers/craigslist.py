"""Craigslist scraper implementation."""

from typing import List, Dict, Any, Optional
import time
from bs4 import BeautifulSoup as bs

from .base import BaseScraper
try:
    from ..models import CraigslistLead, ScrapedLead
    from ..utils.buyer_intent import BuyerIntentDetector
except ImportError:
    from models import CraigslistLead, ScrapedLead
    from utils.buyer_intent import BuyerIntentDetector


class CraigslistScraper(BaseScraper):
    """Scraper for Craigslist service listings."""
    
    def __init__(self, **kwargs):
        super().__init__("craigslist", db_manager=kwargs.pop('db_manager', None))
        self.headers = {
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.9',
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        }

    def parse_search_item(self, soup_element) -> Dict[str, Any]:
        """Parse a single Craigslist result-node HTML block."""
        link = soup_element.select_one("a")
        if link:
            title_elem = link.select_one(".title") or link.select_one("div.title")
            location_elem = link.select_one(".location") or link.select_one("div.location")
            price_elem = link.select_one(".price") or link.select_one("div.price")
            return {
                "title": title_elem.get_text(strip=True) if title_elem else soup_element.get("title"),
                "url": link.get("href"),
                "location": location_elem.get_text(strip=True) if location_elem else None,
                "price": price_elem.get_text(strip=True) if price_elem else None,
                "date_short": (ds := soup_element.select_one(".meta > span") or soup_element.select_one(".result-date")) and ds.get_text(strip=True),
                "date_full": (ds := soup_element.select_one(".meta > span") or soup_element.select_one(".result-date")) and ds.get("title"),
                "image_url": (img := soup_element.select_one("img")) and img.get("src"),
                "image_alt": (img := soup_element.select_one("img")) and img.get("alt"),
            }
        
        title_link = soup_element.select_one("a.posting-title") or soup_element.select_one("a.cl-search-anchor")
        location_elem = soup_element.select_one(".result-info > div") or soup_element.select_one(".result-hood")
        date_span = soup_element.select_one(".meta > span") or soup_element.select_one(".result-date")
        img = soup_element.select_one("img")
        
        return {
            "title": title_link.get_text(strip=True) if title_link else None,
            "url": title_link.get("href") if title_link else None,
            "location": location_elem.get_text(strip=True) if location_elem else None,
            "price": None,
            "date_short": date_span.get_text(strip=True) if date_span else None,
            "date_full": date_span.get("title") if date_span else None,
            "image_url": img.get("src") if img else None,
            "image_alt": img.get("alt") if img else None,
        }
    
    def get_total_count(self, soup: bs) -> int:
        """Extract total number of results from the page."""
        try:
            if count_elem := soup.select_one(".totalcount"):
                return int(count_elem.get_text(strip=True))
            return 0
        except Exception:
            return 0

    def scrape_search_page(self, search_url: str, offset: int = 0, category: Optional[str] = None) -> tuple:
        """Scrape a single search results page at a specific offset."""
        page_url = f"{search_url}{'&' if '?' in search_url else '?'}s={offset}"
        self.logger.info("scraping_page", url=page_url, offset=offset)
        
        try:
            response = self.make_request(page_url, headers=self.headers, use_proxy=True)
            soup = bs(response.text, "html.parser")
            items = soup.select("li.cl-static-search-result, [class*='cl-search-result'] > div.result-node, .result-row") or soup.select(".cl-search-result")
            
            parsed_items = []
            for item in items:
                if (parsed := self.parse_search_item(item)) and parsed.get('title') and parsed.get('url'):
                    if category:
                        parsed['category'] = category
                    parsed_items.append(parsed)
            
            self.logger.debug("page_scraped", url=page_url, items_found=len(parsed_items))
            return parsed_items, soup
        except Exception as e:
            self.logger.error("scraping_page_failed", url=page_url, error=str(e))
            raise

    def parse_item(self, raw_data: Dict[str, Any]) -> Optional[CraigslistLead]:
        """Parse raw scraped data into a CraigslistLead model."""
        try:
            posting_id = None
            if url := raw_data.get('url'):
                if parts := url.split('/'):
                    if (clean_part := parts[-1].replace('.html', '')).isdigit():
                        posting_id = clean_part
            
            # Combine title and description for buyer intent analysis
            text = f"{raw_data.get('title', '')} {raw_data.get('description', '')}"
            
            # Use centralized buyer intent detector
            is_buyer_request = BuyerIntentDetector.is_buyer_request(
                text=text,
                require_url=True,
                url=raw_data.get('url')
            )
            
            # Log detection reason for debugging
            if not is_buyer_request:
                reason = BuyerIntentDetector.get_detection_reason(text, raw_data.get('url'))
                self.logger.debug("filtered_non_buyer_post", reason=reason, title=raw_data.get('title'))
            
            return CraigslistLead(
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
                is_buyer_request=is_buyer_request,
            )
        except Exception as e:
            self.logger.warning("failed_to_parse_item", error=str(e))
            return None

    def get_subcategories(self, location_url: str) -> List[Dict[str, str]]:
        """Get subcategories using requests."""
        try:
            response = self.make_request(location_url, headers=self.headers, use_proxy=True)
            soup = bs(response.text, "html.parser")
            if not (services_section := soup.select_one("#bbb")):
                return []
            return [{"name": link.get_text(strip=True), "url": location_url.rstrip("/") + link.get("href")}
                   for link in services_section.select("li > a")]
        except Exception as e:
            self.logger.error("failed_to_fetch_subcategories", error=str(e))
            return []

    def scrape(self, target: str, **kwargs) -> List[ScrapedLead]:
        """Main scraping method."""
        category = kwargs.get('category')
        subcategories = kwargs.get('subcategories', [])
        max_pages = kwargs.get('max_pages', 5)
        all_leads = []
        
        try:
            if not subcategories and target.endswith('.craigslist.org/'):
                subcategories = [s['url'] for s in self.get_subcategories(target)]
            if not subcategories:
                subcategories = [target]
            
            for sub_url in subcategories:
                self.logger.info("scraping_subcategory", url=sub_url)
                offset = 0
                
                for page in range(max_pages):
                    try:
                        raw_items, soup = self.scrape_search_page(sub_url, offset, category)
                        if not raw_items:
                            break
                        
                        for raw in raw_items:
                            if lead := self.parse_item(raw):
                                all_leads.append(lead)
                        
                        if offset + len(raw_items) >= self.get_total_count(soup) or len(raw_items) == 0:
                            break
                        
                        offset += len(raw_items)
                        time.sleep(2)
                    except Exception as e:
                        self.logger.error("page_loop_failed", error=str(e))
                        break
            
            print(all_leads)
            return all_leads
        except Exception as e:
            self.logger.error("scrape_failed", error=str(e))
            raise
