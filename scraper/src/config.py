import os
from typing import Optional, List, Dict
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
    
    # Google Sheets
    google_sheet_id: Optional[str] = Field(default=None, description="Google Spreadsheet ID")
    google_credentials_path: str = Field(default="google_credentials.json")


    # Bright Data Proxy (Legacy)
    brightdata_proxy_server: Optional[str] = None
    brightdata_proxy_user: Optional[str] = None
    brightdata_proxy_pass: Optional[str] = None

    # Generic Proxy (Decodo/Webshare)
    proxy_server: Optional[str] = None
    proxy_user: Optional[str] = None
    proxy_pass: Optional[str] = None

    # Facebook 2FA
    facebook_2fa_secret: Optional[str] = None

    # Ollama AI Configuration
    ollama_cloud_url: str = Field(default="http://ollama:11434/api/chat")
    ollama_cloud_model: str = Field(default="qwen2.5:7b")

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
            "scraperapi_proxy": s.scraperapi_proxy,
            "brightdata_proxy_server": s.brightdata_proxy_server,
            "brightdata_proxy_user": s.brightdata_proxy_user,
            "brightdata_proxy_pass": s.brightdata_proxy_pass,
            "proxy_server": s.proxy_server,
            "proxy_user": s.proxy_user,
            "proxy_pass": s.proxy_pass,
            "google_sheet_id": s.google_sheet_id,
            "google_credentials_path": s.google_credentials_path}
def get_proxy_list() -> List[Dict[str, str]]:
    """Read proxies from proxies.txt and return as a list of dictionaries."""
    # Current dir is scraper/src/
    proxy_file = os.path.join(os.path.dirname(__file__), "proxies.txt")
    if not os.path.exists(proxy_file):
        return []
    
    proxies = []
    with open(proxy_file, "r") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            parts = line.split(":")
            if len(parts) == 4:
                proxies.append({
                    "server": f"{parts[0]}:{parts[1]}",
                    "username": parts[2],
                    "password": parts[3]
                })
    return proxies

