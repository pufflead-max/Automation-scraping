"""Main entry point for the scraping system."""

import os
import sys
from typing import Optional, List
import argparse

sys.path.insert(0, os.path.dirname(__file__))

from config import get_settings
from logger import get_logger, ScraperLogger
from scrapers.craigslist import CraigslistScraper
from models import ScrapedLead

logger = get_logger(__name__)


def run_nextdoor_scraper(cookies: Optional[dict] = None, save_to_db: bool = True, max_pages: int = 5) -> List[ScrapedLead]:
    from scrapers.nextdoor import NextdoorScraper
    
    scraper_logger = ScraperLogger("nextdoor")
    scraper_logger.info("starting_nextdoor_scraper", max_pages=max_pages)
    
    try:
        scraper = NextdoorScraper(cookies=cookies)
        leads = scraper.run(target=None, save_to_db=save_to_db, max_pages=max_pages)
        scraper_logger.info("nextdoor_scraper_completed", leads_count=len(leads))
        return leads
    except Exception as e:
        scraper_logger.error("nextdoor_scraper_failed", error=str(e), error_type=type(e).__name__)
        raise


def run_craigslist_scraper(target: str, category: Optional[str] = None, save_to_db: bool = True, headless: bool = True) -> List[ScrapedLead]:
    scraper_logger = ScraperLogger("craigslist")
    scraper_logger.info("starting_craigslist_scraper", target=target, category=category)
    
    try:
        scraper = CraigslistScraper(headless=headless)
        leads = scraper.run(target=target, category=category, save_to_db=save_to_db)
        scraper_logger.info("craigslist_scraper_completed", target=target, leads_count=len(leads))
        return leads
    except Exception as e:
        scraper_logger.error("craigslist_scraper_failed", target=target, error=str(e), error_type=type(e).__name__)
        raise


def main():
    parser = argparse.ArgumentParser(description="Run web scrapers for lead extraction")
    parser.add_argument("--scraper", type=str, required=True, choices=["craigslist", "nextdoor"], help="Which scraper to run")
    parser.add_argument("--target", type=str, required=True, help="Target URL or location to scrape")
    parser.add_argument("--category", type=str, default=None, help="Category name for the scraping job")
    parser.add_argument("--no-save", action="store_true", help="Don't save results to database (dry run)")
    parser.add_argument("--no-headless", action="store_true", help="Run browser in visible mode (for debugging)")
    parser.add_argument("--nextdoor-cookies", type=str, default=None, help="Path to JSON file containing Nextdoor authentication cookies")
    parser.add_argument("--max-pages", type=int, default=30, help="Maximum number of pages to scrape (for Nextdoor)")
    
    args = parser.parse_args()
    
    logger.info("scraper_starting", scraper=args.scraper, target=args.target, category=args.category, save_to_db=not args.no_save)
    
    try:
        settings = get_settings()
        logger.info("configuration_loaded", log_level=settings.log_level)
        
        if args.scraper == "craigslist":
            leads = run_craigslist_scraper(target=args.target, category=args.category, save_to_db=not args.no_save, headless=not args.no_headless)
        elif args.scraper == "nextdoor":
            cookies = None
            if args.nextdoor_cookies:
                import json
                try:
                    with open(args.nextdoor_cookies, 'r') as f:
                        cookies = json.load(f)
                    logger.info("nextdoor_cookies_loaded", cookie_count=len(cookies))
                except Exception as e:
                    logger.error("failed_to_load_nextdoor_cookies", error=str(e))
                    print(f"\n✗ Failed to load cookies: {e}")
                    sys.exit(1)
            
            if not cookies:
                logger.error("nextdoor_cookies_required")
                print("\n✗ Nextdoor scraper requires authentication cookies\n"
                      "  Use --nextdoor-cookies path/to/cookies.json\n"
                      "  See: development_pipelines/testing_nextdoor_1_jan_2026.ipynb")
                sys.exit(1)
            
            leads = run_nextdoor_scraper(cookies=cookies, save_to_db=not args.no_save, max_pages=args.max_pages)
        else:
            logger.error("unknown_scraper", scraper=args.scraper)
            sys.exit(1)
        
        logger.info("scraper_completed_successfully", scraper=args.scraper, leads_count=len(leads))
        print(f"\n✓ Successfully scraped {len(leads)} leads")
        sys.exit(0)
    except Exception as e:
        logger.exception("scraper_failed_with_exception", scraper=args.scraper, error=str(e))
        print(f"\n✗ Scraper failed: {e}")
        sys.exit(1)
