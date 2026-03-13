#!/usr/bin/env python3
import os
import sys
from datetime import datetime, timedelta

# Ensure we can import from the src directory
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from database import get_db_manager
from config import get_settings
from integrations.google_sheets import GoogleSheetsClient
from logger import get_logger

logger = get_logger("sync_sheets")

def sync_leads_to_sheets():
    settings = get_settings()
    db = get_db_manager()

    sheet_id = settings.google_sheet_id
    creds_path = settings.google_credentials_path

    if not sheet_id:
        print(" Error: GOOGLE_SHEET_ID missing in .env")
        return

    try:
        client = GoogleSheetsClient(creds_path, sheet_id)
        client.connect()
    except Exception as e:
        print(f" Google Sheets Connection Failed: {e}")
        return

    # Sources to sync
    sources = ["Facebook", "Craigslist", "Nextdoor"]

    for source in sources:
        col_name = f"{source}_final_data"
        print(f" Syncing {source} final leads...")

        # Fetch leads from the last 7 days (or all final leads)
        leads = db.find_many(col_name, {})

        if not leads:
            print(f"ℹ No final leads found for {source}.")
            continue

        # Process leads for JSON serialization
        processed_leads = []
        for l in leads:
            l_copy = l.copy()
            l_copy['_id'] = str(l_copy.get('_id', ''))
            # Format dates for Sheets
            for k, v in l_copy.items():
                if isinstance(v, datetime):
                    l_copy[k] = v.strftime("%Y-%m-%d %H:%M")
            processed_leads.append(l_copy)

        try:
            count = client.push_leads(processed_leads, worksheet_name=source)
            print(f" Successfully pushed {count} leads to '{source}' tab.")
        except Exception as e:
            print(f" Failed to push {source} leads: {e}")

    print("\n Sync Complete!")

if __name__ == "__main__":
    sync_leads_to_sheets()
