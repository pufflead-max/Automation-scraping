from dotenv import load_dotenv
load_dotenv()

import os
import sys
import requests
from pymongo import MongoClient

# Add parent directory to path to import local modules
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    from logger import get_logger
    logger = get_logger("init_geo_data")
except ImportError:
    import logging
    logging.basicConfig(level=logging.INFO)
    logger = logging.getLogger("init_geo_data")

def init_geo_data():
    """Fetch US states and cities and save to MongoDB."""
    
    mongo_uri = os.getenv("MONGO_URI", "mongodb://localhost:27017")
    db_name = os.getenv("MONGO_DB", "PUFF")
    
    client = MongoClient(mongo_uri)
    db = client[db_name]
    collection = db["geo_data"]
    
    # Public URL for US States and Cities JSON (Comprehensive)
    URL = "https://raw.githubusercontent.com/cschoi3/US-states-and-cities-json/master/data.json"
    
    logger.info(f"Fetching geo data from {URL}...")
    
    try:
        response = requests.get(URL)
        response.raise_for_status()
        data = response.json() # Format: {"Alabama": ["ABBEVILLE", ...], ...}
        
        # Mapping of State Name to Abbreviation
        state_abbrs = {
            "Alabama": "AL", "Alaska": "AK", "Arizona": "AZ", "Arkansas": "AR", "California": "CA",
            "Colorado": "CO", "Connecticut": "CT", "Delaware": "DE", "Florida": "FL", "Georgia": "GA",
            "Hawaii": "HI", "Idaho": "ID", "Illinois": "IL", "Indiana": "IN", "Iowa": "IA",
            "Kansas": "KS", "Kentucky": "KY", "Louisiana": "LA", "Maine": "ME", "Maryland": "MD",
            "Massachusetts": "MA", "Michigan": "MI", "Minnesota": "MN", "Mississippi": "MS", "Missouri": "MO",
            "Montana": "MT", "Nebraska": "NE", "Nevada": "NV", "New Hampshire": "NH", "New Jersey": "NJ",
            "New Mexico": "NM", "New York": "NY", "North Carolina": "NC", "North Dakota": "ND", "Ohio": "OH",
            "Oklahoma": "OK", "Oregon": "OR", "Pennsylvania": "PA", "Rhode Island": "RI", "South Carolina": "SC",
            "South Dakota": "SD", "Tennessee": "TN", "Texas": "TX", "Utah": "UT", "Vermont": "VT",
            "Virginia": "VA", "Washington": "WA", "West Virginia": "WV", "Wisconsin": "WI", "Wyoming": "WY",
            "District of Columbia": "DC", "American Samoa": "AS", "Guam": "GU", "Northern Mariana Islands": "MP",
            "Puerto Rico": "PR", "Virgin Islands": "VI", "Maryland": "MD", "Maine": "ME", "Mississippi": "MS",
            "Missouri": "MO", "Montana": "MT"
        }
        
        geo_docs = []
       
        for state_name, cities in data.items():
            state_name = state_name.strip()
            abbr = state_abbrs.get(state_name)
            
            if not abbr:
                # If it's a 2-letter key already, use it
                if len(state_name) == 2:
                    abbr = state_name.upper()
                else:
                    # Skip unknown states that would collide with major codes
                    # Marshall Islands starts with MA, but we want Massachusetts to have MA.
                    continue 

            # Sanitize cities: title case for better display
            sanitized_cities = sorted(list(set([c.strip().title() for c in cities if c.strip()])))
            
            doc = {
                "state_name": state_name,
                "state_code": abbr,
                "cities": sanitized_cities,
                "updated_at": os.popen('date').read().strip()
            }
            geo_docs.append(doc)
            
        if geo_docs:
            # Clear existing geo data
            collection.delete_many({})
            # Insert new data
            collection.insert_many(geo_docs)
            logger.info(f"Successfully saved {len(geo_docs)} states and their cities to MongoDB.")
        else:
            logger.warning("No geo data found to save.")
            
    except Exception as e:
        logger.error(f"Failed to initialize geo data: {e}")
        sys.exit(1)

if __name__ == "__main__":
    init_geo_data()
