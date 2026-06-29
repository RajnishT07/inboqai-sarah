import json
import requests
from datetime import datetime, timezone
from google import genai
import config
import supabase_db
import telegram
# === Initialize Gemini client ===
gemini_client = genai.Client(api_key=config.GEMINI_API_KEY)


# === Get time-based greeting ===
def get_time_greeting():
    # Uses UTC — Dallas TX is UTC-5 (CDT) or UTC-6 (CST)
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
    """
    Checks Supabase if this phone number has contacted us before.
    Returns a context string that gets injected into Sarah's prompt.
    If new customer, returns empty string.
    """
    try:
        existing_lead = supabase_db.get_lead_by_phone(client_id, customer_phone)
        if not existing_lead:
            return ""  # New customer, no context needed

        name = existing_lead.get("name")
        service = existing_lead.get("service")
        status = existing_lead.get("status", "").lower()
        greeting = get_time_greeting()

        # Build context based on their last booking status
        if status == "completed":
            return f"""
RETURNING CUSTOMER DETECTED:
- This customer has contacted us before
- Their name is: {name or "unknown"}
- Their last service was: {service or "a cleaning service"}
- Status: COMPLETED

YOUR FIRST MESSAGE MUST:
- Start with "{greeting} {name or "there"}! 😊 Welcome back to {config.BUSINESS_NAME}!"
- Ask how their previous {service or "service"} went
- Then naturally ask how you can help them today
- Keep it warm and personal — they are a valued returning customer
"""
        elif status == "booked":
            return f"""
RETURNING CUSTOMER DETECTED:
- This customer has an upcoming booking
- Their name is: {name or "unknown"}
- Their booked service: {service or "a cleaning service"}
- Status: BOOKED (upcoming)

YOUR FIRST MESSAGE MUST:
- Start with "{greeting} {name or "there"}! 😊 Great to hear from you!"
- Mention they have an upcoming booking
- Ask if they need to make any changes or need anything else
- Keep it warm and personal
"""
        else:
            return f"""
RETURNING CUSTOMER DETECTED:
- This customer has contacted us before
- Their name is: {name or "unknown"}

YOUR FIRST MESSAGE MUST:
- Start with "{greeting} {name or "there"}! 😊 Welcome back!"
- Ask how you can help them today
- Keep it warm and personal
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
        "DO NOT ask for phone number — you already have it from WhatsApp."
        if channel == "WhatsApp"
        else f"Ask for their phone number naturally during the conversation so the team can confirm the booking. Customer is messaging via {channel}."
    )

    return f"""You are Sarah, a warm and professional AI receptionist for {config.BUSINESS_NAME} in {config.BUSINESS_LOCATION}.

{returning_customer_context}

PERSONALITY — NEVER BREAK THESE:
- Use emojis in EVERY single message 🧹✨
- Sound like a real human — warm, friendly, enthusiastic
- Never sound robotic or scripted
- Be concise — 2 to 4 sentences max per reply
- Make every customer feel valued and heard
- Match the customer's energy — if they're casual, be casual. If they're stressed, be calm and reassuring.

BUSINESS INFORMATION:
- Business Hours: {config.BUSINESS_HOURS}
- Service Areas: {areas_text}
- Services and Pricing:
{services_text}

YOUR JOB:
Help customers by answering questions, collecting their details, and booking appointments.
Collect these 4 things naturally — never like a form, always like a conversation:
1. Customer's full name
2. Service needed (Standard Clean, Deep Clean, or Move-Out Clean)
3. Full address (must be in our service area)
4. Preferred date AND time (always ask for a specific date like "July 3rd at 2pm")
5. {phone_instruction}

CONVERSATION STYLE:
- Never ask multiple questions at once — one question per message
- If customer seems stressed or in a hurry, acknowledge it first before asking questions
- Use their name naturally once you know it — not in every single message
- If customer asks for price, give it immediately — don't make them wait
- Transition smoothly between topics — never feel like an interrogation

URGENCY DETECTION — 4 LEVELS:
Classify every lead into one of these 4 levels:

CRITICAL — needs immediate attention (within 1 hour):
- Words: "emergency", "right now", "immediately", "flooding", "disaster"
- Example: "I need cleaning RIGHT NOW, guests arriving in an hour"

