"""Facebook scraper implementation using Selenium - FIXED VERSION."""

from typing import List, Dict, Any, Optional
from datetime import datetime, timedelta
import os
import re
import json
import time
import traceback
import random
import logging
import zipfile
import tempfile
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.chrome.service import Service
from selenium.common.exceptions import TimeoutException, ElementNotInteractableException, NoSuchElementException, ElementClickInterceptedException


# Handle imports for both local and Airflow environments
import sys
import os

# Ensure the 'src' directory is in PYTHONPATH
src_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if src_dir not in sys.path:
    sys.path.append(src_dir)

try:
    # Try absolute imports (works in Airflow when src is in path)
    from scrapers.base import BaseScraper
    from models import FacebookLead, ScrapedLead
    from utils.buyer_intent import BuyerIntentDetector
    from user_credential_manager import UserCredentialManager
except ImportError:
    try:
        # Try relative imports (works when running as a package)
        from .base import BaseScraper
        from ..models import FacebookLead, ScrapedLead
        from ..utils.buyer_intent import BuyerIntentDetector
        from ..user_credential_manager import UserCredentialManager
    except (ImportError, ValueError):
        # Fallback for direct script execution
        from base import BaseScraper
        from models import FacebookLead, ScrapedLead
        from utils.buyer_intent import BuyerIntentDetector
        from user_credential_manager import UserCredentialManager


