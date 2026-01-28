"""Utility functions and helpers for the scraping system."""

from typing import Optional, Dict, Any
import random
import time
from datetime import datetime
from functools import wraps


USER_AGENTS = [
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/142.0.0.0 Safari/537.36',
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/142.0.0.0 Safari/537.36',
    'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/142.0.0.0 Safari/537.36',
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:122.0) Gecko/20100101 Firefox/122.0',
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.2 Safari/605.1.15',
]


def get_random_user_agent() -> str:
    """Get a random user agent string."""
    return random.choice(USER_AGENTS)


def random_delay(min_seconds: float = 1.0, max_seconds: float = 3.0) -> None:
    """Sleep for a random amount of time."""
    time.sleep(random.uniform(min_seconds, max_seconds))


def timing_decorator(func):
    """Decorator to measure function execution time."""
    @wraps(func)
    def wrapper(*args, **kwargs):
        start_time = time.time()
        result = func(*args, **kwargs)
        duration = time.time() - start_time
        try:
            from .logger import get_logger
            get_logger(__name__).debug("function_execution_time", function=func.__name__, duration_seconds=round(duration, 2))
        except:
            pass
        return result
    return wrapper


def sanitize_filename(filename: str) -> str:
    """Sanitize a string to be safe for use as a filename."""
    for char in '<>:"/\\|?*':
        filename = filename.replace(char, '_')
    filename = filename.strip('. ')
    return filename[:200] if len(filename) > 200 else filename


def extract_domain(url: str) -> Optional[str]:
    """Extract domain from URL."""
    try:
        from urllib.parse import urlparse
        return urlparse(url).netloc
    except:
        return None


def is_valid_url(url: str) -> bool:
    """Check if a string is a valid URL."""
    try:
        from urllib.parse import urlparse
        result = urlparse(url)
        return all([result.scheme, result.netloc])
    except:
        return False


def chunk_list(lst: list, chunk_size: int) -> list:
    """Split a list into chunks of specified size."""
    return [lst[i:i + chunk_size] for i in range(0, len(lst), chunk_size)]


def get_timestamp() -> str:
    """Get current timestamp as ISO format string."""
    return datetime.utcnow().isoformat()


def safe_get(dictionary: Dict[str, Any], key: str, default: Any = None) -> Any:
    """Safely get a value from a dictionary with a default."""
    try:
        return dictionary.get(key, default)
    except:
        return default


def truncate_string(text: str, max_length: int = 100, suffix: str = "...") -> str:
    """Truncate a string to a maximum length."""
    return text if len(text) <= max_length else text[:max_length - len(suffix)] + suffix


class RateLimiter:
    """Simple rate limiter to control request frequency."""
    
    def __init__(self, max_requests: int, time_window: float):
        self.max_requests = max_requests
        self.time_window = time_window
        self.requests = []
    
    def wait_if_needed(self) -> None:
        """Wait if rate limit would be exceeded."""
        now = time.time()
        self.requests = [req_time for req_time in self.requests if now - req_time < self.time_window]
        
        if len(self.requests) >= self.max_requests:
            wait_time = self.time_window - (now - min(self.requests))
            if wait_time > 0:
                time.sleep(wait_time)
                now = time.time()
                self.requests = [req_time for req_time in self.requests if now - req_time < self.time_window]
        
        self.requests.append(now)
