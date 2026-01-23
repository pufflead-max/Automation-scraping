#!/usr/bin/env python3
import sys
import os

# Add scraper/src to path for imports
script_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.append(os.path.join(script_dir, "scraper", "src"))

try:
    from integrations.ghl import GHLClient
    from config import get_ghl_config
except ImportError as e:
    print(f"❌ Error: Could not import scraper modules. {e}")
    sys.exit(1)

def get_contact(contact_id: str):
    ghl_config = get_ghl_config()
    client = GHLClient(ghl_config['api_key'], ghl_config['location_id'])
    
    endpoint = f"/contacts/{contact_id}"
    result = client._make_request("GET", endpoint)
    print(result)

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python3 get_ghl_contact.py [CONTACT_ID]")
        sys.exit(1)
    get_contact(sys.argv[1])
