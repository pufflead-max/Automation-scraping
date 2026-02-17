#!/usr/bin/env python3
"""
User Credential Manager
Manages per-user Facebook and Nextdoor credentials and cookies.
"""

import os
import sys
import json
from typing import Dict, Optional, Any
from datetime import datetime

# Add current directory to path
sys.path.insert(0, os.path.dirname(__file__))

# Try relative and absolute imports for flexibility
try:
    from database import get_db_manager
except ImportError:
    from scraper.src.database import get_db_manager

from pymongo import MongoClient

class UserCredentialManager:
    """Manages user-specific credentials and cookies."""
    
    def __init__(self):
        self.db = get_db_manager()
        self.collection = "users"
        self.cookies_collection = "user_cookies"
        # In Docker, we want /opt/airflow/scraper/cookies/users
        # __file__ is /opt/airflow/scraper/src/user_credential_manager.py
        self.cookies_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "cookies", "users")
        os.makedirs(self.cookies_dir, exist_ok=True)
    
    def add_user_credentials(self, user_email: str, user_name: str, user_phone: str,
                            facebook_email: str = None, facebook_password: str = None,
                            nextdoor_email: str = None, nextdoor_password: str = None,
                            scraping_config: Dict[str, Any] = None):
        """Add or update user credentials and config in MongoDB."""
        
        user_doc = {
            "user": {
                "email": user_email,
                "name": user_name,
                "phone": user_phone
            },
            "credentials": {
                "facebook": {
                    "email": facebook_email,
                    "password": facebook_password
                } if facebook_email else None,
                "nextdoor": {
                    "email": nextdoor_email,
                    "password": nextdoor_password
                } if nextdoor_email else None
            },
            "scraping_config": scraping_config or {
                "facebook": {
                    "urls": [],
                    "limit": 25,
                    "headless": True
                },
                "nextdoor": {
                    "urls": [],
                    "max_pages": 5,
                    "headless": True
                }
            },
            "updated_at": datetime.utcnow()
        }
        
        # Upsert user document
        result = self.db.get_collection(self.collection).update_one(
            {"user.email": user_email},
            {"$set": user_doc},
            upsert=True
        )
        
        print(f"✅ User credentials {'updated' if result.modified_count else 'created'} for {user_email}")
        return user_doc
    
    def get_user_credentials(self, user_email: str) -> Optional[Dict]:
        """Get user credentials from MongoDB, supporting both nested and flat structures."""
        user_doc = self.db.find_one(self.collection, {"user.email": user_email})
        if not user_doc:
            return None
            
        # Start with nested credentials if they exist
        creds = user_doc.get("credentials", {})
        
        # Merge top-level platform keys (from GHL Form) if they exist
        for platform in ["facebook", "nextdoor", "craigslist"]:
            if platform in user_doc and isinstance(user_doc[platform], dict):
                if platform not in creds:
                    creds[platform] = user_doc[platform]
                else:
                    # Merge keys: top-level GHL data takes precedence for onboarding fields
                    for k, v in user_doc[platform].items():
                        if k not in creds[platform] or v: # Prefer non-empty values
                            creds[platform][k] = v
                            
        return creds
    
    def get_facebook_credentials(self, user_email: str) -> Optional[Dict]:
        """Get Facebook credentials for a user."""
        creds = self.get_user_credentials(user_email)
        if creds:
            return creds.get("facebook")
        return None
    
    def get_nextdoor_credentials(self, user_email: str) -> Optional[Dict]:
        """Get Nextdoor credentials for a user."""
        creds = self.get_user_credentials(user_email)
        if creds:
            return creds.get("nextdoor")
        return None

    def get_craigslist_credentials(self, user_email: str) -> Optional[Dict]:
        """Get Craigslist configuration for a user."""
        creds = self.get_user_credentials(user_email)
        if creds:
            return creds.get("craigslist")
        return None
    
    def save_cookies(self, user_email: str, platform: str, cookies: list):
        """Save cookies for a user and platform to a dedicated collection."""
        if not cookies:
            print(f"⚠️ No cookies provided for {user_email}, skipping save.")
            return False

        # Update dedicated cookies collection
        self.db.get_collection(self.cookies_collection).update_one(
            {"user_email": user_email, "platform": platform},
            {
                "$set": {
                    "cookies": cookies,
                    "updated_at": datetime.utcnow()
                }
            },
            upsert=True
        )
        
        print(f"✅ Saved {platform} cookies for {user_email} to '{self.cookies_collection}' collection")
        return True

    def delete_cookies(self, user_email: str, platform: str):
        """Delete cookies for a specific user and platform."""
        res = self.db.get_collection(self.cookies_collection).delete_one(
            {"user_email": user_email, "platform": platform}
        )
        if res.deleted_count > 0:
            print(f"🗑️ Removed expired {platform} cookies for {user_email} from MongoDB")
            return True
        return False
    
    def load_cookies(self, user_email: str, platform: str) -> Optional[list]:
        """Load cookies for a user and platform from the dedicated collection."""
        cookie_doc = self.db.find_one(self.cookies_collection, {"user_email": user_email, "platform": platform})
        
        if cookie_doc and cookie_doc.get("cookies"):
            cookies = cookie_doc.get("cookies")
            print(f"✅ Loaded {len(cookies)} {platform} cookies for {user_email} from '{self.cookies_collection}' collection")
            return cookies
        
        # Original location check (backward compatibility)
        user_doc = self.db.find_one(self.collection, {"user.email": user_email})
        if user_doc:
            creds_nested = user_doc.get("credentials", {}).get(platform, {})
            creds_flat = user_doc.get(platform, {})
            
            cookies = None
            if isinstance(creds_nested, dict): cookies = creds_nested.get("cookies")
            if not cookies and isinstance(creds_flat, dict): cookies = creds_flat.get("cookies")
            
            if cookies:
                print(f"✅ Loaded {len(cookies)} {platform} cookies for {user_email} from onboarding doc (legacy)")
                return cookies

        return None
    
    def list_users(self) -> list:
        """List all users with their credential status across all structures."""
        users = self.db.find_many(self.collection, {})
        
        result = []
        for user_doc in users:
            user = user_doc.get("user", {})
            user_email = user.get("email")
            
            # Use unified credential loader
            creds = self.get_user_credentials(user_email) if user_email else {}
            
            result.append({
                "email": user_email,
                "name": user.get("name"),
                "phone": user.get("phone"),
                "has_facebook": "facebook" in creds and creds["facebook"].get("email") is not None,
                "has_nextdoor": "nextdoor" in creds and creds["nextdoor"].get("email") is not None,
                "has_craigslist": "craigslist" in creds,
                "facebook_email": creds.get("facebook", {}).get("email") if "facebook" in creds else None,
                "nextdoor_email": creds.get("nextdoor", {}).get("email") if "nextdoor" in creds else None
            })
        
        return result
    
    def get_users_with_credentials(self, platform: str) -> list:
        """Get all users who have credentials for a specific platform, checking both nested and flat structures."""
        query = {
            "$or": [
                {f"credentials.{platform}.email": {"$exists": True, "$ne": None}},
                {f"{platform}.email": {"$exists": True, "$ne": None}}
            ]
        }
        
        try:
            print(f"🔍 Querying MongoDB for {platform} users in {self.collection} (DB: {self.db.db_name})")
            users = self.db.find_many(self.collection, query)
            print(f"📊 Found {len(users)} potential user documents in MongoDB")
        except Exception as e:
            print(f"❌ Error querying MongoDB: {e}")
            return []
        
        result = []
        for user_doc in users:
            user = user_doc.get("user", {})
            
            # Extract credentials from either location
            creds = user_doc.get("credentials", {}).get(platform)
            if not creds:
                creds = user_doc.get(platform)
                
            if isinstance(creds, dict) and creds.get("email"):
                result.append({
                    "email": user.get("email"),
                    "name": user.get("name"),
                    "creds": creds
                })
        
        print(f"✅ Filtered to {len(result)} users with valid {platform} credentials")
        return result

    def delete_user_credentials(self, user_email: str, platform: str = None):
        """Delete credentials for a user (optionally for specific platform)."""
        if platform:
            # Delete specific platform credentials
            self.db.get_collection(self.collection).update_one(
                {"user.email": user_email},
                {"$unset": {f"credentials.{platform}": ""}}
            )
            
            # Delete cookie file
            filename = f"{platform}_{user_email.replace('@', '_at_')}.json"
            filepath = os.path.join(self.cookies_dir, filename)
            if os.path.exists(filepath):
                os.remove(filepath)
            
            print(f"✅ Deleted {platform} credentials for {user_email}")
        else:
            # Delete all credentials
            self.db.get_collection(self.collection).update_one(
                {"user.email": user_email},
                {"$unset": {"credentials": ""}}
            )
            
            # Delete all cookie files for this user
            for platform in ["facebook", "nextdoor"]:
                filename = f"{platform}_{user_email.replace('@', '_at_')}.json"
                filepath = os.path.join(self.cookies_dir, filename)
                if os.path.exists(filepath):
                    os.remove(filepath)
            
            print(f"✅ Deleted all credentials for {user_email}")


