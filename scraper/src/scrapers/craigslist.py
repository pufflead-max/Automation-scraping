"""Craigslist scraper implementation using Playwright for robust description extraction."""

from typing import List, Dict, Any, Optional
import os
import time
import re
from playwright.sync_api import sync_playwright

from .base import BaseScraper
try:
    from ..models import CraigslistLead, ScrapedLead
    from ..utils.buyer_intent import BuyerIntentDetector
except (ImportError, ValueError):
    try:
        from models import CraigslistLead, ScrapedLead
        from utils.buyer_intent import BuyerIntentDetector
    except ImportError:
        # Fallback for Airflow dynamic task mapping environment
        try:
            import sys
            import os
            sys.path.append(os.path.join(os.path.dirname(__file__), ".."))
            from models import CraigslistLead, ScrapedLead
            from utils.buyer_intent import BuyerIntentDetector
        except ImportError:
            # Last resort: just try to import from current level if they were moved
            from models import CraigslistLead, ScrapedLead
            from utils.buyer_intent import BuyerIntentDetector


class CraigslistScraper(BaseScraper):
    """Scraper for Craigslist service listings using Playwright."""
    
    def __init__(self, **kwargs):
        super().__init__("craigslist", db_manager=kwargs.pop('db_manager', None))
        self.headless = kwargs.get('headless', True)

    def parse_item(self, raw_data: Dict[str, Any], custom_keywords: Optional[list] = None, 
                   exclude_keywords: Optional[list] = None, 
                   custom_indicators: Optional[list] = None) -> Optional[CraigslistLead]:
        """Parse raw scraped data into a CraigslistLead model."""
        try:
            posting_id = None
            url = raw_data.get('url')
            
            if url:
                if parts := url.split('/'):
                    if (clean_part := parts[-1].replace('.html', '')).isdigit():
                        posting_id = clean_part
            
            description = raw_data.get('description')
            
            # Combine title and description for buyer intent analysis
            text = f"{raw_data.get('title', '')} {description or ''}"

            # Use centralized buyer intent detector
            is_buyer_request = BuyerIntentDetector.is_buyer_request(
                text=text,
                require_url=True,
                url=url,
                custom_keywords=custom_keywords,
                exclude_keywords=exclude_keywords,
                custom_indicators=custom_indicators
            )
            
            # Log detection reason for debugging
            if not is_buyer_request:
                reason = BuyerIntentDetector.get_detection_reason(text, url)
                self.logger.debug("filtered_non_buyer_post", reason=reason, title=raw_data.get('title'))
            
            return CraigslistLead(
                source_url=url or '',
                source_id=posting_id,
                posting_id=posting_id,
                title=raw_data.get('title'),
                description=description,
                location=raw_data.get('location'),
                category=raw_data.get('category'),
                posted_date=raw_data.get('posted_date'),
                images=raw_data.get('images', []),
                is_buyer_request=is_buyer_request,
            )
        except Exception as e:
            self.logger.warning("failed_to_parse_item", error=str(e))
            return None

    def scrape_detail_page(self, page, url: str) -> Dict[str, Any]:
        """Navigate to a detail page and extract full description and images."""
        try:
            self.logger.info("scraping_detail_page", url=url)
            page.goto(url, timeout=60000)
            page.wait_for_load_state("domcontentloaded")
            
            # Extract description
            description = ""
            if posting_body := page.query_selector("#postingbody"):
                # Get the text content, removing the "QR Code Link to This Post" part
                description = page.evaluate("(node) => node.innerText", posting_body)
                description = description.replace("QR Code Link to This Post", "").strip()
            
            # Extract date
            posted_date = None
            if time_tag := page.query_selector("time.date, time.timeago, .postinginfo time"):
                posted_date = time_tag.get_attribute("datetime")
            
            # Extract images
            images = []
            if image_elements := page.query_selector_all(".gallery img, .userbody img"):
                for img in image_elements:
                    if src := img.get_attribute("src"):
                        images.append(src)
            
            return {
                "description": description,
                "posted_date": posted_date,
                "images": images
            }
        except Exception as e:
            self.logger.warning("detail_page_scraping_failed", url=url, error=str(e))
            return {}

    def scrape(self, target: str, **kwargs) -> List[ScrapedLead]:
        """Main scraping method using Playwright."""
        max_pages = kwargs.get('max_pages', 3)
        query = kwargs.get('query')
        category = kwargs.get('category')
        all_leads = []
        
        with sync_playwright() as p:
            launch_args = {"headless": self.headless}
            if chrome_bin := os.getenv("CHROME_BIN"):
                launch_args.update({"executable_path": chrome_bin, "args": ["--no-sandbox", "--disable-dev-shm-usage"]})
            
            browser = p.chromium.launch(**launch_args)
            context = browser.new_context(
                viewport={'width': 1280, 'height': 800},
                user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36'
            )
            page = context.new_page()
            
            # Normalize target URL
            search_url = target
            if query:
                connector = '&' if '?' in search_url else '?'
                search_url = f"{search_url}{connector}query={query}"
            
            self.logger.info("starting_playwright_scrape", url=search_url)
            
            try:
                page.goto(search_url, timeout=90000)
                page.wait_for_load_state("networkidle")
                
                # Craigslist might still show the old layout or new one
                collected_items = []
                
                for p_idx in range(max_pages):
                    self.logger.info(f"scraping_search_results_page_{p_idx + 1}")
                    
                    # Wait for results to load
                    # Some environments/IPs may be served a "static" version of Craigslist
                    # which uses .cl-static-search-result
                    page.wait_for_selector(".cl-search-result, .result-row, .cl-static-search-result", timeout=10000)
                    
                    # Extract list items
                    # New layout uses .cl-search-result
                    # Old layout uses .result-row
                    # Static/Blocked layout uses .cl-static-search-result
                    items = page.query_selector_all(".cl-search-result, .result-row, .cl-static-search-result")
                    
                    for item in items:
                        try:
                            # Basic extraction from search page
                            # .cl-static-search-result usually has the link directly inside it
                            link_elem = item.query_selector("a.posting-title, a.cl-search-anchor, a")
                            if not link_elem:
                                continue
                                
                            url = link_elem.get_attribute("href")
                            if not url:
                                continue
                            
                            if not url.startswith("http"):
                                # Handle relative URLs
                                from urllib.parse import urljoin
                                url = urljoin(search_url, url)
                                
                            title = link_elem.inner_text().strip()
                            
                            location = ""
                            if loc_elem := item.query_selector(".location, .result-hood"):
                                location = loc_elem.inner_text().strip()
                                
                            collected_items.append({
                                "url": url,
                                "title": title,
                                "location": location,
                                "category": category
                            })
                        except Exception as e:
                            self.logger.debug("item_extraction_failed", error=str(e))
                            continue
                    
                    # Check for "next" page
                    if p_idx < max_pages - 1:
                        next_button = page.query_selector("button.cl-next-page, a.next")
                        if next_button and next_button.is_visible() and next_button.is_enabled():
                            next_button.click()
                            page.wait_for_load_state("networkidle")
                            time.sleep(2)
                        else:
                            self.logger.info("no_more_pages")
                            break
                
                self.logger.info(f"collected_{len(collected_items)}_items_now_fetching_details")
                
                # Now fetch details for each item
                for item_data in collected_items:
                    detail_data = self.scrape_detail_page(page, item_data["url"])
                    item_data.update(detail_data)
                    
                    if lead := self.parse_item(item_data, 
                                               custom_keywords=kwargs.get('keywords'),
                                               exclude_keywords=kwargs.get('exclude_keywords'),
                                               custom_indicators=kwargs.get('custom_indicators')):
                        all_leads.append(lead)
                        # Optional: limit items or handle rate limiting
                        time.sleep(1)
                        
            except Exception as e:
                self.logger.error("playwright_scrape_failed", error=str(e))
            finally:
                browser.close()
                
        return all_leads
