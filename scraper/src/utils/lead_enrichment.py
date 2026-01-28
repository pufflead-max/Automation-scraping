"""
Lead Enrichment Utility Module

This module handles:
1. Vertical classification (Business category detection)
2. Phone number extraction
3. City/Location extraction and normalization
"""

import re
import phonenumbers
from typing import Optional, List, Dict, Tuple

class LeadEnricher:
    """Enriches lead data with vertical, phone, and location info."""

    # Vertical Keywords Mapping
    VERTICALS = {
        "Landscaping": [
            "landscap", "lawn", "mow", "grass", "yard work", "garden", "mulch", "leaf removal", 
            "weeding", "trimming bushes", "hedge", "tree service", "stump", "sprinkler"
        ],
        "Snow Removal": [
            "snow", "plow", "shovel", "ice", "salting", "driveway clearing", "snowblow"
        ],
        "Cleaning": [
            "clean", "maid", "housekeeping", "house keeping", "deep clean", "move out clean", 
            "janitor", "commercial cleaning", "office cleaning", "carpet clean", "window wash"
        ],
        "Handyman": [
            "handyman", "handy man", "small repairs", "fix it", "assembly", "mounting", "odd jobs",
            "honey do list", "general repair"
        ],
        "Painting": [
            "paint", "stain", "interior", "exterior", "cabinet refinish", "wallpaper"
        ],
        "Plumbing": [
            "plumb", "leak", "clog", "drain", "pipe", "faucet", "toilet", "water heater", 
            "sewer", "disposal", "shower valve"
        ],
        "Electrical": [
            "electric", "wires", "outlet", "switch", "fixture", "breaker", "panel", "lighting", "ceiling fan"
        ],
        "Roofing": [
            "roof", "shingle", "leak in ceiling", "gutter", "downspout", "chimney"
        ],
        "Fencing": [
            "fence", "fencing", "gate repair", "post replacement"
        ],
        "General Contractor": [
            "remodel", "renovat", "addition", "construction", "basement finish", "kitchen remodel",
            "bathroom remodel", "deck build", "new build", "general contractor"
        ],
        "Mechanic": [
            "mechanic", "auto repair", "car repair", "brake", "oil change", "engine", "transmission",
            "tire", "truck repair", "automotive"
        ]
    }

    # Common US City suffixes to help identify cities in text
    CITY_INDICATORS = [
        "area", "city", "town", "village", "county"
    ]

    @classmethod
    def extract_vertical(cls, text: str) -> Optional[str]:
        """
        Detects the business vertical based on keywords in the text.
        text: Combined title and description.
        Returns: The name of the vertical or None.
        """
        if not text:
            return None
        
        text_lower = text.lower()
        
        # Check each vertical
        scores = {}
        for vertical, keywords in cls.VERTICALS.items():
            count = 0
            for keyword in keywords:
                if keyword in text_lower:
                    count += 1
            if count > 0:
                scores[vertical] = count
        
        if not scores:
            return None
            
        # Return the vertical with the most keyword matches
        # If tie, return the first one found (arbitrary but stable)
        best_vertical = max(scores.items(), key=lambda x: x[1])[0]
        return best_vertical

    @classmethod
    def extract_phone(cls, text: str) -> Optional[str]:
        """
        Extracts phone number from text using phonenumbers library and regex fallback.
        """
        if not text:
            return None
            
        # 1. Try phonenumbers library for US
        try:
            for match in phonenumbers.PhoneNumberMatcher(text, "US"):
                return phonenumbers.format_number(match.number, phonenumbers.PhoneNumberFormat.NATIONAL)
        except Exception:
            pass

        # 2. Regex Fallback for common formats often missed if formatting is weird
        # Matches: (123) 456-7890, 123-456-7890, 123 456 7890, 123.456.7890
        phone_pattern = re.compile(r'\(?\b[2-9][0-9]{2}\)?[-. \u00A0]?[2-9][0-9]{2}[-. \u00A0]?[0-9]{4}\b')
        match = phone_pattern.search(text)
        if match:
             return match.group(0).strip()
             
        return None

    @classmethod
    def extract_city(cls, text: str, existing_location: str = None) -> Optional[str]:
        """
        Attempts to extract a clean city name.
        1. If existing_location is provided, tries to clean it.
        2. Searches text for "in [City]" patterns (heuristics).
        """
        # Strategy 1: Use existing location field if available
        if existing_location:
            # Common cleanup: remove state codes like ", MA" or " (Neighborhood)"
            # Example: "Boston, MA" -> "Boston"
            # Example: "Dorchester (Boston)" -> "Dorchester" or "Boston" - let's default to the whole string mostly but cleaned
            clean_loc = re.sub(r',\s*[A-Z]{2}$', '', existing_location).strip() # Remove state suffix
            clean_loc = re.sub(r'\s*\([^\)]+\)', '', clean_loc).strip() # Remove parens
            if clean_loc:
                return clean_loc

        # Strategy 2: Look for "in [City]" or "near [City]" in text
        # This is a weak heuristic, but better than nothing if location is missing.
        # We look for Capitalized Words after "in" or "near".
        
        # Regex for "in [City]" where City is Title Case
        # Matches "in Boston", "in New York", "near Cambridge"
        match = re.search(r'\b(in|near)\s+([A-Z][a-z]+(?:\s[A-Z][a-z]+)*)', text)
        if match:
             # Validate length to avoid "in The", "in My House"
             city_candidate = match.group(2)
             ignored_words = {"The", "My", "A", "An", "This", "Our", "Good", "Bad", "High", "Low"}
             if city_candidate not in ignored_words and len(city_candidate) > 2:
                 return city_candidate

        return None

    @classmethod
    def enrich(cls, lead_data: Dict) -> Dict:
        """
        Enriches a lead dictionary with vertical, phone, and city data.
        Updates the dictionary in place and returns it.
        """
        title = lead_data.get('title', '') or ''
        description = lead_data.get('description', '') or ''
        combined_text = f"{title} \n {description}"
        
        # Vertical
        vertical = cls.extract_vertical(combined_text)
        lead_data['vertical'] = vertical
        
        # Phone
        phone = cls.extract_phone(combined_text)
        lead_data['phone'] = phone
        
        # City 
        # Prefer explicit city field if scraper extracted it separately
        existing_city = lead_data.get('city') 
        existing_location = lead_data.get('location')
        
        if not existing_city:
             extracted_city = cls.extract_city(combined_text, existing_location)
             if extracted_city:
                 lead_data['city'] = extracted_city
        
        return lead_data
