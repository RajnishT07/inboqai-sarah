import os

# === GROQ (Primary AI Brain) ===
GROQ_API_KEY = os.environ.get("GROQ_API_KEY")
GROQ_MODEL = "llama-3.3-70b-versatile"

# === GEMINI (Fallback AI Brain) ===
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
GEMINI_MODEL = "gemini-2.5-flash"

# === WHATSAPP (Meta Business Cloud) ===
WHATSAPP_TOKEN = os.environ.get("WHATSAPP_TOKEN")
WHATSAPP_VERIFY_TOKEN = os.environ.get("WHATSAPP_VERIFY_TOKEN")
WHATSAPP_PHONE_ID = os.environ.get("WHATSAPP_PHONE_ID")

# === GOOGLE SHEETS (CRM) ===
GOOGLE_SHEETS_ID = os.environ.get("GOOGLE_SHEETS_ID")
GOOGLE_CREDENTIALS_JSON = os.environ.get("GOOGLE_CREDENTIALS_JSON")

# === GOOGLE CALENDAR (Booking) ===
GOOGLE_CALENDAR_ID = os.environ.get("GOOGLE_CALENDAR_ID")

# === TWILIO (Missed Call Recovery) ===
TWILIO_ACCOUNT_SID = os.environ.get("TWILIO_ACCOUNT_SID")
TWILIO_AUTH_TOKEN = os.environ.get("TWILIO_AUTH_TOKEN")
TWILIO_PHONE_NUMBER = os.environ.get("TWILIO_PHONE_NUMBER")

# === DEMO BUSINESS (Sparkle Clean USA) ===
BUSINESS_NAME = "Sparkle Clean USA"
BUSINESS_LOCATION = "Dallas, TX"
BUSINESS_HOURS = "Monday to Saturday, 8am to 6pm"
BUSINESS_SERVICES = {
    "Standard Clean": "$120",
    "Deep Clean": "$220",
    "Move-Out Clean": "$300"
}
BUSINESS_AREAS = ["Dallas", "Plano", "Frisco", "McKinney"]
