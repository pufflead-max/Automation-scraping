"""Base scraper class with common functionality."""

from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional
from datetime import datetime
import time
import uuid
import json
import os
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
    """Abstract base class for all scrapers."""
    
    def __init__(self, scraper_name: str, db_manager: Optional[DatabaseManager] = None):
        self.scraper_name = scraper_name
        self.logger = ScraperLogger(scraper_name)
        self.db = db_manager or get_db_manager()
        self.config = get_scraper_config()
        self.current_job: Optional[ScrapeJob] = None
        self.scraped_items: List[ScrapedLead] = []
        self.logger.info("scraper_initialized", scraper=scraper_name)
    
    @abstractmethod
    def scrape(self, target: str, **kwargs) -> List[ScrapedLead]:
        """Main scraping method - must be implemented by subclasses."""
        pass
    
    @abstractmethod
    def parse_item(self, raw_data: Any) -> Optional[ScrapedLead]:
        """Parse raw scraped data into a ScrapedLead model."""
        pass
    
    def start_job(self, target: str, category: Optional[str] = None) -> ScrapeJob:
        """Start a new scrape job and log it to the database."""
        job = ScrapeJob(job_id=str(uuid.uuid4()), scraper=self.scraper_name, status="started",
                       target=target, category=category, started_at=datetime.utcnow())
        self.current_job = job
        try:
            self.db.insert_one("scrape_jobs", job.model_dump())
            self.logger.log_scrape_start(target, job_id=job.job_id, category=category)
        except Exception as e:
            self.logger.error("failed_to_save_job", error=str(e))
        return job
    
    def complete_job(self, status: str = "completed", error: Optional[Exception] = None) -> None:
        """Mark the current job as completed and update the database."""
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
        
        try:
            self.db.update_one("scrape_jobs", {"job_id": self.current_job.job_id},
                             {"$set": self.current_job.model_dump()}, upsert=True)
            if status == "completed":
                self.logger.log_scrape_success(self.current_job.target, items_count=self.current_job.items_saved, job_id=self.current_job.job_id)
            else:
                self.logger.log_scrape_error(self.current_job.target, error, job_id=self.current_job.job_id)
        except Exception as e:
            self.logger.error("failed_to_update_job", error=str(e))
    
    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10),
           retry=retry_if_exception_type((RequestException, Timeout)), reraise=True)
    def make_request(self, url: str, method: str = "GET", headers: Optional[Dict[str, str]] = None,
                    cookies: Optional[Dict[str, str]] = None, data: Optional[Dict] = None,
                    json: Optional[Dict] = None, use_proxy: bool = True) -> requests.Response:
        """Make an HTTP request with automatic retries and proxy support."""
        proxies = None
        if use_proxy and self.config.get('scraperapi_proxy'):
            proxy_url = f"http://{self.config['scraperapi_proxy']}"
            proxies = {"http": proxy_url, "https": proxy_url}
        
        try:
            response = requests.request(method=method, url=url, headers=headers, cookies=cookies,
                                       data=data, json=json, proxies=proxies,
                                       timeout=self.config.get('timeout', 30), verify=False)
            response.raise_for_status()
            self.logger.debug("request_successful", url=url, status_code=response.status_code,
                            response_size=len(response.content))
            return response
        except Exception as e:
            self.logger.warning("request_failed", url=url, error=str(e), error_type=type(e).__name__)
            raise
    
    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10), reraise=True)
    def save_leads(self, leads: List[ScrapedLead], collection: str = "leads") -> int:
        """Save scraped leads to the database with retries."""
        if not leads:
            self.logger.warning("save_leads_called_with_empty_list")
            return 0
        
        if not self.db:
            from database import get_db_manager
            self.db = get_db_manager()
        
        try:
            count = self.db.bulk_upsert(collection, [lead.model_dump() for lead in leads], unique_field="source_url")
            self.logger.info("leads_saved", collection=collection, count=count,
                           job_id=self.current_job.job_id if self.current_job else None)
            return count
        except Exception as e:
            self.logger.error("failed_to_save_leads", collection=collection, lead_count=len(leads), error=str(e))
            raise

    def save_to_json(self, leads: List[ScrapedLead]) -> str:
        """Save leads to a local JSON file."""
        if not leads:
            return ""
        
        try:
            data_dir = "/opt/airflow/logs/scraped_data" if os.path.exists("/opt/airflow/logs") else os.path.join(
                os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))),
                "airflow", "logs", "scraped_data")
            os.makedirs(data_dir, exist_ok=True)
            
            filepath = os.path.join(data_dir, f"{self.scraper_name}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json")
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump([lead.model_dump(mode='json') for lead in leads], f, indent=2, ensure_ascii=False)
            
            self.logger.info("leads_saved_to_json", file=filepath, count=len(leads))
            print(f"\n✓ Saved backup to: {filepath}")
            return filepath
        except Exception as e:
            self.logger.error("failed_to_save_json", error=str(e))
            return ""
    
    def run(self, target: str, save_to_db: bool = True, **kwargs) -> List[ScrapedLead]:
        """Run the complete scraping workflow."""
        self.start_job(target, kwargs.get('category'))
        
        try:
            leads = self.scrape(target, **kwargs)
            self.scraped_items = leads
            
            json_path = self.save_to_json(leads)
            if json_path:
                self.logger.info("step_json_backup_completed", path=json_path)
            
            if save_to_db and leads:
                scraper_cap = self.scraper_name.capitalize()
                self.logger.info("saving_to_raw_collection", collection=f"{scraper_cap}_raw_data", count=len(leads))
                self.save_leads(leads, collection=f"{scraper_cap}_raw_data")
                
                final_leads = leads
                if self.scraper_name == 'nextdoor':
                    final_leads = [l for l in leads if getattr(l, 'is_service_request', False)]
                
                if final_leads:
                    self.logger.info("saving_to_final_collection", collection=f"{scraper_cap}_final_data", count=len(final_leads))
                    self.save_leads(final_leads, collection=f"{scraper_cap}_final_data")
            
            self.complete_job(status="completed")
            return leads
        except Exception as e:
            self.complete_job(status="failed", error=e)
            raise
    
    def sleep(self, seconds: float) -> None:
        """Sleep for specified seconds with logging."""
        self.logger.debug("sleeping", seconds=seconds)
        time.sleep(seconds)