class FacebookScraper(BaseScraper):
    """Scraper for Facebook page posts using Selenium."""
    
    def __init__(self, cookies: Optional[Dict[str, str]] = None, **kwargs):
        super().__init__("facebook", db_manager=kwargs.get('db_manager'))
        self.cookies = cookies or {}
        self.headless_default = kwargs.get('headless', True)
        self.use_proxy = kwargs.get('use_proxy', False)
        
        # Load cookie file if path provided
        if isinstance(self.cookies, str) and os.path.exists(self.cookies):
            with open(self.cookies, 'r') as f:
                self.cookies = json.load(f)
        
        if self.cookies:
            self.logger.info("using_provided_cookies", source="argument_or_variable", count=len(self.cookies) if isinstance(self.cookies, list) else "dict")
        else:
            self.logger.warning("no_cookies_provided_scraper_will_likely_fail")
        
        self.seen_urls = set()
        self.seen_texts = set()
        self.driver = None
        self.proxy_tmp_dir = None

    def _init_driver(self, headless: bool = True):
        """Initialize the Selenium driver with stealth settings and proxies."""
        self.logger.info("initializing_selenium_driver", headless=headless, use_proxy=self.use_proxy)
        
        options = Options()
        
        # 1. Setup Proxies (Bright Data Residential)
        # proxy_server = self.cfg.get('brightdata_proxy_server')
        # proxy_user = self.cfg.get('brightdata_proxy_user')
        # proxy_pass = self.cfg.get('brightdata_proxy_pass')
        # 
        # if self.use_proxy and proxy_server:
        #     try:
        #         # Format: brd.superproxy.io:33335
        #         host_port = proxy_server.replace("http://", "").replace("https://", "")
        #         if ":" in host_port:
        #             host, port = host_port.split(":")
        #             if proxy_user and proxy_pass:
        #                 self.logger.info("loading_proxy_with_auth", host=host, port=port)
        #                 self.proxy_tmp_dir = tempfile.mkdtemp()
        #                 extension_path = self._create_proxy_extension(host, port, proxy_user, proxy_pass, self.proxy_tmp_dir)
        #                 options.add_extension(extension_path)
        #             else:
        #                 self.logger.info("loading_proxy_no_auth", host=host, port=port)
        #                 options.add_argument(f'--proxy-server={proxy_server}')
        #     except Exception as e:
        #         self.logger.error("proxy_setup_failed", error=str(e))

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
        options.add_argument('--window-size=1366,768')
        options.add_argument('--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36')
        
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
            service = Service(chromedriver_path, service_args=['--verbose'])
        else:
            self.logger.info("system_binaries_not_found_falling_back_to_webdriver_manager")
            service = Service(ChromeDriverManager().install(), service_args=['--verbose'])
        
        # Increase timeout for Chrome startup (especially when running multiple instances)
        self.driver = webdriver.Chrome(service=service, options=options)
        self.driver.set_page_load_timeout(300)  # 5 minutes for page loads
        
        # Inject anti-detection scripts
        self._inject_stealth_scripts()
        
        try:
            self.driver.maximize_window()
        except:
            pass
            
        self.logger.info("driver_initialized")

    def _create_proxy_extension(self, proxy_host, proxy_port, proxy_user, proxy_pass, folder):
        """Create a Chrome extension on the fly to handle proxy authentication."""
        manifest_json = """
        {
            "version": "1.0.0",
            "manifest_version": 2,
            "name": "Chrome Proxy",
            "permissions": [
                "proxy",
                "tabs",
                "unlimitedStorage",
                "storage",
                "<all_urls>",
                "webRequest",
                "webRequestBlocking"
            ],
            "background": {
                "scripts": ["background.js"]
            },
            "minimum_chrome_version":"22.0.0"
        }
        """

        background_js = """
        var config = {
                mode: "fixed_servers",
                rules: {
                singleProxy: {
                    scheme: "http",
                    host: "%s",
                    port: parseInt(%s)
                },
                bypassList: ["localhost"]
                }
            };

        chrome.proxy.settings.set({value: config, scope: "regular"}, function() {});

        chrome.webRequest.onAuthRequired.addListener(
                    function(details) {
                        return {
                            authCredentials: {
                                username: "%s",
                                password: "%s"
                            }
                        };
                    },
                    {urls: ["<all_urls>"]},
                    ["blocking"]
        );
        """ % (proxy_host, proxy_port, proxy_user, proxy_pass)

        extension_path = os.path.join(folder, 'proxy_auth_plugin.zip')
        with zipfile.ZipFile(extension_path, 'w') as zp:
            zp.writestr("manifest.json", manifest_json)
            zp.writestr("background.js", background_js)

        return extension_path

    def quit(self):
        """Quit the driver and clean up resources."""
        if self.driver:
            try:
                self.driver.quit()
                self.logger.info("driver_quit_successful")
            except Exception as e:
                self.logger.warning("driver_quit_failed", error=str(e))
        
        # Clean up temporary proxy directory
        if self.proxy_tmp_dir and os.path.exists(self.proxy_tmp_dir):
            import shutil
            try:
                shutil.rmtree(self.proxy_tmp_dir)
                self.logger.info("proxy_temp_dir_cleaned", path=self.proxy_tmp_dir)
            except Exception as e:
                self.logger.warning("proxy_temp_dir_cleanup_failed", error=str(e))
        
        self.driver = None
        self.proxy_tmp_dir = None

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

            added_count = 0
            for cookie in cookie_list:
                try:
                    c = {
                        'name': cookie.get('name'),
                        'value': cookie.get('value'),
                        'domain': cookie.get('domain', '.facebook.com'),
                        'path': cookie.get('path', '/')
                    }
                    if 'expiry' in cookie: c['expiry'] = int(cookie['expiry'])
                    elif 'expirationDate' in cookie: c['expiry'] = int(cookie['expirationDate'])
                    
                    if 'secure' in cookie: c['secure'] = cookie['secure']
                    
                    self.driver.add_cookie(c)
                    added_count += 1
                except:
                    continue
            
            self.logger.info("cookies_injected_to_browser", count=added_count)
            self.driver.refresh()
            time.sleep(5)
            
            # Log final count of cookies in browser
            browser_cookies = self.driver.get_cookies()
            self.logger.info("browser_cookie_count_after_refresh", count=len(browser_cookies))
            
            if self._is_logged_in():
                self.logger.info("facebook_session_verified_logged_in")
                return True
            else:
                self.logger.warning("facebook_session_invalid_after_cookie_injection", 
                                  url=self.driver.current_url, 
                                  title=self.driver.title)
                return False
        except Exception as e:
            self.logger.error("failed_to_load_cookies", error=str(e))
            return False

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
                'div[role="dialog"] [aria-label="Close"]',
                '#login_popup_cta_form i.x1n2onr6' # Login popup close button
            ]
            
            for selector in close_selectors:
                try:
                    elements = self.driver.find_elements(By.CSS_SELECTOR, selector)
                    for el in elements:
                        if el.is_displayed():
                            el.click()
                            self.logger.info("popup_closed", selector=selector)
                            time.sleep(0.5)
                except:
                    pass
            
            # Special check for the "login/signup" banner at the bottom
            try:
                self.driver.execute_script("""
                    const banner = document.querySelector('div[role="banner"]');
                    if (banner && (banner.textContent.includes('Log In') || banner.textContent.includes('Sign Up'))) {
                        banner.style.display = 'none';
                    }
                """)
            except: pass

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
                    'div[data-testid="post_message"]',
                    'div.x1iorvi4.x1pi30zi.x1l90r2v.x1swvt1m', # New FB container class
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

    def parse_item(self, raw_data: Dict[str, Any], custom_keywords: Optional[str] = None, 
                   exclude_keywords: Optional[list] = None,
                   custom_indicators: Optional[list] = None) -> Optional[FacebookLead]:
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
            
            # Combine title and description for buyer intent analysis
            text = f"{raw_data.get('title', '')} {raw_data.get('text', '')}"
            
            # Use centralized buyer intent detector
            is_buyer_request = BuyerIntentDetector.is_buyer_request(
                text=text,
                require_url=False,  # Facebook posts may not always have stable URLs
                url=raw_data.get('link'),
                custom_keywords=custom_keywords,
                exclude_keywords=exclude_keywords,
                custom_indicators=custom_indicators
            )
            
            # Log detection reason for debugging
            if not is_buyer_request:
                reason = BuyerIntentDetector.get_detection_reason(text, raw_data.get('link'))
                self.logger.debug("filtered_non_buyer_post", reason=reason, title=raw_data.get('title'))

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
                is_buyer_request=is_buyer_request,
                extra_data={'raw_date': post_date_str, 'scraped_at': raw_data.get('scraped_at')}
            )
        except Exception as e:
            self.logger.warning("failed_to_create_facebook_lead", error=str(e))
            return None

    def _scroll_smoothly(self, scroll_count=0):
        """Perform aggressive, human-like scrolling with multiple fallbacks."""
        try:
            # 0. Focus and wiggle to wake up event listeners
            self.driver.execute_script("document.body.focus();")
            self.driver.execute_script("window.scrollBy(0, -50);")
            time.sleep(0.2)
            self.driver.execute_script("window.scrollBy(0, 50);")
            time.sleep(0.3)
            
            # 1. Random small scrolls (mimic mouse wheel)
            for _ in range(3):
                amount = random.randint(500, 1000)
                self.driver.execute_script(f"window.scrollBy(0, {amount});")
                time.sleep(random.uniform(0.5, 1.0))
            
            # 2. Use Page Down keys (very effective for Facebook)
            actions = ActionChains(self.driver)
            for _ in range(random.randint(2, 4)):
                actions.send_keys(Keys.PAGE_DOWN)
                time.sleep(random.uniform(0.2, 0.4))
            actions.perform()
            
            # 3. Use JavaScript to scroll to the last found article
            # This triggers the IntersectionObserver better than just scrolling to the bottom
            self.driver.execute_script("""
                const articles = document.querySelectorAll('div[role="article"]');
                if (articles.length > 0) {
                    articles[articles.length - 1].scrollIntoView({ behavior: 'smooth', block: 'end' });
                } else {
                    window.scrollTo(0, document.body.scrollHeight);
                }
            """)
            
            # 4. Occasional 'End' key to trigger lazy loading
            if scroll_count % 2 == 0:
                self.logger.info("sending_end_key_for_lazy_load")
                ActionChains(self.driver).send_keys(Keys.END).perform()
                time.sleep(2)
            
            # 5. Check for "Loading" indicators or "See More" buttons at the bottom
            self.driver.execute_script("""
                const loadMore = Array.from(document.querySelectorAll('span, div')).find(el => 
                    el.textContent && (el.textContent.includes('See more posts') || el.textContent.includes('Loading'))
                );
                if (loadMore) {
                    loadMore.scrollIntoView();
                    if (typeof loadMore.click === 'function') loadMore.click();
                }
            """)
            
            time.sleep(2.5) # Allow meaningful time for fetch
            
        except Exception as e:
            self.logger.debug("scroll_failed", error=str(e))

    def login(self, email, password):
        """Login to Facebook with credentials and handle multi-stage security checkpoints."""
        self.logger.info("logging_in_to_facebook")
        
        try:
            self.driver.get('https://www.facebook.com/login')
            time.sleep(5)
            
            # 1. Handle initial blockers
            if self._is_captcha_present():
                self.logger.warning("captcha_detected_at_login_start")
                self._try_solve_captcha()

            self._handle_cookie_banners()
            
            # 2. Fill Credentials
            if not self._fill_credentials(email, password):
                return False
            
            # 3. Handle Security Sequence (Loop until logged in or timeout)
            # Facebook often presents multiple screens: Captcha -> Identity Confirmation -> Home
            self.logger.info("entering_security_sequence_monitoring")
            start_time = time.time()
            max_wait = 150 # 2.5 minutes total for the whole sequence
            
            while time.time() - start_time < max_wait:
                if self._is_logged_in():
                    self.logger.info("login_successful_verified")
                    self._save_cookies()
                    return True
                
                # Check for Security Checkpoint or CAPTCHA
                if self._is_captcha_present():
                    self.logger.warning("security_challenge_detected_solving")
                    self._try_solve_captcha()
                    time.sleep(8) # Wait for page to process solve
                    continue
                
                # Check for "Continue" / "Next" buttons common in security checkpoints
                continue_selectors = [
                    'button[type="submit"]',
                    'button#checkpointSubmitButton',
                    'div[role="button"][id*="checkpoint"]',
                    '//button[contains(., "Continue")]',
                    '//button[contains(., "Next")]',
                    '//button[contains(., "Yes")]',
                    '//button[contains(., "OK")]',
                    '//button[contains(., "This was me")]',
                    '//button[contains(., "Continuar")]',
                    '//button[contains(., "Próximo")]',
                    '//button[contains(., "Confirm")]',
                    '//span[contains(., "Continue")]/ancestor::button',
                    '//div[@role="button" and (contains(., "Continue") or contains(., "Continuar"))]'
                ]
                
                button_clicked = False
                for sel in continue_selectors:
                    try:
                        btn = self.driver.find_element(By.XPATH, sel) if sel.startswith('//') else self.driver.find_element(By.CSS_SELECTOR, sel)
                        if btn.is_displayed() and btn.is_enabled():
                            self.logger.info("clicking_security_continue_button", selector=sel)
                            self.driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", btn)
                            time.sleep(1)
                            self.driver.execute_script("arguments[0].click();", btn)
                            button_clicked = True
                            time.sleep(10) # Give it time to load next stage
                            break
                    except: continue
                
                if not button_clicked:
                    self.logger.debug("no_actionable_security_elements_waiting", url=self.driver.current_url)
                    time.sleep(8)
                    
            self.logger.error("login_timed_out_no_success_indicators", url=self.driver.current_url)
            return False
            
        except Exception as e:
            self.logger.error("login_exception", error=str(e), url=self.driver.current_url)
            return False

    def _is_captcha_present(self):
        """Detect if reCAPTCHA or Meta CAPTCHA is on screen.

        IMPORTANT: This method uses conservative detection to avoid false positives.
        Short or ambiguous strings (e.g. 'puzzle', 'checkpoint') have been removed
        from text-based detection. Text checks also require the matching element to
        be visible, ruling out hidden ad units or off-screen content.
        """
        try:
            # 1. Check for known challenge URLs or path segments
            current_url = self.driver.current_url.lower()
            if any(x in current_url for x in ['checkpoint', 'challenge', 'captcha']):
                self.logger.info("captcha_detected_via_url", url=current_url)
                return True

            # 2. Check for reCAPTCHA / hCaptcha / FunCaptcha iframes (Highest Reliability)
            iframes = self.driver.find_elements(By.TAG_NAME, 'iframe')
            for iframe in iframes:
                try:
                    src = iframe.get_attribute('src') or ""
                    if any(x in src.lower() for x in ['recaptcha', 'captcha', 'hcaptcha', 'arkoselabs', 'checkpoint']):
                        self.logger.info("captcha_detected_via_iframe", src=src[:100])
                        return True
                except: continue

            # 3. Text-based detection — ONLY use long, highly specific phrases that won't
            #    false-match unrelated page content (ads, nav labels, sidebar text, etc.).
            #    Removed: 'checkpoint' (covered by URL check), 'puzzle'/'puzzel' (too short,
            #    caused false positive matching e.g. "bus" substring in prior logs).
            captcha_texts = [
                'Confirm Your Identity',
                'Security Check',
                'Please solve the puzzle',
                'Enter the code below',
                'Help us confirm your identity',
                'verify your account',
            ]
            for text in captcha_texts:
                try:
                    text_lower = text.lower()
                    # Use case-insensitive XPath contains on normalized text
                    xpath = (
                        f"//*[contains("
                        f"translate(normalize-space(.), "
                        f"'ABCDEFGHIJKLMNOPQRSTUVWXYZ', "
                        f"'abcdefghijklmnopqrstuvwxyz'), "
                        f"'{text_lower}')]"
                    )
                    matches = self.driver.find_elements(By.XPATH, xpath)
                    # Extra guard: only count visible elements to avoid hidden ad units
                    visible = [m for m in matches if m.is_displayed()]
                    if visible:
                        self.logger.info("captcha_detected_via_text", text=text)
                        return True
                except:
                    continue

            # 4. Look for the "Meta" challenge container or specific elements
            captcha_indicators = [
                'img[src*="captcha"]',
                'input[name="captcha_response"]',
                '.rc-anchor',
                '#captcha_image',
                'header img[alt="Meta"]',
                '.g-recaptcha',
                '#recaptcha',
                '#shredder-iframe', # Internal FB captcha iframe
                'div[id*="captcha"]'
            ]
            for selector in captcha_indicators:
                if self.driver.find_elements(By.CSS_SELECTOR, selector):
                    self.logger.info("captcha_detected_via_selector", selector=selector)
                    return True
            
            return False
        except: return False

    def _try_solve_captcha(self):
        """Bypass CAPTCHA using 2Captcha if API key is present."""
        api_key = os.getenv("TWO_CAPTCHA_API_KEY")
        if not api_key:
            self.logger.error("captcha_solver_missing_api_key", msg="Please add TWO_CAPTCHA_API_KEY to your .env to bypass the Meta challenge.")
            return False

        try:
            from twocaptcha import TwoCaptcha
            solver = TwoCaptcha(api_key)
            self.logger.info("attempting_captcha_solve_via_2captcha")
            
            # Try to find reCAPTCHA site key first
            site_key = None
            try:
                # Primary method: check for the recaptcha iframe src
                iframes = self.driver.find_elements(By.CSS_SELECTOR, 'iframe[src*="recaptcha/api2/anchor"]')
                if iframes:
                    src = iframes[0].get_attribute('src')
                    match = re.search(r'k=([^&]+)', src)
                    if match: site_key = match.group(1)
            except: pass

            if not site_key:
                try:
                    # Secondary method: look for data-sitekey attribute in DOM
                    elements = self.driver.find_elements(By.CSS_SELECTOR, '[data-sitekey]')
                    if elements:
                        site_key = elements[0].get_attribute('data-sitekey')
                except: pass

            if site_key:
                self.logger.info("solving_recaptcha", site_key=site_key)
                result = solver.recaptcha(sitekey=site_key, url=self.driver.current_url)
                code = result['code']
                
                # Use JS to inject the code into all possible reCAPTCHA response fields
                self.driver.execute_script(f"""
                    const fields = document.querySelectorAll('[id^="g-recaptcha-response"], [name^="g-recaptcha-response"]');
                    fields.forEach(f => {{
                        f.innerHTML = "{code}";
                        f.value = "{code}";
                        f.style.display = 'block'; // Ensure it's not hidden
                    }});
                """)
                
                # Check for callbacks
                try:
                    self.driver.execute_script("""
                        if (typeof(onCaptchaFinished) === 'function') { onCaptchaFinished(); }
                        if (typeof(___grecaptcha_cfg) !== 'undefined') {
                            Object.keys(___grecaptcha_cfg.clients).forEach(clientId => {
                                const client = ___grecaptcha_cfg.clients[clientId];
                                Object.keys(client).forEach(prop => {
                                    if (client[prop] && client[prop].callback) {
                                        client[prop].callback();
                                    }
                                });
                            });
                        }
                    """) 
                except:
                    # Fallback: Click verify button if callback is not found
                    try:
                        verify_btn = self.driver.find_element(By.ID, "recaptcha-verify-button")
                        verify_btn.click()
                    except: pass
                
                self.logger.info("recaptcha_solved_successfully")
                time.sleep(5)
                return True
            
            # Fallback: Check for Image CAPTCHA (Normal)
            captcha_img = None
            image_selectors = [
                'img[src*="captcha"]', 
                '#captcha_image', 
                'img[alt="Captcha"]',
                'img[src*="checkpoint/dyi"]',
                'img.captcha'
            ]
            for selector in image_selectors:
                try:
                    elements = self.driver.find_elements(By.CSS_SELECTOR, selector)
                    if elements and elements[0].is_displayed():
                        captcha_img = elements[0]
                        break
                except: continue
                
            if captcha_img:
                self.logger.info("solving_image_captcha")
                # Wait for image to load
                time.sleep(2)
                # Take element screenshot
                captcha_path = "/tmp/fb_captcha.png"
                captcha_img.screenshot(captcha_path)
                
                result = solver.normal(captcha_path)
                code = result['code']
                self.logger.info("image_captcha_solved", code=code)
                
                # Find input field to enter the code
                input_field = None
                input_selectors = [
                    'input[name="captcha_response"]', 
                    'input#captcha_response', 
                    'input[type="text"]',
                    'input.captcha_input'
                ]
                for selector in input_selectors:
                    try:
                        inputs = self.driver.find_elements(By.CSS_SELECTOR, selector)
                        # Find the first visible/interactable one
                        for inp in inputs:
                            if inp.is_displayed():
                                input_field = inp
                                break
                        if input_field: break
                    except: continue
                
                if input_field:
                    input_field.clear()
                    input_field.send_keys(code)
                    time.sleep(1)
                    
                    # Instead of .submit(), try to find the "Continue" or "Submit" button
                    submitted = False
                    submit_selectors = [
                        'button[type="submit"]',
                        'input[type="submit"]',
                        'button#checkpointSubmitButton',
                        '//button[contains(., "Continue")]',
                        '//button[contains(., "Submit")]',
                        '//button[contains(., "Next")]',
                        '//button[contains(., "Continuar")]',
                        '//button[contains(., "Confirm")]',
                        '//button[contains(., "Entrar")]',
                        '//div[@role="button" and (contains(., "Continue") or contains(., "Continuar"))]'
                    ]
                    
                    for sel in submit_selectors:
                        try:
                            if sel.startswith('//'):
                                btn = self.driver.find_element(By.XPATH, sel)
                            else:
                                btn = self.driver.find_element(By.CSS_SELECTOR, sel)
                                
                            if btn.is_displayed():
                                self.driver.execute_script("arguments[0].click();", btn)
                                self.logger.info("captcha_submit_button_clicked", selector=sel)
                                submitted = True
                                break
                        except: continue
                        
                    if not submitted:
                        # Fallback: Send Enter key
                        self.logger.info("no_submit_button_found_sending_enter")
                        input_field.send_keys(Keys.ENTER)
                        
                    time.sleep(5)
                    return True
                else:
                    self.logger.error("could_not_find_captcha_input_field")
            
            self.logger.error("could_not_extract_any_captcha_type")
            return False
        except Exception as e:
            self.logger.error("captcha_solver_error", error=str(e))
            return False

    def _handle_cookie_banners(self):
        cookie_selectors = [
            "//button[contains(., 'Allow all cookies')]",
            "//button[contains(., 'Allow essential and optional cookies')]",
            "//button[contains(., 'Accept All')]",
            "//button[contains(., 'Accept all')]",
            "//button[contains(., 'Only allow essential cookies')]",
            "//button[contains(., 'Decline optional cookies')]",
            "//button[@data-cookiebanner='accept_button']",
            "//button[@id='cookie_banner_accept_button']"
        ]
        for xpath in cookie_selectors:
            try:
                btns = self.driver.find_elements(By.XPATH, xpath)
                if btns:
                    self.driver.execute_script("arguments[0].scrollIntoView(true);", btns[0])
                    time.sleep(0.5)
                    try:
                        btns[0].click()
                    except:
                        self.driver.execute_script("arguments[0].click();", btns[0])
                    self.logger.info("cookie_banner_clicked", xpath=xpath)
                    time.sleep(2)
                    break
            except: continue

    def _fill_credentials(self, email, password, retry_count=0):
        """Fill email and password fields, handling popups and interactability issues."""
        if retry_count > 3:
            self.logger.error("max_fill_retries_reached_aborting")
            return False
            
        try:
            self.logger.info("filling_credentials", url=self.driver.current_url)
            # 1. Enter Email
            email_field = None
            email_selectors = ['input[name="email"]', '#email', 'input[type="text"]', 'input[placeholder*="Email"]', 'input[aria-label*="email"]']
            
            for selector in email_selectors:
                try:
                    email_field = WebDriverWait(self.driver, 10).until(
                        EC.presence_of_element_located((By.CSS_SELECTOR, selector))
                    )
                    if email_field.is_displayed(): 
                        self.driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", email_field)
                        time.sleep(1)
                        break
                except: continue
                
            if not email_field:
                url = self.driver.current_url
                self.logger.warning("email_field_not_found", url=url, title=self.driver.title)
                if self._is_captcha_present():
                    self.logger.warning("captcha_detected_during_fill_credentials")
                    self._try_solve_captcha()
                    return self._fill_credentials(email, password, retry_count + 1)
                
                if "cookie" in url.lower() or "consent" in url.lower():
                    self.logger.info("looks_like_cookie_consent_landing_page")
                    self._handle_cookie_banners()
                    time.sleep(3)
                    return self._fill_credentials(email, password, retry_count + 1)
                
                raise ValueError(f"Could not find email field on page: {url}")
                
            # Use JS to focus and clear to avoid focus issues
            self.driver.execute_script("arguments[0].focus();", email_field)
            self.driver.execute_script("arguments[0].value = '';", email_field)
            time.sleep(0.5)

            # Try to type normally first, fallback to JS if it fails
            try:
                for char in email:
                    email_field.send_keys(char)
                    time.sleep(random.uniform(0.04, 0.12))
                self.logger.info("email_typed_standard")
            except Exception as e:
                self.logger.warning("email_typing_standard_failed_using_js", error=str(e))
                self.driver.execute_script("arguments[0].value = arguments[1];", email_field, email)

            # 2. Enter Password
            password_field = None
            password_selectors = ['input[name="pass"]', '#pass', 'input[type="password"]', 'input[placeholder*="Password"]', 'input[aria-label*="password"]']
            
            for selector in password_selectors:
                try:
                    password_field = self.driver.find_element(By.CSS_SELECTOR, selector)
                    if password_field.is_displayed(): 
                        self.driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", password_field)
                        time.sleep(1)
                        break
                except: continue
                
            if not password_field:
                raise ValueError("Could not find password field.")
                
            self.driver.execute_script("arguments[0].focus();", password_field)
            self.driver.execute_script("arguments[0].value = '';", password_field)
            time.sleep(0.5)

            try:
                for char in password:
                    password_field.send_keys(char)
                    time.sleep(random.uniform(0.04, 0.12))
                self.logger.info("password_typed_standard")
            except Exception as e:
                self.logger.warning("password_typing_standard_failed_using_js", error=str(e))
                self.driver.execute_script("arguments[0].value = arguments[1];", password_field, password)
            
            # 3. Click Login
            login_btn = None
            login_selectors = ['button[name="login"]', 'button[type="submit"]', 'input[type="submit"]', '[data-testid="royal_login_button"]']
            
            for selector in login_selectors:
                try:
                    login_btn = self.driver.find_element(By.CSS_SELECTOR, selector)
                    if login_btn.is_displayed(): 
                        self.driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", login_btn)
                        time.sleep(1)
                        break
                except: continue
                
            if not login_btn:
                # Last resort: look for any button with "Log In"
                try:
                    login_btn = self.driver.find_element(By.XPATH, "//button[contains(., 'Log In')] | //button[contains(., 'Entrar')]")
                except: pass
                
            if not login_btn:
                raise ValueError("Could not find login button.")
                
            self.logger.info("clicking_login_button")
            try:
                # Try clicking normally with a shorter wait
                WebDriverWait(self.driver, 5).until(EC.element_to_be_clickable(login_btn))
                login_btn.click()
            except Exception as e:
                self.logger.warning("click_standard_failed_using_js", error=str(e))
                self.driver.execute_script("arguments[0].click();", login_btn)
                
            return True
        except Exception as e:
            self.logger.error("credential_fill_failed", error=str(e), url=self.driver.current_url, title=self.driver.title)
            # Check for captcha one last time if failed
            if self._is_captcha_present():
                self.logger.warning("captcha_detected_after_fill_failure")
                if self._try_solve_captcha():
                    return self._fill_credentials(email, password, retry_count + 1) # Recursive retry
            return False

    def _save_cookies(self):
        """Save current driver cookies to MongoDB using UserCredentialManager."""
        try:
            cookies = self.driver.get_cookies()
            if not cookies:
                self.logger.warning("no_cookies_found_in_browser_nothing_to_save")
                return None
            
            if self.user_email:
                manager = UserCredentialManager()
                # Remove existing (as per "remove then save" preference for efficiency/cleanliness)
                manager.delete_cookies(self.user_email, 'facebook')
                manager.save_cookies(self.user_email, 'facebook', cookies)
                self.logger.info("cookies_saved_to_mongodb", user=self.user_email)
            else:
                # Fallback to local file if no user context
                cookie_file = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), 
                                         "cookies", "facebook_cookies.json")
                os.makedirs(os.path.dirname(cookie_file), exist_ok=True)
                with open(cookie_file, 'w') as f:
                    json.dump(cookies, f, indent=2)
                self.logger.info("cookies_saved_to_file_fallback", path=cookie_file)
                
            return cookies
        except Exception as e:
            self.logger.error("failed_to_save_cookies", error=str(e))
            return None

    def _is_logged_in(self):
        """Check if session is authenticated."""
        try:
            # Log state for debugging
            current_url = self.driver.current_url.lower()
            page_title = self.driver.title
            
            # Check current URL first
            if "login" in current_url or "checkpoint" in current_url or "confirmemail" in current_url:
                self.logger.debug("login_check_failed_due_to_url", url=current_url)
                return False

            # Check for profile link, account menu, or home feed indicators
            indicators = [
                'div[aria-label*="Account"]',
                'div[aria-label*="Your profile"]',
                'a[href*="/me/"]',
                'svg[aria-label="Your profile"]',
                'a[aria-label="Home"]',
                'div[aria-label*="Stories"]',
                '[role="feed"]',
                'div[aria-label*="What\'s on your mind?"]', # Feed indicator
                'a[href="/"]'
            ]
            for inc in indicators:
                if self.driver.find_elements(By.CSS_SELECTOR, inc):
                    self.logger.debug("login_confirmed_via_indicator", selector=inc)
                    return True
            
            # Fallback: check if the "Log In" button exists (if it does, we are NOT logged in)
            login_buttons = [
                'button[name="login"]',
                'a[href*="/login"]',
            ]
            for btn_sel in login_buttons:
                if self.driver.find_elements(By.CSS_SELECTOR, btn_sel):
                    return False
                     
            return False
        except Exception as e:
            self.logger.debug("is_logged_in_check_error", error=str(e))
            return False

    def scrape(self, target: str = None, **kwargs) -> List[ScrapedLead]:
        """Main scraping method using Selenium."""
        limit = kwargs.get('limit', 25)
        # Handle limit -1 as unlimited
        if limit == -1:
            target_posts = 999999
        else:
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
            
            # Handle expired cookies: If loaded but not logged in, clear them
            if not session_ok and self.cookies and self.user_email:
                self.logger.warning("facebook_cookies_expired_removing_stale_record", user=self.user_email)
                UserCredentialManager().delete_cookies(self.user_email, 'facebook')
            
            # If cookies fail but we have credentials, try to login (Automatic Rotation)
            if not session_ok and email and password:
                self.logger.info("attempting_automatic_session_rotation", user=self.user_email)
                session_ok = self.login(email, password)
            
            if not session_ok:
                self.logger.error("failed_to_establish_authenticated_session")
                raise ValueError("Facebook authentication failed. Please update credentials or cookies.")
            
            self.logger.info("navigating_to_target", url=target)
            self.driver.get(target)
            
            # Allow more time for initial load and redirects (e.g. share links)
            time.sleep(8)
            
            # Check for redirect or login wall
            current_url = self.driver.current_url
            if 'login' in current_url or 'checkpoint' in current_url:
                self.logger.warning("login_wall_detected", url=current_url)
            
            self._close_popups()
            
            last_height = self.driver.execute_script("return document.body.scrollHeight")
            scroll_count = 0
            no_change_count = 0
            consecutive_no_new_posts = 0
            last_batch_save = 0
            
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
                
                # Wait for content to load - Facebook is heavy
                time.sleep(2.5)
                
                # Broadened selectors for Facebook's dynamic UI
                selectors = [
                    'div[role="feed"] div[role="article"]',
                    'div[role="main"] div[role="article"]',
                    'div[role="article"]',
                    'div[aria-posinset]', # Very reliable for FB posts
                    'div[data-testid="fbfeed_story"]',
                    'div.x1yztpqf.x17906v1', # Common feed item container
                    'div[data-ad-preview="message"]'
                ]
                
                articles = []
                for selector in selectors:
                    articles = self.driver.find_elements(By.CSS_SELECTOR, selector)
                    if articles:
                        self.logger.debug("articles_found_with_selector", selector=selector, count=len(articles))
                        break
                    
                if not articles:
                    # Debug: Log what IS in the feed if nothing was found
                    try:
                        feed_content = self.driver.execute_script("return document.body.innerText.substring(0, 500);")
                        self.logger.debug("no_articles_found_body_preview", preview=feed_content)
                        # Try to find any div with substantial text
                        divs = self.driver.find_elements(By.CSS_SELECTOR, 'div[dir="auto"]')
                        if divs:
                            self.logger.debug("found_generic_divs_instead", count=len(divs))
                            # Fallback to these divs if they look like posts
                            articles = [d for d in divs[:20] if len(d.text) > 50]
                    except: pass
                    
                self.logger.info("articles_found_in_dom", count=len(articles))
                
                posts_before = len(extracted_leads)
                
                for article in articles:
                    if len(extracted_leads) >= target_posts:
                        break
                        
                    try:
                        # Extract link with more patterns
                        link = None
                        link_selectors = [
                            'a[href*="/posts/"]', 
                            'a[href*="/photos/"]', 
                            'a[href*="/videos/"]', 
                            'a[href*="/reel/"]',
                            'a[href*="fbid="]',
                            'a[href*="/permalink/"]',
                            'a[href*="/group/"]'
                        ]
                        
                        for sel in link_selectors:
                            try:
                                els = article.find_elements(By.CSS_SELECTOR, sel)
                                for e in els:
                                    href = e.get_attribute('href')
                                    if href and 'facebook.com' in href and not any(x in href for x in ['#', 'javascript:']):
                                        link = href.split('?')[0]
                                        break
                                if link: break
                            except: continue
                        
                        # Extract post text
                        post_text = self._extract_post_content_only(article)
                        text_hash = post_text[:200].strip() if post_text else ""
                        
                        # VALIDATION: Skip if definitely not a post (no text AND no valid link)
                        if not link and (not text_hash or len(text_hash) < 15):
                            self.logger.debug("skipping_empty_article_stub")
                            continue
                        
                        # Skip if we've seen this URL
                        if link and link in self.seen_urls:
                            continue
                        
                        # Skip if we've seen this text (for posts without fixed URLs)
                        # We use a longer hash for better uniqueness
                        if not link and text_hash and text_hash in self.seen_texts:
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
                        
                        if (lead := self.parse_item(raw_item, 
                                                   custom_keywords=kwargs.get('keywords'),
                                                   exclude_keywords=kwargs.get('exclude_keywords'),
                                                   custom_indicators=kwargs.get('custom_indicators'))):
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
                    
                    # Batch save every 25 posts to MongoDB during the scrape
                    if len(extracted_leads) >= last_batch_save + 25:
                        self.logger.info("intermediate_batch_save_triggered", 
                                       count=len(extracted_leads),
                                       batch_size=len(extracted_leads) - last_batch_save)
                        try:
                            scraper_cap = self.scraper_name.capitalize()
                            # Save to both raw and final collections
                            self.save_leads(extracted_leads, collection=f"{scraper_cap}_raw_data")
                            self.save_leads(extracted_leads, collection=f"{scraper_cap}_final_data")
                            last_batch_save = len(extracted_leads)
                        except Exception as e:
                            self.logger.error("intermediate_batch_save_failed", error=str(e))
                
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
                    
                    # Be even more patient - Facebook feed can be very slow
                    if no_change_count >= 20: 
                        self.logger.info("end_of_content_reached_confirmed")
                        break
                    
                    # Try more aggressive unsticking after 5 fails
                    if no_change_count > 5:
                        self.logger.info("forcing_content_load_via_alternative_scroll")
                        # Scroll UP then DOWN
                        self.driver.execute_script("window.scrollBy(0, -1500);")
                        time.sleep(1)
                        self.driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
                        time.sleep(3)
                        # Also click the body just in case
                        try:
                            self.driver.find_element(By.TAG_NAME, "body").click()
                        except: pass
                else:
                    no_change_count = 0
                    last_height = new_height
                
                scroll_count += 1
                
                # Safety limit
                if scroll_count > 200:
                    self.logger.info("safety_scroll_limit_reached")
                    break
                
            self.logger.info("scraping_completed", total_posts=len(extracted_leads))
            
        except Exception as e:
            self.logger.error("scraping_failed", error=str(e))
            traceback.print_exc()
            raise # Re-raise to ensure Airflow sees the failure
        finally:
            self.quit()
                
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