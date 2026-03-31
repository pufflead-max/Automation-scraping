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
    target_url: Optional[str] = Field(None, description="The specific URL/group/page being watched")
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
    is_buyer_request: bool = False
    is_hiring: bool = False
    ollama_result: Optional[bool] = None
    gemini_result: Optional[bool] = None
    is_vertical_match: bool = False
    intent_score: Optional[int] = None
    
    @field_validator('posted_date', mode='before')
    @classmethod
    def parse_posted_date(cls, v: Any) -> Any:
        if not v:
            return None
        if isinstance(v, datetime):
            return v
        if not isinstance(v, str):
            return None

        v = v.strip()
        if not v or v.lower() == "date not found" or v.lower() == "sponsored":
            return None

        import re
        from datetime import timedelta
        from dateutil import parser

        now = datetime.utcnow()

        # 1. Handle "Xh ago", "Xm ago", "Xd ago", "Xw ago" (Craigslist/FB)
        # Patterns like: "2h ago", "6h ago", "10m ago", "2d ago"
        relative_match = re.search(r'(\d+)\s*([mhdw])(\s*ago)?', v, re.IGNORECASE)
        if relative_match:
            amount = int(relative_match.group(1))
            unit = relative_match.group(2).lower()
            res = None
            if unit == 'm': res = now - timedelta(minutes=amount)
            elif unit == 'h': res = now - timedelta(hours=amount)
            elif unit == 'd': res = now - timedelta(days=amount)
            elif unit == 'w': res = now - timedelta(weeks=amount)
            if res:
                return res

        if "just now" in v.lower():
            return now

        # 2. Handle "MM/DD" or "DD/MM" (Craigslist/FB ambiguous formats like 06/03)
        mmdd_match = re.match(r'^(\d{1,2})[/-](\d{1,2})$', v)
        if mmdd_match:
            v1, v2 = int(mmdd_match.group(1)), int(mmdd_match.group(2))
            
            # Try both (Month=v1, Day=v2) and (Month=v2, Day=v1)
            options = []
            for m, d in [(v1, v2), (v2, v1)]:
                if 1 <= m <= 12 and 1 <= d <= 31:
                    try:
                        # Guess year: if month is in the future, assume last year
                        year = now.year
                        if m > now.month or (m == now.month and d > now.day):
                            year -= 1
                        options.append(datetime(year, m, d))
                    except ValueError:
                        continue
            
            if options:
                # Prefer the date closest to 'now' (most recent)
                options.sort(key=lambda x: abs((now - x).total_seconds()))
                return options[0]

        # 3. Handle standard formats with isoformat / dateutil
        try:
            res = datetime.fromisoformat(v.split('.')[0])
            return res
        except (ValueError, TypeError):
            try:
                # dateutil handles "2 hours ago" natively, but we already handled short relative forms
                res = parser.parse(v)
                return res
            except:
                return None
    
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
    has_map: bool = False
    
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
    topics: List[str] = Field(default_factory=list)


class FacebookLead(ScrapedLead):
    """Facebook specific lead model."""
    source: Literal["facebook"] = "facebook"
    author_name: Optional[str] = None
    author_url: Optional[str] = None
    author_location: Optional[str] = None
    videos: List[str] = Field(default_factory=list)
    image_count: int = Field(default=0, ge=0)
    video_count: int = Field(default=0, ge=0)
    has_media: bool = False
    word_count: int = Field(default=0, ge=0)
    word_count: int = Field(default=0, ge=0)


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

