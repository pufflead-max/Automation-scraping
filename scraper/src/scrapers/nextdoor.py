"""Nextdoor scraper implementation."""

from typing import List, Dict, Any, Optional
from datetime import datetime
import os
from playwright.sync_api import sync_playwright

from .base import BaseScraper
try:
    from ..models import NextdoorLead, ScrapedLead
except ImportError:
    from models import NextdoorLead, ScrapedLead


class NextdoorScraper(BaseScraper):
    """Scraper for Nextdoor service posts using Playwright."""
    
    def __init__(self, cookies: Optional[Dict[str, str]] = None, **kwargs):
        super().__init__("nextdoor", **kwargs)
        self.cookies = cookies or {}
        
        # Load cookie file if path provided
        if isinstance(self.cookies, str) and os.path.exists(self.cookies):
            import json
            with open(self.cookies, 'r') as f:
                self.cookies = json.load(f)
        
        # If no cookies passed, try to load from default location
        if not self.cookies:
            import json
            project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
            cookie_path = os.path.join(project_root, 'cookies', 'nextdoor_cookies.json')
            if os.path.exists(cookie_path):
                try:
                    with open(cookie_path, 'r') as f:
                        self.cookies = json.load(f)
                    self.logger.info("loaded_cookies_from_file", path=cookie_path)
                except Exception as e:
                    self.logger.warning("failed_to_load_cookie_file", error=str(e))
    
    def parse_post(self, post_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Parse a single post from the feed."""
        try:
            if post_data.get('feedItemType') != 'POST':
                return None
            
            post = post_data.get('post', {})
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
    
    def parse_item(self, raw_data: Dict[str, Any]) -> Optional[NextdoorLead]:
        """Parse raw data into a NextdoorLead model."""
        try:
            text = f"{raw_data.get('title', '')} {raw_data.get('description', '') or raw_data.get('body', '')}".lower()
            
            high_intent = ["looking for", "need ", "needs ", "in search of", "iso ", "anyone available",
                          "can someone", "help needed", "help wanted", "urgent", "emergency", "asap",
                          "today", "tomorrow", "this week", "available near me", "recommendation for", "quote needed"]
            
            negative = ["free estimate", "i offer", "we offer", "we do", "contact me", "contact us",
                       "call me", "call us", "my number is", "years experience", "services offered",
                       "fully insured", "licensed", "discount", "promotion", "book now",
                       "who do you recommend", "who do you use", "best plumber", "best electrician",
                       "thoughts on", "anyone know if", "has anyone used", "reviews for",
                       "shout out", "wanted to share", "highly recommend", "i recommend",
                       "cannot recommend", "huge thanks", "excellent work", "great job"]
            
            is_service_request = (any(k in text for k in high_intent) and 
                                not any(k in text for k in negative) and 
                                bool(raw_data.get('url')))
            
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

    def scrape(self, target: str = None, **kwargs) -> List[ScrapedLead]:
        """Main scraping method using Playwright."""
        if not self.cookies:
            self.logger.error("nextdoor_cookies_required")
            raise ValueError("Nextdoor cookies not configured.")
        
        max_pages = kwargs.get('max_pages', 5)
        collected_posts = {}
        
        with sync_playwright() as p:
            launch_args = {"headless": True}
            if chrome_bin := os.getenv("CHROME_BIN"):
                launch_args.update({"executable_path": chrome_bin, "args": ["--no-sandbox", "--disable-dev-shm-usage"]})
            
            browser = p.chromium.launch(**launch_args)
            context = browser.new_context(
                viewport={'width': 1280, 'height': 800},
                user_agent='Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
            )
            
            cookie_list = []
            if isinstance(self.cookies, list):
                for c in self.cookies:
                    curr = {'name': c.get('name'), 'value': c.get('value'),
                           'domain': c.get('domain', '.nextdoor.com'), 'path': c.get('path', '/')}
                    if 'expirationDate' in c: curr['expires'] = c['expirationDate']
                    if 'secure' in c: curr['secure'] = c['secure']
                    if 'httpOnly' in c: curr['httpOnly'] = c['httpOnly']
                    if 'sameSite' in c:
                        ss = {'lax': 'Lax', 'strict': 'Strict', 'no_restriction': 'None', 'none': 'None'}.get(c['sameSite'].lower())
                        if ss: curr['sameSite'] = ss
                    cookie_list.append(curr)
            else:
                cookie_list = [{'name': k, 'value': v, 'domain': '.nextdoor.com', 'path': '/'} 
                              for k, v in self.cookies.items()]
            
            context.add_cookies(cookie_list)
            page = context.new_page()
            
            def handle_response(response):
                try:
                    if "PersonalizedFeed" in response.url and response.status == 200:
                        for item in response.json().get('data', {}).get('me', {}).get('personalizedFeed', {}).get('feedItems', []):
                            if (parsed := self.parse_post(item)) and parsed.get('post_id'):
                                collected_posts[parsed['post_id']] = parsed
                except Exception:
                    pass
            
            page.on("response", handle_response)
            
            try:
                self.logger.info("navigating_to_feed")
                page.goto("https://nextdoor.com/news_feed/", timeout=90000)
                try:
                    page.wait_for_load_state("domcontentloaded", timeout=60000)
                except:
                    pass
                page.wait_for_timeout(5000)
                
                previous_height = 0
                for i in range(max_pages):
                    self.logger.info(f"scrolling_page_{i+1}")
                    page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                    
                    try:
                        page.wait_for_timeout(4000)
                        if "login" in page.url or "signup" in page.url:
                            self.logger.error("session_invalid_redirected_to_login")
                            break
                        
                        for btn_text in ["See more", "Load more", "Show more"]:
                            if (buttons := page.get_by_role("button", name=btn_text)).count() > 0 and buttons.first.is_visible():
                                self.logger.info(f"clicking_{btn_text.lower().replace(' ', '_')}_button")
                                buttons.first.click()
                                page.wait_for_timeout(2000)
                                break
                        
                        current_height = page.evaluate("document.body.scrollHeight")
                        if current_height == previous_height:
                            self.logger.info("no_height_change_detected")
                            page.keyboard.press("End")
                            page.wait_for_timeout(2000)
                        previous_height = current_height
                    except Exception as e:
                        self.logger.warning("scroll_iteration_error", error=str(e))
                
                self.logger.info("scrolling_complete", gathered=len(collected_posts))
                
                # Save cookies if session was successful
                if len(collected_posts) > 0:
                    self._save_cookies(context.cookies())
                    
            except Exception as e:
                self.logger.error("playwright_execution_failed", error=str(e))
            finally:
                browser.close()
        
        return [lead for post_data in collected_posts.values() if (lead := self.parse_item(post_data))]

    def _save_cookies(self, cookies):
        """Save current cookies back to the file."""
        import json
        try:
            project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
            cookie_dir = os.path.join(project_root, 'cookies')
            cookie_path = os.path.join(cookie_dir, 'nextdoor_cookies.json')
            
            # Use /tmp if project directory is read-only
            if not os.access(os.path.dirname(project_root), os.W_OK):
                cookie_path = '/tmp/nextdoor_cookies.json'
                
            os.makedirs(os.path.dirname(cookie_path), exist_ok=True)
            with open(cookie_path, 'w', encoding='utf-8') as f:
                json.dump(cookies, f, ensure_ascii=False, indent=2)
            self.logger.info("cookies_saved", path=cookie_path)
        except Exception as e:
            self.logger.warning("failed_to_save_cookies", error=str(e))
