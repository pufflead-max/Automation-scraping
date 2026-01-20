"""Facebook scraper implementation using Selenium - FIXED VERSION."""

from typing import List, Dict, Any, Optional
from datetime import datetime, timedelta
import os
import re
import json
import time
import traceback
import random
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.chrome.service import Service

from .base import BaseScraper
try:
    from ..models import FacebookLead, ScrapedLead
except ImportError:
    from models import FacebookLead, ScrapedLead


class FacebookScraper(BaseScraper):
    """Scraper for Facebook page posts using Selenium."""
    
    def __init__(self, cookies: Optional[Dict[str, str]] = None, **kwargs):
        super().__init__("facebook", db_manager=kwargs.get('db_manager'))
        self.cookies = cookies or {}
        self.headless_default = kwargs.get('headless', True)
        
        # Load cookie file if path provided
        if isinstance(self.cookies, str) and os.path.exists(self.cookies):
            with open(self.cookies, 'r') as f:
                self.cookies = json.load(f)
        
        # If no cookies passed, try to load from default location
        if not self.cookies:
            cookie_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), 'cookies', 'facebook_cookies.json')
            if os.path.exists(cookie_path):
                 with open(cookie_path, 'r') as f:
                    self.cookies = json.load(f)
        
        self.seen_urls = set()
        self.seen_texts = set()
        self.driver = None

    def _init_driver(self, headless: bool = True):
        """Initialize the Selenium driver with stealth settings."""
        self.logger.info("initializing_selenium_driver", headless=headless)
        
        options = Options()
        if headless:
            options.add_argument('--headless=new')
        
        # Enhanced stealth arguments
        options.add_argument('--disable-blink-features=AutomationControlled')
        options.add_argument('--disable-dev-shm-usage')
        options.add_argument('--no-sandbox')
        options.add_argument('--disable-setuid-sandbox')
        options.add_argument('--disable-web-security')
        options.add_argument('--disable-features=IsolateOrigins,site-per-process')
        options.add_argument('--disable-popup-blocking')
        options.add_argument('--disable-notifications')
        options.add_argument('--window-size=1920,1080')
        options.add_argument('user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36')
        
        options.add_experimental_option("excludeSwitches", ["enable-automation"])
        options.add_experimental_option('useAutomationExtension', False)
        
        prefs = {
            "profile.default_content_setting_values.notifications": 2,
            "credentials_enable_service": False,
            "profile.password_manager_enabled": False,
            "profile.default_content_setting_values.geolocation": 2,
            "profile.default_content_setting_values.media_stream": 2,
            "autofill.profile_enabled": False,
            "profile.default_content_setting_values.popups": 2,
            "intl.accept_languages": "en-US,en",
            "profile.managed_default_content_settings.images": 1,
        }
        options.add_experimental_option("prefs", prefs)

        # Use system binaries if they exist
        chromium_path = "/usr/bin/chromium"
        chromedriver_path = "/usr/bin/chromedriver"
        
        if os.path.exists(chromium_path) and os.path.exists(chromedriver_path):
            self.logger.info("using_system_chromium_binaries", chromium=chromium_path, driver=chromedriver_path)
            options.binary_location = chromium_path
            service = Service(chromedriver_path)
        else:
            self.logger.info("system_binaries_not_found_falling_back_to_webdriver_manager")
            service = Service(ChromeDriverManager().install())
            
        self.driver = webdriver.Chrome(service=service, options=options)
        
        # Inject anti-detection scripts
        self._inject_stealth_scripts()
        
        try:
            self.driver.maximize_window()
        except:
            pass
            
        self.logger.info("driver_initialized")

    def _inject_stealth_scripts(self):
        """Inject JavaScript to mask automation (enhanced version)"""
        try:
            stealth_js = """
            // Overwrite the `navigator.webdriver` property
            Object.defineProperty(navigator, 'webdriver', {
                get: () => false,
            });
            
            // Overwrite the `plugins` property to use a custom getter
            Object.defineProperty(navigator, 'plugins', {
                get: () => [1, 2, 3, 4, 5],
            });
            
            // Overwrite the `languages` property to use a custom getter
            Object.defineProperty(navigator, 'languages', {
                get: () => ['en-US', 'en'],
            });
            
            // Pass the Chrome Test
            window.chrome = {
                runtime: {},
            };
            
            // Pass the Permissions Test
            const originalQuery = window.navigator.permissions.query;
            window.navigator.permissions.query = (parameters) => (
                parameters.name === 'notifications' ?
                    Promise.resolve({ state: Notification.permission }) :
                    originalQuery(parameters)
            );
            """
            # Execute on the first page load
            self.driver.execute_cdp_cmd('Page.addScriptToEvaluateOnNewDocument', {
                'source': stealth_js
            })
        except Exception as e:
            self.logger.warning("stealth_injection_failed", error=str(e))

    def _load_cookies(self):
        """Load cookies into the driver."""
        if not self.cookies:
            return False
            
        try:
            self.driver.get('https://www.facebook.com')
            time.sleep(2)
            
            cookie_list = []
            if isinstance(self.cookies, list):
                cookie_list = self.cookies
            else:
                cookie_list = [{'name': k, 'value': v, 'domain': '.facebook.com'} for k, v in self.cookies.items()]

            for cookie in cookie_list:
                try:
                    c = {
                        'name': cookie.get('name'),
                        'value': cookie.get('value'),
                        'domain': cookie.get('domain', '.facebook.com'),
                        'path': cookie.get('path', '/')
                    }
                    if 'secure' in cookie: 
                        c['secure'] = cookie['secure']
                    self.driver.add_cookie(c)
                except:
                    continue
            
            self.driver.refresh()
            time.sleep(3)
            return True
        except Exception as e:
            self.logger.error("failed_to_load_cookies", error=str(e))
            return False

    def _save_cookies(self):
        """Save current cookies back to the file."""
        try:
            cookies = self.driver.get_cookies()
            cookie_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), 'cookies', 'facebook_cookies.json')
            os.makedirs(os.path.dirname(cookie_path), exist_ok=True)
            with open(cookie_path, 'w', encoding='utf-8') as f:
                json.dump(cookies, f, ensure_ascii=False, indent=2)
            self.logger.info("cookies_saved", path=cookie_path)
        except Exception as e:
            self.logger.warning("failed_to_save_cookies", error=str(e))

    def _close_popups(self):
        """Close common Facebook popups."""
        try:
            close_selectors = [
                'div[aria-label="Close"]',
                'button[aria-label="Close"]',
                '[role="button"][aria-label="Close"]',
                '[aria-label="Dismiss"]',
                'div[aria-label="Not Now"]',
                'button[aria-label="Not Now"]',
            ]
            
            for selector in close_selectors:
                try:
                    elements = self.driver.find_elements(By.CSS_SELECTOR, selector)
                    for el in elements:
                        if el.is_displayed():
                            el.click()
                            time.sleep(0.3)
                except:
                    pass
            
            try:
                ActionChains(self.driver).send_keys(Keys.ESCAPE).perform()
            except:
                pass
        except:
            pass

    def _expand_see_more_buttons(self):
        """Click 'See more' to reveal full post text (enhanced version)."""
        try:
            # Use JavaScript to click all see more buttons (more reliable)
            self.driver.execute_script("""
                const buttons = [
                    ...document.querySelectorAll('div[role="button"]'),
                    ...document.querySelectorAll('span'),
                    ...document.querySelectorAll('a')
                ].filter(el => 
                    (el.textContent.includes('See more') || el.textContent.includes('see more')) && 
                    el.offsetParent !== null
                );
                buttons.slice(0, 30).forEach(btn => {
                    try {
                        btn.click();
                    } catch(e) {}
                });
            """)
            time.sleep(0.5)
        except Exception as e:
            self.logger.debug("expand_see_more_failed", error=str(e))

    def _extract_post_content_only(self, article):
        """Extract post text using multiple strategies with fallbacks."""
        try:
            # Strategy 1: Look for data-ad-rendering-role="story_message"
            try:
                story_message_container = article.find_element(By.CSS_SELECTOR, 'div[data-ad-rendering-role="story_message"]')
                message_divs = story_message_container.find_elements(By.CSS_SELECTOR, 'div[dir="auto"]')
                parts = [d.text.strip() for d in message_divs if d.text.strip()]
                if parts:
                    return "\n".join(parts)
            except:
                pass

            # Strategy 2: Look for data-ad-preview="message"
            try:
                message_container = article.find_element(By.CSS_SELECTOR, 'div[data-ad-preview="message"]')
                text = message_container.text.strip()
                if text and len(text) > 10:
                    return text
            except:
                pass

            # Strategy 3: Look for divs with specific classes that contain post content
            try:
                selectors = [
                    'div[data-ad-comet-preview="message"]',
                    'div.xdj266r.x11i5rnm.xat24cr.x1mh8g0r',  # Common post text class
                    'div[dir="auto"][style*="text-align"]',
                ]
                
                for selector in selectors:
                    try:
                        elements = article.find_elements(By.CSS_SELECTOR, selector)
                        for elem in elements:
                            text = elem.text.strip()
                            if text and len(text) > 20:
                                # Filter out UI elements
                                if not any(ui in text for ui in ['Like', 'Comment', 'Share', 'Send', '·', 'Follow']):
                                    return text
                    except:
                        continue
            except:
                pass

            # Strategy 4: Broader search - look for any div[dir="auto"] with substantial text
            try:
                content_divs = article.find_elements(By.CSS_SELECTOR, 'div[dir="auto"]')
                candidates = []
                
                for div in content_divs[:10]:  # Check first 10 to avoid comments
                    text = div.text.strip()
                    if text and len(text) > 30:
                        # Filter out UI noise
                        if not any(ui in text[:50] for ui in ['Like', 'Comment', 'Share', 'Send', 'Sponsored']):
                            candidates.append((len(text), text))
                
                if candidates:
                    candidates.sort(reverse=True)
                    return candidates[0][1]
            except:
                pass

            # Strategy 5: Last resort - get article text and try to extract meaningful content
            try:
                full_text = article.text
                if full_text:
                    lines = [l.strip() for l in full_text.split('\n') if l.strip()]
                    content_lines = []
                    for line in lines:
                        if len(line) > 20 and not any(ui in line for ui in ['Like', 'Comment', 'Share', 'Send', 'Sponsored', '·', 'Follow']):
                            content_lines.append(line)
                    
                    if content_lines:
                        return '\n'.join(content_lines[:5])
            except:
                pass

            return ""
        except:
            return ""

    def _extract_exact_post_date(self, article):
        """Extract exact post date using heuristics and handle relative time."""
        try:
            candidate_dates = []
            links = article.find_elements(By.CSS_SELECTOR, 'a[role="link"], a')
            
            for link in links:
                try:
                    href = link.get_attribute('href') or ""
                    aria = link.get_attribute('aria-label') or ""
                    
                    if aria or any(x in href for x in ['/posts/', '/videos/', '/reel/', '/photo', 'fbid=']):
                        text = self.driver.execute_script("return arguments[0].innerText;", link).strip()
                        if text:
                            candidate_dates.append(text)
                        elif aria:
                            candidate_dates.append(aria)
                    elif "Sponsored" in (link.text or ""):
                        candidate_dates.append("Sponsored")
                except: 
                    continue

            # Sponsored check
            if any("Sponsored" in d for d in candidate_dates):
                return "Sponsored"

            months = ['January', 'February', 'March', 'April', 'May', 'June', 
                      'July', 'August', 'September', 'October', 'November', 'December']

            for d in candidate_dates:
                clean_d = d.strip()
                if len(clean_d) > 50: 
                    continue
                
                # Relative time patterns
                if re.match(r'^\d+[mh]$', clean_d): 
                    return datetime.now().strftime("%d %B %Y")
                
                match_d = re.match(r'^(\d+)d$', clean_d)
                if match_d:
                    past = datetime.now() - timedelta(days=int(match_d.group(1)))
                    return past.strftime("%d %B %Y")

                match_w = re.match(r'^(\d+)w$', clean_d)
                if match_w:
                    past = datetime.now() - timedelta(weeks=int(match_w.group(1)))
                    return past.strftime("%d %B %Y")
                
                match_y = re.match(r'^(\d+)y$', clean_d)
                if match_y:
                    past = datetime.now() - timedelta(days=int(match_y.group(1))*365)
                    return past.strftime("%d %B %Y")

                # Absolute dates
                if any(m in clean_d for m in months):
                    if not re.search(r'\d{4}', clean_d):
                        clean_d = f"{clean_d} {datetime.now().year}"
                    return clean_d

            # Regex search in article text
            try:
                date_pattern = re.compile(r'\b(\d{1,2})\s+(January|February|March|April|May|June|July|August|September|October|November|December)\b', re.IGNORECASE)
                header_text = article.text[:300]
                match = date_pattern.search(header_text)
                if match:
                    found_date = match.group(0)
                    has_year = re.search(r'\d{4}', header_text[match.end():match.end()+10])
                    if has_year:
                        found_date = f"{found_date} {has_year.group(0)}"
                    else:
                        found_date = f"{found_date} {datetime.now().year}"
                    return found_date
            except:
                pass

            return "Date not found"
        except:
            return "Date not found"

    def parse_item(self, raw_data: Dict[str, Any]) -> Optional[FacebookLead]:
        """Parse raw data into a FacebookLead model."""
        try:
            post_date_str = raw_data.get('post_date')
            posted_date = None
            if post_date_str and post_date_str != "Date not found":
                date_formats = ["%d %B %Y", "%Y-%m-%d"]
                for fmt in date_formats:
                    try:
                        posted_date = datetime.strptime(post_date_str, fmt)
                        break
                    except: 
                        continue

            return FacebookLead(
                source_url=raw_data.get('link') or f"https://facebook.com/post/{raw_data.get('id')}",
                source_id=raw_data.get('id'),
                title=raw_data.get('title'),
                description=raw_data.get('text'),
                posted_date=posted_date,
                images=raw_data.get('images', []),
                videos=raw_data.get('videos', []),
                image_count=raw_data.get('image_count', 0),
                video_count=raw_data.get('video_count', 0),
                has_media=raw_data.get('has_media', False),
                word_count=raw_data.get('word_count', 0),
                extra_data={'raw_date': post_date_str, 'scraped_at': raw_data.get('scraped_at')}
            )
        except Exception as e:
            self.logger.warning("failed_to_create_facebook_lead", error=str(e))
            return None

    def _scroll_smoothly(self, scroll_count=0):
        """Perform aggressive, human-like scrolling with multiple fallbacks."""
        try:
            # 0. Initial tiny wiggle to trigger scroll listeners
            self.driver.execute_script("window.scrollBy(0, -10);")
            time.sleep(0.1)
            self.driver.execute_script("window.scrollBy(0, 10);")
            time.sleep(0.2)

            # 1. Random small scrolls (mimic mouse wheel)
            for _ in range(5):
                amount = random.randint(300, 600)
                self.driver.execute_script(f"window.scrollBy(0, {amount});")
                time.sleep(0.4)
            
            # 2. Use Page Down keys (very effective for Facebook)
            actions = ActionChains(self.driver)
            for _ in range(2):
                actions.send_keys(Keys.PAGE_DOWN)
                time.sleep(0.3)
            actions.perform()
            
            # 3. Occasional 'End' key to trigger lazy loading
            if scroll_count % 3 == 0:
                self.logger.info("sending_end_key_for_lazy_load")
                ActionChains(self.driver).send_keys(Keys.END).perform()
                time.sleep(1.5)
            
            # 4. Final Jump
            self.driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
            time.sleep(2)
            
        except Exception as e:
            self.logger.debug("scroll_failed", error=str(e))

    def login(self, email, password):
        """Login to Facebook with credentials and save cookies."""
        self.logger.info("logging_in_to_facebook")
        
        try:
            self.driver.get('https://www.facebook.com')
            time.sleep(3)
            
            # Wait for and fill email
            email_field = WebDriverWait(self.driver, 10).until(
                EC.presence_of_element_located((By.NAME, 'email'))
            )
            email_field.clear()
            email_field.send_keys(email)
            time.sleep(0.5)
            
            # Fill password
            password_field = self.driver.find_element(By.NAME, 'pass')
            password_field.clear()
            password_field.send_keys(password)
            time.sleep(0.5)
            
            # Click login button
            login_button = self.driver.find_element(By.NAME, 'login')
            login_button.click()
            
            self.logger.info("waiting_for_login_completion")
            time.sleep(8)

            self._close_popups()
            time.sleep(2)
            
            # Check if logged in
            if not self._is_logged_in():
                self.logger.warning("login_validation_failed_manual_intervention_might_be_needed")
                # If running locally (not in Docker), we can ask for input
                if not os.getenv('AIRFLOW_HOME'):
                    try:
                        input("👉 Please solve any CAPTCHA/Security step in the browser, then press ENTER here...")
                    except EOFError:
                        pass
            
            self._save_cookies()
            self.logger.info("login_successful_cookies_saved")
            return True
            
        except Exception as e:
            self.logger.error("login_failed", error=str(e))
            return False

    def _is_logged_in(self):
        """Check if session is authenticated."""
        try:
            # Check current URL first
            current_url = self.driver.current_url.lower()
            if "login" in current_url or "checkpoint" in current_url:
                return False

            # Check for profile link or account menu
            indicators = [
                'div[aria-label*="Account"]',
                'div[aria-label*="Your profile"]',
                'a[href*="/me/"]',
                'svg[aria-label="Your profile"]'
            ]
            for inc in indicators:
                if self.driver.find_elements(By.CSS_SELECTOR, inc):
                    return True
            return False
        except:
            return False

    def scrape(self, target: str = None, **kwargs) -> List[ScrapedLead]:
        """Main scraping method using Selenium."""
        limit = kwargs.get('limit', 25)
        target_posts = limit if limit and limit > 0 else 999999
        headless = kwargs.get('headless', self.headless_default)
        extracted_leads = []
        
        email = kwargs.get('email') or os.getenv('FACEBOOK_EMAIL')
        password = kwargs.get('password') or os.getenv('FACEBOOK_PASSWORD')
        
        if target_posts == 999999:
            self.logger.info("starting_unlimited_scrape")
        else:
            self.logger.info("starting_limited_scrape", limit=target_posts)
        
        try:
            self._init_driver(headless=headless)
            
            # Try loading cookies first
            session_ok = self._load_cookies()
            
            # If cookies fail but we have credentials, try to login
            if not session_ok and email and password:
                session_ok = self.login(email, password)
            
            if not session_ok:
                self.logger.warning("continuing_without_authenticated_session")
            
            self.logger.info("navigating_to_target", url=target)
            self.driver.get(target)
            time.sleep(5)
            self._close_popups()
            
            last_height = self.driver.execute_script("return document.body.scrollHeight")
            scroll_count = 0
            no_change_count = 0
            consecutive_no_new_posts = 0
            
            while len(extracted_leads) < target_posts:
                self.logger.info("scroll_iteration", 
                               scroll=scroll_count, 
                               extracted=len(extracted_leads), 
                               target=target_posts,
                               no_change=no_change_count)
                
                # Perform scrolling
                self._scroll_smoothly(scroll_count=scroll_count)
                
                # Expand "See more" buttons
                self._expand_see_more_buttons()
                
                # Wait for content to load
                time.sleep(1.5)
                
                # Extract posts
                # Use more specific selector for actual posts
                articles = self.driver.find_elements(By.CSS_SELECTOR, 'div[role="article"]')
                self.logger.info("articles_found_in_dom", count=len(articles))
                
                posts_before = len(extracted_leads)
                
                for article in articles:
                    if len(extracted_leads) >= target_posts:
                        break
                        
                    try:
                        # Extract link first
                        link = None
                        selectors = [
                            'a[href*="/posts/"]', 
                            'a[href*="/photos/"]', 
                            'a[href*="/videos/"]', 
                            'a[href*="/reel/"]'
                        ]
                        
                        for sel in selectors:
                            try:
                                els = article.find_elements(By.CSS_SELECTOR, sel)
                                for e in els:
                                    href = e.get_attribute('href')
                                    if href and 'facebook.com' in href:
                                        link = href.split('?')[0]
                                        break
                                if link: 
                                    break
                            except: 
                                continue
                        
                        # Skip if we've seen this URL
                        if link and link in self.seen_urls: 
                            continue
                        
                        # Extract post text
                        post_text = self._extract_post_content_only(article)
                        text_hash = post_text[:150].strip()
                        
                        # Skip if no meaningful content
                        if not link and (not text_hash or len(text_hash) < 10): 
                            continue
                        
                        # Skip if we've seen this text
                        if not link and text_hash in self.seen_texts: 
                            continue
                        
                        # Mark as seen
                        if link: 
                            self.seen_urls.add(link)
                        if text_hash: 
                            self.seen_texts.add(text_hash)
                        
                        # Extract other data
                        title = post_text.split('\n')[0][:100] if post_text else "No Title"
                        post_date = self._extract_exact_post_date(article)
                        
                        # Extract images
                        images = []
                        imgs = article.find_elements(By.CSS_SELECTOR, 'img')
                        for im in imgs:
                            src = im.get_attribute('src')
                            if src and not any(x in src.lower() for x in ['emoji', 'static', 'px']):
                                images.append(src)
                        images = list(dict.fromkeys(images))
                        
                        # Create raw item
                        raw_item = {
                            'id': f'post_{len(self.seen_urls)}',
                            'title': title,
                            'text': post_text,
                            'post_date': post_date,
                            'link': link,
                            'images': images,
                            'image_count': len(images),
                            'video_count': 0,
                            'has_media': bool(images),
                            'word_count': len(post_text.split()) if post_text else 0,
                            'scraped_at': datetime.now().isoformat()
                        }
                        
                        if lead := self.parse_item(raw_item):
                            extracted_leads.append(lead)
                            self.logger.debug("post_extracted", 
                                            total=len(extracted_leads),
                                            text_preview=post_text[:50])
                            
                    except Exception as e:
                        self.logger.debug("failed_to_extract_article", error=str(e))
                        continue

                # Check if we got new posts
                posts_after = len(extracted_leads)
                new_posts_this_iteration = posts_after - posts_before
                
                if new_posts_this_iteration == 0:
                    consecutive_no_new_posts += 1
                    self.logger.info("no_new_posts_iteration", consecutive=consecutive_no_new_posts)
                else:
                    consecutive_no_new_posts = 0
                    self.logger.info("new_posts_found", count=new_posts_this_iteration)
                
                # If we haven't found new posts in 4 scrolls, we might be stuck or at end
                if consecutive_no_new_posts >= 4:
                    self.logger.warning("no_new_posts_for_multiple_scrolls_attempting_unstick")
                    
                    # Try aggressive unstick: scroll up a bit then HARD down
                    try:
                        self._close_popups() # Maybe a popup is blocking?
                        curr = self.driver.execute_script("return window.pageYOffset;")
                        self.driver.execute_script(f"window.scrollTo(0, {max(0, curr - 1000)});")
                        time.sleep(1)
                        self.driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
                        time.sleep(4)
                        
                        # Try hitting END key multiple times
                        actions = ActionChains(self.driver)
                        for _ in range(3):
                            actions.send_keys(Keys.END)
                            time.sleep(0.5)
                        actions.perform()
                        
                        consecutive_no_new_posts = 1 # Reset but keep pressure
                    except:
                        pass
                
                # Check if reached target
                if len(extracted_leads) >= target_posts:
                    self.logger.info("target_reached", extracted=len(extracted_leads))
                    break
                    
                # Check page height changes
                new_height = self.driver.execute_script("return document.body.scrollHeight")
                
                if new_height <= last_height:
                    no_change_count += 1
                    self.logger.info("no_height_change", count=no_change_count)
                    
                    # Be very patient before giving up
                    if no_change_count >= 12: 
                        self.logger.info("end_of_content_reached_confirmed")
                        break
                    
                    # Try to trigger more content loading every 3rd fail
                    if no_change_count % 3 == 0:
                        try:
                            self.logger.info("forcing_refresh_via_scroll_jump")
                            self.driver.execute_script("window.scrollBy(0, -500);")
                            time.sleep(1)
                            self.driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
                            time.sleep(3)
                        except:
                            pass
                else:
                    no_change_count = 0
                    last_height = new_height
                
                scroll_count += 1
                
                # Safety limit
                if scroll_count > 200:
                    self.logger.info("safety_scroll_limit_reached")
                    break
                
            self.logger.info("scraping_completed", total_posts=len(extracted_leads))
            self._save_cookies()
            
        except Exception as e:
            self.logger.error("scraping_failed", error=str(e))
            traceback.print_exc()
        finally:
            if self.driver:
                self.driver.quit()
                
        return extracted_leads


if __name__ == "__main__":
    # Standard setup to allow running this file directly for the "Hybrid" approach
    from dotenv import load_dotenv
    import sys
    
    # Add project root to path so imports work
    project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    if project_root not in sys.path:
        sys.path.append(project_root)
        
    load_dotenv()
    
    # Configure basic logging for standalone run
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    # Get target from env or default
    target_url = os.getenv('FACEBOOK_TARGET_URL', 'https://www.facebook.com/groups/712316496457199')
    print(f"\n🚀 Starting HYBRID Facebook Scraper")
    print(f"📍 Target: {target_url}\n")
    
    scraper = FacebookScraper()
    
    # In hybrid mode, we can run with headless=False to debug locally
    results = scraper.run(
        target=target_url, 
        limit=10, 
        headless=False,
        save_to_db=True
    )
    
    print(f"\n✅ Scraping session finished!")
    print(f"📊 Extracted {len(results)} posts.")
    if results:
        print(f"📝 Sample Title: {results[0].title[:50]}...")