def main():
    import argparse
    from tabulate import tabulate
    
    parser = argparse.ArgumentParser(description="User Credential Manager")
    parser.add_argument("--add-user", type=str, metavar="EMAIL", help="Add/update user credentials")
    parser.add_argument("--name", type=str, help="User name")
    parser.add_argument("--phone", type=str, help="User phone")
    parser.add_argument("--fb-email", type=str, help="Facebook email")
    parser.add_argument("--fb-password", type=str, help="Facebook password")
    parser.add_argument("--nd-email", type=str, help="Nextdoor email")
    parser.add_argument("--nd-password", type=str, help="Nextdoor password")
    parser.add_argument("--list-users", action="store_true", help="List all users")
    parser.add_argument("--get-creds", type=str, metavar="EMAIL", help="Get credentials for user")
    parser.add_argument("--delete-creds", type=str, metavar="EMAIL", help="Delete credentials for user")
    parser.add_argument("--platform", choices=["facebook", "nextdoor"], help="Specific platform")
    
    args = parser.parse_args()
    
    manager = UserCredentialManager()
    
    if args.add_user:
        if not args.name or not args.phone:
            print("❌ Error: --name and --phone are required when adding a user")
            return
        
        manager.add_user_credentials(
            user_email=args.add_user,
            user_name=args.name,
            user_phone=args.phone,
            facebook_email=args.fb_email,
            facebook_password=args.fb_password,
            nextdoor_email=args.nd_email,
            nextdoor_password=args.nd_password
        )
    
    elif args.list_users:
        users = manager.list_users()
        
        if not users:
            print("No users found")
            return
        
        table_data = []
        for user in users:
            table_data.append([
                user["name"],
                user["email"],
                user["phone"],
                "✅" if user["has_facebook"] else "❌",
                user["facebook_email"] or "N/A",
                "✅" if user["has_nextdoor"] else "❌",
                user["nextdoor_email"] or "N/A"
            ])
        
        headers = ["Name", "Email", "Phone", "FB", "FB Email", "ND", "ND Email"]
        print("\n" + "="*100)
        print("USER CREDENTIALS")
        print("="*100)
        print(tabulate(table_data, headers=headers, tablefmt="grid"))
        print()
    
    elif args.get_creds:
        creds = manager.get_user_credentials(args.get_creds)
        if creds:
            print(f"\n{'='*60}")
            print(f"CREDENTIALS FOR: {args.get_creds}")
            print(f"{'='*60}\n")
            print(json.dumps(creds, indent=2, default=str))
            print()
        else:
            print(f"❌ No credentials found for {args.get_creds}")
    
    elif args.delete_creds:
        manager.delete_user_credentials(args.delete_creds, args.platform)
    
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
