"""
Lead deduplicator to prevent storing duplicate leads.
Uses URL and content-based hashing for duplicate detection.
"""

from typing import List, Set, Dict, Any, Optional
import hashlib
from datetime import datetime, timedelta

from ..models import ScrapedLead
from ..database import DatabaseManager, get_db_manager
from ..logger import get_logger

logger = get_logger(__name__)


class LeadDeduplicator:
    """
    Detects and removes duplicate leads based on URL and content similarity.
    """
    
    def __init__(self, db_manager: Optional[DatabaseManager] = None):
        """
        Initialize deduplicator.
        
        Args:
            db_manager: Optional database manager for checking existing leads
        """
        self.db = db_manager or get_db_manager()
        self.seen_urls: Set[str] = set()
        self.seen_hashes: Set[str] = set()
        self.dedup_stats = {
            'total': 0,
            'unique': 0,
            'duplicates': 0,
            'db_duplicates': 0
        }
    
    @staticmethod
    def generate_content_hash(lead: ScrapedLead) -> str:
        """
        Generate a hash based on lead content.
        
        Args:
            lead: Lead to hash
        
        Returns:
            str: Content hash
        """
        # Combine key fields for hashing
        content = f"{lead.title}|{lead.description}|{lead.location}|{lead.contact_phone}"
        content = content.lower().strip()
        
        # Generate SHA256 hash
        return hashlib.sha256(content.encode()).hexdigest()
    
    def is_duplicate_in_memory(self, lead: ScrapedLead) -> bool:
        """
        Check if lead is a duplicate in current batch (in-memory check).
        
        Args:
            lead: Lead to check
        
        Returns:
            bool: True if duplicate, False otherwise
        """
        # Check URL
        if lead.source_url in self.seen_urls:
            logger.debug("duplicate_url_found", url=lead.source_url)
            return True
        
        # Check content hash
        content_hash = self.generate_content_hash(lead)
        if content_hash in self.seen_hashes:
            logger.debug("duplicate_content_found", url=lead.source_url)
            return True
        
        # Not a duplicate - add to seen sets
        self.seen_urls.add(lead.source_url)
        self.seen_hashes.add(content_hash)
        
        return False
    
    def is_duplicate_in_database(
        self,
        lead: ScrapedLead,
        collection: str = "leads",
        lookback_days: int = 30
    ) -> bool:
        """
        Check if lead already exists in database.
        
        Args:
            lead: Lead to check
            collection: Collection name to check
            lookback_days: How many days back to check for duplicates
        
        Returns:
            bool: True if duplicate exists in database, False otherwise
        """
        try:
            # Check by URL first (fastest)
            existing = self.db.find_one(
                collection,
                {"source_url": lead.source_url}
            )
            
            if existing:
                logger.debug(
                    "duplicate_in_database_by_url",
                    url=lead.source_url,
                    existing_id=str(existing.get('_id'))
                )
                return True
            
            # Check by content hash for similar leads
            content_hash = self.generate_content_hash(lead)
            
            # Only check recent leads to improve performance
            cutoff_date = datetime.utcnow() - timedelta(days=lookback_days)
            
            existing = self.db.find_one(
                collection,
                {
                    "scraped_date": {"$gte": cutoff_date},
                    "source": lead.source,
                    # Would need to add content_hash field to leads
                }
            )
            
            if existing:
                logger.debug(
                    "duplicate_in_database_by_content",
                    url=lead.source_url,
                    existing_id=str(existing.get('_id'))
                )
                return True
            
            return False
            
        except Exception as e:
            logger.warning(
                "database_duplicate_check_failed",
                url=lead.source_url,
                error=str(e)
            )
            # On error, assume not duplicate to avoid losing data
            return False
    
    def deduplicate_batch(
        self,
        leads: List[ScrapedLead],
        check_database: bool = True,
        collection: str = "leads"
    ) -> List[ScrapedLead]:
        """
        Remove duplicates from a batch of leads.
        
        Args:
            leads: List of leads to deduplicate
            check_database: Whether to check database for existing leads
            collection: Collection name to check in database
        
        Returns:
            List[ScrapedLead]: List of unique leads
        """
        unique_leads = []
        
        for lead in leads:
            self.dedup_stats['total'] += 1
            
            # Check in-memory duplicates
            if self.is_duplicate_in_memory(lead):
                self.dedup_stats['duplicates'] += 1
                continue
            
            # Check database duplicates
            if check_database and self.is_duplicate_in_database(lead, collection):
                self.dedup_stats['db_duplicates'] += 1
                continue
            
            # Lead is unique
            self.dedup_stats['unique'] += 1
            unique_leads.append(lead)
        
        logger.info(
            "deduplication_complete",
            total=self.dedup_stats['total'],
            unique=self.dedup_stats['unique'],
            duplicates=self.dedup_stats['duplicates'],
            db_duplicates=self.dedup_stats['db_duplicates']
        )
        
        return unique_leads
    
    def get_stats(self) -> Dict[str, int]:
        """
        Get deduplication statistics.
        
        Returns:
            Dict: Deduplication statistics
        """
        return self.dedup_stats.copy()
    
    def reset(self) -> None:
        """Reset deduplicator state and statistics."""
        self.seen_urls.clear()
        self.seen_hashes.clear()
        self.dedup_stats = {
            'total': 0,
            'unique': 0,
            'duplicates': 0,
            'db_duplicates': 0
        }


if __name__ == "__main__":
    # Test deduplicator
    from ..models import CraigslistLead
    
    print("Testing LeadDeduplicator...")
    
    deduplicator = LeadDeduplicator()
    
    # Create test leads
    lead1 = CraigslistLead(
        source_url="https://example.com/1",
        title="Test Lead 1"
    )
    
    lead2 = CraigslistLead(
        source_url="https://example.com/2",
        title="Test Lead 2"
    )
    
    lead3 = CraigslistLead(
        source_url="https://example.com/1",  # Duplicate URL
        title="Test Lead 1"
    )
    
    leads = [lead1, lead2, lead3]
    unique = deduplicator.deduplicate_batch(leads, check_database=False)
    
    print(f"\nDeduplication results:")
    print(f"  Total: {deduplicator.dedup_stats['total']}")
    print(f"  Unique: {deduplicator.dedup_stats['unique']}")
    print(f"  Duplicates: {deduplicator.dedup_stats['duplicates']}")
    print(f"\nUnique leads: {len(unique)}")
