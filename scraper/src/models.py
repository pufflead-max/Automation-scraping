"""
Pydantic data models for scraped data validation  .
Ensures data quality and consistency across all scrapers.
"""

from typing import Optional, List, Dict, Any, Literal
from datetime import datetime
from pydantic import BaseModel, Field, field_validator, ConfigDict


class ScrapedLead(BaseModel):
    """Base model for all scraped leads."""
    model_config = ConfigDict(json_encoders={datetime: lambda v: v.isoformat()})
    
    source: str = Field(..., description="Source platform")
    source_url: str = Field(..., description="URL of the listing")
    source_id: Optional[str] = None
    title: Optional[str] = None
    description: Optional[str] = None
    location: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    category: Optional[str] = None
    subcategory: Optional[str] = None
    posted_date: Optional[datetime] = None
    scraped_date: datetime = Field(default_factory=datetime.utcnow)
    images: List[str] = Field(default_factory=list)
    price: Optional[float] = None
    extra_data: dict = Field(default_factory=dict)
    phone: Optional[str] = None
    vertical: Optional[str] = None
    
    @field_validator('posted_date', mode='before')
    @classmethod
    def parse_posted_date(cls, v: Any) -> Any:
        if isinstance(v, str):
            try:
                # Handle Craigslist format: "2024-02-11 12:34:56"
                return datetime.fromisoformat(v.split('.')[0])
            except (ValueError, TypeError):
                try:
                    # Try simpler format if isoformat fails
                    from dateutil import parser
                    return parser.parse(v)
                except:
                    return None
        return v
    
    # User association fields for multi-user support
    user_email: Optional[str] = Field(None, description="Email of the user who owns this lead")
    user_name: Optional[str] = Field(None, description="Name of the user who owns this lead")
    user_phone: Optional[str] = Field(None, description="Phone of the user who owns this lead")


class CraigslistLead(ScrapedLead):
    """Craigslist specific lead model."""
    source: Literal["craigslist"] = "craigslist"
    price: Optional[str] = None
    neighborhood: Optional[str] = None
    map_address: Optional[str] = None
    has_image: bool = False
    has_map: bool = False
    is_buyer_request: bool = False
    
    @field_validator('price')
    @classmethod
    def clean_price(cls, v: Optional[str]) -> Optional[str]:
        return None if v == '$0' else v


class NextdoorLead(ScrapedLead):
    """Nextdoor specific lead model."""
    source: Literal["nextdoor"] = "nextdoor"
    author_name: Optional[str] = None
    author_url: Optional[str] = None
    neighborhood: Optional[str] = None
    comment_count: int = Field(default=0, ge=0)
    reaction_count: int = Field(default=0, ge=0)
    tagged_business: Optional[str] = None
    tagged_business_category: Optional[str] = None
    topics: List[str] = Field(default_factory=list)
    is_service_request: bool = False


class FacebookLead(ScrapedLead):
    """Facebook specific lead model."""
    source: Literal["facebook"] = "facebook"
    videos: List[str] = Field(default_factory=list)
    image_count: int = Field(default=0, ge=0)
    video_count: int = Field(default=0, ge=0)
    has_media: bool = False
    word_count: int = Field(default=0, ge=0)
    is_buyer_request: bool = False


class ScrapeJob(BaseModel):
    """Model for tracking scrape job metadata."""
    model_config = ConfigDict(json_encoders={datetime: lambda v: v.isoformat()})
    
    job_id: str
    scraper: str
    status: str # started, running, completed, failed
    target: Optional[str] = None
    category: Optional[str] = None
    started_at: datetime = Field(default_factory=datetime.utcnow)
    completed_at: Optional[datetime] = None
    items_found: int = 0
    items_saved: int = 0
    items_failed: int = 0
    error_message: Optional[str] = None
    error_type: Optional[str] = None


class ScraperMetrics(BaseModel):
    """Model for scraper performance metrics."""
    model_config = ConfigDict(json_encoders={datetime: lambda v: v.isoformat()})
    
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
