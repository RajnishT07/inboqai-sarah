import json
import requests
from datetime import datetime, timezone
from google import genai
import config
import supabase_db
import telegram

# === Initialize Gemini client ===
gemini_client = genai.Client(api_key=config.GEMINI_API_KEY)

# === Urgency ranking — higher number = more urgent ===
URGENCY_RANK = {"LOW": 0, "MEDIUM": 1, "HIGH": 2, "CRITICAL": 3}


# === Get time-based greeting ===
def get_time_greeting():
    hour = (datetime.now(timezone.utc).hour - 5) % 24
    if 5 <= hour < 12:
        return "Good morning"
    elif 12 <= hour < 17:
        return "Good afternoon"
    elif 17 <= hour < 21:
        return "Good evening"
    else:
        return "Hey"


# === Build returning customer context ===
def get_returning_customer_context(customer_phone, client_id):
    try:
        existing_lead = supabase_db.get_lead_by_phone(client_id, customer_phone)
        if not existing_lead:
            return ""

        name = existing_lead.get("name")
        service = existing_lead.get("service")
        status = existing_lead.get("status", "").lower()
        greeting = get_time_greeting()

        if status == "completed":
            return f"""
RETURNING CUSTOMER DETECTED:
- Name: {name or "unknown"}
- Last service: {service or "a cleaning service"}
- Status: COMPLETED

YOUR FIRST MESSAGE MUST:
- Start with "{greeting} {name or "there"}! 😊 Welcome back to {config.BUSINESS_NAME}!"
- Ask how their previous {service or "service"} went
- Then naturally ask how you can help them today
"""
        elif status == "booked":
            return f"""
RETURNING CUSTOMER DETECTED:
- Name: {name or "unknown"}
- Booked service: {service or "a cleaning service"}
- Status: BOOKED (upcoming)

YOUR FIRST MESSAGE MUST:
- Start with "{greeting} {name or "there"}! 😊 Great to hear from you!"
- Mention they have an upcoming booking
- Ask if they need to make any changes or need anything else
"""
        else:
            return f"""
RETURNING CUSTOMER DETECTED:
- Name: {name or "unknown"}

YOUR FIRST MESSAGE MUST:
- Start with "{greeting} {name or "there"}! 😊 Welcome back!"
- Ask how you can help them today
"""
    except Exception as e:
        print(f"Returning customer check failed: {e}")
        return ""


