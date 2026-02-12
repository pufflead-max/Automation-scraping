from user_credential_manager import UserCredentialManager
import os

def init_dino():
    manager = UserCredentialManager()
    
    # Dino Landscape configuration - MVP Recalibration
    dino_email = "alexxssand869@gmail.com" # From .env
    dino_name = "Dino Landscape"
    dino_phone = "617-000-0000"
    
    # NEW LANDSCAPING RECALIBRATION:
    # 1) Geo-filter: Hingham, MA (primary)
    # 2) Keywords: Specific landscaping terms
    # 3) Intent: Mandatory hiring indicators
    # 4) Blacklist: Handyman, roofing, etc. (handled by EXCLUSION_PATTERN in code)
    
    scraping_config = {
        "craigslist": {
            "urls": [
                "https://boston.craigslist.org/search/sob/fgs?query=hingham",
                "https://boston.craigslist.org/search/sob/lbg?query=hingham",
                "https://boston.craigslist.org/search/sob/hss?query=hingham",
                "https://boston.craigslist.org/search/sob/fgs",
                "https://boston.craigslist.org/search/sob/lbg",
                "https://boston.craigslist.org/search/sob/hss"
            ],
            "keywords": [
                "landscaping", "landscape", "landscaper", "lawn care", 
                "lawn maintenance", "yard cleanup", "spring cleanup", 
                "fall cleanup", "leaf removal", "snow removal", "yard work", "lawn service"
            ],
            "exclude_keywords": [
                "handyman", "roofing", "electrician", "plumbing", "painting", "flooring",
                "for sale", "hiring", "job", "equipment", "tools"
            ],
            "intent_indicators": ["looking for", "need", "recommendation", "can anyone recommend", "who does", "quote", "estimate", "contractor"],
            "max_pages": 10,
            "headless": True,
            "pipeline_id": "leads_pipeline",
            "stage_id": "manual_reply",
            "tags": ["Dino Landscape", "Landscaping", "Hingham", "MVP"]
        },
        "nextdoor": {
            "urls": ["https://nextdoor.com/city/hingham–ma"],
            "keywords": [
                 "landscaping", "landscape", "landscaper", "lawn care", 
                 "lawn maintenance", "yard cleanup", "spring cleanup", 
                 "fall cleanup", "leaf removal", "snow removal", "yard work", "lawn service"
            ],
            "max_pages": 5,
            "daily_limit": 50,
            "region": "Hingham",
            "cookie_sharing": True
        }
    }
    
    print(f"🚀 RECALIBRATING Dino Landscape profile for {dino_email} (Focus: Hingham MVP)...")
    manager.add_user_credentials(
        user_email=dino_email,
        user_name=dino_name,
        user_phone=dino_phone,
        facebook_email=dino_email,
        facebook_password=os.getenv("FACEBOOK_PASSWORD", "Dino0001"),
        nextdoor_email=os.getenv("NEXTDOOR_EMAIL", "nicknickbru@gmail.com"),
        nextdoor_password=os.getenv("NEXTDOOR_PASSWORD"),
        scraping_config=scraping_config
    )
    print("✅ Dino Landscape profile recalibrated for Hingham MVP.")

if __name__ == "__main__":
    init_dino()
