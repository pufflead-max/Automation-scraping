#!/usr/bin/env python3
"""
User Lead Management Utility
Provides commands to view, filter, and manage leads by user.
"""

import sys
import os
from typing import Dict, List
from datetime import datetime, timedelta

# Add scraper/src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "scraper", "src"))

from database import get_db_manager
from tabulate import tabulate

def get_all_users() -> List[Dict]:
    """Get all unique users from the database."""
    db = get_db_manager()
    
    # Get unique users from ghl_onboarding_test collection
    users = db.find_many("ghl_onboarding_test", {})
    return users

def get_user_lead_stats(user_email: str) -> Dict:
    """Get lead statistics for a specific user."""
    db = get_db_manager()
    
    stats = {
        "user_email": user_email,
        "facebook": 0,
        "nextdoor": 0,
        "craigslist": 0,
        "total": 0,
        "pushed_to_ghl": 0,
        "pending": 0
    }
    
    collections = ["Facebook_final_data", "Nextdoor_final_data", "Craigslist_final_data"]
    
    for col in collections:
        source = col.split("_")[0].lower()
        
        # Total leads for user
        total = db.count_leads_by_user(col, user_email)
        stats[source] = total
        stats["total"] += total
        
        # Pushed leads
        pushed = len(db.find_many(col, {"user_email": user_email, "pushed_to_ghl": True}))
        stats["pushed_to_ghl"] += pushed
    
    stats["pending"] = stats["total"] - stats["pushed_to_ghl"]
    
    return stats

def list_all_users_with_stats():
    """List all users with their lead statistics."""
    print("\n" + "="*80)
    print("USER LEAD STATISTICS")
    print("="*80 + "\n")
    
    users = get_all_users()
    
    if not users:
        print("❌ No users found in ghl_onboarding_test collection")
        return
    
    table_data = []
    
    for user_doc in users:
        user = user_doc.get("user", {})
        email = user.get("email", "N/A")
        name = user.get("name", "N/A")
        phone = user.get("phone", "N/A")
        
        stats = get_user_lead_stats(email)
        
        table_data.append([
            name,
            email,
            phone,
            stats["facebook"],
            stats["nextdoor"],
            stats["craigslist"],
            stats["total"],
            stats["pushed_to_ghl"],
            stats["pending"]
        ])
    
    headers = ["Name", "Email", "Phone", "FB", "ND", "CL", "Total", "Pushed", "Pending"]
    print(tabulate(table_data, headers=headers, tablefmt="grid"))
    print()

def view_user_leads(user_email: str, source: str = None, limit: int = 10):
    """View recent leads for a specific user."""
    db = get_db_manager()
    
    print(f"\n{'='*80}")
    print(f"RECENT LEADS FOR: {user_email}")
    print(f"{'='*80}\n")
    
    collections = {
        "facebook": "Facebook_final_data",
        "nextdoor": "Nextdoor_final_data",
        "craigslist": "Craigslist_final_data"
    }
    
    if source:
        collections = {source: collections.get(source.lower())}
    
    for src, col in collections.items():
        if not col:
            continue
            
        leads = db.find_leads_by_user(col, user_email, limit=limit)
        
        if not leads:
            continue
        
        print(f"\n📊 {src.upper()} ({len(leads)} leads)")
        print("-" * 80)
        
        for i, lead in enumerate(leads, 1):
            title = lead.get("title", "No title")[:60]
            posted = lead.get("posted_date", "N/A")
            pushed = "✅ Pushed" if lead.get("pushed_to_ghl") else "⏳ Pending"
            vertical = lead.get("vertical", "N/A")
            city = lead.get("city", "N/A")
            
            print(f"{i}. {title}")
            print(f"   Vertical: {vertical} | City: {city} | Posted: {posted} | {pushed}")
            print()

def export_user_leads_to_json(user_email: str, output_file: str = None):
    """Export all leads for a user to JSON file."""
    import json
    
    db = get_db_manager()
    
    if not output_file:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_file = f"user_leads_{user_email.replace('@', '_at_')}_{timestamp}.json"
    
    all_leads = []
    
    collections = ["Facebook_final_data", "Nextdoor_final_data", "Craigslist_final_data"]
    
    for col in collections:
        leads = db.find_leads_by_user(col, user_email)
        
        for lead in leads:
            # Remove MongoDB _id for JSON serialization
            if "_id" in lead:
                lead["_id"] = str(lead["_id"])
            all_leads.append(lead)
    
    with open(output_file, 'w') as f:
        json.dump(all_leads, f, indent=2, default=str)
    
    print(f"✅ Exported {len(all_leads)} leads to {output_file}")

def main():
    import argparse
    
    parser = argparse.ArgumentParser(description="User Lead Management Utility")
    parser.add_argument("--list-users", action="store_true", help="List all users with statistics")
    parser.add_argument("--view-leads", type=str, metavar="EMAIL", help="View leads for a specific user")
    parser.add_argument("--source", choices=["facebook", "nextdoor", "craigslist"], help="Filter by source")
    parser.add_argument("--limit", type=int, default=10, help="Limit number of leads to display")
    parser.add_argument("--export", type=str, metavar="EMAIL", help="Export user leads to JSON")
    parser.add_argument("--output", type=str, help="Output file for export")
    
    args = parser.parse_args()
    
    if args.list_users:
        list_all_users_with_stats()
    elif args.view_leads:
        view_user_leads(args.view_leads, args.source, args.limit)
    elif args.export:
        export_user_leads_to_json(args.export, args.output)
    else:
        parser.print_help()

if __name__ == "__main__":
    main()
