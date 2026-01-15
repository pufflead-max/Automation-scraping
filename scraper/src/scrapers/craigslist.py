"""
Craigslist scraper implementation.
Extracts service leads from Craigslist listings using Selenium and BeautifulSoup.
"""

from typing import List, Dict, Any, Optional
from datetime import datetime
import time
import pandas as pd
from bs4 import BeautifulSoup as bs
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.common.exceptions import TimeoutException, WebDriverException
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.chrome.service import Service

from .base import BaseScraper
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
    Uses Selenium for dynamic content loading and BeautifulSoup for parsing.
    """
    
    def __init__(self, headless: bool = True, **kwargs):
        """
        Initialize Craigslist scraper.
        
        Args:
            headless: Whether to run browser in headless mode
            **kwargs: Additional arguments passed to BaseScraper
        """
        super().__init__("craigslist", **kwargs)
        self.headless = headless
        self.driver: Optional[webdriver.Chrome] = None
        
        # Craigslist-specific headers and cookies
        self.cookies = {
            'cl_b': '4|0af409a49109a817ee844d8d0a8376a5471336e7|1763514361nP-Dc',
            'ajs_anonymous_id': '%223cd2c65a-0b09-4c92-ac2c-7a36cf853048%22',
            'cl_def_hp': 'boston',
        }
        
        self.headers = {
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.9',
            'Cache-Control': 'max-age=0',
            'Connection': 'keep-alive',
            'Sec-Fetch-Dest': 'document',
            'Sec-Fetch-Mode': 'navigate',
            'Sec-Fetch-Site': 'cross-site',
            'Sec-Fetch-User': '?1',
            'Upgrade-Insecure-Requests': '1',
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/142.0.0.0 Safari/537.36',
        }
    
    def get_driver(self) -> webdriver.Chrome:
        """
        Create and configure Chrome/Chromium WebDriver.
        
        Returns:
            webdriver.Chrome: Configured Chrome driver
        """
        if self.driver is not None:
            return self.driver
        
        self.logger.info("initializing_chrome_driver", headless=self.headless)
        
        options = Options()
        
        # Headless mode
        if self.headless:
            options.add_argument("--headless=new")
        
        # Performance optimizations
        options.add_argument("--disable-gpu")
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--disable-extensions")
        options.add_argument("--disable-infobars")
        options.add_argument("--start-maximized")
        
        # Disable images to save bandwidth
        prefs = {
            "profile.managed_default_content_settings.images": 2
        }
        options.add_experimental_option("prefs", prefs)
        
        try:
            # Check if running in Docker (Chromium) or local (Chrome)
            import os
            chrome_bin = os.getenv('CHROME_BIN')
            chromedriver_path = os.getenv('CHROMEDRIVER_PATH')
            
            if chrome_bin:
                # Running in Docker with Chromium
                options.binary_location = chrome_bin
                self.logger.info("using_chromium", path=chrome_bin)
                
                if chromedriver_path:
                    from selenium.webdriver.chrome.service import Service
                    service = Service(executable_path=chromedriver_path)
                    driver = webdriver.Chrome(service=service, options=options)
                else:
                    driver = webdriver.Chrome(options=options)
            else:
                # Local development - use webdriver-manager
                from webdriver_manager.chrome import ChromeDriverManager
                from selenium.webdriver.chrome.service import Service
                service = Service(ChromeDriverManager().install())
                driver = webdriver.Chrome(service=service, options=options)
            
            driver.set_page_load_timeout(self.config.get('timeout', 30))
            
            self.driver = driver
            self.logger.info("chrome_driver_initialized")
            
            return driver
            
        except Exception as e:
            self.logger.error("failed_to_initialize_driver", error=str(e))
            raise
    
    def close_driver(self) -> None:
        """Close the Chrome driver if it's open."""
        if self.driver:
            try:
                self.driver.quit()
                self.driver = None
                self.logger.info("chrome_driver_closed")
            except Exception as e:
                self.logger.warning("error_closing_driver", error=str(e))
    
    def get_subcategories(self, location_url: str) -> List[Dict[str, str]]:
        """
        Get all service subcategories from a Craigslist location.
        
        Args:
            location_url: Base URL for the location (e.g., https://boston.craigslist.org/)
        
        Returns:
            List[Dict]: List of subcategories with names and links
        """
        self.logger.info("fetching_subcategories", location_url=location_url)
        
        try:
            response = self.make_request(
                location_url,
                headers=self.headers,
                cookies=self.cookies,
                use_proxy=True
            )
            
            soup = bs(response.text, "lxml")
            
            # Find the services section (#bbb)
            services_section = soup.select_one("#bbb")
            if not services_section:
                self.logger.warning("services_section_not_found", location_url=location_url)
                return []
            
            # Extract subcategory links
            subcategories = []
            for link in services_section.select("li > a"):
                subcategories.append({
                    "name": link.get_text(strip=True),
                    "url": location_url.rstrip("/") + link.get("href")
                })
            
            self.logger.info(
                "subcategories_found",
                location_url=location_url,
                count=len(subcategories)
            )
            
            return subcategories
            
        except Exception as e:
            self.logger.error(
                "failed_to_fetch_subcategories",
                location_url=location_url,
                error=str(e)
            )
            return []
    
    def parse_search_item(self, soup_element) -> Dict[str, Any]:
        """
        Parse a single Craigslist result-node HTML block.
        
        Args:
            soup_element: BeautifulSoup element for a result-node
        
        Returns:
            Dict: Parsed item data
        """
        # Root node
        root = soup_element.select_one("div.result-node") or soup_element
        
        # Title and posting URL
        title_link = root.select_one("a.posting-title") or root.select_one("a.cl-search-anchor")
        if title_link:
            label = title_link.select_one(".label")
            title = (label.get_text(strip=True) if label else title_link.get_text(strip=True)) or None
            url = title_link.get("href")
        else:
            title = None
            url = None
        
        # Location
        loc_div = root.select_one(".result-info > div")
        location = loc_div.get_text(strip=True) if loc_div else None
        
        # Date
        date_span = root.select_one(".meta > span")
        date_short = date_span.get_text(strip=True) if date_span else None
        date_full = date_span.get("title") if date_span else None
        
        # Image
        img = root.select_one("a.result-thumb img")
        img_url = img.get("src") if img else None
        img_alt = img.get("alt") if img else None
        
        return {
            "title": title,
            "url": url,
            "location": location,
            "date_short": date_short,
            "date_full": date_full,
            "image_url": img_url,
            "image_alt": img_alt,
        }
    
    def get_items_count(self, driver: webdriver.Chrome) -> int:
        """
        Get the total number of items from the page.
        
        Args:
            driver: Selenium WebDriver instance
        
        Returns:
            int: Total number of items
        """
        try:
            count_elements = driver.find_elements(By.CSS_SELECTOR, "div.visible-counts")
            count_texts = [e.text for e in count_elements if e.text.strip() != ""]
            
            if not count_texts:
                return 0
            
            # Extract the maximum number from the count string
            numbers = [int(n) for n in count_texts[0].strip().split() if n.isnumeric()]
            return max(numbers) if numbers else 0
            
        except Exception as e:
            self.logger.warning("failed_to_get_items_count", error=str(e))
            return 0
    
    def scrape_search_page(
        self,
        search_url: str,
        category: Optional[str] = None,
        max_scrolls: int = 100
    ) -> List[Dict[str, Any]]:
        """
        Scrape a single search results page with infinite scroll.
        
        Args:
            search_url: URL of the search page
            category: Category name for metadata
            max_scrolls: Maximum number of scroll attempts
        
        Returns:
            List[Dict]: List of scraped items
        """
        driver = self.get_driver()
        
        self.logger.info("scraping_search_page", url=search_url, category=category)
        
        try:
            driver.get(search_url)
            time.sleep(3)
            
            total_collected_items = []
            
            for scroll_iteration in range(max_scrolls):
                # Scroll down
                driver.execute_script("window.scrollBy(0, arguments[0]);", scroll_iteration * 300)
                time.sleep(3)
                
                # Get current page source and parse
                soup = bs(driver.page_source, "html.parser")
                items = soup.select("div[class*='cl-search-result'] > div.result-node")
                
                # Parse all items
                for item in items:
                    parsed_item = self.parse_search_item(item)
                    if category:
                        parsed_item['category'] = category
                    total_collected_items.append(parsed_item)
                
                # Remove duplicates based on URL
                df_collected = pd.DataFrame(total_collected_items).drop_duplicates("url")
                total_count = self.get_items_count(driver)
                
                self.logger.debug(
                    "scroll_progress",
                    iteration=scroll_iteration,
                    total_count=total_count,
                    collected=len(df_collected),
                    current_batch=len(items)
                )
                
                # Check if we've collected all items
                if len(df_collected) >= total_count > 0:
                    self.logger.info(
                        "all_items_collected",
                        total=len(df_collected),
                        target=total_count
                    )
                    break
            
            # Convert back to list of dicts
            return df_collected.to_dict('records')
            
        except Exception as e:
            self.logger.error("scraping_search_page_failed", url=search_url, error=str(e))
            raise
    
    def parse_item(self, raw_data: Dict[str, Any]) -> Optional[CraigslistLead]:
        """
        Parse raw scraped data into a CraigslistLead model.
        
        Args:
            raw_data: Raw data dictionary from scraping
        
        Returns:
            Optional[CraigslistLead]: Validated lead or None if parsing fails
        """
        try:
            # Extract posting ID from URL if available
            posting_id = None
            if raw_data.get('url'):
                # URL format: /gbs/aos/d/title/1234567890.html
                parts = raw_data['url'].split('/')
                if parts:
                    posting_id = parts[-1].replace('.html', '')
            
            # Create lead model
            lead = CraigslistLead(
                source_url=raw_data.get('url', ''),
                source_id=posting_id,
                posting_id=posting_id,
                title=raw_data.get('title'),
                description=raw_data.get('description'),  # Would need detail page scraping
                location=raw_data.get('location'),
                category=raw_data.get('category'),
                date_short=raw_data.get('date_short'),
                date_full=raw_data.get('date_full'),
                image_thumbnail=raw_data.get('image_url'),
                images=[raw_data.get('image_url')] if raw_data.get('image_url') else [],
            )
            
            return lead
            
        except Exception as e:
            self.logger.warning(
                "failed_to_parse_item",
                error=str(e),
                raw_data=raw_data
            )
            return None
    
    def scrape(self, target: str, **kwargs) -> List[ScrapedLead]:
        """
        Main scraping method for Craigslist.
        
        Args:
            target: Target URL or location to scrape
            **kwargs: Additional parameters:
                - category: Specific category to scrape
                - subcategories: List of subcategory URLs to scrape
                - max_scrolls: Maximum scroll iterations per page
        
        Returns:
            List[ScrapedLead]: List of scraped and validated leads
        """
        category = kwargs.get('category')
        subcategories = kwargs.get('subcategories', [])
        max_scrolls = kwargs.get('max_scrolls', 100)
        
        all_leads = []
        
        try:
            # If target is a location URL, get subcategories
            if not subcategories and target.endswith('.craigslist.org/'):
                subcategories = self.get_subcategories(target)
                subcategories = [sub['url'] for sub in subcategories]
            
            # If target is a direct search URL
            if not subcategories:
                subcategories = [target]
            
            # Scrape each subcategory
            for sub_url in subcategories:
                self.logger.info("scraping_subcategory", url=sub_url)
                
                try:
                    # Scrape search page
                    raw_items = self.scrape_search_page(
                        sub_url,
                        category=category,
                        max_scrolls=max_scrolls
                    )
                    
                    # Parse and validate items
                    for raw_item in raw_items:
                        lead = self.parse_item(raw_item)
                        if lead:
                            all_leads.append(lead)
                    
                    self.logger.info(
                        "subcategory_scraped",
                        url=sub_url,
                        items=len(raw_items)
                    )
                    
                    # Be polite - wait between subcategories
                    time.sleep(2)
                    
                except Exception as e:
                    self.logger.error(
                        "subcategory_scraping_failed",
                        url=sub_url,
                        error=str(e)
                    )
                    continue
            
            return all_leads
            
        finally:
            # Always close the driver
            self.close_driver()
    
    def __del__(self):
        """Cleanup when scraper is destroyed."""
        self.close_driver()


if __name__ == "__main__":
    # Test the scraper
    print("Testing Craigslist scraper...")
    
    scraper = CraigslistScraper(headless=False)
    
    # Test scraping a single category
    test_url = "https://boston.craigslist.org/search/aos"
    
    try:
        leads = scraper.run(
            target=test_url,
            category="automotive",
            save_to_db=False
        )
        
        print(f"\n✓ Scraped {len(leads)} leads")
        if leads:
            print(f"\nSample lead:")
            print(f"  Title: {leads[0].title}")
            print(f"  URL: {leads[0].source_url}")
            print(f"  Location: {leads[0].location}")
        
    except Exception as e:
        print(f"\n✗ Scraping failed: {e}")
    
    finally:
        scraper.close_driver()
