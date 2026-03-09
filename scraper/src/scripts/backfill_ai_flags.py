import os
import sys
import json
from pymongo import MongoClient
from datetime import datetime

# Add src to path
sys.path.append(os.path.join(os.path.dirname(__file__), ".."))

try:
    from config import get_settings
    from utils.ai_classifier import get_ai_classifier
    from logger import get_logger
except ImportError:
    # If running from project root
    sys.path.append(os.path.join(os.getcwd(), "scraper", "src"))
    from config import get_settings
    from utils.ai_classifier import get_ai_classifier
    from logger import get_logger

logger = get_logger("backfill_ai_flags")

def backfill_facebook_leads():
    settings = get_settings()
    ai = get_ai_classifier()
    
    # Connect to MongoDB
    client = MongoClient(settings.mongo_uri)
    db = client[settings.mongo_db]
    collection = db["Facebook_raw_data"]
    
    # Process leads that haven't been AI-classified yet
    query = {"ai_processed": {"$ne": True}}
    leads = list(collection.find(query).limit(50)) # Limit for test
    
    if not leads:
        print("No new Facebook leads to process.")
        return

    print(f"🔄 Processing {len(leads)} leads from Facebook_raw_data...")

    for lead in leads:
        lead_id = lead["_id"]
        text = f"{lead.get('title', '')} {lead.get('description', '')}".strip()
        
        if not text:
            collection.update_one({"_id": lead_id}, {"$set": {"ai_processed": True, "ai_skip": "empty_text"}})
            continue

        try:
            print(f"🤖 Classifying: {text[:50]}...")
            
            # Step 1: Spam Check
            spam_res = ai.classify_spam(text)
            
            # Step 2: Intent Check
            intent_res = ai.classify_intent(text)
            
            # Update Document
            update_data = {
                "ai_processed": True,
                "ai_last_updated": datetime.utcnow(),
                "ai_classification": {
                    "is_spam": spam_res.get("label") == "spam",
                    "spam_confidence": spam_res.get("confidence", 0),
                    "intent": intent_res.get("label", "unknown"),
                    "intent_confidence": intent_res.get("confidence", 0),
                    "reason": intent_res.get("reason", "")
                }
            }
            
            # Legacy field sync if confirmed buyer
            if intent_res.get("label") == "buyer" and intent_res.get("confidence", 0) > 0.8:
                update_data["is_buyer_request"] = True
            
            collection.update_one({"_id": lead_id}, {"$set": update_data})
            print(f"✅ Updated lead {lead_id} -> {intent_res.get('label')} (Conf: {intent_res.get('confidence')})")
            
        except Exception as e:
            print(f"❌ Failed to process lead {lead_id}: {e}")

    print("🏁 Backfill complete.")

if __name__ == "__main__":
    backfill_facebook_leads()
