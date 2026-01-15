"""
Data validator for scraped leads.
Validates data quality and completeness before saving to database.
"""

from typing import List, Dict, Any, Optional
from pydantic import ValidationError

from ..models import ScrapedLead
from ..logger import get_logger

logger = get_logger(__name__)


class DataValidator:
    """
    Validates scraped lead data for quality and completeness.
    """
    
    def __init__(self, strict: bool = False):
        """
        Initialize validator.
        
        Args:
            strict: If True, reject leads with any validation errors.
                   If False, log warnings but allow partial data.
        """
        self.strict = strict
        self.validation_stats = {
            'total': 0,
            'valid': 0,
            'invalid': 0,
            'warnings': 0
        }
    
    def validate_lead(self, lead: ScrapedLead) -> bool:
        """
        Validate a single lead.
        
        Args:
            lead: Lead to validate
        
        Returns:
            bool: True if lead is valid, False otherwise
        """
        self.validation_stats['total'] += 1
        
        issues = []
        
        # Required fields check
        if not lead.source_url:
            issues.append("Missing source_url")
        
        if not lead.source:
            issues.append("Missing source")
        
        # Data quality checks
        if lead.title and len(lead.title) < 3:
            issues.append(f"Title too short: '{lead.title}'")
        
        if lead.contact_email and '@' not in lead.contact_email:
            issues.append(f"Invalid email format: '{lead.contact_email}'")
        
        if lead.contact_phone and len(lead.contact_phone) < 10:
            issues.append(f"Phone number too short: '{lead.contact_phone}'")
        
        # Log issues
        if issues:
            if self.strict:
                self.validation_stats['invalid'] += 1
                logger.warning(
                    "lead_validation_failed",
                    source_url=lead.source_url,
                    issues=issues
                )
                return False
            else:
                self.validation_stats['warnings'] += 1
                logger.debug(
                    "lead_validation_warnings",
                    source_url=lead.source_url,
                    issues=issues
                )
        
        self.validation_stats['valid'] += 1
        return True
    
    def validate_batch(self, leads: List[ScrapedLead]) -> List[ScrapedLead]:
        """
        Validate a batch of leads.
        
        Args:
            leads: List of leads to validate
        
        Returns:
            List[ScrapedLead]: List of valid leads
        """
        valid_leads = []
        
        for lead in leads:
            if self.validate_lead(lead):
                valid_leads.append(lead)
        
        logger.info(
            "batch_validation_complete",
            total=self.validation_stats['total'],
            valid=self.validation_stats['valid'],
            invalid=self.validation_stats['invalid'],
            warnings=self.validation_stats['warnings']
        )
        
        return valid_leads
    
    def get_stats(self) -> Dict[str, int]:
        """
        Get validation statistics.
        
        Returns:
            Dict: Validation statistics
        """
        return self.validation_stats.copy()
    
    def reset_stats(self) -> None:
        """Reset validation statistics."""
        self.validation_stats = {
            'total': 0,
            'valid': 0,
            'invalid': 0,
            'warnings': 0
        }


if __name__ == "__main__":
    # Test validator
    from ..models import CraigslistLead
    
    print("Testing DataValidator...")
    
    validator = DataValidator(strict=False)
    
    # Valid lead
    lead1 = CraigslistLead(
        source_url="https://example.com/1",
        title="Test Lead",
        contact_email="test@example.com"
    )
    
    # Invalid lead (missing required fields)
    lead2 = CraigslistLead(
        source_url="",
        title="X"  # Too short
    )
    
    results = validator.validate_batch([lead1, lead2])
    
    print(f"\nValidation results:")
    print(f"  Total: {validator.validation_stats['total']}")
    print(f"  Valid: {validator.validation_stats['valid']}")
    print(f"  Invalid: {validator.validation_stats['invalid']}")
    print(f"  Warnings: {validator.validation_stats['warnings']}")
