"""
Lead Enrichment Utility Module  

Handles vertical classification, phone extraction, and location normalization.
Optimized for fewer lines while maintaining accuracy.
"""

import re
import phonenumbers
from typing import Optional, Dict, List
try:
    from .mappings import get_mapping_manager
except ImportError:
    from mappings import get_mapping_manager

class LeadEnricher:
    """Enriches lead data with vertical, phone, and location info."""

    # Vertical Keywords Mapping (condensed)
    # These are defaults; we prefer loading from MongoDB/MappingManager
    VERTICALS = {
        "Landscaping": ["landscap", "lawn", "mow", "grass", "yard work", "garden", "mulch", "leaf removal", 
                        "weeding", "trimming bushes", "hedge", "tree service", "stump", "sprinkler", "yard cleanup", "yard",
                        "branch removal", "clean up", "cleanup", "brush removal", "leaves", "fall clean", "spring clean"],
        "Snow Removal": ["snow", "plow", "shovel", "ice", "salting", "driveway clearing", "snowblow"],
        "Cleaning": ["clean", "maid", "housekeeping", "house keeping", "deep clean", "move out clean", 
                     "janitor", "commercial cleaning", "office cleaning", "carpet clean", "window wash"],
        "Kitchen & Bath Renovations": ["remodel", "renovat", "addition", "construction", "basement finish", 
                                       "kitchen remodel", "bathroom remodel", "deck build", "new build", 
                                       "cabinet installation", "countertop", "vanity installation", "cabinets", "countertops"],
        "Plumbing": ["plumb", "leak", "clog", "drain", "pipe", "faucet", "toilet", "water heater", 
                     "sewer", "disposal", "shower valve", "sump pump", "water heater"],
        "Electrical Services": ["electric", "wires", "outlet", "switch", "fixture", "breaker", "panel", 
                                "lighting", "ceiling fan", "generator", "wiring"],
        "Painting": ["paint", "stain", "interior", "exterior", "cabinet refinish", "wallpaper", "painter"],
        "Roofing": ["roof", "shingle", "leak in ceiling", "gutter", "downspout", "chimney", "skylight"],
        "Fencing": ["fence", "fencing", "gate repair", "post replacement", "vinyl fence"],
        "Handyman": ["handyman", "handy man", "small repairs", "fix it", "assembly", "mounting", 
                     "odd jobs", "honey do list", "general repair", "drywall", "patching"],
        "Mechanic": ["mechanic", "auto repair", "car repair", "brake", "oil change", "engine", 
                     "transmission", "tire", "truck repair", "automotive"]
    }

    # Compiled regex patterns for efficiency
    PHONE_PATTERN = re.compile(r'\(?\b[2-9][0-9]{2}\)?[-. \u00A0]?[2-9][0-9]{2}[-. \u00A0]?[0-9]{4}\b')
    CITY_PATTERN = re.compile(r'\b(in|near)\s+([A-Z][a-z]+(?:\s[A-Z][a-z]+)*)')
    LOCATION_CLEAN = re.compile(r',\s*[A-Z]{2}$|\s*\([^\)]+\)')
    IGNORED_CITIES = {"The", "My", "A", "An", "This", "Our", "Good", "Bad", "High", "Low"}

    @classmethod
    def extract_vertical(cls, text: str) -> Optional[str]:
        """Detects business vertical based on keyword matches."""
        if not text:
            return None
        
        text_lower = text.lower()
        
        # 1. Try to get dynamic vertical list from MappingManager/MongoDB
        try:
            mapper = get_mapping_manager()
            master_verticals = mapper.db.find_many("verticals", {})
            if master_verticals:
                # Build score map dynamically from DB keywords
                scores = {}
                for mv in master_verticals:
                    name = mv.get('name')
                    keywords = mv.get('keywords', [])
                    if name and keywords:
                        score = sum(1 for kw in keywords if kw.lower() in text_lower)
                        if score > 0:
                            scores[name] = score
                
                if scores:
                    return max(scores.items(), key=lambda x: x[1])[0]
        except Exception:
            pass # Fallback to hardcoded

        # 2. Hardcoded fallback
        scores = {vertical: sum(1 for kw in keywords if kw in text_lower) 
                  for vertical, keywords in cls.VERTICALS.items()}
        scores = {k: v for k, v in scores.items() if v > 0}
        
        return max(scores.items(), key=lambda x: x[1])[0] if scores else None

    @classmethod
    def extract_phone(cls, text: str) -> Optional[str]:
        """Extracts phone number using phonenumbers library with regex fallback."""
        if not text:
            return None
        
        # Try phonenumbers library first
        try:
            match = next(phonenumbers.PhoneNumberMatcher(text, "US"), None)
            if match:
                return phonenumbers.format_number(match.number, phonenumbers.PhoneNumberFormat.NATIONAL)
        except Exception:
            pass
        
        # Regex fallback
        match = cls.PHONE_PATTERN.search(text)
        return match.group(0).strip() if match else None

    @classmethod
    def extract_city(cls, text: str, existing_location: str = None) -> Optional[str]:
        """Extracts clean city name from location field or text."""
        # Clean existing location if available
        if existing_location:
            clean_loc = cls.LOCATION_CLEAN.sub('', existing_location).strip()
            if clean_loc:
                return clean_loc
        
        # Search for "in [City]" or "near [City]" pattern
        match = cls.CITY_PATTERN.search(text)
        if match:
            city = match.group(2)
            if city not in cls.IGNORED_CITIES and len(city) > 2:
                return city
        
        return None

    @classmethod
    def enrich(cls, lead_data: Dict) -> Dict:
        """Enriches lead dictionary with vertical, phone, and city data."""
        combined_text = f"{lead_data.get('title', '')} \n {lead_data.get('description', '')}"
        
        # Enrich all fields
        lead_data['vertical'] = cls.extract_vertical(combined_text)
        lead_data['phone'] = cls.extract_phone(combined_text)
        
        # Extract city only if not already present
        if not lead_data.get('city'):
            city = cls.extract_city(combined_text, lead_data.get('location'))
            if city:
                lead_data['city'] = city
        
        return lead_data