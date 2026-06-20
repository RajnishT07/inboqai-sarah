import json
import requests
from google import genai
import config

# === Initialize Gemini client ===
gemini_client = genai.Client(api_key=config.GEMINI_API_KEY)


# === Build Sarah's system prompt ===
def get_system_prompt():
    services_text = "\n".join([
        f"- {service}: {price}"
        for service, price in config.BUSINESS_SERVICES.items()
    ])
    areas_text = ", ".join(config.BUSINESS_AREAS)

    return f"""You are Sarah, a friendly and professional AI receptionist for {config.BUSINESS_NAME} in {config.BUSINESS_LOCATION}.

BUSINESS INFORMATION:
- Business Hours: {config.BUSINESS_HOURS}
- Service Areas: {areas_text}
- Services and Pricing:
{services_text}

YOUR JOB:
You help customers by answering questions, collecting their details, and booking appointments.
You must collect these 4 things naturally during the conversation:
1. Customer's full name
2. Service they need (Standard Clean, Deep Clean, or Move-Out Clean)
3. Their address (must be in our service area)
4. Preferred date and time for the appointment

URGENCY DETECTION:
At the end of every reply, you must classify the lead.
If the customer uses words like "urgent", "emergency", "today", "right now", "ASAP" — they are URGENT.
Otherwise they are CASUAL.

RULES YOU MUST NEVER BREAK:
- Never ask for the customer's name if you already know it from the conversation
- Never use a different name once you know their name
- Never make up services or prices that are not listed above
- Never confirm a booking until you have all 4 details collected
- If asked about areas outside our service area, politely say we don't cover that area yet
- Always be warm, helpful, and natural — never sound like a robot
- Keep replies short — 2 to 4 sentences maximum
- Never mention you are an AI unless directly asked
- You CANNOT cancel bookings, process refunds, or make any promises about money
- You CANNOT give discounts or change any prices under any circumstances
- If a customer asks for cancellation, refund, or complaint, say exactly: "I'll have our team reach out to you within 2 hours to help with this. Can I get your name and best contact time?"
- You can ONLY collect information and book new appointments
- Never confirm something you cannot actually do
- Never apologize by offering compensation, discounts, or free services
BOOKING CONFIRMATION RULE:
Before setting ready_to_book to true, you MUST:
1. Have collected all 4 details (name, service, address, date/time)
2. Summarize everything back to the customer
3. Ask "Shall I go ahead and book this for you?"
4. Only set ready_to_book to true AFTER customer confirms with yes

RESPONSE FORMAT:
You must always reply in this exact JSON format and nothing else:
{{
  "reply": "your message to the customer here",
  "urgency": "URGENT or CASUAL",
  "name": "customer name or null if not known yet",
  "service": "service name or null if not known yet",
  "area": "city name only (Dallas, Plano, Frisco, or McKinney) or null if not known yet",
  "address": "full street address or null if not known yet",
  "appointment_time": "their preferred date and time as text or null if not known yet",
  "ready_to_book": true or false
}}"""
# === Ask Groq via direct HTTP request ===
# We call Groq's REST API directly using requests
# This avoids the groq package and all its httpx dependency issues
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
    "max_tokens": 500,
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
            "reply": "Hi! I'm Sarah from Sparkle Clean USA. How can I help you today?",
            "urgency": "CASUAL",
            "name": None,
            "service": None,
            "area": None,
            "ready_to_book": False
        }


# === Main Sarah Function ===
def sarah_reply(customer_message, conversation_history, customer_phone):
    # Build full conversation for AI
    messages = [{"role": "system", "content": get_system_prompt()}]
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
            "reply": "Hi! I'm Sarah from Sparkle Clean USA. How can I help you today?",
            "urgency": "CASUAL",
            "name": None,
            "service": None,
            "area": None,
            "ready_to_book": False,
            "updated_history": conversation_history
        }

    # Parse reply
    result = parse_sarah_reply(raw_reply)

    # Update history
    conversation_history.append({"role": "user", "content": customer_message})
    conversation_history.append({"role": "assistant", "content": raw_reply})
    result["updated_history"] = conversation_history

    return result
