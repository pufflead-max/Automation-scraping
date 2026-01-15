"""
Unit tests for configuration management.
"""

import pytest
import os
from unittest.mock import patch
from pydantic import ValidationError


def test_settings_loads_from_env():
    """Test that settings load from environment variables."""
    with patch.dict(os.environ, {
        'MONGO_URI': 'mongodb://test:test@localhost:27017/test',
        'MONGO_DB': 'test_db',
        'LOG_LEVEL': 'DEBUG'
    }):
        from scraper.src.config import Settings, reload_settings
        
        settings = reload_settings()
        
        assert settings.mongo_uri == 'mongodb://test:test@localhost:27017/test'
        assert settings.mongo_db == 'test_db'
        assert settings.log_level == 'DEBUG'


def test_log_level_validation():
    """Test that invalid log levels are rejected."""
    with patch.dict(os.environ, {
        'MONGO_URI': 'mongodb://test:test@localhost:27017/test',
        'LOG_LEVEL': 'INVALID'
    }):
        from scraper.src.config import Settings
        
        with pytest.raises(ValidationError):
            Settings()


def test_log_format_validation():
    """Test that invalid log formats are rejected."""
    with patch.dict(os.environ, {
        'MONGO_URI': 'mongodb://test:test@localhost:27017/test',
        'LOG_FORMAT': 'invalid'
    }):
        from scraper.src.config import Settings
        
        with pytest.raises(ValidationError):
            Settings()


def test_default_values():
    """Test that default values are used when env vars not set."""
    with patch.dict(os.environ, {
        'MONGO_URI': 'mongodb://test:test@localhost:27017/test'
    }, clear=True):
        from scraper.src.config import Settings, reload_settings
        
        settings = reload_settings()
        
        assert settings.mongo_db == 'PUFF'
        assert settings.scraper_timeout == 30
        assert settings.scraper_max_retries == 3
        assert settings.log_level == 'INFO'


def test_get_scraper_config():
    """Test scraper config helper function."""
    with patch.dict(os.environ, {
        'MONGO_URI': 'mongodb://test:test@localhost:27017/test',
        'SCRAPER_TIMEOUT': '60',
        'SCRAPER_MAX_RETRIES': '5'
    }):
        from scraper.src.config import get_scraper_config, reload_settings
        
        reload_settings()
        config = get_scraper_config()
        
        assert config['timeout'] == 60
        assert config['max_retries'] == 5
        assert 'scraperapi_key' in config


if __name__ == "__main__":
    pytest.main([__file__, '-v'])
