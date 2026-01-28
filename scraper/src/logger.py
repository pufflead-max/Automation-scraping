"""Structured logging configuration  ."""

import sys, logging, structlog
from typing import Any, Dict

try:
    from config import get_settings
except ImportError:
    from .config import get_settings

def setup_logging():
    s = get_settings()
    logging.basicConfig(format="%(message)s", stream=sys.stdout, level=getattr(logging, s.log_level))
    
    shared_processors = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.filter_by_level,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.stdlib.PositionalArgumentsFormatter(),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
        structlog.processors.UnicodeDecoder(),
    ]

    if s.log_format == "json":
        processors = shared_processors + [
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.JSONRenderer(),
        ]
    else:
        processors = shared_processors + [
            structlog.processors.TimeStamper(fmt="%Y-%m-%d %H:%M:%S"),
            structlog.dev.ConsoleRenderer(),
        ]
    
    structlog.configure(
        processors=processors,
        wrapper_class=structlog.stdlib.BoundLogger,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )

def get_logger(name: str): return structlog.get_logger(name)

class ScraperLogger:
    def __init__(self, name: str):
        self.name, self.logger = name, get_logger(name)
        self.context = {"scraper": name}
        self.logger = self.logger.bind(scraper=name)
    
    def bind(self, **kw):
        self.context.update(kw)
        self.logger = self.logger.bind(**kw)
        return self
    
    def info(self, ev, **kw): self.logger.info(ev, **kw)
    def debug(self, ev, **kw): self.logger.debug(ev, **kw)
    def warning(self, ev, **kw): self.logger.warning(ev, **kw)
    def error(self, ev, **kw): self.logger.error(ev, **kw)
    def exception(self, ev, **kw): self.logger.exception(ev, **kw)
    
    def log_scrape_start(self, target, **kw): self.info("scrape_started", target=target, **kw)
    def log_scrape_success(self, target, count, **kw): self.info("completed", target=target, count=count, status="success", **kw)
    def log_scrape_error(self, target, e, **kw): self.error("failed", target=target, error=str(e), type=type(e).__name__, status="failed", **kw)
    def log_retry(self, att, max_att, reason, **kw): self.warning("retry", attempt=att, max=max_att, reason=reason, **kw)

setup_logging()
