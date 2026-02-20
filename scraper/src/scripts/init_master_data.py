from dotenv import load_dotenv
load_dotenv()

import os
import sys
from pymongo import MongoClient

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from logger import get_logger

logger = get_logger(__name__)

def init_master_data():
    mongo_uri = os.getenv("MONGO_URI")
    db_name = os.getenv("MONGO_DB", "PUFF")
    client = MongoClient(mongo_uri)
    db = client[db_name]
    
    # 1. Vertical Master List
    verticals = [
        {
            "name": "Landscaping Services",
            "slug": "landscaping",
            "keywords": [
                "landscaping", "landscape", "landscaper", "lawn care", 
                "lawn maintenance", "yard cleanup", "spring cleanup", 
                "fall cleanup", "leaf removal", "snow removal", "yard work", "lawn service"
            ],
            "intent_indicators": ["looking for", "need", "recommendation", "can anyone recommend", "who does", "quote", "estimate", "contractor"],
            "exclude_keywords": ["handyman", "roofing", "electrician", "plumbing", "painting", "flooring", "for sale", "hiring", "job", "equipment", "tools"]
        },
        {
            "name": "Painting Services",
            "slug": "painting",
            "keywords": ["painting", "painter", "interior paint", "exterior paint", "house painting", "staining"],
            "intent_indicators": ["looking for", "need", "recommendation", "quote", "estimate"],
            "exclude_keywords": ["artist", "face painting", "hiring", "job"]
        },
        {
            "name": "Asphalt Paving Services",
            "slug": "asphalt_paving",
            "keywords": ["asphalt", "paving", "sealcoating", "driveway paving", "pavement", "blacktop"],
            "intent_indicators": ["looking for", "need", "recommendation", "quote", "estimate"],
            "exclude_keywords": ["hiring", "job"]
        },
        {
            "name": "Carpentry Services",
            "slug": "carpentry",
            "keywords": ["carpentry", "carpenter", "woodworking", "deck building", "framing", "cabinetry", "trim work"],
            "intent_indicators": ["looking for", "need", "recommendation", "quote", "estimate"],
            "exclude_keywords": ["hiring", "job"]
        },
        {
            "name": "Fence Installation & Repair",
            "slug": "fencing",
            "keywords": ["fence", "fencing", "fence repair", "fence installation", "vinyl fence", "wood fence", "chain link"],
            "intent_indicators": ["looking for", "need", "recommendation", "quote", "estimate"],
            "exclude_keywords": ["hiring", "job"]
        },
        {
            "name": "Flooring Installation & Repair",
            "slug": "flooring",
            "keywords": ["flooring", "hardwood floor", "tile installation", "vinyl plank", "laminate flooring", "carpet installation"],
            "intent_indicators": ["looking for", "need", "recommendation", "quote", "estimate"],
            "exclude_keywords": ["hiring", "job"]
        },
        {
            "name": "Cleaning services",
            "slug": "cleaning",
            "keywords": ["house cleaning", "maid service", "deep cleaning", "office cleaning", "carpet cleaning", "window cleaning", "move in cleaning", "move out cleaning"],
            "intent_indicators": ["looking for", "need", "recommendation", "cleaner"],
            "exclude_keywords": ["hiring", "job"]
        }
    ]
    
    db.verticals.delete_many({})
    db.verticals.insert_many(verticals)
    logger.info("verticals_initialized", count=len(verticals))
    
    # helper for search urls
    def get_fb_searches(city, keywords):
        return [f"https://www.facebook.com/search/posts?q={kw}%20{city}".replace(" ", "%20") for kw in keywords[:3]]

    # 2. Group Mappings (Region + Vertical -> URLs)
    mappings = [
        {
            "state": "MA",
            "city": "Hingham",
            "region": "South Shore",
            "vertical": "landscaping",
            "facebook": {
                "group_urls": [
                    "https://www.facebook.com/groups/hinghamcommunity",
                    "https://www.facebook.com/groups/hinghamscooop"
                ] + get_fb_searches("Hingham", verticals[0]["keywords"]),
                "page_urls": []
            },
            "nextdoor": {
                "group_urls": ["https://nextdoor.com/city/hingham--ma/"]
            },
            "craigslist": {
                "urls": [
                    "https://boston.craigslist.org/search/sob/fgs?query=hingham",
                    "https://boston.craigslist.org/search/sob/lbg?query=hingham",
                    "https://boston.craigslist.org/search/sob/hss?query=hingham"
                ]
            }
        },
        {
            "state": "MA",
            "city": "Cohasset",
            "region": "South Shore",
            "vertical": "landscaping",
            "facebook": {
                "group_urls": [
                    "https://www.facebook.com/groups/cohassetcommunity"
                ] + get_fb_searches("Cohasset", verticals[0]["keywords"]),
                "page_urls": []
            },
            "nextdoor": {
                "group_urls": ["https://nextdoor.com/city/cohasset--ma/"]
            },
            "craigslist": {
                "urls": ["https://boston.craigslist.org/search/sob/sss?query=cohasset"]
            }
        },
        {
            "state": "MA",
            "city": "Cambridge",
            "region": "Greater Boston",
            "vertical": "landscaping",
            "facebook": {
                "group_urls": [
                    "https://www.facebook.com/groups/cambridgema"
                ] + get_fb_searches("Cambridge", verticals[0]["keywords"]),
                "page_urls": []
            },
            "nextdoor": {
                "group_urls": ["https://nextdoor.com/city/cambridge--ma/"]
            },
            "craigslist": {
                "urls": ["https://boston.craigslist.org/search/gbs/sss?query=cambridge"]
            }
        },
        {
            "state": "MA",
            "city": "Boston",
            "region": "Greater Boston",
            "vertical": "cleaning",
            "facebook": {
                "group_urls": [
                    "https://www.facebook.com/groups/bostoncommunity",
                ] + get_fb_searches("Boston", verticals[6]["keywords"]),
                "page_urls": []
            },
            "nextdoor": {
                "group_urls": ["https://nextdoor.com/city/boston--ma/"]
            },
            "craigslist": {
                "urls": [
                    "https://boston.craigslist.org/search/hss?query=cleaning"
                ]
            }
        }
    ]
    
    db.group_mappings.delete_many({})
    db.group_mappings.insert_many(mappings)
    logger.info("group_mappings_initialized", count=len(mappings))

if __name__ == "__main__":
    init_master_data()
