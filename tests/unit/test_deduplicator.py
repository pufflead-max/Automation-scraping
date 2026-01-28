"""
Unit tests for deduplication.
"""

import pytest


def test_deduplicator_detects_url_duplicates():
    """Test that deduplicator detects duplicate URLs."""
    from scraper.src.processors.deduplicator import LeadDeduplicator
    from scraper.src.models import CraigslistLead
    
    deduplicator = LeadDeduplicator()
    
    lead1 = CraigslistLead(
        source_url="https://example.com/1",
        title="Lead 1"
    )
    
    lead2 = CraigslistLead(
        source_url="https://example.com/1",  # Same URL
        title="Lead 1 Duplicate"
    )
    
    leads = [lead1, lead2]
    unique = deduplicator.deduplicate_batch(leads, check_database=False)
    
    assert len(unique) == 1
    assert deduplicator.dedup_stats['duplicates'] == 1


def test_deduplicator_detects_content_duplicates():
    """Test that deduplicator detects duplicate content."""
    from scraper.src.processors.deduplicator import LeadDeduplicator
    from scraper.src.models import CraigslistLead
    
    deduplicator = LeadDeduplicator()
    
    lead1 = CraigslistLead(
        source_url="https://example.com/1",
        title="Same Title",
        description="Same description",
        location="Boston"
    )
    
    lead2 = CraigslistLead(
        source_url="https://example.com/2",  # Different URL
        title="Same Title",  # But same content
        description="Same description",
        location="Boston"
    )
    
    leads = [lead1, lead2]
    unique = deduplicator.deduplicate_batch(leads, check_database=False)
    
    assert len(unique) == 1
    assert deduplicator.dedup_stats['duplicates'] == 1


def test_deduplicator_keeps_unique_leads():
    """Test that deduplicator keeps unique leads."""
    from scraper.src.processors.deduplicator import LeadDeduplicator
    from scraper.src.models import CraigslistLead
    
    deduplicator = LeadDeduplicator()
    
    leads = [
        CraigslistLead(source_url="https://example.com/1", title="Lead 1"),
        CraigslistLead(source_url="https://example.com/2", title="Lead 2"),
        CraigslistLead(source_url="https://example.com/3", title="Lead 3"),
    ]
    
    unique = deduplicator.deduplicate_batch(leads, check_database=False)
    
    assert len(unique) == 3
    assert deduplicator.dedup_stats['unique'] == 3
    assert deduplicator.dedup_stats['duplicates'] == 0


def test_content_hash_generation():
    """Test content hash generation."""
    from scraper.src.processors.deduplicator import LeadDeduplicator
    from scraper.src.models import CraigslistLead
    
    lead1 = CraigslistLead(
        source_url="https://example.com/1",
        title="Test",
        description="Description"
    )
    
    lead2 = CraigslistLead(
        source_url="https://example.com/2",
        title="Test",
        description="Description"
    )
    
    hash1 = LeadDeduplicator.generate_content_hash(lead1)
    hash2 = LeadDeduplicator.generate_content_hash(lead2)
    
    assert hash1 == hash2  # Same content should have same hash
    assert len(hash1) == 64  # SHA256 hash length


if __name__ == "__main__":
    pytest.main([__file__, '-v'])
