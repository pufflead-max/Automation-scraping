#!/usr/bin/env python3
import sys
import os
from typing import Dict, Any

# Add scraper/src to path for imports
script_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.append(os.path.join(script_dir, "scraper", "src"))

try:
    from integrations.ghl import GHLClient
    from config import get_ghl_config
    from database import get_db_manager
except ImportError as e:
    print(f"❌ Error: Could not import scraper modules. {e}")
    sys.exit(1)

def check_lead(source_url: str):
    ghl_config = get_ghl_config()
    client = GHLClient(ghl_config['api_key'], ghl_config['location_id'])
    db = get_db_manager()
    
    # Try to find the lead in the database to get the original name/title
    lead_data = None
    for collection in ["Facebook_final_data", "Nextdoor_final_data", "Craigslist_final_data"]:
        found = db.find_one(collection, {"source_url": source_url})
        if found:
            lead_data = found
            lead_data['source'] = collection.split('_')[0].lower()
            break
            
    if not lead_data:
        print(f"⚠️ Warning: Lead not found in local database. Will use fallback name mapping.")
        lead_data = {"source_url": source_url, "name": "lead"}
    
    print(f"🔍 Checking GHL for lead with URL: {source_url}...")
    
    exists = client.check_lead_exists_on_ghl(lead_data)
    
    if exists:
        email = client._generate_deterministic_email(lead_data)
        print(f"✅ Lead is PRESENT on GoHighLevel.")
        print(f"📧 Deterministic Email: {email}")
    else:
        print(f"❌ Lead is NOT present on GoHighLevel.")

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python3 check_ghl_lead.py [SOURCE_URL]")
        sys.exit(1)
    
    check_lead(sys.argv[1])
