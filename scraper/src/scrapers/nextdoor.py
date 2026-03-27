"""Nextdoor scraper implementation."""

from typing import List, Dict, Any, Optional
from datetime import datetime
import os
import time
import zipfile
import pyotp
import tempfile
from playwright.sync_api import sync_playwright
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException

from .base import BaseScraper
try:
    from ..models import NextdoorLead, ScrapedLead
    from ..utils.buyer_intent import BuyerIntentDetector
    from ..user_credential_manager import UserCredentialManager
    from ..utils.email_manager import EmailManager
except ImportError:
    from models import NextdoorLead, ScrapedLead
    from utils.buyer_intent import BuyerIntentDetector
    from user_credential_manager import UserCredentialManager
    from utils.email_manager import EmailManager


class NextdoorScraper(BaseScraper):
    """Scraper for Nextdoor service posts supporting both Playwright and Selenium."""
    
    def __init__(self, cookies: Optional[Dict[str, str]] = None, **kwargs):
        super().__init__("nextdoor", **kwargs)
        self.cookies = cookies or {}
        self.user_email = os.getenv("NEXTDOOR_EMAIL")
        
        # Load cookie file if path provided
        if isinstance(self.cookies, str) and os.path.exists(self.cookies):
            import json
            with open(self.cookies, 'r') as f:
                self.cookies = json.load(f)
        
        if self.cookies:
            self.logger.info("using_provided_cookies", source="argument_or_variable", count=len(self.cookies) if isinstance(self.cookies, list) else "dict")
        else:
            self.logger.warning("no_cookies_provided_scraper_will_likely_fail")
    
    def parse_post(self, post_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Parse a single post from the feed."""
        try:
            # Relaxed check: Search results might have different feedItemType
            post = post_data.get('post')
            if not post and post_data.get('feedItemType') == 'POST':
                 post = post_data # Sometimes the item IS the post
            
            if not post:
                return None
            
            # Skip sponsored posts
            if post.get('isSponsored') or post.get('sponsored') or post_data.get('feedItemType') == 'SPONSORED_POST':
                self.logger.info("skipping_sponsored_post", post_id=post.get('id'))
                return None
            author = post.get('author', {})
            neighborhood_data = author.get('originationNeighborhood', {})
            created_at = post.get('createdAt', {})
            
            posted_date = None
            if posted_timestamp := created_at.get('epochMillis'):
                posted_date = datetime.fromtimestamp(int(posted_timestamp) / 1000)
            
            images = [photo['url'] for photo in post.get('photos', []) if photo.get('url')]
            
            tagged_business = tagged_category = None
            if tagged_content := post.get('taggedContent', []):
                entity_page = tagged_content[0].get('entityPage', {})
                tagged_business = entity_page.get('name')
                if display_category := entity_page.get('categoryInfo', {}).get('displayCategory', {}):
                    tagged_category = display_category.get('styledName', {}).get('text')
            
            topics = [t.get('name', {}).get('singularName') for t in post.get('topics', []) if t.get('name', {}).get('singularName')]
            
            url = None
            if href := post.get('detailLink', {}).get('href', ''):
                url = f"https://nextdoor.com{href.split('?')[0]}"
            
            return {
                'post_id': post.get('legacyPostId') or post.get('id'),
                'url': url,
                'title': post.get('subject', ''),
                'body': post.get('body', ''),
                'author_name': author.get('displayName'),
                'author_url': f"https://nextdoor.com/profile/{author.get('id')}" if author.get('id') else None,
                'neighborhood': neighborhood_data.get('shortName'),
                'city': neighborhood_data.get('city'),
                'state': neighborhood_data.get('state'),
                'posted_date': posted_date,
                'comment_count': post.get('comments', {}).get('totalCommentCount', 0),
                'reaction_count': len(post.get('reactionSummaries', {}).get('summaries', [])),
                'images': images,
                'tagged_business': tagged_business,
                'tagged_category': tagged_category,
                'topics': topics,
            }
        except Exception as e:
            self.logger.warning("failed_to_parse_nextdoor_post", error=str(e))
            return None
    
    def parse_item(self, raw_data: Dict[str, Any], custom_keywords: Optional[str] = None, 
                   exclude_keywords: Optional[list] = None,
                   custom_indicators: Optional[list] = None) -> Optional[NextdoorLead]:
        """Parse raw data into a NextdoorLead model."""
        try:
            # Combine title and description for buyer intent analysis
            text = f"{raw_data.get('title', '')} {raw_data.get('description', '') or raw_data.get('body', '')}"
            
            # Use centralized buyer intent detector
            is_service_request = BuyerIntentDetector.is_buyer_request(
                text=text,
                require_url=True,
                url=raw_data.get('url'),
                custom_keywords=custom_keywords,
                exclude_keywords=exclude_keywords,
                custom_indicators=custom_indicators
            )
            
            # Log detection reason for debugging (Info level for search tests)
            if not is_service_request:
                reason = BuyerIntentDetector.get_detection_reason(text, raw_data.get('url'))
                self.logger.info("filtered_non_buyer_post", reason=reason, title=raw_data.get('title'))
            
            return NextdoorLead(
                source_url=raw_data.get('url', ''),
                source_id=raw_data.get('post_id'),
                post_id=raw_data.get('post_id'),
                title=raw_data.get('title'),
                description=raw_data.get('description') or raw_data.get('body'),
                author_name=raw_data.get('author_name'),
                author_url=raw_data.get('author_url'),
                neighborhood=raw_data.get('neighborhood'),
                city=raw_data.get('city'),
                state=raw_data.get('state'),
                location=f"{raw_data.get('city')}, {raw_data.get('state')}" if raw_data.get('city') else None,
                posted_date=raw_data.get('posted_date'),
                comment_count=raw_data.get('comment_count', 0),
                reaction_count=raw_data.get('reaction_count', 0),
                images=raw_data.get('images', []),
                tagged_business=raw_data.get('tagged_business'),
                tagged_business_category=raw_data.get('tagged_category'),
                topics=raw_data.get('topics', []),
                is_service_request=is_service_request,
            )
        except Exception as e:
            self.logger.warning("failed_to_create_nextdoor_lead", error=str(e))
            return None

    def login_selenium(self, email: str, password: str, **kwargs) -> List[Dict[str, Any]]:
        """Log in to Nextdoor using Selenium and return cookies (Proxies disabled)."""
        headless = kwargs.get('headless', True)
        
        chrome_options = Options()
        if headless:
            chrome_options.add_argument("--headless=new")
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--disable-dev-shm-usage")
        chrome_options.add_argument("--window-size=1280,800")
        chrome_options.add_argument("--disable-blink-features=AutomationControlled")
        chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
        chrome_options.add_experimental_option('useAutomationExtension', False)
        
        if chrome_bin := os.getenv("CHROME_BIN"):
            chrome_options.binary_location = chrome_bin
            
        service = Service(executable_path="/usr/bin/chromedriver")
        driver = webdriver.Chrome(service=service, options=chrome_options)
        
        try:
            self.logger.info("navigating_to_nextdoor_login_selenium_no_proxy")
            driver.get("https://nextdoor.com/login/")
            time.sleep(8)
            
            try:
                email_field = WebDriverWait(driver, 10).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, 'input[name="email"], input#id_email'))
                )
                email_field.send_keys(email)
                
                password_field = driver.find_element(By.CSS_SELECTOR, 'input[name="password"], input#id_password')
                password_field.send_keys(password)
                password_field.send_keys(Keys.ENTER)
                
                self.logger.info("submitted_credentials_waiting")
                time.sleep(8)
                
                # Check for 2FA
                body_text = driver.find_element(By.TAG_NAME, 'body').text.lower()
                if any(x in body_text for x in ["login code", "enter code", "verification code", "verify your identity"]):
                    self.logger.info("2fa_detected")
                    two_fa_secret = kwargs.get('two_fa_secret')
                    code = None
                    
                    if two_fa_secret:
                        code = pyotp.TOTP(two_fa_secret.replace(" ", "")).now()
                    else:
                        app_pass = os.getenv("NEXTDOOR_APP_PASSWORD")
                        code = EmailManager.get_nextdoor_otp(email, app_pass) if app_pass else None
                    
                    if code:
                        self.logger.info("entering_2fa_code")
                        inputs = driver.find_elements(By.CSS_SELECTOR, 'input:not([type="hidden"])')
                        visible = [i for i in inputs if i.is_displayed()]
                        if len(visible) >= 6:
                            for idx, digit in enumerate(code):
                                visible[idx].send_keys(digit)
                        else:
                            visible[0].send_keys(code)
                            visible[0].send_keys(Keys.ENTER)
                        time.sleep(8)

                # Capture cookies
                WebDriverWait(driver, 20).until(lambda d: "login" not in d.current_url.lower())
                return driver.get_cookies()
                
            except TimeoutException:
                screenshot_path = os.path.join(tempfile.gettempdir(), f"nextdoor_timeout_{int(time.time())}.png")
                driver.save_screenshot(screenshot_path)
                self.logger.error("login_fields_not_found_timeout", screenshot=screenshot_path, url=driver.current_url)
                return []
            except Exception as e:
                self.logger.error("inner_login_error", error=str(e), url=driver.current_url)
                return []
                
        except Exception as e:
            self.logger.error("selenium_login_error", error=str(e))
            return []
        finally:
            driver.quit()

    def scrape(self, target: str = None, **kwargs) -> List[ScrapedLead]:
        """Main scraping method using Playwright (Proxies disabled)."""
        if not self.cookies:
            self.logger.error("nextdoor_cookies_required")
            raise ValueError("Nextdoor cookies not configured.")
        
        # Normalize URL
        if target:
            original_target = target
            target = target.replace('—', '--').replace('–', '--')
            import re
            city_match = re.search(r'nextdoor\.com/city/([a-z-]+)-([a-z]{2})/?$', target)
            if city_match and '--' not in target:
                target = target.replace(f"{city_match.group(1)}-{city_match.group(2)}", f"{city_match.group(1)}--{city_match.group(2)}")
            if target != original_target:
                self.logger.info("normalized_nextdoor_url", original=original_target, normalized=target)

        max_pages = kwargs.get('max_pages', 5)
        collected_posts = {}
        
        with sync_playwright() as p:


            launch_args = {"headless": True}
            if chrome_bin := os.getenv("CHROME_BIN"):
                launch_args.update({"executable_path": chrome_bin, "args": ["--no-sandbox", "--disable-dev-shm-usage"]})
            
            browser = p.chromium.launch(**launch_args)
            
            context_args = {
                'viewport': {'width': 1280, 'height': 800},
                'user_agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                'ignore_https_errors': True
            }

            context = browser.new_context(**context_args)
            
            # Add cookies
            cookie_list = []
            if isinstance(self.cookies, list):
                for c in self.cookies:
                    curr = {'name': c.get('name'), 'value': c.get('value'),
                           'domain': c.get('domain', '.nextdoor.com'), 'path': c.get('path', '/')}
                    if 'expiry' in c: curr['expires'] = c['expiry']
                    elif 'expirationDate' in c: curr['expires'] = c['expirationDate']
                    elif 'expires' in c: curr['expires'] = c['expires']
                    if 'secure' in c: curr['secure'] = c['secure']
                    if 'httpOnly' in c: curr['httpOnly'] = c['httpOnly']
                    if 'sameSite' in c: curr['sameSite'] = c['sameSite']
                    cookie_list.append(curr)
            else:
                cookie_list = [{'name': k, 'value': v, 'domain': '.nextdoor.com', 'path': '/'} 
                              for k, v in self.cookies.items()]
            
            context.add_cookies(cookie_list)
            page = context.new_page()
            
            def _find_feed_items(data):
                """Recursively locate a feedItems list anywhere in the JSON tree."""
                if isinstance(data, dict):
                    if 'feedItems' in data and isinstance(data['feedItems'], list):
                        return data['feedItems']
                    for v in data.values():
                        result = _find_feed_items(v)
                        if result is not None:
                            return result
                elif isinstance(data, list):
                    for item in data:
                        result = _find_feed_items(item)
                        if result is not None:
                            return result
                return None
            
            def scrape_from_dom(page):
                """Fallback: extract posts directly from HTML if JSON interception fails."""
                try:
                    # Selectors based on the Search Page HTML structure
                    selectors = [
                        'a[data-app="2"][href*="/p/"]', # Specific Post links in search
                        'a[data-app="2"][href*="/page/"]', # Business page links
                        '[data-testid="styled-text-wrapper"]' 
                    ]
                    
                    found_any = False
                    for selector in selectors:
                        try:
                            elements = page.locator(selector).all()
                            for el in elements:
                                try:
                                    # For text wrappers, we want to look at their parent link card
                                    target_el = el
                                    if selector == '[data-testid="styled-text-wrapper"]':
                                        # Try to find the parent link card
                                        try: target_el = el.locator('xpath=./ancestor::a[@data-app="2"]').first
                                        except: continue
                                    
                                    text = target_el.inner_text().strip()
                                    if not text or len(text) < 40: continue
                                    
                                    href = target_el.get_attribute("href") or ""
                                    post_url = href if "http" in href else f"https://nextdoor.com{href}"
                                    
                                    # Check for "Sponsored" text in the card
                                    if "sponsored" in text.lower() or "promoted" in text.lower():
                                        self.logger.info("skipping_sponsored_dom_result", url=post_url)
                                        continue
                                    
                                    import hashlib
                                    post_id = f"search_{hashlib.md5(text[:100].encode()).hexdigest()}"
                                    
                                    if post_id not in collected_posts:
                                        self.logger.info("search_result_found", url=post_url)
                                        # Split text to find author (usually first line)
                                        lines = text.split("\n")
                                        author = lines[0] if lines else "Nextdoor User"
                                        
                                        collected_posts[post_id] = {
                                            'post_id': post_id,
                                            'title': text[:100].replace("\n", " "),
                                            'body': text,
                                            'url': post_url,
                                            'description': text,
                                            'author_name': author
                                        }
                                        found_any = True
                                except: continue
                        except: continue
                    return found_any
                except Exception as e:
                    self.logger.error("dom_parse_error", error=str(e))
                    return False
                except Exception as e:
                    self.logger.error("dom_parse_error", error=str(e))
                    return False

            def handle_response(response):
                try:
                    if response.status != 200:
                        return
                    ct = response.headers.get('content-type', '')
                    if 'json' not in ct:
                        return
                    self.logger.info("intercepted_json_endpoint", url=response.url)
                    data = response.json()
                    feed_items = _find_feed_items(data) or []
                    if feed_items:
                        self.logger.info("intercepted_feed_items", count=len(feed_items), url=response.url)
                        
                    for item in feed_items:
                        parsed = self.parse_post(item)
                        if parsed and parsed.get('post_id'):
                            collected_posts[parsed['post_id']] = parsed
                        else:
                            # Log if it was found but failed parsing/validation
                            post_id = item.get('id') if isinstance(item, dict) else 'unknown'
                            self.logger.debug("post_rejected", post_id=post_id)
                except Exception:
                    pass
            
            page.on("response", handle_response)
            
            try:
                self.logger.info("navigating_to_url", target=target or "news_feed")
                url = target if target else "https://nextdoor.com/news_feed/"
                page.goto(url, timeout=90000)
                try:
                    # WAIT for network to be completely quiet
                    page.wait_for_load_state("networkidle", timeout=60000)
                except:
                    pass
                page.wait_for_timeout(5000)

                # Initial DOM extraction
                scrape_from_dom(page)

                if "login" in page.url or "signup" in page.url:
                    self.logger.error("session_invalid_redirected")
                    raise ValueError("Nextdoor session invalid.")
                
                previous_count = 0
                for i in range(max_pages):
                    page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                    page.wait_for_timeout(4000)
                    
                    # Call DOM extract during each scroll
                    scrape_from_dom(page)
                    
                    if "login" in page.url or "signup" in page.url: break
                    if len(collected_posts) == previous_count: 
                        break # Stop if no new posts found via JSON or DOM
                    previous_count = len(collected_posts)
                
                self.logger.info("scrolling_complete", gathered=len(collected_posts))
            except Exception as e:
                self.logger.error("playwright_execution_failed", error=str(e))
            finally:
                browser.close()
        
        return [lead for post_data in collected_posts.values() 
                if (lead := self.parse_item(post_data, 
                                            custom_keywords=kwargs.get('keywords'),
                                            exclude_keywords=kwargs.get('exclude_keywords'),
                                            custom_indicators=kwargs.get('custom_indicators')))]
