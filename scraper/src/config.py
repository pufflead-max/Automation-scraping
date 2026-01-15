"""
Centralized configuration management for the scraping system.
Loads configuration from environment variables with validation.
"""

import os
from typing import Optional
from pydantic_settings import BaseSettings
from pydantic import Field, field_validator


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""
    
    # ============================================
    # MONGODB CONFIGURATION
    # ============================================
    mongo_uri: str = Field(..., description="MongoDB connection URI")
    mongo_db: str = Field(default="PUFF", description="MongoDB database name")
    mongo_port: int = Field(default=47018, description="MongoDB external port")
    
    # ============================================
    # SCRAPER CONFIGURATION
    # ============================================
    scraperapi_key: Optional[str] = Field(default=None, description="ScraperAPI key for proxy")
    scraperapi_proxy: Optional[str] = Field(default=None, description="ScraperAPI proxy URL")
    
    scraper_timeout: int = Field(default=30, description="Request timeout in seconds")
    scraper_max_retries: int = Field(default=3, description="Maximum retry attempts")
    scraper_retry_delay: int = Field(default=5, description="Delay between retries in seconds")
    
    # ============================================
    # LOGGING CONFIGURATION
    # ============================================
    log_level: str = Field(default="INFO", description="Logging level")
    log_format: str = Field(default="json", description="Log format: json or text")
    
    # ============================================
    # AIRFLOW CONFIGURATION (optional, for DAGs)
    # ============================================
    airflow_executor: str = Field(default="LocalExecutor", description="Airflow executor type")
    
    @field_validator('log_level')
    @classmethod
    def validate_log_level(cls, v: str) -> str:
        """Validate log level is one of the standard levels."""
        valid_levels = ['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL']
        v = v.upper()
        if v not in valid_levels:
            raise ValueError(f"log_level must be one of {valid_levels}")
        return v
    
    @field_validator('log_format')
    @classmethod
    def validate_log_format(cls, v: str) -> str:
        """Validate log format is json or text."""
        v = v.lower()
        if v not in ['json', 'text']:
            raise ValueError("log_format must be 'json' or 'text'")
        return v
    
    class Config:
        """Pydantic configuration."""
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = False
        extra = "ignore"


# Global settings instance
_settings: Optional[Settings] = None


def get_settings() -> Settings:
    """
    Get the global settings instance.
    Creates it on first call, then returns cached instance.
    
    Returns:
        Settings: The application settings
    """
    global _settings
    if _settings is None:
        _settings = Settings()
    return _settings


def reload_settings() -> Settings:
    """
    Force reload settings from environment.
    Useful for testing or when environment changes.
    
    Returns:
        Settings: The newly loaded settings
    """
    global _settings
    _settings = Settings()
    return _settings


# Convenience function for getting specific config values
def get_mongo_uri() -> str:
    """Get MongoDB connection URI."""
    return get_settings().mongo_uri


def get_mongo_db() -> str:
    """Get MongoDB database name."""
    return get_settings().mongo_db


def get_scraper_config() -> dict:
    """
    Get scraper-specific configuration as a dictionary.
    
    Returns:
        dict: Scraper configuration including timeout, retries, proxy settings
    """
    settings = get_settings()
    return {
        "timeout": settings.scraper_timeout,
        "max_retries": settings.scraper_max_retries,
        "retry_delay": settings.scraper_retry_delay,
        "scraperapi_key": settings.scraperapi_key,
        "scraperapi_proxy": settings.scraperapi_proxy,
    }


if __name__ == "__main__":
    # Test configuration loading
    try:
        settings = get_settings()
        print("✓ Configuration loaded successfully")
        print(f"  MongoDB: {settings.mongo_db}")
        print(f"  Log Level: {settings.log_level}")
        print(f"  Scraper Timeout: {settings.scraper_timeout}s")
    except Exception as e:
        print(f"✗ Configuration error: {e}")
