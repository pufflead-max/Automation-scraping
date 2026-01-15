"""
Pydantic data models for scraped data validation.
Ensures data quality and consistency across all scrapers.
"""

from typing import Optional, List, Dict, Any, Literal
from datetime import datetime
from pydantic import BaseModel, Field, EmailStr, field_validator, ConfigDict
import re
import html
import phonenumbers
from email_validator import validate_email, EmailNotValidError


class ScrapedLead(BaseModel):
    """Base model for all scraped leads."""
    
    # Source information
    source: str = Field(..., description="Source platform (e.g., 'craigslist', 'nextdoor')")
    source_url: str = Field(..., description="URL of the listing")
    source_id: Optional[str] = Field(None, description="Unique ID from source platform")
    
    # Lead information
    title: Optional[str] = Field(None, description="Title or subject of the listing")
    description: Optional[str] = Field(None, description="Full description/body text")
    
    # Contact information
    contact_name: Optional[str] = Field(None, description="Contact person name")
    contact_email: Optional[str] = Field(None, description="Contact email")
    contact_phone: Optional[str] = Field(None, description="Contact phone number")
    
    # Location information
    location: Optional[str] = Field(None, description="Location/area")
    city: Optional[str] = Field(None, description="City")
    state: Optional[str] = Field(None, description="State/province")
    zip_code: Optional[str] = Field(None, description="ZIP/postal code")
    
    # Metadata
    category: Optional[str] = Field(None, description="Category/classification")
    subcategory: Optional[str] = Field(None, description="Subcategory")
    posted_date: Optional[datetime] = Field(None, description="When the listing was posted")
    scraped_date: datetime = Field(default_factory=datetime.utcnow, description="When we scraped it")
    
    # Additional data
    images: List[str] = Field(default_factory=list, description="List of image URLs")
    price: Optional[float] = Field(None, description="Price if applicable")
    extra_data: dict = Field(default_factory=dict, description="Platform-specific extra data")
    
    @field_validator('contact_email')
    @classmethod
    def validate_email_format(cls, v: Optional[str]) -> Optional[str]:
        """Validate email format if provided."""
        if v is None or v.strip() == "":
            return None
        try:
            # Validate and normalize email
            valid = validate_email(v, check_deliverability=False)
            return valid.normalized
        except EmailNotValidError:
            # Return None for invalid emails rather than raising
            return None
    
    @field_validator('contact_phone')
    @classmethod
    def validate_phone_format(cls, v: Optional[str]) -> Optional[str]:
        """Validate and normalize phone number if provided."""
        if v is None or v.strip() == "":
            return None
        try:
            # Try to parse as US number by default
            parsed = phonenumbers.parse(v, "US")
            if phonenumbers.is_valid_number(parsed):
                # Return in E164 format
                return phonenumbers.format_number(parsed, phonenumbers.PhoneNumberFormat.E164)
            return v  # Return original if not valid
        except:
            return v  # Return original if parsing fails
    
    class Config:
        """Pydantic configuration."""
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }


class CraigslistLead(ScrapedLead):
    """
    Craigslist specific lead model.
    """
    source: Literal["craigslist"] = "craigslist"
    price: Optional[str] = Field(None, description="Listing price")
    neighborhood: Optional[str] = Field(None, description="Neighborhood")
    map_address: Optional[str] = Field(None, description="Address from map")
    has_image: bool = Field(default=False, description="Has images")
    has_map: bool = Field(default=False, description="Has map")
    
    @field_validator('price')
    @classmethod
    def clean_price(cls, v: Optional[str]) -> Optional[str]:
        if v and v == '$0':
            return None
        return v


class NextdoorLead(ScrapedLead):
    """
    Nextdoor specific lead model.
    """
    source: Literal["nextdoor"] = "nextdoor"
    author_name: Optional[str] = Field(None, description="Post author name")
    author_url: Optional[str] = Field(None, description="Post author profile URL")
    neighborhood: Optional[str] = Field(None, description="Neighborhood name")
    city: Optional[str] = Field(None, description="City")
    state: Optional[str] = Field(None, description="State")
    
    # Engagement metrics
    comment_count: int = Field(default=0, ge=0)
    reaction_count: int = Field(default=0, ge=0)
    
    # Content specifics
    images: List[str] = Field(default_factory=list)
    tagged_business: Optional[str] = Field(None, description="Tagged business name")
    tagged_business_category: Optional[str] = Field(None, description="Business category")


class ScrapeJob(BaseModel):
    """Model for tracking scrape job metadata."""
    
    job_id: str = Field(..., description="Unique job identifier")
    scraper: str = Field(..., description="Scraper name")
    status: str = Field(..., description="Job status: started, running, completed, failed")
    
    target: Optional[str] = Field(None, description="Target URL or identifier")
    category: Optional[str] = Field(None, description="Category being scraped")
    
    started_at: datetime = Field(default_factory=datetime.utcnow)
    completed_at: Optional[datetime] = None
    
    items_found: int = Field(default=0, description="Number of items found")
    items_saved: int = Field(default=0, description="Number of items saved")
    items_failed: int = Field(default=0, description="Number of items that failed")
    
    error_message: Optional[str] = Field(None, description="Error message if failed")
    error_type: Optional[str] = Field(None, description="Error type if failed")
    
    class Config:
        """Pydantic configuration."""
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }


class ScraperMetrics(BaseModel):
    """Model for scraper performance metrics."""
    
    scraper: str
    date: datetime = Field(default_factory=datetime.utcnow)
    
    total_runs: int = 0
    successful_runs: int = 0
    failed_runs: int = 0
    
    total_items_scraped: int = 0
    total_items_saved: int = 0
    total_items_failed: int = 0
    
    average_runtime_seconds: float = 0.0
    average_items_per_run: float = 0.0
    
    class Config:
        """Pydantic configuration."""
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }


if __name__ == "__main__":
    # Test models
    print("Testing data models...")
    
    # Test CraigslistLead
    lead = CraigslistLead(
        source_url="https://boston.craigslist.org/test/123",
        title="Test Lead",
        description="Test description",
        contact_email="test@example.com",
        contact_phone="+1-555-123-4567",
        location="Boston, MA",
        category="automotive"
    )
    
    print(f"✓ CraigslistLead created: {lead.title}")
    print(f"  Email normalized: {lead.contact_email}")
    print(f"  Phone normalized: {lead.contact_phone}")
    
    # Test JSON serialization
    json_data = lead.model_dump_json(indent=2)
    print(f"\n✓ JSON serialization works")
    
    # Test ScrapeJob
    job = ScrapeJob(
        job_id="test-job-123",
        scraper="craigslist",
        status="completed",
        items_found=100,
        items_saved=95
    )
    
    print(f"\n✓ ScrapeJob created: {job.job_id}")
    print(f"  Success rate: {job.items_saved}/{job.items_found}")
