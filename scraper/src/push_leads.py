#!/usr/bin/env python3
"""Push leads from MongoDB to GoHighLevel  ."""

import os, sys, argparse
from datetime import datetime
from typing import List, Dict, Any, Optional

# Add scraper/src to path for imports
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

try:
    from database import get_db_manager
    from integrations.ghl import GHLClient
    from config import get_ghl_config
    from logger import get_logger
except ImportError:
    # Fallback for different execution contexts
    sys.path.append(os.path.join(os.path.dirname(os.path.abspath(__file__)), "scraper", "src"))
    from database import get_db_manager
    from integrations.ghl import GHLClient
    from config import get_ghl_config
    from logger import get_logger

logger = get_logger("push_leads")

def get_collection_name(source: str) -> str:
    return {"facebook": "Facebook_final_data", "nextdoor": "Nextdoor_final_data", "craigslist": "Craigslist_final_data"}.get(source.lower(), source)

def push_leads(source: str, limit: int = None, force: bool = False):
    db, ghl_cfg = get_db_manager(), get_ghl_config()
    col = get_collection_name(source)
    
    if not ghl_cfg.get('api_key') or not ghl_cfg.get('location_id'):
        print("❌ Error: GHL config missing (.env: GHL_API_KEY, GHL_LOCATION_ID)")
        return

    # Initialize GHL Client
    ghl = GHLClient(**ghl_cfg)
    query = {} if force else {"pushed_to_ghl": {"$ne": True}}
    
    logger.info("fetching_leads", col=col, query=query)
    leads = db.find_many(col, query, limit=limit or 0)
    
    if not leads:
        print(f"ℹ️ No new leads for {source} in {col}.")
        return

    # Deduplicate and filter for buyer requests
    unique_leads = {l.get('source_url'): l for l in leads if l.get('source_url')}.values()
    buyer_leads = [l for l in unique_leads if l.get('is_buyer_request') or l.get('is_service_request')]
    
    if not buyer_leads:
        print(f"⚠️ No buyer leads for {source} after filtering.")
        return

    print(f"🚀 Pushing {len(buyer_leads)} leads to GHL...")
    
    success = 0
    for i, lead in enumerate(buyer_leads):
        lead['source'] = source if 'source' not in lead else lead['source']
        record_id = ghl.save_scraped_lead(lead)
        
        if record_id:
            success += 1
            db.update_one(col, {"_id": lead["_id"]}, {"$set": {"pushed_to_ghl": True, "ghl_record_id": record_id, "pushed_at": datetime.utcnow()}})
            name = lead.get('author_name') or lead.get('title') or "Unknown"
            contact_url = ghl.get_contact_url(record_id)
            print(f"✅ [{i+1}/{len(buyer_leads)}] Pushed: {name[:50]}")
            print(f"   🔗 Link: {contact_url}")
        else:
            print(f"⚠️ [{i+1}/{len(buyer_leads)}] Failed: {lead.get('title', 'Unknown')[:50]}")

    print(f"\n✨ Done! Pushed {success} leads.")

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", default="facebook", choices=["facebook", "nextdoor", "craigslist"])
    parser.add_argument("--limit", type=int)
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--all", action="store_true")
    args = parser.parse_args()
    
    sources = ["facebook", "nextdoor", "craigslist"] if args.all else [args.source]
    for src in sources:
        print(f"\n=== {src.capitalize()} Leads ===")
        push_leads(src, args.limit, args.force)
