"""Data validator for scraped leads."""

from typing import List, Dict
from ..models import ScrapedLead
from ..logger import get_logger

logger = get_logger(__name__)


class DataValidator:
    """Validates scraped lead data for quality and completeness."""
    
    def __init__(self, strict: bool = False):
        self.strict = strict
        self.validation_stats = {'total': 0, 'valid': 0, 'invalid': 0, 'warnings': 0}
    
    def validate_lead(self, lead: ScrapedLead) -> bool:
        """Validate a single lead."""
        self.validation_stats['total'] += 1
        issues = []
        
        if not lead.source_url:
            issues.append("Missing source_url")
        if not lead.source:
            issues.append("Missing source")
        if lead.title and len(lead.title) < 3:
            issues.append(f"Title too short: '{lead.title}'")
        if lead.contact_email and '@' not in lead.contact_email:
            issues.append(f"Invalid email format: '{lead.contact_email}'")
        if lead.contact_phone and len(lead.contact_phone) < 10:
            issues.append(f"Phone number too short: '{lead.contact_phone}'")
        
        if issues:
            if self.strict:
                self.validation_stats['invalid'] += 1
                logger.warning("lead_validation_failed", source_url=lead.source_url, issues=issues)
                return False
            self.validation_stats['warnings'] += 1
            logger.debug("lead_validation_warnings", source_url=lead.source_url, issues=issues)
        
        self.validation_stats['valid'] += 1
        return True
    
    def validate_batch(self, leads: List[ScrapedLead]) -> List[ScrapedLead]:
        """Validate a batch of leads."""
        valid_leads = [lead for lead in leads if self.validate_lead(lead)]
        logger.info("batch_validation_complete", **self.validation_stats)
        return valid_leads
    
    def get_stats(self) -> Dict[str, int]:
        """Get validation statistics."""
        return self.validation_stats.copy()
    
    def reset_stats(self) -> None:
        """Reset validation statistics."""
        self.validation_stats = {'total': 0, 'valid': 0, 'invalid': 0, 'warnings': 0}
