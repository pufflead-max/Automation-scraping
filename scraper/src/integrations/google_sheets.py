"""Google Sheets API integration for lead management."""
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from typing import List, Dict, Any, Optional
import os
import pandas as pd
from datetime import datetime

class GoogleSheetsClient:
    def __init__(self, credentials_path: str, spreadsheet_id: str):
        self.credentials_path = credentials_path
        self.spreadsheet_id = spreadsheet_id
        self.scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
        self.client = None
        self.sheet = None

    def connect(self):
        """Authenticate and connect to the spreadsheet."""
        if not os.path.exists(self.credentials_path):
            raise FileNotFoundError(f"Google credentials not found at: {self.credentials_path}")
        
        creds = ServiceAccountCredentials.from_json_keyfile_name(self.credentials_path, self.scope)
        self.client = gspread.authorize(creds)
        self.sheet = self.client.open_by_key(self.spreadsheet_id)
        return self

    def push_leads(self, leads: List[Dict[str, Any]], worksheet_name: str = "Leads"):
        """Push a list of leads to a specific worksheet, including all data fields."""
        if not self.sheet:
            self.connect()

        # Ensure worksheet exists
        try:
            worksheet = self.sheet.worksheet(worksheet_name)
        except gspread.exceptions.WorksheetNotFound:
            worksheet = self.sheet.add_worksheet(title=worksheet_name, rows=1000, cols=20)

        # Prepare leads for tabular format
        df = pd.DataFrame(leads)
        if df.empty:
            return 0

        # Priority columns to show at the front
        priority_cols = [
            'scraped_date', 'posted_date', 'source', 'title', 'description', 
            'location', 'city', 'price', 'vertical', 'is_buyer_request', 
            'is_spam', 'is_vertical_match', 'source_url', 'user_email'
        ]
        
        # Identify all columns and order them (Priority first, then the rest)
        all_cols = list(df.columns)
        ordered_cols = [c for c in priority_cols if c in all_cols]
        other_cols = sorted([c for c in all_cols if c not in priority_cols])
        final_cols = ordered_cols + other_cols
        
        df = df[final_cols]
        
        # Sort by date (latest first)
        if 'scraped_date' in df.columns:
            try:
                df['_sort_date'] = pd.to_datetime(df['scraped_date'], errors='coerce')
                df.sort_values(by='_sort_date', ascending=False, inplace=True)
                df.drop(columns=['_sort_date'], inplace=True)
            except:
                pass

        # Handle NaNs and convert everything to string to avoid serialization errors in Sheets
        # This ensures nested objects/lists are shown as readable strings
        df = df.astype(str).replace(['nan', 'None', '<NA>'], '')
        
        # Prepare data for update (Headers + Values)
        data = [df.columns.values.tolist()] + df.values.tolist()
        
        # Clear sheet and update
        worksheet.clear()
        worksheet.update('A1', data)
        return len(leads)
