"""Facebook scraper — Selenium + CDP GraphQL capture + full lead pipeline.

Key changes vs previous version
─────────────────────────────────
* scrape() iterates over a list of search_urls supplied by the caller
  (loaded from MongoDB before calling scrape()).
* All buyer-intent / exclusion / US-location / scoring / category logic
  from facebook_lead_engine_v2.py is embedded here — no extra imports.
* parse_item() is still available for legacy use; new path uses
  _is_valid_lead() → _is_us_location() → _score_lead() → _classify_category()
  which mirrors the pipeline in file 1 exactly.
* Cookies and save-to-db wiring is unchanged — callers pass cookies in and
  the existing db_manager / UserCredentialManager handles persistence.
"""

from typing import List, Dict, Any, Optional
from datetime import datetime
import os
import re
import json
import time
import traceback
import random
import logging
from collections import defaultdict

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.chrome.service import Service
from selenium.common.exceptions import (
    TimeoutException,
    ElementNotInteractableException,
    NoSuchElementException,
    ElementClickInterceptedException,
)

import sys

src_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if src_dir not in sys.path:
    sys.path.append(src_dir)

try:
    from scrapers.base import BaseScraper
    from models import FacebookLead, ScrapedLead
    from utils.buyer_intent import (
        BuyerIntentDetector,
        is_us_location,
        score_lead,
        classify_category,
        MIN_SCORE,
    )
    from user_credential_manager import UserCredentialManager
    from utils.email_manager import EmailManager
except ImportError:
    try:
        from .base import BaseScraper
        from ..models import FacebookLead, ScrapedLead
        from ..utils.buyer_intent import BuyerIntentDetector
        from ..user_credential_manager import UserCredentialManager
        from ..utils.email_manager import EmailManager
    except (ImportError, ValueError):
        from base import BaseScraper
        from models import FacebookLead, ScrapedLead
        from utils.buyer_intent import BuyerIntentDetector
        from user_credential_manager import UserCredentialManager
        try:
            from utils.email_manager import EmailManager
        except ImportError:
            try:
                from email_manager import EmailManager
            except ImportError:
                EmailManager = None


# ══════════════════════════════════════════════════════════════════════════════
#  LEAD PIPELINE — Consistently using BuyerIntentDetector
# ══════════════════════════════════════════════════════════════════════════════
# Constants and helpers are now imported from utils.buyer_intent


# ══════════════════════════════════════════════════════════════════════════════
#  SCRAPER CLASS
# ══════════════════════════════════════════════════════════════════════════════