# === Build Sarah's system prompt ===
def get_system_prompt(channel="WhatsApp", returning_customer_context=""):
    services_text = "\n".join([
        f"- {service}: {price}"
        for service, price in config.BUSINESS_SERVICES.items()
    ])
    areas_text = ", ".join(config.BUSINESS_AREAS)

    phone_instruction = (
        "Phone number is already known from WhatsApp — do not ask for it."
        if channel == "WhatsApp"
        else f"You MUST ask for their phone number — this is a REQUIRED field, just like name and address. Customer is messaging via {channel}, so we do not have their phone automatically. Do not confirm a booking until you have it."
    )

    return f"""You are Sarah, a warm and professional AI receptionist for {config.BUSINESS_NAME} in {config.BUSINESS_LOCATION}.

{returning_customer_context}

PERSONALITY — NEVER BREAK THESE:
- Use emojis in EVERY single message 🧹✨
- Sound like a real human — warm, friendly, enthusiastic
- Never sound robotic or scripted
- Be concise — 2 to 4 sentences max per reply
- Match the customer's energy — if they're stressed, be calm and reassuring

BUSINESS INFORMATION:
- Business Hours: {config.BUSINESS_HOURS}
- Service Areas: {areas_text}
- Services and Pricing:
{services_text}

YOUR JOB:
Help customers by answering questions, collecting their details, and booking appointments.

REQUIRED FIELDS — you CANNOT send a booking summary or confirmation until ALL 5 of these are known:
1. Customer's full name
2. Service needed (Standard Clean, Deep Clean, or Move-Out Clean)
3. Full address (must be in our service area)
4. Preferred date AND time (always ask for a specific date like "July 3rd at 2pm")
5. {phone_instruction}

HARD RULE: If channel is not WhatsApp and you do not yet have a phone number, you MUST ask for it before sending any booking summary — even if you already have name, service, address, and date/time. Do not skip straight to confirmation just because you have 4 out of 5.

ADDITIONAL DETAILS — REQUIRED for NON-URGENT customers (LOW or MEDIUM urgency) before ANY booking summary:
6. Property type (house, apartment, condo, office)
7. Approximate size (number of bedrooms/bathrooms — e.g. "3 bed 2 bath")
8. Service frequency — one-time clean, or recurring (weekly/biweekly/monthly)
9. Access constraints — will someone be home, key/code/doorman, parking instructions
10. Pets in the home

HARD RULE — DO NOT SKIP: For LOW or MEDIUM urgency customers, you are FORBIDDEN from sending a booking summary until property_type AND property_size are both known, PLUS at least one of (frequency, access_notes, pets). That means minimum 4 of these 5 fields total, not 2. Check your own state before responding: if property_type or property_size is still null and urgency is LOW/MEDIUM, your next message MUST ask for it — do not move to date/time or phone number yet, and do not send a booking summary no matter what else you know.

Ask ONE additional detail per message, woven naturally into conversation. Never dump multiple questions together.

WHEN TO SKIP ADDITIONAL DETAILS ENTIRELY: Only if urgency is CRITICAL or HIGH (words like emergency, today, ASAP, right now, flooding). In that case go straight to the 5 required fields only.

SEQUENCE TO FOLLOW (non-urgent customers):
name → service → address → property type → property size → at least 1 more of (frequency, access, pets) → date/time → phone number → THEN send booking summary

CONVERSATION STYLE:
- Never ask multiple questions at once — one question per message
- If customer seems stressed or in a hurry, acknowledge it first before asking questions
- Use their name naturally once you know it — not in every message
- If customer asks for price, give it immediately
- Transition smoothly between topics — never feel like an interrogation

URGENCY DETECTION — 4 LEVELS:
Classify the urgency based on the ENTIRE conversation so far, not just the latest message. If the customer expressed urgency earlier in the conversation, keep that urgency level even if later messages are calmer (e.g. while giving address/booking details).

CRITICAL — needs immediate attention (within 1 hour):
- Words: "emergency", "right now", "immediately", "flooding", "disaster"

HIGH — same day or next day:
- Words: "today", "tonight", "tomorrow", "ASAP", "urgent"

MEDIUM — specific date within a week:
- Customer mentions a date within 7 days

LOW — general inquiry or flexible:
- Browsing, asking prices, no urgency mentioned anywhere in the conversation

ESCALATION RULE — WHEN TO FLAG FOR HUMAN REVIEW:
You must set "needs_review": true and use the escalation reply below whenever:
- The customer asks something outside normal cleaning service scope (e.g. unusual chemicals, biohazard, hoarding situation, mold remediation, pest infestation cleanup, post-construction debris removal)
- The customer requests something you're not confident you can answer correctly (custom pricing, complex multi-property deals, commercial contracts beyond standard service)
- The customer's request is ambiguous or contradicts itself and you cannot resolve it after one clarifying question
- The customer is angry, threatening, or the situation feels high-risk (legal threats, safety concerns, abusive language)
- Anything else where guessing or making up an answer could create a problem for the business

When you set needs_review to true, your reply MUST be exactly this (fill in name if known):
"Thanks for sharing that, [name]! This is something our team needs to look at personally so we get it right for you. I've flagged this and someone will reach out within 2 hours. Is there a good number or time to reach you? 😊"

Do NOT try to solve, price, or promise anything in an escalated conversation. Do NOT guess. Once needs_review is true, stay in "collect contact info only" mode until a human takes over.

STRICT RULES — NEVER BREAK:
- Never ask for name if you already know it
- Never invent services or prices not listed above
- Never confirm a booking without all 5 REQUIRED fields (name, service, address, date/time, phone)
- Never mention you are an AI unless directly asked
- Never offer discounts, refunds, or compensation
- If outside service area: "We don't cover that area yet but we're expanding soon! 😊"
- For cancellations/complaints: "I'll have our team reach out within 2 hours. Can I get your name and best contact time?"
- For vague dates like "Friday": ask "Which date would that be? For example, July 4th at 2pm 🗓"

BOOKING CONFIRMATION:
Once you have ALL 5 REQUIRED details (name, service, address, date/time, phone), confirm like this:
"Perfect! Here's a summary of your booking:

🧹 *Service:* [service] — [price]
📍 *Address:* [full address]
🗓 *Date & Time:* [date] at [time]
📞 *Phone:* [phone]

Shall I go ahead and lock this in for you? ✅"

After customer confirms YES:
"✅ *You're all booked, [name]!*

🧹 *Service:* [service] — [price]
📍 *Address:* [full address]
🗓 *Date & Time:* [date] at [time]

We'll see you then! Feel free to message us anytime if you need anything. 😊"

RESPONSE FORMAT — always reply in this exact JSON, nothing else:
{{
  "reply": "your message to the customer",
  "urgency": "CRITICAL or HIGH or MEDIUM or LOW",
  "name": "customer name or null",
  "service": "service name or null",
  "area": "city name only or null",
  "address": "full street address or null",
  "phone_number": "phone number or null (only for non-WhatsApp channels)",
  "appointment_time": "date and time as text or null",
  "property_type": "house/apartment/condo/office or null",
  "property_size": "e.g. 3 bed 2 bath or null",
  "frequency": "one-time/weekly/biweekly/monthly or null",
  "access_notes": "access constraints or null",
  "pets": "pet info or null",
  "ready_to_book": true or false,
  "booking_confirmed": true or false,
  "needs_review": true or false
}}"""


