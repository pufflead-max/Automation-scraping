"""Centralized configuration management for the scraping system  ."""

from typing import Optional
from pydantic_settings import BaseSettings
from pydantic import Field, field_validator

class Settings(BaseSettings):
    """Application settings loaded from environment variables."""
    mongo_uri: str = Field(..., description="MongoDB URI")
    mongo_db: str = Field(default="PUFF")
    mongo_port: int = Field(default=47018)
    scraperapi_key: Optional[str] = None
    scraperapi_proxy: Optional[str] = None
    scraper_timeout: int = 30
    scraper_max_retries: int = 3
    scraper_retry_delay: int = 5
    log_level: str = "INFO"
    log_format: str = "json"
    ghl_api_key: Optional[str] = None
    ghl_location_id: Optional[str] = None
    
    # Environment based GHL
    ghl_environment: str = Field(default="sandbox")
    ghl_sandbox_api_key: Optional[str] = None
    ghl_sandbox_location_id: Optional[str] = None
    ghl_sandbox_crm_url: str = "https://services.leadconnectorhq.com"
    ghl_live_api_key: Optional[str] = None
    ghl_live_location_id: Optional[str] = None
    ghl_live_crm_url: str = "https://services.leadconnectorhq.com"

    airflow_executor: str = "LocalExecutor"

    @field_validator('log_level')
    @classmethod
    def validate_log_level(cls, v: str) -> str:
        v = v.upper()
        if v not in ['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL']:
            raise ValueError("Invalid log_level")
        return v
    
    @field_validator('log_format')
    @classmethod
    def validate_log_format(cls, v: str) -> str:
        if (v := v.lower()) not in ['json', 'text']:
            raise ValueError("log_format must be 'json' or 'text'")
        return v
    
    class Config:
        import os
        env_file = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), ".env")
        extra = "ignore"

_settings: Optional[Settings] = None

def get_settings() -> Settings:
    global _settings
    if not _settings: _settings = Settings()
    return _settings

def reload_settings() -> Settings:
    global _settings
    _settings = Settings()
    return _settings

def get_mongo_uri() -> str: return get_settings().mongo_uri
def get_mongo_db() -> str: return get_settings().mongo_db
def get_ghl_config() -> dict:
    s = get_settings()
    if s.ghl_environment.lower() == "live":
        return {
            "api_key": s.ghl_live_api_key or s.ghl_api_key, 
            "location_id": s.ghl_live_location_id or s.ghl_location_id,
            "crm_url": s.ghl_live_crm_url,
            "environment": "live"
        }
    return {
        "api_key": s.ghl_sandbox_api_key or s.ghl_api_key, 
        "location_id": s.ghl_sandbox_location_id or s.ghl_location_id,
        "crm_url": s.ghl_sandbox_crm_url,
        "environment": "sandbox"
    }

def get_scraper_config() -> dict:
    s = get_settings()
    return {"timeout": s.scraper_timeout, "max_retries": s.scraper_max_retries,
            "retry_delay": s.scraper_retry_delay, "scraperapi_key": s.scraperapi_key,
            "scraperapi_proxy": s.scraperapi_proxy}
