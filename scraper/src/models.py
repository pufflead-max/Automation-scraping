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
    
    # Location information
    location: Optional[str] = Field(None, description="Location/area")
    city: Optional[str] = Field(None, description="City")
    state: Optional[str] = Field(None, description="State/province")
    
    # Metadata
    category: Optional[str] = Field(None, description="Category/classification")
    subcategory: Optional[str] = Field(None, description="Subcategory")
    posted_date: Optional[datetime] = Field(None, description="When the listing was posted")
    scraped_date: datetime = Field(default_factory=datetime.utcnow, description="When we scraped it")
    
    # Additional data
    images: List[str] = Field(default_factory=list, description="List of image URLs")
    price: Optional[float] = Field(None, description="Price if applicable")
    extra_data: dict = Field(default_factory=dict, description="Platform-specific extra data")
    
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
    topics: List[str] = Field(default_factory=list, description="Post topics")
    is_service_request: bool = Field(default=False, description="Whether this is a service request")


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


class FacebookLead(ScrapedLead):
    """
    Facebook specific lead model.
    """
    source: Literal["facebook"] = "facebook"
    
    # Media
    images: List[str] = Field(default_factory=list, description="List of image URLs")
    videos: List[str] = Field(default_factory=list, description="List of video URLs")
    image_count: int = Field(default=0, ge=0)
    video_count: int = Field(default=0, ge=0)
    has_media: bool = Field(default=False)
    
    # Content metrics
    word_count: int = Field(default=0, ge=0)