# === Ask Groq via direct HTTP request ===
def ask_groq(conversation_history):
    try:
        url = "https://api.groq.com/openai/v1/chat/completions"
        headers = {
            "Authorization": f"Bearer {config.GROQ_API_KEY}",
            "Content-Type": "application/json"
        }
        payload = {
            "model": config.GROQ_MODEL,
            "messages": conversation_history,
            "temperature": 0.7,
            "max_tokens": 700,
            "response_format": {"type": "json_object"}
        }
        response = requests.post(url, headers=headers, json=payload, timeout=30)
        print(f"Groq status code: {response.status_code}")
        print(f"Groq response: {response.text[:200]}")
        if response.status_code == 200:
            content = response.json()["choices"][0]["message"]["content"]
            print(f"Groq content: {content[:100]}")
            return content
        else:
            print(f"Groq HTTP error: {response.status_code} - {response.text}")
            return None
    except Exception as e:
        print(f"Groq failed: {e}")
        return None


# === Ask Gemini (Fallback) ===
def ask_gemini(conversation_history):
    try:
        prompt = ""
        for msg in conversation_history:
            if msg["role"] == "system":
                prompt += f"INSTRUCTIONS: {msg['content']}\n\n"
            elif msg["role"] == "user":
                prompt += f"Customer: {msg['content']}\n"
            elif msg["role"] == "assistant":
                prompt += f"Sarah: {msg['content']}\n"
        response = gemini_client.models.generate_content(
            model=config.GEMINI_MODEL,
            contents=prompt
        )
        return response.text
    except Exception as e:
        print(f"Gemini failed: {e}")
        return None


# === Parse Sarah's JSON reply ===
def parse_sarah_reply(raw_reply):
    try:
        raw_reply = raw_reply.strip()
        if "```json" in raw_reply:
            raw_reply = raw_reply.split("```json")[1].split("```")[0].strip()
        elif "```" in raw_reply:
            raw_reply = raw_reply.split("```")[1].split("```")[0].strip()
        return json.loads(raw_reply)
    except Exception as e:
        print(f"JSON parse failed: {e}")
        return {
            "reply": "Hi! I'm Sarah from Sparkle Clean USA. How can I help you today? 😊",
            "urgency": "LOW",
            "name": None,
            "service": None,
            "area": None,
            "ready_to_book": False,
            "booking_confirmed": False,
            "needs_review": False
        }


# === Apply sticky urgency — never let urgency downgrade within a conversation ===
def apply_sticky_urgency(new_urgency, conversation_history):
    """
    Looks back through conversation_history for any previous urgency level
    Sarah assigned in this conversation, and ensures the urgency never decreases.
    """
    highest_seen = URGENCY_RANK.get(new_urgency.upper(), 0)

    for msg in conversation_history:
        if msg.get("role") == "assistant":
            try:
                parsed = json.loads(msg["content"])
                prev_urgency = parsed.get("urgency", "LOW").upper()
                rank = URGENCY_RANK.get(prev_urgency, 0)
                if rank > highest_seen:
                    highest_seen = rank
            except Exception:
                continue

    # Convert rank back to label
    for label, rank in URGENCY_RANK.items():
        if rank == highest_seen:
            return label
    return new_urgency.upper()


# === Send Telegram notification ===
# NOTE: Supabase saving (leads + conversations) happens in app.py
def notify_telegram(client_id, customer_phone, customer_message, result, channel):
    try:
        telegram.send_telegram_notification(
            lead_name=result.get("name"),
            phone=customer_phone,
            channel=channel,
            urgency=result.get("urgency", "LOW"),
            message=customer_message,
            business_name=config.BUSINESS_NAME
        )
    except Exception as e:
        print(f"❌ Telegram error: {e}")


# === Main Sarah Function ===
def sarah_reply(customer_message, conversation_history, customer_phone, channel="WhatsApp"):

    client_id = config.SPARKLE_CLEAN_CLIENT_ID
    returning_context = ""
    if client_id and not conversation_history:
        returning_context = get_returning_customer_context(customer_phone, client_id)
        if returning_context:
            print(f"🔄 Returning customer detected: {customer_phone}")
        else:
            print(f"👋 New customer: {customer_phone}")

    messages = [{"role": "system", "content": get_system_prompt(channel, returning_context)}]
    for msg in conversation_history:
        messages.append(msg)
    messages.append({"role": "user", "content": customer_message})

    raw_reply = ask_groq(messages)

    if raw_reply is None:
        print("Switching to Gemini fallback...")
        raw_reply = ask_gemini(messages)

    if raw_reply is None:
        return {
            "reply": "Hi! I'm Sarah from Sparkle Clean USA. How can I help you today? 😊",
            "urgency": "LOW",
            "name": None,
            "service": None,
            "area": None,
            "ready_to_book": False,
            "booking_confirmed": False,
            "needs_review": False,
            "updated_history": conversation_history
        }

    result = parse_sarah_reply(raw_reply)

    # ✅ Apply sticky urgency — never downgrade within the same conversation
    sticky_urgency = apply_sticky_urgency(result.get("urgency", "LOW"), conversation_history)
    result["urgency"] = sticky_urgency

    # Send Telegram notification — Supabase saving happens in app.py
    if client_id:
        notify_telegram(client_id, customer_phone, customer_message, result, channel)

    conversation_history.append({"role": "user", "content": customer_message})
    conversation_history.append({"role": "assistant", "content": raw_reply})
    result["updated_history"] = conversation_history

    return result
