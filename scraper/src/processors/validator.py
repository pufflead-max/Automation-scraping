"""Data validator for scraped leads  ."""

from typing import List, Dict
from ..models import ScrapedLead
from ..logger import get_logger

logger = get_logger(__name__)

class DataValidator:
    def __init__(self, strict: bool = False):
        self.strict, self.stats = strict, {'total': 0, 'valid': 0, 'invalid': 0, 'warns': 0}
    
    def validate(self, l: ScrapedLead) -> bool:
        self.stats['total'] += 1
        issues = []
        if not l.source_url: issues.append("Missing source_url")
        if not l.source: issues.append("Missing source")
        if l.title and len(l.title) < 3: issues.append("Title too short")
        if l.phone and len(l.phone) < 7: issues.append("Phone too short")
        
        if issues:
            if self.strict:
                self.stats['invalid'] += 1
                logger.warning("validation_failed", url=l.source_url, issues=issues)
                return False
            self.stats['warns'] += 1
        
        self.stats['valid'] += 1
        return True
    
    def validate_batch(self, leads: List[ScrapedLead]) -> List[ScrapedLead]:
        res = [l for l in leads if self.validate(l)]
        logger.info("validation_complete", **self.stats)
        return res
    
    def reset(self): self.stats = {'total': 0, 'valid': 0, 'invalid': 0, 'warns': 0}
