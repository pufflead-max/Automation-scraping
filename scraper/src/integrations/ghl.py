"""GoHighLevel integration client  """

import json
import hashlib
import requests
from typing import Dict, Any, Optional, List

try:
    from ..logger import get_logger
except ImportError:
    try:
        from logger import get_logger
    except ImportError:
        import logging
        get_logger = lambda name: logging.getLogger(name)

logger = get_logger(__name__)


class GHLClient:
    """Client for interacting with GoHighLevel API V2."""
    
    BASE_URL = "https://services.leadconnectorhq.com"
    
    # Schema field definitions
    SCRAPED_LEADS_FIELDS = [
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
    
    def __init__(self, api_key: str, location_id: str, **kwargs):
        """Initialize GHL client."""
        self.api_key = api_key
        self.location_id = location_id
        self.crm_url = kwargs.get("crm_url", "https://services.leadconnectorhq.com").rstrip("/")
        self.headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "Version": "2021-07-28"
        }
        self._custom_fields_cache: Dict[str, str] = {}
        self._custom_object_schemas: Dict[str, str] = {}
        logger.info("ghl_client_initialized", location_id=location_id)

    def _make_request(self, method: str, endpoint: str, data: Optional[Dict] = None, 
                      params: Optional[Dict] = None) -> Optional[Dict[str, Any]]:
        """Make HTTP request to GHL API."""
        try:
            response = requests.request(
                method=method,
                url=f"{self.BASE_URL}{endpoint}",
                headers=self.headers,
                json=data,
                params=params,
                timeout=30
            )
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            status_code = getattr(e.response, 'status_code', None)
            error_msg = str(e)
            
            if status_code == 403:
                logger.error("ghl_permission_denied", 
                           method=method, 
                           endpoint=endpoint, 
                           hint="Check if your Private Integration Token has the required scopes.",
                           error=error_msg)
            else:
                logger.error("ghl_api_request_failed", 
                           method=method, 
                           endpoint=endpoint,
                           status=status_code, 
                           error=error_msg)
            return None

    # ===== CUSTOM OBJECTS =====
    
    def get_custom_object_schemas(self) -> List[Dict[str, Any]]:
        """Fetch all custom object schemas for the location."""
        result = self._make_request("GET", "/objects/schemas", params={"locationId": self.location_id})
        schemas = result.get('schemas', []) if result else []
        
        # Cache schemas by name
        self._custom_object_schemas = {s['name']: s['id'] for s in schemas if 'name' in s and 'id' in s}
        logger.info("ghl_custom_object_schemas_fetched", count=len(schemas))
        return schemas
    
    def get_schema_id(self, schema_name: str) -> Optional[str]:
        """Get schema ID by name."""
        return self._custom_object_schemas.get(schema_name) or \
               (self.get_custom_object_schemas() and self._custom_object_schemas.get(schema_name))
    
    def create_custom_object_schema(self, name: str, fields: List[Dict[str, Any]]) -> Optional[str]:
        """Create a new custom object schema."""
        payload = {"locationId": self.location_id, "name": name, "fields": fields}
        result = self._make_request("POST", "/objects/schemas", data=payload)
        schema_id = result.get('id') if result else None
        if schema_id:
            logger.info("ghl_custom_object_schema_created", name=name, schema_id=schema_id)
        return schema_id
    
    def create_custom_object_record(self, schema_id: str, record_data: Dict[str, Any]) -> Optional[str]:
        """Create a custom object record."""
        endpoint = f"/locations/{self.location_id}/customObjects/{schema_id}/records"
        result = self._make_request("POST", endpoint, data=record_data)
        record_id = result.get('id') if result else None
        if record_id:
            logger.info("ghl_custom_object_record_created", schema_id=schema_id, record_id=record_id)
        return record_id
    
    def search_custom_object_records(self, schema_id: str, filters: Optional[Dict] = None) -> List[Dict[str, Any]]:
        """Search custom object records."""
        endpoint = f"/locations/{self.location_id}/customObjects/{schema_id}/records/search"
        result = self._make_request("POST", endpoint, data=filters or {})
        return result.get('records', []) if result else []
    
    # ===== CONTACTS =====
    
    def get_custom_fields(self) -> List[Dict[str, Any]]:
        """Fetch all custom fields for the location."""
        result = self._make_request("GET", f"/locations/{self.location_id}/customFields")
        fields = result.get('customFields', []) if result else []
        
        # Cache fields by name
        self._custom_fields_cache = {f['name']: f['id'] for f in fields if 'name' in f and 'id' in f}
        logger.info("ghl_custom_fields_fetched", count=len(fields))
        return fields

    def get_field_id(self, field_name: str) -> Optional[str]:
        """Get field ID by name (case-insensitive)."""
        if not self._custom_fields_cache:
            self.get_custom_fields()
        
        # Exact match or case-insensitive fallback
        return self._custom_fields_cache.get(field_name) or \
               next((v for k, v in self._custom_fields_cache.items() if k.lower() == field_name.lower()), None)

    def _prepare_contact_data(self, contact_data: Dict[str, Any]) -> Dict[str, Any]:
        """Prepare contact data for API submission."""
        data = contact_data.copy()
        
        # Set defaults
        data.setdefault('locationId', self.location_id)
        data.setdefault('name', 'Scraped Lead')
        
        # Ensure email or phone exists
        if not data.get('email') and not data.get('phone'):
            data['email'] = self._generate_deterministic_email(data)
        
        # Convert customField dict to customFields array (v2 format)
        if 'customField' in data and data['customField'] and 'customFields' not in data:
            data['customFields'] = [{"id": k, "value": v} for k, v in data['customField'].items()]
            del data['customField']
        
        # Remove internal fields
        for field in ['source_url']:
            data.pop(field, None)
        
        return data

    def create_contact(self, contact_data: Dict[str, Any]) -> Optional[str]:
        """Create a contact in GHL."""
        data = self._prepare_contact_data(contact_data)
        result = self._make_request("POST", "/contacts/", data=data)
        
        if not result:
            return None
        
        contact_id = result.get('contact', {}).get('id')
        logger.info("ghl_contact_created", contact_id=contact_id)
        return contact_id

    def upsert_contact(self, contact_data: Dict[str, Any]) -> Optional[str]:
        """Create or update a contact using upsert."""
        data = self._prepare_contact_data(contact_data)
        result = self._make_request("POST", "/contacts/upsert", data=data)
        
        if not result:
            return None
        
        contact_id = result.get('contact', {}).get('id')
        logger.info("ghl_contact_upserted", contact_id=contact_id)
        return contact_id

    def get_contact_url(self, contact_id: str) -> str:
        """Get the direct CRM link for a GHL contact."""
        return f"{self.crm_url}/v2/location/{self.location_id}/contacts/detail/{contact_id}"

    def get_contact_by_email(self, email: str) -> Optional[Dict[str, Any]]:
        """Search for a contact by email address."""
        result = self._make_request("GET", "/contacts/", params={"locationId": self.location_id, "query": email})
        return result['contacts'][0] if result and result.get('contacts') else None

    def check_lead_exists_on_ghl(self, lead_data: Dict[str, Any]) -> bool:
        """Check if a lead already exists as a contact in GHL."""
        email = self._generate_deterministic_email(lead_data)
        return self.get_contact_by_email(email) is not None

    # ===== SCRAPED LEADS =====
    
    def ensure_scraped_leads_schema(self) -> Optional[str]:
        """Ensure the 'Scraped Leads' custom object schema exists."""
        schema_name = "Scraped Leads"
        schema_id = self.get_schema_id(schema_name)
        
        if schema_id:
            logger.info("ghl_scraped_leads_schema_exists", schema_id=schema_id)
            return schema_id
        
        return self.create_custom_object_schema(schema_name, self.SCRAPED_LEADS_FIELDS)
    
    def _generate_deterministic_email(self, lead_data: Dict[str, Any]) -> str:
        """Generate a stable email from lead source data."""
        unique_key = lead_data.get('source_id') or lead_data.get('source_url') or ""
        name_val = lead_data.get('name') or lead_data.get('author_name') or lead_data.get('title') or "lead"
        name_part = "".join(c for c in str(name_val).lower() if c.isalnum() or c == '_')[:20] or "lead"
        id_hash = hashlib.md5(str(unique_key).encode()).hexdigest()[:8]
        return f"{name_part}_{id_hash}@scraped.local"

    def save_scraped_lead(self, scraped_lead: Dict[str, Any]) -> Optional[str]:
        """Save a scraped lead as a Custom Object record (fallback to Contact)."""
        user_detail = scraped_lead.get('extra_data', {}).get('user_detail')
        contact_id = None

        # 1. If user_detail exists, we should associate this lead with the TEST USER contact
        if user_detail:
            logger.info("associating_with_test_user", user=user_detail.get('email'))
            # Use upsert to get/create contact for the test user
            contact_payload = {
                "name": user_detail.get('name'),
                "email": user_detail.get('email'),
                "phone": user_detail.get('phone'),
                "tags": ["test_user_automation"]
            }
            contact_id = self.upsert_contact(contact_payload)
        
        # 2. Try custom objects first
        schema_id = self.ensure_scraped_leads_schema()
        if schema_id:
            record_data = self._map_to_custom_object(scraped_lead)
            # If we have a contact_id, associate the record
            if contact_id:
                record_data['contactId'] = contact_id
                
            record_id = self.create_custom_object_record(schema_id, record_data)
            if record_id:
                return record_id
        
        # 3. Fallback to contacts or notes
        if contact_id:
            # If we couldn't use custom objects but have a contact_id (the test user),
            # we should add the lead info as a NOTE instead of overwriting the contact.
            logger.info("falling_back_to_notes_for_test_user", contact_id=contact_id)
            return self.add_contact_note(contact_id, scraped_lead)
        
        logger.info("falling_back_to_contacts", lead=scraped_lead.get('title'))
        return self._save_as_contact(scraped_lead)

    def add_contact_note(self, contact_id: str, lead: Dict[str, Any]) -> Optional[str]:
        """Add a note to a GHL contact."""
        note_body = (
            f"NEW SCRAPED LEAD FOUND:\n"
            f"Title: {lead.get('title')}\n"
            f"Source: {lead.get('source')} ({lead.get('source_url')})\n"
            f"Author: {lead.get('author_name')}\n"
            f"Description: {lead.get('description')}\n"
            f"Vertical: {lead.get('vertical')}\n"
            f"Phone: {lead.get('phone')}\n"
            f"City: {lead.get('city')}\n"
            f"Date: {lead.get('posted_date')}"
        )
        endpoint = f"/contacts/{contact_id}/notes"
        result = self._make_request("POST", endpoint, data={"body": note_body})
        return result.get('note', {}).get('id') if result else None
    
    def _map_to_custom_object(self, lead: Dict[str, Any]) -> Dict[str, Any]:
        """Map scraped lead to custom object record."""
        record = {}
        
        # Text mappings
        text_map = {
            "title": "Lead Title", "description": "Lead Description", "author_name": "Author Name",
            "category": "Lead Category", "location": "Location", "source": "Source",
            "source_id": "Source ID", "source_url": "Source URL", "posted_date": "Posted Date",
            "scraped_date": "Scraped Date", "phone": "Phone", "city": "City", "vertical": "Vertical"
        }
        for lead_key, field_name in text_map.items():
            if lead.get(lead_key):
                record[field_name] = str(lead[lead_key])
        
        # Numeric mappings
        num_map = {
            "comment_count": "Comment Count", "reaction_count": "Reaction Count",
            "image_count": "Image Count", "video_count": "Video Count", "word_count": "Word Count"
        }
        for lead_key, field_name in num_map.items():
            if lead.get(lead_key) is not None:
                record[field_name] = lead[lead_key]
        
        # Boolean mappings
        bool_map = {"has_image": "Has Image", "has_map": "Has Map", "has_media": "Has Media"}
        for lead_key, field_name in bool_map.items():
            if lead.get(lead_key) is not None:
                record[field_name] = "Yes" if lead[lead_key] else "No"
        
        # JSON fields
        for key, field in [("images", "Images"), ("videos", "Videos"), ("extra_data", "Extra Data")]:
            if lead.get(key):
                record[field] = json.dumps(lead[key])
        
        if lead.get('is_service_request') is not None:
            record["Services Requested"] = "Yes" if lead['is_service_request'] else "No"
        
        return record
    
    def _save_as_contact(self, lead: Dict[str, Any]) -> Optional[str]:
        """Save scraped lead as contact (fallback method)."""
        # Prepare lead data
        temp_lead = lead.copy()
        for key in ["has_image", "has_map", "has_media"]:
            if key in temp_lead:
                temp_lead[key] = "Yes" if temp_lead[key] else "No"
        
        # Get name
        name = temp_lead.get('contact_name') or temp_lead.get('author_name') or temp_lead.get('title') or "Scraped Lead"
        name = (str(name)[:97] + "...") if len(str(name)) > 100 else name
        
        # Field mapping
        mapping = {
            "source": "source", "city": "city", "state": "state", "phone": "phone", "vertical": "vertical",
            "reaction_count": "Reaction Count", "image_count": "Image Count", "video_count": "Video Count",
            "word_count": "Word Count", "posted_date": "Posted Date", "scraped_date": "Scraped Date",
            "has_image": "Has Image", "has_map": "Has Map", "has_media": "Has Media",
            "images": "Images", "videos": "Videos", "source_url": "source_url", "source_id": "Source ID",
            "author_name": "Author Name", "description": "Lead Description", "title": "Lead Title",
            "category": "Lead Category", "comment_count": "Comment Count", "is_service_request": "Services Requested"
        }
        
        temp_lead["source_url_display"] = temp_lead.get("source_url")
        mapping["source_url_display"] = "Source URL"
        
        contact_payload = self.map_lead_to_ghl(temp_lead, mapping)
        contact_payload['name'] = name
        return self.upsert_contact(contact_payload)
    
    def map_lead_to_ghl(self, lead: Dict[str, Any], mapping: Dict[str, str]) -> Dict[str, Any]:
        """Map a generic lead dictionary to GHL contact structure."""
        ghl_contact = {"locationId": self.location_id, "customField": {}}
        standard_fields = ['firstName', 'lastName', 'name', 'email', 'phone', 'address1', 'city', 
                          'state', 'country', 'postalCode', 'companyName', 'website', 'tags', 'source', 'source_url']
        
        for lead_key, ghl_key in mapping.items():
            value = lead.get(lead_key)
            if not value:
                continue
            
            if ghl_key in standard_fields:
                ghl_contact[ghl_key] = value
            else:
                field_id = self.get_field_id(ghl_key)
                if field_id:
                    ghl_contact['customField'][field_id] = json.dumps(value) if isinstance(value, (dict, list)) else str(value)
                else:
                    logger.warning("ghl_custom_field_not_found", field_name=ghl_key)
        
        if not ghl_contact['customField']:
            del ghl_contact['customField']
        
        return ghl_contact