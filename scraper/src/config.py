"""Centralized configuration management for the scraping system."""

from typing import Optional
from pydantic_settings import BaseSettings
from pydantic import Field, field_validator


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""
    
    mongo_uri: str = Field(..., description="MongoDB connection URI")
    mongo_db: str = Field(default="PUFF", description="MongoDB database name")
    mongo_port: int = Field(default=47018, description="MongoDB external port")
    
    scraperapi_key: Optional[str] = Field(default=None, description="ScraperAPI key for proxy")
    scraperapi_proxy: Optional[str] = Field(default=None, description="ScraperAPI proxy URL")
    
    scraper_timeout: int = Field(default=30, description="Request timeout in seconds")
    scraper_max_retries: int = Field(default=3, description="Maximum retry attempts")
    scraper_retry_delay: int = Field(default=5, description="Delay between retries in seconds")
    
    log_level: str = Field(default="INFO", description="Logging level")
    log_format: str = Field(default="json", description="Log format: json or text")
    
    ghl_api_key: Optional[str] = Field(default=None, description="GoHighLevel API Key")
    ghl_location_id: Optional[str] = Field(default=None, description="GoHighLevel Location ID")
    
    airflow_executor: str = Field(default="LocalExecutor", description="Airflow executor type")
    
    @field_validator('log_level')
    @classmethod
    def validate_log_level(cls, v: str) -> str:
        v = v.upper()
        if v not in ['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL']:
            raise ValueError(f"log_level must be one of DEBUG, INFO, WARNING, ERROR, CRITICAL")
        return v
    
    @field_validator('log_format')
    @classmethod
    def validate_log_format(cls, v: str) -> str:
        if (v := v.lower()) not in ['json', 'text']:
            raise ValueError("log_format must be 'json' or 'text'")
        return v
    
    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = False
        extra = "ignore"


_settings: Optional[Settings] = None


def get_settings() -> Settings:
    """Get the global settings instance."""
    global _settings
    if _settings is None:
        _settings = Settings()
    return _settings


def reload_settings() -> Settings:
    """Force reload settings from environment."""
    global _settings
    _settings = Settings()
    return _settings


def get_mongo_uri() -> str:
    """Get MongoDB connection URI."""
    return get_settings().mongo_uri


def get_mongo_db() -> str:
    """Get MongoDB database name."""
    return get_settings().mongo_db


def get_ghl_config() -> dict:
    """Get GoHighLevel configuration."""
    s = get_settings()
    return {
        "api_key": s.ghl_api_key,
        "location_id": s.ghl_location_id
    }


def get_scraper_config() -> dict:
    """Get scraper-specific configuration as a dictionary."""
    s = get_settings()
    return {"timeout": s.scraper_timeout, "max_retries": s.scraper_max_retries,
            "retry_delay": s.scraper_retry_delay, "scraperapi_key": s.scraperapi_key,
            "scraperapi_proxy": s.scraperapi_proxy}


