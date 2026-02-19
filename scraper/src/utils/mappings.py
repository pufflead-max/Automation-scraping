import os
import sys
from typing import List, Dict, Any, Optional

try:
    from database import get_db_manager
except ImportError:
    from ..database import get_db_manager

class MappingManager:
    def __init__(self):
        self.db = get_db_manager()
        self.users_col = "users"
        self.mappings_col = "group_mappings"
        self.verticals_col = "verticals"

    def get_vertical_map(self) -> Dict[str, str]:
        """Map GHL vertical names to slugs. Loads from MongoDB first, falls back to hardcoded."""
        # Hardcoded fallback
        fallback = {
            "Landscaping Services": "landscaping",
            "Painting Services": "painting",
            "Asphalt Paving Services": "asphalt_paving",
            "Carpentry Services": "carpentry",
            "Fence Installation & Repair": "fencing",
            "Flooring Installation & Repair": "flooring",
            "Cleaning services": "cleaning"
        }
        
        # Load from MongoDB verticals collection dynamically
        try:
            master_verticals = self.db.find_many(self.verticals_col, {})
            if master_verticals:
                db_map = {mv['name']: mv['slug'] for mv in master_verticals if 'name' in mv and 'slug' in mv}
                # Merge: DB takes precedence over hardcoded
                fallback.update(db_map)
        except Exception:
            pass
        
        return fallback

    def _resolve_vertical_slug(self, vertical_name: str) -> str:
        """Resolve a vertical name to its slug, case-insensitive."""
        v_map = self.get_vertical_map()
        
        # Try exact match first
        if vertical_name in v_map:
            return v_map[vertical_name]
        
        # Try case-insensitive match
        lower_name = vertical_name.lower()
        for name, slug in v_map.items():
            if name.lower() == lower_name:
                return slug
        
        # Fallback: slugify the name
        return vertical_name.lower().replace(" ", "_").replace("&", "and")

    def _get_craigslist_subdomain(self, state_code: str, city: str) -> str:
        """Map city/state to craigslist subdomain."""
        if state_code == "MA":
            return "boston"
        # Add more mappings as needed
        return "geo" # Default

    def _get_craigslist_categories(self, vertical: str) -> List[str]:
        """Map vertical to Craigslist category codes."""
        cats = {
            "landscaping": ["fgs", "lbg", "hss"],
            "cleaning": ["hss"],
            "painting": ["hss", "lbg"],
            "asphalt_paving": ["hss", "lbg"],
            "carpentry": ["hss", "lbg"],
            "fencing": ["hss", "lbg"],
            "flooring": ["hss", "lbg"]
        }
        return cats.get(vertical, ["hss", "lbg", "sss"]) # Extended defaults

    def _get_region_path(self, region: str) -> str:
        """Map region name to Craigslist region path."""
        if not region: return ""
        r = region.lower()
        if "south shore" in r: return "/sob"
        if "greater boston" in r: return "/gbs"
        if "northwest" in r: return "/nwb"
        return ""

    def get_user_mappings(self, user_email: str) -> List[Dict[str, Any]]:
        """Get all group mappings applicable to a user based on their verticals and location."""
        user_doc = self.db.find_one(self.users_col, {"user.email": user_email})
        if not user_doc:
            return []

        user_data = user_doc.get("user", {})
        user_verticals = user_data.get("verticals", [])
        user_state = user_data.get("state")
        user_city = user_data.get("city")

        if not user_verticals:
            return []

        v_slugs = [self._resolve_vertical_slug(v) for v in user_verticals]

        query = {
            "vertical": {"$in": v_slugs}
        }
        
        # Optionally filter by state/city if available
        if user_state:
            query["state"] = user_state
        if user_city:
            query["city"] = user_city

        results = self.db.find_many(self.mappings_col, query)
        
        # If no hardcoded results, generate dynamically
        if not results and user_city and (user_state or user_data.get("state_code")):
            state_code = user_data.get("state_code") or (user_state[:2].upper() if user_state else "MA")
            region = user_data.get("region")
            
            for v_slug in v_slugs:
                # 1. Nextdoor Dynamic URL
                city_slug = user_city.lower().replace(" ", "-")
                nd_url = f"https://nextdoor.com/city/{city_slug}--{state_code.lower()}/"
                
                # 2. Craigslist Dynamic URLs
                cl_subdomain = self._get_craigslist_subdomain(state_code, user_city)
                cl_region = self._get_region_path(region)
                cl_cats = self._get_craigslist_categories(v_slug)
                
                cl_urls = []
                for cat in cl_cats:
                    url = f"https://{cl_subdomain}.craigslist.org/search{cl_region}/{cat}?query={user_city.lower()}"
                    cl_urls.append(url)

                results.append({
                    "state": user_state,
                    "city": user_city,
                    "vertical": v_slug,
                    "nextdoor": {"group_urls": [nd_url]},
                    "craigslist": {"urls": cl_urls},
                    "facebook": {"group_urls": [], "page_urls": []},
                    "source": "dynamic_generator"
                })
        
        return results

    def get_vertical_config(self, vertical_slug: str) -> Optional[Dict[str, Any]]:
        """Get keywords and indicators for a vertical."""
        return self.db.find_one(self.verticals_col, {"slug": vertical_slug})

def get_mapping_manager():
    return MappingManager()
