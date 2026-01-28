"""Scraper source package."""

__version__ = "1.0.0"

from .config import get_settings, get_scraper_config
from .logger import get_logger, ScraperLogger, setup_logging
from .database import get_db_manager, get_db_connection, DatabaseManager
from .models import ScrapedLead, CraigslistLead, NextdoorLead, ScrapeJob

__all__ = [
    'get_settings',
    'get_scraper_config',
    'get_logger',
    'ScraperLogger',
    'setup_logging',
    'get_db_manager',
    'get_db_connection',
    'DatabaseManager',
    'ScrapedLead',
    'CraigslistLead',
    'NextdoorLead',
    'ScrapeJob',
]
