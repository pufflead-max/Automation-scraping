import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from logger import get_logger
from database import get_db_manager

logger = get_logger(__name__)

SEARCH_QUERIES = {
    "plumbing": [
        "need a plumber in {city}",
        "looking for plumber {city}",
        "need a plumber in {city}",
        "need plumber in {city}",
        "pipe leak repair needed",
        "water leak repair help",
    ],
    "electrical": [
        "need an electrician in {city}",
        "looking for electrician {city}",
        "need electrician in {city}",
        "electrical issue help needed",
        "wiring problem need help",
    ],
    "painting": [
        "need a painter {city}",
        "looking for house painter",
        "recommend a good painter",
        "need painting done {city}",
    ],
    "carpentry": [
        "need a carpenter {city}",
        "furniture repair help needed",
        "woodwork repair needed",
    ],
    "landscaping": [
        "need landscaping help {city}",
        "lawn care service needed",
        "garden cleanup help needed",
    ],
    "cleaning": [
        "need house cleaning service",
        "looking for cleaning service {city}",
        "deep cleaning help needed",
    ],
    "flooring": [
        "need flooring installation {city}",
        "floor repair help needed",
        "tile installation help needed",
    ],
    "fencing": [
        "need fence installation {city}",
        "fence repair help needed",
    ],
    "asphalt_paving": [
        "need driveway paving {city}",
        "asphalt repair help needed",
    ],
    "kitchen_and_bath": [
        "need kitchen renovation {city}",
        "bathroom renovation help needed",
        "home renovation contractor needed",
    ],
}

_RECENT_FILTER = "eyJyZWNlbnRfcG9zdHM6MCI6IntcIm5hbWVcIjpcInJlY2VudF9wb3N0c1wiLFwiYXJncyI6XCJcIn0ifQ%3D%3D"

def _make_url(query: str) -> str:
    q = query.replace(" ", "%20")
    return f"https://www.facebook.com/search/top?q={q}&filters={_RECENT_FILTER}"

def main():
    db = get_db_manager()
    users = db.find_many("users", {})
    updated_count = 0
    
    for user_doc in users:
        user_info = user_doc.get("user", {})
        email = user_info.get("email")
        if not email:
            continue
            
        city = user_info.get("city", "New York") # default if none
        verticals = user_info.get("verticals", [])
        
        all_fb_urls = []
        for vertical in verticals:
            templates = SEARCH_QUERIES.get(vertical.lower(), [])
            for template in templates:
                query = template.format(city=city)
                all_fb_urls.append(_make_url(query))
        
        # Merge safely if user already has a facebook object
        fb_obj = user_doc.get("facebook", {})
        fb_obj["page_urls"] = list(set(fb_obj.get("page_urls", []) + all_fb_urls))
        fb_obj["group_urls"] = fb_obj.get("group_urls", []) # keep existing if any
        
        # update the user's document
        try:
            db.update_one(
                "users",
                {"_id": user_doc["_id"]},
                {"$set": {"facebook": fb_obj}}
            )
            logger.info("updated_user_facebook_urls", email=email, urls_added=len(all_fb_urls))
            updated_count += 1
        except Exception as e:
            logger.error("failed_to_update_user", email=email, error=str(e))
            
    print(f"Update completed. {updated_count} user(s) modified.")

if __name__ == "__main__":
    main()
