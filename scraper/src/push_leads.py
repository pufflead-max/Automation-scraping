#!/usr/bin/env python3
"""Push leads from MongoDB to GoHighLevel and Google Sheets."""

import os
import sys
import argparse
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional

# Add scraper/src to path for imports
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

try:
    from database import get_db_manager
    from integrations.ghl import GHLClient
    from integrations.google_sheets import GoogleSheetsClient
    from config import get_ghl_config, get_scraper_config
    from logger import get_logger
except ImportError:
    # Fallback for different execution contexts
    sys.path.append(os.path.join(os.path.dirname(os.path.abspath(__file__)), "scraper", "src"))
    from database import get_db_manager
    from integrations.ghl import GHLClient
    from integrations.google_sheets import GoogleSheetsClient
    from config import get_ghl_config, get_scraper_config
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

    ghl = GHLClient(**ghl_cfg)
    
    # query for new leads
    query = {} if force else {"pushed_to_ghl": {"$ne": True}}
    if user_email:
        query["user_email"] = user_email
        print(f"🔍 Filtering leads for user: {user_email}")
    
    leads = db.find_many(col, query, limit=limit or 0)
    
    if not leads:
        print(f"ℹ️ No new leads for {source} in {col}.")
        return

    # Deduplicate by source_url
    dedup_map = {}
    for l in leads:
        key = l.get('source_url') or str(l.get('_id', id(l)))
        dedup_map[key] = l
    unique_leads = list(dedup_map.values())
    
    # Age Filter: 168 Hour Limit (7 days)
    now = datetime.utcnow()
    age_limit = now - timedelta(hours=168)
    
    buyer_leads = []
    for l in unique_leads:
        if not (l.get('is_buyer_request') or l.get('is_service_request')):
            continue
            
        posted_date = l.get('posted_date')
        if isinstance(posted_date, str):
            try:
                from dateutil import parser
                posted_date = parser.parse(posted_date)
            except:
                posted_date = None
                
        if posted_date:
            if posted_date.tzinfo is not None:
                posted_date = posted_date.replace(tzinfo=None)
            if posted_date < age_limit:
                continue
        
        buyer_leads.append(l)
    
    if not buyer_leads:
        print(f"ℹ️ No fresh buyer leads (last 48h) for {source} after filtering.")
        return

    # User profile cache
    _user_profile_cache: Dict[str, Dict[str, Any]] = {}

    def get_user_profile(email: str) -> Dict[str, Any]:
        if email in _user_profile_cache:
            return _user_profile_cache[email]
        try:
            from user_credential_manager import UserCredentialManager
            mgr = UserCredentialManager()
            doc = mgr.db.find_one(mgr.collection, {"user.email": email})
            profile = doc.get("user", {}) if doc else {}
        except Exception as e:
            logger.warning("user_profile_lookup_failed", email=email, error=str(e))
            profile = {}
        _user_profile_cache[email] = profile
        return profile

    # Group leads by user
    leads_by_user: Dict[str, list] = {}
    for lead in buyer_leads:
        u = lead.get('user_email', 'no_user')
        leads_by_user.setdefault(u, []).append(lead)

    print(f"🚀 Pushing {len(buyer_leads)} leads to GHL...")
    
    success = 0
    total_processed = 0

    for u_email, user_leads in leads_by_user.items():
        if u_email != 'no_user':
            profile = get_user_profile(u_email)
            owner_name  = profile.get("name", "")
            owner_email = profile.get("email", u_email)
            owner_phone = profile.get("phone", "")
        else:
            owner_name = owner_email = owner_phone = ""

        for i, lead in enumerate(user_leads):
            total_processed += 1
            lead['source'] = source if 'source' not in lead else lead['source']

            if owner_name:  lead['user_name']  = owner_name
            if owner_email: lead['user_email'] = owner_email
            if owner_phone: lead['user_phone'] = owner_phone

            if source == 'craigslist':
                lead['tags'] = lead.get('tags', []) + ['Dino Landscape', 'Landscaping', 'Craigslist']
                lead['pipeline_id'] = 'leads_pipeline'
                lead['stage_id']    = 'manual_reply'

            record_id = ghl.save_scraped_lead(lead)

            if record_id:
                success += 1
                db.update_one(col, {"_id": lead["_id"]}, {
                    "$set": {
                        "pushed_to_ghl": True,
                        "ghl_record_id": record_id,
                        "pushed_at": datetime.utcnow(),
                        # Also sync our local fields to MongoDB for completeness
                        "user_name": owner_name,
                        "user_phone": owner_phone
                    }
                })
                name = lead.get('author_name') or lead.get('title') or "Unknown"
                contact_url = ghl.get_contact_url(record_id)
                print(f"✅ [{total_processed}/{len(buyer_leads)}] Pushed: {name[:50]}")
            else:
                print(f"⚠️ [{total_processed}/{len(buyer_leads)}] Failed: {lead.get('title', 'Unknown')[:50]}")

    # Synchronize to Google Sheets
    try:
        cfg = get_scraper_config()
        spreadsheet_id = cfg.get("google_sheet_id") or os.getenv("GOOGLE_SHEET_ID")
        credentials_path = cfg.get("google_credentials_path") or "/home/rohan/projects/resenha-automation/Automation-scraping/scraper/cookies/google_credentials.json"

        if spreadsheet_id and os.path.exists(credentials_path):
            print(f"\n📊 Syncing {source} leads to Google Sheets...")
            sheets = GoogleSheetsClient(credentials_path, spreadsheet_id)
            all_leads_for_source = db.find_many(col, {"is_buyer_request": True})
            for l in all_leads_for_source:
                if "_id" in l: l["_id"] = str(l["_id"])
            
            worksheet_map = {"facebook": "Facebook Leads", "nextdoor": "Nextdoor Leads", "craigslist": "Craigslist Leads"}
            count = sheets.push_leads(all_leads_for_source, worksheet_name=worksheet_map.get(source.lower(), f"{source} Leads"))
            print(f"✅ Successfully synced {count} leads to Google Sheets.")
    except Exception as e:
        print(f"⚠️ Google Sheets sync failed: {e}")

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
