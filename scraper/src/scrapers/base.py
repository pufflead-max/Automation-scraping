"""
Base scraper class with common functionality.
All specific scrapers inherit from this class.
"""

from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional
from datetime import datetime
import time
import uuid
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type
import requests
from requests.exceptions import RequestException, Timeout

try:
    from ..logger import ScraperLogger
    from ..database import DatabaseManager, get_db_manager
    from ..config import get_scraper_config
    from ..models import ScrapedLead, ScrapeJob
except ImportError:
    from logger import ScraperLogger
    from database import DatabaseManager, get_db_manager
    from config import get_scraper_config
    from models import ScrapedLead, ScrapeJob


class BaseScraper(ABC):
    """
    Abstract base class for all scrapers.
    Provides common functionality for scraping, error handling, and data storage.
    """
    
    def __init__(self, scraper_name: str, db_manager: Optional[DatabaseManager] = None):
        """
        Initialize base scraper.
        
        Args:
            scraper_name: Name of the scraper (e.g., 'craigslist')
            db_manager: Optional database manager instance
        """
        self.scraper_name = scraper_name
        self.logger = ScraperLogger(scraper_name)
        self.db = db_manager or get_db_manager()
        self.config = get_scraper_config()
        
        # Job tracking
        self.current_job: Optional[ScrapeJob] = None
        self.scraped_items: List[ScrapedLead] = []
        
        self.logger.info("scraper_initialized", scraper=scraper_name)
    
    @abstractmethod
    def scrape(self, target: str, **kwargs) -> List[ScrapedLead]:
        """
        Main scraping method - must be implemented by subclasses.
        
        Args:
            target: Target URL or identifier to scrape
            **kwargs: Additional scraper-specific parameters
        
        Returns:
            List[ScrapedLead]: List of scraped and validated leads
        """
        pass
    
    @abstractmethod
    def parse_item(self, raw_data: Any) -> Optional[ScrapedLead]:
        """
        Parse raw scraped data into a ScrapedLead model.
        
        Args:
            raw_data: Raw data from the source (HTML, JSON, etc.)
        
        Returns:
            Optional[ScrapedLead]: Parsed and validated lead, or None if parsing fails
        """
        pass
    
    def start_job(self, target: str, category: Optional[str] = None) -> ScrapeJob:
        """
        Start a new scrape job and log it to the database.
        
        Args:
            target: Target being scraped
            category: Optional category
        
        Returns:
            ScrapeJob: The created job instance
        """
        job = ScrapeJob(
            job_id=str(uuid.uuid4()),
            scraper=self.scraper_name,
            status="started",
            target=target,
            category=category,
            started_at=datetime.utcnow()
        )
        
        self.current_job = job
        
        # Save job to database
        try:
            self.db.insert_one("scrape_jobs", job.model_dump())
            self.logger.log_scrape_start(target, job_id=job.job_id, category=category)
        except Exception as e:
            self.logger.error("failed_to_save_job", error=str(e))
        
        return job
    
    def complete_job(self, status: str = "completed", error: Optional[Exception] = None) -> None:
        """
        Mark the current job as completed and update the database.
        
        Args:
            status: Final status ('completed' or 'failed')
            error: Optional exception if job failed
        """
        if not self.current_job:
            self.logger.warning("complete_job_called_without_active_job")
            return
        
        self.current_job.status = status
        self.current_job.completed_at = datetime.utcnow()
        self.current_job.items_found = len(self.scraped_items)
        self.current_job.items_saved = len([item for item in self.scraped_items if item])
        
        if error:
            self.current_job.error_message = str(error)
            self.current_job.error_type = type(error).__name__
        
        # Update job in database
        try:
            self.db.update_one(
                "scrape_jobs",
                {"job_id": self.current_job.job_id},
                {"$set": self.current_job.model_dump()},
                upsert=True
            )
            
            if status == "completed":
                self.logger.log_scrape_success(
                    self.current_job.target,
                    items_count=self.current_job.items_saved,
                    job_id=self.current_job.job_id
                )
            else:
                self.logger.log_scrape_error(
                    self.current_job.target,
                    error,
                    job_id=self.current_job.job_id
                )
        except Exception as e:
            self.logger.error("failed_to_update_job", error=str(e))
    
    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        retry=retry_if_exception_type((RequestException, Timeout)),
        reraise=True
    )
    def make_request(
        self,
        url: str,
        method: str = "GET",
        headers: Optional[Dict[str, str]] = None,
        cookies: Optional[Dict[str, str]] = None,
        data: Optional[Dict] = None,
        json: Optional[Dict] = None,
        use_proxy: bool = True
    ) -> requests.Response:
        """
        Make an HTTP request with automatic retries and proxy support.
        
        Args:
            url: Target URL
            method: HTTP method (GET, POST, etc.)
            headers: Optional headers
            cookies: Optional cookies
            data: Optional form data
            json: Optional JSON data
            use_proxy: Whether to use ScraperAPI proxy
        
        Returns:
            requests.Response: The response object
        
        Raises:
            RequestException: If request fails after retries
        """
        proxies = None
        if use_proxy and self.config.get('scraperapi_proxy'):
            proxies = {
                "http": f"http://{self.config['scraperapi_proxy']}",
                "https": f"https://{self.config['scraperapi_proxy']}"
            }
        
        try:
            response = requests.request(
                method=method,
                url=url,
                headers=headers,
                cookies=cookies,
                data=data,
                json=json,
                proxies=proxies,
                timeout=self.config.get('timeout', 30),
                verify=False  # Disable SSL verification for proxies
            )
            
            response.raise_for_status()
            
            self.logger.debug(
                "request_successful",
                url=url,
                status_code=response.status_code,
                response_size=len(response.content)
            )
            
            return response
            
        except Exception as e:
            self.logger.warning(
                "request_failed",
                url=url,
                error=str(e),
                error_type=type(e).__name__
            )
            raise
    
    def save_leads(self, leads: List[ScrapedLead], collection: str = "leads") -> int:
        """
        Save scraped leads to the database.
        
        Args:
            leads: List of validated leads
            collection: Collection name to save to
        
        Returns:
            int: Number of leads successfully saved
        """
        if not leads:
            self.logger.warning("save_leads_called_with_empty_list")
            return 0
        
        # Convert leads to dictionaries
        lead_dicts = [lead.model_dump() for lead in leads]
        
        try:
            # Insert leads
            inserted_ids = self.db.insert_many(collection, lead_dicts)
            
            self.logger.info(
                "leads_saved",
                collection=collection,
                count=len(inserted_ids),
                job_id=self.current_job.job_id if self.current_job else None
            )
            
            return len(inserted_ids)
            
        except Exception as e:
            self.logger.error(
                "failed_to_save_leads",
                collection=collection,
                lead_count=len(leads),
                error=str(e)
            )
            return 0

    def save_to_json(self, leads: List[ScrapedLead]) -> str:
        """
        Save leads to a local JSON file.
        
        Args:
            leads: List of leads to save
        
        Returns:
            str: Path of the saved file
        """
        import json
        import os
        
        if not leads:
            return ""
            
        try:
            # Ensure data directory exists (use logs dir which is writable and mounted)
            data_dir = "/opt/airflow/logs/scraped_data"
            os.makedirs(data_dir, exist_ok=True)
            
            # Generate filename: scraper_YYYYMMDD_HHMMSS.json
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"{self.scraper_name}_{timestamp}.json"
            filepath = os.path.join(data_dir, filename)
            
            # Dump data
            data = [lead.model_dump(mode='json') for lead in leads]
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
                
            self.logger.info("leads_saved_to_json", file=filepath, count=len(leads))
            print(f"\n✓ Saved backup to: {filepath}")
            return filepath
            
        except Exception as e:
            self.logger.error("failed_to_save_json", error=str(e))
            return ""
    
    def run(self, target: str, save_to_db: bool = True, **kwargs) -> List[ScrapedLead]:
        """
        Run the complete scraping workflow.
        
        Args:
            target: Target to scrape
            save_to_db: Whether to save results to database
            **kwargs: Additional scraper-specific parameters
        
        Returns:
            List[ScrapedLead]: List of scraped leads
        """
        # Start job
        category = kwargs.get('category')
        self.start_job(target, category)
        
        try:
            # Run scraper
            leads = self.scrape(target, **kwargs)
            self.scraped_items = leads
            
            # Save to JSON file (Backup)
            self.save_to_json(leads)

            # Save to database if requested
            if save_to_db and leads:
                self.save_leads(leads)
            
            # Mark job as completed
            self.complete_job(status="completed")
            
            return leads
            
        except Exception as e:
            # Mark job as failed
            self.complete_job(status="failed", error=e)
            raise
    
    def sleep(self, seconds: float) -> None:
        """
        Sleep for specified seconds with logging.
        
        Args:
            seconds: Number of seconds to sleep
        """
        self.logger.debug("sleeping", seconds=seconds)
        time.sleep(seconds)


if __name__ == "__main__":
    # Test base scraper (can't instantiate abstract class directly)
    print("BaseScraper is an abstract class and must be subclassed.")
    print("See craigslist.py or nextdoor.py for concrete implementations.")
