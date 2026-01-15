"""
Unit tests for data validation.
"""

import pytest


def test_validator_accepts_valid_lead():
    """Test that validator accepts valid leads."""
    from scraper.src.processors.validator import DataValidator
    from scraper.src.models import CraigslistLead
    
    validator = DataValidator(strict=False)
    
    lead = CraigslistLead(
        source_url="https://example.com/test",
        title="Valid Test Lead",
        contact_email="test@example.com",
        contact_phone="+15551234567"
    )
    
    assert validator.validate_lead(lead) == True
    assert validator.validation_stats['valid'] == 1
    assert validator.validation_stats['invalid'] == 0


def test_validator_rejects_invalid_lead_strict():
    """Test that validator rejects invalid leads in strict mode."""
    from scraper.src.processors.validator import DataValidator
    from scraper.src.models import CraigslistLead
    
    validator = DataValidator(strict=True)
    
    lead = CraigslistLead(
        source_url="",  # Missing required field
        title="X"  # Too short
    )
    
    assert validator.validate_lead(lead) == False
    assert validator.validation_stats['invalid'] == 1


def test_validator_warns_in_non_strict_mode():
    """Test that validator warns but accepts in non-strict mode."""
    from scraper.src.processors.validator import DataValidator
    from scraper.src.models import CraigslistLead
    
    validator = DataValidator(strict=False)
    
    lead = CraigslistLead(
        source_url="https://example.com",
        title="X"  # Too short - should warn
    )
    
    assert validator.validate_lead(lead) == True
    assert validator.validation_stats['warnings'] == 1


def test_batch_validation():
    """Test validating a batch of leads."""
    from scraper.src.processors.validator import DataValidator
    from scraper.src.models import CraigslistLead
    
    validator = DataValidator(strict=True)
    
    leads = [
        CraigslistLead(source_url="https://example.com/1", title="Valid Lead 1"),
        CraigslistLead(source_url="", title="X"),  # Invalid
        CraigslistLead(source_url="https://example.com/2", title="Valid Lead 2"),
    ]
    
    valid_leads = validator.validate_batch(leads)
    
    assert len(valid_leads) == 2
    assert validator.validation_stats['total'] == 3
    assert validator.validation_stats['valid'] == 2
    assert validator.validation_stats['invalid'] == 1


if __name__ == "__main__":
    pytest.main([__file__, '-v'])
