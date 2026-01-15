"""
Structured logging configuration for the scraping system.
Provides consistent, structured logging across all components.
"""

import sys
import logging
from typing import Any, Dict
import structlog
from pythonjsonlogger import jsonlogger

try:
    from .config import get_settings
except ImportError:
    from config import get_settings


def setup_logging() -> None:
    """
    Configure structured logging for the application.
    Uses structlog for structured logging with JSON output.
    """
    settings = get_settings()
    
    # Configure standard library logging
    logging.basicConfig(
        format="%(message)s",
        stream=sys.stdout,
        level=getattr(logging, settings.log_level),
    )
    
    # Determine processors based on format
    if settings.log_format == "json":
        processors = [
            structlog.contextvars.merge_contextvars,
            structlog.stdlib.filter_by_level,
            structlog.stdlib.add_logger_name,
            structlog.stdlib.add_log_level,
            structlog.stdlib.PositionalArgumentsFormatter(),
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.processors.UnicodeDecoder(),
            structlog.processors.JSONRenderer(),
        ]
    else:
        processors = [
            structlog.contextvars.merge_contextvars,
            structlog.stdlib.filter_by_level,
            structlog.stdlib.add_logger_name,
            structlog.stdlib.add_log_level,
            structlog.stdlib.PositionalArgumentsFormatter(),
            structlog.processors.TimeStamper(fmt="%Y-%m-%d %H:%M:%S"),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.processors.UnicodeDecoder(),
            structlog.dev.ConsoleRenderer(),
        ]
    
    # Configure structlog
    structlog.configure(
        processors=processors,
        wrapper_class=structlog.stdlib.BoundLogger,
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )


def get_logger(name: str) -> structlog.stdlib.BoundLogger:
    """
    Get a structured logger instance.
    
    Args:
        name: Logger name (typically __name__ of the module)
    
    Returns:
        structlog.stdlib.BoundLogger: Configured logger instance
    """
    return structlog.get_logger(name)


class ScraperLogger:
    """
    Specialized logger for scraping operations with context management.
    Automatically adds scraper-specific context to all log messages.
    """
    
    def __init__(self, scraper_name: str):
        """
        Initialize scraper logger.
        
        Args:
            scraper_name: Name of the scraper (e.g., 'craigslist', 'nextdoor')
        """
        self.scraper_name = scraper_name
        self.logger = get_logger(scraper_name)
        self.context: Dict[str, Any] = {"scraper": scraper_name}
    
    def bind(self, **kwargs) -> 'ScraperLogger':
        """
        Add context to all subsequent log messages.
        
        Args:
            **kwargs: Key-value pairs to add to context
        
        Returns:
            ScraperLogger: Self for chaining
        """
        self.context.update(kwargs)
        self.logger = self.logger.bind(**kwargs)
        return self
    
    def unbind(self, *keys) -> 'ScraperLogger':
        """
        Remove context keys.
        
        Args:
            *keys: Keys to remove from context
        
        Returns:
            ScraperLogger: Self for chaining
        """
        for key in keys:
            self.context.pop(key, None)
        self.logger = self.logger.unbind(*keys)
        return self
    
    def debug(self, event: str, **kwargs) -> None:
        """Log debug message."""
        self.logger.debug(event, **kwargs)
    
    def info(self, event: str, **kwargs) -> None:
        """Log info message."""
        self.logger.info(event, **kwargs)
    
    def warning(self, event: str, **kwargs) -> None:
        """Log warning message."""
        self.logger.warning(event, **kwargs)
    
    def error(self, event: str, **kwargs) -> None:
        """Log error message."""
        self.logger.error(event, **kwargs)
    
    def critical(self, event: str, **kwargs) -> None:
        """Log critical message."""
        self.logger.critical(event, **kwargs)
    
    def exception(self, event: str, **kwargs) -> None:
        """Log exception with traceback."""
        self.logger.exception(event, **kwargs)
    
    def log_scrape_start(self, target: str, **kwargs) -> None:
        """Log start of scraping operation."""
        self.info(
            "scrape_started",
            target=target,
            **kwargs
        )
    
    def log_scrape_success(self, target: str, items_count: int, **kwargs) -> None:
        """Log successful scraping operation."""
        self.info(
            "scrape_completed",
            target=target,
            items_count=items_count,
            status="success",
            **kwargs
        )
    
    def log_scrape_error(self, target: str, error: Exception, **kwargs) -> None:
        """Log scraping error."""
        self.error(
            "scrape_failed",
            target=target,
            error=str(error),
            error_type=type(error).__name__,
            status="failed",
            **kwargs
        )
    
    def log_item_processed(self, item_id: str, **kwargs) -> None:
        """Log individual item processing."""
        self.debug(
            "item_processed",
            item_id=item_id,
            **kwargs
        )
    
    def log_retry(self, attempt: int, max_attempts: int, reason: str, **kwargs) -> None:
        """Log retry attempt."""
        self.warning(
            "retry_attempt",
            attempt=attempt,
            max_attempts=max_attempts,
            reason=reason,
            **kwargs
        )


# Initialize logging on module import
setup_logging()


if __name__ == "__main__":
    # Test logging
    logger = ScraperLogger("test_scraper")
    logger.bind(job_id="test-123")
    
    logger.info("Testing structured logging")
    logger.log_scrape_start("https://example.com", category="test")
    logger.log_scrape_success("https://example.com", items_count=42)
    
    try:
        raise ValueError("Test error")
    except Exception as e:
        logger.log_scrape_error("https://example.com", e)