class FacebookScraper(BaseScraper):
    """Scraper for Facebook posts using Selenium + CDP GraphQL capture."""

    def __init__(self, cookies: Optional[Dict[str, str]] = None, **kwargs):
        super().__init__("facebook", db_manager=kwargs.get("db_manager"))
        self.cookies = cookies or {}
        self.headless_default = kwargs.get("headless", True)

        if isinstance(self.cookies, str) and os.path.exists(self.cookies):
            with open(self.cookies, "r") as f:
                self.cookies = json.load(f)

        if self.cookies:
            self.logger.info(
                "using_provided_cookies",
                source="argument_or_variable",
                count=len(self.cookies) if isinstance(self.cookies, list) else "dict",
            )
        else:
            self.logger.warning("no_cookies_provided_scraper_will_likely_fail")

        self.seen_urls = set()
        self.seen_texts = set()
        self.driver = None

        self.email = kwargs.get("email") or os.getenv("FACEBOOK_EMAIL", "default")
        safe_email = re.sub(r"[^a-zA-Z0-9]", "_", self.email)

        if os.path.exists("/opt/airflow"):
            self.profiles_base_dir = "/opt/airflow/scraper/cookies/facebook_profiles"
        else:
            project_root = os.path.dirname(
                os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
            )
            self.profiles_base_dir = os.path.join(
                project_root, "scraper", "cookies", "facebook_profiles"
            )

        self.user_profile_dir = os.path.join(self.profiles_base_dir, safe_email)

        if kwargs.get("clear_profile"):
            import shutil
            try:
                if os.path.exists(self.user_profile_dir):
                    self.logger.info("clearing_existing_profile", path=self.user_profile_dir)
                    shutil.rmtree(self.user_profile_dir)
            except Exception as e:
                self.logger.warning("failed_to_clear_profile", error=str(e))

        os.makedirs(self.user_profile_dir, exist_ok=True)
        self.logger.info("persistent_profile_path", path=self.user_profile_dir)

    # ── Driver initialisation ─────────────────────────────────────────────────

    def _init_driver(self, headless: bool = True):
        self.logger.info("initializing_selenium_driver", headless=headless)
        options = Options()

        if headless:
            options.add_argument("--headless=new")

        options.add_argument("--disable-blink-features=AutomationControlled")
        options.add_argument(
            "--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36"
        )
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-setuid-sandbox")
        options.add_argument("--disable-web-security")
        options.add_argument("--disable-features=IsolateOrigins,site-per-process")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--no-zygote")
        options.add_argument("--disable-gpu")
        options.add_argument("--disable-software-rasterizer")
        options.add_argument("--disable-extensions")
        options.add_argument("--disable-background-networking")
        options.add_argument("--disable-default-apps")
        options.add_argument("--disable-translate")
        options.add_argument("--disable-sync")
        options.add_argument("--disable-background-timer-throttling")
        options.add_argument("--disable-backgrounding-occluded-windows")
        options.add_argument("--disable-renderer-backgrounding")
        options.add_argument("--disable-hang-monitor")
        options.add_argument("--metrics-recording-only")
        options.add_argument("--mute-audio")
        options.add_argument("--window-size=1280,720")
        options.add_argument(f"--user-data-dir={self.user_profile_dir}")
        options.add_argument("--profile-directory=Default")
        options.add_argument("--js-flags=--max-old-space-size=512")
        options.add_argument("--disable-popup-blocking")
        options.add_argument("--disable-notifications")
        options.add_experimental_option("excludeSwitches", ["enable-automation"])
        options.add_experimental_option("useAutomationExtension", False)

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
        options.set_capability("goog:loggingPrefs", {"performance": "ALL"})

        chromium_path = "/usr/bin/chromium"
        chromedriver_path = "/usr/bin/chromedriver"

        if os.path.exists(chromium_path) and os.path.exists(chromedriver_path):
            self.logger.info(
                "using_system_chromium_binaries",
                chromium=chromium_path,
                driver=chromedriver_path,
            )
            options.binary_location = chromium_path
            service = Service(chromedriver_path, service_args=["--verbose"])
        else:
            self.logger.info("system_binaries_not_found_falling_back_to_webdriver_manager")
            service = Service(ChromeDriverManager().install(), service_args=["--verbose"])

        try:
            lock_file = os.path.join(self.user_profile_dir, "SingletonLock")
            if os.path.islink(lock_file) or os.path.exists(lock_file):
                self.logger.info("removing_stale_chrome_lock", path=lock_file)
                os.unlink(lock_file)
        except Exception as e:
            self.logger.warning("failed_to_remove_lock_file", error=str(e))

        try:
            self.driver = webdriver.Chrome(service=service, options=options)
        except Exception as e:
            self.logger.error("primary_driver_init_failed_trying_fallback", error=str(e))
            if "--user-data-dir" in str(options.arguments):
                self.logger.warning("retrying_without_persistent_profile")
                new_options = Options()
                for arg in options.arguments:
                    if "--user-data-dir" not in arg:
                        new_options.add_argument(arg)
                self.driver = webdriver.Chrome(service=service, options=new_options)
            else:
                raise

        self.driver.set_page_load_timeout(300)
        self._inject_stealth_scripts()

        try:
            self.driver.maximize_window()
        except Exception:
            pass

        self.logger.info("driver_initialized")

    def quit(self):
        if self.driver:
            try:
                self.driver.quit()
                self.logger.info("driver_quit_successful")
            except Exception as e:
                self.logger.warning("driver_quit_failed", error=str(e))
        self.driver = None

    def _inject_stealth_scripts(self):
        try:
            stealth_js = """
            Object.defineProperty(navigator, 'webdriver', { get: () => false });
            Object.defineProperty(navigator, 'plugins', {
                get: () => [
                    { name: 'Chrome PDF Viewer', filename: 'internal-pdf-viewer' },
                    { name: 'Chromium PDF Viewer', filename: 'internal-pdf-viewer' },
                    { name: 'PDF Viewer', filename: 'internal-pdf-viewer' }
                ],
            });
            Object.defineProperty(navigator, 'deviceMemory', { get: () => 8 });
            Object.defineProperty(navigator, 'hardwareConcurrency', { get: () => 4 });
            Object.defineProperty(navigator, 'languages', { get: () => ['en-US', 'en'] });
            Object.defineProperty(navigator, 'platform', { get: () => 'Win32' });
            const getParameter = WebGLRenderingContext.prototype.getParameter;
            WebGLRenderingContext.prototype.getParameter = function(parameter) {
                if (parameter === 37445) return 'Google Inc. (NVIDIA)';
                if (parameter === 37446) return 'ANGLE (NVIDIA, NVIDIA GeForce RTX 3060 Direct3D11 vs_5_0 ps_5_0, D3D11)';
                return getParameter.apply(this, arguments);
            };
            window.chrome = { runtime: {}, loadTimes: function() {}, csi: function() {}, app: {} };
            const originalQuery = window.navigator.permissions.query;
            window.navigator.permissions.query = (parameters) => (
                parameters.name === 'notifications' ?
                    Promise.resolve({ state: Notification.permission }) :
                    originalQuery(parameters)
            );
            """
            self.driver.execute_cdp_cmd(
                "Page.addScriptToEvaluateOnNewDocument", {"source": stealth_js}
            )
        except Exception as e:
            self.logger.warning("stealth_injection_failed", error=str(e))

    # ── Auth helpers ──────────────────────────────────────────────────────────

    def _load_cookies(self):
        if not self.cookies:
            return False
        try:
            self.driver.get("https://www.facebook.com")
            time.sleep(random.uniform(3, 6))

            cookie_list = (
                self.cookies
                if isinstance(self.cookies, list)
                else [
                    {"name": k, "value": v, "domain": ".facebook.com"}
                    for k, v in self.cookies.items()
                ]
            )

            added_count = 0
            for cookie in cookie_list:
                try:
                    c = {
                        "name": cookie.get("name"),
                        "value": cookie.get("value"),
                        "domain": cookie.get("domain", ".facebook.com"),
                        "path": cookie.get("path", "/"),
                    }
                    if "expiry" in cookie:
                        c["expiry"] = int(cookie["expiry"])
                    elif "expirationDate" in cookie:
                        c["expiry"] = int(cookie["expirationDate"])
                    if "secure" in cookie:
                        c["secure"] = cookie["secure"]
                    self.driver.add_cookie(c)
                    added_count += 1
                    if added_count % 5 == 0:
                        time.sleep(random.uniform(0.1, 0.3))
                except Exception:
                    continue

            self.logger.info("cookies_injected_to_browser", count=added_count)
            time.sleep(random.uniform(1.5, 3))
            self.driver.refresh()
            time.sleep(random.uniform(5, 8))

            if self._is_logged_in():
                self.logger.info("facebook_session_verified_logged_in")
                return True
            else:
                self.logger.warning(
                    "facebook_session_invalid_after_cookie_injection",
                    url=self.driver.current_url,
                    title=self.driver.title,
                )
                return False
        except Exception as e:
            self.logger.error("failed_to_load_cookies", error=str(e))
            return False

    def _is_logged_in(self):
        try:
            current_url = self.driver.current_url.lower()
            if any(x in current_url for x in ["login", "checkpoint", "confirmemail"]):
                return False
            if "home.php" in current_url:
                return True
            indicators = [
                'div[aria-label*="Account"]',
                'div[aria-label*="Your profile"]',
                'a[href*="/me/"]',
                'svg[aria-label="Your profile"]',
                'a[aria-label="Home"]',
                '[role="feed"]',
            ]
            for inc in indicators:
                if self.driver.find_elements(By.CSS_SELECTOR, inc):
                    return True
            for btn_sel in ['button[name="login"]', 'a[href*="/login"]']:
                if self.driver.find_elements(By.CSS_SELECTOR, btn_sel):
                    return False
            return False
        except Exception:
            return False

    def _close_popups(self):
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
                    for el in self.driver.find_elements(By.CSS_SELECTOR, selector):
                        if el.is_displayed():
                            el.click()
                            time.sleep(0.5)
                except Exception:
                    pass
            try:
                ActionChains(self.driver).send_keys(Keys.ESCAPE).perform()
            except Exception:
                pass
        except Exception:
            pass

    def _save_cookies(self):
        try:
            cookies = self.driver.get_cookies()
            if not cookies:
                return None
            if self.user_email:
                manager = UserCredentialManager()
                manager.delete_cookies(self.user_email, "facebook")
                manager.save_cookies(self.user_email, "facebook", cookies)
                self.logger.info("cookies_saved_to_mongodb", user=self.user_email)
            else:
                cookie_file = os.path.join(
                    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
                    "cookies",
                    "facebook_cookies.json",
                )
                os.makedirs(os.path.dirname(cookie_file), exist_ok=True)
                with open(cookie_file, "w") as f:
                    json.dump(cookies, f, indent=2)
            return cookies
        except Exception as e:
            self.logger.error("failed_to_save_cookies", error=str(e))
            return None

    # ── Scrolling ─────────────────────────────────────────────────────────────

    def _scroll_smoothly(self, scroll_count: int = 0):
        try:
            self.driver.execute_script("document.body.focus();")
            self.driver.execute_script(f"window.scrollBy(0, {-random.randint(30, 70)});")
            time.sleep(random.uniform(0.2, 0.4))
            self.driver.execute_script(f"window.scrollBy(0, {random.randint(40, 80)});")
            time.sleep(random.uniform(0.3, 0.6))

            for _ in range(random.randint(2, 4)):
                self.driver.execute_script(f"window.scrollBy(0, {random.randint(400, 1200)});")
                time.sleep(random.uniform(0.7, 1.4))

            actions = ActionChains(self.driver)
            for _ in range(random.randint(1, 3)):
                actions.send_keys(Keys.PAGE_DOWN)
                time.sleep(random.uniform(0.3, 0.7))
            actions.perform()

            self.driver.execute_script("""
                const articles = document.querySelectorAll('div[role="article"]');
                if (articles.length > 0) {
                    articles[articles.length - 1].scrollIntoView({ behavior: 'smooth', block: 'end' });
                } else {
                    window.scrollTo(0, document.body.scrollHeight);
                }
            """)

            if scroll_count % 3 == 0:
                ActionChains(self.driver).send_keys(Keys.END).perform()
                time.sleep(random.uniform(2, 4))

            time.sleep(random.uniform(2.5, 4.5))
        except Exception as e:
            self.logger.debug("scroll_failed", error=str(e))

    # ── GraphQL parsing helpers ───────────────────────────────────────────────

    @staticmethod
    def _deep_find(obj, target_keys: set, results: list, depth: int = 0) -> None:
        if depth > 25:
            return
        if isinstance(obj, dict):
            if target_keys & obj.keys():
                results.append(obj)
            for v in obj.values():
                FacebookScraper._deep_find(v, target_keys, results, depth + 1)
        elif isinstance(obj, list):
            for item in obj:
                FacebookScraper._deep_find(item, target_keys, results, depth + 1)

    @staticmethod
    def _gql_get_text(node: dict) -> str:
        candidates = []
        for key in ("message", "body", "primary_body"):
            val = node.get(key)
            if isinstance(val, dict):
                t = val.get("text", "")
                if t:
                    candidates.append(t)
        comet_story = (
            node.get("comet_sections", {}).get("content", {}).get("story", {})
        )
        if isinstance(comet_story, dict):
            msg = comet_story.get("message")
            if isinstance(msg, dict):
                t = msg.get("text", "")
                if t:
                    candidates.append(t)
        valid = [c for c in candidates if c and len(c.strip()) > 20]
        return max(valid, key=len).strip() if valid else ""

    @staticmethod
    def _gql_get_author(node: dict) -> str:
        actors = node.get("actors") or []
        if actors and isinstance(actors, list):
            first = actors[0]
            if isinstance(first, dict):
                return first.get("name", "Unknown")
        actor = node.get("actor")
        if isinstance(actor, dict):
            return actor.get("name", "Unknown")
        return "Unknown"

    @staticmethod
    def _gql_get_url(node: dict, post_id: str) -> str:
        for key in ("wwwURL", "url", "permalink_url"):
            val = node.get(key, "")
            if val and isinstance(val, str) and val.startswith("http"):
                return val
        if post_id and post_id.isdigit():
            return f"https://www.facebook.com/permalink.php?story_fbid={post_id}"
        return ""

    @staticmethod
    def _gql_get_post_id(node: dict) -> str:
        for key in ("post_id", "story_fbid", "id"):
            val = node.get(key)
            if val and isinstance(val, str):
                return val
        return ""

    @staticmethod
    def _gql_get_timestamp(node: dict) -> str:
        for key in ("creation_time", "created_time", "publish_time"):
            ts = node.get(key)
            if ts:
                try:
                    return datetime.utcfromtimestamp(int(ts)).strftime(
                        "%Y-%m-%d %H:%M:%S UTC"
                    )
                except Exception:
                    pass
        return ""

    def _extract_posts_from_graphql(self, raw_bodies: list) -> list:
        posts = []
        seen_ids: set = set()
        seen_txt: set = set()

        story_keys = {
            "message", "actors", "actor", "wwwURL", "story_fbid",
            "creation_time", "body", "comet_sections",
        }

        for body in raw_bodies:
            for line in body.splitlines():
                line = line.strip()
                if not line:
                    continue
                try:
                    data = json.loads(line)
                except json.JSONDecodeError:
                    continue

                candidates: list = []
                self._deep_find(data, story_keys, candidates)

                for node in candidates:
                    text = self._gql_get_text(node)
                    if not text or len(text) < 20:
                        continue

                    post_id = self._gql_get_post_id(node)

                    if post_id and post_id in seen_ids:
                        continue
                    txt_sig = text[:200]
                    if txt_sig in seen_txt:
                        continue
                    if post_id:
                        seen_ids.add(post_id)
                    seen_txt.add(txt_sig)

                    url = self._gql_get_url(node, post_id)
                    posts.append({
                        "id": post_id,
                        "title": text.split("\n")[0][:100],
                        "text": text,
                        "post_date": self._gql_get_timestamp(node),
                        "link": url,
                        "images": [],
                        "image_count": 0,
                        "video_count": 0,
                        "has_media": False,
                        "word_count": len(text.split()),
                        "scraped_at": datetime.utcnow().isoformat(),
                        "author_name": self._gql_get_author(node),
                        "author_url": None,
                    })

        self.logger.info("graphql_posts_parsed", count=len(posts))
        return posts

    # ── Lead pipeline ─────────────────────────────────────────────────────────

    def _run_lead_pipeline(self, raw_posts: list, stats: dict) -> list:
        """
        Apply the full 3-gate lead pipeline using the centralized BuyerIntentDetector:
          Gate 1 — buyer intent present AND not a promo/ad/hiring post (includes Ollama AI check)
          Gate 2 — US location detected
          Gate 3 — intent score >= MIN_SCORE

        Returns a list of dicts ready to be turned into FacebookLead objects.
        """
        qualified = []

        for raw in raw_posts:
            content = raw.get("text", "")

            # Gate 1: buyer intent + not a promo + Ollama check
            if not BuyerIntentDetector.is_buyer_request(content):
                stats["excluded_non_buyer"] += 1
                continue

            # Gate 2: US-only
            is_us, location = is_us_location(content)
            if not is_us:
                stats["excluded_non_us"] += 1
                continue

            # Gate 3: score threshold
            score = score_lead(content)
            if score < MIN_SCORE:
                stats["excluded_low_score"] += 1
                continue

            stats.setdefault("qualified", 0)
            stats["qualified"] += 1
            category = classify_category(content)

            qualified.append({
                **raw,
                "location": location,
                "intent_score": score,
                "category": category,
                "is_buyer_request": True,
            })

        # Highest intent first
        qualified.sort(key=lambda x: x.get("intent_score", 0), reverse=True)
        return qualified

    def _raw_to_lead(self, raw: dict) -> Optional[FacebookLead]:
        """Convert a pipeline-qualified raw dict to a FacebookLead model."""
        try:
            return FacebookLead(
                source_url=raw.get("link"),
                source_id=raw.get("id"),
                title=raw.get("title"),
                description=raw.get("text"),
                posted_date=raw.get("post_date") or None,
                author_name=raw.get("author_name"),
                author_url=raw.get("author_url"),
                location=raw.get("location"),
                category=raw.get("category"),
                intent_score=raw.get("intent_score"),
                images=raw.get("images", []),
                videos=raw.get("videos", []),
                image_count=raw.get("image_count", 0),
                video_count=raw.get("video_count", 0),
                has_media=raw.get("has_media", False),
                word_count=raw.get("word_count", 0),
                is_buyer_request=raw.get("is_buyer_request", True),
                extra_data={
                    "raw_date": raw.get("post_date"),
                    "scraped_at": raw.get("scraped_at"),
                },
            )
        except Exception as e:
            self.logger.warning("failed_to_create_facebook_lead", error=str(e))
            return None

    # ── Scroll + CDP capture for a single URL ─────────────────────────────────

    def _capture_graphql_for_url(
        self, url: str, scroll_rounds: int, seen_req_ids: set
    ) -> list:
        """
        Navigate to *url*, scroll to trigger GraphQL calls, and return
        the list of captured response body strings for this URL.
        Reuses *seen_req_ids* across calls so duplicate CDP request IDs
        are never double-fetched across URLs in the same browser session.
        """
        graphql_bodies: list = []

        try:
            self.logger.info("navigating_to_search_url", url=url)
            self.driver.get(url)
            time.sleep(random.uniform(6, 10))

            current_url = self.driver.current_url
            if "login" in current_url or "checkpoint" in current_url:
                self.logger.warning("login_wall_detected_skipping_url", url=current_url)
                return graphql_bodies

            self._close_popups()

            last_height = self.driver.execute_script("return document.body.scrollHeight")
            no_change_count = 0

            for i in range(scroll_rounds):
                self.logger.info(
                    "scroll_iteration", scroll=i + 1, total=scroll_rounds, url=url
                )
                self._scroll_smoothly(scroll_count=i)
                time.sleep(2.5)

                # ── Poll CDP performance log ──────────────────────────────
                try:
                    perf_logs = self.driver.get_log("performance")
                    for entry in perf_logs:
                        try:
                            msg = json.loads(entry.get("message", "{}"))
                            params = msg.get("message", {}).get("params", {})
                            req_id = params.get("requestId", "")
                            url_check = (
                                params.get("response", {}).get("url", "")
                                or params.get("request", {}).get("url", "")
                            )
                            if "api/graphql" not in url_check:
                                continue
                            if req_id in seen_req_ids:
                                continue
                            seen_req_ids.add(req_id)

                            try:
                                resp = self.driver.execute_cdp_cmd(
                                    "Network.getResponseBody", {"requestId": req_id}
                                )
                                body = resp.get("body", "")
                                if body and len(body) > 20:
                                    graphql_bodies.append(body)
                                    self.logger.debug(
                                        "graphql_body_captured",
                                        req_id=req_id,
                                        size=len(body),
                                    )
                            except Exception:
                                pass
                        except Exception:
                            continue
                except Exception as perf_err:
                    self.logger.debug("perf_log_fetch_failed", error=str(perf_err))

                new_height = self.driver.execute_script("return document.body.scrollHeight")
                if new_height <= last_height:
                    no_change_count += 1
                    if no_change_count >= 4:
                        self.logger.info(
                            "no_scroll_progress_stopping_url_early", iteration=i
                        )
                        break
                else:
                    no_change_count = 0
                    last_height = new_height

        except Exception as e:
            self.logger.error("capture_failed_for_url", url=url, error=str(e))

        self.logger.info(
            "graphql_bodies_for_url",
            url=url,
            bodies=len(graphql_bodies),
        )
        return graphql_bodies

    # ── Main scrape method ────────────────────────────────────────────────────

    def scrape(self, target: Optional[str] = None, **kwargs) -> List[ScrapedLead]:
        """
        Main entry point.

        Parameters
        ──────────
        search_urls : list[str]
            Facebook search URLs to scrape (loaded from MongoDB by the caller).
            If not supplied, falls back to *target* as a single URL.
        limit       : int
            Max qualified leads to collect across all URLs (-1 = unlimited).
        scroll_rounds : int
            Scroll iterations per URL (default 6).
        headless    : bool
            Override headless setting for this run.
        email / password : str
            Fallback credentials if cookie auth fails.
        """
        # ── Resolve search URLs ───────────────────────────────────────────────
        search_urls: list = kwargs.get("search_urls") or []
        if not search_urls and target:
            search_urls = [target]
        if not search_urls:
            self.logger.error("no_search_urls_provided")
            return []

        limit = kwargs.get("limit", 15)
        target_leads = 999_999 if limit == -1 else (limit if limit and limit > 0 else 999_999)
        scroll_rounds = kwargs.get("scroll_rounds", 6)
        headless = kwargs.get("headless", self.headless_default)
        email = kwargs.get("email") or os.getenv("FACEBOOK_EMAIL")
        password = kwargs.get("password") or os.getenv("FACEBOOK_PASSWORD")

        self.logger.info(
            "starting_scrape",
            urls=len(search_urls),
            limit=target_leads,
            scroll_rounds=scroll_rounds,
        )

        # ── Pipeline stats ────────────────────────────────────────────────────
        stats: dict = defaultdict(int)
        all_leads: List[ScrapedLead] = []
        global_seen: set = set()       # dedup across all URLs
        seen_req_ids: set = set()      # dedup CDP request IDs across URLs

        try:
            self._init_driver(headless=headless)

            # Enable CDP network capture once for the whole session
            try:
                self.driver.execute_cdp_cmd("Network.enable", {})
                self.logger.info("cdp_network_enabled")
            except Exception as e:
                self.logger.warning("cdp_network_enable_failed", error=str(e))

            # ── Auth ──────────────────────────────────────────────────────────
            session_ok = self._load_cookies()

            if not session_ok and self.cookies and self.user_email:
                self.logger.warning(
                    "facebook_cookies_expired_removing_stale_record",
                    user=self.user_email,
                )
                UserCredentialManager().delete_cookies(self.user_email, "facebook")

            if not session_ok and email and password:
                self.logger.info("attempting_login_with_credentials")
                session_ok = self.login(email, password)

            if not session_ok:
                self.logger.error("failed_to_establish_authenticated_session")
                raise ValueError(
                    "Facebook authentication failed. Please update credentials or cookies."
                )

            # ── Iterate over every search URL ─────────────────────────────────
            for url_idx, search_url in enumerate(search_urls, start=1):
                if len(all_leads) >= target_leads:
                    self.logger.info(
                        "lead_limit_reached_stopping_url_loop",
                        collected=len(all_leads),
                    )
                    break

                self.logger.info(
                    "processing_search_url",
                    index=url_idx,
                    total=len(search_urls),
                    url=search_url,
                )

                # Capture raw GraphQL bodies for this URL
                raw_bodies = self._capture_graphql_for_url(
                    search_url, scroll_rounds, seen_req_ids
                )
                stats["total_graphql_bodies"] += len(raw_bodies)

                # Parse bodies → raw post dicts
                raw_posts = self._extract_posts_from_graphql(raw_bodies)
                stats["total_raw_posts"] += len(raw_posts)
                self.logger.info(
                    "raw_posts_for_url",
                    url=search_url,
                    count=len(raw_posts),
                )

                # Apply full lead pipeline (buyer intent + US filter + scoring)
                qualified = self._run_lead_pipeline(raw_posts, stats)

                # Global dedup + convert to leads
                new_this_url = 0
                for raw in qualified:
                    if len(all_leads) >= target_leads:
                        break

                    dedup_key = raw.get("id") or raw.get("text", "")[:200]
                    if dedup_key in global_seen:
                        continue
                    global_seen.add(dedup_key)

                    lead = self._raw_to_lead(raw)
                    if lead:
                        all_leads.append(lead)
                        new_this_url += 1

                self.logger.info(
                    "new_leads_from_url",
                    url=search_url,
                    new=new_this_url,
                    total_so_far=len(all_leads),
                )

                # Brief pause between URLs to avoid rate-limiting
                if url_idx < len(search_urls):
                    time.sleep(random.uniform(4, 8))

            # ── Summary ───────────────────────────────────────────────────────
            urgent = sum(1 for l in all_leads if getattr(l, "intent_score", 0) == 5)
            per_cat: dict = defaultdict(int)
            for l in all_leads:
                per_cat[getattr(l, "category", "other")] += 1

            self.logger.info(
                "scrape_complete",
                urls_processed=url_idx if search_urls else 0,
                total_graphql_bodies=stats["total_graphql_bodies"],
                total_raw_posts=stats["total_raw_posts"],
                excluded_non_buyer=stats["excluded_non_buyer"],
                excluded_non_us=stats["excluded_non_us"],
                excluded_low_score=stats["excluded_low_score"],
                qualified_leads=len(all_leads),
                urgent_leads=urgent,
                per_category=dict(per_cat),
            )

        except Exception as e:
            err_str = str(e).lower()
            if any(sig in err_str for sig in ["tab crashed", "no such session", "invalid session"]):
                self.logger.warning(
                    "chrome_tab_crashed_returning_partial_results",
                    collected=len(all_leads),
                    error=str(e),
                )
            else:
                self.logger.error("scraping_failed", error=str(e))
                traceback.print_exc()
                raise
        finally:
            self.quit()

        return all_leads

    # ── login / captcha helpers (unchanged from previous version) ─────────────

    def login(self, email, password):
        """Login to Facebook with credentials and handle security checkpoints."""
        self.logger.info("logging_in_to_facebook")
        try:
            self.driver.get("https://www.facebook.com/")
            time.sleep(5)
            if self._is_logged_in():
                self.logger.info("already_logged_in_skipping_credentials_entry")
                return True

            self.driver.get("https://www.facebook.com/login")
            time.sleep(5)

            self._handle_cookie_banners()

            if not self._fill_credentials(email, password):
                return False

            start_time = time.time()
            max_wait = 150

            while time.time() - start_time < max_wait:
                if self._is_logged_in():
                    self.logger.info("login_successful_verified")
                    self._save_cookies()
                    return True

                if self._is_captcha_present():
                    self._try_solve_captcha()
                    time.sleep(8)
                    continue

                # OTP handling
                otp_input = None
                for sel in [
                    'input[name="approvals_code"]',
                    'input[id="approvals_code"]',
                    'input[placeholder*="Code"]',
                    'input#code',
                ]:
                    try:
                        el = self.driver.find_element(By.CSS_SELECTOR, sel)
                        if el.is_displayed():
                            otp_input = el
                            break
                    except Exception:
                        continue

                if otp_input:
                    fa_secret = os.getenv("FACEBOOK_2FA_SECRET")
                    if fa_secret:
                        try:
                            import pyotp
                            code = pyotp.TOTP(fa_secret.replace(" ", "")).now()
                            otp_input.clear()
                            otp_input.send_keys(code)
                        except Exception as e:
                            self.logger.error("totp_generation_failed", error=str(e))
                    elif EmailManager:
                        email_user = os.getenv("FACEBOOK_EMAIL")
                        app_pass = os.getenv("FACEBOOK_APP_PASSWORD")
                        if email_user and app_pass:
                            code = EmailManager.get_facebook_otp(email_user, app_pass)
                            if code:
                                otp_input.clear()
                                for char in code:
                                    otp_input.send_keys(char)
                                    time.sleep(random.uniform(0.1, 0.3))

                # Continue / Next buttons
                button_clicked = False
                for sel in [
                    'button[type="submit"]',
                    'button#checkpointSubmitButton',
                    '//button[contains(., "Continue")]',
                    '//button[contains(., "Next")]',
                    '//button[contains(., "This was me")]',
                    '//button[contains(., "Confirm")]',
                ]:
                    try:
                        btn = (
                            self.driver.find_element(By.XPATH, sel)
                            if sel.startswith("//")
                            else self.driver.find_element(By.CSS_SELECTOR, sel)
                        )
                        if btn.is_displayed() and btn.is_enabled():
                            self.driver.execute_script(
                                "arguments[0].scrollIntoView({block:'center'});", btn
                            )
                            time.sleep(1)
                            self.driver.execute_script("arguments[0].click();", btn)
                            button_clicked = True
                            time.sleep(10)
                            break
                    except Exception:
                        continue

                if not button_clicked:
                    time.sleep(8)

            self.logger.error("login_timed_out", url=self.driver.current_url)
            return False

        except Exception as e:
            self.logger.error("login_exception", error=str(e))
            try:
                self.driver.save_screenshot("/tmp/fb_login_crash.png")
            except Exception:
                pass
            return False

    def _handle_cookie_banners(self):
        for xpath in [
            "//button[contains(., 'Allow all cookies')]",
            "//button[contains(., 'Accept All')]",
            "//button[contains(., 'Only allow essential cookies')]",
        ]:
            try:
                btns = self.driver.find_elements(By.XPATH, xpath)
                if btns:
                    self.driver.execute_script("arguments[0].scrollIntoView(true);", btns[0])
                    time.sleep(0.5)
                    try:
                        btns[0].click()
                    except Exception:
                        self.driver.execute_script("arguments[0].click();", btns[0])
                    time.sleep(2)
                    break
            except Exception:
                continue

    def _fill_credentials(self, email, password, retry_count=0):
        if retry_count > 3:
            return False
        try:
            email_field = None
            for selector in [
                'input[name="email"]',
                '#email',
                'input[type="text"]',
                'input[placeholder*="Email"]',
            ]:
                try:
                    email_field = WebDriverWait(self.driver, 10).until(
                        EC.presence_of_element_located((By.CSS_SELECTOR, selector))
                    )
                    if email_field.is_displayed():
                        break
                except Exception:
                    continue

            if not email_field:
                raise ValueError(f"Email field not found on {self.driver.current_url}")

            self.driver.execute_script("arguments[0].focus();", email_field)
            self.driver.execute_script("arguments[0].value = '';", email_field)
            time.sleep(0.5)
            for char in email:
                email_field.send_keys(char)
                time.sleep(random.uniform(0.04, 0.12))

            password_field = None
            for selector in ['input[name="pass"]', '#pass', 'input[type="password"]']:
                try:
                    password_field = self.driver.find_element(By.CSS_SELECTOR, selector)
                    if password_field.is_displayed():
                        break
                except Exception:
                    continue

            if not password_field:
                raise ValueError("Password field not found.")

            self.driver.execute_script("arguments[0].focus();", password_field)
            self.driver.execute_script("arguments[0].value = '';", password_field)
            time.sleep(0.5)
            for char in password:
                password_field.send_keys(char)
                time.sleep(random.uniform(0.04, 0.12))

            login_btn = None
            for selector in [
                'button[name="login"]',
                'button[type="submit"]',
                'input[type="submit"]',
                '[data-testid="royal_login_button"]',
                '[aria-label="Log In"]',
                '[aria-label="Log in"]',
            ]:
                try:
                    el = self.driver.find_element(By.CSS_SELECTOR, selector)
                    if el.is_displayed():
                        login_btn = el
                        break
                except Exception:
                    continue

            if not login_btn:
                for xpath in [
                    "//button[contains(., 'Log In')]",
                    "//button[contains(., 'Log in')]",
                    "//button[contains(., 'Entrar')]",
                    "//input[@type='submit']",
                ]:
                    try:
                        el = self.driver.find_element(By.XPATH, xpath)
                        if el.is_displayed():
                            login_btn = el
                            break
                    except Exception:
                        continue

            if not login_btn:
                # Last resort — JS-click the first visible submit-like element
                try:
                    self.driver.execute_script("""
                        const btn = Array.from(
                            document.querySelectorAll('button,input[type=submit]')
                        ).find(el => el.offsetParent !== null);
                        if (btn) btn.click();
                    """)
                    self.logger.warning("login_btn_not_found_used_js_fallback")
                    return True
                except Exception:
                    raise ValueError("Login button not found.")

            try:
                WebDriverWait(self.driver, 5).until(EC.element_to_be_clickable(login_btn))
                login_btn.click()
            except Exception:
                self.driver.execute_script("arguments[0].click();", login_btn)

            return True
        except Exception as e:
            self.logger.error("credential_fill_failed", error=str(e))
            return False

    def _is_captcha_present(self):
        try:
            current_url = self.driver.current_url.lower()
            if any(x in current_url for x in ["checkpoint", "challenge", "captcha"]):
                return True
            for iframe in self.driver.find_elements(By.TAG_NAME, "iframe"):
                try:
                    src = iframe.get_attribute("src") or ""
                    if any(x in src.lower() for x in ["recaptcha", "captcha", "hcaptcha", "arkoselabs"]):
                        return True
                except Exception:
                    continue
            for selector in [
                'img[src*="captcha"]',
                'input[name="captcha_response"]',
                ".g-recaptcha",
                "#recaptcha",
            ]:
                if self.driver.find_elements(By.CSS_SELECTOR, selector):
                    return True
            return False
        except Exception:
            return False

    def _try_solve_captcha(self):
        api_key = os.getenv("TWO_CAPTCHA_API_KEY")
        if not api_key:
            self.logger.error("captcha_solver_missing_api_key")
            return False
        try:
            from twocaptcha import TwoCaptcha
            solver = TwoCaptcha(api_key)
            site_key = None
            try:
                iframes = self.driver.find_elements(
                    By.CSS_SELECTOR, 'iframe[src*="recaptcha/api2/anchor"]'
                )
                if iframes:
                    src = iframes[0].get_attribute("src")
                    match = re.search(r"k=([^&]+)", src)
                    if match:
                        site_key = match.group(1)
            except Exception:
                pass

            if site_key:
                result = solver.recaptcha(sitekey=site_key, url=self.driver.current_url)
                code = result["code"]
                self.driver.execute_script(f"""
                    document.querySelectorAll('[id^="g-recaptcha-response"]').forEach(f => {{
                        f.innerHTML = "{code}";
                        f.value = "{code}";
                        f.style.display = 'block';
                    }});
                """)
                time.sleep(5)
                return True
            return False
        except Exception as e:
            self.logger.error("captcha_solver_error", error=str(e))
            return False

    # ── Legacy parse_item kept for compatibility ──────────────────────────────

    def parse_item(
        self,
        raw_data: Dict[str, Any],
        custom_keywords: Optional[str] = None,
        exclude_keywords: Optional[list] = None,
        custom_indicators: Optional[list] = None,
    ) -> Optional[FacebookLead]:
        """Legacy parse path — still available for callers that use it directly."""
        try:
            text = f"{raw_data.get('title', '')} {raw_data.get('text', '')}"
            is_buyer = _is_valid_lead(text)
            is_us, location = _is_us_location(text)
            if not is_us:
                is_buyer = False
            score = _score_lead(text)
            category = _classify_category(text)

            return FacebookLead(
                source_url=raw_data.get("link"),
                source_id=raw_data.get("id"),
                title=raw_data.get("title"),
                description=raw_data.get("text"),
                posted_date=raw_data.get("post_date") or None,
                author_name=raw_data.get("author_name"),
                author_url=raw_data.get("author_url"),
                location=location if is_us else None,
                category=category,
                intent_score=score,
                images=raw_data.get("images", []),
                videos=raw_data.get("videos", []),
                image_count=raw_data.get("image_count", 0),
                video_count=raw_data.get("video_count", 0),
                has_media=raw_data.get("has_media", False),
                word_count=raw_data.get("word_count", 0),
                is_buyer_request=is_buyer,
                extra_data={
                    "raw_date": raw_data.get("post_date"),
                    "scraped_at": raw_data.get("scraped_at"),
                },
            )
        except Exception as e:
            self.logger.warning("failed_to_create_facebook_lead", error=str(e))
            return None

