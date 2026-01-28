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
    from ..config import get_scraper_config, get_ghl_config
    from ..models import ScrapedLead, ScrapeJob
    from ..integrations.ghl import GHLClient
    from ..utils.lead_enrichment import LeadEnricher
except ImportError:
    from logger import ScraperLogger
    from database import DatabaseManager, get_db_manager
    from config import get_scraper_config, get_ghl_config
    from models import ScrapedLead, ScrapeJob
    from integrations.ghl import GHLClient
    from utils.lead_enrichment import LeadEnricher


class BaseScraper(ABC):
    """Abstract base class for all scrapers."""
    
    def __init__(self, scraper_name: str, db_manager: Optional[DatabaseManager] = None):
        self.scraper_name = scraper_name
        self.logger = ScraperLogger(scraper_name)
        self.db = db_manager or get_db_manager()
        self.config = get_scraper_config()
        self.ghl_config = get_ghl_config()
        
        self.ghl_client = None
        if self.ghl_config.get('api_key') and self.ghl_config.get('location_id'):
            self.ghl_client = GHLClient(self.ghl_config['api_key'], self.ghl_config['location_id'])
            
        self.current_job = None
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
            
            # Filter for buyer requests IMMEDIATELY (before any saving)
            # Check if leads have is_buyer_request or is_service_request attribute
            buyer_leads = []
            for lead in leads:
                # Support both is_buyer_request (Craigslist, Facebook) and is_service_request (Nextdoor)
                is_buyer = getattr(lead, 'is_buyer_request', None)
                is_service = getattr(lead, 'is_service_request', None)
                
                # Include lead if either flag is True
                if is_buyer or is_service:
                    buyer_leads.append(lead)
            
            # Log filtering results
            total_scraped = len(leads)
            total_buyers = len(buyer_leads)
            filtered_count = total_scraped - total_buyers
            
            self.logger.info("buyer_intent_filtering_complete",
                           total_scraped=total_scraped,
                           buyer_leads=total_buyers,
                           seller_posts_filtered=filtered_count,
                           buyer_percentage=f"{(total_buyers/total_scraped*100):.1f}%" if total_scraped > 0 else "0%")
            
            if filtered_count > 0:
                self.logger.info("filtered_seller_content", 
                               filtered_out=filtered_count,
                               message=f"Skipped {filtered_count} seller/non-buyer posts - NOT saved to database")
            
            # Save JSON backup of BUYER LEADS ONLY
            if buyer_leads:
                # Enrich buyer leads with vertical, phone, and city
                for lead in buyer_leads:
                    # Combine title and description for analysis
                    text = f"{lead.title or ''} {lead.description or ''}"
                    
                    # Vertical
                    lead.vertical = LeadEnricher.extract_vertical(text)
                    
                    # Phone
                    lead.phone = LeadEnricher.extract_phone(text)
                    
                    # City (Attempt to improve if missing)
                    if not lead.city:
                         lead.city = LeadEnricher.extract_city(text, lead.location)
                
                json_path = self.save_to_json(buyer_leads)
                if json_path:
                    self.logger.info("step_json_backup_completed", path=json_path, count=len(buyer_leads))
            
            # Save to MongoDB - BUYER LEADS ONLY
            if save_to_db and buyer_leads:
                scraper_cap = self.scraper_name.capitalize()
                
                # Save to final collection only (no raw data collection)
                self.logger.info("saving_buyer_leads_to_db", 
                               collection=f"{scraper_cap}_final_data", 
                               count=len(buyer_leads))
                self.save_leads(buyer_leads, collection=f"{scraper_cap}_final_data")
                
                self.logger.info("buyer_leads_saved_successfully", 
                               saved=len(buyer_leads),
                               skipped=filtered_count)
            elif save_to_db and not buyer_leads:
                self.logger.warning("no_buyer_leads_found_nothing_saved", 
                                  total_scraped=total_scraped,
                                  message="All posts were seller content - nothing saved to database")
            
            self.complete_job(status="completed")
            return buyer_leads  # Return only buyer leads
        except Exception as e:
            self.complete_job(status="failed", error=e)
            raise

    def sleep(self, seconds: float) -> None:
        """Sleep for specified seconds with logging."""
        self.logger.debug("sleeping", seconds=seconds)
        time.sleep(seconds)
