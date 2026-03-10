"""Base scraper class with common functionality  ."""

import uuid, json, os, requests, time
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
            # 1. Ensure Index for fast lookups
            self.db.get_collection(col).create_index("source_url", background=True)
            
            # 2. Convert to dicts for bulk update
            # We no longer filter by existing_urls here because we want to allow 
            # existing leads to be updated with enriched information (like dates).
            leads_to_save = [l.model_dump() for l in leads]
            
            if not leads_to_save:
                return 0
                
            count = self.db.bulk_upsert(col, leads_to_save, key="source_url")
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
            
            # 1. Decorate ALL leads with user metadata and fresh scraped_date
            for l in leads:
                l.scraped_date = datetime.utcnow()
                if user_data:
                    l.user_email = user_data.get('email')
                    l.user_name = user_data.get('name')
                    l.user_phone = user_data.get('phone')
                    l.extra_data = l.extra_data or {}
                    l.extra_data['user_detail'] = user_data
            
            # 2. ── Age Filter: Drop leads older than 48 hours ─────────────────
            age_limit = datetime.utcnow() - timedelta(hours=48)
            fresh_leads = []
            stale_count = 0
            for l in leads:
                posted = getattr(l, 'posted_date', None)
                if posted:
                    try:
                        # Normalize to naive datetime if timezone-aware
                        if hasattr(posted, 'tzinfo') and posted.tzinfo is not None:
                            posted = posted.replace(tzinfo=None)
                        elif isinstance(posted, str):
                            from dateutil import parser as dateparser
                            posted = dateparser.parse(posted)
                            if posted and posted.tzinfo:
                                posted = posted.replace(tzinfo=None)
                    except Exception:
                        posted = None

                    if posted and posted < age_limit:
                        stale_count += 1
                        self.logger.debug("lead_too_old_skipped",
                                          url=getattr(l, 'source_url', ''),
                                          age_hours=round((datetime.utcnow() - posted).total_seconds() / 3600, 1))
                        continue
                fresh_leads.append(l)

            if stale_count:
                self.logger.info("stale_leads_dropped", count=stale_count, kept=len(fresh_leads))
            leads = fresh_leads

            # 3. Save ALL fresh leads to Raw Data collection
            if save and leads:
                self.save_leads(leads, f"{self.name.capitalize()}_raw_data")

            # 4. Hybrid Filtering and Enrichment
            # Determine user's allowed verticals for cross-referencing
            user_allowed_slugs = []
            mapper = None
            if user_data and user_data.get('verticals'):
                try:
                    from ..utils.mappings import get_mapping_manager
                    mapper = get_mapping_manager()
                    user_allowed_slugs = [mapper._resolve_vertical_slug(v) for v in user_data.get('verticals', [])]
                    self.logger.info("user_verticals_filter", email=self.user_email, allowed=user_allowed_slugs)
                except Exception as e:
                    self.logger.warning("failed_to_load_mapping_manager", error=str(e))

            # Initial intent filter
            intent_leads = [l for l in leads if getattr(l, 'is_buyer_request', False) or getattr(l, 'is_service_request', False)]
            self.logger.info("intent_filter_results", total=len(leads), initial_buyers=len(intent_leads))
            
            # Initialize Cloud AI Classifier
            ai = None
            try:
                from ..utils.ai_classifier import get_ai_classifier
                ai = get_ai_classifier()
            except Exception as e:
                self.logger.warning("failed_to_initialize_ai_classifier", error=str(e))

            final_leads = []
            if intent_leads:
                for l in intent_leads:
                    text = f"{l.title or ''} {l.description or ''}"
                    
                    # ── Stage 4: Cloud AI Validation (Buyer Intent) ──
                    if ai:
                        try:
                            # Intent Check (Buyer vs Seller vs Noise)
                            intent_res = ai.classify_intent(text)
                            if intent_res.get('label') in ['seller', 'noise'] and intent_res.get('confidence', 0) > 0.7:
                                self.logger.debug("ai_intent_filtered", url=getattr(l, 'source_url', ''), label=intent_res.get('label'), reason=intent_res.get('reason'))
                                continue
                            
                            # If AI strongly confirms buyer, update local intent
                            if intent_res.get('label') == 'buyer' and intent_res.get('confidence', 0) > 0.8:
                                l.is_buyer_request = True
                                
                        except Exception as e:
                            self.logger.warning("ai_classification_failed_continuing_with_regex", error=str(e))

                    # Enrich: Extract Vertical, Phone, and City
                    detected_v_name = LeadEnricher.extract_vertical(text)
                    l.vertical = detected_v_name
                    l.phone = LeadEnricher.extract_phone(text)
                    if not l.city: 
                        l.city = LeadEnricher.extract_city(text, l.location)
                    
                    # ── Phase 2: Hybrid Vertical Validation ──────────────────
                    # If we have user verticals, only pass leads that match the vertical
                    if user_allowed_slugs and mapper:
                        detected_slug = mapper._resolve_vertical_slug(detected_v_name) if detected_v_name else "unknown"
                        if detected_slug not in user_allowed_slugs:
                            self.logger.debug("hybrid_filter_vertical_mismatch", 
                                             url=getattr(l, 'source_url', ''), 
                                             detected=detected_slug, 
                                             allowed=user_allowed_slugs)
                            continue
                    
                    final_leads.append(l)
                
                self.logger.info("hybrid_filter_complete", 
                                 intent_only=len(intent_leads), 
                                 after_vertical_match=len(final_leads))

                # JSON Backup for audit trail
                path = os.path.join(os.getcwd(), "scraped_data")
                os.makedirs(path, exist_ok=True)
                fname = os.path.join(path, f"{self.name}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json")
                with open(fname, 'w') as f: 
                    json.dump([l.model_dump(mode='json') for l in final_leads], f, indent=2)
                
                # 5. Save enriched leads to Final Data collection
                if save and final_leads:
                    self.save_leads(final_leads, f"{self.name.capitalize()}_final_data")
            
            self.complete_job("completed")
            return final_leads
        except Exception as e:
            self.complete_job("failed", e); raise
