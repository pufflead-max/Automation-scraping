"""GoHighLevel integration client using direct API calls."""

import json
import time
import requests
from typing import Dict, Any, Optional, List

try:
    from ..logger import get_logger
except ImportError:
    try:
        from logger import get_logger
    except ImportError:
        import logging
        def get_logger(name):
            return logging.getLogger(name)

logger = get_logger(__name__)


class GHLClient:
    """Client for interacting with GoHighLevel API V2."""
    
    BASE_URL = "https://services.leadconnectorhq.com"
    
    def __init__(
        self, 
        api_key: str,
        location_id: str,
        **kwargs  # Accept but ignore other parameters for compatibility
    ):
        """
        Initialize GHL client.
        
        Args:
            api_key: Your GHL API key (bearer token)
            location_id: The GHL location ID to work with
        """
        self.api_key = api_key
        self.location_id = location_id
        self.headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "Version": "2021-07-28"
        }
        self._custom_fields_cache: Dict[str, str] = {}
        self._custom_object_schemas: Dict[str, str] = {}  # schema_name -> schema_id
        logger.info("ghl_client_initialized", location_id=location_id)

    def _make_request(
        self, 
        method: str, 
        endpoint: str, 
        data: Optional[Dict] = None,
        params: Optional[Dict] = None
    ) -> Optional[Dict[str, Any]]:
        """Make HTTP request to GHL API."""
        try:
            url = f"{self.BASE_URL}{endpoint}"
            response = requests.request(
                method=method,
                url=url,
                headers=self.headers,
                json=data,
                params=params,
                timeout=30
            )
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            logger.error(
                "ghl_api_request_failed",
                method=method,
                endpoint=endpoint,
                status=getattr(e.response, 'status_code', None),
                error=str(e),
                response=getattr(e.response, 'text', None)
            )
            return None

    # ===== CUSTOM OBJECTS METHODS =====
    
    def get_custom_object_schemas(self) -> List[Dict[str, Any]]:
        """Fetch all custom object schemas for the location."""
        try:
            # v2 official endpoint uses /objects/schemas with locationId query param
            endpoint = "/objects/schemas"
            params = {"locationId": self.location_id}
            result = self._make_request("GET", endpoint, params=params)
            
            if not result:
                return []
            
            schemas = result.get('schemas', [])
            
            # Cache schemas by name
            for schema in schemas:
                if 'name' in schema and 'id' in schema:
                    self._custom_object_schemas[schema['name']] = schema['id']
            
            logger.info("ghl_custom_object_schemas_fetched", count=len(schemas))
            return schemas
        except Exception as e:
            logger.error("ghl_get_custom_object_schemas_failed", error=str(e))
            return []
    
    def get_schema_id(self, schema_name: str) -> Optional[str]:
        """Get schema ID by name."""
        if not self._custom_object_schemas:
            self.get_custom_object_schemas()
        return self._custom_object_schemas.get(schema_name)
    
    def create_custom_object_schema(self, name: str, fields: List[Dict[str, Any]]) -> Optional[str]:
        """Create a new custom object schema."""
        try:
            endpoint = "/objects/schemas"
            payload = {
                "locationId": self.location_id,
                "name": name,
                "fields": fields
            }
            
            result = self._make_request("POST", endpoint, data=payload)
            
            if not result:
                return None
            
            schema_id = result.get('id')
            logger.info("ghl_custom_object_schema_created", name=name, schema_id=schema_id)
            return schema_id
        except Exception as e:
            logger.error("ghl_create_custom_object_schema_failed", error=str(e), name=name)
            return None
    
    def create_custom_object_record(self, schema_id: str, record_data: Dict[str, Any]) -> Optional[str]:
        """
        Create a custom object record.
        
        Args:
            schema_id: The schema ID
            record_data: Dictionary with field names and values
        
        Returns:
            record_id if successful, None otherwise
        """
        try:
            endpoint = f"/locations/{self.location_id}/customObjects/{schema_id}/records"
            
            result = self._make_request("POST", endpoint, data=record_data)
            
            if not result:
                return None
            
            record_id = result.get('id')
            logger.info("ghl_custom_object_record_created", schema_id=schema_id, record_id=record_id)
            return record_id
        except Exception as e:
            logger.error("ghl_create_custom_object_record_failed", error=str(e), schema_id=schema_id)
            return None
    
    def search_custom_object_records(self, schema_id: str, filters: Optional[Dict] = None) -> List[Dict[str, Any]]:
        """Search custom object records."""
        try:
            endpoint = f"/locations/{self.location_id}/customObjects/{schema_id}/records/search"
            
            payload = filters or {}
            result = self._make_request("POST", endpoint, data=payload)
            
            if not result:
                return []
            
            return result.get('records', [])
        except Exception as e:
            logger.error("ghl_search_custom_object_records_failed", error=str(e), schema_id=schema_id)
            return []
    
    # ===== CONTACTS METHODS (Keep for backward compatibility) =====
    
    def get_custom_fields(self) -> List[Dict[str, Any]]:
        """Fetch all custom fields for the location."""
        try:
            endpoint = f"/locations/{self.location_id}/customFields"
            result = self._make_request("GET", endpoint)
            
            if not result:
                return []
            
            fields = result.get('customFields', [])
            
            # Cache fields by name
            for field in fields:
                if 'name' in field and 'id' in field:
                    self._custom_fields_cache[field['name']] = field['id']
            
            logger.info("ghl_custom_fields_fetched", count=len(fields))
            return fields
        except Exception as e:
            logger.error("ghl_get_custom_fields_failed", error=str(e))
            return []

    def get_field_id(self, field_name: str) -> Optional[str]:
        """Get field ID by name using cache (case-insensitive fallback)."""
        if not self._custom_fields_cache:
            self.get_custom_fields()
        
        # Exact match
        if field_name in self._custom_fields_cache:
            return self._custom_fields_cache[field_name]
        
        # Case-insensitive match
        field_name_lower = field_name.lower()
        for name, id_val in self._custom_fields_cache.items():
            if name.lower() == field_name_lower:
                return id_val
                
        return None

    def create_contact(self, contact_data: Dict[str, Any]) -> Optional[str]:
        """Create a contact in GHL."""
        try:
            if 'locationId' not in contact_data:
                contact_data['locationId'] = self.location_id
            
            # GHL requires email or phone
            if not contact_data.get('email') and not contact_data.get('phone'):
                contact_data['email'] = self._generate_deterministic_email(contact_data)
            
            # Ensure contact name is a string and not empty
            if not contact_data.get('name'):
                contact_data['name'] = "Scraped Lead"

            # Convert customField dict to customFields array format (v2)
            if 'customField' in contact_data and contact_data['customField'] and 'customFields' not in contact_data:
                custom_fields_array = []
                for field_id, value in contact_data['customField'].items():
                    custom_fields_array.append({
                        "id": field_id,
                        "value": value
                    })
                contact_data['customFields'] = custom_fields_array
                del contact_data['customField']
            
            # Remove internal fields not supported by GHL standard properties
            internal_fields = ['source_url']
            for field in internal_fields:
                if field in contact_data:
                    del contact_data[field]
            
            endpoint = "/contacts/"
            result = self._make_request("POST", endpoint, data=contact_data)
            
            if not result:
                return None
            
            contact_id = result.get('contact', {}).get('id')
            logger.info("ghl_contact_created", contact_id=contact_id)
            return contact_id
        except Exception as e:
            error_msg = str(e)
            if "already exists" in error_msg.lower():
                logger.info("ghl_contact_already_exists", email=contact_data.get('email'))
                return None
            logger.error("ghl_create_contact_failed", error=error_msg, payload=contact_data)
            return None

    def upsert_contact(self, contact_data: Dict[str, Any]) -> Optional[str]:
        """Create or update a contact using upsert."""
        try:
            if 'locationId' not in contact_data:
                contact_data['locationId'] = self.location_id
            
            # GHL REQUIRES email or phone for upsert
            if not contact_data.get('email') and not contact_data.get('phone'):
                contact_data['email'] = self._generate_deterministic_email(contact_data)
            
            # Ensure contact name is a string and not empty
            if not contact_data.get('name'):
                contact_data['name'] = "Scraped Lead"

            # Convert customField dict to customFields array format (v2)
            if 'customField' in contact_data and contact_data['customField'] and 'customFields' not in contact_data:
                custom_fields_array = []
                for field_id, value in contact_data['customField'].items():
                    custom_fields_array.append({
                        "id": field_id,
                        "value": value
                    })
                contact_data['customFields'] = custom_fields_array
                del contact_data['customField']
            
            # Remove internal fields not supported by GHL standard properties
            internal_fields = ['source_url']
            for field in internal_fields:
                if field in contact_data:
                    del contact_data[field]
            
            endpoint = "/contacts/upsert"
            result = self._make_request("POST", endpoint, data=contact_data)
            
            if not result:
                return None
            
            contact_id = result.get('contact', {}).get('id')
            logger.info("ghl_contact_upserted", contact_id=contact_id)
            return contact_id
        except Exception as e:
            logger.error("ghl_upsert_contact_failed", error=str(e), payload=contact_data)
            return None

    # ===== SCRAPED LEAD METHODS =====
    
    def ensure_scraped_leads_schema(self) -> Optional[str]:
        """
        Ensure the 'Scraped Leads' custom object schema exists.
        Creates it if it doesn't exist.
        
        Returns:
            schema_id if successful, None otherwise
        """
        schema_name = "Scraped Leads"
        
        # Check if schema already exists
        schema_id = self.get_schema_id(schema_name)
        if schema_id:
            logger.info("ghl_scraped_leads_schema_exists", schema_id=schema_id)
            return schema_id
        
        # Create the schema
        fields = [
            {"name": "Lead Title", "dataType": "TEXT"},
            {"name": "Lead Description", "dataType": "LARGE_TEXT"},
            {"name": "Author Name", "dataType": "TEXT"},
            {"name": "Lead Category", "dataType": "TEXT"},
            {"name": "Location", "dataType": "TEXT"},
            {"name": "Source", "dataType": "TEXT"},
            {"name": "Source ID", "dataType": "TEXT"},
            {"name": "Source URL", "dataType": "TEXT"},
            {"name": "Posted Date", "dataType": "TEXT"},
            {"name": "Scraped Date", "dataType": "TEXT"},
            {"name": "Comment Count", "dataType": "NUMBER"},
            {"name": "Reaction Count", "dataType": "NUMBER"},
            {"name": "Image Count", "dataType": "NUMBER"},
            {"name": "Video Count", "dataType": "NUMBER"},
            {"name": "Word Count", "dataType": "NUMBER"},
            {"name": "Has Image", "dataType": "TEXT"},
            {"name": "Has Map", "dataType": "TEXT"},
            {"name": "Has Media", "dataType": "TEXT"},
            {"name": "Images", "dataType": "LARGE_TEXT"},
            {"name": "Videos", "dataType": "LARGE_TEXT"},
            {"name": "Extra Data", "dataType": "LARGE_TEXT"},
            {"name": "Services Requested", "dataType": "TEXT"},
            {"name": "Phone", "dataType": "TEXT"},
            {"name": "City", "dataType": "TEXT"},
            {"name": "Vertical", "dataType": "TEXT"},
        ]
        
        schema_id = self.create_custom_object_schema(schema_name, fields)
        return schema_id
    
    def _generate_deterministic_email(self, lead_data: Dict[str, Any]) -> str:
        """Centralized logic for generating a stable email from lead source data."""
        source_id = lead_data.get('source_id') or ""
        source_url = lead_data.get('source_url') or ""
        unique_key = source_id or source_url
        
        name_val = lead_data.get('name') or lead_data.get('author_name') or lead_data.get('title') or "lead"
        # Keep only alphanumeric for email part
        name_part = "".join(c for c in str(name_val).lower() if c.isalnum() or c == '_')[:20]
        if not name_part:
            name_part = "lead"
        
        # Create a stable hash based on ID/URL to prevent duplicates
        import hashlib
        id_hash = hashlib.md5(str(unique_key).encode()).hexdigest()[:8]
        return f"{name_part}_{id_hash}@scraped.local"

    def get_contact_by_email(self, email: str) -> Optional[Dict[str, Any]]:
        """Search for a contact by email address."""
        endpoint = "/contacts/"
        params = {
            "locationId": self.location_id,
            "query": email
        }
        result = self._make_request("GET", endpoint, params=params)
        if result and result.get('contacts'):
            return result['contacts'][0]
        return None

    def check_lead_exists_on_ghl(self, lead_data: Dict[str, Any]) -> bool:
        """
        Check if a lead already exists as a contact in GHL
        using its deterministic email.
        """
        email = self._generate_deterministic_email(lead_data)
        contact = self.get_contact_by_email(email)
        return contact is not None

    def save_scraped_lead(self, scraped_lead: Dict[str, Any]) -> Optional[str]:
        """
        Save a scraped lead as a Custom Object record. 
        Falls back to creating a Contact if Custom Objects are unavailable.
        """
        try:
            # TRY CUSTOM OBJECTS FIRST
            schema_id = self.ensure_scraped_leads_schema()
            if schema_id:
                # Map scraped lead to custom object record
                record_data = {}
                
                # Map text fields
                text_mappings = {
                    "title": "Lead Title",
                    "description": "Lead Description",
                    "author_name": "Author Name",
                    "category": "Lead Category",
                    "location": "Location",
                    "source": "Source",
                    "source_id": "Source ID",
                    "source_url": "Source URL",
                    "posted_date": "Posted Date",
                    "scraped_date": "Scraped Date",
                    "phone": "Phone",
                    "city": "City",
                    "vertical": "Vertical",
                }
                
                for lead_key, field_name in text_mappings.items():
                    value = scraped_lead.get(lead_key)
                    if value:
                        record_data[field_name] = str(value)
                
                # Map numeric fields
                numeric_mappings = {
                    "comment_count": "Comment Count",
                    "reaction_count": "Reaction Count",
                    "image_count": "Image Count",
                    "video_count": "Video Count",
                    "word_count": "Word Count",
                }
                
                for lead_key, field_name in numeric_mappings.items():
                    value = scraped_lead.get(lead_key)
                    if value is not None:
                        record_data[field_name] = value
                
                # Map boolean fields
                boolean_mappings = {
                    "has_image": "Has Image",
                    "has_map": "Has Map",
                    "has_media": "Has Media",
                }
                
                for lead_key, field_name in boolean_mappings.items():
                    value = scraped_lead.get(lead_key)
                    if value is not None:
                        record_data[field_name] = "Yes" if value else "No"
                
                # Map array/object fields (store as JSON)
                if scraped_lead.get('images'):
                    record_data["Images"] = json.dumps(scraped_lead['images'])
                
                if scraped_lead.get('videos'):
                    record_data["Videos"] = json.dumps(scraped_lead['videos'])
                
                if scraped_lead.get('extra_data'):
                    record_data["Extra Data"] = json.dumps(scraped_lead['extra_data'])

                if scraped_lead.get('is_service_request') is not None:
                    record_data["Services Requested"] = "Yes" if scraped_lead['is_service_request'] else "No"
                
                # Create the record
                record_id = self.create_custom_object_record(schema_id, record_data)
                if record_id:
                    return record_id

            # FALLBACK TO CONTACTS
            logger.info("falling_back_to_contacts", lead=scraped_lead.get('title'))
            
            # Try to find a name for the contact
            name = (
                scraped_lead.get('contact_name') or 
                scraped_lead.get('author_name') or 
                scraped_lead.get('title') or 
                "Scraped Lead"
            )
            # Truncate name if too long for GHL
            if len(str(name)) > 100:
                name = str(name)[:97] + "..."

            # Create a copy to handle boolean conversions
            temp_lead = scraped_lead.copy()
            for bool_key in ["has_image", "has_map", "has_media"]:
                if bool_key in temp_lead:
                    temp_lead[bool_key] = "Yes" if temp_lead[bool_key] else "No"

            # Comprehensive mapping for contact custom fields
            mapping = {
                "source": "source", # Standard field
                "city": "city",     # Standard field
                "state": "state",   # Standard field
                "reaction_count": "Reaction Count",
                "image_count": "Image Count",
                "video_count": "Video Count",
                "word_count": "Word Count",
                "posted_date": "Posted Date",
                "scraped_date": "Scraped Date",
                "has_image": "Has Image",
                "has_map": "Has Map",
                "has_media": "Has Media",
                "images": "Images",
                "videos": "Videos",
                "source_url": "source_url", # Keep at top level for email hashing
                "source_id": "Source ID",
                "author_name": "Author Name",
                "description": "Lead Description",
                "title": "Lead Title",
                "category": "Lead Category",
                "comment_count": "Comment Count",
                "is_service_request": "Services Requested",
                "phone": "phone",
                "vertical": "vertical"
            }
            
            # Also add a custom field for the URL if needed for display
            mapping["source_url_display"] = "Source URL"
            temp_lead["source_url_display"] = temp_lead.get("source_url")
            
            contact_payload = self.map_lead_to_ghl(temp_lead, mapping)
            contact_payload['name'] = name
            
            return self.upsert_contact(contact_payload)
            
        except Exception as e:
            logger.error("save_scraped_lead_failed", error=str(e), lead=scraped_lead)
            return None
    
    def map_lead_to_ghl(self, lead: Dict[str, Any], mapping: Dict[str, str]) -> Dict[str, Any]:
        """
        Map a generic lead dictionary to GHL contact structure.
        (Kept for backward compatibility)
        """
        ghl_contact = {
            "locationId": self.location_id,
            "customField": {}
        }
        
        standard_fields = [
            'firstName', 'lastName', 'name', 'email', 'phone', 
            'address1', 'city', 'state', 'country', 'postalCode', 
            'companyName', 'website', 'tags', 'source', 'source_url'
        ]
        
        for lead_key, ghl_key in mapping.items():
            value = lead.get(lead_key)
            if not value:
                continue
                
            if ghl_key in standard_fields:
                ghl_contact[ghl_key] = value
            else:
                field_id = self.get_field_id(ghl_key)
                if field_id:
                    if isinstance(value, (dict, list)):
                        ghl_contact['customField'][field_id] = json.dumps(value)
                    else:
                        ghl_contact['customField'][field_id] = str(value)
                else:
                    logger.warning("ghl_custom_field_not_found", field_name=ghl_key)
        
        if not ghl_contact['customField']:
            del ghl_contact['customField']
            
        return ghl_contact