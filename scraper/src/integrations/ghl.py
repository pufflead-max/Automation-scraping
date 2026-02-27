"""GoHighLevel integration client"""

import json
import hashlib
import requests
from datetime import datetime
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
        {"name": "Owner Name", "dataType": "TEXT"},
        {"name": "Owner Email", "dataType": "TEXT"},
        {"name": "Owner Phone", "dataType": "TEXT"},
    ]
    
    def __init__(self, api_key: str, location_id: str, **kwargs):
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

    def _make_request(self, method: str, endpoint: str, data: Optional[Dict] = None, 
                       params: Optional[Dict] = None) -> Optional[Dict[str, Any]]:
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
            logger.error("ghl_api_request_failed", method=method, endpoint=endpoint, status=status_code, error=str(e))
            return None

    def get_custom_object_schemas(self) -> List[Dict[str, Any]]:
        result = self._make_request("GET", "/objects/schemas", params={"locationId": self.location_id})
        schemas = result.get('schemas', []) if result else []
        self._custom_object_schemas = {s['name']: s['id'] for s in schemas if 'name' in s and 'id' in s}
        return schemas
    
    def get_schema_id(self, schema_name: str) -> Optional[str]:
        return self._custom_object_schemas.get(schema_name) or \
               (self.get_custom_object_schemas() and self._custom_object_schemas.get(schema_name))
    
    def create_custom_object_schema(self, name: str, fields: List[Dict[str, Any]]) -> Optional[str]:
        payload = {"locationId": self.location_id, "name": name, "fields": fields}
        result = self._make_request("POST", "/objects/schemas", data=payload)
        schema_id = result.get('id') if result else None
        if schema_id:
            logger.info("ghl_custom_object_schema_created", name=name, schema_id=schema_id)
        return schema_id
    
    def create_custom_object_record(self, schema_id: str, record_data: Dict[str, Any]) -> Optional[str]:
        endpoint = f"/locations/{self.location_id}/customObjects/{schema_id}/records"
        result = self._make_request("POST", endpoint, data=record_data)
        record_id = result.get('id') if result else None
        return record_id
    
    def search_custom_object_records(self, schema_id: str, filters: Optional[Dict] = None) -> List[Dict[str, Any]]:
        endpoint = f"/locations/{self.location_id}/customObjects/{schema_id}/records/search"
        result = self._make_request("POST", endpoint, data=filters or {})
        return result.get('records', []) if result else []
    
    def get_custom_fields(self) -> List[Dict[str, Any]]:
        result = self._make_request("GET", f"/locations/{self.location_id}/customFields")
        fields = result.get('customFields', []) if result else []
        self._custom_fields_cache = {f['name']: f['id'] for f in fields if 'name' in f and 'id' in f}
        return fields

    def get_field_id(self, field_name: str) -> Optional[str]:
        if not self._custom_fields_cache:
            self.get_custom_fields()
        return self._custom_fields_cache.get(field_name) or \
               next((v for k, v in self._custom_fields_cache.items() if k.lower() == field_name.lower()), None)

    def _prepare_contact_data(self, contact_data: Dict[str, Any]) -> Dict[str, Any]:
        data = contact_data.copy()
        data.setdefault('locationId', self.location_id)
        data.setdefault('name', 'Scraped Lead')
        if not data.get('email') and not data.get('phone'):
            data['email'] = self._generate_deterministic_email(data)
        if 'customField' in data and data['customField'] and 'customFields' not in data:
            data['customFields'] = [{"id": k, "value": v} for k, v in data['customField'].items()]
            del data['customField']
        data.pop('source_url', None)
        return data

    def create_contact(self, contact_data: Dict[str, Any]) -> Optional[str]:
        data = self._prepare_contact_data(contact_data)
        result = self._make_request("POST", "/contacts/", data=data)
        return result.get('contact', {}).get('id') if result else None

    def upsert_contact(self, contact_data: Dict[str, Any]) -> Optional[str]:
        data = self._prepare_contact_data(contact_data)
        result = self._make_request("POST", "/contacts/upsert", data=data)
        return result.get('contact', {}).get('id') if result else None

    def get_contact_url(self, contact_id: str) -> str:
        return f"{self.crm_url}/v2/location/{self.location_id}/contacts/detail/{contact_id}"

    def get_contact_by_email(self, email: str) -> Optional[Dict[str, Any]]:
        result = self._make_request("GET", "/contacts/", params={"locationId": self.location_id, "query": email})
        return result['contacts'][0] if result and result.get('contacts') else None

    def get_contacts(self, limit: int = 100, query: Optional[str] = None, 
                     tags: Optional[List[str]] = None) -> List[Dict[str, Any]]:
        all_contacts = []
        # Support limit=0 for unlimited results
        fetch_all = (limit == 0 or limit is None)
        
        params = {"locationId": self.location_id, "limit": 100}
        if query: params["query"] = query
        
        while True:
            result = self._make_request("GET", "/contacts/", params=params)
            if not result: break
            
            contacts = result.get('contacts', [])
            all_contacts.extend(contacts)
            
            # Check if we should continue
            meta = result.get('meta', {})
            next_token = meta.get('nextPageToken')
            start_after_id = meta.get('startAfterId')
            start_after = meta.get('startAfter')
            
            if not fetch_all and len(all_contacts) >= limit:
                break
                
            if next_token:
                params["nextPageToken"] = next_token
            elif start_after_id and start_after:
                # GHL v2 pagination uses startAfter and startAfterId
                params["startAfterId"] = start_after_id
                params["startAfter"] = start_after
                # Ensure nextPageToken is NOT sent if we are using startAfter
                if "nextPageToken" in params: del params["nextPageToken"]
            else:
                # No more pages
                break
                
            # Adjust limit for next batch if not fetching all
            if not fetch_all:
                params["limit"] = min(100, limit - len(all_contacts))

        if tags: 
            all_contacts = [c for c in all_contacts if any(t in c.get('tags', []) for t in tags)]
            
        return all_contacts

    def check_lead_exists_on_ghl(self, lead_data: Dict[str, Any]) -> bool:
        email = self._generate_deterministic_email(lead_data)
        return self.get_contact_by_email(email) is not None

    def ensure_scraped_leads_schema(self) -> Optional[str]:
        schema_name = "Scraped Leads"
        schema_id = self.get_schema_id(schema_name)
        if schema_id: return schema_id
        return self.create_custom_object_schema(schema_name, self.SCRAPED_LEADS_FIELDS)
    
    def _generate_deterministic_email(self, lead_data: Dict[str, Any]) -> str:
        unique_key = lead_data.get('source_id') or lead_data.get('source_url') or ""
        name_val = lead_data.get('name') or lead_data.get('author_name') or lead_data.get('title') or "lead"
        name_part = "".join(c for c in str(name_val).lower() if c.isalnum() or c == '_')[:20] or "lead"
        id_hash = hashlib.md5(str(unique_key).encode()).hexdigest()[:8]
        return f"{name_part}_{id_hash}@scraped.local"

    def save_scraped_lead(self, scraped_lead: Dict[str, Any]) -> Optional[str]:
        """
        Saves a lead as a separate contact in GHL without overwriting the Contractor/User profile.
        Contractor details are stored in 'Owner' custom fields for linking.
        """
        # Generate a unique email for the LEAD (not the user) to prevent merging with Victor's customer record
        lead_email = self._generate_deterministic_email(scraped_lead)
        
        # Mapping to standalone contact with Owner details in custom fields
        mapping = {
            "source": "source", "city": "city", "vertical": "vertical",
            "title": "Lead Title", "description": "Lead Description", 
            "author_name": "Author Name", "source_url": "Source URL",
            "scraped_date": "Scraped Date", "posted_date": "Posted Date",
            # Map Contractor details to Owner custom fields
            "user_name": "Owner Name", "user_email": "Owner Email", "user_phone": "Owner Phone"
        }
        
        # Build the payload
        contact_payload = self.map_lead_to_ghl(scraped_lead, mapping)
        contact_payload['email'] = lead_email
        contact_payload['name'] = scraped_lead.get('title', 'New Lead')[:100]
        
        # Tags to identify this as a separate Lead
        tags = scraped_lead.get('tags', [])
        tags.extend(['status:lead', 'type:lead', 'scraped_lead'])
        if scraped_lead.get('source') == 'craigslist':
            tags.extend(['Dino Landscape', 'Landscaping', 'Craigslist'])
        contact_payload['tags'] = list(set(tags))

        # UPSERT the lead as a separate contact
        contact_id = self.upsert_contact(contact_payload)
        
        if contact_id:
            # Add note for full lead context
            self.add_contact_note(contact_id, scraped_lead)

        # Optional: Try Custom Object if enabled
        try:
            schema_id = self.ensure_scraped_leads_schema()
            if schema_id:
                record_data = self._map_to_custom_object(scraped_lead)
                if contact_id: record_data['contactId'] = contact_id
                self.create_custom_object_record(schema_id, record_data)
        except Exception: pass

        return contact_id

    def _save_as_contact(self, lead: Dict[str, Any]) -> Optional[str]:
        """Deprecated in favor of the new save_scraped_lead logic."""
        return self.save_scraped_lead(lead)
    
    def add_contact_note(self, contact_id: str, lead: Dict[str, Any]) -> Optional[str]:
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
        record = {}
        text_map = {
            "title": "Lead Title", "description": "Lead Description", "author_name": "Author Name",
            "category": "Lead Category", "location": "Location", "source": "Source",
            "posted_date": "Posted Date", "scraped_date": "Scraped Date", "phone": "Phone", "city": "City", "vertical": "Vertical",
            "user_name": "Owner Name", "user_email": "Owner Email", "user_phone": "Owner Phone"
        }
        for lead_key, field_name in text_map.items():
            if lead.get(lead_key): record[field_name] = str(lead[lead_key])
        
        num_map = {
            "comment_count": "Comment Count", "reaction_count": "Reaction Count",
            "image_count": "Image Count", "video_count": "Video Count", "word_count": "Word Count"
        }
        for lead_key, field_name in num_map.items():
            if lead.get(lead_key) is not None: record[field_name] = lead[lead_key]
        
        bool_map = {"has_image": "Has Image", "has_map": "Has Map", "has_media": "Has Media"}
        for lead_key, field_name in bool_map.items():
            if lead.get(lead_key) is not None: record[field_name] = "Yes" if lead[lead_key] else "No"
        
        for key, field in [("images", "Images"), ("videos", "Videos"), ("extra_data", "Extra Data")]:
            if lead.get(key): record[field] = json.dumps(lead[key])
        
        if lead.get('is_service_request') is not None:
            record["Services Requested"] = "Yes" if lead['is_service_request'] else "No"
        return record
    
    def _save_as_contact(self, lead: Dict[str, Any]) -> Optional[str]:
        temp_lead = lead.copy()
        for key in ["has_image", "has_map", "has_media"]:
            if key in temp_lead: temp_lead[key] = "Yes" if temp_lead[key] else "No"
        
        name = temp_lead.get('contact_name') or temp_lead.get('author_name') or temp_lead.get('title') or "Scraped Lead"
        name = (str(name)[:97] + "...") if len(str(name)) > 100 else name
        
        mapping = {
            "source": "source", "city": "city", "state": "state", "phone": "phone", "vertical": "vertical",
            "reaction_count": "Reaction Count", "image_count": "Image Count", "video_count": "Video Count",
            "word_count": "Word Count", "posted_date": "Posted Date", "scraped_date": "Scraped Date",
            "has_image": "Has Image", "has_map": "Has Map", "has_media": "Has Media",
            "images": "Images", "videos": "Videos", "source_url": "source_url", "source_id": "Source ID",
            "author_name": "Author Name", "description": "Lead Description", "title": "Lead Title",
            "category": "Lead Category", "comment_count": "Comment Count", "is_service_request": "Services Requested",
            "user_name": "name", "user_email": "email", "user_phone": "phone"
        }
        
        temp_lead["source_url_display"] = temp_lead.get("source_url")
        mapping["source_url_display"] = "Source URL"
        
        contact_payload = self.map_lead_to_ghl(temp_lead, mapping)
        
        # If user_name is available, use it as the primary contact name
        if temp_lead.get('user_name'):
            contact_payload['name'] = temp_lead['user_name']
        else:
            contact_payload['name'] = name # Fallback to lead title/author
            
        if temp_lead.get('tags'):
            contact_payload['tags'] = list(set(contact_payload.get('tags', []) + temp_lead['tags']))
        if temp_lead.get('pipelineId'): contact_payload['pipelineId'] = temp_lead['pipelineId']
        if temp_lead.get('pipelineStageId'): contact_payload['pipelineStageId'] = temp_lead['pipelineStageId']
        return self.upsert_contact(contact_payload)
    
    def map_lead_to_ghl(self, lead: Dict[str, Any], mapping: Dict[str, str]) -> Dict[str, Any]:
        ghl_contact = {"locationId": self.location_id, "customField": {}}
        standard_fields = ['firstName', 'lastName', 'name', 'email', 'phone', 'address1', 'city', 
                          'state', 'country', 'postalCode', 'companyName', 'website', 'tags', 'source']
        
        for lead_key, ghl_key in mapping.items():
            value = lead.get(lead_key)
            if not value: continue
            if ghl_key in standard_fields:
                ghl_contact[ghl_key] = value
            else:
                field_id = self.get_field_id(ghl_key)
                if field_id:
                    if isinstance(value, datetime):
                        val_str = value.strftime('%Y-%m-%d %H:%M:%S')
                    elif isinstance(value, (dict, list)):
                        val_str = json.dumps(value)
                    else:
                        val_str = str(value)
                    ghl_contact['customField'][field_id] = val_str
        
        if not ghl_contact['customField']: del ghl_contact['customField']
        return ghl_contact