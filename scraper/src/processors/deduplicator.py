"""Lead deduplicator to prevent storing duplicate leads."""

from typing import List, Set, Dict, Any, Optional
import hashlib
from datetime import datetime, timedelta

from ..models import ScrapedLead
from ..database import DatabaseManager, get_db_manager
from ..logger import get_logger

logger = get_logger(__name__)


class LeadDeduplicator:
    """Detects and removes duplicate leads based on URL and content similarity."""
    
    def __init__(self, db_manager: Optional[DatabaseManager] = None):
        self.db = db_manager or get_db_manager()
        self.seen_urls: Set[str] = set()
        self.seen_hashes: Set[str] = set()
        self.dedup_stats = {'total': 0, 'unique': 0, 'duplicates': 0, 'db_duplicates': 0}
    
    @staticmethod
    def generate_content_hash(lead: ScrapedLead) -> str:
        """Generate a hash based on lead content."""
        content = f"{lead.title}|{lead.description}|{lead.location}|{lead.contact_phone}".lower().strip()
        return hashlib.sha256(content.encode()).hexdigest()
    
    def is_duplicate_in_memory(self, lead: ScrapedLead) -> bool:
        """Check if lead is a duplicate in current batch (in-memory check)."""
        if lead.source_url in self.seen_urls:
            logger.debug("duplicate_url_found", url=lead.source_url)
            return True
        
        if (content_hash := self.generate_content_hash(lead)) in self.seen_hashes:
            logger.debug("duplicate_content_found", url=lead.source_url)
            return True
        
        self.seen_urls.add(lead.source_url)
        self.seen_hashes.add(content_hash)
        return False
    
    def is_duplicate_in_database(self, lead: ScrapedLead, collection: str = "leads", 
                                lookback_days: int = 30) -> bool:
        """Check if lead already exists in database."""
        try:
            if existing := self.db.find_one(collection, {"source_url": lead.source_url}):
                logger.debug("duplicate_in_database_by_url", url=lead.source_url, 
                           existing_id=str(existing.get('_id')))
                return True
            
            cutoff_date = datetime.utcnow() - timedelta(days=lookback_days)
            if existing := self.db.find_one(collection, {"scraped_date": {"$gte": cutoff_date}, 
                                                        "source": lead.source}):
                logger.debug("duplicate_in_database_by_content", url=lead.source_url,
                           existing_id=str(existing.get('_id')))
                return True
            
            return False
        except Exception as e:
            logger.warning("database_duplicate_check_failed", url=lead.source_url, error=str(e))
            return False
    
    def deduplicate_batch(self, leads: List[ScrapedLead], check_database: bool = True,
                         collection: str = "leads") -> List[ScrapedLead]:
        """Remove duplicates from a batch of leads."""
        unique_leads = []
        
        for lead in leads:
            self.dedup_stats['total'] += 1
            
            if self.is_duplicate_in_memory(lead):
                self.dedup_stats['duplicates'] += 1
            elif check_database and self.is_duplicate_in_database(lead, collection):
                self.dedup_stats['db_duplicates'] += 1
            else:
                self.dedup_stats['unique'] += 1
                unique_leads.append(lead)
        
        logger.info("deduplication_complete", **self.dedup_stats)
        return unique_leads
    
    def get_stats(self) -> Dict[str, int]:
        """Get deduplication statistics."""
        return self.dedup_stats.copy()
    
    def reset(self) -> None:
        """Reset deduplicator state and statistics."""
        self.seen_urls.clear()
        self.seen_hashes.clear()
        self.dedup_stats = {'total': 0, 'unique': 0, 'duplicates': 0, 'db_duplicates': 0}
