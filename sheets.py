import gspread
from google.oauth2.service_account import Credentials
from datetime import datetime
import json
import config

# === Connect to Google Sheets ===
# This function creates a connection to your Google Sheet
# using the service account credentials stored in Render
def get_sheet():
    try:
        # Define what permissions we need
        scopes = [
            "https://www.googleapis.com/auth/spreadsheets",
            "https://www.googleapis.com/auth/drive"
        ]
        
        # Load credentials from environment variable
        # The JSON string stored in Render gets converted back to a dictionary
        credentials_dict = json.loads(config.GOOGLE_CREDENTIALS_JSON)
        
        credentials = Credentials.from_service_account_info(
            credentials_dict,
            scopes=scopes
        )
        
        # Connect to Google Sheets
        client = gspread.authorize(credentials)
        
        # Open the specific sheet by ID
        sheet = client.open_by_key(config.GOOGLE_SHEETS_ID).sheet1
        
        return sheet
    except Exception as e:
        print(f"Google Sheets connection failed: {e}")
        return None


# === Log or Update Lead ===
# This is the main function Sarah calls after every conversation
# It checks if the customer already exists and updates or creates their row
def log_lead(phone, name, channel, service, address, urgency, status, last_message):
    try:
        sheet = get_sheet()
        if not sheet:
            print("Could not connect to Google Sheets")
            return False
        
        # Get current timestamp
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        # Get all existing rows
        all_rows = sheet.get_all_values()
        
        # Search for existing row with this phone number
        # We skip row 1 (headers) and search from row 2
        existing_row_index = None
        for i, row in enumerate(all_rows[1:], start=2):
            if row and row[0] == str(phone):
                existing_row_index = i
                break
        
        # Prepare the row data
        # Order must match your sheet columns exactly:
        # Phone | Name | Channel | Service | Address | Urgency | Status | Last Message | Last Updated
        row_data = [
            str(phone),
            name or "",
            channel or "WhatsApp",
            service or "",
            address or "",
            urgency or "CASUAL",
            status or "New Lead",
            last_message or "",
            now
        ]
        
        if existing_row_index:
            # Customer exists — update their row
            # We only update fields that have new information
            existing_row = all_rows[existing_row_index - 1]
            
            # Keep existing values if new ones are empty
            updated_row = [
                row_data[0],  # Phone never changes
                row_data[1] if row_data[1] else (existing_row[1] if len(existing_row) > 1 else ""),
                row_data[2] if row_data[2] else (existing_row[2] if len(existing_row) > 2 else ""),
                row_data[3] if row_data[3] else (existing_row[3] if len(existing_row) > 3 else ""),
                row_data[4] if row_data[4] else (existing_row[4] if len(existing_row) > 4 else ""),
                row_data[5] if row_data[5] else (existing_row[5] if len(existing_row) > 5 else ""),
                row_data[6],  # Status always updates
                row_data[7],  # Last message always updates
                row_data[8]   # Timestamp always updates
            ]
            
            sheet.update(f"A{existing_row_index}:I{existing_row_index}", [updated_row])
            print(f"Updated existing lead: {phone}")
        else:
            # New customer — add a new row
            sheet.append_row(row_data)
            print(f"Added new lead: {phone}")
        
        return True
        
    except Exception as e:
        print(f"Google Sheets log failed: {e}")
        return False
# === Get existing lead data ===
# When a customer messages, load their existing data from Sheets
# So Sarah remembers them even after Render restarts
def get_lead(phone):
    try:
        sheet = get_sheet()
        if not sheet:
            return None
        
        all_rows = sheet.get_all_values()
        
        for row in all_rows[1:]:
            if row and row[0] == str(phone):
                return {
                    "phone": row[0] if len(row) > 0 else None,
                    "name": row[1] if len(row) > 1 else None,
                    "channel": row[2] if len(row) > 2 else None,
                    "service": row[3] if len(row) > 3 else None,
                    "address": row[4] if len(row) > 4 else None,
                    "urgency": row[5] if len(row) > 5 else None,
                    "status": row[6] if len(row) > 6 else None,
                    "last_message": row[7] if len(row) > 7 else None,
                }
        
        return None
        
    except Exception as e:
        print(f"Get lead failed: {e}")
        return None
