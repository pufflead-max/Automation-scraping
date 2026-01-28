"""Utility functions and helpers for the scraping system  ."""

import random, time, re
from typing import Optional, Dict, Any, List
from datetime import datetime
from functools import wraps
from urllib.parse import urlparse

USER_AGENTS = [
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/142.0.0.0 Safari/537.36',
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/142.0.0.0 Safari/537.36',
    'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/142.0.0.0 Safari/537.36',
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:122.0) Gecko/20100101 Firefox/122.0',
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.2 Safari/605.1.15',
]

def get_random_user_agent() -> str:
    return random.choice(USER_AGENTS)

def random_delay(min_sec: float = 1.0, max_sec: float = 3.0) -> None:
    time.sleep(random.uniform(min_sec, max_sec))

def timing_decorator(func):
    @wraps(func)
    def wrapper(*args, **kwargs):
        start = time.time()
        res = func(*args, **kwargs)
        duration = time.time() - start
        try:
            from logger import get_logger
            get_logger(__name__).debug("exec_time", func=func.__name__, duration=round(duration, 2))
        except: pass
        return res
    return wrapper

def sanitize_filename(name: str) -> str:
    return re.sub(r'[<>:"/\\|?*]', '_', name).strip('. ')[:200]

def extract_domain(url: str) -> Optional[str]:
    return urlparse(url).netloc if url else None

def is_valid_url(url: str) -> bool:
    try:
        res = urlparse(url)
        return all([res.scheme, res.netloc])
    except: return False

def chunk_list(lst: list, size: int) -> list:
    return [lst[i:i + size] for i in range(0, len(lst), size)]

def get_timestamp() -> str:
    return datetime.utcnow().isoformat()

def safe_get(d: Dict[str, Any], key: str, default: Any = None) -> Any:
    return d.get(key, default) if isinstance(d, dict) else default

def truncate_string(text: str, max_len: int = 100, suffix: str = "...") -> str:
    return text[:max_len-len(suffix)] + suffix if len(text) > max_len else text

class RateLimiter:
    def __init__(self, max_req: int, window: float):
        self.max_req, self.window, self.requests = max_req, window, []
    
    def wait_if_needed(self) -> None:
        now = time.time()
        self.requests = [r for r in self.requests if now - r < self.window]
        if len(self.requests) >= self.max_req:
            wait = self.window - (now - min(self.requests))
            if wait > 0: time.sleep(wait)
        self.requests.append(time.time())
