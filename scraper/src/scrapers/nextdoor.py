"""Nextdoor scraper implementation."""

from typing import List, Dict, Any, Optional
from datetime import datetime
import os
import re
from playwright.sync_api import sync_playwright

from .base import BaseScraper
try:
    from ..models import NextdoorLead, ScrapedLead
    from ..utils.buyer_intent import BuyerIntentDetector
    from ..user_credential_manager import UserCredentialManager
except ImportError:
    from models import NextdoorLead, ScrapedLead
    from utils.buyer_intent import BuyerIntentDetector
    from user_credential_manager import UserCredentialManager


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
        
        if self.cookies:
            self.logger.info("using_provided_cookies", source="argument_or_variable", count=len(self.cookies) if isinstance(self.cookies, list) else "dict")
        else:
            self.logger.warning("no_cookies_provided_scraper_will_likely_fail")
    
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
            
            # Log detection reason for debugging
            if not is_service_request:
                reason = BuyerIntentDetector.get_detection_reason(text, raw_data.get('url'))
                self.logger.debug("filtered_non_buyer_post", reason=reason, title=raw_data.get('title'))
            
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
        
        # Normalize URL: Handle common formatting issues like em-dashes or single hyphens in city URLs
        if target:
            original_target = target
            # Replace em-dash (—) or en-dash (–) with double hyphen (--)
            target = target.replace('—', '--').replace('–', '--')
            
            # Handle city URLs normalization
            city_match = re.search(r'nextdoor\.com/city/([a-z-]+)-([a-z]{2})/?$', target)
            if city_match and '--' not in target:
                target = target.replace(f"{city_match.group(1)}-{city_match.group(2)}", f"{city_match.group(1)}--{city_match.group(2)}")
            
            # Handle neighborhood URLs normalization
            # Pattern: nextdoor.com/neighborhood/name--city--state/
            nb_match = re.search(r'nextdoor\.com/neighborhood/([a-z0-9-]+)/?$', target)
            if nb_match:
                name_part = nb_match.group(1)
                # If it contains single hyphens but no double hyphens, and looks like name-city-state
                if '-' in name_part and '--' not in name_part:
                    # Very basic heuristic: if it has at least 2 hyphens, try to fix it
                    parts = name_part.split('-')
                    if len(parts) >= 3:
                        # Re-join with double hyphens
                        # Note: This is an estimate, usually it's {neighborhood}--{city}--{state}
                        # If neighborhood or city have spaces/hyphens originally, this might be tricky,
                        # but usually Nextdoor uses double hyphens as the primary delimiter.
                        # We'll just replace all single with double for safety if they are missing.
                        target = target.replace(name_part, name_part.replace('-', '--'))

            if target != original_target:
                self.logger.info("normalized_nextdoor_url", original=original_target, normalized=target)

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
                    elif 'expires' in c: curr['expires'] = c['expires']
                    elif 'expiry' in c: curr['expires'] = c['expiry']
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
                self.target_url = target if target else "https://nextdoor.com/news_feed/"
                self.logger.info(f"Navigating to {self.target_url}", extra={"scraper": self.name, "target": self.target_url})
                page.goto(self.target_url, wait_until="domcontentloaded", timeout=60000)
                page.wait_for_timeout(5000)

                # Check if we are actually logged in
                # Use .first() to avoid strict mode violation if multiple Log in buttons exist
                login_button = page.get_by_role("button", name=re.compile("Log in", re.IGNORECASE)).first
                
                # Check for specific session cookies
                browser_cookies = context.cookies()
                has_session = any(c['name'] == 'ndbr_at' for c in browser_cookies)
                
                if login_button.is_visible() or not has_session:
                    self.logger.error("NOT LOGGED IN: Redirected to login page or missing session cookie", 
                                     extra={"scraper": self.name, "has_session_cookie": has_session})
                    if self.user_email:
                        self.logger.warning("nextdoor_cookies_expired_removing_stale_record", user=self.user_email)
                        UserCredentialManager().delete_cookies(self.user_email, 'nextdoor')
                    raise ValueError("Nextdoor session invalid. Cookie rotation required.")
                
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
                    
            except Exception as e:
                self.logger.error("playwright_execution_failed", error=str(e))
            finally:
                browser.close()
        
        return [lead for post_data in collected_posts.values() 
                if (lead := self.parse_item(post_data, 
                                            custom_keywords=kwargs.get('keywords'),
                                            exclude_keywords=kwargs.get('exclude_keywords'),
                                            custom_indicators=kwargs.get('custom_indicators')))]

