"""
Nextdoor scraper implementation.
Extracts service leads from Nextdoor using Playwright to intercept GraphQL traffic.
"""

from typing import List, Dict, Any, Optional
from datetime import datetime
import time
import json
from playwright.sync_api import sync_playwright

from .base import BaseScraper
try:
    from ..models import NextdoorLead, ScrapedLead
    from ..logger import ScraperLogger
except ImportError:
    from models import NextdoorLead, ScrapedLead
    from logger import ScraperLogger


class NextdoorScraper(BaseScraper):
    """
    Scraper for Nextdoor service posts.
    Uses Playwright to automate the browser and intercept GraphQL API calls.
    """
    
    def __init__(self, cookies: Optional[Dict[str, str]] = None, **kwargs):
        """
        Initialize Nextdoor scraper.
        
        Args:
            cookies: Nextdoor session cookies (required for authentication)
            **kwargs: Additional arguments passed to BaseScraper
        """
        super().__init__("nextdoor", **kwargs)
        self.cookies = cookies or {}
    
    def parse_post(self, post_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        Parse a single post from the feed.
        """
        try:
            # Skip if not a POST type
            if post_data.get('feedItemType') != 'POST':
                return None
            
            post = post_data.get('post', {})
            
            # Extract basic info
            post_id = post.get('legacyPostId') or post.get('id')
            title = post.get('subject', '')
            body = post.get('body', '')
            
            # Extract author info
            author = post.get('author', {})
            author_name = author.get('displayName')
            author_url = f"https://nextdoor.com/profile/{author.get('id')}" if author.get('id') else None
            
            # Extract neighborhood
            neighborhood_data = author.get('originationNeighborhood', {})
            neighborhood = neighborhood_data.get('shortName')
            city = neighborhood_data.get('city')
            state = neighborhood_data.get('state')
            
            # Extract timestamps
            created_at = post.get('createdAt', {})
            posted_timestamp = created_at.get('epochMillis')
            posted_date = None
            if posted_timestamp:
                posted_date = datetime.fromtimestamp(int(posted_timestamp) / 1000)
            
            # Extract engagement
            comments = post.get('comments', {})
            comment_count = comments.get('totalCommentCount', 0)
            
            reactions = post.get('reactionSummaries', {})
            reaction_count = len(reactions.get('summaries', []))
            
            # Extract images
            images = []
            photos = post.get('photos', [])
            for photo in photos:
                if photo.get('url'):
                    images.append(photo['url'])
            
            # Review tagged business
            tagged_business = None
            tagged_category = None
            tagged_content = post.get('taggedContent', [])
            if tagged_content:
                entity_page = tagged_content[0].get('entityPage', {})
                tagged_business = entity_page.get('name')
                category_info = entity_page.get('categoryInfo', {})
                display_category = category_info.get('displayCategory', {})
                if display_category:
                    tagged_category = display_category.get('styledName', {}).get('text')
            
            # Extract topics
            topics = []
            for topic in post.get('topics', []):
                topic_name = topic.get('name', {}).get('singularName')
                if topic_name:
                    topics.append(topic_name)
            
            # Build URL
            detail_link = post.get('detailLink', {})
            href = detail_link.get('href', '')
            if href:
                href = href.split('?')[0]  # Remove query parameters for robust deduplication
                url = f"https://nextdoor.com{href}"
            else:
                url = None
            
            return {
                'post_id': post_id,
                'url': url,
                'title': title,
                'body': body,
                'author_name': author_name,
                'author_url': author_url,
                'neighborhood': neighborhood,
                'city': city,
                'state': state,
                'posted_date': posted_date,
                'comment_count': comment_count,
                'reaction_count': reaction_count,
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
            # Determine if service request
            # Heuristic: Title or body contains request keywords and NOT promotion keywords
            title = raw_data.get('title', '') or ''
            description = raw_data.get('description', '') or raw_data.get('body', '') or ''
            text = f"{title} {description}".lower()
            
            request_keywords = [
                "looking for", "need ", "needs ", "in search of", "iso ", "anyone know", 
                "can anyone", "help needed", "searching for", "help wanted", 
                "recommendation needed", "who do you use", "referral needed",
                "anyone available", "can someone", "anyone recommend"
            ]
            
            negative_keywords = [
                # Promotions/Ads
                "free estimate", "i offer", "we offer", "we do", "contact me", "contact us",
                "call me", "call us", "my number", "years experience", "services offered",
                "fully insured", "licensed",
                # Recommendations/Reviews
                "wanted to share", "shout out", "highly recommend", "i recommend", 
                "cannot recommend", "huge thanks", "excellent work", "great job", 
                "recommend this", "recommend him", "recommend her", "recommend them"
            ]
            
            has_request = any(k in text for k in request_keywords)
            has_negative = any(k in text for k in negative_keywords)
            
            # If specifically in 'General' or 'Recommendations' but has request keywords, it's likely a request.
            # But if it has negative keywords (ads or reviews), it's NOT a request.
            
            is_service_request = has_request and not has_negative

            lead = NextdoorLead(
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
            return lead
        except Exception as e:
            self.logger.warning("failed_to_create_nextdoor_lead", error=str(e))
            return None

    def scrape(self, target: str = None, **kwargs) -> List[ScrapedLead]:
        """
        Main scraping method using Playwright.
        Arguments:
            max_pages: Number of scroll pages to load
        """
        max_pages = kwargs.get('max_pages', 5)
        all_leads = []
        collected_posts = {} # Deduplication dict by ID

        if not self.cookies:
            self.logger.error("nextdoor_cookies_required")
            raise ValueError("Nextdoor cookies not configured.")

        # Playwright Execution
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            context = browser.new_context(
                viewport={'width': 1280, 'height': 800},
                user_agent='Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
            )
            
            # Add cookies
            cookie_list = []
            for k, v in self.cookies.items():
                cookie_list.append({
                    'name': k,
                    'value': v,
                    'domain': '.nextdoor.com',
                    'path': '/'
                })
            context.add_cookies(cookie_list)
            
            page = context.new_page()
            
            # Response listener for GraphQL
            def handle_response(response):
                try:
                    if "PersonalizedFeed" in response.url and response.status == 200:
                        data = response.json()
                        feed_data = data.get('data', {}).get('me', {}).get('personalizedFeed', {})
                        feed_items = feed_data.get('feedItems', [])
                        
                        for item in feed_items:
                            parsed = self.parse_post(item)
                            if parsed and parsed.get('post_id'):
                                collected_posts[parsed['post_id']] = parsed
                except Exception:
                    pass

            page.on("response", handle_response)
            
            try:
                self.logger.info("navigating_to_feed")
                page.goto("https://nextdoor.com/news_feed/", timeout=60000)
                page.wait_for_load_state("networkidle")
                
                # Scroll loop
                for i in range(max_pages):
                    self.logger.info(f"scrolling_page_{i+1}")
                    page.evaluate("window.scrollBy(0, 1000)")
                    try:
                        page.wait_for_timeout(2000) # Wait for network
                        # Check for 'Sign in' redirect which implies cookies failed
                        if "login" in page.url or "signup" in page.url:
                             self.logger.error("session_invalid_redirected_to_login")
                             break
                    except Exception:
                        pass
                
                self.logger.info("scrolling_complete", gathered=len(collected_posts))
                
            except Exception as e:
                self.logger.error("playwright_execution_failed", error=str(e))
            finally:
                browser.close()
        
        # Convert collected dicts to Leads
        for post_data in collected_posts.values():
            lead = self.parse_item(post_data)
            if lead:
                all_leads.append(lead)
                
        return all_leads
