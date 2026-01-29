"""Main entry point for the scraping system  ."""

import os, sys, argparse, json
from typing import Optional, List

sys.path.insert(0, os.path.dirname(__file__))
from config import get_settings
from logger import get_logger, ScraperLogger

logger = get_logger(__name__)

def run_scraper(name: str, target: Optional[str], **kwargs):
    scraper_logger = ScraperLogger(name)
    scraper_logger.info(f"starting_{name}_scraper", target=target, **kwargs)
    
    try:
        common = {"save": kwargs.get('save', kwargs.get('save_to_db', True)), "category": kwargs.get('category')}
        if name == "craigslist":
            from scrapers.craigslist import CraigslistScraper
            leads = CraigslistScraper(headless=kwargs.get('headless', True)).run(target=target, **common)
        elif name == "nextdoor":
            from scrapers.nextdoor import NextdoorScraper
            leads = NextdoorScraper(cookies=kwargs.get('cookies')).run(target=target, max_pages=kwargs.get('max_pages', 5), **common)
        elif name == "facebook":
            from scrapers.facebook import FacebookScraper
            leads = FacebookScraper(cookies=kwargs.get('cookies'), headless=kwargs.get('headless', True)).run(target=target, limit=kwargs.get('limit', 25), **common)
        else:
            raise ValueError(f"Unknown scraper: {name}")
            
        scraper_logger.info(f"{name}_completed", count=len(leads))
        return leads
    except Exception as e:
        scraper_logger.exception(f"{name}_failed", error=str(e))
        raise

def run_craigslist_scraper(**kwargs): return run_scraper("craigslist", kwargs.pop('target', None), **kwargs)
def run_nextdoor_scraper(**kwargs): return run_scraper("nextdoor", kwargs.pop('target', None), **kwargs)
def run_facebook_scraper(**kwargs): return run_scraper("facebook", kwargs.pop('target', None), **kwargs)

def main():
    parser = argparse.ArgumentParser(description="Run web scrapers")
    parser.add_argument("--scraper", required=True, choices=["craigslist", "nextdoor", "facebook"])
    parser.add_argument("--target", required=True)
    parser.add_argument("--category")
    parser.add_argument("--no-save", action="store_true")
    parser.add_argument("--no-headless", action="store_true")
    parser.add_argument("--cookies", help="Path to JSON cookies file")
    parser.add_argument("--max-pages", type=int, default=30)
    parser.add_argument("--limit", type=int, default=25)
    
    args = parser.parse_args()
    
    try:
        cookies = None
        if args.cookies and os.path.exists(args.cookies):
            with open(args.cookies, 'r') as f:
                cookies = json.load(f)
        
        if args.scraper == "nextdoor" and not cookies:
            print("✗ Nextdoor requires --cookies"); sys.exit(1)
            
        leads = run_scraper(
            args.scraper, args.target, category=args.category, 
            save=not args.no_save, headless=not args.no_headless,
            cookies=cookies, max_pages=args.max_pages, limit=args.limit
        )
        
        print(f"\n✓ Scraped {len(leads)} leads")
    except Exception as e:
        print(f"\n✗ Failed: {e}"); sys.exit(1)

if __name__ == "__main__":
    main()
