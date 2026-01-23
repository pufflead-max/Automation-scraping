#!/usr/bin/env python3
import os
import sys
import argparse
from typing import List, Dict, Any, Optional
from datetime import datetime

# Add scraper/src to path for imports
script_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.append(os.path.join(script_dir, "scraper", "src"))

try:
    from database import get_db_manager
    from integrations.ghl import GHLClient
    from config import get_ghl_config
    from logger import get_logger
except ImportError as e:
    print(f"❌ Error: Could not import scraper modules. Ensure you are running from the project root. {e}")
    sys.exit(1)

logger = get_logger("push_leads")

def get_collection_name(source: str) -> str:
    """Map source name to collection name."""
    mapping = {
        "facebook": "Facebook_final_data",
        "nextdoor": "Nextdoor_final_data",
        "craigslist": "Craigslist_final_data"
    }
    return mapping.get(source.lower(), source)

def push_leads(source: str, limit: int = None, force: bool = False):
    """Fetch leads from MongoDB and push to GoHighLevel."""
    db = get_db_manager()
    ghl_config = get_ghl_config()
    
    collection_name = get_collection_name(source)
    
    if not ghl_config.get('api_key') or not ghl_config.get('location_id'):
        logger.error("ghl_config_missing", 
                    api_key=bool(ghl_config.get('api_key')), 
                    location_id=bool(ghl_config.get('location_id')))
        print("❌ Error: GoHighLevel configuration missing in .env (GHL_API_KEY, GHL_LOCATION_ID)")
        return

    logger.info("initializing_ghl_client")
    ghl_client = GHLClient(ghl_config['api_key'], ghl_config['location_id'])
    
    # Define query - only push if not already pushed, unless force is True
    query = {}
    if not force:
        query["pushed_to_ghl"] = {"$ne": True}
    
    logger.info("fetching_leads_from_db", collection=collection_name, query=query)
    try:
        leads_data = db.find_many(collection_name, query, limit=limit)
    except Exception as e:
        logger.error("db_fetch_failed", error=str(e))
        print(f"❌ Error: Failed to fetch leads from MongoDB: {e}")
        return
    
    if not leads_data:
        logger.info("no_new_leads_to_push", source=source)
        print(f"ℹ️ No new leads found for {source} in {collection_name}.")
        return

    # In-memory deduplication to be extra safe
    seen_urls = set()
    unique_leads = []
    for lead in leads_data:
        url = lead.get('source_url')
        if url not in seen_urls:
            unique_leads.append(lead)
            seen_urls.add(url)
    
    leads_data = unique_leads

    logger.info("leads_to_push", count=len(leads_data), source=source)
    print(f"🚀 Found {len(leads_data)} unique leads for {source} to push to GoHighLevel...")
    
    success_count = 0
    for i, lead_dict in enumerate(leads_data):
        try:
            # Ensure source is explicitly set in payload
            if 'source' not in lead_dict:
                lead_dict['source'] = source
            
            # Sync to GHL
            record_id = ghl_client.save_scraped_lead(lead_dict)
            
            if record_id:
                success_count += 1
                # Mark as pushed in DB
                db.update_one(collection_name, {"_id": lead_dict["_id"]}, 
                             {"$set": {
                                 "pushed_to_ghl": True, 
                                 "ghl_record_id": record_id,
                                 "pushed_at": datetime.utcnow()
                             }})
                logger.info("lead_pushed_successfully", record_id=record_id, index=i+1, source=source)
                name = lead_dict.get('author_name') or lead_dict.get('title') or "Unknown"
                print(f"✅ [{i+1}/{len(leads_data)}] Pushed: {name}")
            else:
                logger.warning("lead_push_failed", index=i+1, source=source)
                name = lead_dict.get('author_name') or lead_dict.get('title') or "Unknown"
                print(f"⚠️ [{i+1}/{len(leads_data)}] Failed to push lead: {name}")
                
        except Exception as e:
            logger.error("error_pushing_lead", error=str(e), index=i+1, source=source)
            print(f"❌ [{i+1}/{len(leads_data)}] Error: {e}")

    logger.info("push_process_completed", total=len(leads_data), successful=success_count, source=source)
    print(f"\n✨ Done! Successfully pushed {success_count} {source} leads to GoHighLevel.")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Push leads from MongoDB to GoHighLevel")
    parser.add_argument("--source", default="facebook", choices=["facebook", "nextdoor", "craigslist"], help="Source of leads (facebook, nextdoor, or craigslist)")
    parser.add_argument("--limit", type=int, help="Limit number of leads to push")
    parser.add_argument("--force", action="store_true", help="Push leads even if already marked as pushed")
    parser.add_argument("--all", action="store_true", help="Push leads from all sources")
    
    args = parser.parse_args()
    
    if args.all:
        for src in ["facebook", "nextdoor", "craigslist"]:
            print(f"\n=== Pushing {src.capitalize()} Leads ===")
            push_leads(source=src, limit=args.limit, force=args.force)
    else:
        push_leads(source=args.source, limit=args.limit, force=args.force)
