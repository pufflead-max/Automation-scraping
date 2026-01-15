"""
Utility functions and helpers for the scraping system.
"""

from typing import Optional, Dict, Any
import random
import time
from datetime import datetime
from functools import wraps


# User agent rotation for avoiding detection
USER_AGENTS = [
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/142.0.0.0 Safari/537.36',
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/142.0.0.0 Safari/537.36',
    'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/142.0.0.0 Safari/537.36',
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:122.0) Gecko/20100101 Firefox/122.0',
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.2 Safari/605.1.15',
]


def get_random_user_agent() -> str:
    """
    Get a random user agent string.
    
    Returns:
        str: Random user agent
    """
    return random.choice(USER_AGENTS)


def random_delay(min_seconds: float = 1.0, max_seconds: float = 3.0) -> None:
    """
    Sleep for a random amount of time.
    Useful for avoiding detection and being polite to servers.
    
    Args:
        min_seconds: Minimum delay in seconds
        max_seconds: Maximum delay in seconds
    """
    delay = random.uniform(min_seconds, max_seconds)
    time.sleep(delay)


def timing_decorator(func):
    """
    Decorator to measure function execution time.
    
    Args:
        func: Function to time
    
    Returns:
        Wrapped function that logs execution time
    """
    @wraps(func)
    def wrapper(*args, **kwargs):
        start_time = time.time()
        result = func(*args, **kwargs)
        end_time = time.time()
        duration = end_time - start_time
        
        # Try to log if logger is available
        try:
            from .logger import get_logger
            logger = get_logger(__name__)
            logger.debug(
                "function_execution_time",
                function=func.__name__,
                duration_seconds=round(duration, 2)
            )
        except:
            pass
        
        return result
    
    return wrapper


def sanitize_filename(filename: str) -> str:
    """
    Sanitize a string to be safe for use as a filename.
    
    Args:
        filename: Original filename
    
    Returns:
        str: Sanitized filename
    """
    # Remove or replace unsafe characters
    unsafe_chars = '<>:"/\\|?*'
    for char in unsafe_chars:
        filename = filename.replace(char, '_')
    
    # Remove leading/trailing spaces and dots
    filename = filename.strip('. ')
    
    # Limit length
    max_length = 200
    if len(filename) > max_length:
        filename = filename[:max_length]
    
    return filename


def extract_domain(url: str) -> Optional[str]:
    """
    Extract domain from URL.
    
    Args:
        url: Full URL
    
    Returns:
        Optional[str]: Domain or None if invalid
    """
    try:
        from urllib.parse import urlparse
        parsed = urlparse(url)
        return parsed.netloc
    except:
        return None


def is_valid_url(url: str) -> bool:
    """
    Check if a string is a valid URL.
    
    Args:
        url: URL to validate
    
    Returns:
        bool: True if valid URL, False otherwise
    """
    try:
        from urllib.parse import urlparse
        result = urlparse(url)
        return all([result.scheme, result.netloc])
    except:
        return False


def chunk_list(lst: list, chunk_size: int) -> list:
    """
    Split a list into chunks of specified size.
    
    Args:
        lst: List to chunk
        chunk_size: Size of each chunk
    
    Returns:
        list: List of chunks
    """
    return [lst[i:i + chunk_size] for i in range(0, len(lst), chunk_size)]


def get_timestamp() -> str:
    """
    Get current timestamp as ISO format string.
    
    Returns:
        str: ISO format timestamp
    """
    return datetime.utcnow().isoformat()


def safe_get(dictionary: Dict[str, Any], key: str, default: Any = None) -> Any:
    """
    Safely get a value from a dictionary with a default.
    
    Args:
        dictionary: Dictionary to get value from
        key: Key to look up
        default: Default value if key not found
    
    Returns:
        Any: Value or default
    """
    try:
        return dictionary.get(key, default)
    except:
        return default


def truncate_string(text: str, max_length: int = 100, suffix: str = "...") -> str:
    """
    Truncate a string to a maximum length.
    
    Args:
        text: Text to truncate
        max_length: Maximum length
        suffix: Suffix to add if truncated
    
    Returns:
        str: Truncated string
    """
    if len(text) <= max_length:
        return text
    return text[:max_length - len(suffix)] + suffix


class RateLimiter:
    """
    Simple rate limiter to control request frequency.
    """
    
    def __init__(self, max_requests: int, time_window: float):
        """
        Initialize rate limiter.
        
        Args:
            max_requests: Maximum number of requests allowed
            time_window: Time window in seconds
        """
        self.max_requests = max_requests
        self.time_window = time_window
        self.requests = []
    
    def wait_if_needed(self) -> None:
        """
        Wait if rate limit would be exceeded.
        """
        now = time.time()
        
        # Remove old requests outside the time window
        self.requests = [req_time for req_time in self.requests 
                        if now - req_time < self.time_window]
        
        # If at limit, wait
        if len(self.requests) >= self.max_requests:
            oldest_request = min(self.requests)
            wait_time = self.time_window - (now - oldest_request)
            if wait_time > 0:
                time.sleep(wait_time)
                # Clean up again after waiting
                now = time.time()
                self.requests = [req_time for req_time in self.requests 
                               if now - req_time < self.time_window]
        
        # Record this request
        self.requests.append(now)


if __name__ == "__main__":
    # Test utilities
    print("Testing utility functions...")
    
    # Test user agent
    ua = get_random_user_agent()
    print(f"✓ Random user agent: {ua[:50]}...")
    
    # Test URL validation
    assert is_valid_url("https://example.com") == True
    assert is_valid_url("not a url") == False
    print("✓ URL validation works")
    
    # Test domain extraction
    domain = extract_domain("https://boston.craigslist.org/search/aos")
    assert domain == "boston.craigslist.org"
    print(f"✓ Domain extraction: {domain}")
    
    # Test chunking
    chunks = chunk_list([1, 2, 3, 4, 5], 2)
    assert len(chunks) == 3
    print(f"✓ List chunking: {chunks}")
    
    # Test truncation
    truncated = truncate_string("This is a very long string", 10)
    assert len(truncated) == 10
    print(f"✓ String truncation: {truncated}")
    
    # Test rate limiter
    limiter = RateLimiter(max_requests=3, time_window=1.0)
    for i in range(5):
        limiter.wait_if_needed()
        print(f"  Request {i+1}")
    print("✓ Rate limiter works")
    
    print("\n✓ All utility tests passed!")
