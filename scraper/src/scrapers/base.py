"""Base scraper class with common functionality  ."""

import uuid, json, os, requests, time
from abc import ABC, abstractmethod
from datetime import datetime
from typing import List, Dict, Any, Optional
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type
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
    def __init__(self, scraper_name: str, db_manager: Optional[DatabaseManager] = None):
        self.name, self.logger, self.db = scraper_name, ScraperLogger(scraper_name), db_manager or get_db_manager()
        self.cfg, self.ghl_cfg = get_scraper_config(), get_ghl_config()
        self.ghl = GHLClient(self.ghl_cfg['api_key'], self.ghl_cfg['location_id']) if self.ghl_cfg.get('api_key') else None
        self.current_job = None
        self.scraped_items = []
        self.user_email = None  # Store current user context
        self.logger.info("init", scraper=scraper_name)
    
    @abstractmethod
    def scrape(self, target: str, **kw) -> List[ScrapedLead]: pass
    
    @abstractmethod
    def parse_item(self, raw: Any) -> Optional[ScrapedLead]: pass
    
    def start_job(self, target: str, cat: Optional[str] = None) -> ScrapeJob:
        job = ScrapeJob(job_id=str(uuid.uuid4()), scraper=self.name, status="started", target=target, category=cat)
        self.current_job = job
        try:
            self.db.insert_one("scrape_jobs", job.model_dump())
            self.logger.log_scrape_start(target, job_id=job.job_id, category=cat)
        except Exception as e: self.logger.error("job_save_failed", error=str(e))
        return job
    
    def complete_job(self, status: str = "completed", error: Optional[Exception] = None):
        if not (j := self.current_job): return
        j.status, j.completed_at, j.items_found = status, datetime.utcnow(), len(self.scraped_items)
        j.items_saved = len([i for i in self.scraped_items if i])
        if error: j.error_message, j.error_type = str(error), type(error).__name__
        try:
            self.db.update_one("scrape_jobs", {"job_id": j.job_id}, {"$set": j.model_dump()}, upsert=True)
            if status == "completed": self.logger.log_scrape_success(j.target, j.items_saved, job_id=j.job_id)
            else: self.logger.log_scrape_error(j.target, error, job_id=j.job_id)
        except Exception as e: self.logger.error("job_update_failed", error=str(e))
    
    @retry(stop=stop_after_attempt(3), wait=wait_exponential(1, 2, 10), retry=retry_if_exception_type((RequestException, Timeout)), reraise=True)
    def make_request(self, url, method="GET", headers=None, cookies=None, **kw) -> requests.Response:
        use_proxy = kw.pop('use_proxy', True)
        proxies = {"http": f"http://{p}", "https": f"http://{p}"} if (p := self.cfg.get('scraperapi_proxy')) and use_proxy else None
        res = requests.request(method, url, headers=headers, cookies=cookies, proxies=proxies, timeout=self.cfg.get('timeout', 30), verify=False, **kw)
        res.raise_for_status()
        return res
    
    def save_leads(self, leads: List[ScrapedLead], col: str = "leads") -> int:
        if not leads: return 0
        try:
            count = self.db.bulk_upsert(col, [l.model_dump() for l in leads], key="source_url")
            self.logger.info("leads_saved", col=col, count=count)
            return count
        except Exception as e:
            self.logger.error("save_failed", col=col, error=str(e)); raise
    
    def run(self, target: str, save: bool = True, **kw) -> List[ScrapedLead]:
        user_data = kw.get('user_data')
        if user_data:
            self.user_email = user_data.get('email')
            
        self.start_job(target, kw.get('category'))
        try:
            leads = self.scrape(target, **kw)
            self.scraped_items = leads
            buyers = [l for l in leads if getattr(l, 'is_buyer_request', False) or getattr(l, 'is_service_request', False)]
            
            self.logger.info("filtered", total=len(leads), buyers=len(buyers))
            
            if buyers:
                for l in buyers:
                    text = f"{l.title or ''} {l.description or ''}"
                    l.vertical, l.phone = LeadEnricher.extract_vertical(text), LeadEnricher.extract_phone(text)
                    if not l.city: l.city = LeadEnricher.extract_city(text, l.location)
                    
                    # Attach user metadata if available
                    if user_data:
                        l.extra_data = l.extra_data or {}
                        l.extra_data['user_detail'] = user_data
                        
                        # Extract user data to top-level fields for easier querying and GHL mapping
                        self.user_email = user_data.get('email')
                        l.user_email = self.user_email
                        l.user_name = user_data.get('name')
                        l.user_phone = user_data.get('phone')
                
                # JSON Backup
                path = os.path.join(os.getcwd(), "scraped_data")
                os.makedirs(path, exist_ok=True)
                fname = os.path.join(path, f"{self.name}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json")
                with open(fname, 'w') as f: json.dump([l.model_dump(mode='json') for l in buyers], f, indent=2)
                
                if save: self.save_leads(buyers, f"{self.name.capitalize()}_final_data")
            
            self.complete_job("completed")
            return buyers
        except Exception as e:
            self.complete_job("failed", e); raise
