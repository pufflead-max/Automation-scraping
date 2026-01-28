"""
Unit tests for data models.
"""

import pytest
from datetime import datetime
from pydantic import ValidationError


def test_scraped_lead_creation():
    """Test creating a basic scraped lead."""
    from scraper.src.models import ScrapedLead
    
    lead = ScrapedLead(
        source="test",
        source_url="https://example.com/test"
    )
    
    assert lead.source == "test"
    assert lead.source_url == "https://example.com/test"
    assert isinstance(lead.scraped_date, datetime)


def test_craigslist_lead_creation():
    """Test creating a Craigslist lead."""
    from scraper.src.models import CraigslistLead
    
    lead = CraigslistLead(
        source_url="https://boston.craigslist.org/test/123",
        title="Test Listing",
        location="Boston, MA",
        category="automotive"
    )
    
    assert lead.source == "craigslist"
    assert lead.title == "Test Listing"
    assert lead.location == "Boston, MA"


def test_email_validation():
    """Test email validation and normalization."""
    from scraper.src.models import ScrapedLead
    
    # Valid email
    lead = ScrapedLead(
        source="test",
        source_url="https://example.com",
        contact_email="Test@Example.COM"
    )
    assert lead.contact_email == "test@example.com"  # Normalized
    
    # Invalid email
    lead = ScrapedLead(
        source="test",
        source_url="https://example.com",
        contact_email="not-an-email"
    )
    assert lead.contact_email is None  # Invalid emails become None


def test_phone_validation():
    """Test phone number validation and normalization."""
    from scraper.src.models import ScrapedLead
    
    # Valid US phone
    lead = ScrapedLead(
        source="test",
        source_url="https://example.com",
        contact_phone="(555) 123-4567"
    )
    assert lead.contact_phone == "+15551234567"  # E164 format
    
    # Invalid phone
    lead = ScrapedLead(
        source="test",
        source_url="https://example.com",
        contact_phone="123"  # Too short
    )
    assert lead.contact_phone == "123"  # Returns original if invalid


def test_scrape_job_creation():
    """Test creating a scrape job."""
    from scraper.src.models import ScrapeJob
    
    job = ScrapeJob(
        job_id="test-123",
        scraper="craigslist",
        status="started",
        target="https://example.com"
    )
    
    assert job.job_id == "test-123"
    assert job.scraper == "craigslist"
    assert job.status == "started"
    assert job.items_found == 0
    assert isinstance(job.started_at, datetime)


def test_lead_json_serialization():
    """Test that leads can be serialized to JSON."""
    from scraper.src.models import CraigslistLead
    
    lead = CraigslistLead(
        source_url="https://example.com",
        title="Test",
        posted_date=datetime(2026, 1, 15, 12, 0, 0)
    )
    
    json_str = lead.model_dump_json()
    assert '"source":"craigslist"' in json_str
    assert '"title":"Test"' in json_str


if __name__ == "__main__":
    pytest.main([__file__, '-v'])
