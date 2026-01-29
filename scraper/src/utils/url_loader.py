"""Utility for loading scraping URLs from text files."""

import os
from typing import List, Dict, Optional
from pathlib import Path


class URLLoader:
    """Load and manage scraping URLs from text files."""
    
    @staticmethod
    def load_urls_from_file(file_path: str, scraper_type: Optional[str] = None) -> List[str]:
        """
        Load URLs from a text file.
        
        Args:
            file_path: Path to the text file containing URLs (one per line)
            scraper_type: Optional scraper type for validation
            
        Returns:
            List of valid URLs
        """
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"URL file not found: {file_path}")
        
        urls = []
        with open(file_path, 'r') as f:
            for line in f:
                line = line.strip()
                # Skip empty lines and comments
                if not line or line.startswith('#'):
                    continue
                urls.append(line)
        
        return urls
    
    @staticmethod
    def get_default_url_file(scraper_type: str, base_dir: str = "/opt/airflow/scraper") -> str:
        """
        Get the default URL file path for a scraper type.
        
        Args:
            scraper_type: Type of scraper (facebook, nextdoor, craigslist)
            base_dir: Base directory for scraper files
            
        Returns:
            Path to the URL file
        """
        return os.path.join(base_dir, "urls", f"{scraper_type}_urls.txt")
    
    @staticmethod
    def load_urls_for_scraper(scraper_type: str, custom_file: Optional[str] = None) -> List[str]:
        """
        Load URLs for a specific scraper type.
        
        Args:
            scraper_type: Type of scraper (facebook, nextdoor, craigslist)
            custom_file: Optional custom file path
            
        Returns:
            List of URLs to scrape
        """
        file_path = custom_file or URLLoader.get_default_url_file(scraper_type)
        
        # If file doesn't exist, return empty list (will use default URL from env/config)
        if not os.path.exists(file_path):
            return []
        
        return URLLoader.load_urls_from_file(file_path, scraper_type)
    
    @staticmethod
    def load_urls_from_db(scraper_type: str) -> List[str]:
        """Load URLs from MongoDB config collection."""
        try:
            from database import get_db_manager
            db = get_db_manager()
            config = db.find_one("scraper_config", {"type": "urls", "scraper": scraper_type})
            if config and "urls" in config:
                urls = config["urls"]
                if isinstance(urls, str):
                    return [u.strip() for u in urls.replace('\n', ',').split(',') if u.strip()]
                return urls
        except Exception:
            pass
        return []

    @staticmethod
    def create_url_file_template(scraper_type: str, base_dir: str = "/opt/airflow/scraper"):
        """
        Create a template URL file for a scraper type.
        
        Args:
            scraper_type: Type of scraper
            base_dir: Base directory for scraper files
        """
        urls_dir = os.path.join(base_dir, "urls")
        os.makedirs(urls_dir, exist_ok=True)
        
        file_path = os.path.join(urls_dir, f"{scraper_type}_urls.txt")
        
        if os.path.exists(file_path):
            return
        
        templates = {
            "facebook": [
                "# Facebook URLs to scrape (one per line)",
                "# Example: https://www.facebook.com/groups/123456789",
                "# Example: https://www.facebook.com/share/g/14Tv25M9ns8/",
                ""
            ],
            "nextdoor": [
                "# Nextdoor URLs to scrape (one per line)",
                "# Note: Nextdoor typically uses feed-based scraping",
                "# Leave empty to use default feed",
                ""
            ],
            "craigslist": [
                "# Craigslist URLs to scrape (one per line)",
                "# Example: https://boston.craigslist.org/search/sks",
                "# Example: https://boston.craigslist.org/search/hss",
                ""
            ]
        }
        
        content = templates.get(scraper_type, ["# URLs to scrape (one per line)", ""])
        
        with open(file_path, 'w') as f:
            f.write('\n'.join(content))


def get_scraper_urls(scraper_type: str, default_url: Optional[str] = None) -> List[str]:
    """
    Get URLs for a scraper, checking DB, file, then default.
    
    Args:
        scraper_type: Type of scraper
        default_url: Default URL if no other source found
        
    Returns:
        List of URLs to scrape
    """
    # 1. Try DB first
    urls = URLLoader.load_urls_from_db(scraper_type)
    
    # 2. Try file if DB is empty
    if not urls:
        urls = URLLoader.load_urls_for_scraper(scraper_type)
    
    # 3. Use default if still empty
    if not urls and default_url:
        urls = [default_url]
    
    return urls
