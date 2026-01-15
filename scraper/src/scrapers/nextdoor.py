"""
Nextdoor scraper implementation.
Extracts service leads from Nextdoor using their GraphQL API.
"""

from typing import List, Dict, Any, Optional
from datetime import datetime
import time
import uuid

from .base import BaseScraper
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
    Uses Nextdoor's GraphQL API to fetch personalized feed items.
    """
    
    # GraphQL API endpoint
    GRAPHQL_ENDPOINT = "https://nextdoor.com/api/gql/PersonalizedFeed"
    
    # GraphQL query hash (from network inspection)
    QUERY_HASH = "b416264b6fcbca3bec23ac002bba373679f002c09e28ba0f4884c7edc0838718"
    
    def __init__(self, cookies: Optional[Dict[str, str]] = None, **kwargs):
        """
        Initialize Nextdoor scraper.
        
        Args:
            cookies: Nextdoor session cookies (required for authentication)
            **kwargs: Additional arguments passed to BaseScraper
        """
        super().__init__("nextdoor", **kwargs)
        
        # Nextdoor requires authentication cookies
        # These should be provided via environment or passed in
        self.cookies = cookies or self._get_cookies_from_env()
        
        # Nextdoor-specific headers
        self.headers = {
            'accept': '*/*',
            'accept-language': 'en-US,en;q=0.9',
            'cache-control': 'no-cache',
            'content-type': 'application/json',
            'enable-alphafeed': 'false',
            'origin': 'https://nextdoor.com',
            'referer': 'https://nextdoor.com/news_feed/',
            'sec-ch-ua': '"Not_A Brand";v="8", "Chromium";v="120", "Google Chrome";v="120"',
            'sec-ch-ua-mobile': '?0',
            'sec-ch-ua-platform': '"macOS"',
            'sec-fetch-dest': 'empty',
            'sec-fetch-mode': 'cors',
            'sec-fetch-site': 'same-origin',
            'user-agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        }
        
        # Add CSRF token from cookies if available
        if self.cookies and 'csrftoken' in self.cookies:
            self.headers['x-csrftoken'] = self.cookies['csrftoken']
    
    def _get_cookies_from_env(self) -> Dict[str, str]:
        """
        Get Nextdoor cookies from environment variables.
        
        Returns:
            Dict: Cookies dictionary
        """
        # TODO: Load from environment or configuration
        # For now, return empty dict - cookies should be provided
        self.logger.warning("nextdoor_cookies_not_configured", 
                          message="Nextdoor requires authentication cookies")
        return {}
    
    def build_graphql_query(
        self,
        page_size: int = 100,
        next_page: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Build GraphQL query for PersonalizedFeed.
        
        Args:
            page_size: Number of items to fetch
            next_page: Pagination cursor (None for first page)
        
        Returns:
            Dict: GraphQL query payload
        """
        return {
            'operationName': 'PersonalizedFeed',
            'variables': {
                'pagedCommentsMode': 'FEED',
                'includeModerationInfo': False,
                'mainFeedArgs': {
                    'pageSize': page_size,
                    'nextPage': next_page,
                    'supportedFeatures': {
                        'rollupTypes': ['CAROUSEL', 'LIST', 'GRID'],
                        'rollupItemTypes': [
                            'IMAGE_CARD',
                            'LIST_CARD',
                            'POST',
                            'PUBLISHER_DISCOVERY',
                            'ONBOARDING_CAROUSEL_CARD',
                        ],
                        'numCommentsForNewsPosts': 2,
                        'isCommentRankedByRelevance': False,
                    },
                    'sortOrder': 'RECENT_POSTS',
                    'feedRequestId': str(uuid.uuid4()),
                },
                'timeZone': 'America/New_York',
            },
            'extensions': {
                'persistedQuery': {
                    'version': 1,
                    'sha256Hash': self.QUERY_HASH,
                },
            },
        }
    
    def fetch_feed(
        self,
        page_size: int = 100,
        next_page: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Fetch feed items from Nextdoor GraphQL API.
        
        Args:
            page_size: Number of items to fetch
            next_page: Pagination cursor
        
        Returns:
            Dict: API response data
        """
        query = self.build_graphql_query(page_size, next_page)
        
        try:
            response = self.make_request(
                self.GRAPHQL_ENDPOINT,
                method="POST",
                headers=self.headers,
                cookies=self.cookies,
                json=query,
                use_proxy=False  # Nextdoor might block proxies
            )
            
            data = response.json()
            
            self.logger.debug(
                "nextdoor_feed_fetched",
                page_size=page_size,
                has_next_page=next_page is not None
            )
            
            return data
            
        except Exception as e:
            self.logger.error(
                "nextdoor_feed_fetch_failed",
                error=str(e),
                error_type=type(e).__name__
            )
            raise
    
    def parse_post(self, post_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        Parse a single post from the feed.
        
        Args:
            post_data: Raw post data from GraphQL response
        
        Returns:
            Optional[Dict]: Parsed post data or None
        """
        try:
            # Skip if not a POST type
            if post_data.get('feedItemType') != 'POST':
                return None
            
            post = post_data.get('post', {})
            
            # Extract basic info
            post_id = post.get('legacyPostId')
            title = post.get('subject', '')
            body = post.get('body', '')
            
            # Extract author info
            author = post.get('author', {})
            author_name = author.get('displayName')
            author_url = author.get('url')
            
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
            
            # Extract tagged business
            tagged_content = post.get('taggedContent', [])
            tagged_business = None
            tagged_category = None
            
            if tagged_content:
                entity_page = tagged_content[0].get('entityPage', {})
                tagged_business = entity_page.get('name')
                category_info = entity_page.get('categoryInfo', {})
                display_category = category_info.get('displayCategory', {})
                if display_category:
                    tagged_category = display_category.get('styledName', {}).get('text')
            
            # Build URL
            detail_link = post.get('detailLink', {})
            url = f"https://nextdoor.com{detail_link.get('href', '')}" if detail_link.get('href') else None
            
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
            }
            
        except Exception as e:
            self.logger.warning(
                "failed_to_parse_nextdoor_post",
                error=str(e),
                post_id=post_data.get('contentId')
            )
            return None
    
    def parse_item(self, raw_data: Dict[str, Any]) -> Optional[NextdoorLead]:
        """
        Parse raw data into a NextdoorLead model.
        
        Args:
            raw_data: Parsed post data
        
        Returns:
            Optional[NextdoorLead]: Validated lead or None
        """
        try:
            # Create lead model
            lead = NextdoorLead(
                source_url=raw_data.get('url', ''),
                source_id=raw_data.get('post_id'),
                post_id=raw_data.get('post_id'),
                title=raw_data.get('title'),
                description=raw_data.get('body'),
                author_name=raw_data.get('author_name'),
                author_url=raw_data.get('author_url'),
                neighborhood=raw_data.get('neighborhood'),
                city=raw_data.get('city'),
                state=raw_data.get('state'),
                location=f"{raw_data.get('city')}, {raw_data.get('state')}" if raw_data.get('city') and raw_data.get('state') else None,
                posted_date=raw_data.get('posted_date'),
                comment_count=raw_data.get('comment_count', 0),
                reaction_count=raw_data.get('reaction_count', 0),
                images=raw_data.get('images', []),
                tagged_business=raw_data.get('tagged_business'),
                tagged_business_category=raw_data.get('tagged_category'),
            )
            
            return lead
            
        except Exception as e:
            self.logger.warning(
                "failed_to_create_nextdoor_lead",
                error=str(e),
                raw_data=raw_data
            )
            return None
    
    def scrape(self, target: str = None, **kwargs) -> List[ScrapedLead]:
        """
        Main scraping method for Nextdoor.
        
        Args:
            target: Not used for Nextdoor (uses authenticated feed)
            **kwargs: Additional parameters:
                - max_pages: Maximum number of pages to scrape
                - page_size: Items per page
        
        Returns:
            List[ScrapedLead]: List of scraped and validated leads
        """
        max_pages = kwargs.get('max_pages', 5)
        page_size = kwargs.get('page_size', 100)
        
        all_leads = []
        next_page = None
        
        # Check if cookies are configured
        if not self.cookies:
            self.logger.error("nextdoor_cookies_required",
                            message="Nextdoor scraper requires authentication cookies")
            raise ValueError("Nextdoor cookies not configured. Please provide authentication cookies.")
        
        try:
            for page_num in range(max_pages):
                self.logger.info(
                    "fetching_nextdoor_page",
                    page=page_num + 1,
                    max_pages=max_pages
                )
                
                # Fetch feed
                response_data = self.fetch_feed(
                    page_size=page_size,
                    next_page=next_page
                )
                
                # Extract feed items
                if not response_data:
                    self.logger.error("nextdoor_response_empty", page=page_num + 1)
                    continue

                feed_data = response_data.get('data', {}).get('me', {}).get('personalizedFeed', {})
                feed_items = feed_data.get('feedItems', [])
                
                if not feed_items:
                    self.logger.info("no_more_feed_items")
                    break
                
                # Parse each item
                for item in feed_items:
                    parsed_post = self.parse_post(item)
                    if parsed_post:
                        lead = self.parse_item(parsed_post)
                        if lead:
                            all_leads.append(lead)
                
                # Get next page cursor
                next_page = feed_data.get('nextPage')
                if not next_page:
                    self.logger.info("no_next_page_available")
                    break
                
                # Be polite - wait between pages
                time.sleep(2)
            
            self.logger.info(
                "nextdoor_scraping_complete",
                total_leads=len(all_leads),
                pages_scraped=page_num + 1
            )
            
            return all_leads
            
        except Exception as e:
            self.logger.error(
                "nextdoor_scraping_failed",
                error=str(e),
                error_type=type(e).__name__
            )
            raise


if __name__ == "__main__":
    # Test the scraper
    print("Testing Nextdoor scraper...")
    print("\n⚠️  Note: Nextdoor scraper requires authentication cookies.")
    print("Please provide cookies from an authenticated Nextdoor session.\n")
    
    # Example cookies (these are expired/invalid - replace with real ones)
    example_cookies = {
        'csrftoken': 'your_csrf_token_here',
        'ndbr_at': 'your_auth_token_here',
        
    }
    
    try:
        scraper = NextdoorScraper(cookies=example_cookies)
        
        # This will fail without valid cookies
        # leads = scraper.run(save_to_db=False, max_pages=1)
        
        print("✓ Nextdoor scraper initialized")
        print("  To use: Provide valid authentication cookies")
        print("  See notebook: development_pipelines/testing_nextdoor_1_jan_2026.ipynb")
        
    except Exception as e:
        print(f"✗ Scraper test failed: {e}")
