"""Facebook scraper implementation using Selenium for robust data extraction."""

import os
import time
import json
import uuid
import re
from datetime import datetime
from typing import List, Dict, Any, Optional

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.chrome.service import Service
from selenium.common.exceptions import TimeoutException, NoSuchElementException

try:
    from .base import BaseScraper
    from ..models import FacebookLead, ScrapedLead
    from ..utils.buyer_intent import BuyerIntentDetector
    from ..user_credential_manager import UserCredentialManager
    from ..utils.email_manager import EmailManager
except (ImportError, ValueError):
    try:
        from scrapers.base import BaseScraper
        from models import FacebookLead, ScrapedLead
        from utils.buyer_intent import BuyerIntentDetector
        from user_credential_manager import UserCredentialManager
        from utils.email_manager import EmailManager
    except ImportError:
        import sys
        sys.path.append(os.path.join(os.path.dirname(__file__), ".."))
        from scrapers.base import BaseScraper
        from models import FacebookLead, ScrapedLead
        from utils.buyer_intent import BuyerIntentDetector
        from user_credential_manager import UserCredentialManager
        from utils.email_manager import EmailManager

class FacebookScraper(BaseScraper):
    """Scraper for Facebook groups and pages using Selenium."""
    
    def __init__(self, **kwargs):
        super().__init__("facebook", db_manager=kwargs.pop('db_manager', None))
        self.driver = None
        self.cookies_path = os.path.join(os.path.dirname(__file__), "..", "cookies", "facebook_cookies.json")
        self.headless = kwargs.get('headless', True)
        self._init_driver()

    def _init_driver(self):
        """Initialize the Selenium WebDriver."""
        chrome_options = Options()
        if self.headless:
            chrome_options.add_argument("--headless=new")
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--disable-dev-shm-usage")
        chrome_options.add_argument("--disable-notifications")
        chrome_options.add_argument("--window-size=1280,800")
        
        # Detect environment (Docker vs Local)
        chrome_bin = os.getenv("CHROME_BIN")
        if chrome_bin:
            chrome_options.binary_location = chrome_bin
            service = Service(executable_path=os.getenv("CHROMEDRIVER_BIN", "/usr/bin/chromedriver"))
        else:
            service = Service(ChromeDriverManager().install())
            
        self.driver = webdriver.Chrome(service=service, options=chrome_options)
        self.driver.set_page_load_timeout(30)

    def login(self, cookies: Optional[List[Dict]] = None):
        """Log in to Facebook using cookies or credentials."""
        try:
            self.driver.get("https://www.facebook.com")
            
            if cookies:
                for cookie in cookies:
                    self.driver.add_cookie(cookie)
                self.driver.refresh()
                time.sleep(2)
            
            # Simple check if logged in
            try:
                self.driver.find_element(By.CSS_SELECTOR, "[aria-label='Facebook']")
                self.logger.info("facebook_login_success")
                return True
            except NoSuchElementException:
                self.logger.warning("facebook_login_required")
                return False
        except Exception as e:
            self.logger.error("facebook_login_failed", error=str(e))
            return False

    def scrape(self, target: str, **kwargs) -> List[FacebookLead]:
        """Main scraping method for Facebook."""
        limit = kwargs.get('limit', 15)
        max_pages = kwargs.get('max_pages', 5)
        
        try:
            if not self.login(kwargs.get('cookies')):
                self.logger.error("aborting_scrape_no_login")
                return []
                
            self.driver.get(target)
            time.sleep(3)
            
            raw_items = self._scroll_and_collect(limit)
            leads = self._process_items(raw_items)
            return leads
            
        except Exception as e:
            self.logger.error("facebook_scrape_failed", error=str(e))
            return []
        finally:
            if self.driver:
                self.driver.quit()

    def _scroll_and_collect(self, limit: int) -> List[Dict[str, Any]]:
        """Scroll and collect post elements."""
        items = []
        last_height = self.driver.execute_script("return document.body.scrollHeight")
        
        while len(items) < limit:
            # Find post containers (Facebook's class names change, but structures remain)
            posts = self.driver.find_elements(By.CSS_SELECTOR, "div[role='feed'] > div, div[role='main'] div[data-ad-preview='message']")
            
            for post in posts:
                try:
                    text_elem = post.find_element(By.CSS_SELECTOR, "div[data-ad-comet-preview='message'], .userContent")
                    text = text_elem.text
                    
                    if any(item['text'] == text for item in items):
                        continue
                        
                    items.append({
                        "text": text,
                        "url": self.driver.current_url,
                        "timestamp": datetime.utcnow()
                    })
                    
                    if len(items) >= limit:
                        break
                except:
                    continue
            
            # Scroll down
            self.driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
            time.sleep(2)
            new_height = self.driver.execute_script("return document.body.scrollHeight")
            if new_height == last_height:
                break
            last_height = new_height
            
        return items

    def _process_items(self, raw_items: List[Dict[str, Any]]) -> List[FacebookLead]:
        """Convert raw items into FacebookLead objects (NO AI check here)."""
        leads = []
        for item in raw_items:
            lead = FacebookLead(
                source="facebook",
                source_url=item['url'],
                description=item['text'],
                title=item['text'][:100], # Fallback title
                posted_date=item['timestamp'],
                is_buyer_request=False, # AI Check happens in BaseScraper.run
                is_hiring=False,
                intent_score=0
            )
            leads.append(lead)
        return leads

    def parse_item(self, raw: Any) -> Optional[ScrapedLead]:
        """Minimal implementation of abstract method."""
        return None
