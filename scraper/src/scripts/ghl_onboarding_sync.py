import os
import json
import sys
from datetime import datetime
from pymongo import MongoClient
from dotenv import load_dotenv

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from integrations.ghl import GHLClient
from logger import get_logger

logger = get_logger(__name__)

def sync_ghl_onboarding():
    load_dotenv()
    
    env = os.getenv("GHL_ENVIRONMENT", "sandbox")
    api_key = os.getenv(f"GHL_{env.upper()}_API_KEY") or os.getenv("GHL_API_KEY")
    loc_id = os.getenv(f"GHL_{env.upper()}_LOCATION_ID") or os.getenv("GHL_LOCATION_ID")
    
    if not api_key or not loc_id:
        logger.error("ghl_credentials_missing", env=env)
        return

    ghl = GHLClient(api_key, loc_id)
    
    mongo_uri = os.getenv("MONGO_URI")
    db_name = os.getenv("MONGO_DB", "PUFF")
    client = MongoClient(mongo_uri)
    db = client[db_name]
    collection = db["ghl_onboarding_test"]

    logger.info("starting_ghl_sync", location_id=loc_id)
    
    contacts = ghl.get_contacts(limit=100)
    
    custom_fields = ghl.get_custom_fields()
    field_id_to_name = {f['id']: f['name'] for f in custom_fields}
    
    synced_count = 0
    
    for contact in contacts:
        cf_values = {field_id_to_name.get(f['id'], f['id']): f['value'] for f in contact.get('customFields', [])}
        has_scraping = any("target keywords" in k.lower() or "urls" in k.lower() for k in cf_values.keys())
        if not has_scraping and "onboarding" not in [t.lower() for t in contact.get('tags', [])]: continue

        def get_cf(pattern):
            for k, v in cf_values.items():
                if pattern.lower() in k.lower(): return v
            return None

        onboarding_doc = {
            "user": {
                "name": contact.get('name') or f"{contact.get('firstName', '')} {contact.get('lastName', '')}".strip(),
                "email": contact.get('email'),
                "phone": contact.get('phone')
            },
            "facebook": {
                "email": get_cf("FB Email") or get_cf("Facebook Email") or os.getenv("FACEBOOK_EMAIL"),
                "password": get_cf("FB Password") or get_cf("Facebook Password") or os.getenv("FACEBOOK_PASSWORD"),
                "target_keywords": get_cf("FB Target Keywords") or get_cf("Facebook Target Keywords"),
                "page_urls": get_cf("FB Page URLs") or get_cf("Facebook Page URLs"),
                "group_urls": get_cf("FB Group URLs") or get_cf("Facebook Group URLs")
            },
            "nextdoor": {
                "email": get_cf("ND Email") or get_cf("Nextdoor Email") or os.getenv("NEXTDOOR_EMAIL"),
                "password": get_cf("ND Password") or get_cf("Nextdoor Password") or os.getenv("NEXTDOOR_PASSWORD"),
                "target_keywords": get_cf("ND Target Keywords") or get_cf("Nextdoor Target Keywords"),
                "page_urls": get_cf("ND Page URLs") or get_cf("Nextdoor Page URLs"),
                "group_urls": get_cf("ND Group URLs") or get_cf("Nextdoor Group URLs")
            },
            "craigslist": {
                "target_keywords": get_cf("CL Target Keywords") or get_cf("Craigslist Target Keywords"),
                "group_urls": get_cf("CL Group URLs") or get_cf("Craigslist Group URLs") or get_cf("Craigslist URLs")
            },
            "metadata": {
                "source": "GHL_Onboarding_Form",
                "environment": "test",
                "synced_at": datetime.utcnow().isoformat(),
                "ghl_contact_id": contact.get('id')
            }
        }

        collection.update_one(
            {"user.email": onboarding_doc["user"]["email"]},
            {"$set": onboarding_doc},
            upsert=True
        )
        synced_count += 1
        logger.info("contact_synced", email=onboarding_doc["user"]["email"])

    logger.info("ghl_sync_complete", synced=synced_count)

if __name__ == "__main__":
    sync_ghl_onboarding()

