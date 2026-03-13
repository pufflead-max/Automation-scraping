from dotenv import load_dotenv
load_dotenv()

import os
import sys
from urllib.parse import quote_plus
from itertools import product as iter_product
from pymongo import MongoClient

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from logger import get_logger

logger = get_logger(__name__)


# ─────────────────────────────────────────────────────────────────
# URL BUILDERS
# ─────────────────────────────────────────────────────────────────

def make_nextdoor_urls(keywords: list, intent_indicators: list) -> list:
    """
    Generate Nextdoor search URLs by combining each intent indicator
    with each keyword.
    e.g. "looking for" + "landscaper" → nextdoor.com/search/?query=looking+for+landscaper
    """
    urls = []
    for intent, kw in iter_product(intent_indicators, keywords):
        query = f"{intent} {kw}"
        urls.append(f"https://nextdoor.com/search/?query={quote_plus(query)}")
    return urls


def make_facebook_search_urls(keywords: list, intent_indicators: list, city: str = "") -> list:
    """
    Generate Facebook post search URLs by combining intent + keyword,
    optionally appending a city name to narrow results geographically.
    """
    urls = []
    for intent, kw in iter_product(intent_indicators, keywords):
        query = f"{intent} {kw} {city}".strip()
        urls.append(f"https://www.facebook.com/search/posts/?q={quote_plus(query)}")
    return urls


def make_craigslist_urls(subdomain: str, keywords: list, intent_indicators: list) -> list:
    """
    Generate Craigslist search URLs (sorted by newest) by combining
    intent + keyword for the given city subdomain.
    """
    base = f"https://{subdomain}.craigslist.org/search/sss"
    urls = []
    for intent, kw in iter_product(intent_indicators, keywords):
        query = f"{intent} {kw}"
        urls.append(f"{base}?query={quote_plus(query)}&sort=date")
    return urls


# ─────────────────────────────────────────────────────────────────
# MAIN INIT
# ─────────────────────────────────────────────────────────────────

