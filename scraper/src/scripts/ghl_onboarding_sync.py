from dotenv import load_dotenv
import os
import sys
import re

# Load environment variables from project root before anything else
# Path from scraper/src/scripts/ghl_onboarding_sync.py to root .env
curr_dir = os.path.dirname(os.path.abspath(__file__))
# 1: src, 2: scraper, 3: root
env_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(curr_dir))), ".env")

if os.path.exists(env_path):
    load_dotenv(env_path)
else:
    # Try project root based on common structure
    root_path = os.path.abspath(os.path.join(curr_dir, "../../..")) # Faster fallback
    env_path = os.path.join(root_path, ".env")
    load_dotenv(env_path)

from datetime import datetime
from pymongo import MongoClient

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from integrations.ghl import GHLClient
from logger import get_logger
from utils.mappings import get_mapping_manager

logger = get_logger(__name__)

def _clean(s):
    """Strip non-alphanumeric chars and lowercase for comparison."""
    return re.sub(r'[^a-zA-Z0-9]', '', str(s)).lower() if s else ""

def validate_geo_data(db, state_input, city_input):
    """Standardize state and city based on master geo_data."""
    if not state_input:
        return state_input, city_input, None

    # 1. Match State
    
    clean_state = _clean(state_input)
    # Search by code (MA) or name (Massachusetts)
    state_doc = db.geo_data.find_one({
        "$or": [
            {"state_code": {"$regex": f"^{state_input}$", "$options": "i"}},
            {"state_name": {"$regex": f"^{state_input}$", "$options": "i"}}
        ]
    })
    
    # If not found with exact, try cleaner match
    if not state_doc:
        all_states = db.geo_data.find({}, {"state_name": 1, "state_code": 1})
        for s in all_states:
            if _clean(s['state_name']) == clean_state or _clean(s['state_code']) == clean_state:
                state_doc = db.geo_data.find_one({"_id": s["_id"]})
                break

    if not state_doc:
        logger.warning("state_not_found_in_master", input=state_input)
        return state_input, city_input, None

    std_state = state_doc["state_name"]
    std_code = state_doc["state_code"]
    std_city = city_input

    # 2. Match City within that state
    if city_input:
        clean_city = _clean(city_input)
        matched_city = next((c for c in state_doc["cities"] if _clean(c) == clean_city), None)
        
        if matched_city:
            std_city = matched_city
        else:
            pattern = re.compile(re.escape(city_input), re.IGNORECASE)
            matched_city = next((c for c in state_doc["cities"] if pattern.search(c)), None)
            if matched_city: std_city = matched_city
            else: logger.warning("city_not_found_in_state", city=city_input, state=std_state)

    return std_state, std_city, std_code

def validate_verticals(db, raw_verticals):
    """Standardize vertical names by matching against master verticals collection."""
    if not raw_verticals:
        return []
    

    
    # Load all master verticals
    master_verticals = list(db.verticals.find({}, {"name": 1, "slug": 1}))
    if not master_verticals:
        logger.warning("no_master_verticals_found", msg="verticals collection is empty")
        return raw_verticals  # Return as-is if no master data
    
    validated = []
    for raw_v in raw_verticals:
        raw_v = raw_v.strip()
        if not raw_v:
            continue
        
        clean_raw = _clean(raw_v)
        matched = None
        
        # 1. Exact match (case-insensitive)
        for mv in master_verticals:
            if _clean(mv['name']) == clean_raw or _clean(mv.get('slug', '')) == clean_raw:
                matched = mv['name']
                break
        
        # 2. Partial/substring match
        if not matched:
            for mv in master_verticals:
                if clean_raw in _clean(mv['name']) or _clean(mv['name']) in clean_raw:
                    matched = mv['name']
                    break
        
        # 3. Slug-based match (e.g., "landscaping" -> "Landscaping Services")
        if not matched:
            for mv in master_verticals:
                slug = mv.get('slug', '')
                if slug and (clean_raw in _clean(slug) or _clean(slug) in clean_raw):
                    matched = mv['name']
                    break
        
        if matched:
            if matched != raw_v:
                logger.info("vertical_corrected", original=raw_v, corrected=matched)
            validated.append(matched)
        else:
            logger.warning("vertical_not_found_in_master", vertical=raw_v)
            validated.append(raw_v)  # Keep original if no match
    
    return validated

