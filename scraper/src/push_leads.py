#!/usr/bin/env python3
"""Push leads from MongoDB to GoHighLevel  ."""

import os, sys, argparse
from datetime import datetime, timedelta
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

def push_leads(source: str, limit: int = None, force: bool = False, user_email: str = None):
    db, ghl_cfg = get_db_manager(), get_ghl_config()
    col = get_collection_name(source)
    
    if not ghl_cfg.get('api_key') or not ghl_cfg.get('location_id'):
        print("❌ Error: GHL config missing (.env: GHL_API_KEY, GHL_LOCATION_ID)")
        return

    # Initialize GHL Client
    ghl = GHLClient(**ghl_cfg)
    
    # Build query with optional user filter
    query = {} if force else {"pushed_to_ghl": {"$ne": True}}
    if user_email:
        query["user_email"] = user_email
        print(f"🔍 Filtering leads for user: {user_email}")
    
    logger.info("fetching_leads", col=col, query=query)
    print('DEBUG: about to find leads')
    leads = db.find_many(col, query, limit=limit or 0)
    print(f'DEBUG: found {len(leads)} leads')
    for idx, l in enumerate(leads):
        desc = l.get('description')
        desc_len = len(desc) if desc else 0
        desc_preview = (desc[:100].replace('\n', ' ') + '...') if desc else 'None'
        print(f"DEBUG Lead {idx+1}: Title='{l.get('title')}' | DescLen={desc_len} | BuyerReq={l.get('is_buyer_request')} | Date={l.get('posted_date')}")
        print(f"  --> URL: {l.get('source_url')}")
        print(f"  --> Description Snippet: {desc_preview}")
    
    if not leads:
        print(f"ℹ️ No new leads for {source} in {col}.")
        return

    # Deduplicate by source_url. Falls back to MongoDB _id for leads without a URL
    # so they are not silently collapsed into a single entry on the None key.
    dedup_map = {}
    for l in leads:
        key = l.get('source_url') or str(l.get('_id', id(l)))
        dedup_map[key] = l
    unique_leads = dedup_map.values()
    
    # ── Age Filter: 48 Hour Limit ───────────────────────────────────────────
    now = datetime.utcnow()
    age_limit = now - timedelta(hours=48)
    
    buyer_leads = []
    for l in unique_leads:
        if not (l.get('is_buyer_request') or l.get('is_service_request')):
            continue
            
        # Check posted date
        posted_date = l.get('posted_date')
        if isinstance(posted_date, str):
            try:
                from dateutil import parser
                posted_date = parser.parse(posted_date)
            except:
                posted_date = None
                
        if posted_date:
            # Ensure posted_date is offset-naive if now is naive (standard for our app)
            if posted_date.tzinfo is not None:
                posted_date = posted_date.replace(tzinfo=None)
                
            if posted_date < age_limit:
                age_hours = (now - posted_date).total_seconds() / 3600
                logger.debug("skipping_old_lead", url=l.get('source_url'), age_hours=round(age_hours, 1))
                continue
        
        buyer_leads.append(l)
    
    if not buyer_leads:
        print(f"⚠️ No fresh buyer leads (last 48h) for {source} after filtering.")
        return

    # Group leads by user for better organization
    leads_by_user = {}
    for lead in buyer_leads:
        user_email = lead.get('user_email', 'no_user')
        if user_email not in leads_by_user:
            leads_by_user[user_email] = []
        leads_by_user[user_email].append(lead)
    
    print(f"🚀 Pushing {len(buyer_leads)} leads to GHL...")
    print(f"📊 Grouped into {len(leads_by_user)} user(s)")
    
    success = 0
    total_processed = 0
    
    # Process leads grouped by user
    for user_email, user_leads in leads_by_user.items():
        if user_email != 'no_user':
            print(f"\n👤 Processing {len(user_leads)} leads for user: {user_email}")
        else:
            print(f"\n📋 Processing {len(user_leads)} leads without user assignment")
        
        for i, lead in enumerate(user_leads):
            total_processed += 1
            lead['source'] = source if 'source' not in lead else lead['source']
            
            # Add specific tags and stage for Craigslist/Dino
            if source == 'craigslist':
                lead['tags'] = lead.get('tags', []) + ['Dino Landscape', 'Landscaping', 'Craigslist']
                # Adding hints for the GHL client to use the right stage
                lead['pipeline_id'] = 'leads_pipeline' # Example ID or Name hint
                lead['stage_id'] = 'manual_reply'      # Example ID or Name hint
                
            record_id = ghl.save_scraped_lead(lead)
            
            if record_id:
                success += 1
                db.update_one(col, {"_id": lead["_id"]}, {
                    "$set": {
                        "pushed_to_ghl": True, 
                        "ghl_record_id": record_id, 
                        "pushed_at": datetime.utcnow()
                    }
                })
                name = lead.get('author_name') or lead.get('title') or "Unknown"
                user_info = f" (User: {lead.get('user_name', 'N/A')})" if lead.get('user_email') else ""
                
                contact_url = ghl.get_contact_url(record_id)
                print(f"✅ [{total_processed}/{len(buyer_leads)}] Pushed: {name[:50]}{user_info}")
                print(f"   🔗 Link: {contact_url}")
            else:
                print(f"⚠️ [{total_processed}/{len(buyer_leads)}] Failed: {lead.get('title', 'Unknown')[:50]}")

    print(f"\n✨ Done! Pushed {success}/{len(buyer_leads)} leads successfully.")

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", default="facebook", choices=["facebook", "nextdoor", "craigslist"])
    parser.add_argument("--limit", type=int)
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--all", action="store_true")
    parser.add_argument("--user", type=str, help="Filter leads by user email")
    args = parser.parse_args()
    
    sources = ["facebook", "nextdoor", "craigslist"] if args.all else [args.source]
    for src in sources:
        print(f"\n=== {src.capitalize()} Leads ===")
        push_leads(src, args.limit, args.force, args.user)
