import os
from supabase import create_client, Client

SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY")

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)


# ─── CLIENT FUNCTIONS ───────────────────────────────────────────

def get_client_by_id(client_id):
    result = supabase.table("clients").select("*").eq("id", client_id).single().execute()
    return result.data


def get_all_clients():
    result = supabase.table("clients").select("*").eq("is_active", True).execute()
    return result.data


# ─── LEAD FUNCTIONS ─────────────────────────────────────────────

def create_or_update_lead(client_id, phone, name=None, channel=None, urgency="low"):
    existing = supabase.table("leads").select("*").eq("client_id", client_id).eq("phone", phone).execute()

    if existing.data:
        lead_id = existing.data[0]["id"]
        existing_name = existing.data[0].get("name")

        # Build update object
        update_data = {"urgency": urgency}

        # ✅ Only update name if we now know it and didn't before
        if name and not existing_name:
            update_data["name"] = name

        supabase.table("leads").update(update_data).eq("id", lead_id).execute()
        return lead_id
    else:
        result = supabase.table("leads").insert({
            "client_id": client_id,
            "name": name,
            "phone": phone,
            "channel": channel,
            "urgency": urgency,
            "status": "new"
        }).execute()
        return result.data[0]["id"]


def get_leads_by_client(client_id):
    result = supabase.table("leads").select("*").eq("client_id", client_id).order("created_at", desc=True).execute()
    return result.data


def update_lead_status(lead_id, status):
    supabase.table("leads").update({"status": status}).eq("id", lead_id).execute()


# ─── CONVERSATION FUNCTIONS ──────────────────────────────────────

def save_message(client_id, lead_id, role, message, session_id=None, channel=None):
    supabase.table("conversations").insert({
        "client_id": client_id,
        "lead_id": lead_id,
        "role": role,
        "message": message,
        "session_id": session_id,
        "channel": channel
    }).execute()


def get_conversation(lead_id):
    result = supabase.table("conversations").select("*").eq("lead_id", lead_id).order("created_at", asc=True).execute()
    return result.data


def get_conversation_by_session(session_id):
    result = supabase.table("conversations").select("*").eq("session_id", session_id).order("created_at", asc=True).execute()
    return result.data


# ─── RETURNING CUSTOMER CHECK ────────────────────────────────────

def get_lead_by_phone(client_id, phone):
    result = supabase.table("leads").select("*").eq("client_id", client_id).eq("phone", phone).execute()
    if result.data:
        return result.data[0]
    return None
