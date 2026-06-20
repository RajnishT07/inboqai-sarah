from googleapiclient.discovery import build
from google.oauth2.service_account import Credentials
from datetime import datetime, timedelta
import json
import requests
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
def is_slot_available(service, start_datetime, end_datetime):
    try:
        events_result = service.events().list(
            calendarId=config.GOOGLE_CALENDAR_ID,
            timeMin=start_datetime.isoformat() + "Z",
            timeMax=end_datetime.isoformat() + "Z",
            singleEvents=True
        ).execute()
        events = events_result.get("items", [])
        return len(events) == 0
    except Exception as e:
        print(f"Availability check failed: {e}")
        return False


# === Parse appointment datetime from text ===
def parse_appointment_time(date_text):
    try:
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
                    "content": f"""Today is {today} (Friday).
Convert this appointment time to ISO format: '{date_text}'
Rules:
- Use 24-hour time (2pm = 14:00, 10am = 10:00)
- If day is not specified assume next available weekday
- Reply with ONLY the ISO string like: 2026-06-21T14:00:00
- No extra text, no explanation"""
                }
            ],
            "temperature": 0,
            "max_tokens": 30
        }

        response = requests.post(url, headers=headers, json=payload, timeout=10)

        if response.status_code == 200:
            iso_string = response.json()["choices"][0]["message"]["content"].strip()
            # Clean any extra characters
            iso_string = iso_string.replace('"', '').replace("'", '').strip()
            print(f"Parsed datetime: {iso_string}")
            return datetime.fromisoformat(iso_string)
        else:
            print(f"Groq datetime parse failed: {response.text}")
            return None

    except Exception as e:
        print(f"DateTime parse failed: {e}")
        return None


# === Create Booking ===
def create_booking(name, phone, service_name, address, appointment_datetime):
    try:
        # Get calendar service connection
        cal_service = get_calendar_service()
        if not cal_service:
            return False, "Could not connect to calendar"

        # Get service price from config
        price = config.BUSINESS_SERVICES.get(service_name, "")

        # Appointment duration — 2 hours
        start_time = appointment_datetime
        end_time = appointment_datetime + timedelta(hours=2)

        # Check availability
        if not is_slot_available(cal_service, start_time, end_time):
            return False, "That time slot is already booked"

        # Build the calendar event
        event = {
            "summary": f"{service_name} — {name}",
            "location": address,
            "description": f"Customer: {name}\nPhone: {phone}\nService: {service_name}\nPrice: {price}\nAddress: {address}\nBooked via: WhatsApp (Sarah AI)",
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

        # Create the event
        created_event = cal_service.events().insert(
            calendarId=config.GOOGLE_CALENDAR_ID,
            body=event
        ).execute()

        print(f"Booking created: {created_event.get('htmlLink')}")
        return True, "Booking confirmed"

    except Exception as e:
        print(f"Booking creation failed: {e}")
        return False, str(e)
