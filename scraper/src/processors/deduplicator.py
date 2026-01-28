"""Lead deduplicator to prevent storing duplicate leads  ."""

import hashlib
from typing import List, Dict, Any, Optional
from datetime import datetime, timedelta
from ..models import ScrapedLead
from ..database import DatabaseManager, get_db_manager
from ..logger import get_logger

logger = get_logger(__name__)

class LeadDeduplicator:
    def __init__(self, db: Optional[DatabaseManager] = None):
        self.db, self.urls, self.hashes = db or get_db_manager(), set(), set()
        self.stats = {'total': 0, 'unique': 0, 'dupes': 0, 'db_dupes': 0}
    
    @staticmethod
    def gen_hash(l: ScrapedLead) -> str:
        return hashlib.sha256(f"{l.title}|{l.description}|{l.location}".lower().strip().encode()).hexdigest()
    
    def is_dupe_mem(self, l: ScrapedLead) -> bool:
        if l.source_url in self.urls or (h := self.gen_hash(l)) in self.hashes: return True
        self.urls.add(l.source_url); self.hashes.add(h); return False
    
    def is_dupe_db(self, l: ScrapedLead, col: str = "leads", days: int = 30) -> bool:
        try:
            if self.db.find_one(col, {"source_url": l.source_url}): return True
            cutoff = datetime.utcnow() - timedelta(days=days)
            return bool(self.db.find_one(col, {"scraped_date": {"$gte": cutoff}, "source": l.source}))
        except: return False
    
    def deduplicate(self, leads: List[ScrapedLead], check_db: bool = True, col: str = "leads") -> List[ScrapedLead]:
        unique = []
        for l in leads:
            self.stats['total'] += 1
            if self.is_dupe_mem(l): self.stats['dupes'] += 1
            elif check_db and self.is_dupe_db(l, col): self.stats['db_dupes'] += 1
            else:
                self.stats['unique'] += 1
                unique.append(l)
        logger.info("dedup_complete", **self.stats)
        return unique
    
    def reset(self):
        self.urls.clear(); self.hashes.clear()
        self.stats = {'total': 0, 'unique': 0, 'dupes': 0, 'db_dupes': 0}
