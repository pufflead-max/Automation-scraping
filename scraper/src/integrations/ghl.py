"""GoHighLevel integration client."""

import requests
from typing import Dict, Any, Optional, List
try:
    from ..logger import get_logger
except ImportError:
    from logger import get_logger

logger = get_logger(__name__)

class GHLClient:
    """Client for interacting with GoHighLevel API."""
    
    BASE_URL = "https://rest.gohighlevel.com/v1"
    
    def __init__(self, api_key: str, location_id: str):
        self.api_key = api_key
        self.location_id = location_id
        self.headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        self._custom_fields_cache: Dict[str, str] = {}
        logger.info("ghl_client_initialized", location_id=location_id)

    def get_custom_fields(self) -> List[Dict[str, Any]]:
        """Fetch all custom fields for the location."""
        try:
            url = f"{self.BASE_URL}/custom-fields/"
            response = requests.get(url, headers=self.headers)
            response.raise_for_status()
            fields = response.json().get('customFields', [])
            
            # Cache fields by name for easier mapping
            for field in fields:
                self._custom_fields_cache[field['name']] = field['id']
            
            logger.info("ghl_custom_fields_fetched", count=len(fields))
            return fields
        except Exception as e:
            logger.error("ghl_get_custom_fields_failed", error=str(e))
            return []

    def get_field_id(self, field_name: str) -> Optional[str]:
        """Get field ID by name using cache."""
        if not self._custom_fields_cache:
            self.get_custom_fields()
        return self._custom_fields_cache.get(field_name)

    def create_contact(self, contact_data: Dict[str, Any]) -> Optional[str]:
        """Create or update a contact in GHL."""
        try:
            # Ensure locationId is present
            if 'locationId' not in contact_data:
                contact_data['locationId'] = self.location_id
            
            url = f"{self.BASE_URL}/contacts/"
            response = requests.post(url, headers=self.headers, json=contact_data)
            
            if response.status_code == 400 and "already exists" in response.text:
                logger.info("ghl_contact_already_exists", email=contact_data.get('email'))
                # We could update here if needed, but the user said "everything else is handled automatically"
                return None
                
            response.raise_for_status()
            result = response.json()
            contact_id = result.get('contact', {}).get('id')
            logger.info("ghl_contact_created", contact_id=contact_id)
            return contact_id
        except Exception as e:
            logger.error("ghl_create_contact_failed", error=str(e), payload=contact_data)
            return None

    def map_lead_to_ghl(self, lead: Dict[str, Any], mapping: Dict[str, str]) -> Dict[str, Any]:
        """
        Map a ScrapedLead dictionary to GHL contact structure.
        mapping: Dictionary mapping ScrapedLead keys to GHL fields or custom field names.
        """
        ghl_contact = {
            "locationId": self.location_id,
            "customField": {}
        }
        
        # Standard GHL fields
        standard_fields = ['firstName', 'lastName', 'name', 'email', 'phone', 'address1', 'city', 'state', 'country', 'postalCode', 'companyName', 'website', 'tags']
        
        for lead_key, ghl_key in mapping.items():
            value = lead.get(lead_key)
            if not value:
                continue
                
            if ghl_key in standard_fields:
                ghl_contact[ghl_key] = value
            else:
                # Treat as custom field name
                field_id = self.get_field_id(ghl_key)
                if field_id:
                    ghl_contact['customField'][field_id] = str(value)
                else:
                    logger.warning("ghl_custom_field_not_found", field_name=ghl_key)
        
        # Cleanup empty custom fields
        if not ghl_contact['customField']:
            del ghl_contact['customField']
            
        return ghl_contact