def sync_ghl_onboarding():
    load_dotenv()
    
    env = os.getenv("GHL_ENVIRONMENT", "sandbox")
    api_key = os.getenv(f"GHL_{env.upper()}_API_KEY") or os.getenv("GHL_API_KEY")
    loc_id = os.getenv(f"GHL_{env.upper()}_LOCATION_ID") or os.getenv("GHL_LOCATION_ID")
    
    if not api_key or not loc_id:
        logger.error("ghl_credentials_missing", env=env)
        return

    ghl = GHLClient(api_key, loc_id)
    
    mongo_uri = os.getenv("MONGO_URI")
    db_name = os.getenv("MONGO_DB", "PUFF")
    client = MongoClient(mongo_uri)
    db = client[db_name]
    collection = db["users"]

    logger.info("starting_ghl_sync", location_id=loc_id)
    
    contacts = ghl.get_contacts(limit=0)
    
    
    custom_fields = ghl.get_custom_fields()
    field_id_to_name = {f['id']: f['name'] for f in custom_fields}
    
    synced_count = 0
    
    for contact in contacts:
        cf_values = {field_id_to_name.get(f['id'], f['id']): f['value'] for f in contact.get('customFields', [])}

        def get_cf(pattern):
            for k, v in cf_values.items():
                if pattern.lower() in k.lower(): return v
            return None

        # Reverted to strict AND logic as requested
        source_val = contact.get('source')
        cf_source_val = get_cf("Contact Source")
        contact_type = str(contact.get('type') or "").lower()
        cf_contact_type = str(get_cf("Contact Type") or "").lower()
        tags = [str(t).lower() for t in contact.get('tags', [])]

        # Check source field, custom field, OR tags for "Dino Landscape"
        is_dino_source = (source_val == 'Dino Landscape') or \
                        (cf_source_val == 'Dino Landscape') or \
                        ('dino landscape' in tags)
        
        is_customer = (contact_type == 'customer') or (cf_contact_type == 'customer')
        
        logger.info("processing_raw_contact_start", 
                    contact_id=contact.get('id'), 
                    email=contact.get('email'))
        
        # Strict AND: Must be the right source AND the right type
        if not (is_dino_source and is_customer):
            reason = []
            if not is_dino_source: reason.append("source_mismatch")
            if not is_customer: reason.append("type_not_customer")
            
            logger.debug("skipping_contact", 
                       email=contact.get('email'), 
                       reason="+".join(reason), 
                       source=source_val or cf_source_val,
                       type=contact_type or cf_contact_type)
            continue
        
        raw_state = contact.get('state') or get_cf("State")
        raw_city = contact.get('city') or get_cf("City")
        
        # Validate and Standardize Geo Data
        std_state, std_city, std_code = validate_geo_data(db, raw_state, raw_city)

        # Parse and Validate Verticals (Handle list or comma-separated string)
        raw_v_data = get_cf("Verticals") or []
        if isinstance(raw_v_data, str):
            raw_verticals = [v.strip() for v in raw_v_data.split(",") if v.strip()]
        elif isinstance(raw_v_data, list):
            raw_verticals = [str(v).strip() for v in raw_v_data if str(v).strip()]
        else:
            raw_verticals = [str(raw_v_data).strip()] if raw_v_data else []
            
        validated_verticals = validate_verticals(db, raw_verticals)

        onboarding_doc = {
            "user": {
                "name": contact.get('name') or f"{contact.get('firstName', '')} {contact.get('lastName', '')}".strip(),
                "email": contact.get('email'),
                "phone": contact.get('phone'),
                "state": std_state,
                "city": std_city,
                "state_code": std_code,
                "region": get_cf("Region"),
                "service_area": get_cf("Service Area"),
                "verticals": validated_verticals,
                "onboarding_status": "pending"
            },
            "metadata": {
                "source": "GHL_Onboarding_Form",
                "environment": "test",
                "synced_at": datetime.utcnow().isoformat(),
                "ghl_contact_id": contact.get('id')
            }
        }

        # 3. Generate and Store Platform URLs
        mapper = get_mapping_manager()
        mappings = mapper.get_mappings_for_user(onboarding_doc)
        
        # Consolidate URLs across all mappings (Primary + Service Area)
        fb_urls = []
        nd_urls = []
        cl_urls = []
        
        for m in mappings:
            fb_urls.extend(m.get("facebook", {}).get("group_urls", []))
            nd_urls.extend(m.get("nextdoor", {}).get("group_urls", []))
            cl_urls.extend(m.get("craigslist", {}).get("urls", []))
            
        onboarding_doc["facebook"] = {"group_urls": list(set(fb_urls)), "page_urls": []}
        onboarding_doc["nextdoor"] = {"group_urls": list(set(nd_urls))}
        onboarding_doc["craigslist"] = {"urls": list(set(cl_urls))}

        if not onboarding_doc["user"]["email"]:
            logger.warning("skipping_contact_no_email", contact_id=contact.get('id'))
            continue

        # Log full document for transparency
        logger.info("syncing_document", 
                   email=onboarding_doc["user"]["email"], 
                   facebook_urls=len(onboarding_doc["facebook"]["group_urls"]),
                   nextdoor_urls=len(onboarding_doc["nextdoor"]["group_urls"]),
                   craigslist_urls=len(onboarding_doc["craigslist"]["urls"]))

        collection.update_one(
            {"user.email": onboarding_doc["user"]["email"]},
            {"$set": onboarding_doc},
            upsert=True
        )
        synced_count += 1
        logger.info("contact_synced", email=onboarding_doc["user"]["email"])
        
        # Internal Notification Placeholder
        logger.info("INTERNAL_NOTIFICATION: New user signup synced from GHL", 
                    name=onboarding_doc["user"]["name"], 
                    email=onboarding_doc["user"]["email"],
                    verticals=onboarding_doc["user"]["verticals"])

    logger.info("ghl_sync_complete", synced=synced_count)

if __name__ == "__main__":
    sync_ghl_onboarding()

