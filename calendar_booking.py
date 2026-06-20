from googleapiclient.discovery import build
from google.oauth2.service_account import Credentials
from datetime import datetime, timedelta
import json
import config

# === Connect to Google Calendar ===
def get_calendar_service():
    try:
        scopes = ["https://www.googleapis.com/auth/calendar"]
        
        credentials_dict = json.loads(config.GOOGLE_CREDENTIALS_JSON)
        
        credentials = Credentials.from_service_account_info(
            credentials_dict,
            scopes=scopes
        )
        
        service = build("calendar", "v3", credentials=credentials)
        return service
    except Exception as e:
        print(f"Google Calendar connection failed: {e}")
        return None


# === Check if time slot is available ===
# Before booking, we check if the requested time is free
def is_slot_available(start_datetime, end_datetime):
    try:
        service = get_calendar_service()
        if not service:
            return False
        
        # Query calendar for events in the requested time window
        events_result = service.events().list(
            calendarId=config.GOOGLE_CALENDAR_ID,
            timeMin=start_datetime.isoformat() + "Z",
            timeMax=end_datetime.isoformat() + "Z",
            singleEvents=True
        ).execute()
        
        events = events_result.get("items", [])
        
        # If no events found in that window, slot is available
        return len(events) == 0
        
    except Exception as e:
        print(f"Availability check failed: {e}")
        return False


# === Create Booking ===
# This creates the actual appointment in Google Calendar
def create_booking(name, phone, service, address, appointment_datetime):
    try:
        service = get_calendar_service()
        if not service:
            return False, "Could not connect to calendar"
        
        # Get service price from config
        price = config.BUSINESS_SERVICES.get(service, "")
        
        # Appointment duration — 2 hours by default
        start_time = appointment_datetime
        end_time = appointment_datetime + timedelta(hours=2)
        
        # Check availability first
        if not is_slot_available(start_time, end_time):
            return False, "That time slot is already booked"
        
        # Build the calendar event
        event = {
            "summary": f"{service} — {name}",
            "location": address,
            "description": f"""
Customer: {name}
Phone: {phone}
Service: {service}
Price: {price}
Address: {address}
Booked via: WhatsApp (Sarah AI)
            """.strip(),
            "start": {
                "dateTime": start_time.isoformat(),
                "timeZone": "America/Chicago"
            },
            "end": {
                "dateTime": end_time.isoformat(),
                "timeZone": "America/Chicago"
            },
            "reminders": {
                "useDefault": False,
                "overrides": [
                    {"method": "email", "minutes": 24 * 60},
                    {"method": "popup", "minutes": 60}
                ]
            }
        }
        
        # Create the event in Google Calendar
        created_event = service.events().insert(
            calendarId=config.GOOGLE_CALENDAR_ID,
            body=event
        ).execute()
        
        print(f"Booking created: {created_event.get('htmlLink')}")
        return True, "Booking confirmed"
        
    except Exception as e:
        print(f"Booking creation failed: {e}")
        return False, str(e)


# === Parse appointment datetime from text ===
# Sarah collects date/time as text like "Friday at 10am"
# This function converts that to a real Python datetime object
def parse_appointment_time(date_text):
    try:
        # We ask Groq to convert the date text to a standard format
        # For now we use a simple approach — if it fails we return None
        from datetime import datetime
        import requests
        
        url = "https://api.groq.com/openai/v1/chat/completions"
        headers = {
            "Authorization": f"Bearer {config.GROQ_API_KEY}",
            "Content-Type": "application/json"
        }
        
        today = datetime.now().strftime("%Y-%m-%d")
        
        payload = {
            "model": config.GROQ_MODEL,
            "messages": [
                {
                    "role": "user",
                    "content": f"Today is {today}. Convert this appointment time to ISO format (YYYY-MM-DDTHH:MM:SS): '{date_text}'. Reply with ONLY the ISO datetime string, nothing else."
                }
            ],
            "temperature": 0,
            "max_tokens": 50
        }
        
        response = requests.post(url, headers=headers, json=payload, timeout=10)
        
        if response.status_code == 200:
            iso_string = response.json()["choices"][0]["message"]["content"].strip()
            print(f"Parsed datetime: {iso_string}")
            return datetime.fromisoformat(iso_string)
        else:
            return None
            
    except Exception as e:
        print(f"DateTime parse failed: {e}")
        return None