def init_master_data():
    mongo_uri = os.getenv("MONGO_URI")
    db_name = os.getenv("MONGO_DB", "PUFF")
    client = MongoClient(mongo_uri)
    db = client[db_name]

    # ─────────────────────────────────────────────────────────────
    # 1. Vertical Master List
    # ─────────────────────────────────────────────────────────────
    verticals = [
        {
            "name": "Landscaping Services",
            "slug": "landscaping",
            "keywords": [
                "landscaping", "landscape", "landscaper", "lawn care",
                "lawn maintenance", "yard cleanup", "spring cleanup",
                "fall cleanup", "leaf removal", "snow removal", "yard work", "lawn service"
            ],
            "intent_indicators": [
                "looking for", "need", "recommendation", "can anyone recommend",
                "who does", "quote", "estimate", "contractor"
            ],
            "exclude_keywords": [
                "handyman", "roofing", "electrician", "plumbing", "painting",
                "flooring", "for sale", "hiring", "job", "equipment", "tools"
            ]
        },
        {
            "name": "Painting Services",
            "slug": "painting",
            "keywords": [
                "painting", "painter", "interior paint", "exterior paint",
                "house painting", "staining"
            ],
            "intent_indicators": ["looking for", "need", "recommendation", "quote", "estimate"],
            "exclude_keywords": ["artist", "face painting", "hiring", "job"]
        },
        {
            "name": "Asphalt Paving Services",
            "slug": "asphalt_paving",
            "keywords": [
                "asphalt", "paving", "sealcoating", "driveway paving",
                "pavement", "blacktop"
            ],
            "intent_indicators": ["looking for", "need", "recommendation", "quote", "estimate"],
            "exclude_keywords": ["hiring", "job"]
        },
        {
            "name": "Carpentry Services",
            "slug": "carpentry",
            "keywords": [
                "carpentry", "carpenter", "woodworking", "deck building",
                "framing", "cabinetry", "trim work"
            ],
            "intent_indicators": ["looking for", "need", "recommendation", "quote", "estimate"],
            "exclude_keywords": ["hiring", "job"]
        },
        {
            "name": "Fence Installation & Repair",
            "slug": "fencing",
            "keywords": [
                "fence", "fencing", "fence repair", "fence installation",
                "vinyl fence", "wood fence", "chain link"
            ],
            "intent_indicators": ["looking for", "need", "recommendation", "quote", "estimate"],
            "exclude_keywords": ["hiring", "job"]
        },
        {
            "name": "Flooring Installation & Repair",
            "slug": "flooring",
            "keywords": [
                "flooring", "hardwood floor", "tile installation",
                "vinyl plank", "laminate flooring", "carpet installation"
            ],
            "intent_indicators": ["looking for", "need", "recommendation", "quote", "estimate"],
            "exclude_keywords": ["hiring", "job"]
        },
        {
            "name": "Cleaning services",
            "slug": "cleaning",
            "keywords": [
                "house cleaning", "maid service", "deep cleaning", "office cleaning",
                "carpet cleaning", "window cleaning", "move in cleaning", "move out cleaning"
            ],
            "intent_indicators": ["looking for", "need", "recommendation", "cleaner"],
            "exclude_keywords": ["hiring", "job"]
        },
        {
            "name": "Kitchen & Bath Renovations",
            "slug": "kitchen_and_bath",
            "keywords": [
                "kitchen remodel", "bathroom remodel", "cabinet installation",
                "countertop", "vanity installation", "shower remodel",
                "bath renovation", "kitchen renovation"
            ],
            "intent_indicators": ["looking for", "need", "recommendation", "quote", "estimate"],
            "exclude_keywords": ["hiring", "job"]
        },
        {
            "name": "Plumbing",
            "slug": "plumbing",
            "keywords": [
                "plumber", "plumbing", "leak", "clog", "faucet repair",
                "pipe burst", "water heater", "drain cleaning", "sewer line", "toilet repair"
            ],
            "intent_indicators": [
                "looking for", "need", "recommendation", "quote", "estimate", "clogged"
            ],
            "exclude_keywords": ["hiring", "job"]
        },
        {
            "name": "Electrical Services",
            "slug": "electrical",
            "keywords": [
                "electrician", "electrical", "wiring", "outlets", "circuit breaker",
                "lighting installation", "panel upgrade", "generator installation"
            ],
            "intent_indicators": ["looking for", "need", "recommendation", "quote", "estimate"],
            "exclude_keywords": ["hiring", "job"]
        }
    ]

    # Build a quick slug → vertical lookup for use in mappings below
    vertical_map = {v["slug"]: v for v in verticals}

    db.verticals.delete_many({})
    db.verticals.insert_many(verticals)
    logger.info("verticals_initialized", count=len(verticals))

    # ─────────────────────────────────────────────────────────────
    # 2. Group Mappings  (Region + Vertical → URLs)
    #    Nextdoor, Facebook, and Craigslist URLs are now generated
    #    dynamically using intent × keyword combos per vertical.
    # ─────────────────────────────────────────────────────────────

    # Raw mapping definitions — URLs are generated automatically below
    mapping_defs = [
        {
            "state": "MA",
            "city": "Hingham",
            "region": "South Shore",
            "vertical": "landscaping",
            "craigslist_subdomain": "boston",
            "facebook_group_urls": [
                "https://www.facebook.com/groups/hinghamcommunity",
                "https://www.facebook.com/groups/hinghamscooop"
            ],
            "nextdoor_neighborhoods": [
                "crow-point", "liberty-pole", "hingham-center", "glad-tidings"
            ],
        },
        {
            "state": "MA",
            "city": "Cohasset",
            "region": "South Shore",
            "vertical": "landscaping",
            "craigslist_subdomain": "boston",
            "facebook_group_urls": [
                "https://www.facebook.com/groups/cohassetcommunity"
            ],
        },
        {
            "state": "MA",
            "city": "Cambridge",
            "region": "Greater Boston",
            "vertical": "landscaping",
            "craigslist_subdomain": "boston",
            "facebook_group_urls": [
                "https://www.facebook.com/groups/cambridgema"
            ],
        },
        {
            "state": "MA",
            "city": "Boston",
            "region": "Greater Boston",
            "vertical": "cleaning",
            "craigslist_subdomain": "boston",
            "facebook_group_urls": [
                "https://www.facebook.com/groups/bostoncommunity"
            ],
        },
        # ── Victor Moura (Weymouth, MA) ───────────────────────────
        {
            "state": "MA",
            "city": "Weymouth",
            "region": "South Shore",
            "vertical": "plumbing",
            "craigslist_subdomain": "boston",
            "facebook_group_urls": [
                "https://www.facebook.com/groups/weymouthma",
                "https://www.facebook.com/groups/weymouthcommunity",
            ],
        },
        {
            "state": "MA",
            "city": "Weymouth",
            "region": "South Shore",
            "vertical": "kitchen_and_bath",
            "craigslist_subdomain": "boston",
            "facebook_group_urls": [
                "https://www.facebook.com/groups/weymouthma",
                "https://www.facebook.com/groups/weymouthcommunity",
            ],
        },
        {
            "state": "MA",
            "city": "Weymouth",
            "region": "South Shore",
            "vertical": "electrical",
            "craigslist_subdomain": "boston",
            "facebook_group_urls": [
                "https://www.facebook.com/groups/weymouthma",
                "https://www.facebook.com/groups/weymouthcommunity",
            ],
        },
    ]

    mappings = []
    for defn in mapping_defs:
        slug = defn["vertical"]
        v = vertical_map[slug]
        keywords = v["keywords"]
        intents = v["intent_indicators"]
        city = defn["city"]
        subdomain = defn["craigslist_subdomain"]

        mappings.append({
            "state":  defn["state"],
            "city":   city,
            "region": defn["region"],
            "vertical": slug,
            "facebook": {
                # Curated community group URLs stay first
                "group_urls": defn["facebook_group_urls"],
                # Intent-based post search URLs (city-scoped)
                "search_urls": make_facebook_search_urls(keywords, intents, city=city),
                "page_urls": []
            },
            "nextdoor": {
                # City landing page
                "city_url": f"https://nextdoor.com/city/{city.lower().replace(' ', '-')}--{defn['state'].lower()}/",
                # Neighborhood-specific pages (hyper-local)
                "neighborhood_urls": [
                    f"https://nextdoor.com/neighborhood/{nb.lower().replace(' ', '-')}--{city.lower().replace(' ', '-')}--{defn['state'].lower()}/"
                    for nb in defn.get("nextdoor_neighborhoods", [])
                ],
                # Intent-based search URLs
                "search_urls": make_nextdoor_urls(keywords, intents),
            },
            "craigslist": {
                # Intent-based search URLs for the correct regional subdomain
                "search_urls": make_craigslist_urls(subdomain, keywords, intents),
            },
        })

    db.group_mappings.delete_many({})
    db.group_mappings.insert_many(mappings)
    logger.info("group_mappings_initialized", count=len(mappings))

    # ─────────────────────────────────────────────────────────────
    # 3. Craigslist Site Mappings (Dynamic lookup — all 50 states)
    # ─────────────────────────────────────────────────────────────
    cl_sites = [
        {"state_code": "AL", "subdomain": "birmingham",    "name": "Birmingham"},
        {"state_code": "AK", "subdomain": "anchorage",     "name": "Anchorage"},
        {"state_code": "AZ", "subdomain": "phoenix",       "name": "Phoenix"},
        {"state_code": "AR", "subdomain": "littlerock",    "name": "Little Rock"},
        {"state_code": "CA", "subdomain": "sfbay",         "name": "SF Bay Area"},
        {"state_code": "CO", "subdomain": "denver",        "name": "Denver"},
        {"state_code": "CT", "subdomain": "newhaven",      "name": "New Haven"},
        {"state_code": "DE", "subdomain": "delaware",      "name": "Delaware"},
        {"state_code": "FL", "subdomain": "miami",         "name": "Miami"},
        {"state_code": "GA", "subdomain": "atlanta",       "name": "Atlanta"},
        {"state_code": "HI", "subdomain": "honolulu",      "name": "Honolulu"},
        {"state_code": "ID", "subdomain": "boise",         "name": "Boise"},
        {"state_code": "IL", "subdomain": "chicago",       "name": "Chicago"},
        {"state_code": "IN", "subdomain": "indianapolis",  "name": "Indianapolis"},
        {"state_code": "IA", "subdomain": "desmoines",     "name": "Des Moines"},
        {"state_code": "KS", "subdomain": "wichita",       "name": "Wichita"},
        {"state_code": "KY", "subdomain": "louisville",    "name": "Louisville"},
        {"state_code": "LA", "subdomain": "neworleans",    "name": "New Orleans"},
        {"state_code": "ME", "subdomain": "maine",         "name": "Maine"},
        {"state_code": "MD", "subdomain": "baltimore",     "name": "Baltimore"},
        {"state_code": "MA", "subdomain": "boston",        "name": "Boston"},
        {"state_code": "MI", "subdomain": "detroit",       "name": "Detroit"},
        {"state_code": "MN", "subdomain": "minneapolis",   "name": "Minneapolis"},
        {"state_code": "MS", "subdomain": "jackson",       "name": "Jackson"},
        {"state_code": "MO", "subdomain": "stlouis",       "name": "St. Louis"},
        {"state_code": "MT", "subdomain": "billings",      "name": "Billings"},
        {"state_code": "NE", "subdomain": "omaha",         "name": "Omaha"},
        {"state_code": "NV", "subdomain": "lasvegas",      "name": "Las Vegas"},
        {"state_code": "NH", "subdomain": "nh",            "name": "New Hampshire"},
        {"state_code": "NJ", "subdomain": "newjersey",     "name": "North Jersey"},
        {"state_code": "NM", "subdomain": "albuquerque",   "name": "Albuquerque"},
        {"state_code": "NY", "subdomain": "newyork",       "name": "New York City"},
        {"state_code": "NC", "subdomain": "raleigh",       "name": "Raleigh"},
        {"state_code": "ND", "subdomain": "bismarck",      "name": "Bismarck"},
        {"state_code": "OH", "subdomain": "columbus",      "name": "Columbus"},
        {"state_code": "OK", "subdomain": "oklahomacity",  "name": "Oklahoma City"},
        {"state_code": "OR", "subdomain": "portland",      "name": "Portland"},
        {"state_code": "PA", "subdomain": "philadelphia",  "name": "Philadelphia"},
        {"state_code": "RI", "subdomain": "providence",    "name": "Rhode Island"},
        {"state_code": "SC", "subdomain": "columbia",      "name": "Columbia"},
        {"state_code": "SD", "subdomain": "siouxfalls",    "name": "Sioux Falls"},
        {"state_code": "TN", "subdomain": "nashville",     "name": "Nashville"},
        {"state_code": "TX", "subdomain": "austin",        "name": "Austin"},
        {"state_code": "UT", "subdomain": "slc",           "name": "Salt Lake City"},
        {"state_code": "VT", "subdomain": "vermont",       "name": "Vermont"},
        {"state_code": "VA", "subdomain": "richmond",      "name": "Richmond"},
        {"state_code": "WA", "subdomain": "seattle",       "name": "Seattle"},
        {"state_code": "WV", "subdomain": "parkersburg",   "name": "Parkersburg"},
        {"state_code": "WI", "subdomain": "milwaukee",     "name": "Milwaukee"},
        {"state_code": "WY", "subdomain": "wyoming",       "name": "Wyoming"},
    ]

    db.craigslist_sites.delete_many({})
    db.craigslist_sites.insert_many(cl_sites)
    logger.info("craigslist_sites_initialized", count=len(cl_sites))


if __name__ == "__main__":
    init_master_data()