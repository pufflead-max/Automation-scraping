import os
import sys
import json
import argparse
from typing import Dict, Any

# Add src to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from user_credential_manager import UserCredentialManager

def onboard_client(email: str, name: str, vertical: str, city: str, phone: str = "000-000-0000"):
    """
    Onboard a client dynamically using vertical templates and geographic parameters.
    """
    # Try multiple common locations for verticals.json
    possible_paths = [
        os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "configs", "verticals.json"),
        "/opt/airflow/scraper/src/configs/verticals.json",
        "./scraper/src/configs/verticals.json"
    ]
    
    v_conf = None
    for path in possible_paths:
        if os.path.exists(path):
            with open(path, "r") as f:
                verticals = json.load(f)
                v_conf = verticals.get(vertical)
                break
    
    if not v_conf:
        print(f"❌ Vertical '{vertical}' not found in configuration templates or config file not found.")
        return
    
    # Construct Craigslist URLs dynamically based on City and Sections
    # Assuming Boston as the base domain for now, could be expanded
    base_domain = "https://boston.craigslist.org"
    sub_area = "sob" # Default to South Shore for many landscaping use cases
    
    cl_urls = []
    for section in v_conf.get("craigslist_sections", []):
        # Specific query URL
        cl_urls.append(f"{base_domain}/search/{sub_area}/{section}?query={city.lower()}")
        # General sub-area URL
        cl_urls.append(f"{base_domain}/search/{sub_area}/{section}")
        
    scraping_config = {
        "craigslist": {
            "urls": list(set(cl_urls)),
            "keywords": v_conf["keywords"],
            "exclude_keywords": v_conf["exclude_keywords"],
            "intent_indicators": v_conf["intent_indicators"],
            "max_pages": 10,
            "headless": True,
            "pipeline_id": v_conf["pipeline_id"],
            "stage_id": v_conf["stage_id"],
            "tags": [name, vertical.capitalize(), city.capitalize(), "MVP"] + v_conf.get("tags", [])
        },
        "nextdoor": {
            "urls": [f"https://nextdoor.com/city/{city.lower()}–ma"],
            "keywords": v_conf["keywords"],
            "exclude_keywords": v_conf["exclude_keywords"],
            "max_pages": 5,
            "daily_limit": 50,
            "region": city.capitalize()
        }
    }
    
    manager = UserCredentialManager()
    manager.add_user_credentials(
        user_email=email,
        user_name=name,
        user_phone=phone,
        facebook_email=email, # Assuming email is same for login
        facebook_password=os.getenv("FACEBOOK_PASSWORD", "Dino0001"),
        nextdoor_email=os.getenv("NEXTDOOR_EMAIL", "nicknickbru@gmail.com"),
        nextdoor_password=os.getenv("NEXTDOOR_PASSWORD"),
        scraping_config=scraping_config
    )
    print(f"✅ Successfully onboarded {name} for {vertical} in {city}.")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Onboard a new client dynamically.")
    parser.add_argument("--email", required=True)
    parser.add_argument("--name", required=True)
    parser.add_argument("--vertical", required=True, help="e.g. landscaping")
    parser.add_argument("--city", required=True, help="e.g. hingham")
    
    args = parser.parse_args()
    onboard_client(args.email, args.name, args.vertical, args.city)