HIGH — same day or next day:
- Words: "today", "tonight", "tomorrow", "ASAP", "urgent"
- Example: "Can someone come today?"

MEDIUM — specific date within a week:
- Customer mentions a date within 7 days
- Example: "Can someone come Thursday?"

LOW — general inquiry or flexible:
- Browsing, asking prices, no urgency
- Example: "What services do you offer?"

STRICT RULES — NEVER BREAK:
- Never ask for name if you already know it
- Never invent services or prices not listed above
- Never confirm a booking without all 4 details
- Never mention you are an AI unless directly asked
- Never offer discounts, refunds, or compensation
- Never promise anything you cannot deliver
- If outside service area: "We don't cover that area yet but we're expanding soon! 😊"
- For cancellations/complaints: "I'll have our team reach out within 2 hours. Can I get your name and best contact time?"
- For date like "Friday": ask "Which date would that be? For example, July 4th at 2pm 🗓"

BOOKING CONFIRMATION:
Once you have ALL 4 details, confirm like this:
"Perfect! Here's a summary of your booking:

🧹 *Service:* [service] — [price]
📍 *Address:* [full address]
🗓 *Date & Time:* [date] at [time]

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
  "appointment_time": "date and time as text or null",
  "ready_to_book": true or false
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
            "max_tokens": 600,
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
            "ready_to_book": False
        }


# === Save conversation to Supabase ===
def save_to_supabase(client_id, customer_phone, customer_message, result, channel):
    try:
        # Create or update lead in Supabase
        lead_id = supabase_db.create_or_update_lead(
            client_id=client_id,
            phone=customer_phone,
            name=result.get("name"),
            channel=channel,
            urgency=result.get("urgency", "LOW").lower()
        )

        # Save customer message
        supabase_db.save_message(
            client_id=client_id,
            lead_id=lead_id,
            role="user",
            message=customer_message,
            channel=channel
        )

        # Save Sarah's reply
        supabase_db.save_message(
            client_id=client_id,
            lead_id=lead_id,
            role="assistant",
            message=result.get("reply", ""),
            channel=channel
        )

        print(f"✅ Saved to Supabase — lead_id: {lead_id}")

        # Send Telegram notification for CRITICAL and HIGH leads
        telegram.send_telegram_notification(
            lead_name=result.get("name"),
            phone=customer_phone,
            channel=channel,
            urgency=result.get("urgency", "LOW"),
            message=customer_message,
            business_name=config.BUSINESS_NAME
        )

        return lead_id

    except Exception as e:
        print(f"❌ Supabase save failed: {e}")
        return None


# === Main Sarah Function ===
def sarah_reply(customer_message, conversation_history, customer_phone, channel="WhatsApp"):

    # Check if returning customer
    client_id = config.SPARKLE_CLEAN_CLIENT_ID
    returning_context = ""
    if client_id and not conversation_history:
        # Only check on FIRST message of conversation
        returning_context = get_returning_customer_context(customer_phone, client_id)
        if returning_context:
            print(f"🔄 Returning customer detected: {customer_phone}")
        else:
            print(f"👋 New customer: {customer_phone}")

    # Build full conversation for AI
    messages = [{"role": "system", "content": get_system_prompt(channel, returning_context)}]
    for msg in conversation_history:
        messages.append(msg)
    messages.append({"role": "user", "content": customer_message})

    # Try Groq first
    raw_reply = ask_groq(messages)

    # Fallback to Gemini
    if raw_reply is None:
        print("Switching to Gemini fallback...")
        raw_reply = ask_gemini(messages)

    # If both fail
    if raw_reply is None:
        return {
            "reply": "Hi! I'm Sarah from Sparkle Clean USA. How can I help you today? 😊",
            "urgency": "LOW",
            "name": None,
            "service": None,
            "area": None,
            "ready_to_book": False,
            "updated_history": conversation_history
        }

    # Parse reply
    result = parse_sarah_reply(raw_reply)

    # Save to Supabase
    if client_id:
        save_to_supabase(client_id, customer_phone, customer_message, result, channel)

    # Update conversation history
    conversation_history.append({"role": "user", "content": customer_message})
    conversation_history.append({"role": "assistant", "content": raw_reply})
    result["updated_history"] = conversation_history

    return result
