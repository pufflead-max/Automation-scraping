"""Base scraper class with common functionality."""

import uuid, os, requests, time
from abc import ABC, abstractmethod
from datetime import datetime, timedelta
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
    from ..utils.mappings import get_mapping_manager
except (ImportError, ValueError):
    try:
        from logger import ScraperLogger
        from database import DatabaseManager, get_db_manager
        from config import get_scraper_config, get_ghl_config
        from models import ScrapedLead, ScrapeJob
        from integrations.ghl import GHLClient
        from utils.lead_enrichment import LeadEnricher
        from utils.mappings import get_mapping_manager
    except ImportError:
        import sys
        sys.path.append(os.path.join(os.path.dirname(__file__), ".."))
        from logger import ScraperLogger
        from database import DatabaseManager, get_db_manager
        from config import get_scraper_config, get_ghl_config
        from models import ScrapedLead, ScrapeJob
        from integrations.ghl import GHLClient
        from utils.lead_enrichment import LeadEnricher
        from utils.mappings import get_mapping_manager

class BaseScraper(ABC):
    def __init__(self, scraper_name: str, db_manager: Optional[DatabaseManager] = None):
        self.name, self.logger, self.db = scraper_name, ScraperLogger(scraper_name), db_manager or get_db_manager()
        self.cfg, self.ghl_cfg = get_scraper_config(), get_ghl_config()
        self.ghl = GHLClient(self.ghl_cfg['api_key'], self.ghl_cfg['location_id']) if self.ghl_cfg.get('api_key') else None
        self.current_job = None
        self.scraped_items = []
        self.user_email = None
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
            self.db.get_collection(col).create_index("source_url", background=True)
            leads_to_save = [l.model_dump() for l in leads]
            if not leads_to_save: return 0
            count = self.db.bulk_upsert(col, leads_to_save, key="source_url")
            self.logger.info("leads_saved", col=col, count=count)
            return count
        except Exception as e:
            self.logger.error("save_failed", col=col, error=str(e)); raise
    
    def run(self, target: str, save: bool = True, **kw) -> List[ScrapedLead]:
        user_data = kw.get('user_data')
        if user_data:
            user_profile = user_data.get('user') if 'user' in user_data else user_data
            self.user_email = user_profile.get('email')
            
        self.start_job(target, kw.get('category'))
        try:
            # 1. Scrape Leads (Now returns items with minimal processing)
            leads = self.scrape(target, **kw)
            self.scraped_items = leads
            
            # Decorate leads with user metadata
            for l in leads:
                l.scraped_date = datetime.utcnow()
                l.target_url = target
                if user_data:
                    user_profile = user_data.get('user') if 'user' in user_data else user_data
                    l.user_email = user_profile.get('email')
                    l.user_name  = user_profile.get('name')
                    l.user_phone = user_profile.get('phone')
                    l.extra_data = l.extra_data or {}
                    l.extra_data['user_detail'] = user_data

            # 2. Save to Raw Data Collection
            if save and leads:
                self.save_leads(leads, f"{self.name.capitalize()}_raw_data")
                
                # 3. Regex and AI Checks (Standardized Binary Gate)
                from utils.buyer_intent import BuyerIntentDetector
                self.logger.info("starting_ai_qualification", count=len(leads))
                
                final_leads = []
                for l in leads:
                    text = f"{l.title or ''} {l.description or ''}".strip()
                    if not text: continue
                    
                    # Run the strict triple-check and capture individual results
                    res = BuyerIntentDetector.get_detailed_results(text)
                    l.ollama_result = res.get("ollama_result")
                    l.gemini_result = res.get("gemini_result")
                    l.is_buyer_request = res.get("final_decision", False)
                    l.is_hiring = l.is_buyer_request
                    
                    if l.is_hiring:
                        l.intent_score = 5
                        final_leads.append(l)
                
                # 4. Save to Final Data Collection
                if final_leads:
                    self.save_leads(final_leads, f"{self.name.capitalize()}_final_data")
                    
                    # 5. Sync to Google Sheets and Push to GHL
                    self._sync_and_push(final_leads)
                
                self.logger.info("pipeline_summary",
                    total_scraped=len(leads),
                    qualified=len(final_leads),
                    rejected=len(leads) - len(final_leads)
                )

            self.complete_job("completed")
            return leads
        except Exception as e:
            self.complete_job("failed", e); raise

    def _sync_and_push(self, leads: List[ScrapedLead]):
        """Helper to sync leads to GHL and Google Sheets after AI classification."""
        try:
            from push_leads import push_leads
            self.logger.info("starting_external_sync", count=len(leads))
            # push_leads script already handles GHL and Sheets based on source name
            push_leads(source=self.name, user_email=self.user_email)
        except Exception as e:
            self.logger.error("sync_push_failed", error=str(e))
